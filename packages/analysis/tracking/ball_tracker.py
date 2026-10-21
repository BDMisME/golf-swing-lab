import logging
import math
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


def validate_ball_trajectory_physics(points: list[dict[str, Any]]) -> bool:
    """
    高爾夫出球物理合理性檢核:
    1. 軌跡點數必須 >= 3
    2. 初始出球點 y 必須在打擊墊或擊球台合理區間 (y >= 0.48)
    3. 終點 y 必須小於等於起點 y (小白球朝天空上方飛行，容許 0.04 測量誤差)
    4. 總位移長度必須具備實質飛行向量 (hypot(dx, dy) >= 0.04)，相容左打者 (左飛) 與右打者 (右飛)
    """
    if len(points) < 3:
        return False
    init_pt = points[0]
    last_pt = points[-1]
    if float(init_pt["y"]) < 0.48:
        return False
    if float(last_pt["y"]) > float(init_pt["y"]) + 0.04:
        return False
    dx = float(last_pt["x"]) - float(init_pt["x"])
    dy = float(last_pt["y"]) - float(init_pt["y"])
    if (dx * dx + dy * dy) < 0.0016:  # 總位移小於 0.04
        return False
    # 5. 出球升空向量檢核: 全揮桿擊球出球必有真實仰角升空 (dy <= -0.06，畫面 y 向上遞減)
    # 排除水平穿越地面或向後平移之雜訊，同時相容左打 (dx < 0) 與右打 (dx > 0)
    if dy > -0.06:
        return False
    return True


def analyze_ball_launch_continuity(
    raw_obs: list[dict[str, Any]],
    impact_ref_ms: int,
) -> dict[str, Any]:
    """
    同一顆球的時序追蹤與連續性檢查 (P0-A):
    區分: stationary (打擊席靜止), moving (位移起點), airborne (升空飛行), occluded (遺失)。
    物理原則:
    1. 靜止球被辨識到不等於擊球。
    2. 必須具有可辨識的位移量 (與打擊席靜止基準相比 hypot(dx, dy) >= 0.035) 且仰角升空 (dy <= -0.015)。
    3. 連續性檢查: 升空後至少連續 2 幀保持位移增加或騰空。
    """
    if len(raw_obs) < 2:
        return {
            "state": "occluded" if not raw_obs else "stationary",
            "launch_ms": None,
            "stationary_point": None,
            "airborne_points": [],
            "max_displacement": 0.0,
            "is_launch": False,
        }

    # 1. 尋找擊球瞬間前打擊席上的靜止球基準點 (以 impact 前或前 1~3 幀之球位為錨點)
    early_obs = [p for p in raw_obs if p["time_ms"] <= impact_ref_ms + 40]
    if not early_obs:
        early_obs = raw_obs[: min(3, len(raw_obs))]

    base_x = float(np.median([p["x"] for p in early_obs]))
    base_y = float(np.median([p["y"] for p in early_obs]))

    annotated = []
    max_disp = 0.0
    for p in raw_obs:
        dx = float(p["x"]) - base_x
        dy = float(p["y"]) - base_y
        dist = math.hypot(dx, dy)
        max_disp = max(max_disp, dist)

        # 狀態細緻判定
        if dist < 0.025:
            st = "stationary"
        elif dy <= -0.015 and dist >= 0.035:
            st = "airborne"
        elif dist >= 0.025:
            st = "moving"
        else:
            st = "stationary"

        annotated.append({**p, "dx": dx, "dy": dy, "dist": dist, "state": st})

    # 2. 檢驗是否具備「靜止 -> 升空」的真實物理轉換與時間相鄰性 (P0-A 升級)
    airborne_pts = sorted([p for p in annotated if p["state"] == "airborne"], key=lambda p: p["time_ms"])

    # 嚴格條件: 必須存在時間相鄰 (dt <= 55ms) 且位移遞增/高度遞減的連續 2 影格觀測點
    valid_pair = None
    if len(airborne_pts) >= 2:
        for k in range(len(airborne_pts) - 1):
            p1 = airborne_pts[k]
            p2 = airborne_pts[k + 1]
            dt = p2["time_ms"] - p1["time_ms"]
            # 時間相鄰性驗證：必須在連續影格或至多允許 1 幀落空 (dt <= 55ms)
            if 0 < dt <= 55:
                step_disp = math.hypot(p2["x"] - p1["x"], p2["y"] - p1["y"])
                # 連續性驗證：維持升空飛行向量，排除單幀瞬移噪聲 (step_disp <= 0.35)
                if p2["dist"] >= p1["dist"] - 0.01 and p2["y"] <= p1["y"] + 0.03 and step_disp <= 0.35:
                    valid_pair = (p1, p2)
                    break

    if valid_pair is not None:
        first_air = valid_pair[0]
        return {
            "state": "airborne",
            "launch_ms": int(round(first_air["time_ms"])),
            "stationary_point": (base_x, base_y),
            "airborne_points": airborne_pts,
            "max_displacement": max_disp,
            "is_launch": True,
        }

    # 若全無升空，但有偵測到點，且位移很小，則為純靜止球 (排除靜止球誤判擊球)
    if max_disp < 0.030:
        return {
            "state": "stationary",
            "launch_ms": None,
            "stationary_point": (base_x, base_y),
            "airborne_points": [],
            "max_displacement": max_disp,
            "is_launch": False,
        }

    return {
        "state": "unclear_motion",
        "launch_ms": None,
        "stationary_point": (base_x, base_y),
        "airborne_points": [],
        "max_displacement": max_disp,
        "is_launch": False,
    }


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
            from packages.analysis.pose.yolo_extractor import _YOLO_GLOBAL_LOCK

            with _YOLO_GLOBAL_LOCK:
                results_list = list(self.model(roi_crop, verbose=False, conf=self.conf_threshold))
            if not results_list:
                return None

            first_res: Any = results_list[0]
            boxes = getattr(first_res, "boxes", None)
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
                # 小白球寬高在局部 ROI 內通常小於 45%
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
    ) -> list[dict[str, Any]]:
        """
        在擊球瞬間前後精準捕捉出球軌跡，透過卡爾曼濾波器輸出發光 Toptracer 點位列表。
        嚴守 P0-A: 只有在球真正升空飛行時才產生發光軌跡，靜止球不輸出飛行彈道。
        """
        feedback = self.track_swing_launch_with_feedback(
            video_path=video_path,
            impact_ms=impact_ms,
            player_wrist_norm=player_wrist_norm,
            duration_ms=duration_ms,
        )
        return feedback.get("trajectory_points", [])

    def track_swing_launch_with_feedback(
        self,
        video_path: str | Path,
        impact_ms: int,
        player_wrist_norm: tuple[float, float] | None = None,
        duration_ms: int = 1200,
    ) -> dict[str, Any]:
        """
        在擊球瞬間前後精準捕捉出球軌跡，並進行同一顆球的時序追蹤與連續性檢查 (P0-A)。
        只有在有明確位移與升空證據時，才判定為可靠出球 (is_valid=True, confirmed_strike 候選)。
        靜止球保留為 stationary，不標記出球。
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return {
                "trajectory_points": [],
                "observed_launch_ms": None,
                "observed_count": 0,
                "is_valid": False,
                "launch_state": "occluded",
                "max_displacement": 0.0,
            }

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

        start_ms = max(0, impact_ms - 250)
        end_ms = impact_ms + duration_ms
        cap.set(cv2.CAP_PROP_POS_MSEC, float(start_ms))

        raw_observations: list[dict[str, Any]] = []

        try:
            while True:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break
                pts_ms = int(round(cap.get(cv2.CAP_PROP_POS_MSEC)))
                if pts_ms > end_ms:
                    break

                if pts_ms >= start_ms:
                    progress = min(1.0, max(0.0, (pts_ms - impact_ms) / float(duration_ms)))
                    exp_x2 = min(w, int(roi_x2 + progress * (w - roi_x2)))
                    exp_y1 = max(0, int(roi_y1 - progress * roi_y1 * 0.8))

                    det = self.detect_in_roi(frame, (roi_x1, exp_y1, exp_x2, roi_y2))
                    if det:
                        mx, my, conf = det
                        raw_observations.append(
                            {
                                "time_ms": pts_ms,
                                "x": float(mx),
                                "y": float(my),
                                "conf": float(conf),
                            }
                        )
        finally:
            cap.release()

        # -------------------------------------------------------------
        # P0-A 核心檢驗: 區分 stationary 與 airborne
        # -------------------------------------------------------------
        analysis = analyze_ball_launch_continuity(raw_observations, impact_ref_ms=impact_ms)
        launch_state = analysis["state"]
        launch_ms = analysis["launch_ms"]
        max_disp = analysis["max_displacement"]
        obs_count = len(raw_observations)

        # 靜止球防呆保護: 若球完全靜止 (stationary) 或未見升空，絕不輸出飛行軌跡與出球時間
        if not analysis["is_launch"] or launch_ms is None:
            logger.info(
                f"小白球時序檢核結果: state={launch_state}, max_disp={max_disp:.4f} "
                f"(未見真球升空飛行，嚴守誠信原則不判定出球，不輸出推論假球路)"
            )
            return {
                "trajectory_points": [],
                "observed_launch_ms": None,
                "observed_count": obs_count,
                "is_valid": False,
                "launch_state": launch_state,
                "max_displacement": max_disp,
            }

        # -------------------------------------------------------------
        # 若確認有升空出球，啟動卡爾曼濾波器進行軌跡平滑補全
        # -------------------------------------------------------------
        tracker = KalmanBallTracker(fps=fps)
        trajectory_points: list[dict[str, Any]] = []
        airborne_map = {p["time_ms"]: p for p in analysis["airborne_points"]}

        # 從出球點開始建立飛行彈道
        sorted_times = sorted(list({p["time_ms"] for p in raw_observations if p["time_ms"] >= launch_ms}))
        for t_ms in sorted_times:
            if t_ms in airborne_map:
                pt = airborne_map[t_ms]
                sx, sy = tracker.update(pt["x"], pt["y"], t_ms)
                trajectory_points.append(
                    {
                        "time_ms": float(t_ms),
                        "x": float(np.clip(sx, 0.0, 1.0)),
                        "y": float(np.clip(sy, 0.0, 1.0)),
                        "raw_x": round(pt["x"], 4),
                        "raw_y": round(pt["y"], 4),
                        "point_type": "observed",
                        "confidence": round(pt["conf"], 3),
                    }
                )

        if trajectory_points and not validate_ball_trajectory_physics(trajectory_points):
            logger.info("卡爾曼出球軌跡未通過物理合理性檢核，自動濾除。")
            return {
                "trajectory_points": [],
                "observed_launch_ms": None,
                "observed_count": obs_count,
                "is_valid": False,
                "launch_state": "rejected_by_physics",
                "max_displacement": max_disp,
            }

        return {
            "trajectory_points": trajectory_points,
            "observed_launch_ms": launch_ms,
            "observed_count": obs_count,
            "is_valid": True,
            "launch_state": "airborne",
            "max_displacement": max_disp,
        }

