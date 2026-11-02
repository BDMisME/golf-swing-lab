"""
Golf Tracer Studio R4 — Direct Clubhead Detection Adapter (`clubhead_detector.py`).
支援載入本地專用桿頭/桿身偵測模型 (`swingtrace-yolo11m.pt`)，並嚴格區分：
- `club_head` (直接桿頭視覺證據 -> detector_observed)
- `club_shaft` (桿身輔助框)
- `hands` (僅供排除手部誤判，絕不當作桿頭輸出)
若本機未安裝權重 (如 HuggingFace gated repo 未經使用者授權下載)，誠實回報 `MODEL_UNAVAILABLE`，絕不偽造偵測結果。
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_CLUBHEAD_MODEL_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "GolfSwingLab"
    / "models"
    / "swingtrace-yolo11m.pt"
)


@dataclass(frozen=True)
class ClubDetectionResult:
    head_x_norm: float
    head_y_norm: float
    head_bbox_norm: tuple[float, float, float, float]
    confidence: float
    uncertainty_px: float
    shaft_bbox_norm: tuple[float, float, float, float] | None = None
    hands_bbox_norm: tuple[float, float, float, float] | None = None
    model_id: str = "swingtrace-yolo11m"


def detect_compute_device() -> str:
    """偵測本機可用推論硬體：優先驗證 Apple Silicon MPS，不可用時優雅降級至 CPU。"""
    try:
        import torch

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


class ClubheadDetector:
    """專用高爾夫桿頭視覺偵測器 Adapter。"""

    def __init__(
        self,
        model_path: str | Path | None = None,
        conf_threshold: float = 0.28,
        injected_model: Any | None = None,
    ) -> None:
        self.model_path = Path(model_path) if model_path else DEFAULT_CLUBHEAD_MODEL_PATH
        self.conf_threshold = float(conf_threshold)
        self.device = detect_compute_device()
        self.model: Any | None = injected_model
        self.model_sha256: str | None = None
        self.availability_status: str = "MODEL_UNAVAILABLE"
        self.unavailability_reason: str = (
            "本機未安裝 swingtrace-yolo11m.pt 權重（HuggingFace 儲存庫為 gated: auto / AGPL-3.0，需使用者本人登入授權後放置於 ~/Library/Application Support/GolfSwingLab/models/）"
        )

        if self.model is not None:
            self.availability_status = "READY"
            self.unavailability_reason = ""
            self.model_sha256 = "injected_test_model"
        elif self.model_path.exists() and self.model_path.stat().st_size > 1024:
            try:
                from ultralytics import YOLO

                self.model = YOLO(str(self.model_path))
                h = hashlib.sha256()
                with self.model_path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                self.model_sha256 = h.hexdigest()
                self.availability_status = "READY"
                self.unavailability_reason = ""
                logger.info(f"成功載入桿頭專用模型: {self.model_path} (sha256={self.model_sha256[:12]})")
            except Exception as exc:
                self.model = None
                self.availability_status = "MODEL_LOAD_FAILED"
                self.unavailability_reason = f"載入桿頭模型失敗: {exc}"
                logger.warning(self.unavailability_reason)

    @property
    def is_available(self) -> bool:
        return self.model is not None and self.availability_status == "READY"

    def get_status_dict(self) -> dict[str, Any]:
        return {
            "name": "swingtrace-yolo11m",
            "task": "club_head_and_shaft_detection",
            "local_path": str(self.model_path),
            "available": self.is_available,
            "availability": self.availability_status,
            "sha256": self.model_sha256,
            "license": "AGPL-3.0 (gated on HuggingFace)",
            "device": self.device,
            "notes": self.unavailability_reason or "Ready for local inference",
        }

    def detect_in_roi(
        self,
        frame_bgr: np.ndarray,
        roi_box: tuple[int, int, int, int],
        wrist_hint_norm: tuple[float, float] | None = None,
    ) -> ClubDetectionResult | None:
        """
        在指定 ROI 內偵測真實 `club_head`。
        嚴格防呆：
        1. 若模型未就緒，直接回傳 None (`MODEL_UNAVAILABLE`)。
        2. 排除與 `hands` 或 `wrist_hint_norm` 距離過近 (< 0.06 畫面比例) 之誤檢框，確保 0 例 wrist-as-head。
        """
        if not self.is_available or self.model is None:
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
            names = getattr(first_res, "names", None) or getattr(self.model, "names", {}) or {}
            if boxes is None or len(boxes) == 0:
                return None

            best_head: tuple[float, float, tuple[float, float, float, float], float, float] | None = None
            best_shaft: tuple[float, float, float, float] | None = None
            best_hands: tuple[float, float, float, float] | None = None

            for b in boxes:
                bx, by, bw, bh = b.xywh[0].cpu().numpy()
                conf = float(b.conf[0])
                cls_id = int(b.cls[0]) if hasattr(b, "cls") and len(b.cls) > 0 else 0
                cls_name = str(names.get(cls_id, "")).lower()

                abs_cx = (rx1 + float(bx)) / float(w)
                abs_cy = (ry1 + float(by)) / float(h)
                norm_w = float(bw) / float(w)
                norm_h = float(bh) / float(h)
                bbox_norm = (
                    float(np.clip(abs_cx - norm_w / 2.0, 0.0, 1.0)),
                    float(np.clip(abs_cy - norm_h / 2.0, 0.0, 1.0)),
                    float(np.clip(norm_w, 0.0, 1.0)),
                    float(np.clip(norm_h, 0.0, 1.0)),
                )

                if "hand" in cls_name:
                    best_hands = bbox_norm
                    continue
                if "shaft" in cls_name:
                    best_shaft = bbox_norm
                    continue

                # 僅接受明確為 club_head / head / 類別 0 (於專用桿頭模型中) 之偵測框
                if "head" in cls_name or "club" in cls_name or cls_id in (0, 1):
                    # 防呆：若距離手腕小於 0.065，拒絕將手部/握把誤認為桿頭
                    if wrist_hint_norm is not None:
                        dist_to_wrist = float(np.hypot(abs_cx - wrist_hint_norm[0], abs_cy - wrist_hint_norm[1]))
                        if dist_to_wrist < 0.065:
                            continue
                    if best_head is None or conf > best_head[3]:
                        unc_px = float(max(bw, bh) * 0.35 * (1080.0 / max(1.0, float(min(w, h)))))
                        best_head = (
                            float(np.clip(abs_cx, 0.0, 1.0)),
                            float(np.clip(abs_cy, 0.0, 1.0)),
                            bbox_norm,
                            conf,
                            unc_px,
                        )

            if best_head is None:
                return None

            # 額外檢查：若檢出 hands bbox，桿頭中心不可落於 hands bbox 內部
            if best_hands is not None:
                hx1, hy1, hw, hh = best_hands
                if (hx1 <= best_head[0] <= hx1 + hw) and (hy1 <= best_head[1] <= hy1 + hh):
                    return None

            return ClubDetectionResult(
                head_x_norm=best_head[0],
                head_y_norm=best_head[1],
                head_bbox_norm=best_head[2],
                confidence=best_head[3],
                uncertainty_px=round(best_head[4], 2),
                shaft_bbox_norm=best_shaft,
                hands_bbox_norm=best_hands,
                model_id=f"swingtrace-yolo11m:{(self.model_sha256 or 'local')[:8]}",
            )
        except Exception as exc:
            logger.debug(f"Clubhead ROI 偵測異常: {exc}")
            return None
