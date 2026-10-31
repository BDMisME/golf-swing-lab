"""
Golf Tracer Studio R4 — Adaptive Left/Right & Multi-Direction ROI Planner (`roi_planner.py`).
解決既有 ball_tracker 僅向右擴展 ROI 的設計債：
- 支援右手 (right) 與左手 (left) 球員
- 出球後支援向飛行初速方向、左側、右側及上方雙向動態擴展
- 驗證拍攝視角 (DTL / FO)，非支援視角回傳 NOT_COMPARABLE
"""

from dataclasses import dataclass

SUPPORTED_VIEWS = {"DTL", "FO", "FACE_ON", "DOWN_THE_LINE"}


@dataclass(frozen=True)
class PlannedROI:
    x1: int
    y1: int
    x2: int
    y2: int
    handedness: str
    direction_hint: str  # "bidirectional" | "rightward" | "leftward" | "upward"

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.x1, self.y1, self.x2, self.y2)


def is_view_comparable(camera_angle: str) -> tuple[bool, str]:
    """檢查視角是否支援平面軌跡分析：支援 DTL 與 FO (Face-On)，其餘回報 NOT_COMPARABLE。"""
    norm = str(camera_angle or "DTL").strip().upper()
    if norm in ("DTL", "DOWN_THE_LINE", "DOWN-THE-LINE"):
        return (True, "DTL")
    if norm in ("FO", "FACE_ON", "FACE-ON"):
        return (True, "FO")
    return (False, "NOT_COMPARABLE")


def plan_club_roi(
    display_width: int,
    display_height: int,
    handedness: str = "right",
    wrist_hint_norm: tuple[float, float] | None = None,
    prev_head_norm: tuple[float, float] | None = None,
) -> PlannedROI:
    """
    規劃球桿與桿頭偵測 ROI：
    - 若有上一格桿頭位置，以該位置為中心擴展搜尋窗
    - 若有手腕位置，僅以手腕為球桿握把圓心建立半徑約 0.42 畫面寬高的寬鬆搜尋窗（絕不將手腕當桿頭！）
    """
    w = max(16, int(display_width))
    h = max(16, int(display_height))
    hand = "left" if str(handedness).lower() == "left" else "right"

    if prev_head_norm is not None:
        hx, hy = prev_head_norm
        x1 = int(max(0, (hx - 0.25) * w))
        x2 = int(min(w, (hx + 0.25) * w))
        y1 = int(max(0, (hy - 0.25) * h))
        y2 = int(min(h, (hy + 0.25) * h))
        return PlannedROI(x1=x1, y1=y1, x2=x2, y2=y2, handedness=hand, direction_hint="bidirectional")

    if wrist_hint_norm is not None:
        wx, wy = wrist_hint_norm
        x1 = int(max(0, (wx - 0.42) * w))
        x2 = int(min(w, (wx + 0.42) * w))
        y1 = int(max(0, (wy - 0.42) * h))
        y2 = int(min(h, (wy + 0.45) * h))
        return PlannedROI(x1=x1, y1=y1, x2=x2, y2=y2, handedness=hand, direction_hint="bidirectional")

    return PlannedROI(
        x1=int(w * 0.08),
        y1=int(h * 0.08),
        x2=int(w * 0.92),
        y2=int(h * 0.92),
        handedness=hand,
        direction_hint="bidirectional",
    )


def plan_ball_flight_roi(
    display_width: int = 1080,
    display_height: int = 1920,
    progress: float = 0.0,
    handedness: str = "right",
    stationary_ball_norm: tuple[float, float] | None = None,
    wrist_hint_norm: tuple[float, float] | None = None,
    velocity_hint_norm: tuple[float, float] | None = None,
    *,
    frame_width: int | None = None,
    frame_height: int | None = None,
    ball_origin_norm: tuple[float, float] | None = None,
) -> PlannedROI:
    """
    規劃高爾夫球升空飛行 ROI：
    - 改善 R3 僅向畫面右側擴展之偏差，支援左打者、右打者、左飛/右飛/正上方飛行之雙向動態視窗。
    - 當已知初始飛行速度向量 `velocity_hint_norm=(vx, vy)` 時，自動朝實際飛行方向擴展。
    """
    w = max(16, int(frame_width if frame_width is not None else display_width))
    h = max(16, int(frame_height if frame_height is not None else display_height))
    hand = "left" if str(handedness).lower() == "left" else "right"
    prog = float(min(1.0, max(0.0, progress)))
    eff_ball_origin = ball_origin_norm if ball_origin_norm is not None else stationary_ball_norm

    if eff_ball_origin is not None:
        bx, by = eff_ball_origin
    elif wrist_hint_norm is not None:
        wx, wy = wrist_hint_norm
        offset_x = -0.10 if hand == "left" else 0.10
        bx = min(0.85, max(0.15, wx + offset_x))
        by = min(0.88, max(0.50, wy + 0.20))
    else:
        bx = 0.45 if hand == "left" else 0.55
        by = 0.72

    # 基礎地面擊球區 (涵蓋左右雙側)
    base_half_w = 0.24
    x1_norm = max(0.02, bx - base_half_w)
    x2_norm = min(0.98, bx + base_half_w)
    y1_norm = max(0.02, by - 0.18)
    y2_norm = min(0.96, by + 0.14)

    # 隨時間推進，同時向雙側與天空上方擴展
    if velocity_hint_norm is not None and abs(velocity_hint_norm[0]) > 0.005:
        vx, _ = velocity_hint_norm
        if vx < 0:
            x1_norm = max(0.0, x1_norm - prog * 0.55)
            x2_norm = min(1.0, x2_norm + prog * 0.20)
            dir_hint = "leftward"
        else:
            x1_norm = max(0.0, x1_norm - prog * 0.20)
            x2_norm = min(1.0, x2_norm + prog * 0.55)
            dir_hint = "rightward"
    else:
        # 雙向對稱擴展，兼顧左打/右打與推拉球
        left_weight = 0.50 if hand == "left" else 0.38
        right_weight = 0.38 if hand == "left" else 0.50
        x1_norm = max(0.0, x1_norm - prog * left_weight)
        x2_norm = min(1.0, x2_norm + prog * right_weight)
        dir_hint = "bidirectional"

    y1_norm = max(0.0, y1_norm - prog * 0.75)

    return PlannedROI(
        x1=int(round(x1_norm * w)),
        y1=int(round(y1_norm * h)),
        x2=max(int(round(x1_norm * w)) + 8, int(round(x2_norm * w))),
        y2=max(int(round(y1_norm * h)) + 8, int(round(y2_norm * h))),
        handedness=hand,
        direction_hint=dir_hint,
    )
