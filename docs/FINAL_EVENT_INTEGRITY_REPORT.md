# GOLF SWING LAB — 第三輪最終事件誠信與真實 App 驗收報告
**文檔編號**：`GSL-R3-FINAL-EVENT-INTEGRITY`  
**評估日期**：2026-10-24  
**當前分支**：`fix/autonomous-event-accuracy-recovery`  
**驗收狀態**：`PASS`（開發集對齊驗收通過；外部獨立盲測真值維持 `NOT_VALIDATED`）

---

## 1. 執行總結與關鍵成果

本輪針對外部獨立工程審查提出的 P0-A ~ P0-D 與 P1 意見，進行深度逐幀視覺與音訊物理分析、根因鎖定、架構修復與真實全流程端到端驗收。

### 核心成果指標對比：
| 評估維度 | 第二輪審查基準 (舊版) | 第三輪最終誠信修復 (新版) | 進步幅度 / 狀態 |
|---|---|---|---|
| **第 10 球 Impact 預測 (30fps Proxy)** | 121067 ms (誤延遲 152ms) | **120967 ms** (真實觸球 120898ms) | **誤差縮減 100ms (1.6 影格)** |
| **第 10 球 節奏排行榜狀態** | 誤判 TEMPO 第 1 名 (虛假推薦) | **嚴格排除於 TEMPO / POSTURE 榜外** | **已根除錯誤推薦** |
| **第 10 球 審核狀態與旗標** | auto_accepted (假高分 0.88) | **needs_review / audio_kinematic_conflict** | **誠實降級 (conf=0.65, unc=82ms)** |
| **30fps Proxy Top MAE (主要驗收)** | 66.7 ms (2.0 frames) | **58.4 ms (1.8 frames)** | **進步 12.4%** |
| **30fps Proxy Impact MAE (主要驗收)** | 41.1 ms (1.2 frames) | **32.7 ms (1.0 frames)** | **精準度達 1.0 影格以內** |
| **60fps 原片 Top MAE** | 89.0 ms (5.3 frames) | **76.5 ms (4.6 frames)** | **進步 14.0%** |
| **60fps 原片 Impact MAE** | 27.8 ms (1.7 frames) | **22.2 ms (1.3 frames)** | **進步 20.1%** |
| **12 球生理下桿時長符合率** | 100.0% (12/12) | **100.0% (12/12)** | **無任何 timing_anomaly** |
| **後端自動化測試套件** | 74 / 74 PASSED | **76 / 76 PASSED (100%)** | **新增專項回歸測試通過** |
| **前端 Next.js 生產建置** | 9 / 9 靜態頁面成功 | **9 / 9 靜態頁面成功 (0 錯誤)** | **型別與架構完好** |

---

## 2. P0-A：第 10 球 Impact 誤判根因與客觀物理證據

### 2.1 逐幀像素差分與白球起飛分析 (120700ms ~ 121150ms)
我們在 60fps 原片（Frame 7240 ~ 7270）進行全域反光與像素差分檢測：
1. **Frame 7252 (120865ms)**：桿頭極速進入打擊區低位。
2. **Frame 7253 (120881ms)**：打擊區白色像素暴增至 2064（全場最高反光，桿面觸球瞬間 Clubface Contact）。
3. **Frame 7254 (120898ms)**：打擊區像素差分值達 5.06（全場最大劇變，球體脫離打擊墊噴出 Launch Onset）。
4. **Frame 7255 (120915ms)**：白色像素降至 524，小白球已離墊起飛。
5. **Frame 7256 (120931ms)**：白像素恢復基準 205，打擊墊上的球已完全消失！
6. **Frame 7264 (121065ms)**：擊球後 180ms，球手手腕已翻起隨揮（$wrist\_y=0.4971, v_y=-0.483$），地面的球早就飛走！

### 2.2 音訊瞬態分佈真相
- **120680ms**：球員上桿頂點（Top 在 120666ms 附近），這是球員衣物摩擦、頂點轉折風切聲或練習場背景音，與真實觸球（120881ms）相差 201ms，絕非觸球聲。
- **120840ms / 120860ms**：球員下桿極速切入打擊區之揮桿聲或極近距擊球初音。
- **121060ms**：擊球後 160ms，隨揮上挑聲、球桿破空風切聲或護網反彈聲。

### 2.3 舊版誤判至 121067ms 之技術根因
1. 30fps Proxy 取樣步長為 33.3ms（影格時間碼包含 120866, 120899, 120933, 120966, 121000, 121033, 121067ms）。
2. 細掃/粗掃狀態機初步估計 Impact `center_ms` 為 121000ms 或 121033ms。
3. `_refine_event_local_high_fps` 只要在 `center_ms ± 75ms` 內找到任何音訊瞬態（121060ms 在範圍內），即**無條件鎖定該音訊**（`best_idx = 121067ms`），並給出 `confidence = 0.88, uncertainty_ms = 40`。
4. 完全忽略了此時手腕已向上隨揮（$v_y = -0.904$ 劇烈向上），造成 152ms 巨大時間偏離！

### 2.4 運動學合理性閘門 (Kinematic Plausibility Gate on Audio) 修復
在採納音訊瞬態時，引入三道客觀生物力學硬性約束：
1. **深度約束**：音訊影格手腕垂直深度必須處於擊球區底部（$wrist\_y \ge \max(wrist\_y) - 0.22 \times span$）。
2. **速度約束**：垂直速度不可為劇烈向上隨揮（$v_y \ge -0.22$）。
3. **運動學吻合度**：音訊影格與純運動學評估之擊球最低點影格偏差不得 $> 55\text{ms}$。
- 若違反上述條件，系統判定為 `audio_kinematic_conflict`，**嚴禁被偽音訊拉偏**，安全回退至手腕軌跡最低點與制動減速（Kinematic Lowest Point & Deceleration）。
- 第 10 球 Impact 成功修正回 **120967ms**（30fps Proxy）與 **120932ms**（60fps 原片），緊密吻合真實觸球（120898ms）！

---

## 3. P0-B：Confidence 嚴格分離與誠實降級

我們嚴格將過去混淆的各項指標徹底解耦：
1. **Landmark Visibility**：關鍵點可見度（0.0 ~ 1.0）。
2. **Kinematic Evidence Quality**：下桿爆發加速、最低點制動與零交越能量（0.0 ~ 1.0）。
3. **Audio Evidence Quality**：是否具備單一、無矛盾之擊球音訊脈衝（0.0 ~ 1.0）。
4. **Ball Launch Evidence**：真球位移與出發點觀測（0.0 ~ 1.0）。
5. **Competing Hypothesis Margin**：第二候選與第一候選之分差。
6. **Sampling Resolution**：影片取樣步長（60fps 為 16ms，30fps 為 33ms）。
7. **Estimated Timing Uncertainty**：事件時間定位保守不確定區間。

### 降級規則落地：
- 凡音訊與運動學衝突（如第 10 球）：
  - 信心度強制限制在 **$0.50 \le \text{conf} \le 0.65$**。
  - 不確定度放大至 **$\ge 70\text{ms}$**（Proxy 實測為 82ms）。
  - 標記 `review_flags = ["audio_kinematic_conflict"]`，`review_status = "needs_review"`。

---

## 4. P0-C：真實 Ranking 資料流與驗收腳本統一

### 4.1 廢除雙軌排行榜決策
- 徹底移除 `scripts/run_production_acceptance.py` 中自行撰寫的 `sorted(...)`。
- 驗收腳本全面呼叫正式 `rank_session_swings()`。
- 保證「驗收測試所驗」與「真實 Web/API 所跑」完全使用同一套商業邏輯。

### 4.2 排行榜安全排除機制落地
在 `packages/analysis/scoring/engine.py` 的 `rank_session_swings()` 中：
- `posture`（最佳姿勢）與 `tempo`（最佳節奏）依賴精確的時序對齊，**凡帶有 `needs_review`、`audio_kinematic_conflict`、`candidate_ambiguous` 或 `timing_anomaly` 的球，嚴格排除推薦**！
- 第 10 球因音訊矛盾被降級為 `needs_review`，**成功自最佳節奏榜單中剔除**！
- 最佳節奏第一名由無爭議的第 7 球（45.8 分，上下桿時間比 1.70:1）正當奪得。
- 獨立的 `finish`（收桿得分 89.4，停頓 2200ms）排名第 3、`ig`（視覺評分 90.8，畫面完整度 99.9）排名第 1，符合各維度可觀測客觀證據。

---

## 5. P0-D：30fps Proxy 正式路徑逐球驗收對照

| Seq | GT Top->Imp (ds) | Raw Top->Imp (ds) | Proxy Top->Imp (ds) | Raw Err (Top/Imp) | Proxy Err (Top/Imp) | Proxy 狀態與旗標 |
|---|---|---|---|---|---|---|
| #1 | 10672->10938 (266ms) | 10572->10905 (333ms) | 10600->10933 (333ms) | 100 / 33 ms | 72 / 5 ms | auto_accepted |
| #2 | 25310->25610 (300ms) | 25260->25593 (333ms) | 25300->25633 (333ms) | 50 / 17 ms | 10 / 23 ms | auto_accepted |
| #3 | 38178->38478 (300ms) | 38095->38412 (317ms) | 38100->38433 (333ms) | 83 / 66 ms | 78 / 45 ms | needs_review (audio_conflict) |
| #4 | 51682->51915 (233ms) | 51582->51898 (316ms) | 51600->51933 (333ms) | 100 / 17 ms | 82 / 18 ms | needs_review (audio_conflict) |
| #5 | 66435->66702 (267ms) | 66335->66685 (350ms) | 66400->66733 (333ms) | 100 / 17 ms | 35 / 31 ms | needs_review (audio_conflict) |
| #6 | 84340->84673 (333ms) | 84323->84673 (350ms) | 84433->84733 (300ms) | 17 / 0 ms | 93 / 60 ms | needs_review (audio_conflict) |
| #7 | 105112->105412 (300ms) | 105028->105378 (350ms) | 105100->105433 (333ms) | 84 / 34 ms | 12 / 21 ms | auto_accepted (TEMPO #1) |
| #8 | 110780->111147 (367ms) | 110813->111163 (350ms) | 110867->111200 (333ms) | 33 / 16 ms | 87 / 53 ms | auto_accepted |
| #9 | 114780->115013 (233ms) | 114680->115030 (350ms) | 114733->115067 (334ms) | 100 / 17 ms | 47 / 54 ms | auto_accepted (POSTURE #1) |
| #10 | 120682->120915 (233ms) | 120632->120932 (300ms) | 120633->120967 (334ms) | 50 / 17 ms | 49 / 52 ms | needs_review (audio_conflict, IG #1) |
| #11 | 125200->125467 (267ms) | 125133->125483 (350ms) | 125133->125467 (334ms) | 67 / 16 ms | 67 / 0 ms | auto_accepted |
| #12 | 136502->136737 (235ms) | 136368->136720 (352ms) | 136433->136767 (334ms) | 134 / 17 ms | 69 / 30 ms | auto_accepted |

---

## 6. 接觸片與證據檔案清單

- **正式評估 JSON**：`docs/reports/takeover/production_acceptance_report.json`
- **關鍵球接觸片**：
  - `docs/reports/takeover/contact_sheets/swing_8_contact_sheet.jpg` (478KB)
  - `docs/reports/takeover/contact_sheets/swing_9_contact_sheet.jpg` (396KB)
  - `docs/reports/takeover/contact_sheets/swing_10_contact_sheet.jpg` (370KB)
- **回歸測試套件**：`tests/test_swing_10_regression.py` (3 / 3 PASSED)
- **全量測試結果**：`tests/` 共 76 項單元與整合測試 100% 通過。
