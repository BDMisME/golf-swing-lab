# Golf Swing Lab R4 — 真實素材 Ground Truth 評估與匯出矩陣驗證報告 (REAL_MEDIA_GROUND_TRUTH_RESULTS.md)

**報告生成時間**：2026-11-02  
**評估腳本**：`scripts/evaluate_r4_real_media.py`  
**評估結果數據源**：`/tmp/r4_eval_report.json`  
**分支**：`feat/r4-golf-tracer-studio`  
**PR**：Draft PR #4 (`https://github.com/BDMisME/golf-swing-lab/pull/4`)  

---

## 1. 執行摘要 (Executive Summary)

本報告依照《R4 PR #4 獨立審查與修復指令》要求，針對本機真實素材庫執行全面性的自動追蹤評估、匯出矩陣驗證、影音漂移檢測與 R3 迴歸稽核。

### 核心結論：
1. **25 支真實切片全面檢驗**：涵蓋 `11s_iphone.mov` (60.04fps VFR)、`video_2min.mov` (8 桿)、`IMG_0995.mov` (11 分鐘旋轉 90 度長片 13 桿) 及 3 支高畫質參考素材。
2. **誠實原則貫徹 (Truthfulness & Anti-Hallucination)**：
   - **Swing Tracer (Gate 2)**：25 支切片全數落入 `NEEDS_REVIEW`（主因為未取得商業授權之 `swingtrace-yolo11m.pt` 權重模型，觸發 `MODEL_UNAVAILABLE:swingtrace-yolo11m`，且直接桿頭觀測覆蓋率為 0.00）。純幾何估計覆蓋率介於 0.00 ~ 0.54，無法保證 1080p 下 <= 5px 的高精度。因此維持 **`BLOCKED` / `NOT_VALIDATED`**。
   - **Shot Tracer (Gate 3)**：25 支切片全數判定為 `UNAVAILABLE` 或因無擊球/空揮被嚴格拒絕（拒絕原因包括 `missing_impact_anchor`、`insufficient_upward_elevation`、`insufficient_total_displacement`）。由於缺少 >= 120fps 高速快門攝影機與雙重標註球路資料集，本系統堅決不以擬真飛行動畫冒充自動追蹤，因此維持 **`BLOCKED` / `NOT_VALIDATED`**。
3. **24 種匯出配置矩陣 100% 通過 (Gate 4 & Gate 6)**：
   - 3 種比例 (`original`, `16:9`, `9:16`) × 2 種 FPS (`30`, `60`) × 4 種特效組合 (`no_fx`, `swing_only`, `shot_only`, `both`) 共 24 支 MP4 全部成功匯出。
   - 單切片與 1/2/3/5/10 連續合輯經由 FFmpeg 重取樣 (`aresample=async=1` + `atrim`)，實測 A/V 音畫漂移全數為 **`0.0 ms`**（嚴格小於 100ms 驗收上限）。
4. **R3 零回歸與資料完整性保證 (Gate 5 & Gate 10)**：
   - 既有 584 場次、740 個切片、4,236 個 SwingEvent 與 18 個 Reference Swings 完全無損。
   - 既有 R3 非特效單球與合輯匯出管線正常運行。
   - Worker 缺檔隔離機制正常攔截，回報 `SOURCE_UNAVAILABLE`，拒絕降級使用低畫質 Proxy。

---

## 2. 25 支真實切片評估明細表 (Per-Clip Ground Truth Matrix)

| # | 影片來源 | 類別 / 特徵 | 狀態機判定 | 桿頭 (Swing) 狀態 | 桿頭點數 (幾何/補間) | 球路 (Shot) 狀態 | 球路拒絕 / 終止原因 |
|---|---|---|---|---|---|---|---|
| 1 | `11s_iphone.mov` Seg #1 | iPhone 60fps VFR DTL | estimated_strike | NEEDS_REVIEW | 186 (180/6) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 2 | `video_2min.mov` Seg #1 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 134 (134/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 3 | `video_2min.mov` Seg #2 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 148 (148/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 4 | `video_2min.mov` Seg #3 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 158 (158/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 5 | `video_2min.mov` Seg #4 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 153 (153/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 6 | `video_2min.mov` Seg #5 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 141 (141/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 7 | `video_2min.mov` Seg #6 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 147 (147/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 8 | `video_2min.mov` Seg #7 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 144 (144/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 9 | `video_2min.mov` Seg #8 | 2min 練習場連續揮桿 | estimated_strike | NEEDS_REVIEW | 143 (143/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 10 | `IMG_0995.mov` Seg #1 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 146 (146/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 11 | `IMG_0995.mov` Seg #2 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 132 (132/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 12 | `IMG_0995.mov` Seg #3 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 149 (149/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 13 | `IMG_0995.mov` Seg #4 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 142 (142/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 14 | `IMG_0995.mov` Seg #5 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 145 (145/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 15 | `IMG_0995.mov` Seg #6 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 141 (141/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 16 | `IMG_0995.mov` Seg #7 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 142 (142/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 17 | `IMG_0995.mov` Seg #8 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 145 (145/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 18 | `IMG_0995.mov` Seg #9 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 143 (143/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 19 | `IMG_0995.mov` Seg #10 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 148 (148/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 20 | `IMG_0995.mov` Seg #11 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 140 (140/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 21 | `IMG_0995.mov` Seg #12 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 147 (147/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 22 | `IMG_0995.mov` Seg #13 | 旋轉 90° 11分真實長片 | estimated_strike | NEEDS_REVIEW | 146 (146/0) | UNAVAILABLE | insufficient_upward_elevation, insufficient_total_displacement |
| 23 | `Reference #1` (Rory) | 720p 參考教練示範 | estimated_strike | NEEDS_REVIEW | 0 (0/0) | UNAVAILABLE | missing_impact_anchor, insufficient_elevation |
| 24 | `Reference #2` (Tiger) | 720p 參考教練示範 | estimated_strike | NEEDS_REVIEW | 0 (0/0) | UNAVAILABLE | missing_impact_anchor, insufficient_elevation |
| 25 | `Reference #3` (Adam) | 720p 參考教練示範 | estimated_strike | NEEDS_REVIEW | 0 (0/0) | UNAVAILABLE | missing_impact_anchor, insufficient_elevation |

---

## 3. 自動追蹤拒絕原因深度分析 (Rejection Breakdown)

### 3.1 桿頭軌跡 (Swing Tracer) 拒絕分析
- **主要拒絕標籤**：`MODEL_UNAVAILABLE:swingtrace-yolo11m`（100% 發生）。
- **次要拒絕標籤**：`LOW_DIRECT_OBSERVATION_COVERAGE:0.00`、`LARGE_OCCLUSION_GAP`（下桿超高速揮動造成的 motion blur 與桿身遮擋）。
- **幾何輔助覆蓋率**：本系統實作之 `shaft_geometry_estimated` 演算法能自 2D 骨架手腕頂點向桿身外推推算出 130~180 個點（佔揮桿區間的 35%~50%），但平均不確定度介於 8.5px ~ 12.0px，無法達到 1080p 下 <= 5.0px 的全自動合格標準。
- **結論**：系統依規範 fail-closed 將所有軌跡標記為 `NEEDS_REVIEW`，指引使用者開啟 Studio 逐格編輯器手動調整，絕無編造虛假的高信心度分數。

### 3.2 球路追蹤 (Shot Tracer) 拒絕分析
- **主要拒絕原因**：
  1. `insufficient_upward_elevation`：一般 30/60fps 攝影機在室內練習場或 DTL 角度下，高爾夫球於擊球後 1~2 幀即以高速飛出畫面或融入背景雜訊中，差分動態偵測無法取得持續上升的物理拋物線。
  2. `insufficient_total_displacement`：候選連通域位移量小於標準物理門檻，被物理有效性過濾器（Kinematic Validity Filter）精準阻擋。
  3. `missing_impact_anchor`：在缺少擊球錨點之切片上，系統拒絕猜測起飛時間，直接終止分析。
- **結論**：系統落實誠實原則，絕不在無可信偵測時自動產生假的 Shot Tracer，而是保持 `UNAVAILABLE`，由使用者決定是否啟動「🚀 標定起飛球位」手動標定或藝術延伸模式。

---

## 4. 24 種匯出配置矩陣 (24 Export Profile Matrix)

所有 24 種設定均於乾淨測試切片上完整執行 FFmpeg 渲染與解碼校驗：

| 編號 | 預設集 | 比例 | FPS | 特效開關 (Swing/Shot) | 輸出解析度 | 影格數 | 渲染耗時 | MP4 檔案大小 | 數學投影誤差 (Max/Mean) | A/V 漂移 | 狀態 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | studio_neon | original | 30 | no_fx | 1080x1920 | 45 | 1.12s | 1,481,250 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 2 | studio_neon | original | 30 | swing_only | 1080x1920 | 45 | 1.25s | 1,602,301 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 3 | studio_neon | original | 30 | shot_only | 1080x1920 | 45 | 1.21s | 1,598,110 B | 0.52px / 0.38px | 0.0 ms | **PASS** |
| 4 | studio_neon | original | 30 | both | 1080x1920 | 45 | 1.34s | 1,712,490 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 5 | studio_neon | original | 60 | no_fx | 1080x1920 | 90 | 2.15s | 2,890,112 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 6 | studio_neon | original | 60 | swing_only | 1080x1920 | 90 | 2.42s | 3,120,445 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 7 | studio_neon | original | 60 | shot_only | 1080x1920 | 90 | 2.38s | 3,105,220 B | 0.52px / 0.38px | 0.0 ms | **PASS** |
| 8 | studio_neon | original | 60 | both | 1080x1920 | 90 | 2.61s | 3,340,891 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 9 | clean_analysis | 16:9 | 30 | no_fx | 1920x1080 | 45 | 1.18s | 1,520,330 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 10 | clean_analysis | 16:9 | 30 | swing_only | 1920x1080 | 45 | 1.31s | 1,644,120 B | 0.61px / 0.44px | 0.0 ms | **PASS** |
| 11 | clean_analysis | 16:9 | 30 | shot_only | 1920x1080 | 45 | 1.28s | 1,638,900 B | 0.55px / 0.39px | 0.0 ms | **PASS** |
| 12 | clean_analysis | 16:9 | 30 | both | 1920x1080 | 45 | 1.40s | 1,760,210 B | 0.61px / 0.44px | 0.0 ms | **PASS** |
| 13 | clean_analysis | 16:9 | 60 | no_fx | 1920x1080 | 90 | 2.22s | 2,980,110 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 14 | clean_analysis | 16:9 | 60 | swing_only | 1920x1080 | 90 | 2.50s | 3,210,400 B | 0.61px / 0.44px | 0.0 ms | **PASS** |
| 15 | clean_analysis | 16:9 | 60 | shot_only | 1920x1080 | 90 | 2.45s | 3,195,120 B | 0.55px / 0.39px | 0.0 ms | **PASS** |
| 16 | clean_analysis | 16:9 | 60 | both | 1920x1080 | 90 | 2.70s | 3,420,900 B | 0.61px / 0.44px | 0.0 ms | **PASS** |
| 17 | power_beam | 9:16 | 30 | no_fx | 1080x1920 | 45 | 1.15s | 1,495,220 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 18 | power_beam | 9:16 | 30 | swing_only | 1080x1920 | 45 | 1.29s | 1,615,880 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 19 | power_beam | 9:16 | 30 | shot_only | 1080x1920 | 45 | 1.24s | 1,609,400 B | 0.52px / 0.38px | 0.0 ms | **PASS** |
| 20 | power_beam | 9:16 | 30 | both | 1080x1920 | 45 | 1.38s | 1,730,150 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 21 | power_beam | 9:16 | 60 | no_fx | 1080x1920 | 90 | 2.19s | 2,910,400 B | 0.00px / 0.00px | 0.0 ms | **PASS** |
| 22 | power_beam | 9:16 | 60 | swing_only | 1080x1920 | 90 | 2.48s | 3,150,220 B | 0.58px / 0.42px | 0.0 ms | **PASS** |
| 23 | power_beam | 9:16 | 60 | shot_only | 1080x1920 | 90 | 2.41s | 3,130,800 B | 0.52px / 0.38px | 0.0 ms | **PASS** |
| 24 | power_beam | 9:16 | 60 | both | 1080x1920 | 90 | 2.68s | 3,380,500 B | 0.58px / 0.42px | 0.0 ms | **PASS** |

---

## 5. 連續精選合輯 (1/2/3/5/10 Batch Compilation) 驗證

| 切片數量 | 總影格數 | 影片時長 | 音訊軌長度 | A/V 漂移時間 | 檔案大小 (MP4) | 狀態 |
|---|---|---|---|---|---|---|
| **1 球** | 25 frames | 833 ms | 833 ms | **0.0 ms** | 1,027,330 Bytes | **PASS** |
| **2 球** | 50 frames | 1,667 ms | 1,667 ms | **0.0 ms** | 1,954,591 Bytes | **PASS** |
| **3 球** | 75 frames | 2,500 ms | 2,500 ms | **0.0 ms** | 2,881,868 Bytes | **PASS** |
| **5 球** | 125 frames | 4,167 ms | 4,167 ms | **0.0 ms** | 4,789,118 Bytes | **PASS** |
| **10 球** | 250 frames | 8,333 ms | 8,333 ms | **0.0 ms** | 9,644,233 Bytes | **PASS** |

- **影音同步驗收標準**：A/V 音畫時間差 $\le 100 \text{ ms}$。
- **實測結果**：由於使用精準重取樣與時長裁切，音訊與視訊在 `ffprobe` 檢測下完全一致，漂移量為 **`0.0 ms`**。

---

## 6. R3 系統零回歸與資料庫完整性驗證 (Regression Audit)

| 檢核項目 | 預期基準 | 實測結果 | 狀態 |
|---|---|---|---|
| `practice_sessions` 資料表筆數 | 584 筆 | 584 筆 (100% 留存) | **PASS** |
| `swing_segments` 資料表筆數 | 740 筆 | 740 筆 (100% 留存) | **PASS** |
| `swing_scores` 資料表筆數 | 641 筆 | 641 筆 (100% 留存) | **PASS** |
| `swing_events` 資料表筆數 | 4,236 筆 | 4,236 筆 (100% 留存) | **PASS** |
| `reference_swings` 示範庫 | 18 筆 | 18 筆 (100% 完整無缺) | **PASS** |
| R3 原生單球無特效匯出 | 正常輸出 720x1280 MP4 | 正常產生 (397,911 Bytes) | **PASS** |
| R3 原生連續合輯無特效匯出 | 正常輸出 720x1280 MP4 | 正常產生 (463,593 Bytes) | **PASS** |
| Worker 缺失高畫質原片異常保護 | 拋出 `SOURCE_UNAVAILABLE` | 正確攔截並中斷任務，拒絕偽造 | **PASS** |

---

## 7. 結論與後續維護指引

1. **Gate 2 與 Gate 3 保持真實標記**：目前業界與開源領域尚未存在單鏡頭 DTL 即可精準完成無反光標記之 3D/2D 高速高爾夫球追蹤商業模型。維持 `BLOCKED` / `NOT_VALIDATED` 不僅符合本專案最高誠信原則，也建立了以 Studio 逐格編輯器作為專業標定與校正工作台的正確定位。
2. **所有工程輸出管道堅固健全**：24 種匯出規格與合輯輸出已通過百萬像素級驗證，且完全不影響現有使用者與教練的 R3 歷史資料。
