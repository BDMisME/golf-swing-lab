# Golf Swing Lab R4 — 預覽與匯出座標/時間對齊實測報告 (`EXPORT_PARITY_REPORT.md`)

- **驗證時間**：2026-10-31T09:48:48Z (`2026-10-31T17:48:48+08:00`)
- **測試原片**：`11s_iphone.mov`（`1080x1920` 直立高解析原片，60.04fps HEVC，含音軌）與 `IMG_0995.mov`（`1920x1080` `rotation=270` 直立後 `1080x1920`，59.96fps HEVC，含音軌）
- **驗收門檻**：
  1. 預覽畫布與最終匯出 MP4 在 1080p 基準下之最大座標對齊誤差 `max_coordinate_error_px <= 2.0 px`
  2. 時間軸對齊誤差 `max_frame_delta_frames <= 1.0 frame`
  3. 輸出編碼必須為 `h264` (`yuv420p`)、`rotation = 0`（不二次旋轉）、音軌狀態與 `preserve`/`mute` 100% 一致，並附帶 `.tracer.json` 溯源 Sidecar

---

## 1. 單球匯出矩陣 (`original` / `16:9` / `9:16` × `30` / `60fps` × `preserve` / `mute`) 實測結果

| 匯出組態 (`config`) | 比例 (`aspect`) | 目標幀率 (`fps`) | 音訊模式 (`audio`) | `ffprobe` 實測寬×高 | `ffprobe` 實測 Codec / FPS / 音軌 / 旋轉 | 總幀數 (`frames`) | 檢查點數 | 最大座標誤差 (`max_err_px`) | 平均座標誤差 (`mean_err_px`) | 最大時間誤差 (`frames`) | Parity 判定 | MP4 SHA256 (前 16 碼) |
|---|---|---:|---|---|---|---|---:|---:|---:|---:|---|---|
| `original_30fps_preserve` | `original` | `30` | `preserve` | `1080×1920` | `h264` / `30.0` / `audio=True` / `rot=0` | 61 | 37 | **`0.5811 px`** | `0.4199 px` | **`0.50 F`** (`16667 us`) | **`PASS`** | `4f920e0e29ed283f` |
| `original_60fps_mute` | `original` | `60` | `mute` | `1080×1920` | `h264` / `60.0` / `audio=False` / `rot=0` | 121 | 37 | **`0.5811 px`** | `0.4199 px` | **`0.40 F`** (`6667 us`) | **`PASS`** | `f61d078d446403a8` |
| `16x9_30fps_preserve` | `16:9` | `30` | `preserve` | `1920×1080` | `h264` / `30.0` / `audio=True` / `rot=0` | 61 | 37 | **`0.6647 px`** | `0.3624 px` | **`0.50 F`** (`16667 us`) | **`PASS`** | `cd1775c79f6998de` |
| `16x9_60fps_mute` | `16:9` | `60` | `mute` | `1920×1080` | `h264` / `60.0` / `audio=False` / `rot=0` | 121 | 37 | **`0.6647 px`** | `0.3624 px` | **`0.40 F`** (`6667 us`) | **`PASS`** | `dd363c7c51aa65a6` |
| `9x16_30fps_preserve` | `9:16` | `30` | `preserve` | `1080×1920` | `h264` / `30.0` / `audio=True` / `rot=0` | 61 | 37 | **`0.5811 px`** | `0.4199 px` | **`0.50 F`** (`16667 us`) | **`PASS`** | `4f920e0e29ed283f` |
| `9x16_60fps_mute` | `9:16` | `60` | `mute` | `1080×1920` | `h264` / `60.0` / `audio=False` / `rot=0` | 121 | 37 | **`0.5811 px`** | `0.4199 px` | **`0.40 F`** (`6667 us`) | **`PASS`** | `f61d078d446403a8` |

---

## 2. 多球連續合輯匯出 (`export_batch_tracer_compilation`, 跨旋轉角度原片串接) 實測結果

- **輸入片段**：
  - Clip 1：`11s_iphone.mov` (`rotation=0°`, `1080x1920`, `3200ms–4950ms`)
  - Clip 2：`IMG_0995.mov` (`rotation=270°` -> 自動轉正為 `1080x1920`, `87400ms–89200ms`)
- **目標格式**：`9:16` (`1080x1920`), `30fps`, `audio_mode=preserve`
- **實測數據**：
  - 輸出檔案：`/tmp/r4_export_matrix/batch_compilation_2clips.mp4` (`2,803,860 bytes`, `sha256=b50a57cc5d0762a0...`)
  - Sidecar：`/tmp/r4_export_matrix/batch_compilation_2clips.tracer.json` (`11 KB`)
  - `ffprobe` 驗證：`codec=h264`, `width=1080`, `height=1920`, `has_audio=True`
  - Parity 對齊報告：`max_coordinate_error_px = 0.5793 px` (`<= 2.0 px`), `max_frame_delta_frames = 0.50 F` (`<= 1.0 F`) -> **`PASS`**
