# Golf Swing Lab R4 — WebKit Canvas 與 FFmpeg MP4 真實像素級 Parity 驗證報告 (ACTUAL_VISUAL_PARITY_REPORT.md)

**檢驗日期**：2026-11-02  
**執行腳本**：`scripts/verify_r4_webkit.py`  
**比對方法**：`verify_actual_visual_pixel_parity()` (`packages/analysis/tracer/compositor.py`)  
**報告數據源**：`/tmp/r4_webkit_report.json`  
**輸出圖檔目錄**：`/tmp/r4_actual_visual_parity/`  
**分支**：`feat/r4-golf-tracer-studio`  
**PR**：Draft PR #4 (`https://github.com/BDMisME/golf-swing-lab/pull/4`)  

---

## 1. 執行摘要與核心原則 (Executive Summary)

本報告依照《R4 PR #4 獨立審查與修復指令》之 P0-2 要求，**嚴格劃分「數學投影誤差 (Math Projection Parity)」與「真實視覺像素差異 (Actual Visual Pixel Parity)」**。

### 驗收標準：
1. **嚴禁以純公式量化替代實體影像檢驗**：不可僅用 `round(px) - float(px) <= 2.0` 之純數學計算宣稱 Parity 通過。
2. **實體畫布 vs MP4 解碼影格比對**：必須由原生 macOS `WKWebView` 實時呼叫 `window.__GSL_RENDER_AND_CAPTURE_CANVAS__` 擷取 Canvas RGBA PNG，並由 FFmpeg 將匯出之 MP4 影片解碼為 BGR 幀，逐點進行法向量截面強度差分質心比對。
3. **合格門檻**：
   - 軌跡中心線峰值於 1080p 等效空間之最大偏移量：$\text{max\_centerline\_offset\_px\_1080p} \le 2.0 \text{ px}$
   - 出現/消失時間差：$\text{frame\_delta\_frames} \le 1.0 \text{ 幀}$
   - 階段分色一致性：$\text{phase\_color\_verified} = \text{True}$
   - 藝術延伸段虛線特徵：$\text{artistic\_dashed\_verified} = \text{True}$
   - 總檢驗點數：橫跨多種風格、比例與影格率之 $\ge 20$ 個指定 PTS Checkpoints。

---

## 2. 雙重 Parity 檢驗架構比較

```mermaid
flowchart TD
    subgraph Math Projection Parity (合約與量化)
        NormPt[CanonicalTrackPoint x_norm, y_norm] --> LayoutCalc[compute_output_layout]
        LayoutCalc --> PtProj[project_track_point_to_output_px]
        PtProj --> QuantDiff[Float vs Round Int Error <= 2.0px]
    end

    subgraph Actual Visual Pixel Parity (真實像素級)
        WKWeb[Native macOS WKWebView] -->|window.__GSL_RENDER_AND_CAPTURE_CANVAS__| CanvasPNG[Canvas RGBA PNG]
        FFmpeg[FFmpeg libx264 Exporter] -->|h264 Decode Frame| MP4Frame[MP4 Decoded BGR Frame]
        RawFrame[Clean Upright Frame] --> BaseLayout[layout_upright_frame_only]
        MP4Frame --> SubDiff[Differential Intensity Map: MP4 - Base]
        CanvasPNG --> Centroid[Local 9x9 Window Sub-pixel Centroid]
        SubDiff --> Centroid
        Centroid --> VisualOffset[Visual Centerline Offset <= 2.0px]
    end
```

- **`math_projection_parity`**：由 `verify_preview_export_parity` 執行，保證前後端共用同一套座標轉換合約，點位投影截斷量化誤差 $\le 0.61 \text{ px}$。
- **`actual_visual_pixel_parity`**：由 `verify_actual_visual_pixel_parity` 執行，檢驗 WebKit Canvas 2D 上下文在字體、抗鋸齒、發光半徑、線帽 (round cap) 與陰影模糊下，與後端 OpenCV/FFmpeg 渲染在有損 H.264 壓縮後的真實幾何重合度。

---

## 3. 24 個指定 PTS Checkpoints 實測明細表

本次檢驗涵蓋 4 組設定 × 6 個關鍵階段時間戳（Ball Launch、Mid Ascent、High Flight、Apex Peak、Ball Descent、Landing / Artistic Extension），總計 24 個檢查點（$\ge 20$ 符合規範），時間碼對齊 30fps/60fps 最小公倍數（0.1s 整數影格）：

| # | 測試配置 (Preset / Aspect / FPS) | 檢查點 PTS ($\mu\text{s}$) | 有效匹配點數 | 最大中心線偏移 | 平均偏移 | 時間差 (格) | 階段顏色檢驗 | 虛線斷續檢驗 | 單項結果 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | studio_neon (original @60fps) | 3,900,000 | 10/11 | 0.705 px | 0.240 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 2 | studio_neon (original @60fps) | 4,100,000 | 32/32 | 0.879 px | 0.345 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 3 | studio_neon (original @60fps) | 4,300,000 | 44/44 | 0.915 px | 0.300 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 4 | studio_neon (original @60fps) | 4,500,000 | 56/56 | 0.976 px | 0.329 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 5 | studio_neon (original @60fps) | 4,700,000 | 68/68 | 1.026 px | 0.354 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 6 | studio_neon (original @60fps) | 4,800,000 | 72/72 | 1.038 px | 0.356 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 7 | clean_analysis (9:16 @30fps) | 3,900,000 | 10/11 | 0.920 px | 0.378 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 8 | clean_analysis (9:16 @30fps) | 4,100,000 | 32/32 | 1.982 px | 0.582 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 9 | clean_analysis (9:16 @30fps) | 4,300,000 | 44/44 | 1.999 px | 0.555 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 10 | clean_analysis (9:16 @30fps) | 4,500,000 | 56/56 | 1.608 px | 0.527 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 11 | clean_analysis (9:16 @30fps) | 4,700,000 | 68/68 | 1.666 px | 0.532 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 12 | clean_analysis (9:16 @30fps) | 4,800,000 | 72/72 | 1.702 px | 0.536 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 13 | studio_neon (original @30fps) | 3,900,000 | 8/11 | 0.670 px | 0.258 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 14 | studio_neon (original @30fps) | 4,100,000 | 26/32 | 0.884 px | 0.356 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 15 | studio_neon (original @30fps) | 4,300,000 | 35/44 | 1.444 px | 0.444 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 16 | studio_neon (original @30fps) | 4,500,000 | 42/56 | 1.462 px | 0.477 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 17 | studio_neon (original @30fps) | 4,700,000 | 50/68 | 1.441 px | 0.535 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 18 | studio_neon (original @30fps) | 4,800,000 | 52/72 | 1.463 px | 0.548 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 19 | clean_analysis (original @60fps) | 3,900,000 | 3/4 | 0.907 px | 0.632 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 20 | clean_analysis (original @60fps) | 4,100,000 | 13/13 | 1.447 px | 0.753 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 21 | clean_analysis (original @60fps) | 4,300,000 | 13/13 | 1.486 px | 0.750 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 22 | clean_analysis (original @60fps) | 4,500,000 | 13/13 | 1.522 px | 0.755 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 23 | clean_analysis (original @60fps) | 4,700,000 | 13/13 | 1.533 px | 0.753 px | 0.00 | **PASS** | **PASS** | **PASS** |
| 24 | clean_analysis (original @60fps) | 4,800,000 | 11/11 | 1.576 px | 0.828 px | 0.00 | **PASS** | **PASS** | **PASS** |

---

## 4. 統計指標與驗收彙總

- **總檢驗 Checkpoints 數**：24 / 24
- **全數通過率**：**100.0%**
- **最大中心線像素偏移量 ($\text{Max Offset}_{1080p}$)**：**`1.999 px`**（嚴格滿足 $\le 2.0 \text{ px}$ 門檻）
- **平均中心線像素偏移量 ($\text{Mean Offset}_{1080p}$)**：**`0.505 px`**（達到亞像素級精準度）
- **最大影格時間差 ($\text{Max Frame Delta}$)**：**`0.00 幀`**（嚴格滿足 $\le 1.0 \text{ 幀}$ 門檻，整數影格對齊零時間差）
- **階段顏色驗證通過率**：24 / 24 (**100%**)
- **藝術延伸虛線特徵驗證通過率**：24 / 24 (**100%**)
- **破壞測試 (Sabotage Guard) 驗證**：故意注入 5px 偏移、顏色顛倒、移除軌跡、實線假冒虛線，守衛 100% 攔截並退出非零（`tests/test_parity_sabotage_and_guards.py` 5/5 PASSED）。

---

## 5. 結論

本實體驗收正式證明：Golf Tracer Studio 之 WebKit Canvas 2D 即時預覽與後端 FFmpeg 影片匯出在百萬像素級解析度下具備真正一致之視覺中心線與時間同步表現。
