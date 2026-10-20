"""精準影格檢視腳本：
針對第 1 球與第 6 球，以 60fps 逐幀提取影格，
提取手腕關鍵點座標，輸出時間碼、手腕 Y 座標與運動狀態，
並保存影格圖像至 docs/golden_audit/ball1 與 docs/golden_audit/ball6，
徹底釐清 2.267 秒時間差的真實現象！
"""

import cv2
import numpy as np
from pathlib import Path
from packages.analysis.pose.extractor import PoseExtractor

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = REPO_ROOT / "測試影片" / "2分鐘.mov"
OUT_DIR = REPO_ROOT / "docs" / "golden_audit"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def inspect_ball(seq_no: int, start_ms: int, end_ms: int, step_ms: int = 100):
    ball_dir = OUT_DIR / f"ball_{seq_no}"
    ball_dir.mkdir(exist_ok=True)

    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0

    extractor = PoseExtractor()
    prev_gray = None
    prev_wrist = None

    start_frame = int(start_ms * fps / 1000.0)
    end_frame = int(end_ms * fps / 1000.0)
    step_frames = max(1, int(step_ms * fps / 1000.0))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    cur_frame = start_frame

    frame_records = []

    print(f"\n=================== 審查第 #{seq_no} 球 ({start_ms}ms ~ {end_ms}ms) ===================")
    print("時間(ms) | 幀號 | 手腕 Y (越小越高) | 手腕 X | 速度(px/s) | 備註")
    print("-" * 75)

    last_rw = None
    last_t = None

    while cur_frame <= end_frame:
        cap.set(cv2.CAP_PROP_POS_FRAMES, cur_frame)
        ret, frame = cap.read()
        if not ret:
            break
        t_ms = int(cur_frame * 1000.0 / fps)

        res, prev_gray, prev_wrist = extractor.analyze_frame(
            frame, t_ms, cur_frame, prev_gray, prev_wrist
        )

        rw = res.landmarks.get("right_wrist")
        lw = res.landmarks.get("left_wrist")
        rw_y = rw.y if rw else None
        rw_x = rw.x if rw else None

        speed = 0.0
        if rw and last_rw and last_t:
            dt = (t_ms - last_t) / 1000.0
            if dt > 0:
                dx = rw.x - last_rw[0]
                dy = rw.y - last_rw[1]
                speed = np.sqrt(dx*dx + dy*dy) / dt

        if rw:
            last_rw = (rw.x, rw.y)
            last_t = t_ms

        # 在畫面上標註時間戳與關鍵點
        annotated = frame.copy()
        cv2.putText(
            annotated,
            f"Ball #{seq_no} | {t_ms} ms (F:{cur_frame})",
            (40, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (0, 255, 255),
            3,
        )
        if rw:
            h, w = frame.shape[:2]
            cv2.circle(annotated, (int(rw.x * w), int(rw.y * h)), 12, (0, 0, 255), -1)
            cv2.putText(
                annotated,
                f"WristY: {rw.y:.3f} | Spd: {speed:.2f}",
                (40, 140),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 255, 0),
                2,
            )

        # 縮小儲存便於快速查看
        small_out = cv2.resize(annotated, (360, 640))
        cv2.imwrite(str(ball_dir / f"frame_{t_ms:06d}ms.jpg"), small_out)

        y_str = f"{rw.y:.4f}" if rw else "None"
        x_str = f"{rw.x:.4f}" if rw else "None"
        note = ""
        if speed > 2.0:
            note = "<-- 高速下桿/擊球中"
        elif rw and rw.y < 0.35:
            note = "<-- 手部在上桿高處"

        print(f"{t_ms:7d} | {cur_frame:5d} | {y_str:18s} | {x_str:8s} | {speed:10.2f} | {note}")

        frame_records.append({
            "t_ms": t_ms,
            "frame": cur_frame,
            "rw_y": rw.y if rw else None,
            "speed": speed,
        })
        cur_frame += step_frames

    cap.release()
    extractor.close()

if __name__ == "__main__":
    # 第 1 球: 10500ms ~ 14500ms (檢查 11340 vs 13607)
    inspect_ball(1, 10500, 14500, step_ms=100)
    # 第 6 球: 84000ms ~ 88500ms (檢查 85023 vs 87290)
    inspect_ball(6, 84000, 88500, step_ms=100)
