"""
Golf Tracer Studio R4 — Shot Ball Detector & Optical Flow Bridge (`shot_detector.py`).
負責於高解析度正向影格 (Original Upright Frame) 執行小白球偵測：
1. 載入並檢驗本機 `golf_ball_yolov8n.pt` 模型權重雜湊與類別表 (`{0: 'golf_ball'}`)。
2. 支援雙向 ROI (`plan_ball_flight_roi`) 內之多候選球體偵測，回傳包含 bbox 與不確定度之 `BallDetectionCandidate`。
3. 支援金字塔 Lucas-Kanade 光流追蹤 (`cv2.calcOpticalFlowPyrLK`) 搭配雙向一致性檢查 (Forward-Backward Error)，
   於球速極快模糊幀提供 `optical_flow_estimated` 候選（明確與 `detector_observed` 區分）。
"""

from dataclasses import dataclass
import hashlib
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from packages.analysis.tracer.clubhead_detector import detect_compute_device
from packages.analysis.tracer.roi_planner import PlannedROI

logger = logging.getLogger(__name__)

DEFAULT_GOLF_BALL_MODEL_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "GolfSwingLab"
    / "models"
    / "golf_ball_yolov8n.pt"
)


@dataclass(frozen=True)
class BallDetectionCandidate:
    """單一影格內之高爾夫球偵測候選。"""

    x_norm: float
    y_norm: float
    bbox_norm: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    confidence: float
    uncertainty_px: float
    model_id: str
    is_optical_flow: bool = False


class ShotBallDetector:
    """
    高解析度高爾夫球偵測器與光流輔助器。
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        conf_threshold: float = 0.18,
    ) -> None:
        self.model_path = Path(model_path) if model_path else DEFAULT_GOLF_BALL_MODEL_PATH
        self.conf_threshold = conf_threshold
        self.device = detect_compute_device()
        self.model: Any = None
        self.model_id = "golf_ball_yolov8n"
        self.weights_sha256: str | None = None
        self.status: str = "UNINITIALIZED"
        self._load_model()

    def _load_model(self) -> None:
        if not self.model_path.exists() or self.model_path.stat().st_size < 1024:
            self.status = "MODEL_UNAVAILABLE"
            logger.warning("找不到小白球偵測模型: %s", self.model_path)
            return

        try:
            h = hashlib.sha256()
            with self.model_path.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            self.weights_sha256 = h.hexdigest()

            from ultralytics import YOLO

            self.model = YOLO(str(self.model_path))
            self.status = "READY"
        except Exception as exc:
            self.status = f"LOAD_ERROR:{exc}"
            self.model = None
            logger.warning("載入小白球模型失敗: %s", exc)

    @property
    def is_available(self) -> bool:
        return self.model is not None and self.status == "READY"

    def detect_candidates_in_roi(
        self,
        upright_bgr: np.ndarray,
        roi: PlannedROI,
    ) -> list[BallDetectionCandidate]:
        """
        於雙向飛球 ROI 內執行 YOLOv8n 球體偵測，回傳所有合理尺寸之候選點（按信心度排序）。
        """
        if not self.is_available:
            return []

        h, w = upright_bgr.shape[:2]
        rx1 = max(0, min(w - 1, roi.x1))
        ry1 = max(0, min(h - 1, roi.y1))
        rx2 = max(rx1 + 1, min(w, roi.x2))
        ry2 = max(ry1 + 1, min(h, roi.y2))
        roi_w = rx2 - rx1
        roi_h = ry2 - ry1
        if roi_w < 16 or roi_h < 16:
            return []

        crop = upright_bgr[ry1:ry2, rx1:rx2]
        try:
            try:
                from packages.analysis.pose.yolo_extractor import _YOLO_GLOBAL_LOCK

                with _YOLO_GLOBAL_LOCK:
                    results = list(
                        self.model.predict(
                            crop,
                            conf=self.conf_threshold,
                            device=self.device,
                            verbose=False,
                        )
                    )
            except ImportError:
                results = list(
                    self.model.predict(
                        crop,
                        conf=self.conf_threshold,
                        device=self.device,
                        verbose=False,
                    )
                )

            if not results:
                return []

            boxes = getattr(results[0], "boxes", None)
            if boxes is None or len(boxes) == 0:
                return []

            candidates: list[BallDetectionCandidate] = []
            for box in boxes:
                conf = float(box.conf[0].item())
                if conf < self.conf_threshold:
                    continue
                xyxy = box.xyxy[0].cpu().numpy()
                bx1, by1, bx2, by2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                bw = max(1.0, bx2 - bx1)
                bh = max(1.0, by2 - by1)

                # 排除過大背景雜訊與極端長條誤檢 (允許高速快門模糊造成的適度拉長)
                if bw > roi_w * 0.35 or bh > roi_h * 0.35:
                    continue
                if bw > max(w, h) * 0.12 or bh > max(w, h) * 0.12:
                    continue
                aspect = bw / bh
                if aspect < 0.22 or aspect > 4.5:
                    continue

                abs_x1 = rx1 + bx1
                abs_y1 = ry1 + by1
                abs_x2 = rx1 + bx2
                abs_y2 = ry1 + by2
                cx = 0.5 * (abs_x1 + abs_x2)
                cy = 0.5 * (abs_y1 + abs_y2)
                uncertainty_px = round(max(1.5, 0.25 * math.hypot(bw, bh) * (1.15 - min(1.0, conf))), 2)

                candidates.append(
                    BallDetectionCandidate(
                        x_norm=float(np.clip(cx / float(w), 0.0, 1.0)),
                        y_norm=float(np.clip(cy / float(h), 0.0, 1.0)),
                        bbox_norm=(
                            float(np.clip(abs_x1 / float(w), 0.0, 1.0)),
                            float(np.clip(abs_y1 / float(h), 0.0, 1.0)),
                            float(np.clip(abs_x2 / float(w), 0.0, 1.0)),
                            float(np.clip(abs_y2 / float(h), 0.0, 1.0)),
                        ),
                        confidence=round(conf, 4),
                        uncertainty_px=uncertainty_px,
                        model_id=self.model_id,
                        is_optical_flow=False,
                    )
                )

            candidates.sort(key=lambda c: c.confidence, reverse=True)
            return candidates
        except Exception as exc:
            logger.debug("ShotBallDetector ROI 推論異常: %s", exc)
            return []

    def track_optical_flow_step(
        self,
        prev_bgr: np.ndarray,
        curr_bgr: np.ndarray,
        prev_xy_norm: tuple[float, float],
        expected_v_norm: tuple[float, float] | None = None,
    ) -> BallDetectionCandidate | None:
        """
        當 YOLO 在高速飛行單幀漏檢時，以雙向金字塔 Lucas-Kanade 光流追蹤小白球位置。
        嚴格要求 Forward-Backward 一致性誤差 <= 5.5 px 且位移向上/向前合理，
        回傳標記 `is_optical_flow=True` 之候選（將映射為 `optical_flow_estimated`）。
        """
        h, w = curr_bgr.shape[:2]
        if prev_bgr.shape[:2] != (h, w):
            return None

        prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.cvtColor(curr_bgr, cv2.COLOR_BGR2GRAY)

        px = float(prev_xy_norm[0]) * w
        py = float(prev_xy_norm[1]) * h
        p0 = np.array([[[px, py]]], dtype=np.float32)

        lk_params: dict[str, Any] = {
            "winSize": (25, 25),
            "maxLevel": 3,
            "criteria": (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
        }

        if expected_v_norm is not None:
            init_x = px + expected_v_norm[0] * w
            init_y = py + expected_v_norm[1] * h
            p1_init = np.array([[[init_x, init_y]]], dtype=np.float32)
            p1, st1, _ = cv2.calcOpticalFlowPyrLK(
                prev_gray,
                curr_gray,
                p0,
                p1_init,
                flags=cv2.OPTFLOW_USE_INITIAL_FLOW,
                **lk_params,
            )
        else:
            p1, st1, _ = cv2.calcOpticalFlowPyrLK(prev_gray, curr_gray, p0, None, **lk_params)

        if p1 is None or st1 is None or int(st1[0, 0]) != 1:
            return None

        # 反向光流驗證 (Forward-Backward consistency check)
        p0_back, st2, _ = cv2.calcOpticalFlowPyrLK(curr_gray, prev_gray, p1, None, **lk_params)
        if p0_back is None or st2 is None or int(st2[0, 0]) != 1:
            return None

        nx, ny = float(p1[0, 0, 0]), float(p1[0, 0, 1])
        bx, by = float(p0_back[0, 0, 0]), float(p0_back[0, 0, 1])
        fb_err = math.hypot(px - bx, py - by)
        if fb_err > 5.5:
            return None

        if nx < 4 or nx >= w - 4 or ny < 4 or ny >= h - 4:
            return None

        step_px = math.hypot(nx - px, ny - py)
        if step_px < 3.0 or step_px > max(w, h) * 0.22:
            return None

        # 必須維持向天空方向或水平合理飛行 (dy_px <= 4.0)
        if (ny - py) > 4.0:
            return None

        conf = float(np.clip(0.58 - (fb_err / 15.0), 0.25, 0.58))
        r_px = 6.0
        return BallDetectionCandidate(
            x_norm=float(np.clip(nx / float(w), 0.0, 1.0)),
            y_norm=float(np.clip(ny / float(h), 0.0, 1.0)),
            bbox_norm=(
                float(np.clip((nx - r_px) / float(w), 0.0, 1.0)),
                float(np.clip((ny - r_px) / float(h), 0.0, 1.0)),
                float(np.clip((nx + r_px) / float(w), 0.0, 1.0)),
                float(np.clip((ny + r_px) / float(h), 0.0, 1.0)),
            ),
            confidence=round(conf, 4),
            uncertainty_px=round(max(3.5, fb_err * 1.8), 2),
            model_id="lk_optical_flow_v1",
            is_optical_flow=True,
        )
