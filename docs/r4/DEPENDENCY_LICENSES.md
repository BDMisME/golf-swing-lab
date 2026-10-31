# Golf Swing Lab R4 — 第三方模型與開源依賴授權審查 (`DEPENDENCY_LICENSES.md`)

> **審查日期**：2026-10-31  
> **審查原則**：嚴格區分程式碼授權（Code License）、模型權重授權（Weight License）、訓練資料集授權（Dataset License）、下載門檻（Gated Access）與再散布限制（Redistribution）。禁止靜默自動下載受限模型或將未授權權重打包進 Git / 發行包。

---

## 1. 現有與新增依賴授權總表

| 組件 / 模型 | 版本 / 識別碼 | 程式碼授權 | 權重 / 資產授權 | 本機狀態與 SHA256 | 採用決策與合規邊界 |
|---|---|---|---|---|---|
| **OpenCV (`opencv-python-headless`)** | `>=4.10.0.84` | Apache-2.0 | N/A | 已安裝於 `.venv` | **PRIMARY**：用於 LK 光流 (`calcOpticalFlowPyrLK`)、KalmanFilter、Canny/HoughLinesP 桿身幾何偵測、RANSAC/Huber 擬合、相機晃動特徵匹配與 RGBA 向量光暈渲染。可合法商業與個人使用。 |
| **FFmpeg / FFprobe** | System binary (`/opt/homebrew/bin/ffmpeg`) | LGPL v2.1+ / GPL v2+ (含 `libx264`) | N/A | 已安裝於本機 macOS | **PRIMARY_EXPORT**：透過 `subprocess.run` 參數陣列（禁止 shell interpolation）呼叫本機系統 `ffmpeg`/`ffprobe`，不將 GPL `libx264` 靜態連結進專有二進位檔，亦不在 Git repo 中再散布 FFmpeg 執行檔。 |
| **Ultralytics (`ultralytics`)** | `>=8.4.182` | AGPL-3.0 | 視具體模型而定 | 已安裝於 `.venv` | **ISOLATED_ADAPTER**：既有 R3 依賴。在 R4 中透過 `ClubheadDetector` 與 `ShotDetector` 介面隔離；僅供本機執行，不將 AGPL 權重打包公開再散布。 |
| **本機小白球模型 (`golf_ball_yolov8n.pt`)** | `golf_ball_yolov8n` (`{0: 'golf_ball'}`) | AGPL-3.0 (Ultralytics runtime) | 本機既有私有權重 | 已安裝於 `~/Library/Application Support/GolfSwingLab/models/golf_ball_yolov8n.pt`<br>`sha256: 45e8f8bd8975dc7f437919a11c3f6ee1fe7c8ae40b0f49910d0677d1c0326791`<br>`size: 24,458,339 bytes` | **ADOPTED_LOCAL**：由 `packages/analysis/tracer/shot_detector.py` 載入並記錄模型 SHA256 與版本。`.gitignore` 已攔截 `*.pt`，絕不提交至 GitHub。 |
| **本機姿態模型 (`yolov8x-pose.pt`)** | `yolov8x-pose` | AGPL-3.0 | Ultralytics 公開權重 | 已安裝於 `~/Library/Application Support/GolfSwingLab/models/yolov8x-pose.pt`<br>`sha256: 7a9bf952c2fc1c07d4a1da00dbb4cfab5ed71f89cbe8824d51a8f7a61cee5825` | **EXISTING_R3**：供 R3 姿態與手腕 ROI 先驗參考；**嚴禁將手腕點當成桿頭點**。 |
| **SwingTrace (`nishsm/golf-club-detection-swingtrace`)** | `swingtrace-yolo11m.pt` | AGPL-3.0 | AGPL-3.0 (HuggingFace `gated: auto`，訓練集來自 Roboflow Universe `golf-club-tracking`) | **本機未安裝 (`MODEL_UNAVAILABLE`)**<br>實測匿名 HEAD 請求回傳 `HTTP 401 GatedRepo`（需使用者本人登入 HuggingFace 同意授權條款方可下載） | **ADAPTER_READY_BUT_GATED**：<br>1. 系統內建 `SwingTraceClubheadAdapter`，支援使用者自行合法下載至 `~/Library/Application Support/GolfSwingLab/models/swingtrace-yolo11m.pt` 後自動啟用。<br>2. 絕不繞過 HF 認證或代使用者靜默下載。<br>3. 未安裝該權重時，`/api/tracer/models/status` 與 `/api/tracer/health` 誠實回報 `MODEL_UNAVAILABLE` (`gated_auth_required`)，Swing Tracer 自動直接桿頭偵測標記為 `BLOCKED_SWING_AUTO`，並自動切換為 `shaft_geometry_estimated`（OpenCV 桿身線段端點幾何推算，獨立標記來源）或 `manually_annotated`（人工逐格校正）。 |
| **React / Next.js / HTML5 Canvas 2D** | Next.js 15.5, React 19.0, Lucide React | MIT | N/A | 已安裝於 `apps/web` | **PRIMARY_UI**：使用原生 HTML5 `<canvas>` + Pointer Events + Shared Geometry Transforms 實作逐幀編輯器，避免 `react-konva` 在 React 19 下潛在 peer dependency 衝突與 WebKit 額外記憶體開銷，確保 100% 輕量與確定性座標轉換。 |
| **GolfShotTracer (`jonibek95/GolfShotTracer`)** | GitHub Repo | 未明確標示開源授權（All Rights Reserved 風險） | 未知 | 未下載、未引用 | **REJECTED_CODE_AND_WEIGHTS**：未確認授權且其 3D 物理模擬違反本專案「不將模擬球路冒充真實觀測」原則，0 行程式碼複製。 |
| **Norfair / SAM 2 / BoxMOT** | 外部候選套件 | BSD-3 / Apache-2.0 / AGPL-3.0 | Apache-2.0 / AGPL-3.0 | 未安裝 | **NOT_INSTALLED**：單球與單桿追蹤由本機 OpenCV PTS-Kalman + 多方向光流 + 幾何約束完成，避免為單目標引入數百 MB 額外依賴或破壞 Mac 打包穩定性。 |

---

## 2. 隱私與無外部網路洩漏保證（Offline Egress Guard）

1. **禁止外傳私人影片**：所有 `packages/analysis/tracer/*` 與 `/api/tracer/*` 端點 100% 於本機處理，不包含任何外部 HTTP 呼叫或雲端視覺 API。
2. **禁止背景自動下載模型**：`tracer_model_registry` 僅讀取本機 `~/Library/Application Support/GolfSwingLab/models/` 目錄並校驗 SHA256，絕不在背景向 HuggingFace 或外部伺服器發起下載。
3. **私人媒體 Git 隔離**：`.gitignore` 強制排除 `*.mov`、`*.MOV`、`*.pt`、`docs/screenshots/webkit_*`，確保私有高爾夫原片與模型權重不會被提交至 GitHub。
