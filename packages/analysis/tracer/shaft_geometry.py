"""
Golf Tracer Studio R4 — Shaft Line Geometry Endpoint Estimator (`shaft_geometry.py`).
當專用桿頭模型缺席或高速揮桿導致桿頭動態模糊時，利用 OpenCV Canny + HoughLinesP 偵測細長桿身線段，
並以握把端 (近手腕約束區) 至遠端 (Distal Endpoint) 幾何關係推算桿頭端點。
嚴格誠信規範：
1. 所有經由本模組產出之點位一律標記 `source_type = shaft_geometry_estimated`，絕不混充 `detector_observed`。
2. 遠端點與手腕握把距離必須 `>= 0.10` 正規化畫面尺度，絕對禁止回傳手腕或前臂座標。
"""

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class ShaftEndpointEstimate:
    head_x_norm: float
    head_y_norm: float
    grip_x_norm: float
    grip_y_norm: float
    confidence: float
    uncertainty_px: float
    shaft_length_norm: float


class ShaftGeometryEstimator:
    """基於影像邊緣與直線霍夫變換之桿身遠端端點估計器。"""

    def __init__(
        self,
        min_shaft_len_norm: float = 0.10,
        max_shaft_len_norm: float = 0.46,
        max_grip_dist_norm: float = 0.18,
    ) -> None:
        self.min_shaft_len_norm = float(min_shaft_len_norm)
        self.max_shaft_len_norm = float(max_shaft_len_norm)
        self.max_grip_dist_norm = float(max_grip_dist_norm)

    def estimate_from_frame(
        self,
        frame_bgr: np.ndarray,
        roi_box: tuple[int, int, int, int],
        wrist_hint_norm: tuple[float, float] | None = None,
        prev_head_norm: tuple[float, float] | None = None,
    ) -> ShaftEndpointEstimate | None:
        """
        從單一影格與 ROI 尋找符合球桿幾何特徵之細長線段，回傳遠端桿頭估計位置與像素不確定度。
        若無握把約束且無前一格桿頭錨點，為避免背景欄杆/柱子誤判，嚴格回傳 None。
        """
        if wrist_hint_norm is None and prev_head_norm is None:
            return None

        h, w = frame_bgr.shape[:2]
        rx1, ry1, rx2, ry2 = roi_box
        rx1, ry1 = max(0, rx1), max(0, ry1)
        rx2, ry2 = min(w, rx2), min(h, ry2)
        if rx2 - rx1 < 24 or ry2 - ry1 < 24:
            return None

        crop = frame_bgr[ry1:ry2, rx1:rx2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 45, 135)

        diag = float(math.hypot(w, h))
        min_line_px = max(18, int(round(self.min_shaft_len_norm * min(w, h))))
        lines = cv2.HoughLinesP(
            edges,
            rho=1.0,
            theta=np.pi / 180.0,
            threshold=24,
            minLineLength=min_line_px,
            maxLineGap=10,
        )
        if lines is None or len(lines) == 0:
            return None

        best_candidate: ShaftEndpointEstimate | None = None
        best_score = -1.0

        for line in lines[:, 0, :]:
            lx1, ly1, lx2, ly2 = [float(v) for v in line]
            ax1 = (rx1 + lx1) / float(w)
            ay1 = (ry1 + ly1) / float(h)
            ax2 = (rx1 + lx2) / float(w)
            ay2 = (ry1 + ly2) / float(h)

            seg_len = float(math.hypot(ax2 - ax1, ay2 - ay1))
            if seg_len < self.min_shaft_len_norm or seg_len > self.max_shaft_len_norm:
                continue

            # 排除純水平與純垂直之背景建築線條 (如練習場柱子、打擊墊邊緣)
            dx = abs(ax2 - ax1)
            dy = abs(ay2 - ay1)
            if dx < 0.012 or dy < 0.012:
                continue

            # 決定哪一端是握把 (Grip)、哪一端是桿頭 (Clubhead)
            if wrist_hint_norm is not None:
                wx, wy = wrist_hint_norm
                d1 = float(math.hypot(ax1 - wx, ay1 - wy))
                d2 = float(math.hypot(ax2 - wx, ay2 - wy))
                if d1 <= d2:
                    gx, gy, hx, hy = ax1, ay1, ax2, ay2
                    grip_dist = d1
                    head_dist_from_wrist = d2
                else:
                    gx, gy, hx, hy = ax2, ay2, ax1, ay1
                    grip_dist = d2
                    head_dist_from_wrist = d1

                if grip_dist > self.max_grip_dist_norm:
                    continue
                # 嚴格防呆：桿頭端點必須遠離手腕 >= 0.10，絕不可把近手腕點當桿頭
                if head_dist_from_wrist < max(0.10, grip_dist + 0.07):
                    continue
            elif prev_head_norm is not None:
                px, py = prev_head_norm
                d1 = float(math.hypot(ax1 - px, ay1 - py))
                d2 = float(math.hypot(ax2 - px, ay2 - py))
                if d1 <= d2:
                    hx, hy, gx, gy = ax1, ay1, ax2, ay2
                    grip_dist = d1
                else:
                    hx, hy, gx, gy = ax2, ay2, ax1, ay1
                    grip_dist = d2
                if grip_dist > 0.15:
                    continue
            else:
                continue

            temporal_bonus = 0.0
            if prev_head_norm is not None:
                step_d = float(math.hypot(hx - prev_head_norm[0], hy - prev_head_norm[1]))
                if step_d > 0.22:
                    continue
                temporal_bonus = max(0.0, 0.20 * (1.0 - step_d / 0.22))

            len_score = min(1.0, seg_len / 0.25)
            prox_score = max(0.0, 1.0 - (grip_dist / self.max_grip_dist_norm))
            score = 0.45 * prox_score + 0.35 * len_score + temporal_bonus

            if score > best_score:
                best_score = score
                conf = round(float(np.clip(0.35 + 0.40 * score, 0.35, 0.76)), 3)
                unc_px = round(float((1.0 - score * 0.6) * 22.0 * (1080.0 / max(1.0, diag / 1.4))), 2)
                best_candidate = ShaftEndpointEstimate(
                    head_x_norm=float(np.clip(hx, 0.0, 1.0)),
                    head_y_norm=float(np.clip(hy, 0.0, 1.0)),
                    grip_x_norm=float(np.clip(gx, 0.0, 1.0)),
                    grip_y_norm=float(np.clip(gy, 0.0, 1.0)),
                    confidence=conf,
                    uncertainty_px=max(8.0, unc_px),
                    shaft_length_norm=round(seg_len, 4),
                )

        return best_candidate
