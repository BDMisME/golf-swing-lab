"""
Golf Tracer Studio R4 — Authoritative Presentation Timestamp (PTS) Media Clock (`media_clock.py`).
定義 5 種時間尺標且絕不混用：
1. source_pts_us：原始影片可呈現影格的真實 Presentation Timestamp (整數微秒)
2. segment_start_pts_us / segment_end_pts_us：對齊原片 PTS 的段落邊界，記錄 rounding_error_us
3. local_time_us = source_pts_us - clip_zero_pts_us：段內相對時間
4. output_pts_us：CFR 輸出時間點，使用整數有理數 (frame_idx * 1_000_000) // fps 避免累積漂移
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from packages.analysis.probe import VideoProbeError, probe_video_file


@dataclass(frozen=True)
class FrameClockEntry:
    source_frame_index: int
    source_pts_us: int
    duration_us: int = 16667
    is_keyframe: bool = False


class RationalCFRTimelineList(list[FrameClockEntry]):
    """同時支援 `list[FrameClockEntry]` 與 `.entries` 存取之有理數時間表容器。"""

    @property
    def entries(self) -> list[FrameClockEntry]:
        return list(self)


@dataclass
class MediaClockTimeline:
    video_path: str
    duration_us: int
    fps_num: int
    fps_den: int
    is_vfr: bool
    rotation: int
    coded_width: int
    coded_height: int
    has_audio: bool
    codec: str
    frames: list[FrameClockEntry] = field(default_factory=list)
    clock_source: str = "ffprobe_pts"  # ffprobe_pts | rational_cfr_grid

    @property
    def entries(self) -> list[FrameClockEntry]:
        return self.frames

    @property
    def nominal_fps(self) -> float:
        return self.fps_num / max(1, self.fps_den)

    def snap_ms_to_pts_us(self, target_ms: int | float) -> tuple[int, int, int]:
        """
        將既有毫秒時間碼對齊至最接近的原片真實影格 PTS (微秒)。
        回傳 (snapped_pts_us, source_frame_index, rounding_error_us)。
        """
        target_us = int(round(float(target_ms) * 1000.0))
        if not self.frames:
            return (max(0, target_us), 0, 0)

        # 二分搜尋最接近之影格
        lo, hi = 0, len(self.frames) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.frames[mid].source_pts_us < target_us:
                lo = mid + 1
            else:
                hi = mid

        best_idx = lo
        if lo > 0:
            prev_diff = abs(self.frames[lo - 1].source_pts_us - target_us)
            curr_diff = abs(self.frames[lo].source_pts_us - target_us)
            if prev_diff <= curr_diff:
                best_idx = lo - 1

        chosen = self.frames[best_idx]
        rounding_err_us = chosen.source_pts_us - target_us
        return (chosen.source_pts_us, chosen.source_frame_index, rounding_err_us)

    def slice_window(self, start_pts_us: int, end_pts_us: int, pad_us: int = 0) -> list[FrameClockEntry]:
        s_us = max(0, start_pts_us - pad_us)
        e_us = min(self.duration_us, end_pts_us + pad_us)
        return [f for f in self.frames if s_us <= f.source_pts_us <= e_us]


def compute_local_time_us(source_pts_us: int, clip_zero_pts_us: int) -> int:
    """計算段內局部時間 (local_time_us = source_pts_us - clip_zero_pts_us)。"""
    return int(source_pts_us) - int(clip_zero_pts_us)


def generate_cfr_output_pts_us(
    start_pts_us: int | None = None,
    end_pts_us: int | None = None,
    target_fps: int = 60,
    *,
    clip_start_pts_us: int | None = None,
    clip_end_pts_us: int | None = None,
) -> list[int]:
    """
    以整數有理數 time_base (1 / target_fps 秒) 生成輸出 CFR 影格對應之來源時間點序列，
    嚴禁使用整數固定步長累加 (例如 += 16666) 造成長影片時間漂移。
    """
    s_pts = int(clip_start_pts_us if clip_start_pts_us is not None else (start_pts_us or 0))
    e_pts = int(clip_end_pts_us if clip_end_pts_us is not None else (end_pts_us or 0))

    if target_fps not in (24, 25, 30, 50, 60, 120):
        raise ValueError(f"不支援的輸出 CFR FPS: {target_fps}")
    span_us = max(0, e_pts - s_pts)
    if span_us == 0:
        return [s_pts]

    total_frames = max(1, int((span_us * target_fps) // 1_000_000) + 1)
    result: list[int] = []
    for idx in range(total_frames):
        offset_us = int(round((idx * 1_000_000) / float(target_fps)))
        pts_us = s_pts + offset_us
        if pts_us <= e_pts + (500_000 // target_fps):
            result.append(pts_us)
    return result


def build_rational_cfr_timeline(
    duration_us: int | None = None,
    fps_num: int = 60,
    fps_den: int = 1,
    start_us: int = 0,
    end_us: int | None = None,
    *,
    duration_ms: int | float | None = None,
) -> RationalCFRTimelineList:
    """
    使用精確有理數 (fps_den / fps_num 秒) 建立無累積漂移之影格時間表。
    支援 23.976 (24000/1001)、29.97 (30000/1001)、59.94 (60000/1001)、30/1、60/1、120/1 等。
    """
    if duration_us is None:
        if duration_ms is not None:
            duration_us = int(round(float(duration_ms) * 1000.0))
        else:
            duration_us = 1_000_000

    if fps_num <= 0 or fps_den <= 0:
        raise VideoProbeError(f"無效的有理數幀率: {fps_num}/{fps_den}")
    stop_us = duration_us if end_us is None else min(duration_us, end_us)
    start_idx = max(0, int((start_us * fps_num) // (1_000_000 * fps_den)))
    end_idx = max(start_idx, int((stop_us * fps_num) // (1_000_000 * fps_den)))

    entries = RationalCFRTimelineList()
    for idx in range(start_idx, end_idx + 1):
        pts_us = int(round((idx * 1_000_000 * fps_den) / float(fps_num)))
        next_pts_us = int(round(((idx + 1) * 1_000_000 * fps_den) / float(fps_num)))
        if start_us <= pts_us <= stop_us:
            entries.append(
                FrameClockEntry(
                    source_frame_index=idx,
                    source_pts_us=pts_us,
                    duration_us=max(1, next_pts_us - pts_us),
                    is_keyframe=(idx % 30 == 0),
                )
            )
    return entries


def extract_clip_pts_timeline(
    video_path: str | Path,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> MediaClockTimeline:
    """
    從原始影片擷取指定區間之真實 Presentation Timestamp (PTS, 微秒)。
    - 對 B-frame 依據呈現時間排序並去除重複或負數異常時間戳
    - 若偵測到無效或退化時間軸，Fail-Closed 拋出 VideoProbeError
    """
    p = Path(video_path)
    meta = probe_video_file(p, collect_pts=False)
    duration_us = meta.duration_ms * 1000

    s_sec = max(0.0, (start_ms / 1000.0) - 0.5) if start_ms is not None else 0.0
    e_sec = ((end_ms / 1000.0) + 0.5) if end_ms is not None else (meta.duration_ms / 1000.0)
    dur_sec = max(0.5, e_sec - s_sec)

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "packet=pts_time,duration_time,flags",
        "-read_intervals",
        f"{s_sec:.3f}%+{dur_sec:.3f}",
        "-of",
        "json",
        str(p),
    ]
    raw_pts_us: list[tuple[int, int, bool]] = []
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            for pkt in data.get("packets") or []:
                ts_str = pkt.get("pts_time")
                if ts_str is None:
                    continue
                try:
                    pts_val = int(round(float(ts_str) * 1_000_000))
                except (ValueError, TypeError):
                    continue
                if pts_val < 0:
                    continue
                dur_str = pkt.get("duration_time")
                dur_val = (
                    int(round(float(dur_str) * 1_000_000))
                    if dur_str
                    else int(round(1_000_000 / max(1.0, meta.fps)))
                )
                is_key = "K" in str(pkt.get("flags") or "")
                raw_pts_us.append((pts_val, max(1, dur_val), is_key))
    except Exception:
        raw_pts_us = []

    # 依呈現時間 (PTS) 排序並去重（處理 B-frame 解碼順序與呈現順序差異）
    raw_pts_us.sort(key=lambda item: item[0])
    deduped: list[FrameClockEntry] = []
    seen_pts: set[int] = set()
    base_idx = int(round(s_sec * meta.fps)) if start_ms is not None else 0

    for pts_val, dur_val, is_key in raw_pts_us:
        if pts_val in seen_pts:
            continue
        seen_pts.add(pts_val)
        deduped.append(
            FrameClockEntry(
                source_frame_index=base_idx + len(deduped),
                source_pts_us=pts_val,
                duration_us=dur_val,
                is_keyframe=is_key,
            )
        )

    is_vfr = meta.is_vfr
    if len(deduped) >= 4:
        diffs = [deduped[i + 1].source_pts_us - deduped[i].source_pts_us for i in range(len(deduped) - 1)]
        if max(diffs) - min(diffs) > 4000:  # > 4ms jitter indicates VFR
            is_vfr = True
        clock_source = "ffprobe_pts"
    else:
        s_us = int(start_ms * 1000) if start_ms is not None else 0
        e_us = int(end_ms * 1000) if end_ms is not None else duration_us
        deduped = list(
            build_rational_cfr_timeline(
                duration_us=duration_us,
                fps_num=meta.fps_num,
                fps_den=meta.fps_den,
                start_us=max(0, s_us - 500_000),
                end_us=min(duration_us, e_us + 500_000),
            )
        )
        clock_source = "rational_cfr_grid"

    if not deduped:
        raise VideoProbeError(f"無法建立可靠 PTS 時間軸 (Fail-Closed): {video_path}")

    return MediaClockTimeline(
        video_path=str(p),
        duration_us=duration_us,
        fps_num=meta.fps_num,
        fps_den=meta.fps_den,
        is_vfr=is_vfr,
        rotation=meta.rotation,
        coded_width=meta.width,
        coded_height=meta.height,
        has_audio=meta.has_audio,
        codec=meta.codec,
        frames=deduped,
        clock_source=clock_source,
    )
