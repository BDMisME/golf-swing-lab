"""
Golf Tracer Studio R4 — Camera Motion & Background Shake Estimator (`camera_motion.py`).
偵測拍攝期間相機晃動與背景位移，提供背景補償位移量 (dx_norm, dy_norm)；
若晃動超過安全門檻，標記 CAMERA_MOVED 並阻止假自動追蹤通過。
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class CameraMotionEstimate:
    source_pts_us: int
    dx_norm: float
    dy_norm: float
    magnitude_norm: float
    is_unstable: bool

    @property
    def stability_score(self) -> float:
        return float(np.clip(1.0 - self.magnitude_norm * 10.0, 0.0, 1.0))


class CameraMotionTracker:
    """基於邊緣靜態背景區特徵點光流之相機穩定度分析器。"""

    def __init__(self, unstable_threshold_norm: float = 0.018) -> None:
        self.unstable_threshold_norm = float(unstable_threshold_norm)
        self._prev_gray: np.ndarray | None = None
        self._cum_dx: float = 0.0
        self._cum_dy: float = 0.0

    def update(self, frame_bgr: np.ndarray, source_pts_us: int = 0) -> CameraMotionEstimate:
        return self.step(frame_bgr, source_pts_us)

    def step(self, frame_bgr: np.ndarray, source_pts_us: int = 0) -> CameraMotionEstimate:
        h, w = frame_bgr.shape[:2]
        small_w, small_h = 320, max(180, int(round(320 * h / max(1, w))))
        gray = cv2.cvtColor(cv2.resize(frame_bgr, (small_w, small_h)), cv2.COLOR_BGR2GRAY)

        if self._prev_gray is None or self._prev_gray.shape != gray.shape:
            self._prev_gray = gray
            return CameraMotionEstimate(
                source_pts_us=source_pts_us,
                dx_norm=0.0,
                dy_norm=0.0,
                magnitude_norm=0.0,
                is_unstable=False,
            )

        # 建立外圍背景遮罩 (排除中央球員揮桿區域 [0.22..0.78, 0.18..0.92])
        mask = np.full_like(gray, 255)
        mx1, mx2 = int(small_w * 0.22), int(small_w * 0.78)
        my1, my2 = int(small_h * 0.18), int(small_h * 0.92)
        mask[my1:my2, mx1:mx2] = 0

        pts0 = cv2.goodFeaturesToTrack(
            self._prev_gray,
            maxCorners=60,
            qualityLevel=0.02,
            minDistance=8,
            mask=mask,
        )
        dx_norm, dy_norm, mag = 0.0, 0.0, 0.0
        if pts0 is not None and len(pts0) >= 6:
            pts1, st, _ = cv2.calcOpticalFlowPyrLK(
                self._prev_gray,
                gray,
                pts0,
                None,
                winSize=(15, 15),
                maxLevel=2,
            )
            if pts1 is not None and st is not None:
                good0 = pts0[st.ravel() == 1].reshape(-1, 2)
                good1 = pts1[st.ravel() == 1].reshape(-1, 2)
                if len(good0) >= 6:
                    diffs = good1 - good0
                    med_dx = float(np.median(diffs[:, 0])) / float(small_w)
                    med_dy = float(np.median(diffs[:, 1])) / float(small_h)
                    dx_norm = med_dx
                    dy_norm = med_dy
                    mag = float(np.hypot(dx_norm, dy_norm))
                    self._cum_dx += dx_norm
                    self._cum_dy += dy_norm

        self._prev_gray = gray
        return CameraMotionEstimate(
            source_pts_us=source_pts_us,
            dx_norm=dx_norm,
            dy_norm=dy_norm,
            magnitude_norm=mag,
            is_unstable=(mag > self.unstable_threshold_norm),
        )
