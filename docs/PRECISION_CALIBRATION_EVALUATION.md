# PRECISION_CALIBRATION_EVALUATION.md — 真實原片精準度校準驗收基準報表

> 產生時間: 2026-10-21 | 依據 P0/P1/P2 要求，嚴格保留改版前後對比、各事件來源、真球出球回饋與人工真值配對指標。

## 1. 總體效能與成功率指標摘要

| 測試影片 | 影片長度 | 偵測球數 | 總處理耗時 | 處理速度 (倍實時) | 音訊狀態 | 真球觀測出球 | 人工真值配對 Recall (門檻 ≥90%) | 人工真值配對 Precision (門檻 ≥85%) |
|---|---|---|---|---|---|---|---|---|
| `11秒.mov` | 11.5s | 1 記 | 16.06s | 0.71x | ok (未逾時) | 有 | 100.0% (1/1) | 100.0% (1/1) |
| `2分鐘.mov` | 139.1s | 12 記 | 128.45s | 1.08x | ok (139s未逾時) | 6 / 12 記 | 100.0% (12/12) | 100.0% (12/12) |

---

## 2. 2 分鐘原片 12 記真實擊球改版前後時間碼與多訊號來源清單

### 2.1 改版前後時間碼對照（粗步 ~15 FPS  vs 60 FPS 局部精修與真球出球回饋）

| 球號 | 改版前 Top (ms) | 改版後 Top (ms) | Top 微調量 | 改版前 Impact (ms) | 改版後 Impact (ms) | Impact 微調量 | 擊球狀態 | 時間不確定度 |
|---|---|---|---|---|---|---|---|---|
| #1 | 12340 | 12290 | -50 ms | 14140 | 14140 | 0 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #2 | 25943 | 25910 | -33 ms | 28210 | 28093 | -117 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |
| #3 | 38078 | 38095 | +17 ms | 38412 | 38562 | +150 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |
| #4 | 51548 | 51515 | -33 ms | 51882 | 52048 | +166 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |
| #5 | 66285 | 66252 | -33 ms | 66685 | 66502 | -183 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |
| #6 | 85823 | 85707 | -116 ms | 87892 | 87908 | +16 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #7 | 105028 | 105028 | 0 ms | 105362 | 105378 | +16 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #8 | 110697 | 110713 | +16 ms | 112230 | 112280 | +50 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #9 | 115698 | 115563 | -135 ms | 116365 | 116365 | 0 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #10 | 120365 | 120415 | +50 ms | 120898 | 121048 | +150 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |
| #11 | 126033 | 125867 | -166 ms | 128100 | 128250 | +150 ms (真球鎖定) | `confirmed_strike` | Top: ±16ms / Imp: ±16ms |
| #12 | 137103 | 137120 | +17 ms | 138703 | 138570 | -133 ms (高FPS精修) | `estimated_strike` | Top: ±16ms / Imp: ±16ms |

### 2.2 各多訊號來源參與情況審計

| 球號 | 姿態時序參與 | 音訊瞬態參與 | 真球出球觀測參與 | 證據來源 (detection_sources) | 二次精修 / 球體回饋判定依據 |
|---|---|---|---|---|---|
| #1 | 是 (轉折/零交) | 是 (共振判定) | 是 (初速觀測) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ0ms) |
| #2 | 是 (轉折/極小值) | 否 (距擊球>60ms未收斂) | 否 (未達2幀真球門檻) | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, wrist_y_local_minimum, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ-117ms) |
| #3 | 是 (轉折/零交) | 否 (噪音剔除) | 否 (打擊墊遮擋) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ+150ms) |
| #4 | 是 (轉折/極小值) | 是 (共振判定) | 否 (未達2幀真球門檻) | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ+166ms) |
| #5 | 是 (轉折/零交) | 是 (共振判定) | 否 (未達2幀真球門檻) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ-183ms) |
| #6 | 是 (轉折/極小值) | 是 (共振判定) | 是 (初速觀測) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ+16ms) |
| #7 | 是 (轉折/零交) | 是 (共振判定) | 是 (初速觀測) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ+16ms) |
| #8 | 是 (轉折/極小值) | 是 (共振判定) | 是 (初速觀測) | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ+50ms) |
| #9 | 是 (轉折/零交) | 是 (共振判定) | 是 (初速觀測) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ0ms) |
| #10 | 是 (轉折/極小值) | 是 (共振判定) | 否 (未達2幀真球門檻) | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, audio_transient_consensus, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ+150ms) |
| #11 | 是 (轉折/零交) | 否 (聲音過小) | 是 (初速觀測) | Top: [top_pause_min_speed, wrist_velocity_zero_crossing, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, ball_flight_observed_launch] | 真球出球回饋閉環鎖定 (Δ+150ms) |
| #12 | 是 (轉折/極小值) | 否 (距擊球>60ms未收斂) | 否 (未達2幀真球門檻) | Top: [wrist_velocity_zero_crossing, top_pause_min_speed, wrist_y_local_minimum, local_high_fps_refinement]<br>Imp: [wrist_kinematic_deceleration, local_high_fps_refinement] | 局部 60 FPS 精修 (Δ-133ms) |

---

## 3. 測試斷言門檻與精準度統計

### 3.1 測試門檻修正（消除註解與 assert 不一致）
- `tests/test_r2_long_video_accuracy.py` 已正式同步鎖定高標準門檻：
  - 正式目標 **Recall ≥ 0.90**（實測值：**1.0000**，12/12 記命中）
  - 正式目標 **Precision ≥ 0.85**（實測值：**1.0000**，0 假球冒充）
  - 邊界誤差中位數：**894.5 ms**

### 3.2 關鍵功能落地檢核
1. **音訊長片解碼**：139 秒無 timeout，解碼狀態 `ok`，共檢出 8/12 記揮桿共振。
2. **真球觀測回饋**：#1, #6, #7, #8, #9, #11 精確捕獲真球由打擊墊升空瞬間，回饋修正 Impact 至 ±16ms，狀態升級 `confirmed_strike`，並記入 `ball_flight_observed_launch`。
3. **局部高 FPS 精修**：12/12 揮桿全數主動觸發（`uncertainty_ms > 20` 門檻），時間不確定度由 ±66ms 收斂至 ±16ms。

---

## 4. 人工 Golden Set 未確認事件之誠信揭露

依據專案最高誠信原則（Truthfulness & Anti-Hallucination）：
1. **起迄時間碼**：經過獨立人工校準與一對一配對比對（TP=12/12）。
2. **微觀關鍵影格 (Address, Top, Impact, Finish)**：
   - 雖已由多訊號卡爾曼追蹤、音訊瞬態與局部 60 FPS 精修收斂至 ±16ms，但在高爾夫職業教練雙盲逐幀簽署確認前，系統內部標記為 `PROVISIONAL` / `NOT_VALIDATED`。
   - **絕不將暫時性機器建議值冒充為經過專業認證的 Ground Truth MAE 達標**。