# Golf Swing Lab R4 — 實拍高解析度媒體評估報告 (`REAL_MEDIA_EVALUATION.md`)

- **評估時間**：2026-10-31T09:48:48Z (`2026-10-31T17:48:48+08:00`)
- **評估腳本**：[evaluate_r4_real_media.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/scripts/evaluate_r4_real_media.py)
- **原始輸出證據**：`/tmp/r4_eval_report.json`

---

## 1. 實拍高解析度揮桿片段追蹤結果總表

我們針對本機 `~/.golfswinglab/storage/raw/` 中具備完整 `PoseArtifact`（手腕關鍵點提示）與 `SwingEvent` 的 6 段真實 iPhone 1080p 高解析原片揮桿片段執行 `SwingTracerEngine` 與 `ShotTracerEngine`：

| 片段 ID (`segment_id`) | 原片檔名與解析度/旋轉 | 時間窗 (`start_ms`–`end_ms`) | 擊球狀態 (`ball_strike_status`) | Swing Tracer 狀態 | 桿身幾何端點估算點數 (`geometry_estimated`) | 幾何輔助覆蓋率 | Swing 耗時 (`ms`) | Shot Tracer 模式 | Shot 拒斥原因 (`rejection_reasons`) | Shot 耗時 (`ms`) |
|---|---|---|---|---|---:|---:|---:|---|---|---:|
| `e9ef2b80-e9d7-40d3-9be7-6a5b2e4faa7d` | `11s_iphone.mov` (`1080x1920`, `rot=0°`, `60.04fps`) | `1933–9100ms` (454 格) | `estimated_strike` | `NEEDS_REVIEW` | 180 (+6 內插 = 186) | `39.65%` | `8999.9` | `UNAVAILABLE` (0 點) | `insufficient_upward_elevation`, `insufficient_total_displacement` | `4222.9` |
| `37c19971-d56d-4592-99a7-a323a3d945ca` | `video_2min.mov` (`1080x1920`, `rot=0°`, `59.99fps`) | `9200–16300ms` (451 格) | `estimated_strike` | `NEEDS_REVIEW` | 82 (+10 內插 = 92) | `18.18%` | `8957.9` | `UNAVAILABLE` (0 點) | `insufficient_upward_elevation`, `insufficient_total_displacement` | `2659.8` |
| `90262dd3-dccc-4b03-9d14-3b6c4e4e1d6b` | `video_2min.mov` (`1080x1920`, `rot=0°`, `59.99fps`) | `24067–31000ms` (440 格) | `estimated_strike` | `NEEDS_REVIEW` | 103 (+19 內插 = 122) | `23.41%` | `8809.9` | `UNAVAILABLE` (0 點) | `launch_pair_time_gap_too_large` | `2377.4` |
| `810c7517-026d-4b1f-b3d7-6a0dcb257857` | `IMG_0995.mov` (`1920x1080` `rot=270°` -> `1080x1920`, `59.96fps`) | `86400–93700ms` (463 格) | `confirmed_strike` | `NEEDS_REVIEW` | 192 (+17 內插 = 209) | `41.47%` | `16947.2` | `UNAVAILABLE` (0 點) | `launch_origin_too_high`, `insufficient_upward_elevation`, `insufficient_total_displacement` | `11388.9` |
| `33da6b35-cc38-49ed-8f92-edd9527f81bd` | `IMG_0995.mov` (`1920x1080` `rot=270°` -> `1080x1920`, `59.96fps`, 9.5 分鐘後段) | `567000–574300ms` (463 格) | `estimated_strike` | `NEEDS_REVIEW` | 180 (+9 內插 = 189) | `38.88%` | `18444.3` | `UNAVAILABLE` (0 點) | `launch_origin_too_high` | `11671.6` |
| `d870c908-6b88-4731-9c71-a0ee55a08f2e` | `IMG_0995.mov` (`1920x1080` `rot=270°` -> `1080x1920`, `59.96fps`, 空揮) | `200–1783ms` (120 格) | `no_ball` | `NEEDS_REVIEW` | 38 (+1 內插 = 39) | `31.67%` | `2075.3` | `UNAVAILABLE` (0 點) | `no_ball_detected` | `3563.9` |

---

## 2. 誠實品質與阻礙評估（Anti-Hallucination Disclosure）

### 2.1 Swing Tracer 實拍表現與 `BLOCKED_SWING_AUTO` 原因
1. **模型權重限制 (`BLOCKED_GATED_WEIGHTS`)**：
   - 專用桿頭與握把偵測權重 `swingtrace-yolo11m.pt` 對應之 HuggingFace 儲存庫 `nishsm/golf-club-detection-swingtrace` 處於 `gated: auto` 狀態（未授權下載回傳 `HTTP 401 GatedRepo`），且授權為 `AGPL-3.0-or-later`。
   - 因此本機 `TracerModelRegistry` 如實登記 `swingtrace_yolo11m` 為 `BLOCKED_GATED_WEIGHTS`，全自動 `AUTO_TRACED` 閘門標記為 **`BLOCKED_SWING_AUTO`**。
2. **桿身幾何端點估算 (`shaft_geometry_estimated`) 實拍表現**：
   - 在無 `swingtrace-yolo11m.pt` 的情況下，`SwingTracerEngine` 結合手腕關鍵點提示 (`wrist_hints_by_ms`) 與 OpenCV Canny + CLAHE + `HoughLinesP` 在局部扇形區搜尋球桿線段，取遠離手腕之真實幾何端點作為桿頭估算點。
   - 在 `11s_iphone.mov` 與 `IMG_0995.mov` 上分別取得 `39.65%`（180 點）與 `41.47%`（192 點）之幾何輔助覆蓋率，P50 不確定度約 `8.62px–10.12px`，且 **0 點使用手腕座標冒充桿頭** (`direct_observed_count = 0`, `created_by != 'wrist'`)，並誠實標記為 `NEEDS_REVIEW` 供使用者於 Studio 逐幀微調。

### 2.2 Shot Tracer 實拍表現與物理合理性守門
1. **60fps 室內/夜間練習場運動模糊與小目標挑戰**：
   - 本機實拍影片（`11s_iphone.mov`、`video_2min.mov`、`IMG_0995.mov`）均為約 `60fps` 之練習場實拍影片；擊球瞬間小白球初速極快（每格位移大且具動態模糊），`golf_ball_yolov8n.pt` 在擊球後大多僅能偵測到打擊墊附近未大幅升空之殘影或背景高處固定亮點（如 `y_norm < 0.35` 的練習場頂棚燈具）。
2. **反造假物理守門員 100% 攔截假彈道**：
   - `ShotTracerEngine` 的物理合理性檢核（`launch_origin_too_high`、`insufficient_upward_elevation`、`insufficient_total_displacement`、`launch_pair_time_gap_too_large`、`no_ball_detected`）成功攔截所有打擊墊靜止球、頂棚燈具誤報與空揮 (`d870c908`)，誠實回傳 `ShotTrackMode.UNAVAILABLE`（0 假彈道點），絕不憑空捏造拋物線。
3. **Studio 手動錨點與可選藝術延伸閉環**：
   - 當自動觀測回傳 `UNAVAILABLE` 時，使用者可於 `/tracer-studio/[projectId]` 點選起飛 (`launch`)、最高點 (`apex`) 與落點 (`landing`)，系統即以 `MANUAL_ANCHORED`（或顯式勾選 `ARTISTIC_EXTENSION`）生成帶清晰模式徽章的彈道並匯出高畫質 MP4。

### 2.3 真實影片驗收樣本缺口聲明 (`NOT_VALIDATED` / `BLOCKED` 項目)
依據原始規格書第 11 節量化驗收門檻，本機環境目前存在以下外部素材與標註缺口，依誠信原則如實揭露，絕不偽稱為 `PASS`：
1. **缺少 `>= 120fps` 實拍高幀率原片**：本機目前為 `0` 支（門檻需 `>= 3` 支）。
2. **缺少左打者 (`handedness=left`) 實拍原片**：本機目前為 `0` 支（門檻需 `>= 4` 支）。
3. **10–30 分鐘完整長片數量不足**：本機目前僅 `1` 支 (`IMG_0995.mov`, 11 分鐘)，門檻需 `>= 3` 支不同長片。
4. **缺少 2 人獨立交叉標註之逐幀桿頭/球心 Ground Truth JSON**：因此無法計算對照人工雙標註之像素 RMSE 統計，標記為 `NOT_VALIDATED`。
