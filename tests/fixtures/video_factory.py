import math
import subprocess
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def _draw_golfer_frame(
    width: int,
    height: int,
    time_ms: int,
    swings_spec: list[dict[str, Any]],
    brightness_scale: float = 1.0,
    intruder_window_ms: tuple[int, int] | None = None,
) -> np.ndarray:
    """
    繪製單幀 DTL 練習場畫面與高對比關節標記球員：
    - 預設靜止準備姿勢：手腕位於 (0.52, 0.56)
    - 當 time_ms 落在某次揮桿 [start_ms, end_ms] 內時，執行完整：
      Address -> Takeaway -> Backswing -> Top -> Downswing -> Impact -> Follow-through -> Finish
    """
    bg_val = int(48 * brightness_scale)
    frame = np.full((height, width, 3), (bg_val, int(56 * brightness_scale), int(44 * brightness_scale)), dtype=np.uint8)

    # 繪製練習場地面草皮與打擊墊
    horizon_y = int(height * 0.62)
    cv2.rectangle(
        frame,
        (0, horizon_y),
        (width, height),
        (int(36 * brightness_scale), int(68 * brightness_scale), int(36 * brightness_scale)),
        -1,
    )

    # 基準關節歸一化座標 (DTL 右打後方視角)
    ankle_x, ankle_y = 0.44, 0.84
    knee_x, knee_y = 0.46, 0.72
    hip_x, hip_y = 0.43, 0.56
    shoulder_x, shoulder_y = 0.49, 0.38
    nose_x, nose_y = 0.53, 0.31
    wrist_x, wrist_y = 0.55, 0.54

    active_swing: dict[str, Any] | None = None
    for sw in swings_spec:
        if int(sw["start_ms"]) <= time_ms <= int(sw["end_ms"]):
            active_swing = sw
            break

    if active_swing is not None:
        s_ms = int(active_swing["start_ms"])
        e_ms = int(active_swing["end_ms"])
        is_practice = active_swing.get("label") == "practice_swing"
        spine_delta = float(active_swing.get("spine_delta_deg", 1.8))
        rel = (time_ms - s_ms) / float(max(1, e_ms - s_ms))

        # 定義階段比例：
        # 0.00 - 0.18: Address
        # 0.18 - 0.52: Takeaway & Backswing -> Top (rel=0.52)
        # 0.52 - 0.64: Downswing -> Impact (rel=0.64)
        # 0.64 - 0.80: Follow-through
        # 0.80 - 1.00: Finish Hold
        amp = 0.11 if is_practice else 0.24
        if rel < 0.18:
            wrist_x, wrist_y = 0.55, 0.54
        elif rel < 0.52:
            p = (rel - 0.18) / 0.34
            wrist_x = 0.55 - 0.08 * math.sin(p * math.pi / 2)
            wrist_y = 0.54 - amp * math.sin(p * math.pi / 2)
        elif rel < 0.64:
            p = (rel - 0.52) / 0.12
            top_wy = 0.54 - amp
            imp_wy = 0.46 if is_practice else 0.56
            wrist_x = 0.47 + 0.09 * p
            wrist_y = top_wy + (imp_wy - top_wy) * p
            # 模擬擊球瞬間之軀幹前傾微小變化
            shoulder_x += (spine_delta / 90.0) * 0.04 * p
        elif rel < 0.80:
            p = (rel - 0.64) / 0.16
            imp_wy = 0.46 if is_practice else 0.56
            fin_wy = 0.42 if is_practice else 0.30
            wrist_x = 0.56 - 0.10 * p
            wrist_y = imp_wy + (fin_wy - imp_wy) * p
        else:
            wrist_x = 0.46
            wrist_y = 0.42 if is_practice else 0.30

    def pt(nx: float, ny: float) -> tuple[int, int]:
        return (int(round(nx * width)), int(round(ny * height)))

    def scale_bgr(b: int, g: int, r: int) -> tuple[int, int, int]:
        return (
            int(np.clip(b * brightness_scale, 0, 255)),
            int(np.clip(g * brightness_scale, 0, 255)),
            int(np.clip(r * brightness_scale, 0, 255)),
        )

    p_ankle = pt(ankle_x, ankle_y)
    p_knee = pt(knee_x, knee_y)
    p_hip = pt(hip_x, hip_y)
    p_shoulder = pt(shoulder_x, shoulder_y)
    p_nose = pt(nose_x, nose_y)
    p_wrist = pt(wrist_x, wrist_y)

    # 繪製軀幹與四肢連線
    limb_color = scale_bgr(210, 210, 210)
    cv2.line(frame, p_ankle, p_knee, limb_color, 4)
    cv2.line(frame, p_knee, p_hip, limb_color, 5)
    cv2.line(frame, p_hip, p_shoulder, limb_color, 6)
    cv2.line(frame, p_shoulder, p_nose, limb_color, 4)
    cv2.line(frame, p_shoulder, p_wrist, limb_color, 4)

    # 繪製關節色標（供 PoseExtractor 精準追蹤）
    cv2.circle(frame, p_nose, 8, scale_bgr(0, 255, 255), -1)       # nose
    cv2.circle(frame, p_shoulder, 9, scale_bgr(255, 200, 0), -1)   # shoulder
    cv2.circle(frame, p_wrist, 9, scale_bgr(0, 80, 255), -1)       # wrist
    cv2.circle(frame, p_hip, 9, scale_bgr(255, 0, 255), -1)        # hip
    cv2.circle(frame, p_knee, 8, scale_bgr(0, 255, 0), -1)         # knee
    cv2.circle(frame, p_ankle, 8, scale_bgr(255, 120, 120), -1)    # ankle

    # 若設定多人干擾區間，於背景繪製第二人干擾色塊
    if intruder_window_ms and intruder_window_ms[0] <= time_ms <= intruder_window_ms[1]:
        cv2.rectangle(
            frame,
            (int(width * 0.75), int(height * 0.35)),
            (int(width * 0.85), int(height * 0.78)),
            scale_bgr(180, 10, 180),
            -1,
        )

    return frame


def create_synthetic_dtl_video(
    output_path: str | Path,
    duration_ms: int = 16000,
    fps: int = 30,
    width: int = 480,
    height: int = 360,
    swings_spec: list[dict[str, Any]] | None = None,
    codec: str = "libx264",
    rotation: int = 0,
    vfr: bool = False,
    brightness_scale: float = 1.0,
    intruder_window_ms: tuple[int, int] | None = None,
) -> Path:
    """產生真實編碼之 MP4 / MOV 測試影片（支援 H.264、HEVC、旋轉 metadata、VFR、低光與多人干擾）。"""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    raw_avi = out_p.parent / f"_tmp_{out_p.stem}.mp4"

    if swings_spec is None:
        swings_spec = [
            {"start_ms": 1500, "end_ms": 4700, "label": "valid_swing", "spine_delta_deg": 1.6},
            {"start_ms": 6500, "end_ms": 9700, "label": "valid_swing", "spine_delta_deg": 2.4},
            {"start_ms": 11500, "end_ms": 14700, "label": "valid_swing", "spine_delta_deg": 3.5},
        ]

    total_frames = int(round((duration_ms / 1000.0) * fps))
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(raw_avi), fourcc, float(fps), (width, height))
    try:
        for idx in range(total_frames):
            t_ms = int(round((idx / float(fps)) * 1000))
            fr = _draw_golfer_frame(
                width=width,
                height=height,
                time_ms=t_ms,
                swings_spec=swings_spec,
                brightness_scale=brightness_scale,
                intruder_window_ms=intruder_window_ms,
            )
            writer.write(fr)
    finally:
        writer.release()

    cmd = ["ffmpeg", "-y", "-i", str(raw_avi)]
    if vfr:
        cmd.extend(["-vf", "mpdecimate", "-fps_mode", "vfr"])
    if codec == "libx265":
        cmd.extend(["-c:v", "libx265", "-preset", "ultrafast", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"])
    else:
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p"])

    encoded_target = out_p.parent / f"_enc_{out_p.name}" if rotation in (90, 180, 270) else out_p
    cmd.extend(["-movflags", "+faststart", str(encoded_target)])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    raw_avi.unlink(missing_ok=True)
    if proc.returncode != 0:
        encoded_target.unlink(missing_ok=True)
        raise RuntimeError(f"合成測試影片產生失敗: {proc.stderr[-300:]}")

    if rotation in (90, 180, 270):
        rot_cmd = [
            "ffmpeg",
            "-y",
            "-display_rotation:v:0",
            str(rotation),
            "-i",
            str(encoded_target),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out_p),
        ]
        rot_proc = subprocess.run(rot_cmd, capture_output=True, text=True, timeout=60)
        encoded_target.unlink(missing_ok=True)
        if rot_proc.returncode != 0:
            raise RuntimeError(f"寫入旋轉矩陣失敗: {rot_proc.stderr[-300:]}")

    return out_p

