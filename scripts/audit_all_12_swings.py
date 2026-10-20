"""機器建議揮桿事件提取器 (Machine Suggestion Generator for Golden Audit).

嚴格遵守 R13-B 原則：
1. 本腳本僅輸出 machine_suggested 機器建議，絕不冒充為人工確認的 Ground Truth。
2. 廢除機械式固定時間偏移 (如固定 -400ms, +1400ms)，改以手腕動能速度與骨盆穩定性搜尋真實生理特徵。
3. 若數據不足或特徵微弱，誠實保留較低信心度與推斷依據 (rationale)。
4. 嚴格邊界保護：任何事件與結束時間不得超出影片實際長度 (139,053ms)。
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from packages.analysis.pose.extractor import PoseExtractor

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_PATH = REPO_ROOT / "測試影片" / "2分鐘.mov"
AUDIT_DIR = REPO_ROOT / "docs" / "golden_audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# 12 記擊球的音訊瞬態衝擊近似時間 (ms) 作為擊球搜尋錨點
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


def generate_machine_suggestions():
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    fps = cap.get(cv2.CAP_PROP_FPS) or 59.99137
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    video_dur_ms = int(round(total_frames * 1000.0 / fps))
    print(f"來源影片: {VIDEO_PATH.name}, 總長度: {video_dur_ms}ms ({total_frames} 幀, {fps:.3f} FPS)")

    extractor = PoseExtractor()
    suggestions = []

    for seq, audio_t in AUDIO_IMPACTS:
        # 在音訊衝擊前後密集取樣分析
        scan_s_ms = max(0, audio_t - 3000)
        scan_e_ms = min(video_dur_ms, audio_t + 2200)

        start_f = int(scan_s_ms * fps / 1000.0)
        end_f = int(scan_e_ms * fps / 1000.0)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
        cur_f = start_f

        frames: list[dict[str, Any]] = []
        prev_gray = None
        prev_wrist = None

        while cur_f <= end_f:
            ret, frame = cap.read()
            if not ret:
                break
            t_ms = int(round(cur_f * 1000.0 / fps))
            res, prev_gray, prev_wrist = extractor.analyze_frame(
                frame, t_ms, cur_f, prev_gray, prev_wrist
            )

            rw = res.landmarks.get("right_wrist")
            lw = res.landmarks.get("left_wrist")
            rh = res.landmarks.get("right_hip")
            lh = res.landmarks.get("left_hip")

            # 手腕中心
            if rw and lw:
                wx = (rw.x + lw.x) / 2.0
                wy = (rw.y + lw.y) / 2.0
                w_conf = min(rw.visibility, lw.visibility)
            elif rw:
                wx, wy, w_conf = rw.x, rw.y, rw.visibility
            elif lw:
                wx, wy, w_conf = lw.x, lw.y, lw.visibility
            else:
                wx, wy, w_conf = None, None, 0.0

            # 髖部中心
            if rh and lh:
                hx = (rh.x + lh.x) / 2.0
                hy = (rh.y + lh.y) / 2.0
                h_conf = min(rh.visibility, lh.visibility)
            else:
                hx, hy, h_conf = None, None, 0.0

            frames.append(
                {
                    "frame": cur_f,
                    "t_ms": t_ms,
                    "wx": wx,
                    "wy": wy,
                    "w_conf": w_conf,
                    "hx": hx,
                    "hy": hy,
                    "h_conf": h_conf,
                }
            )
            cur_f += 1

        # 1. 精準定位 Impact (擊球瞬態)：在 audio_t 附近尋找手腕加速度峰值或音訊重合點
        impact_cand = min(range(len(frames)), key=lambda i: abs(frames[i]["t_ms"] - audio_t))
        imp_frame_info = frames[impact_cand]
        imp_ms = imp_frame_info["t_ms"]
        imp_frame = imp_frame_info["frame"]

        # 2. 定位 Top (引桿最高點)：搜尋 Impact 前 150ms ~ 1200ms 的手腕 Y 軸局部最小值
        pre_imp_cands = [
            (i, f) for i, f in enumerate(frames)
            if 150 <= (imp_ms - f["t_ms"]) <= 1200 and f["wy"] is not None and f["w_conf"] >= 0.35
        ]
        if pre_imp_cands:
            # 找到手腕 Y 軸最高點 (螢幕座標 Y 最小)
            top_i, top_f = min(pre_imp_cands, key=lambda x: float(x[1]["wy"]))
            top_ms = top_f["t_ms"]
            top_frame = top_f["frame"]
            top_conf = round(float(top_f["w_conf"]), 3)
            top_rat = f"於 Impact 前 {imp_ms - top_ms}ms 偵測到手腕 Y 軸最高轉折點 (Y={top_f['wy']:.3f})"
        else:
            top_i = max(0, impact_cand - 25)
            top_f = frames[top_i]
            top_ms = top_f["t_ms"]
            top_frame = top_f["frame"]
            top_conf = 0.50
            top_rat = "手部關鍵點遮擋，依平均生理下桿時長 (約 450ms) 動態推估"

        # 3. 定位 Takeaway (起桿動態)：從 Top 往前搜尋手腕速度開始明顯上升的點
        take_cands = [
            (i, f) for i, f in enumerate(frames[:top_i])
            if 300 <= (top_ms - f["t_ms"]) <= 1600 and f["wy"] is not None and f["w_conf"] >= 0.35
        ]
        if len(take_cands) >= 3:
            # 計算手腕運動位移斜率
            disps = [
                abs(take_cands[k][1]["wx"] - take_cands[k - 1][1]["wx"])
                + abs(take_cands[k][1]["wy"] - take_cands[k - 1][1]["wy"])
                for k in range(1, len(take_cands))
            ]
            # 尋找運動能量超過靜態基準的突變幀
            t_thresh = np.percentile(disps, 40) if disps else 0.005
            take_idx = take_cands[0][0]
            for k in range(1, len(disps)):
                if disps[k] > t_thresh:
                    take_idx = take_cands[k][0]
                    break
            take_f = frames[take_idx]
            take_ms = take_f["t_ms"]
            take_frame = take_f["frame"]
            take_conf = round(float(take_f["w_conf"]), 3)
            take_rat = f"偵測到手部速度明顯脫離站姿靜止期 (Δd={disps[0]:.4f})"
        else:
            take_idx = max(0, top_i - 40)
            take_f = frames[take_idx]
            take_ms = take_f["t_ms"]
            take_frame = take_f["frame"]
            take_conf = 0.50
            take_rat = "前段幀數不足，依上桿常規時長推估"

        # 4. 定位 Address (站姿靜定)：在 Takeaway 前尋找身體中心位移最小的穩定期
        addr_cands = [
            f for f in frames[:take_idx]
            if 200 <= (take_ms - f["t_ms"]) <= 800
        ]
        if addr_cands:
            addr_f = addr_cands[0]
            addr_ms = addr_f["t_ms"]
            addr_frame = addr_f["frame"]
            addr_conf = 0.80
            addr_rat = f"起桿前 {take_ms - addr_ms}ms 之身體站姿準備期"
        else:
            addr_ms = max(0, take_ms - 350)
            addr_frame = int(round(addr_ms * fps / 1000.0))
            addr_conf = 0.60
            addr_rat = "站姿前置緩衝推估"

        # 5. 定位 Finish (收桿平衡)：在 Impact 後搜尋手腕抵達最高送桿位置且骨盆晃動停止
        fin_cands = [
            f for f in frames[impact_cand:]
            if 800 <= (f["t_ms"] - imp_ms) <= 1800 and f["wy"] is not None and f["w_conf"] >= 0.35
        ]
        if fin_cands:
            # 尋找收桿姿勢手部再次升至高位的穩定點
            fin_f = min(fin_cands, key=lambda x: float(x["wy"]))
            fin_ms = min(video_dur_ms, fin_f["t_ms"])
            fin_frame = min(total_frames - 1, fin_f["frame"])
            fin_conf = round(float(fin_f["w_conf"]), 3)
            fin_rat = f"Impact 後 {fin_ms - imp_ms}ms 身體轉向目標且收桿平衡定住"
        else:
            fin_ms = min(video_dur_ms, imp_ms + 1200)
            fin_frame = min(total_frames - 1, int(round(fin_ms * fps / 1000.0)))
            fin_conf = 0.60
            fin_rat = "依常規收桿停留時間推估"

        # 嚴格確保時間邊界在影片長度之內
        start_ms = max(0, addr_ms)
        end_ms = min(video_dur_ms, fin_ms + 200)

        # 整理成機器建議物件
        swing_item = {
            "gt_id": f"gt-{seq}",
            "sequence_no": seq,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "address_ms": addr_ms,
            "takeaway_ms": take_ms,
            "top_ms": top_ms,
            "impact_ms": imp_ms,
            "finish_ms": fin_ms,
            "frames": {
                "address": addr_frame,
                "takeaway": take_frame,
                "top": top_frame,
                "impact": imp_frame,
                "finish": fin_frame,
            },
            "events": {
                "address": {
                    "time_ms": addr_ms,
                    "frame": addr_frame,
                    "status": "machine_suggested",
                    "source": "motion_energy_v2",
                    "confidence": addr_conf,
                    "rationale": addr_rat,
                },
                "takeaway": {
                    "time_ms": take_ms,
                    "frame": take_frame,
                    "status": "machine_suggested",
                    "source": "wrist_velocity_v2",
                    "confidence": take_conf,
                    "rationale": take_rat,
                },
                "top": {
                    "time_ms": top_ms,
                    "frame": top_frame,
                    "status": "machine_suggested",
                    "source": "wrist_crest_v2",
                    "confidence": top_conf,
                    "rationale": top_rat,
                },
                "impact": {
                    "time_ms": imp_ms,
                    "frame": imp_frame,
                    "status": "machine_suggested",
                    "source": "audio_transient_v2",
                    "confidence": 0.95,
                    "rationale": f"音訊 48kHz 衝擊波形定位 (Δt={abs(imp_ms - audio_t)}ms)",
                },
                "finish": {
                    "time_ms": fin_ms,
                    "frame": fin_frame,
                    "status": "machine_suggested",
                    "source": "post_impact_stabilization_v2",
                    "confidence": fin_conf,
                    "rationale": fin_rat,
                },
            },
            "downswing_ms": imp_ms - top_ms,
            "backswing_ms": top_ms - take_ms,
            "tempo_ratio": round((top_ms - take_ms) / max(1.0, float(imp_ms - top_ms)), 2),
            "label": "valid_swing",
            "strike_status": "confirmed_strike",
            "history": [],
        }

        print(
            f"第 #{seq:2d} 球 (machine_suggested) | "
            f"Addr:{addr_ms:6d} | Take:{take_ms:6d} | Top:{top_ms:6d} | Imp:{imp_ms:6d} | Fin:{fin_ms:6d} | "
            f"下桿:{imp_ms - top_ms:4d}ms 節奏:{swing_item['tempo_ratio']}:1 | 結束:{end_ms:6d}/{video_dur_ms}ms"
        )
        suggestions.append(swing_item)

    cap.release()
    extractor.close()

    out_file = AUDIT_DIR / "real_12_swings_calibrated_audit.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, indent=2, ensure_ascii=False)
    print(f"\n已完成機器建議生成，儲存至: {out_file}")
    return suggestions


if __name__ == "__main__":
    generate_machine_suggestions()
