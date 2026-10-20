# Golf Swing Lab — 黃金標註集逐球評估報告 (Golden Set Evaluation)

## 1. 執行原則與評估架構 (Evaluation Methodology)
本報告遵循最高誠信原則（Truthfulness & Anti-Hallucination）：
- **廢除偽指標**：嚴禁以 `detected_count / total_gt` 的簡單數量比值作為 Recall。
- **嚴格逐球一對一配對**：全面採用 `packages/analysis/evaluation/golden_eval.py`，透過時序交集聯集比（IoU >= 0.20）與時間中心差距，執行匈牙利/貪婪一對一配對。
- **真實邊界誤差量測**：精確量測準備姿勢（Address）、疑似擊球（Impact）與收桿（Finish）之絕對時間碼誤差中位數（Combined Boundary Median Error）。

---

## 2. 既有真實基準影片評估成果 (Current Benchmark Dataset)

### 2.1 案例一：真實單球全揮桿（測試影片/11秒.mov）
- **影片資訊**：時長 11,458 ms、60.0 fps、DTL 視角、右打者。
- **人工標註 (Ground Truth)**：
  - `gt-1`: start=1,800ms, end=6,600ms, impact=4,650ms (valid_swing)
- **演算法偵測結果**：
  - `pred-1`: start=1,766ms, end=6,566ms, impact=4,633ms, confidence=0.82
- **逐球一對一配對指標**：
  - **TP: 1 / FP: 0 / FN: 0**
  - **逐球真 Recall: 1.00 (100%)**
  - **逐球真 Precision: 1.00 (100%)**
  - **IoU: 0.942**
  - **Start 誤差: 34ms / End 誤差: 34ms / Impact 誤差: 17ms**
  - **驗收判定：PASS**

### 2.2 案例二：真實練習場連續揮桿長影片（測試影片/2分鐘.mov）
- **影片資訊**：時長 139,053 ms、60.0 fps、DTL 視角、右打者、共 12 記實體擊球。
- **人工標註 (Ground Truth)**：共 12 記揮桿 (`gt-1` ~ `gt-12`)，記錄各球精確起手、擊球與收桿時間。
- **舊版偽 Recall vs 新版真實配對比較**：
  - **舊版算法宣稱**：偵測出 12 個 candidates 即宣稱「12/12 完美召回 (Recall 100%)」。
  - **新版真實一對一配對**：
    - 總偵測候選數：12
    - 真陽性配對 (TP)：6
    - 假陽性 (FP)：6
    - 漏判 (FN)：6
    - **逐球真 Recall：50.0%**
    - **逐球真 Precision：50.0%**
    - **邊界誤差中位數：1,345.0 ms**
- **根因深度分析**：
  - 球友在練習場每次揮桿前有長達 1.5–3 秒的準備站位與試揮（Waggle），舊版粗取樣視窗緩衝（650ms）過窄，導致狀態機在粗掃描視窗內找不到完整的 Address 站定位，進而將起手時間誤判往後推遲 2–3 秒。
  - 目前透過擴大 Coarse Window 緩衝（win_s: -1500ms, win_e: +1200ms）與狀態機 Address/Takeaway 容錯精修，持續提升配對率。

---

## 3. R10 正式產品驗收差距與狀態聲明 (Acceptance Gap & Status)

依據 R10 驗收規範：
> 「至少 5 段真實 DTL 影片、合計至少 100 球之正式驗收。缺少必要真實影片時，標示 NOT_VALIDATED，不得以 SKIPPED 當成正式 PASS。」

- **現行資料集現況**：
  - 目前本機僅包含 2 段真實練習場影片（11秒與 2分鐘），合計 13 記真實擊球。
  - 尚缺 3 段以上不同光線、不同球友、不同球場之 10–30 分鐘長影片（累計需達 100 球）。
- **誠信狀態標記**：
  - 針對「5 段真實 DTL 影片合計 100 球基準評估」：**狀態正式標記為 `NOT_VALIDATED`**（受限於缺少外部真實原片，保留評估腳本與現有 13 球完整標註，嚴禁偽稱 PASS）。
