"""
Golf Tracer Studio R4 — Reversible Coordinate Space Transforms (`transforms.py`).
定義並驗證 4 階段可逆座標轉換鏈：
1. Coded Pixels (coded_width x coded_height, with container rotation 0/90/180/270)
2. Display Upright Pixels (display_width x display_height, zero double-rotation)
3. Source Normalized ([0.0, 1.0] in upright display space)
4. Crop / Pad / Output Pixels (original, 16:9, 9:16 with contain or cover)
"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class FrameGeometry:
    coded_width: int
    coded_height: int
    rotation: int = 0
    coordinate_space_version: int = 1

    def __init__(
        self,
        coded_width: int,
        coded_height: int,
        rotation: int | None = None,
        rotation_deg: int | None = None,
        coordinate_space_version: int = 1,
    ) -> None:
        rot_val = rotation_deg if rotation_deg is not None else (rotation if rotation is not None else 0)
        object.__setattr__(self, "coded_width", int(coded_width))
        object.__setattr__(self, "coded_height", int(coded_height))
        object.__setattr__(self, "rotation", int(rot_val))
        object.__setattr__(self, "coordinate_space_version", int(coordinate_space_version))

    @property
    def rotation_deg(self) -> int:
        return self.normalized_rotation

    @property
    def normalized_rotation(self) -> int:
        r = int(self.rotation) % 360
        if r in (90, 180, 270):
            return r
        return 0

    @property
    def display_width(self) -> int:
        if self.normalized_rotation in (90, 270):
            return self.coded_height
        return self.coded_width

    @property
    def display_height(self) -> int:
        if self.normalized_rotation in (90, 270):
            return self.coded_width
        return self.coded_height

    @property
    def upright_width(self) -> int:
        return self.display_width

    @property
    def upright_height(self) -> int:
        return self.display_height


@dataclass(frozen=True)
class OutputLayout:
    aspect_ratio: str  # "original" | "16:9" | "9:16"
    crop_mode: str  # "contain" | "cover"
    display_width: int
    display_height: int
    output_width: int
    output_height: int
    scale_x: float
    scale_y: float
    offset_x: float  # in output pixel space (positive = letterbox pad, negative = cover crop offset)
    offset_y: float

    @property
    def target_aspect(self) -> str:
        return self.aspect_ratio

    @property
    def upright_width(self) -> int:
        return self.display_width

    @property
    def upright_height(self) -> int:
        return self.display_height

    @property
    def scale(self) -> float:
        return self.scale_x / float(max(1, self.display_width))

    @property
    def pad_x(self) -> float:
        return self.offset_x

    @property
    def pad_y(self) -> float:
        return self.offset_y


def ensure_even(val: int) -> int:
    v = max(2, int(round(val)))
    return v if (v % 2 == 0) else (v + 1)


def rotate_coded_frame_to_upright(
    frame_bgr: np.ndarray,
    geometry: FrameGeometry | int,
    force_rotate: bool = False,
) -> np.ndarray:
    """
    將解碼後之影格轉為直立顯示方向 (Display Upright)，並嚴格防止二次旋轉 (Zero Double-Rotation)：
    - 若 OpenCV/FFmpeg 已自動套用 container rotation（即對於非正方形 90/270 度影片，
      frame_bgr 寬高已等於 display_width x display_height），除非 force_rotate=True，否則不重複旋轉。
    """
    h, w = frame_bgr.shape[:2]
    if isinstance(geometry, int):
        geom = FrameGeometry(coded_width=w, coded_height=h, rotation=geometry)
    else:
        geom = geometry

    rot = geom.normalized_rotation
    if rot == 0:
        return frame_bgr

    if (
        not force_rotate
        and rot in (90, 270)
        and geom.coded_width != geom.coded_height
        and w == geom.display_width
        and h == geom.display_height
    ):
        return frame_bgr

    if rot == 90:
        return cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
    if rot == 180:
        return cv2.rotate(frame_bgr, cv2.ROTATE_180)
    if rot == 270:
        return cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return frame_bgr


def coded_px_to_upright_norm(
    x_coded: float,
    y_coded: float,
    geometry: FrameGeometry,
) -> tuple[float, float]:
    """將未旋轉之 Coded Pixel 座標轉換為直立顯示空間之正規化座標 [0, 1]。"""
    cw = max(1.0, float(geometry.coded_width))
    ch = max(1.0, float(geometry.coded_height))
    nx = x_coded / cw
    ny = y_coded / ch
    rot = geometry.normalized_rotation
    if rot == 90:
        # 順時針 90 度: (x, y) -> (1 - ny, nx)
        ux, uy = 1.0 - ny, nx
    elif rot == 180:
        ux, uy = 1.0 - nx, 1.0 - ny
    elif rot == 270:
        # 逆時針 90 度 (270 CW): (x, y) -> (ny, 1 - nx)
        ux, uy = ny, 1.0 - nx
    else:
        ux, uy = nx, ny
    return (float(np.clip(ux, 0.0, 1.0)), float(np.clip(uy, 0.0, 1.0)))


def upright_norm_to_coded_px(
    x_norm: float,
    y_norm: float,
    geometry: FrameGeometry,
) -> tuple[float, float]:
    """將直立顯示空間正規化座標 [0, 1] 逆轉換回 Coded Pixel 座標。"""
    ux = float(np.clip(x_norm, 0.0, 1.0))
    uy = float(np.clip(y_norm, 0.0, 1.0))
    rot = geometry.normalized_rotation
    if rot == 90:
        nx, ny = uy, 1.0 - ux
    elif rot == 180:
        nx, ny = 1.0 - ux, 1.0 - uy
    elif rot == 270:
        nx, ny = 1.0 - uy, ux
    else:
        nx, ny = ux, uy
    return (nx * float(geometry.coded_width), ny * float(geometry.coded_height))


def roi_px_to_upright_norm(
    x_roi: float,
    y_roi: float,
    roi_box: tuple[int, int, int, int],
    display_width: int,
    display_height: int,
    roi_scale: float = 1.0,
) -> tuple[float, float]:
    """將局部 ROI crop 內像素座標還原為直立全畫面正規化座標 [0, 1]。"""
    rx1, ry1, _, _ = roi_box
    inv_scale = 1.0 / max(1e-6, float(roi_scale))
    abs_x = float(rx1) + (float(x_roi) * inv_scale)
    abs_y = float(ry1) + (float(y_roi) * inv_scale)
    return (
        float(np.clip(abs_x / max(1.0, float(display_width)), 0.0, 1.0)),
        float(np.clip(abs_y / max(1.0, float(display_height)), 0.0, 1.0)),
    )


def compute_output_layout(
    display_width: int | FrameGeometry = 1080,
    display_height: int | None = None,
    aspect_ratio: str = "original",
    crop_mode: str = "contain",
    target_short_side: int = 1080,
    pan_x_norm: float = 0.5,
    pan_y_norm: float = 0.5,
    *,
    geometry: FrameGeometry | None = None,
    target_aspect: str | None = None,
) -> OutputLayout:
    """
    計算輸出畫布幾何參數 (original / 16:9 / 9:16 × contain / cover)，
    確保所有寬高均為偶數像素，並支援與前端預覽完全一致之座標投影。
    支援傳入 `geometry=FrameGeometry(...)` 或 `(display_width, display_height)`。
    """
    if geometry is not None:
        dw = max(2, int(geometry.display_width))
        dh = max(2, int(geometry.display_height))
    elif isinstance(display_width, FrameGeometry):
        dw = max(2, int(display_width.display_width))
        dh = max(2, int(display_width.display_height))
    else:
        dw = max(2, int(display_width))
        dh = max(2, int(display_height if display_height is not None else 1920))

    eff_aspect = target_aspect if target_aspect is not None else aspect_ratio

    if eff_aspect == "16:9":
        out_h = ensure_even(target_short_side)
        out_w = ensure_even(int(round(out_h * 16.0 / 9.0)))
    elif eff_aspect == "9:16":
        out_w = ensure_even(target_short_side)
        out_h = ensure_even(int(round(out_w * 16.0 / 9.0)))
    else:
        out_w = ensure_even(dw)
        out_h = ensure_even(dh)

    if eff_aspect == "original":
        return OutputLayout(
            aspect_ratio="original",
            crop_mode=crop_mode,
            display_width=dw,
            display_height=dh,
            output_width=out_w,
            output_height=out_h,
            scale_x=float(out_w),
            scale_y=float(out_h),
            offset_x=0.0,
            offset_y=0.0,
        )

    if crop_mode == "cover":
        scale = max(out_w / float(dw), out_h / float(dh))
        scaled_w = dw * scale
        scaled_h = dh * scale
        px = float(np.clip(pan_x_norm, 0.0, 1.0))
        py = float(np.clip(pan_y_norm, 0.0, 1.0))
        off_x = -(scaled_w - out_w) * px
        off_y = -(scaled_h - out_h) * py
    else:
        scale = min(out_w / float(dw), out_h / float(dh))
        scaled_w = dw * scale
        scaled_h = dh * scale
        off_x = (out_w - scaled_w) / 2.0
        off_y = (out_h - scaled_h) / 2.0

    return OutputLayout(
        aspect_ratio=eff_aspect,
        crop_mode=crop_mode,
        display_width=dw,
        display_height=dh,
        output_width=out_w,
        output_height=out_h,
        scale_x=scaled_w,
        scale_y=scaled_h,
        offset_x=off_x,
        offset_y=off_y,
    )


def project_upright_norm_to_output_px(
    x_norm: float,
    y_norm: float,
    layout: OutputLayout,
) -> tuple[float, float]:
    """將直立正規化座標 [0, 1] 投影至輸出畫布像素座標 (out_x, out_y)。"""
    out_x = layout.offset_x + float(x_norm) * layout.scale_x
    out_y = layout.offset_y + float(y_norm) * layout.scale_y
    return (out_x, out_y)


def unproject_output_px_to_upright_norm(
    out_x: float,
    out_y: float,
    layout: OutputLayout,
) -> tuple[float, float]:
    """將輸出畫布像素座標逆投影回直立正規化座標 [0, 1]。"""
    nx = (float(out_x) - layout.offset_x) / max(1e-6, layout.scale_x)
    ny = (float(out_y) - layout.offset_y) / max(1e-6, layout.scale_y)
    return (float(np.clip(nx, 0.0, 1.0)), float(np.clip(ny, 0.0, 1.0)))


def canvas_click_to_upright_norm(
    client_x: float,
    client_y: float,
    rect_left: float,
    rect_top: float,
    rect_width: float,
    rect_height: float,
    display_width: int,
    display_height: int,
    object_fit: str = "contain",
) -> tuple[float, float]:
    """
    將瀏覽器 / WebKit Canvas 點擊座標 (含 CSS object-fit: contain letterbox padding)
    精準轉換為直立來源正規化座標 [0, 1]。
    """
    rw = max(1.0, float(rect_width))
    rh = max(1.0, float(rect_height))
    dw = max(1.0, float(display_width))
    dh = max(1.0, float(display_height))

    local_x = float(client_x) - float(rect_left)
    local_y = float(client_y) - float(rect_top)

    if object_fit == "contain":
        scale = min(rw / dw, rh / dh)
        rendered_w = dw * scale
        rendered_h = dh * scale
        pad_x = (rw - rendered_w) / 2.0
        pad_y = (rh - rendered_h) / 2.0
        nx = (local_x - pad_x) / max(1e-6, rendered_w)
        ny = (local_y - pad_y) / max(1e-6, rendered_h)
    else:
        nx = local_x / rw
        ny = local_y / rh

    return (float(np.clip(nx, 0.0, 1.0)), float(np.clip(ny, 0.0, 1.0)))


def scale_width_at_1080(
    first_arg: OutputLayout | float,
    second_arg: float | int = 1080,
    output_height: int | None = None,
) -> int:
    """
    根據輸出解析度短邊相對於 1080px 等比例縮放線寬與特效半徑。
    支援 `scale_width_at_1080(layout, width_px)` 與 `scale_width_at_1080(width_px, out_w, out_h)` 兩種呼叫方式。
    """
    if isinstance(first_arg, OutputLayout):
        layout = first_arg
        width_px = float(second_arg)
        short_side = float(min(max(1, layout.output_width), max(1, layout.output_height)))
    else:
        width_px = float(first_arg)
        out_w = int(second_arg)
        out_h = int(output_height if output_height is not None else out_w)
        short_side = float(min(max(1, out_w), max(1, out_h)))
    return max(1, int(round(width_px * (short_side / 1080.0))))
