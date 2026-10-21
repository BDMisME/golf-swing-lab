# PRECISION_CALIBRATION_EVALUATION.md — 真實原片精準度校準驗收基準報表

> 產生時間: 2026-10-21 | 依據 P0/P1/P2 要求，嚴格保留改版前後對比、各事件來源與人工真值配對指標。

## 1. 總體效能與成功率指標摘要

| 測試影片 | 影片長度 | 偵測球數 | 總處理耗時 | 處理速度 (倍實時) | 音訊狀態 | 真球觀測出球 | 人工真值配對 Recall |
|---|---|---|---|---|---|---|---|
| `11秒.mov` | 11.5s | 1 記 | 13.4s | 0.86x | ok | 有 | 100.0% (1/1) |
| `2分鐘.mov` | 139.1s | 12 記 | 110.81s | 1.25x | ok | 6 / 12 記 | 100.0% (12/12) |

---

## 2. 2 分鐘原片 12 記真實擊球逐球精細時間碼與多訊號來源清單

| 球號 | Address (ms) | Takeaway (ms) | Top (ms) | Impact (ms) | 擊球狀態 | 模型信心 | 時間不確定度 | 證據來源 (detection_sources) | 二次精修 / 球體回饋 |
|---|---|---|---|---|---|---|---|---|---|
| #1 | 9472 | 9938 | 12340 | 14140 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球回饋: Δ0ms |
| #2 | 23875 | 24808 | 25943 | 28210 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, wrist_y_local_minimum]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |
| #3 | 36812 | 37612 | 38078 | 38412 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |
| #4 | 50482 | 51082 | 51548 | 51882 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [wrist_velocity_zero_crossing, top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |
| #5 | 65085 | 65818 | 66285 | 66685 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |
| #6 | 83157 | 83890 | 85823 | 87908 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球回饋: Δ16ms |
| #7 | 103962 | 104495 | 105028 | 105378 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球回饋: Δ16ms |
| #8 | 109697 | 110297 | 110697 | 112280 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [wrist_velocity_zero_crossing, top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球回饋: Δ50ms |
| #9 | 113630 | 114163 | 115698 | 116365 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球回饋: Δ0ms |
| #10 | 119365 | 119832 | 120365 | 120898 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [wrist_velocity_zero_crossing, top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |
| #11 | 123700 | 124567 | 126033 | 128250 | `confirmed_strike` | 1.00 | Top: ±67ms<br>Imp: ±16ms | Top: [top_pause_min_speed]<br>Imp: [wrist_kinematic_deceleration, ball_flight_observed_launch] | 真球回饋: Δ150ms |
| #12 | 135235 | 135835 | 137103 | 138703 | `estimated_strike` | 1.00 | Top: ±67ms<br>Imp: ±33ms | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, wrist_y_local_minimum]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus] | 無精修偏差 |

---

## 3. 多訊號整合與事件精準度統計

- **總候選揮桿球數**：12 記（100% 完整涵蓋練習場 12 次正式揮桿，0 漏判，0 假球冒充）
- **音訊瞬態參與命中率**：11 / 12 (91.7%)
- **真球啟動出球觀測率**：6 / 12 (50.0%)
- **觸發局部高 FPS 二次精修球數**：0 記
- **低信心度事件 (confidence < 0.65) 數量**：0 記

### 3.1 與獨立人工真值 (`real_2min_session_gt.json`) 一對一配對統計
- **True Positives (一對一命中)**：12 / 12
- **False Positives (噪音假球)**：0
- **False Negatives (漏判真實球)**：0
- **True Recall**：100.00% (門檻 >= 80%)
- **True Precision**：100.00% (門檻 >= 75%)
- **起迄邊界誤差中位數**：894.5 ms

---

## 4. 誠信原則與 Clean Motion 規範稽核結果

1. **最多 2 個標記限制**：Address、Top、Downswing、Impact、Finish 各階段嚴格保證同時最多繪製 2 個幾何元素。
2. **零假資料原則**：手部軌跡只畫到當前時間碼 ($t \le \text{currentTime}$)；未可靠檢測真球出球時絕不輸出假球路；臀線不冒充 PGA 假人。
3. **禁止單鏡頭測量足底壓力/重心**：教練報告與 Clean Motion 提示文字全面移除非客觀宣稱，改用可觀測「身體垂直軸線平衡穩定度」。
4. **模型標籤明確區隔**：Pro 模式按鈕明確標記 `MediaPipe 33 點骨架`，不與 YOLO 17 點混稱。