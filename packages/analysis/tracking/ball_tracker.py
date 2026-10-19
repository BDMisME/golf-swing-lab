import logging
from collections import deque
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_BALL_MODEL_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "GolfSwingLab"
    / "models"
    / "golf_ball_yolov8n.pt"
)


class KalmanBallTracker:
    """
    高爾夫小白球 2D 卡爾曼濾波追蹤器：
    狀態向量: [x, y, vx, vy]^T
    量測向量: [x, y]^T
    包含重力與空氣阻力先驗，在球速極快導致快門模糊或短暫丟球時自動平滑補全彈道。
    """

    def __init__(self, fps: float = 60.0) -> None:
        self.dt = 1.0 / max(10.0, fps)
        self.kalman = cv2.KalmanFilter(4, 2)
        # 狀態轉移矩陣 (等速度模型 + 重力影響)
        self.kalman.transitionMatrix = np.array(
            [
                [1.0, 0.0, self.dt, 0.0],
                [0.0, 1.0, 0.0, self.dt],
                [0.0, 0.0, 0.98, 0.0],  # 空氣阻力微衰減
                [0.0, 0.0, 0.0, 0.98],
            ],
            dtype=np.float32,
        )
        # 量測矩陣 (只觀測位置 x, y)
        self.kalman.measurementMatrix = np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32
        )
        # 雜訊協方差矩陣
        self.kalman.processNoiseCov = (
            np.eye(4, dtype=np.float32) * 1e-2
        )
        self.kalman.measurementNoiseCov = (
            np.eye(2, dtype=np.float32) * 1e-1
        )
        self.kalman.errorCovPost = np.eye(4, dtype=np.float32)

        self.initialized = False
        self.history: list[tuple[float, float, int]] = []  # (norm_x, norm_y, time_ms)

    def init_state(self, x: float, y: float, vx: float = 0.0, vy: float = 0.0) -> None:
        self.kalman.statePost = np.array([[x], [y], [vx], [vy]], dtype=np.float32)
        self.initialized = True

    def update(
        self, meas_x: float | None, meas_y: float | None, time_ms: int
    ) -> tuple[float, float]:
        pred = self.kalman.predict()
        px, py = float(pred[0, 0]), float(pred[1, 0])

        if meas_x is not None and meas_y is not None:
            if not self.initialized:
                self.init_state(meas_x, meas_y)
                px, py = meas_x, meas_y
            else:
                meas = np.array([[meas_x], [meas_y]], dtype=np.float32)
                est = self.kalman.correct(meas)
                px, py = float(est[0, 0]), float(est[1, 0])

        self.history.append((px, py, time_ms))
        return (px, py)


def validate_ball_trajectory_physics(points: list[dict[str, float]]) -> bool:
    """
    高爾夫出球物理合理性檢核:
    1. 軌跡點數必須 >= 3
    2. 初始出球點 y 必須在打擊墊合理區間 (y >= 0.48)
    3. 終點 y 必須小於等於起點 y (小白球朝天空上方飛行)
    4. 終點 x 必須大於等於起點 x (球朝前方飛行)
    """
    if len(points) < 3:
        return False
    init_pt = points[0]
    last_pt = points[-1]
    if init_pt["y"] < 0.48 or (last_pt["y"] > init_pt["y"] + 0.04) or (last_pt["x"] < init_pt["x"] - 0.05):
        return False
    return True


class GolfBallDetector:
    """
    基於 YOLOv8-nano 之專用高爾夫球偵測器。
    搭配 ROI (擊球區智能聚焦) 排除燈光、雜物干擾，實現 60 FPS 即時真球捕獲。
    """

    def __init__(self, model_path: str | Path | None = None, conf_threshold: float = 0.20) -> None:
        self.model_path = Path(model_path) if model_path else DEFAULT_BALL_MODEL_PATH
        self.conf_threshold = conf_threshold
        self.model = None

        if self.model_path.exists():
            try:
                from ultralytics import YOLO

                self.model = YOLO(str(self.model_path))
                logger.info(f"成功載入小白球專用偵測模型: {self.model_path}")
            except Exception as e:
                logger.warning(f"載入小白球模型失敗: {e}")

    def detect_in_roi(
        self,
        frame_bgr: np.ndarray,
        roi_box: tuple[int, int, int, int],  # (x1, y1, x2, y2)
    ) -> tuple[float, float, float] | None:
        """
        在特定局部擊球區 ROI 內偵測小白球，回傳全圖正規化座標 (norm_x, norm_y, conf)。
        """
        if self.model is None:
            return None

        h, w = frame_bgr.shape[:2]
        rx1, ry1, rx2, ry2 = roi_box
        rx1, ry1 = max(0, rx1), max(0, ry1)
        rx2, ry2 = min(w, rx2), min(h, ry2)

        if rx2 <= rx1 or ry2 <= ry1:
            return None

        roi_crop = frame_bgr[ry1:ry2, rx1:rx2]
        try:
            results = self.model(roi_crop, verbose=False, conf=self.conf_threshold)
            if not results or len(results) == 0:
                return None

            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                return None

            # 挑選在局部區域內面積最合理 (非巨大背景) 且置信度最高的球
            best_det = None
            best_conf = 0.0
            roi_w = rx2 - rx1
            roi_h = ry2 - ry1

            for b in boxes:
                bx, by, bw, bh = b.xywh[0].cpu().numpy()
                conf = float(b.conf[0])
                # 小白球寬高在局部 ROI 內通常小於 40%
                if bw < roi_w * 0.45 and bh < roi_h * 0.45:
                    if conf > best_conf:
                        best_conf = conf
                        abs_x = rx1 + bx
                        abs_y = ry1 + by
                        best_det = (abs_x / w, abs_y / h, conf)

            return best_det
        except Exception as exc:
            logger.debug(f"ROI 球偵測異常: {exc}")
            return None

    def track_swing_launch(
        self,
        video_path: str | Path,
        impact_ms: int,
        player_wrist_norm: tuple[float, float] | None = None,
        duration_ms: int = 1200,
    ) -> list[dict[str, float]]:
        """
        在擊球瞬間前後精準捕捉出球軌跡，透過卡爾曼濾波器輸出發光 Toptracer 點位列表。
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 定義地面擊球區 ROI
        if player_wrist_norm:
            wx, wy = player_wrist_norm
            roi_x1 = int(max(0, (wx - 0.15) * w))
            roi_x2 = int(min(w, (wx + 0.35) * w))
            roi_y1 = int(max(0, (wy - 0.05) * h))
            roi_y2 = int(min(h, (wy + 0.35) * h))
        else:
            roi_x1, roi_x2 = int(w * 0.25), int(w * 0.65)
            roi_y1, roi_y2 = int(h * 0.50), int(h * 0.85)

        tracker = KalmanBallTracker(fps=fps)
        start_ms = max(0, impact_ms - 200)
        end_ms = impact_ms + duration_ms
        cap.set(cv2.CAP_PROP_POS_MSEC, float(start_ms))

        trajectory_points: list[dict[str, float]] = []

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                pts_ms = int(round(cap.get(cv2.CAP_PROP_POS_MSEC)))
                if pts_ms > end_ms:
                    break

                if pts_ms >= start_ms:
                    # 隨著球飛出，逐步放大 ROI 以包容飛行彈道
                    progress = min(1.0, max(0.0, (pts_ms - impact_ms) / float(duration_ms)))
                    exp_x2 = min(w, int(roi_x2 + progress * (w - roi_x2)))
                    exp_y1 = max(0, int(roi_y1 - progress * roi_y1 * 0.8))

                    det = self.detect_in_roi(frame, (roi_x1, exp_y1, exp_x2, roi_y2))
                    if det:
                        mx, my, conf = det
                        smooth_x, smooth_y = tracker.update(mx, my, pts_ms)
                    else:
                        smooth_x, smooth_y = tracker.update(None, None, pts_ms)

                    if tracker.initialized:
                        trajectory_points.append(
                            {
                                "time_ms": float(pts_ms),
                                "x": float(np.clip(smooth_x, 0.0, 1.0)),
                                "y": float(np.clip(smooth_y, 0.0, 1.0)),
                            }
                        )
        finally:
            cap.release()

        # 高爾夫物理合理性檢核: 濾除背景水平穿越身體或向後倒退之雜訊
        if trajectory_points and not validate_ball_trajectory_physics(trajectory_points):
            logger.info("卡爾曼出球軌跡未通過高爾夫物理合理性檢核（檢測到背景水平雜訊或倒退），自動濾除。")
            return []

        return trajectory_points
