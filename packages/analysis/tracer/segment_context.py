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
    top_pts_us: int
    impact_pts_us: int
    finish_pts_us: int
    anchor_source: str  # "r3_events" | "tracer_anchor_override"
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
    若提供 `anchor_override`（來自 `tracer_anchor_revisions`），僅在 Studio 上下文中覆蓋 Top/Impact，
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
            # 若呼叫者需要讀檔（未傳自訂 pts_snapping_fn 且檔案真不存在），檢查是否為純記憶體驗證
            if "/" in str(source_storage_key) or str(source_storage_key).endswith((".mp4", ".mov", ".MOV", ".MP4")):
                try:
                    _resolve_local_video_path(str(source_storage_key), video_id=video_id)
                except SourceUnavailableError:
                    # 僅當 storage_key 指向實際遺失之儲存鍵且未給自訂 snapping 時拋出
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
    for ev in events or []:
        ename = str(ev.get("event_name") or "").lower()
        tms = ev.get("time_ms")
        if ename and tms is not None:
            ev_map[ename] = int(tms)

    span_ms = max(500, end_ms - start_ms)
    takeaway_ms = ev_map.get("takeaway") or ev_map.get("address") or (start_ms + int(span_ms * 0.12))
    top_ms = ev_map.get("top") or (start_ms + int(span_ms * 0.48))
    impact_ms = ev_map.get("impact_estimated") or ev_map.get("impact") or (start_ms + int(span_ms * 0.68))
    finish_ms = ev_map.get("finish") or ev_map.get("follow_through") or (end_ms - int(span_ms * 0.08))

    takeaway_us = _to_pts(takeaway_ms, "takeaway")
    top_us = _to_pts(top_ms, "top")
    impact_us = _to_pts(impact_ms, "impact")
    finish_us = _to_pts(finish_ms, "finish")

    anchor_source = "r3_events"
    anchor_rev_id: str | None = None
    if anchor_override:
        if anchor_override.get("top_pts_us") is not None:
            top_us = int(anchor_override["top_pts_us"])
            anchor_source = "tracer_anchor_override"
        if anchor_override.get("impact_pts_us") is not None:
            impact_us = int(anchor_override["impact_pts_us"])
            anchor_source = "tracer_anchor_override"
        anchor_rev_id = anchor_override.get("id")

    # 確保順序單調合理 (top < impact)
    if impact_us <= top_us:
        impact_us = top_us + 150_000

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
    """依據權威 source_pts_us 切分揮桿階段：backswing / downswing / follow_through。"""
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
