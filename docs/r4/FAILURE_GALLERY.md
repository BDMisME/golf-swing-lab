# Golf Swing Lab R4 — 誠實失敗與阻擋案例圖鑑 (`FAILURE_GALLERY.md`)

本文件完整收錄 R4 實作與實拍驗證過程中，系統依最高誠信原則（Fail-Closed & Anti-Hallucination）主動攔截、降級或標示為 `NEEDS_REVIEW` / `UNAVAILABLE` / `BLOCKED` 之真實案例與原因碼。

---

## 案例 1：專用桿頭偵測權重 `swingtrace-yolo11m.pt` 受限於 Gated Repo (`MODEL_UNAVAILABLE:swingtrace-yolo11m`)
- **觸發片段**：全部實拍揮桿片段（如 `11s_iphone.mov` `e9ef2b80`、`IMG_0995.mov` `810c7517`）
- **現象**：HuggingFace `nishsm/golf-club-detection-swingtrace` 為 `gated: auto`（未登入下載回傳 `HTTP 401 GatedRepo`），本機 `~/Library/Application Support/GolfSwingLab/models/swingtrace-yolo11m.pt` 不存在。
- **系統誠實處置**：
  1. `TracerModelRegistry` 狀態設為 `BLOCKED_GATED_WEIGHTS`。
  2. `SwingTracerEngine` 自動切換至 OpenCV Canny+CLAHE+HoughLinesP 桿身幾何端點估算，所有點位標記為 `source_type = 'shaft_geometry_estimated'`（0 點標為 `detector_observed`，0 點使用手腕座標）。
  3. 片段狀態強制設為 `NEEDS_REVIEW`，`end_to_end_eligible = False`，附上原因碼 `MODEL_UNAVAILABLE:swingtrace-yolo11m` 與 `LOW_DIRECT_OBSERVATION_COVERAGE:0.00`。

---

## 案例 2：打擊墊靜止球與背景高空燈具誤報攔截 (`launch_origin_too_high` / `insufficient_upward_elevation`)
- **觸發片段**：`IMG_0995.mov` (`810c7517`, `86.4s–93.7s`)、`11s_iphone.mov` (`e9ef2b80`, `1.9s–9.1s`)
- **現象**：
  - 在 60fps 室內/夜間練習場畫面中，擊球後真球因高初速產生運動模糊；`golf_ball_yolov8n.pt` 在部分影格偵測到練習場頂棚燈具 (`y_norm < 0.35`) 或打擊墊邊緣未升空之白點 (`upward_elevation < 0.04`)。
- **系統誠實處置**：
  1. 背景靜止濾波器 (`_filter_background_static_points`) 先剔除跨多格位置不變 (`disp < 0.008`) 的固定亮點。
  2. 物理合理性守門員檢驗起飛點高度 (`y_norm >= 0.42`)、向上爬升量 (`upward_elevation >= 0.04`) 與總位移 (`total_disp >= 0.06`)。
  3. 未通過檢核時，100% 清空殘留點並回傳 `ShotTrackMode.UNAVAILABLE`，附上明確原因碼 `launch_origin_too_high`、`insufficient_upward_elevation`、`insufficient_total_displacement`。

---

## 案例 3：空揮片段零假球道保證 (`no_ball_detected`)
- **觸發片段**：`IMG_0995.mov` (`d870c908`, `0.2s–1.8s`, `ball_strike_status = 'no_ball'`)
- **現象**：球友進行空揮練習，地面無擊球升空。
- **系統誠實處置**：
  - `ShotTracerEngine` 在擊球時間窗內未觀測到任何有效起飛球對，回傳 `ShotTrackMode.UNAVAILABLE`、`total_points = 0`、`rejection_reasons = ['no_ball_detected']`。

---

## 案例 4：下桿高速模糊造成 `> 200ms` 遮擋缺口時禁止硬連內插 (`LARGE_OCCLUSION_GAP`)
- **觸發片段**：`video_2min.mov` (`37c19971`, `largest_gap_ms = 1083.3ms`)、`IMG_0995.mov` (`810c7517`, `largest_gap_ms = 616.7ms`)
- **現象**：在收桿或身體遮擋區間，連續超過 `200ms`（或 `> 6` 格）無法穩定提取球桿幾何直線。
- **系統誠實處置**：
  - `interpolate_pts_gap` 嚴格遵守 `max_gap_us = 200_000` (`200ms`) 與 `max_gap_frames = 6` 上限；超過門檻之缺口回傳 `[]`（留空斷開），絕不以長距離樣條曲線跨越身體遮擋區硬連出虛假揮桿圓弧，並於品質摘要記錄 `LARGE_OCCLUSION_GAP:617ms`。

---

## 案例 5：低解析度或 Proxy 代理影片拒絕執行高解析追蹤 (`SOURCE_LOW_RESOLUTION` / `PROXY_NOT_ALLOWED`)
- **觸發情境**：傳入 `proxies/.../proxy.mp4` 或短邊 `< 600px` 之低解析影片（如 `iphone_rotated.mov` `480x360`）。
- **系統誠實處置**：
  - `BoundedFrameReader` 與 `resolve_segment_context` 立即拋出 `SourceUnavailableError`，將專案狀態設為 `source_unavailable` 並於 Studio UI 顯示明確錯誤提示，禁止以低解析度 Proxy 冒充高畫質原片追蹤。
