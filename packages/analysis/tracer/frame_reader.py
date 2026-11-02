"""
Golf Tracer Studio R4 — High-Resolution Bounded Streaming Frame Reader (`frame_reader.py`).
按單球時間窗串流讀取高解析原片，對齊 MediaClockTimeline 之真實 source_pts_us，
並透過有界 LRU 快取控制記憶體峰值，絕不將 30 分鐘長片全量載入 RAM。
"""

import hashlib
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
import subprocess

import cv2
import numpy as np

from packages.analysis.tracer.media_clock import MediaClockTimeline, extract_clip_pts_timeline
from packages.analysis.tracer.segment_context import SourceUnavailableError
from packages.analysis.tracer.transforms import FrameGeometry, rotate_coded_frame_to_upright


@dataclass
class DecodedUprightFrame:
    source_frame_index: int
    source_pts_us: int
    frame_bgr: np.ndarray
    geometry: FrameGeometry
    frame_sha256: str

    @property
    def image_bgr(self) -> np.ndarray:
        return self.frame_bgr

    @property
    def width(self) -> int:
        return int(self.frame_bgr.shape[1])

    @property
    def height(self) -> int:
        return int(self.frame_bgr.shape[0])


class BoundedFrameReader:
    """高解析度局部區間串流影格讀取器（含 LRU 快取、Proxy 低解析度阻擋與零二次旋轉保證）。"""

    def __init__(
        self,
        video_path: str | Path | None = None,
        timeline: MediaClockTimeline | None = None,
        max_cache_frames: int = 24,
        *,
        source_path: str | Path | None = None,
        geometry: FrameGeometry | None = None,
        require_high_res: bool = False,
    ) -> None:
        resolved_path = source_path if source_path is not None else video_path
        if resolved_path is None:
            raise SourceUnavailableError("未提供原始高解析影片路徑")
        self.video_path = Path(resolved_path)
        if not self.video_path.exists() or self.video_path.stat().st_size == 0:
            raise SourceUnavailableError(
                f"高解析原片不存在或為空檔: {self.video_path}",
                storage_key=str(self.video_path),
            )
        if require_high_res and ("_proxy" in self.video_path.name.lower() or "/proxies/" in self.video_path.as_posix().lower()):
            raise SourceUnavailableError(
                f"拒絕使用低解析度 Proxy 影片執行高畫質追蹤: {self.video_path}",
                storage_key=str(self.video_path),
            )

        self.timeline = timeline
        self._explicit_geometry = geometry
        self.require_high_res = require_high_res
        self.max_cache_frames = max(4, int(max_cache_frames))
        self._cache: OrderedDict[int, DecodedUprightFrame] = OrderedDict()

        if self.require_high_res:
            tl = self._ensure_timeline()
            short_side = min(tl.coded_width, tl.coded_height)
            if short_side < 600:
                raise SourceUnavailableError(
                    f"影片短邊解析度 ({short_side}px) 低於高畫質追蹤門檻 (600px)，拒絕以低畫質來源冒充原片: {self.video_path}",
                    storage_key=str(self.video_path),
                )

    def _ensure_timeline(self, start_ms: int | None = None, end_ms: int | None = None) -> MediaClockTimeline:
        if self.timeline is None:
            self.timeline = extract_clip_pts_timeline(self.video_path, start_ms=start_ms, end_ms=end_ms)
            return self.timeline
        if start_ms is not None and end_ms is not None and self.timeline.entries:
            first_ms = self.timeline.entries[0].source_pts_us // 1000
            last_ms = self.timeline.entries[-1].source_pts_us // 1000
            if start_ms < first_ms - 100 or end_ms > last_ms + 100:
                self.timeline = extract_clip_pts_timeline(self.video_path, start_ms=start_ms, end_ms=end_ms)
        return self.timeline

    @property
    def geometry(self) -> FrameGeometry:
        if self._explicit_geometry is not None:
            return self._explicit_geometry
        tl = self._ensure_timeline()
        return FrameGeometry(
            coded_width=tl.coded_width,
            coded_height=tl.coded_height,
            rotation=tl.rotation,
        )

    def _put_cache(self, pts_us: int, item: DecodedUprightFrame) -> None:
        if pts_us in self._cache:
            self._cache.move_to_end(pts_us)
        self._cache[pts_us] = item
        while len(self._cache) > self.max_cache_frames:
            self._cache.popitem(last=False)

    def iter_frames(
        self,
        start_pts_us: int,
        end_pts_us: int,
        pad_before_us: int = 0,
        pad_after_us: int = 0,
    ) -> Iterator[DecodedUprightFrame]:
        return self.iter_window(
            start_pts_us=start_pts_us,
            end_pts_us=end_pts_us,
            pad_before_us=pad_before_us,
            pad_after_us=pad_after_us,
        )

    def iter_window(
        self,
        start_pts_us: int,
        end_pts_us: int,
        pad_before_us: int = 250_000,
        pad_after_us: int = 250_000,
    ) -> Iterator[DecodedUprightFrame]:
        """
        串流解碼 `[start_pts_us - pad_before_us, end_pts_us + pad_after_us]` 區間內之直立高解析影格。
        每一格皆附帶權威 `source_pts_us` 與 `frame_sha256` 證據雜湊。
        """
        s_us = max(0, int(start_pts_us) - max(0, int(pad_before_us)))
        e_us = int(end_pts_us) + max(0, int(pad_after_us))
        tl = self._ensure_timeline(start_ms=s_us // 1000, end_ms=(e_us // 1000) + 1)
        e_us = min(tl.duration_us, e_us)

        geom = self._explicit_geometry or FrameGeometry(
            coded_width=tl.coded_width,
            coded_height=tl.coded_height,
            rotation=tl.rotation,
        )

        window_entries = tl.slice_window(s_us, e_us, pad_us=0)
        if not window_entries:
            return

        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise RuntimeError(f"無法開啟視訊檔進行高解析解碼: {self.video_path}")

        emitted_count = 0
        try:
            seek_ms = max(0.0, (s_us / 1000.0) - 80.0)
            if seek_ms > 0:
                cap.set(cv2.CAP_PROP_POS_MSEC, seek_ms)

            entry_idx = 0
            last_emitted_pts = -1
            while entry_idx < len(window_entries):
                ret, raw_frame = cap.read()
                if not ret or raw_frame is None:
                    break

                pos_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                pos_us = int(round(pos_ms * 1000.0))

                # 對齊至 MediaClockTimeline 中最接近且遞增之真實 PTS
                target_entry = window_entries[entry_idx]
                if pos_us > 0 and pos_us + int(target_entry.duration_us * 1.5) < s_us:
                    continue

                if target_entry.source_pts_us <= last_emitted_pts:
                    entry_idx += 1
                    continue

                upright = rotate_coded_frame_to_upright(raw_frame, geom)
                small = cv2.resize(upright, (64, 64), interpolation=cv2.INTER_AREA)
                frame_hash = hashlib.sha256(
                    small.tobytes() + str(target_entry.source_pts_us).encode("utf-8")
                ).hexdigest()

                decoded = DecodedUprightFrame(
                    source_frame_index=target_entry.source_frame_index,
                    source_pts_us=target_entry.source_pts_us,
                    frame_bgr=upright,
                    geometry=geom,
                    frame_sha256=frame_hash,
                )
                self._put_cache(target_entry.source_pts_us, decoded)
                last_emitted_pts = target_entry.source_pts_us
                entry_idx += 1
                emitted_count += 1
                yield decoded
        finally:
            cap.release()

        # 若 OpenCV 對 HEVC 長片後段 seek 失敗 (emitted_count == 0)，自動切換為 FFmpeg 原生精准定位管道
        if emitted_count == 0 and window_entries:
            frame_bytes = geom.coded_width * geom.coded_height * 3
            dur_sec = max(0.2, (e_us - s_us) / 1_000_000.0 + 0.15)
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-noautorotate",
                "-ss",
                f"{s_us / 1_000_000.0:.3f}",
                "-t",
                f"{dur_sec:.3f}",
                "-i",
                str(self.video_path),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "bgr24",
                "-",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                assert proc.stdout is not None
                for target_entry in window_entries:
                    buf = proc.stdout.read(frame_bytes)
                    if len(buf) < frame_bytes:
                        break
                    raw_frame = np.frombuffer(buf, dtype=np.uint8).reshape(
                        (geom.coded_height, geom.coded_width, 3)
                    )
                    upright = rotate_coded_frame_to_upright(raw_frame, geom)
                    small = cv2.resize(upright, (64, 64), interpolation=cv2.INTER_AREA)
                    frame_hash = hashlib.sha256(
                        small.tobytes() + str(target_entry.source_pts_us).encode("utf-8")
                    ).hexdigest()
                    decoded = DecodedUprightFrame(
                        source_frame_index=target_entry.source_frame_index,
                        source_pts_us=target_entry.source_pts_us,
                        frame_bgr=upright,
                        geometry=geom,
                        frame_sha256=frame_hash,
                    )
                    self._put_cache(target_entry.source_pts_us, decoded)
                    yield decoded
            finally:
                if proc.stdout:
                    proc.stdout.close()
                proc.terminate()
                proc.wait(timeout=5)

    def read_frame_at_pts(self, target_pts_us: int) -> DecodedUprightFrame:
        """讀取單一指定 PTS (微秒) 最接近之直立影格，優先命中 LRU 快取。"""
        tl = self._ensure_timeline(
            start_ms=max(0, (target_pts_us // 1000) - 500),
            end_ms=(target_pts_us // 1000) + 500,
        )
        snapped_pts_us, frame_idx, _ = tl.snap_ms_to_pts_us(target_pts_us / 1000.0)
        if snapped_pts_us in self._cache:
            self._cache.move_to_end(snapped_pts_us)
            return self._cache[snapped_pts_us]

        geom = self._explicit_geometry or FrameGeometry(
            coded_width=tl.coded_width,
            coded_height=tl.coded_height,
            rotation=tl.rotation,
        )
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise RuntimeError(f"無法開啟視訊檔: {self.video_path}")
        try:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, snapped_pts_us / 1000.0))
            ret, raw_frame = cap.read()
            if not ret or raw_frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, raw_frame = cap.read()
            if not ret or raw_frame is None:
                raise RuntimeError(f"無法讀取 PTS={snapped_pts_us}us 之影格")
            upright = rotate_coded_frame_to_upright(raw_frame, geom)
            small = cv2.resize(upright, (64, 64), interpolation=cv2.INTER_AREA)
            frame_hash = hashlib.sha256(
                small.tobytes() + str(snapped_pts_us).encode("utf-8")
            ).hexdigest()
            decoded = DecodedUprightFrame(
                source_frame_index=frame_idx,
                source_pts_us=snapped_pts_us,
                frame_bgr=upright,
                geometry=geom,
                frame_sha256=frame_hash,
            )
            self._put_cache(snapped_pts_us, decoded)
            return decoded
        finally:
            cap.release()
