import logging
import threading
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch

from packages.analysis.pose.extractor import FramePoseResult, Landmark2D

logger = logging.getLogger(__name__)

# 全域推論鎖：防止 macOS Metal/MPS 在多執行緒或多測試同時呼叫時引發 SIGABRT (Metal context collision)
_YOLO_GLOBAL_LOCK = threading.Lock()

# COCO 17 關鍵點到高爾夫幾何字典的對照表
YOLO_COCO_MAP: dict[str, int] = {
    "nose": 0,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

# 預設本地持久化模型目錄 (Mac 桌面 App 規範)
DEFAULT_DESKTOP_MODEL_DIR = (
    Path.home() / "Library" / "Application Support" / "GolfSwingLab" / "models"
)


class YoloPoseExtractor:
    """
    基於 Ultralytics YOLOv8-pose 之頂級 2D 人體骨架與關節點抽取器。
    原生支援 Apple Silicon Metal (MPS) 硬體加速，徹底解決高爾夫下桿快門殘影手腕遺失之痛點。
    輸出與原 PoseExtractor 介面 100% 相容。
    """

    def __init__(
        self,
        model_name: str = "yolov8x-pose.pt",
        device: str | None = None,
        conf_threshold: float = 0.25,
    ) -> None:
        self.model_name = model_name
        self.conf_threshold = conf_threshold

        # 1. 決定運算裝置 (優先使用 Mac Apple Silicon Metal - MPS)
        if device is not None:
            self.device = device
        elif torch.backends.mps.is_available():
            self.device = "mps"
        elif torch.cuda.is_available():
            self.device = "cuda"
        else:
            self.device = "cpu"

        # 2. 確定本機模型持久化儲存路徑
        self.model_path = self._resolve_model_path(model_name)
        logger.info(
            f"正在初始化 YOLOv8-pose 引擎: model={self.model_name}, device={self.device}, path={self.model_path}"
        )

        from ultralytics import YOLO

        self.model = YOLO(str(self.model_path))

    def _resolve_model_path(self, model_name: str) -> Path:
        """解析模型權重路徑，優先讀取本地持久化目錄，若無則自動快取。"""
        try:
            DEFAULT_DESKTOP_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            desktop_path = DEFAULT_DESKTOP_MODEL_DIR / model_name
            if desktop_path.exists():
                return desktop_path
        except Exception:
            pass

        # 專案內部模型路徑
        repo_path = Path(__file__).parent / "models" / model_name
        if repo_path.exists():
            return repo_path

        # 當前工作目錄
        cwd_path = Path.cwd() / model_name
        if cwd_path.exists():
            return cwd_path

        # 若本地皆不存在，直接傳遞檔名讓 Ultralytics 下載並快取
        return Path(model_name)

    def close(self) -> None:
        """釋放 GPU / MPS 記憶體。"""
        if hasattr(self, "model"):
            del self.model
        if self.device == "mps" and hasattr(torch, "mps"):
            torch.mps.empty_cache()
        elif self.device == "cuda" and hasattr(torch, "cuda"):
            torch.cuda.empty_cache()

    def analyze_frame(
        self,
        frame_bgr: np.ndarray,
        time_ms: int,
        frame_idx: int,
        prev_gray: np.ndarray | None = None,
        prev_wrist: tuple[float, float] | None = None,
    ) -> tuple[FramePoseResult, np.ndarray, tuple[float, float] | None]:
        """對單一影格執行 YOLOv8-pose 高精度推論與品質指標提取。"""
        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        camera_motion = 0.0
        if prev_gray is not None and prev_gray.shape == gray.shape:
            border_diff = float(
                np.mean(
                    np.abs(
                        gray[:, : max(8, w // 10)].astype(np.float32)
                        - prev_gray[:, : max(8, w // 10)].astype(np.float32)
                    )
                )
            )
            camera_motion = border_diff / 255.0

        flags: list[str] = []
        if brightness < 35.0:
            flags.append("low_light")
        if camera_motion > 0.08:
            flags.append("camera_motion")

        landmarks: dict[str, Landmark2D] = {}
        person_count = 0
        source = f"yolov8-pose-{self.model_name.replace('.pt', '')}"

        try:
            # 執行 YOLOv8-pose 推論 (加全域鎖保護 MPS/Metal 執行緒安全)
            with _YOLO_GLOBAL_LOCK:
                results = self.model(
                    frame_bgr,
                    device=self.device,
                    verbose=False,
                    conf=self.conf_threshold,
                )
            results_list = list(results) if results else []

            if results_list:
                res: Any = results_list[0]
                boxes = getattr(res, "boxes", None)
                person_count = len(boxes) if boxes is not None else 0
                if person_count > 1:
                    flags.append("multi_person")

                keypoints = getattr(res, "keypoints", None)
                if keypoints is not None and getattr(keypoints, "data", None) is not None and len(keypoints.data) > 0:
                    # 選擇畫面中最顯著、置信度最高的目標選手 (Primary Golfer)
                    kpts = keypoints.data[0].cpu().numpy()  # shape: [17, 3] (x, y, conf)

                    for name, coco_idx in YOLO_COCO_MAP.items():
                        if coco_idx < len(kpts):
                            pt_x, pt_y, pt_conf = kpts[coco_idx]
                            # 正規化座標為 0.0 ~ 1.0
                            norm_x = float(np.clip(pt_x / max(1, w), 0.0, 1.0))
                            norm_y = float(np.clip(pt_y / max(1, h), 0.0, 1.0))
                            norm_vis = float(np.clip(pt_conf, 0.0, 1.0))

                            landmarks[name] = Landmark2D(
                                x=norm_x,
                                y=norm_y,
                                visibility=norm_vis,
                            )
        except Exception as exc:
            logger.warning(f"YOLOv8-pose 單幀推論異常 (t={time_ms}ms): {exc}")
            flags.append("inference_error")

        if landmarks:
            vis_list = [lm.visibility for lm in landmarks.values()]
            pose_confidence = float(np.mean(vis_list)) * (
                len(landmarks) / len(YOLO_COCO_MAP)
            )
            if "low_light" in flags:
                pose_confidence *= 0.70
            if "multi_person" in flags:
                pose_confidence *= 0.85
            pose_confidence = float(np.clip(pose_confidence, 0.0, 1.0))
        else:
            pose_confidence = 0.0
            flags.append("pose_missing")

        # 取得手腕位置用於計算運動能量
        wrist_pos: tuple[float, float] | None = None
        rw = landmarks.get("right_wrist")
        lw = landmarks.get("left_wrist")
        if rw and rw.visibility >= 0.35 and lw and lw.visibility >= 0.35:
            wrist_pos = ((rw.x + lw.x) / 2.0, (rw.y + lw.y) / 2.0)
        elif rw and rw.visibility >= 0.35:
            wrist_pos = (rw.x, rw.y)
        elif lw and lw.visibility >= 0.35:
            wrist_pos = (lw.x, lw.y)

        wrist_motion_energy = 0.0
        if wrist_pos is not None and prev_wrist is not None:
            dx = wrist_pos[0] - prev_wrist[0]
            dy = wrist_pos[1] - prev_wrist[1]
            wrist_motion_energy = float(np.hypot(dx, dy))

        return (
            FramePoseResult(
                time_ms=time_ms,
                frame_idx=frame_idx,
                landmarks=landmarks,
                pose_confidence=pose_confidence,
                wrist_motion_energy=wrist_motion_energy,
                person_count=person_count,
                brightness=brightness,
                sharpness=sharpness,
                camera_motion=camera_motion,
                source=source,
                flags=flags,
            ),
            gray,
            wrist_pos,
        )
