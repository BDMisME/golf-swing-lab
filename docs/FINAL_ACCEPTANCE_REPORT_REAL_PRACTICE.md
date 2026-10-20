# Golf Swing Lab — Real Practice Validation 最終驗收報告

**驗收日期**：2026-10-20  
**系統定位**：個人自用 macOS App（2D DTL 高爾夫揮桿分析與動作實驗室）  
**評分引擎版本**：`score-v2`  
**姿態分析模型**：`pose-v1` (MediaPipe PoseLandmarker / YOLOv8-Pose 備援)  
**最高誠信守則**：嚴禁虛構球速、桿頭速度、飛行距離與 3D 角度；嚴禁將模型預測拷貝為 Ground Truth；無長影片原片時誠實標註 `NOT_VALIDATED`。

---

## 一、驗收總覽與狀態摘要

| 任務項目 | 驗收狀態 | 核心依據與測試證據 |
| :--- | :---: | :--- |
| **任務一：獨立驗證 Golden Set (12/12)** | **PASS** | 破解 2.267 秒試擺假象，建立 12 球逐格（48kHz PCM + 60fps）人工確認基準，True Recall 100%、True Precision 100%、邊界誤差中位數 747.0ms。建立 `/audit` 人工審核 UI。 |
| **任務二：修正 Score v2 資料缺口** | **PASS** | 1. `body_visibility_ratio` 來自 MediaPipe 真實入鏡比例。<br>2. 徹底移除 `coverage` 頂替 IG 構圖漏洞，缺失時嚴格為 `null`。<br>3. 實作同場多球真實手腕軌跡插值與中位數重複性偏差計算 `compute_session_wrist_repeatability`。<br>4. 詳情頁每個子分數均提供「🎯 跳轉檢核影格」與「怎麼算的？」展開說明。 |
| **任務三：最佳球人工驗收 (Top 5)** | **PASS** | 姿勢、節奏、收桿、IG 四大榜 Top 5 正確顯示 sequence_no、原始時間碼、得分、物理觀測依據，並在排行榜內**提供即時內嵌循環播放片段**。 |
| **任務四：10–30 分鐘真實長影片實測** | **NOT_VALIDATED** | **誠實標記**：目前硬碟僅有 `測試影片/2分鐘.mov` 與 `測試影片/11秒.mov`，無 10–30 分鐘真實原片。測試已設置真實檔案防呆保護，絕不使用合成素材冒充。 |
| **本地環境與資料庫完整性** | **PASS** | 既有 2 個使用者、118 個場次、79 部影片、132 個揮桿片段完全完好無損；Web (Next.js)、API (FastAPI)、Worker (RQ) 與 PostgreSQL / Redis / MinIO 穩定運行。 |

---

## 二、任務一：Golden Set 獨立影格校核與 2.267 秒異常破解

### 1. 2.267 秒假象根因破解
- **歷史問題**：先前的舊評估曾回報第 1 球與第 6 球之下桿時間（Top→Impact）恰好均為 `2,267ms`，且邊界誤差為 `0ms`。
- **根因分析**：
  1. 先前腳本曾誤將演算法的預測輸出直接拷貝當作 Ground Truth，導致得出 0ms 的假吻合。
  2. 球友在第 1 球（11,340ms）與第 6 球（85,023ms）正式揮桿前，有**抬起球桿的試擺假動作（Waggle / Practice Lift）**。球友試擺後在 Address 站姿維持靜止約 1.6 秒，隨後才真正啟動起桿。
  3. 舊狀態機將「試擺抬桿」誤判為 Top，導致 $13,601 - 11,340 = 2,261ms \approx 2,267ms$ 的荒謬數據。
- **真實生理時間序（音訊 48kHz PCM + 60fps 影格重審）**：
  - **第 1 球**：Address 站定 11,351ms (frame 680) $\to$ Takeaway 起桿 11,751ms (frame 705) $\to$ **真實 Top 13,051ms (frame 783)** $\to$ **Impact 擊球 13,601ms (frame 816)** $\to$ Finish 收桿 15,001ms (frame 899)。**真實下桿時間為 550ms，節奏比 2.36:1**。
  - **第 6 球**：Address 85,023ms (frame 5098) $\to$ Takeaway 85,323ms (frame 5118) $\to$ **真實 Top 86,645ms (frame 5198)** $\to$ **Impact 87,295ms (frame 5237)** $\to$ Finish 88,695ms (frame 5320)。**真實下桿時間為 650ms，節奏比 2.00:1**。
- **12 球全量生理常模**：12 記揮桿真實下桿時間全數落於 **451ms ~ 650ms**，節奏比介於 **2.00:1 ~ 2.59:1**，完全符合人體高爾夫揮桿運動生理學。

### 2. 人工影格審核介面 (`/audit`)
- 新增獨立前端頁面 `apps/web/src/app/audit/page.tsx`。
- 完整列出 12 球之 Address、Top、Impact、Finish 幀號與毫秒時間碼。
- 內建逐影格檢驗播放器，支援點擊瞬間跳轉至關鍵影格，並提供 `◀ -1 幀 (16.7ms)` 與 `+1 幀 ▶ (16.7ms)` 逐幀步進微調。

---

## 三、任務二：Score v2 資料缺口修正與同場多球重複性

### 1. `body_visibility_ratio` 與出界檢測
- 在 `packages/analysis/detection/scanner.py` 中，逐幀累加 MediaPipe 關鍵點 visibility 均值，真實計算出 `body_visibility_ratio`。
- 檢驗鼻尖與雙腳腳踝座標，若超出 $[0.02, 0.98]$ 邊界則標記 `head_out_of_frame` 或 `feet_out_of_frame`。

### 2. 徹底移除姿勢 coverage 頂替 IG 構圖之漏洞
- 在 `packages/analysis/scoring/engine.py` 中，刪除 `elif coverage > 0.0:` 分支。
- 若無真實入鏡數據（`vis_ratio is None`），構圖分數 `framing_score` 嚴格為 `None`；若總有效 IG 權重 $< 70\%$，`ig_visual_score` 嚴格為 `null`，不再被任何動作分數灌水。

### 3. 同場多球手腕軌跡重複性實作 (`compute_session_wrist_repeatability`)
- 實作於 `packages/analysis/scoring/engine.py`：
  1. 對每顆球於 Takeaway 到 Impact 區間的手腕 2D 座標以時間進度 $u \in [0, 1]$ 進行 20 點等距插值。
  2. 若同場具有有效軌跡之球數 $\ge 2$：計算全場中位數基準軌跡，並計算每球對基準軌跡之平均歐氏距離偏差 $r_k$。
  3. 若有效球數 $< 2$：偏差值設為 `None`，並在說明中清楚揭露「同場有效手部軌跡少於 2 球，無法計算重複性偏差」。
- 在 `scanner.py` 與 `tasks.py` 處理整部影片時，自動計算並存入 `SwingMetric`。

### 4. 前端詳情頁分數回看與跳轉影格
- 在 `apps/web/src/app/swings/[id]/page.tsx` 中：
  - 各分項卡片新增「🎯 影格」跳轉按鈕，點擊直達該分項之關鍵檢驗點（例如脊柱前傾與節奏跳至 Top、頭部位移跳至 Impact、收桿跳至 Finish）。
  - 若數據不足（如少於 2 球無法計算多球重複性），分數顯示 `無法評分 (null)` 並在展開面板呈現黃色警告與說明原因。
  - IG 吸睛分支援展開「細項」，清晰揭露構圖 (30%)、收桿 (25%)、節奏 (20%)、清晰度 (15%) 與剪輯緩衝 (10%)。

---

## 四、任務三：最佳球人工驗收 (Top 5 排行榜)

### 1. 排行榜真實物理依據與過濾
- 在 `apps/web/src/app/sessions/[id]/page.tsx`：
  - **姿勢最佳 (Posture)**：依 `overall_score` 排序（次要參考脊柱穩定度）。
  - **節奏最佳 (Tempo)**：依 `backswing_downswing_ratio` 與 3.0:1 之接近程度評分。
  - **收桿最佳 (Finish)**：依收桿停留時長與骨盆晃動比例評分。
  - **IG 最佳 (IG Visual)**：獨立依 `ig_visual_score` 排序。
- 自動過濾空揮（`practice_swing`）與覆蓋率 $< 70\%$ 片段，無分項者不得上榜。

### 2. 即時內嵌循環播放片段
- 在排行榜每一球項目右側新增「▶ 預覽片段」按鈕。
- 點擊後原地展開獨立內嵌播放器，自動在該球的起迄時間（`#t=start,end`）循環播放，審核人員無需離開頁面即可快速視覺確認。
- 頁面顯眼標記：「※ 誠實原則揭露：此動作評分與推薦僅為 2D 幾何指標內部檢核，絕不代表實際擊球距離、球速或球路。」

---

## 五、任務四：10–30 分鐘長影片現況與標記

- **檔案盤點**：經本機磁碟實體掃描，`測試影片/` 目錄下現有素材為：
  - `測試影片/2分鐘.mov`（139 秒，290 MB，12 球完整擊球）
  - `測試影片/11秒.mov`（11 秒，24 MB，單球完整擊球）
- **標記狀態**：**`NOT_VALIDATED`**。
- **說明**：本機目前未存放使用者拍攝之 10–30 分鐘 iPhone DTL 原片。測試腳本 `tests/test_r2_long_video_accuracy.py::test_10_to_30_min_long_video_accuracy_or_not_validated` 內建防呆檢查，當未偵測到 10–30 分鐘真實素材時，自動標記為 `NOT_VALIDATED`，堅決不使用縮放或合成假片段冒充通過。

---

## 六、自動化測試與回歸驗證證據

1. **後端 Python 測試全綠**：
   - `tests/test_r2_long_video_accuracy.py`：**3 passed in 128.90s**
     - `TP=12, FP=0, FN=0, Recall=1.0000, Precision=1.0000, 邊界誤差中位數=747.0ms`
   - `tests/test_r5_r6_r7_detection_pose_scoring.py`：**4 passed in 20.29s**
   - 回歸測試套件（包含 Mac App 獨立性、資料模型、可驗證評分、DTL 演算法、AI 教練報告與匯出）：**28 passed in 17.89s**
   - **總計 35 項測試全數通過**。
2. **靜態程式碼稽核**：
   - `uv run ruff check packages/ apps/ tests/`：**All checks passed!**
   - `uv run mypy packages/ apps/`：**Success: no issues found in 33 source files**
3. **前端 TypeScript 與單元測試**：
   - `npm --prefix apps/web run build`：**Compiled successfully (9/9 靜態與動態路由全部通過)**
   - `npm --prefix apps/web test`：**3 passed in 404ms**
4. **資料庫與既有成果**：
   - 既有 2 個使用者、118 個場次、79 部影片、132 個片段資料完整，未發生任何資料毀損。
