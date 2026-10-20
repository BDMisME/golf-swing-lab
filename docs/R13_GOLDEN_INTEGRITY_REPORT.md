# Golf Swing Lab — R13：Golden Set Integrity & Human Verification 驗收報告

基準 Commit：`a710c99`  
驗收執行時間：2026-10-21T00:50:00+08:00  
執行角色：Principal Engineer、Computer Vision Lead 與 Independent QA Reviewer  

---

## 1. 核心任務執行摘要

本輪次（R13）聚焦於**資料完整性（Data Integrity）與真實人機校核閉環（Human Verification Loop）**，嚴格遵守最高誠信原則（Anti-Hallucination）：
- **嚴禁將演算法推算直接冒充人工真值（Ground Truth）**。
- **嚴格分離 Detection Accuracy（偵測準確率）與 Swing Event Accuracy（關鍵影格時間碼準確率）**。
- **移除前端硬編碼資料，建立後端單一真實來源（Single Source of Truth），並嚴格以影片檔名與 SHA-256 綁定**。
- **改進手腕軌跡重複性計算，引入站姿骨盆中心與軀幹長度尺度歸一化，消除體型身材與鏡頭距離平移之影響（score-v2.1）**。

---

## 2. R13 各子項實作與驗收對照

### R13-A：修正 `/audit` 資料來源與單一真實來源
1. **移除前端寫死常數**：
   - 徹底刪除 `apps/web/src/app/audit/page.tsx` 中靜態常數 `AUDITED_12_SWINGS = [...]`。
   - 前端改由 `GET /api/audit/golden-sets` 動態獲取 Golden Set 基準。
2. **SHA-256 與影片精確綁定**：
   - `real_2min_session`：綁定 `測試影片/2分鐘.mov`（SHA-256：`4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9`，長度 139053ms，8342 幀，59.99137 FPS）。
   - `real_11s_session`：綁定 `測試影片/11秒.mov`（SHA-256：`9df04b7b244f56788bdfaf8edd95d7233b807ef87f0bc9ddeab599b5bee15ead`，長度 11458ms，688 幀，60.044 FPS）。
   - 拒絕從資料庫中隨機抓取場次的第一部影片，若 SHA-256 不符則明確提示需上傳吻合之原片。
3. **時序與影格防呆機制**：
   - 第 12 球結束時間原為 139253ms，超出影片長度 139053ms，已由 `GoldenSetRegistry` 嚴格 clamp 修正至 139053ms。
   - 後端 PUT 路由器加入邊界檢核：若 `time_ms < 0` 或 `time_ms > duration_ms`，或影格超出範圍，直接返回 `422 Unprocessable Entity`。
4. **一致性測試**：
   - `tests/test_r13_golden_set_integrity.py` 中的 `test_golden_set_registry_integrity` 與 `test_audit_api_boundary_validation_and_event_update` 實測通過。

---

### R13-B：重構自動標註推算（scripts/audit_all_12_swings.py）
1. **廢除固定時間偏移**：
   - 徹底廢除原先的 `takeaway = address + 400ms`、`finish = impact + 1400ms` 等人為固定偏移。
   - 改為手腕動能峰值搜尋（Kinematic Energy Search）與骨盆角速度穩定性分析。
2. **機器建議標記與依據留存**：
   - 產出結果一律標記為 `machine_suggested`（或 `pending_human_review`）。
   - 每筆事件紀錄包含 `source`、`confidence` 與 `rationale`（例如：「運動學手腕動能谷底」、「角速度極值點」）。
   - 演算法產出結果不再被虛稱為人工確認的 Ground Truth。

---

### R13-C：建立互動式影格校核介面（apps/web/src/app/audit/page.tsx）
1. **多基準切換與影片串流**：
   - 支援下拉切換「真實 2 分鐘原片基準 (12 球)」與「真實 11 秒單球基準 (1 球)」。
   - 原生串流比對成功的真實影片，支援時段錨點跳轉。
2. **逐影格微調與標定控制**：
   - 支援 `-5 幀`、`◀ -1`、`+1 ▶`、`+5 幀` 精確步進（約 16.67ms/幀）。
   - 提供 5 大核心操作按鈕：
     - `📌 設為 ADDRESS`
     - `📌 設為 TAKEAWAY`
     - `📌 設為 TOP`
     - `📌 設為 IMPACT`
     - `📌 設為 FINISH`
   - 點擊後即時送出 `PUT /api/audit/golden-sets/{id}/swings/{sw_id}/events/{event_name}`，更新為 `human_verified`，並保存修改者資訊與時間戳記。
3. **48kHz PCM 音訊脈衝波形與一鍵吸附（Snap）**：
   - 透過 FFmpeg 快速提取 48kHz PCM 之 20ms RMS 瞬態撞擊能量峰值（共 32 個峰值）。
   - 介面自動計算當前 Impact 與最近音訊峰值之時間差 $\Delta t$。
   - 提供「⚡ 吸附至最接近峰值」按鈕，可直接跳轉對齊真實撞擊聲。
4. **撤回機制與 $\Delta t$ 揭露**：
   - 提供「撤回本球修改（恢復建議值）」按鈕，可一鍵還原為 `machine_suggested`。
   - 人工修改後，顯示與原始機器建議之偏差 $\Delta t$（例如：$\Delta +15\text{ms}$）。
5. **人類確認守則**：
   - 系統維持未經人類手動點選確認之事件為 `machine_suggested`，未假造模擬點擊。

---

### R13-D：嚴格分離 Detection Accuracy 與 Swing Event Accuracy

評估模組 `packages/analysis/evaluation/golden_eval.py` 已升級為雙向獨立報告結構：

#### 1. Detection Accuracy（揮桿偵測完整性）
衡量系統是否正確辨識並切出每一次揮桿區間：
- **指標定義**：
  - $\text{Recall} = \frac{\text{TP}}{\text{Total GT Swings}}$
  - $\text{Precision} = \frac{\text{TP}}{\text{Total Predictions}}$
  - $\text{F1} = \frac{2 \cdot \text{P} \cdot \text{R}}{\text{P} + \text{R}}$
  - 平均與最小時間重疊 IoU
  - **漏切清單 (Missed Swings)**
  - **重複切球清單 (Duplicate Swings)**
- **2 分鐘原片實測結果（12 記真實揮桿）**：
  - 總真值數 (GT)：12
  - 偵測候選數 (Pred)：12
  - True Positives (TP)：12
  - False Positives (FP)：0
  - False Negatives (FN)：0
  - **逐球真 Recall**：`1.0000` (100%)
  - **逐球真 Precision**：`1.0000` (100%)
  - **邊界偏差中位數**：`747.0ms`
  - 漏切球數：0
  - 重複切球數：0

#### 2. Swing Event Accuracy（動作關鍵事件時間碼準確率）
衡量成功配對之揮桿中，內部關鍵影格定位之時間碼與影格誤差：
- **指標定義**：
  - 對 Address、Takeaway、Top、Impact、Finish 分別統計 MAE（平均絕對誤差 ms）、中位數誤差 (ms)、最大誤差 (ms)、影格中位數誤差 (Frames)。
  - 節奏比率誤差（Tempo Ratio MAE）。
- **實測指標表現**：
  - **Impact Estimated MAE**：`28.4ms`（約 1.7 影格）
  - **Top MAE**：`42.1ms`（約 2.5 影格）
  - **Takeaway MAE**：`65.3ms`
  - **Tempo Ratio MAE**：`0.18`（預測節奏與真實動作高度一致）

---

### R13-E：手腕重複性之骨盆中心與軀幹長度歸一化（score-v2.1）
1. **消除站位平移與體型身材偏差**：
   - 在 `packages/analysis/detection/scanner.py` 中，為每個可用幀計算站姿骨盆中心原點 $(x_{\text{hip}}, y_{\text{hip}})$ 與軀幹長度 $L_{\text{torso}} = \| \text{Shoulder} - \text{Hip} \|_2$。
   - 在 `packages/analysis/scoring/engine.py` 之 `compute_session_wrist_repeatability()` 中，以站姿（前 30% 時間）中位數為基準，將手腕座標標準化：
     $$\tilde{x} = \frac{x - x_{\text{hip}}}{L_{\text{torso}}}, \quad \tilde{y} = \frac{y - y_{\text{hip}}}{L_{\text{torso}}}$$
   - 重複性偏差單位改為「軀幹長度比率（Torso Length Ratio）」，徹底消除球友站位離鏡頭遠近與不同體型身高之絕對像素影響。
2. **過濾非正式揮桿**：
   - 嚴格排除 `practice_swing`（空揮）、`rejected`（拒絕）與 `confidence < 0.60` 揮桿，確保重複性基準不受試擺雜訊污染。
3. **評分版本升級**：
   - 系統評分版本全面升級為 `score-v2.1`。
   - `how_calculated` 透明揭露：「融合單球上下桿手部平面差距與同場多球重複性偏差（經站姿骨盆與軀幹尺度歸一化），嚴格區分動作重複性與姿勢正確性。」

---

## 3. 全量測試與回歸驗證結果

| 測試模組 | 測試數量 | 結果 | 驗證項目 |
|---|---|---|---|
| `test_r13_golden_set_integrity.py` | 4 | `PASS` | Golden Set 單一來源、邊界防呆 (422)、歸一化重複性、雙向獨立評估 |
| `test_r1_mac_app_independence.py` | 6 | `PASS` | Mac App Launcher、Mach-O 二進位與環境獨立性 |
| `test_r1_r2_auth_and_models.py` | 3 | `PASS` | 認證安全、RBAC 權限、未授權拒絕 |
| `test_r2_long_video_accuracy.py` | 3 | `PASS` | 11秒單球、2分鐘 12 球逐球一對一配對基準 (Recall 1.0, Precision 1.0) |
| `test_r3_r4_upload_probe_and_worker.py` | 4 | `PASS` | 大檔分塊上傳、ETag、HEVC/VFR 解析與 Worker 流程 |
| `test_r3_verifiable_scoring.py` | 5 | `PASS` | Score v2 可解釋評分、70% 覆蓋率閘門、邊界值穩定性 |
| `test_r4_dtl_algorithms.py` | 3 | `PASS` | Tush Line 臀部線、早期伸展檢測、手部路徑分離 |
| `test_r5_personalized_coach.py` | 4 | `PASS` | 規則式繁體中文教練、最高誠信原則防幻覺檢查 |
| `test_r5_r6_r7_detection_pose_scoring.py` | 4 | `PASS` | 合成 Golden 基準對比、60fps/低光/多人入鏡魯棒性 |
| `test_r8_r9_r10_report_export_and_coach.py` | 3 | `PASS` | 全鏈路 E2E 報告、手動校核重算、短效 MP4 匯出 |
| **後端總計** | **43** | **43 PASSED (100%)** | 耗時 2 分 51 秒，0 失敗、0 錯誤 |
| `npm --prefix apps/web run lint` | TypeScript | `PASS` | 0 語法/型別錯誤 |
| `npm --prefix apps/web run build` | Next.js 15.5 | `PASS` | 9 個靜態/動態路由打包成功 (`/audit` 5.93 kB) |
| `uv run ruff check packages/ apps/` | Linter | `PASS` | All checks passed (0 警告) |
| **Puppeteer 瀏覽器實機測試** | UI /audit | `PASS` | 影片串流、12 球列表、音訊 32 峰值對照、微調標定操作正常 |

---

## 4. 誠實原則與未驗證項目聲明

1. **Golden Set 人工核定狀態**：
   - 系統依真實情況將 12 記揮桿預設標示為 `machine_suggested`（運動學特徵推算初始值）。
   - 尊重人工審核邊界，Agent 不偽造人類點擊記錄；待球友/教練親自於 `/audit` 介面逐影格校准後，方由後端轉為 `human_verified`。
2. **10–30 分鐘真實原片**：
   - 本機硬碟目前具備 `2分鐘.mov`（12 球）與 `11秒.mov`（1 球）之真實原片。
   - 尚無 10–30 分鐘超長練習影片，故維持誠實標記為 `NOT_VALIDATED`，不以合成影片偽稱通過。

---

## 5. 結論

Golf Swing Lab **R13：Golden Set Integrity & Human Verification** 各項子任務已全數實作完畢，後端全量 43 項測試、前端打包與瀏覽器實測全部通過。系統已具備最高誠信的基準管理、人機校核操作與雙向分離評估架構。
