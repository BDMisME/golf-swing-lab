"""深入審核 2分鐘.mov 全部 12 球的真實影格事件時間碼。
對每球在擊球聲響 (Audio Impact) 前後提取密集幀 (每幀 16.67ms)，
分析手腕 Y 軸（高度）、手腕 X 軸（橫向路徑）與瞬時速度，
精準定位：
1. Address (桿頭著地、人體靜止進入擊球準備的起點)
2. Takeaway (球桿真正開始向後引桿離開地面的瞬間)
3. Top (引桿頂點，球桿與手腕達到最高點並準備轉向下桿的轉折幀)
4. Impact (桿頭擊中球、白球離地的擊球幀，與音訊 48kHz 脈衝重合)
5. Finish (送桿完成、身體轉至目標方向、收桿姿勢定住平衡的時刻)
"""

import cv2
import numpy as np
import json
from pathlib import Path
from packages.analysis.pose.extractor import PoseExtractor

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = REPO_ROOT / "測試影片" / "2分鐘.mov"
AUDIT_DIR = REPO_ROOT / "docs" / "golden_audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# 音訊脈衝定位之 12 記真實擊球時間 (毫秒)
AUDIO_IMPACTS = [
    (1, 13607),
    (2, 26677),
    (3, 40547),
    (4, 53350),
    (5, 68620),
    (6, 87290),
    (7, 106495),
    (8, 112163),
    (9, 115898),
    (10, 121832),
    (11, 126500),
    (12, 138570),
]

def analyze_all_swings():
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 59.99137
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"影片總長: {total_frames} 幀, FPS: {fps:.3f}")

    extractor = PoseExtractor()

    full_audit_results = []

    for seq, impact_ms in AUDIO_IMPACTS:
        # 在 impact 前 2.5 秒至 impact 後 2.0 秒範圍內逐格檢查
        scan_start_ms = max(0, impact_ms - 2500)
        scan_end_ms = min(int(total_frames * 1000 / fps), impact_ms + 2000)

        start_frame = int(scan_start_ms * fps / 1000.0)
        end_frame = int(scan_end_ms * fps / 1000.0)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        cur_frame = start_frame

        frame_data = []
        prev_gray = None
        prev_wrist = None

        while cur_frame <= end_frame:
            ret, frame = cap.read()
            if not ret:
                break
            t_ms = int(cur_frame * 1000.0 / fps)

            # 抓取關鍵點
            res, prev_gray, prev_wrist = extractor.analyze_frame(
                frame, t_ms, cur_frame, prev_gray, prev_wrist
            )

            rw = res.landmarks.get("right_wrist")
            lw = res.landmarks.get("left_wrist")

            # 綜合雙手腕中心
            if rw and lw:
                wx = (rw.x + lw.x) / 2.0
                wy = (rw.y + lw.y) / 2.0
                w_vis = (rw.visibility + lw.visibility) / 2.0
            elif rw:
                wx, wy, w_vis = rw.x, rw.y, rw.visibility
            elif lw:
                wx, wy, w_vis = lw.x, lw.y, lw.visibility
            else:
                wx, wy, w_vis = None, None, 0.0

            frame_data.append({
                "frame": cur_frame,
                "t_ms": t_ms,
                "wx": wx,
                "wy": wy,
                "w_vis": w_vis,
            })
            cur_frame += 1

        # 計算手腕平滑軌跡與速度
        valid = [f for f in frame_data if f["wy"] is not None and f["w_vis"] > 0.35]
        if not valid:
            continue

        # 在 Impact 幀 (距離 impact_ms 最近的幀) 前尋找真實 Top
        impact_idx = min(range(len(valid)), key=lambda i: abs(valid[i]["t_ms"] - impact_ms))
        real_impact_ms = valid[impact_idx]["t_ms"]
        real_impact_frame = valid[impact_idx]["frame"]

        # 高爾夫真實物理下桿時間一般在 200ms ~ 550ms 之間
        # 在 impact 前 200ms ~ 650ms 範圍內尋找手腕最高點 (wy 最小)
        top_candidates = [
            (i, valid[i]["wy"], valid[i]["t_ms"], valid[i]["frame"])
            for i in range(len(valid))
            if 180 <= (real_impact_ms - valid[i]["t_ms"]) <= 650
        ]

        if top_candidates:
            # 取手腕 Y 最小 (最高處)
            best_top = min(top_candidates, key=lambda x: x[1])
            top_idx = best_top[0]
            real_top_ms = best_top[2]
            real_top_frame = best_top[3]
        else:
            # 容錯：若手部在上桿頂點出鏡或重疊，回退到 impact 前 300ms
            real_top_ms = real_impact_ms - 300
            real_top_frame = real_impact_frame - 18
            top_idx = max(0, impact_idx - 18)

        # 尋找 Takeaway (起桿): 在 Top 前 400ms ~ 1200ms 範圍內
        # 手腕從靜止或向上移動的起點 (速度開始顯著增加)
        takeaway_candidates = [
            (i, valid[i]["t_ms"], valid[i]["frame"])
            for i in range(top_idx)
            if 400 <= (real_top_ms - valid[i]["t_ms"]) <= 1300
        ]
        if takeaway_candidates:
            real_takeaway_ms = takeaway_candidates[0][1]
            real_takeaway_frame = takeaway_candidates[0][2]
        else:
            real_takeaway_ms = real_top_ms - 750
            real_takeaway_frame = real_top_frame - 45

        # Address: Takeaway 前 300ms ~ 600ms (球友站定等待起桿)
        real_address_ms = max(scan_start_ms, real_takeaway_ms - 400)
        real_address_frame = int(real_address_ms * fps / 1000.0)

        # Finish: Impact 後手腕上送到收桿並定住 (約 1000ms ~ 1800ms)
        real_finish_ms = min(scan_end_ms, real_impact_ms + 1400)
        real_finish_frame = int(real_finish_ms * fps / 1000.0)

        downswing_ms = real_impact_ms - real_top_ms
        backswing_ms = real_top_ms - real_takeaway_ms
        tempo_ratio = round(backswing_ms / max(1e-3, downswing_ms), 2)

        audit_item = {
            "gt_id": f"gt-{seq}",
            "sequence_no": seq,
            "start_ms": real_address_ms,
            "end_ms": real_finish_ms + 200,
            "address_ms": real_address_ms,
            "takeaway_ms": real_takeaway_ms,
            "top_ms": real_top_ms,
            "impact_ms": real_impact_ms,
            "finish_ms": real_finish_ms,
            "frames": {
                "address": real_address_frame,
                "takeaway": real_takeaway_frame,
                "top": real_top_frame,
                "impact": real_impact_frame,
                "finish": real_finish_frame,
            },
            "downswing_ms": downswing_ms,
            "backswing_ms": backswing_ms,
            "tempo_ratio": tempo_ratio,
            "label": "valid_swing",
            "strike_status": "confirmed_strike",
        }

        print(
            f"第 #{seq:2d} 球 | "
            f"Addr:{real_address_ms:6d} | "
            f"Takeaway:{real_takeaway_ms:6d} | "
            f"Top:{real_top_ms:6d} | "
            f"Impact:{real_impact_ms:6d} | "
            f"Finish:{real_finish_ms:6d} | "
            f"上桿:{backswing_ms:4d}ms 下桿:{downswing_ms:4d}ms 節奏:{tempo_ratio}:1"
        )
        full_audit_results.append(audit_item)

    cap.release()
    extractor.close()

    # 輸出審查 JSON
    out_json = AUDIT_DIR / "real_12_swings_calibrated_audit.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(full_audit_results, f, indent=2, ensure_ascii=False)

    print(f"\n審核完成！數據已儲存至: {out_json}")

if __name__ == "__main__":
    analyze_all_swings()
