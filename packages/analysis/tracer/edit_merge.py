"""
Golf Tracer Studio R4 — Copy-on-Write Manual Edit & Anchor Merger (`edit_merge.py`).
負責將使用者於 Studio 編輯器執行之手動操作：
1. 錨點調整 (`address_pts_us`, `top_pts_us`, `impact_pts_us`, `finish_pts_us`, `launch_pts_us`, `apex_pts_us`, `landing_pts_us`)
2. 逐幀軌跡點編輯 (`add`, `move`, `delete`)
3. 局部重算 (`interpolate_between_manual_anchors`) 與可選藝術延伸 (`artistic_extension_enabled`)
合併為全新不可變修訂版 (`revision = parent_revision + 1`)，
同時保證：
- 絕不覆寫原始 `Revision 1` 自動推論軌跡。
- 絕不修改 R3 主系統 `SwingEvent`, `SwingScore`, `PoseArtifact` 資料表。
- 所有人工新增/移動點嚴格標記 `source_type='manually_annotated'`, `position_role='manual_anchor'`, `created_by='user'`。
"""

from dataclasses import dataclass, field
from typing import Any

from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    TrackSourceType,
    TrackType,
)
from packages.analysis.tracer.interpolation import (
    generate_artistic_ballistic_extension,
    interpolate_pts_gap,
)
from packages.analysis.tracer.segment_context import classify_swing_phase_at_pts


@dataclass(frozen=True)
class ManualPointEditOp:
    """單筆逐幀手動編輯指令。"""

    op: str  # "add" | "move" | "delete"
    source_pts_us: int
    source_frame_index: int = 0
    x_norm: float | None = None
    y_norm: float | None = None
    point_role: str = "manual_anchor"  # "manual_anchor" | "artistic_control"
    note: str = ""


@dataclass(frozen=True)
class StudioAnchorOverrides:
    """Studio 專案層級之時間/空間錨點覆寫（與 R3 SwingEvent 完全隔離）。"""

    address_pts_us: int | None = None
    top_pts_us: int | None = None
    impact_pts_us: int | None = None
    finish_pts_us: int | None = None
    launch_pts_us: int | None = None
    apex_pts_us: int | None = None
    landing_pts_us: int | None = None
    apex_xy_norm: tuple[float, float] | None = None
    landing_xy_norm: tuple[float, float] | None = None
    artistic_extension_enabled: bool = False
    recompute_between_manual_anchors: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def apply_manual_edits_copy_on_write(
    base_points: list[CanonicalTrackPoint],
    track_type: TrackType,
    track_id: str,
    segment_id: str,
    source_video_id: str,
    new_revision: int,
    edits: list[ManualPointEditOp],
    anchors: StudioAnchorOverrides | None = None,
    frame_pts_timeline: list[tuple[int, int]] | None = None,  # [(source_pts_us, source_frame_index), ...]
) -> list[CanonicalTrackPoint]:
    """
    以 Copy-on-Write 模式套用手動點位與錨點編輯，回傳全新 `CanonicalTrackPoint` 列表。
    """
    anchor_cfg = anchors or StudioAnchorOverrides()

    # 1. 複製基底點位（按 source_pts_us 建立索引，避免變動原物件）
    pts_map: dict[int, CanonicalTrackPoint] = {}
    for pt in base_points:
        # 若為上一輪重算產生的 interpolated 或 artistic_only 點，且本次要重算，先略過以便重新產生
        if anchor_cfg.recompute_between_manual_anchors and pt.source_type == TrackSourceType.INTERPOLATED:
            continue
        if pt.source_type == TrackSourceType.ARTISTIC_ONLY:
            continue
        pts_map[pt.source_pts_us] = pt.model_copy(deep=True)

    # 2. 依序套用 delete / add / move 操作
    for edit in edits:
        op = edit.op.lower().strip()
        target_pts = int(edit.source_pts_us)

        if op == "delete":
            # 也支援尋找距離 <= 8ms 的最近點刪除
            matched_pts = _find_nearest_pts_key(pts_map, target_pts, tolerance_us=8_500)
            if matched_pts is not None:
                del pts_map[matched_pts]
            continue

        if op in ("add", "move"):
            if edit.x_norm is None or edit.y_norm is None:
                raise ValueError(f"手動編輯 {op} 必須提供 x_norm 與 y_norm")
            x_val = round(min(1.0, max(0.0, float(edit.x_norm))), 6)
            y_val = round(min(1.0, max(0.0, float(edit.y_norm))), 6)

            matched_pts = _find_nearest_pts_key(pts_map, target_pts, tolerance_us=8_500)
            use_pts = matched_pts if (op == "move" and matched_pts is not None) else target_pts
            existing = pts_map.get(use_pts)
            frame_idx = (
                existing.source_frame_index
                if existing is not None
                else max(0, int(edit.source_frame_index))
            )

            is_artistic = edit.point_role == "artistic_control"
            phase_str = _resolve_phase_for_point(track_type, use_pts, anchor_cfg)

            pts_map[use_pts] = CanonicalTrackPoint(
                track_id=track_id,
                track_type=track_type,
                segment_id=segment_id,
                source_video_id=source_video_id,
                source_pts_us=use_pts,
                source_frame_index=frame_idx,
                x_norm=x_val,
                y_norm=y_val,
                confidence=0.95 if not is_artistic else 0.25,
                source_type=(
                    TrackSourceType.ARTISTIC_ONLY
                    if is_artistic
                    else TrackSourceType.MANUALLY_ANNOTATED
                ),
                position_role=(
                    PositionRole.ARTISTIC_CONTROL
                    if is_artistic
                    else PositionRole.MANUAL_ANCHOR
                ),
                raw_observation={
                    "x_norm": x_val,
                    "y_norm": y_val,
                    "bbox": [max(0.0, x_val - 0.01), max(0.0, y_val - 0.01), min(1.0, x_val + 0.01), min(1.0, y_val + 0.01)],
                    "uncertainty_px": 1.5,
                    "detector_confidence": 1.0,
                    "evidence_kind": "manual_click",
                },
                phase=phase_str,
                model_id="studio_manual_editor_v1",
                evidence_frame_sha256=existing.evidence_frame_sha256 if existing else None,
                occlusion_state=(
                    OcclusionState.UNOBSERVABLE if is_artistic else OcclusionState.VISIBLE
                ),
                uncertainty_px=1.5 if not is_artistic else 20.0,
                error_flags=[] if not is_artistic else ["artistic_control_point"],
                created_by="user" if not is_artistic else "artist",
                revision=new_revision,
            )

    # 3. 更新所有點位之 revision 與對應錨點之揮桿階段 (Top / Impact 分色)
    sorted_pts = sorted(pts_map.values(), key=lambda p: p.source_pts_us)
    updated_points: list[CanonicalTrackPoint] = []
    for pt in sorted_pts:
        new_phase = _resolve_phase_for_point(track_type, pt.source_pts_us, anchor_cfg, fallback=pt.phase)
        updated_points.append(
            pt.model_copy(
                update={
                    "phase": new_phase,
                    "revision": new_revision,
                }
            )
        )

    # 4. 若開啟局部錨點間重算，針對相鄰錨點間缺漏之影格進行 PTS 感知 Hermite 內插
    if anchor_cfg.recompute_between_manual_anchors and len(updated_points) >= 2:
        updated_points = _fill_manual_anchor_gaps(
            points=updated_points,
            track_type=track_type,
            anchor_cfg=anchor_cfg,
            frame_pts_timeline=frame_pts_timeline,
            revision=new_revision,
        )

    # 5. 若為 ball 軌跡且啟用 artistic_extension_enabled + 具備 landing_xy_norm，附加標記為 artistic_only 之延伸段
    if (
        track_type == TrackType.BALL
        and anchor_cfg.artistic_extension_enabled
        and anchor_cfg.landing_xy_norm is not None
        and updated_points
    ):
        last_obs_pts = updated_points[-1].source_pts_us
        last_obs_fidx = updated_points[-1].source_frame_index
        target_end_pts = anchor_cfg.landing_pts_us or (last_obs_pts + 600_000)
        if target_end_pts <= last_obs_pts:
            target_end_pts = last_obs_pts + 450_000

        ext_timeline: list[tuple[int, int]] = []
        if frame_pts_timeline:
            ext_timeline = [
                (pts, fidx)
                for pts, fidx in frame_pts_timeline
                if last_obs_pts < pts <= target_end_pts
            ]
        if not ext_timeline:
            step_us = 16_667
            cur_pts = last_obs_pts + step_us
            cur_fidx = last_obs_fidx + 1
            while cur_pts <= target_end_pts:
                ext_timeline.append((cur_pts, cur_fidx))
                cur_pts += step_us
                cur_fidx += 1

        artistic_pts = generate_artistic_ballistic_extension(
            observed_points=updated_points,
            apex_xy_norm=anchor_cfg.apex_xy_norm,
            landing_xy_norm=anchor_cfg.landing_xy_norm,
            extension_pts_timeline=ext_timeline,
            revision=new_revision,
        )
        updated_points.extend(artistic_pts)

    updated_points.sort(key=lambda p: p.source_pts_us)
    return updated_points


def _find_nearest_pts_key(
    pts_map: dict[int, CanonicalTrackPoint],
    target_pts_us: int,
    tolerance_us: int = 8_500,
) -> int | None:
    if target_pts_us in pts_map:
        return target_pts_us
    best_k: int | None = None
    best_diff = tolerance_us + 1
    for k in pts_map:
        d = abs(k - target_pts_us)
        if d <= tolerance_us and d < best_diff:
            best_diff = d
            best_k = k
    return best_k


def _resolve_phase_for_point(
    track_type: TrackType,
    pts_us: int,
    anchor_cfg: StudioAnchorOverrides,
    fallback: str = "unknown",
) -> str:
    if track_type == TrackType.BALL:
        return "follow_through"
    if (
        anchor_cfg.address_pts_us is None
        and anchor_cfg.top_pts_us is None
        and anchor_cfg.impact_pts_us is None
        and anchor_cfg.finish_pts_us is None
    ):
        return fallback if fallback != "unknown" else "downswing"
    return classify_swing_phase_at_pts(
        pts_us=pts_us,
        address_pts_us=anchor_cfg.address_pts_us,
        top_pts_us=anchor_cfg.top_pts_us,
        impact_pts_us=anchor_cfg.impact_pts_us,
        finish_pts_us=anchor_cfg.finish_pts_us,
    )


def _fill_manual_anchor_gaps(
    points: list[CanonicalTrackPoint],
    track_type: TrackType,
    anchor_cfg: StudioAnchorOverrides,
    frame_pts_timeline: list[tuple[int, int]] | None,
    revision: int,
) -> list[CanonicalTrackPoint]:
    """
    當兩個相鄰點其中至少一個為 `manually_annotated` 且時間間隔介於 24ms ~ 450ms 時，
    自動於中間幀進行平滑插值 (`interpolated`)，使手動拉動錨點即刻更新整段平滑曲線。
    """
    result: list[CanonicalTrackPoint] = []
    for i in range(len(points) - 1):
        p_curr = points[i]
        p_next = points[i + 1]
        result.append(p_curr)

        gap_us = p_next.source_pts_us - p_curr.source_pts_us
        involves_manual = (
            p_curr.source_type == TrackSourceType.MANUALLY_ANNOTATED
            or p_next.source_type == TrackSourceType.MANUALLY_ANNOTATED
        )
        if not involves_manual or gap_us < 24_000 or gap_us > 550_000:
            continue

        intermediate_frames: list[tuple[int, int, str]] = []
        if frame_pts_timeline:
            for f_pts, f_idx in frame_pts_timeline:
                if p_curr.source_pts_us + 8_000 < f_pts < p_next.source_pts_us - 8_000:
                    phase = _resolve_phase_for_point(track_type, f_pts, anchor_cfg, fallback=p_curr.phase)
                    intermediate_frames.append((f_pts, f_idx, phase))
        else:
            step_us = 16_667
            n_steps = max(1, int(round(gap_us / float(step_us))) - 1)
            for s in range(1, n_steps + 1):
                f_pts = int(round(p_curr.source_pts_us + (gap_us * s) / float(n_steps + 1)))
                f_idx = p_curr.source_frame_index + s
                phase = _resolve_phase_for_point(track_type, f_pts, anchor_cfg, fallback=p_curr.phase)
                intermediate_frames.append((f_pts, f_idx, phase))

        if intermediate_frames:
            interp_pts = interpolate_pts_gap(
                start_pt=p_curr,
                end_pt=p_next,
                intermediate_frames=intermediate_frames,
                revision=revision,
            )
            result.extend(interp_pts)

    result.append(points[-1])
    return result
