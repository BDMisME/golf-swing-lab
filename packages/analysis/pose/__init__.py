import logging
import os
from typing import Any

from packages.analysis.pose.extractor import (
    FramePoseResult,
    Landmark2D,
    PoseExtractor,
    VideoQualitySummary,
)

logger = logging.getLogger(__name__)

def create_pose_extractor(backend: str | None = None, model_name: str = "yolov8x-pose.pt") -> Any:
    """
    動態建立高爾夫 2D 姿態估計引擎：
    優先載入 Ultralytics YOLOv8-pose (支援 Apple Silicon MPS 加速)；
    若環境不支援或指定 mediapipe，則自動降級使用 Google MediaPipe。
    """
    selected = backend or os.environ.get("POSE_BACKEND", "yolov8x-pose")
    if selected.lower() in ("mediapipe", "mp", "pose-v1"):
        logger.info("使用 MediaPipe PoseLandmarker 引擎")
        return PoseExtractor()

    try:
        from packages.analysis.pose.yolo_extractor import YoloPoseExtractor
        raw_name = selected.lower().replace(".pt", "")
        if "yolo" in raw_name and "-pose" not in raw_name:
            m_name = f"{raw_name}-pose.pt"
        elif not selected.endswith(".pt"):
            m_name = f"{selected}.pt"
        else:
            m_name = selected
        return YoloPoseExtractor(model_name=m_name)
    except Exception as exc:
        logger.warning(f"初始化 YOLOv8-pose 失敗 ({exc})，自動安全降級使用 MediaPipe: {exc}")
        return PoseExtractor()

__all__ = [
    "FramePoseResult",
    "Landmark2D",
    "PoseExtractor",
    "VideoQualitySummary",
    "create_pose_extractor",
]

