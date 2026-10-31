# Golf Swing Lab R4 — 實作歷程與階段證據紀錄 (`IMPLEMENTATION_LOG.md`)

- **分支**：`feat/r4-golf-tracer-studio`（基於 `origin/main` `306de571d8b5983e3465432fb574112241148a5e`）
- **實作日期**：2026-10-31 (Asia/Taipei)
- **資料庫遷移狀態**：Alembic `0003_tracer_studio` (`upgrade head -> downgrade 0002_r3_reference_library -> upgrade head` 雙向驗證通過)

---

## 1. 階段開發與驗證摘要

| 階段 | 範圍與核心產出 | 驗證指令與證據 | 狀態 |
|---|---|---|---|
| **Phase 0** | 基準盤點、PostgreSQL 非破壞性備份 (`pre_r4_baseline_20261031.dump`)、R3 基準測試核實、開源授權清冊 | `docs/r4/BASELINE_AUDIT.md`, `docs/r4/DEPENDENCY_LICENSES.md`, Commit `4997a31` | `PASS` |
| **Phase 1** | 單一時間權威 (`source_pts_us`) 與正規化直立座標契約、8 張 `tracer_*` 資料表、`/api/tracer/*` REST 端點、Studio 逐幀編輯器與 Copy-on-Write 修訂版 | `tests/test_tracer_contracts_and_math.py` (`13 passed`), `tests/test_tracer_api_and_security.py` (`2 passed`), `apps/web/src/__tests__/tracer_studio.test.ts` (`4 passed`) | `PASS` |
| **Phase 2** | **Swing Tracer**：專用桿頭偵測器介面 (`ClubheadDetector`)、OpenCV Canny+CLAHE+HoughLinesP 桿身幾何端點估算 (`shaft_geometry.py`)、嚴禁手腕冒充桿頭、三階段上色切分 (`backswing`/`downswing`/`follow_through`)、品質閘門 | `tests/test_tracer_engines.py` (`7 passed`)；實拍缺 `swingtrace-yolo11m.pt` 權重誠實標記 `BLOCKED_SWING_AUTO` / `NEEDS_REVIEW` | `PASS` (Engine & Fallback) / `BLOCKED_SWING_AUTO` (Gated Weights) |
| **Phase 3** | **Shot Tracer**：高解析原片串流讀取 (`BoundedFrameReader`)、雙向左右飛球 ROI (`roi_planner.py`)、`golf_ball_yolov8n.pt` + 白色圓斑候選、LK 光流、真實 PTS `dt` 卡爾曼濾波、打擊墊靜止球與背景固定亮點排除、五態誠實標示 | `tests/test_tracer_engines.py`；6 段實拍高解析片段測試與拒斥原因紀錄 (`docs/r4/REAL_MEDIA_EVALUATION.md`) | `PASS` (Engine & Rejection Gates) |
| **Phase 4** | **Flight FX + 匯出矩陣 + 多球合輯 + Mac App 安全打包**：`RenderRecipeV1` 6 種核心風格與 6 組預設、預覽與匯出同源幾何合成 (`<=2.0px@1080p`, `<=1 frame`)、`original`/`16:9`/`9:16` × `30`/`60fps` × `preserve`/`mute`、1–10 球合輯、`.tracer.json` Sidecar、`scripts/build_mac_app.sh` 安全升級 | `/tmp/r4_eval_report.json`（6 組單球匯出 + 2 球合輯 100% 通過 Parity 與 `ffprobe` 驗證）、`scripts/build_mac_app.sh` v1.4.0 驗證 | `PASS` |
| **Phase 5** | 單元/整合/安全測試、實拍媒體評估、原生 macOS `WKWebView` 實測截圖、錯誤圖鑑、8 份完整技術報告與 Draft PR | `.venv/bin/pytest -q` (`157 passed`), `vitest` (`7 passed`), `next build` (`PASS`), `docs/r4/webkit_tracer_studio.png` (`542 KB`, 0 JS Error) | `PASS` |

---

## 2. 自主除錯與根因修復紀錄（Root Cause & Fix Loop）

### 2.1 FFmpeg 9.0.2 移除 `-vsync cfr` 參數相容性問題
- **現象**：於 macOS Homebrew FFmpeg `9.0.2` 執行 `export_single_tracer_clip` 時，FFmpeg 回報 `Unrecognized option 'vsync'. Error splitting the argument list: Option not found`。
- **根因**：FFmpeg 7.x/8.x/9.x 已正式棄用並移除 `-vsync`，改以 `-fps_mode cfr` 取代。
- **修復**：於 [studio_exporter.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/packages/analysis/tracer/studio_exporter.py) 將 `-vsync cfr` 更新為 `-fps_mode cfr`。
- **複驗**：6 組單球匯出與 2 球批次合輯全數通過 `ffprobe` 驗證。

### 2.2 藝術延伸超出原始片段 `end_pts_us` 時之 PTS 對齊誤差
- **現象**：當啟用 `artistic_extension_enabled=True` 且落點時間 `landing_pts_us` 延伸至原始片段 `spec.end_pts_us` 之後（例如 `1350ms -> 1590ms`）時，`parity_report.pts_parity_passed` 為 `False`。
- **根因**：`export_single_tracer_clip` 原本僅以 `[spec.start_pts_us, spec.end_pts_us]` 產生 `output_pts_grid`，導致延伸至 `1590ms` 的軌跡點與最後一格輸出影格產生 `240ms` 時間差。
- **修復**：於 [studio_exporter.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/packages/analysis/tracer/studio_exporter.py) 動態計算 `all_pts = [p.source_pts_us for p in (spec.swing_points + spec.shot_points)]`，將 `reader_end_us` 擴展至涵蓋所有軌跡點（上限為原片總長 `tl.duration_us`）。
- **複驗**：`max_frame_delta_frames <= 0.5 <= 1.0`，`pts_parity_passed = True`。

### 2.3 11 分鐘 HEVC 長片 (`IMG_0995.mov`) 後段區間 OpenCV Seek 失敗
- **現象**：針對 `IMG_0995.mov` 後段 `567.0s–574.3s` 揮桿片段 (`33da6b35`) 呼叫 `BoundedFrameReader.iter_window` 時，OpenCV `cap.set(cv2.CAP_PROP_POS_MSEC, 567000)` 後 `cap.read()` 回傳 `False`。
- **根因**：1. `BoundedFrameReader.__init__` 探測時僅載入前段 PTS 時間軸；2. OpenCV 內建 FFmpeg 封裝對含 B-frame 之 1.38GB HEVC `.mov` 長片在大時間跨度 `CAP_PROP_POS_MSEC` 定位時會失敗。
- **修復**：於 [frame_reader.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/packages/analysis/tracer/frame_reader.py) 擴充 `_ensure_timeline` 自動依請求區間重抽 `ffprobe -read_intervals` PTS 時間軸，並於 OpenCV seek 回傳 0 格時自動切換至 `ffmpeg -noautorotate -ss <sec> -t <dur> -i <video> -f rawvideo -pix_fmt bgr24 -` 原生管道解碼。
- **複驗**：`IMG_0995.mov` 在 `567.0s–574.3s` 成功解碼全部 463 格高解析直立影格並產出 189 個桿身幾何追蹤點。
