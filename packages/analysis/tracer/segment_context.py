"""
Golf Tracer Studio R4 — Segment & Event Context Resolver (`segment_context.py`).
重用既有 R3 SwingSegment 與 SwingEvent，並提供 Tracer 專屬之獨立 Anchor Override。
嚴格保證：修改 Tracer Studio 內部 Top / Impact 錨點絕不覆寫 R3 資料庫之 SwingEvent、SwingScore 或 PoseArtifact。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.analysis.tracer.media_clock import (
    MediaClockTimeline,
    build_rational_cfr_timeline,
    extract_clip_pts_timeline,
)
from packages.analysis.tracer.transforms import FrameGeometry
from packages.storage.s3_client import get_storage_service


class SourceUnavailableError(Exception):
    """當高解析原始影片遺失或無法讀取時拋出，禁止靜默退化為低畫質 Proxy。"""

    def __init__(self, message: str, video_id: str = "", storage_key: str = "") -> None:
        super().__init__(message)
        self.code = "SOURCE_UNAVAILABLE"
        self.video_id = video_id
        self.storage_key = storage_key


@dataclass(frozen=True)
class ResolvedSegmentContext:
    segment_id: str
    video_id: str
    session_id: str
    owner_id: str
    source_storage_key: str
    source_sha256: str
    handedness: str  # "right" | "left"
    camera_angle: str  # "DTL" | "FO" | other
    club_type: str
    segment_start_pts_us: int
    segment_end_pts_us: int
    takeaway_pts_us: int
    top_pts_us: int | None
    impact_pts_us: int | None
    finish_pts_us: int
    anchor_source: str  # "r3_events" | "tracer_anchor_override" | "missing_events"
    top_source: str = "missing"  # "observed" | "r3_estimated" | "user_manual" | "missing"
    impact_source: str = "missing"  # "observed" | "r3_estimated" | "user_manual" | "missing"
    launch_pts_us: int | None = None
    launch_xy_norm: tuple[float, float] | None = None
    anchor_revision_id: str | None = None
    rounding_errors_us: dict[str, int] = field(default_factory=dict)
    wrist_hints_by_ms: dict[int, tuple[float, float]] = field(default_factory=dict)
    r3_confidence: float = 0.8
    source_video_path: Path | None = None
    geometry: FrameGeometry = field(default_factory=lambda: FrameGeometry(1080, 1920, 0))
    timeline: MediaClockTimeline | None = None

    @property
    def source_video_id(self) -> str:
        return self.video_id

    @property
    def view_angle(self) -> str:
        return self.camera_angle

    @property
    def start_pts_us(self) -> int:
        return self.segment_start_pts_us

    @property
    def end_pts_us(self) -> int:
        return self.segment_end_pts_us

    @property
    def address_pts_us(self) -> int:
        return self.takeaway_pts_us

    def lookup_wrist_norm_at_pts(
        self,
        pts_us: int,
        max_delta_us: int = 180_000,
    ) -> tuple[float, float] | None:
        if not self.wrist_hints_by_ms:
            return None
        target_ms = int(round(pts_us / 1000.0))
        nearest_ms = min(self.wrist_hints_by_ms.keys(), key=lambda k: abs(k - target_ms))
        if abs(nearest_ms * 1000 - pts_us) <= max_delta_us:
            return self.wrist_hints_by_ms[nearest_ms]
        return None


def _resolve_local_video_path(
    source_storage_key: str,
    explicit_video_path: str | Path | None = None,
    video_id: str = "",
) -> Path:
    if explicit_video_path is not None:
        p = Path(explicit_video_path)
        if p.exists() and p.stat().st_size > 0:
            return p
        raise SourceUnavailableError(
            f"指定的高解析原始影片不存在: {p}",
            video_id=video_id,
            storage_key=source_storage_key,
        )

    cand = Path(source_storage_key)
    if cand.is_absolute() and cand.exists() and cand.stat().st_size > 0:
        return cand

    try:
        storage = get_storage_service()
        # 1. 優先檢查本地磁碟物件儲存目錄
        if hasattr(storage, "local_service"):
            local_p = storage.local_service._resolve(source_storage_key)
            if local_p.exists() and local_p.stat().st_size > 0:
                return local_p
        # 2. 若存於 S3/MinIO，下載至本地快取路徑後回傳
        safe_rel = str(source_storage_key).strip("/")
        cache_dir = Path(getattr(storage.local_service, "base_dir", "/tmp/gsl_storage_cache")) / "_tracer_media_cache"
        cached_p = cache_dir / safe_rel
        if cached_p.exists() and cached_p.stat().st_size > 0:
            return cached_p
        downloaded = storage.download_to_path(source_storage_key, cached_p)
        if downloaded.exists() and downloaded.stat().st_size > 0:
            return downloaded
    except Exception:
        pass

    raise SourceUnavailableError(
        f"無法在本機儲存區找到高解析原始影片 ({source_storage_key})，拒絕退化使用低解析度 Proxy",
        video_id=video_id,
        storage_key=source_storage_key,
    )


def resolve_segment_context(
    segment_id: str,
    video_id: str,
    session_id: str = "",
    owner_id: str = "",
    source_storage_key: str | None = None,
    source_sha256: str | None = None,
    start_ms: int = 0,
    end_ms: int = 3000,
    events: list[dict[str, Any]] | None = None,
    keyframes: list[dict[str, Any]] | None = None,
    handedness: str = "right",
    camera_angle: str = "DTL",
    club_type: str = "7I",
    r3_confidence: float = 0.8,
    anchor_override: dict[str, Any] | None = None,
    pts_snapping_fn: Any | None = None,
    *,
    proxy_storage_key: str | None = None,
    pose_keyframes: list[dict[str, Any]] | None = None,
    view_angle: str | None = None,
    source_video_path: str | Path | None = None,
    coded_width: int = 1080,
    coded_height: int = 1920,
    rotation: int = 0,
) -> ResolvedSegmentContext:
    """
    將 R3 SwingSegment 與 SwingEvent 解析為微秒級 `source_pts_us` 錨點；
    嚴格誠信原則 (P0-1)：
    - 禁止在缺少事件時使用 `start + 0.48 * span` 或 `start + 0.68 * span` 等固定比例假時間戳冒充 Top / Impact。
    - 明確標註 `top_source` 與 `impact_source` (`observed` / `r3_estimated` / `user_manual` / `missing`)。
    - 若提供 `anchor_override`（來自 `tracer_anchor_revisions`），僅在 Studio 上下文中覆蓋錨點，
      不修改傳入之 `events` 列表或任何 R3 資料表。
    """
    _ = proxy_storage_key  # 嚴禁退回使用 proxy_storage_key！
    if not source_storage_key or not str(source_storage_key).strip():
        raise SourceUnavailableError(
            "找不到原始高解析影片 storage_key，禁止使用低解析 Proxy 冒充高畫質追蹤來源",
            video_id=video_id,
        )

    eff_angle = str(view_angle if view_angle is not None else camera_angle or "DTL").upper()
    eff_keyframes = pose_keyframes if pose_keyframes is not None else keyframes

    local_video_path: Path | None = None
    tl: MediaClockTimeline | None = None
    geom = FrameGeometry(coded_width=coded_width, coded_height=coded_height, rotation=rotation)

    # 若未顯式傳入 pts_snapping_fn，嘗試定位本機原片並擷取真實 MediaClockTimeline
    try:
        local_video_path = _resolve_local_video_path(
            str(source_storage_key),
            explicit_video_path=source_video_path,
            video_id=video_id,
        )
        tl = extract_clip_pts_timeline(local_video_path, start_ms=start_ms, end_ms=end_ms)
        geom = FrameGeometry(
            coded_width=tl.coded_width,
            coded_height=tl.coded_height,
            rotation=tl.rotation,
        )
        if pts_snapping_fn is None:
            pts_snapping_fn = tl.snap_ms_to_pts_us
    except SourceUnavailableError:
        if pts_snapping_fn is None and source_video_path is None:
            if "/" in str(source_storage_key) or str(source_storage_key).endswith((".mp4", ".mov", ".MOV", ".MP4")):
                try:
                    _resolve_local_video_path(str(source_storage_key), video_id=video_id)
                except SourceUnavailableError:
                    raise
    except Exception:
        pass

    if tl is None:
        dur_us = max(1_000_000, int(end_ms) * 1000 + 500_000)
        tl = MediaClockTimeline(
            video_path=str(local_video_path or source_storage_key),
            duration_us=dur_us,
            fps_num=60,
            fps_den=1,
            is_vfr=False,
            rotation=geom.normalized_rotation,
            coded_width=geom.coded_width,
            coded_height=geom.coded_height,
            has_audio=True,
            codec="h264",
            frames=list(build_rational_cfr_timeline(duration_us=dur_us, fps_num=60, fps_den=1)),
            clock_source="rational_cfr_grid",
        )

    rounding_errors: dict[str, int] = {}

    def _to_pts(ms_val: int, key_name: str) -> int:
        if pts_snapping_fn is not None:
            pts_us, _, err_us = pts_snapping_fn(ms_val)
            rounding_errors[key_name] = int(err_us)
            return int(pts_us)
        rounding_errors[key_name] = 0
        return int(ms_val) * 1000

    seg_start_us = _to_pts(start_ms, "segment_start")
    seg_end_us = max(seg_start_us + 100_000, _to_pts(end_ms, "segment_end"))

    ev_map: dict[str, int] = {}
    ev_conf: dict[str, float] = {}
    for ev in events or []:
        ename = str(ev.get("event_name") or "").lower()
        tms = ev.get("time_ms")
        if ename and tms is not None:
            ev_map[ename] = int(tms)
            ev_conf[ename] = float(ev.get("confidence") if ev.get("confidence") is not None else 0.7)

    takeaway_ms = ev_map.get("takeaway") if "takeaway" in ev_map else ev_map.get("address", start_ms)
    finish_ms = ev_map.get("finish") if "finish" in ev_map else ev_map.get("follow_through", end_ms)
    takeaway_us = _to_pts(takeaway_ms, "takeaway")
    finish_us = _to_pts(finish_ms, "finish")

    top_us: int | None = None
    top_source = "missing"
    if "top" in ev_map:
        top_us = _to_pts(ev_map["top"], "top")
        top_source = "observed" if ev_conf.get("top", 0.7) >= 0.8 else "r3_estimated"

    impact_us: int | None = None
    impact_source = "missing"
    if "impact" in ev_map:
        impact_us = _to_pts(ev_map["impact"], "impact")
        impact_source = "observed"
    elif "impact_estimated" in ev_map:
        impact_us = _to_pts(ev_map["impact_estimated"], "impact")
        impact_source = "r3_estimated"

    launch_us: int | None = impact_us
    launch_xy: tuple[float, float] | None = None

    anchor_source = "r3_events" if (top_us is not None or impact_us is not None) else "missing_events"
    anchor_rev_id: str | None = None
    if anchor_override:
        if anchor_override.get("address_pts_us") is not None:
            takeaway_us = int(anchor_override["address_pts_us"])
        if anchor_override.get("top_pts_us") is not None:
            top_us = int(anchor_override["top_pts_us"])
            if anchor_override.get("created_by") == "user" or anchor_override.get("revision", 1) > 1 or "id" not in anchor_override:
                top_source = "user_manual"
                anchor_source = "tracer_anchor_override"
            elif top_source == "missing":
                top_source = "r3_estimated"
        if anchor_override.get("impact_pts_us") is not None:
            impact_us = int(anchor_override["impact_pts_us"])
            if anchor_override.get("created_by") == "user" or anchor_override.get("revision", 1) > 1 or "id" not in anchor_override:
                impact_source = "user_manual"
                anchor_source = "tracer_anchor_override"
            elif impact_source == "missing":
                impact_source = "r3_estimated"
        if anchor_override.get("finish_pts_us") is not None:
            finish_us = int(anchor_override["finish_pts_us"])
        if anchor_override.get("launch_pts_us") is not None:
            launch_us = int(anchor_override["launch_pts_us"])
        elif impact_us is not None:
            launch_us = impact_us
        raw_lxy = anchor_override.get("launch_xy_norm")
        if isinstance(raw_lxy, (list, tuple)) and len(raw_lxy) == 2:
            launch_xy = (float(raw_lxy[0]), float(raw_lxy[1]))
        anchor_rev_id = anchor_override.get("id")

    # 僅當 top 與 impact 皆實際存在時確保順序單調合理 (top < impact)
    if top_us is not None and impact_us is not None and impact_us <= top_us:
        impact_us = top_us + 150_000
        if launch_us is None or launch_us < impact_us:
            launch_us = impact_us

    # 提取手腕位置僅供 ROI 搜尋視窗約束（嚴禁直接當作桿頭點！）
    wrist_hints: dict[int, tuple[float, float]] = {}
    for kf in eff_keyframes or []:
        t_ms = kf.get("time_ms")
        lms = kf.get("landmarks") or {}
        if t_ms is not None and isinstance(lms, dict):
            lead_w = lms.get("left_wrist") if handedness == "right" else lms.get("right_wrist")
            trail_w = lms.get("right_wrist") if handedness == "right" else lms.get("left_wrist")
            chosen = trail_w or lead_w
            if isinstance(chosen, dict) and "x" in chosen and "y" in chosen:
                wrist_hints[int(t_ms)] = (float(chosen["x"]), float(chosen["y"]))

    return ResolvedSegmentContext(
        segment_id=segment_id,
        video_id=video_id,
        session_id=session_id,
        owner_id=owner_id,
        source_storage_key=str(source_storage_key),
        source_sha256=str(source_sha256 or ""),
        handedness="left" if str(handedness).lower() == "left" else "right",
        camera_angle=eff_angle,
        club_type=str(club_type or "7I"),
        segment_start_pts_us=seg_start_us,
        segment_end_pts_us=seg_end_us,
        takeaway_pts_us=takeaway_us,
        top_pts_us=top_us,
        impact_pts_us=impact_us,
        finish_pts_us=finish_us,
        anchor_source=anchor_source,
        top_source=top_source,
        impact_source=impact_source,
        launch_pts_us=launch_us,
        launch_xy_norm=launch_xy,
        anchor_revision_id=anchor_rev_id,
        rounding_errors_us=rounding_errors,
        wrist_hints_by_ms=wrist_hints,
        r3_confidence=float(r3_confidence),
        source_video_path=local_video_path,
        geometry=geom,
        timeline=tl,
    )


def classify_swing_phase_at_pts(
    pts_us: int,
    takeaway_pts_us: int | None = None,
    top_pts_us: int | None = None,
    impact_pts_us: int | None = None,
    finish_pts_us: int | None = None,
    *,
    address_pts_us: int | None = None,
) -> str:
    """依據權威 source_pts_us 切分揮桿階段：backswing / downswing / follow_through / unknown。"""
    if top_pts_us is None and impact_pts_us is None:
        return "unknown"
    eff_takeaway = takeaway_pts_us if takeaway_pts_us is not None else address_pts_us
    if eff_takeaway is not None and pts_us < eff_takeaway:
        return "address"
    if top_pts_us is not None and pts_us <= top_pts_us:
        return "backswing"
    if impact_pts_us is not None and pts_us <= impact_pts_us:
        return "downswing"
    if finish_pts_us is not None and pts_us <= finish_pts_us:
        return "follow_through"
    if impact_pts_us is not None and pts_us > impact_pts_us:
        return "follow_through"
    return "finish"
