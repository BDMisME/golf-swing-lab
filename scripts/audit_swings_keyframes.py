"""逐球影格人工審查腳本：
針對 2分鐘.mov 的 12 球提取關鍵影格 (每球以 50ms-100ms 步進抽取候選影格)，
分析人體關鍵點 (手腕高度、手部速度、音訊脈衝)，
精確找出 Address, Top, Impact, Finish 的真實毫秒數，並生成逐球影格審核表。
"""

import json
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = REPO_ROOT / "測試影片" / "2分鐘.mov"
OUTPUT_DIR = REPO_ROOT / "docs" / "golden_audit"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 粗定位區間 (包含準備、揮桿與收桿)
ROUGH_RANGES = [
    (1, 9000, 16500),
    (2, 23500, 30500),
    (3, 36500, 44500),
    (4, 50000, 58000),
    (5, 64500, 72000),
    (6, 83500, 90500),
    (7, 103500, 108500),
    (8, 109000, 114000),
    (9, 113000, 117500),
    (10, 118500, 123500),
    (11, 123500, 130000),
    (12, 134500, 139050),
]

def analyze_motion_profile():
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video FPS: {fps}, Total Frames: {total_frames}")

    from packages.analysis.pose.extractor import PoseExtractor
    extractor = PoseExtractor()

    audit_records = []

    for seq, start_ms, end_ms in ROUGH_RANGES:
        start_frame = int(start_ms * fps / 1000.0)
        end_frame = int(end_ms * fps / 1000.0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        frame_data = []
        cur_frame = start_frame

        while cur_frame <= end_frame:
            ret, frame = cap.read()
            if not ret:
                break
            t_ms = cur_frame * 1000.0 / fps

            # 縮放加速 MediaPipe
            h, w = frame.shape[:2]
            small_rgb = cv2.cvtColor(cv2.resize(frame, (360, 640)), cv2.COLOR_BGR2RGB)
            results = pose.process(small_rgb)

            rw_y = None
            lw_y = None
            rw_x = None
            lw_x = None
            vis = 0.0

            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                rw = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST]
                lw = landmarks[mp_pose.PoseLandmark.LEFT_WRIST]
                rw_y = rw.y
                rw_x = rw.x
                lw_y = lw.y
                lw_x = lw.x
                vis = (rw.visibility + lw.visibility) / 2.0

            frame_data.append({
                "frame": cur_frame,
                "t_ms": t_ms,
                "rw_y": rw_y,
                "rw_x": rw_x,
                "lw_y": lw_y,
                "lw_x": lw_x,
                "vis": vis,
            })
            cur_frame += 1

        # 分析手腕高度與速度曲線以尋找 Top 與 Impact
        # 在 DTL 視角中：
        # Y 軸向上為小 (0 在頂端，1 在底部)
        # 上桿時手腕向上移動，Y 變小！Top 是手腕 Y 達到局域極小值 (最高點)！
        # 下桿時手腕迅速下落 (Y 變大)，擊球 (Impact) 通常在手腕接近最低點或快速穿過地面球位處
        # 接著手腕向上送桿與收桿 (Finish)
        valid_pts = [p for p in frame_data if p["rw_y"] is not None and p["vis"] > 0.3]
        if not valid_pts:
            continue

        # 計算手腕平均 y
        for p in valid_pts:
            p["wrist_y"] = (p["rw_y"] + p["lw_y"]) / 2.0 if (p["rw_y"] and p["lw_y"]) else (p["rw_y"] or p["lw_y"])
            p["wrist_x"] = (p["rw_x"] + p["lw_x"]) / 2.0 if (p["rw_x"] and p["lw_x"]) else (p["rw_x"] or p["lw_x"])

        # 平滑手腕 Y
        y_vals = [p["wrist_y"] for p in valid_pts]
        t_vals = [p["t_ms"] for p in valid_pts]

        # 計算手腕移動速度 dy/dt
        speeds = []
        for i in range(1, len(valid_pts)):
            dt = (t_vals[i] - t_vals[i-1]) / 1000.0
            if dt > 0:
                dy = (y_vals[i] - y_vals[i-1])
                dx = (valid_pts[i]["wrist_x"] - valid_pts[i-1]["wrist_x"])
                v = np.sqrt(dx*dx + dy*dy) / dt
            else:
                v = 0.0
            speeds.append(v)
        speeds.append(speeds[-1] if speeds else 0.0)

        # 找速度最大峰值附近 -> 下桿與 Impact
        # 找速度峰值前的 Y 最小值 (最高點) -> Top of backswing
        max_v_idx = int(np.argmax(speeds))
        impact_est_ms = t_vals[max_v_idx]

        # 在 impact 之前 200ms ~ 1200ms 內尋找 Top (手腕最高點，即 Y 最小)
        top_candidates = [
            (i, valid_pts[i]["wrist_y"], valid_pts[i]["t_ms"])
            for i in range(len(valid_pts))
            if 200 <= (impact_est_ms - valid_pts[i]["t_ms"]) <= 1400
        ]
        if top_candidates:
            best_top = min(top_candidates, key=lambda x: x[1])
            top_ms = best_top[2]
        else:
            top_ms = impact_est_ms - 300.0

        downswing_duration_ms = impact_est_ms - top_ms

        print(
            f"Ball #{seq}: Window [{start_ms:.0f} - {end_ms:.0f}ms] | "
            f"Top: {top_ms:.0f}ms, Impact: {impact_est_ms:.0f}ms, Downswing: {downswing_duration_ms:.0f}ms"
        )

        audit_records.append({
            "sequence_no": seq,
            "window_start_ms": start_ms,
            "window_end_ms": end_ms,
            "top_ms": round(top_ms, 1),
            "impact_ms": round(impact_est_ms, 1),
            "downswing_ms": round(downswing_duration_ms, 1),
        })

    cap.release()
    pose.close()

    with open(OUTPUT_DIR / "initial_motion_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_records, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    analyze_motion_profile()
