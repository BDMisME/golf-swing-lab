# Golf Swing Lab R4 — Golf Tracer Studio【完整整合書＋GitHub 開源研究＋Gemini 4 Argon Master Prompt】

> **獨立新 Session 可直接閱讀的單一 Markdown 交付檔**。截至 2026-10-31。

## 文件順序

1. 讀取說明
2. 完整系統架構與嚴格驗收
3. GitHub 開源模型與授權研究
4. Gemini 4 Argon 一次性自主開發總指令

---



<!-- BEGIN README_START_HERE.md -->

# Golf Tracer Studio R4 — 新 Session 開發交付包

**基準**：`BDMisME/golf-swing-lab`，PR #3 已合併；當時 `main` 合併 SHA `306de571d8b5983e3465432fb574112241148a5e`（新 Session 先核實最新 HEAD）。

**這個交付包是架構規劃與開發 Prompt，不是 R4 已完工的程式碼。**

## 文件

1. `GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md` — **最完整整合書**，含既有專案真實盤點、Swing/Shot/FX、資料庫、API、逐幀編輯器、原片/PTS、Worker、Mac App、完整實拍驗收標準。
2. `GITHUB_OPEN_SOURCE_RESEARCH.md` — GitHub 模型、演算法與渲染工具研究、授權及採用決策。
3. `GEMINI_4_ARGON_MASTER_PROMPT.md` — **在新 Gemini 4 Argon Session 執行的總指令**，要求一次連續開發、主動測試、修 Bug、Draft PR，不得假 PASS。

## 使用方法

在新 Session 上傳上述三個 `.md`（或這個 ZIP），並貼上以下一句：

> 請完整讀取我上傳的 `GEMINI_4_ARGON_MASTER_PROMPT.md`、`GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md` 和 `GITHUB_OPEN_SOURCE_RESEARCH.md`。它們是本次 Golf Swing Lab R4 唯一完整規格。依主控 Prompt 直接連續執行從 GitHub main 盤點、R4 開發、測試、修復到獨立 Draft PR；不得只交計畫、不得擅自 merge main、不得捏造任何真實影片測試、模型權重或 Mac native 驗收通過結果。若缺真實資源要誠實 BLOCKED。

## 真實限制

- 自動 Swing/Shot 的實際準確度必須有真實影片和人工標註才能驗收；文件列的數字是 **目標**，不是已經通過的性能。
- AI 是否能在新 Session 直接操作 GitHub、本機 Mac／WebKit、模型下載，取決於 Session 的已授權工具，不能靠文字 Prompt 產生沒有的權限。
- 原始私有影片與第三方權重受隱私與授權限制；審查/報告必須保護。

**Ready for Gemini R4 engineering, not ready for production release.**


<!-- END README_START_HERE.md -->

---


<!-- BEGIN GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md -->

# Golf Swing Lab R4 — Golf Tracer Studio 完整系統架構暨工程整合規格書

> **文件類型**：Gemini 4 Argon 新 Session 可直接讀取的獨立技術規格／單一事實來源（Source of Truth）  
> **版本**：R4.0 — Architecture & Implementation Contract  
> **日期**：2026-10-31（Asia/Taipei）  
> **目標儲存庫**：https://github.com/BDMisME/golf-swing-lab  
> **已核實基準**：PR #3 已於 2026-10-31 合併，合併提交 `306de571d8b5983e3465432fb574112241148a5e`。開始時仍須 `git fetch`、重新核對 `origin/main`，不可把這個 SHA 硬當永遠不變的 HEAD。  
> **用途**：供 Gemini 4 Argon 在新的、沒有歷史對話的 Session，自主理解現有應用、審查、規劃、連續實作、測試、修復，最後交付獨立 Draft PR。  
> **現況聲明**：本文件是**規劃文件，不是已完成的 R4 功能／測試報告**。本次僅遠端抽查 GitHub 既有檔案與開源來源，沒有在使用者的 Mac 上實測 R4，也沒有提交 R4 程式碼。

---

## 0. 一頁總綱：做什麼、不能做什麼、怎樣算成功

### 0.1 產品定位

在既有 **Golf Swing Lab** macOS 個人揮桿分析應用之上，新增 **Golf Tracer Studio** 影像創作及可解釋軌跡分析工作區，完整提供：

1. **Swing Tracer** — 對真正的球桿桿頭進行 2D 辨識與逐格追蹤；上桿／下桿／隨揮三段可選不同顏色，顯示平面投影路徑、逐格校正與雙揮桿對比。
2. **Shot Tracer** — 從實際可觀測影格偵測高爾夫球飛行軌跡；支援自動追蹤、低可信度提示、人工錨點、重新擬合，以及**明確標註**的推測／藝術延伸。
3. **Flight FX** — 共用視覺特效引擎，提供 Clean／Neon／Beam／Gradient／Tail／Pulse，能分別套用於 Swing、Shot，也能疊加；支援尺寸、顏色、光暈、透明度、生命週期、圖層順序與批次套用。
4. **輸出／批次** — 保持原有「無特效匯出」，另提供原比例／16:9／9:16、30/60fps、單球／多球合輯與可預覽的非破壞式製作流程。
5. **Mac 本機優先、無新付費 API 依賴** — 分析、編輯、渲染、匯出均可在本機離線運作；無需新雲端帳號或 API Key。

### 0.2 絕對邊界

- **禁止以手腕、前臂、握把軌跡直接偽裝桿頭**。人體關鍵點可做候選 ROI 和運動約束，`club_head` 的來源必須是桿頭直接影像偵測、可信的桿身幾何推定，或明確人工點位；其餘標為估計或不可觀測。
- 單視角 2D 軌跡不是球速、桿頭速度、Carry、Total Distance、Spin、3D Club Path、Face Angle、Attack Angle 或真正 3D Swing Plane。不得以炫目效果暗示這些不可量測數據已被精確取得。
- **觀測點、插值點、外推點、手動點、藝術化點**必須保留獨立類型與來源，畫面與 JSON 均能辨識。未觀測到的球路不得寫成成功追蹤。
- 修改 Impact/Top 僅影響 Tracer 工程的獨立 anchor override；**不得默默覆寫**既有 R3 核心 `SwingEvent`、Pose、Score 與教練證據。若將來支援寫回，必須明示與獨立授權、版本化。
- 不刪除原始影片、資料庫、18 筆示範紀錄或其他個人資產；不執行破壞性 schema migration；不得直接合併 `main`。
- 不因專用模型缺失而以合成假線假點冒充真實測試；缺模型必須明確報告 `MODEL_UNAVAILABLE`，並保證人工模式可正常使用。
- **一次性自主完成**意指單一工作階段持續從盤點→計畫→開發→測試→修復→Draft PR；不是跳過驗收、捏造樣本或假裝不具備的 Mac/GPU／模型已就緒。遇真實外部阻擋要寫 `BLOCKED` 和證據。

### 0.3 最終驗收狀態

只允許 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`，每個模組及整體版本分開評分。**整體 PASS 必須 Swing Tracer、Shot Tracer、Flight FX、匯出、批次、R3 回歸、Mac App 全部 PASS。** 人工模式通過不能替代自動模式通過。未取得必要真實影片數量不能全案 PASS。

---

## 1. 已核對的 R3 現有系統與「改造而非推倒重練」策略

### 1.1 基準與版本驗證

- Repo：`BDMisME/golf-swing-lab`，private；PR #3 `feat/r3-offline-coach-and-slow-motion` 已合併至 `main`，合併 SHA 見文件首頁。
- Python：`>=3.12,<3.13`；FastAPI、SQLAlchemy 2、Alembic、Pydantic v2、Redis/RQ、OpenCV、MediaPipe、Ultralytics、NumPy、pywebview。`pyproject.toml` 為證據。
- 前端：Next.js 15、React 19、TypeScript、Tailwind；`apps/web/package.json` 的前端測試命令為 Vitest、型別檢查為 `tsc --noEmit`。
- Storage：`packages/storage/s3_client.py` 提供 Local / S3 / Hybrid storage；現有本機預設路徑 `~/.golfswinglab/storage`；存在 MinIO 舊資料相容路徑。
- 服務：Web 開發 port 23000、API port 28000；PostgreSQL/Redis/MinIO 由既有環境提供，不可硬改使用者環境變數。
- R3：離線教練，8 項可觀測 2D 比較指標，雙影片慢動作同步，18 筆示範素材庫，既有單球與合輯匯出。R3 報告為基準，必須由新 Session 在本機重新跑以取得真實新鮮結果。

### 1.2 關鍵程式定位表

| 區域 | 真實既有檔案／函式 | R4 應做的改造 |
|---|---|---|
| 切球與事件 | `packages/analysis/detection/scanner.py`，`CoarseToFineDetector.analyze_video` / `analyze_single_window` | 重用 `SwingSegment.start_ms/end_ms` 和 `SwingEvent.time_ms`；不得重新解析全場事件 |
| 初始球體偵測 | `packages/analysis/tracking/ball_tracker.py`，`GolfBallDetector.detect_in_roi`、`track_swing_launch_with_feedback` | 可沿用 YOLO ROI、Kalman 與可見證據，**另建 Studio Shot Tracker**；延長可見追蹤窗口，但不可將原本 1.2s 證據直接冒充完整飛行軌跡 |
| 原先 Impact 回饋 | `scanner.py` 中 ball launch feedback 會在符合條件時更新 estimated impact | R4 自有 anchor override；永不透過 Studio 不經批准改寫 R3 自動事件與評分 |
| 分析 Worker | `apps/worker/tasks.py` `run_video_analysis_job` | 新增 `run_tracer_job`，不要將特效分析嵌入初次長片全量掃描 |
| 現有 Worker Queue | `apps/worker/main.py` 有 `gsl-analysis`、`gsl-exports` | 增設 `gsl-tracer`（或設計可退化 queue），序列化背景任務與可取消性 |
| 影片匯出 | `packages/analysis/exporter.py` `export_swing_compilation` | 保持原函式及無特效效果不變；新增 `studio_exporter.py`／`compositor.py` |
| API | `apps/api/main.py` `/api/videos/.../swings`、`/api/swings/{id}`、`/api/exports` 等 | 新增獨立 `apps/api/routers/tracer_studio.py`；只在必要時擴充既有匯出契約 |
| API Contracts | `apps/api/schemas.py` `CreateExportRequest` | 既有限制 1–3 球、`original|9:16`；新 Studio 新版本 schema，保留舊端點 |
| DB | `apps/api/models.py` `Video`、`SwingSegment`、`SwingEvent`、`PoseArtifact`、`SwingScore`、`ExportJob` | 新建 Tracer 專屬資料表與 Alembic migration；以外鍵關聯不覆寫原本紀錄 |
| PTS/旋轉 | `packages/analysis/probe.py` `probe_video_file`、`VideoMetadata` | 沿用 video rotation / VFR 訊息，但新增可靠逐影格 PTS 抽取與座標轉換測試 |
| 高階雙球 UI | `apps/web/src/components/SwingComparisonPlayer.tsx` | 可重用影片播放和幀步進設計；Studio Editor 應分獨立元件，不將 2,000+ 行元件繼續膨脹 |
| Mac 打包 | `scripts/build_mac_app.sh`、`launcher.c` | 打包新增模型／資產與本地路徑；修改安裝流程的備份／安全守衛 |

### 1.3 現有已知缺口／必須處理的設計債

1. **來源畫質**：`run_video_analysis_job` 生成 Proxy 後優先用 Proxy 做 coarse/fine；`run_export_job` 也優先下載 Proxy；高爾夫球可能小到只有數像素，R4 追蹤與正式匯出必須明確選**原始高解析素材**。Proxy 僅用於預覽、低解析 UI；原片失聯應 `SOURCE_UNAVAILABLE`，不可安靜退化而仍聲稱高畫質。
2. **既有球追蹤不等於完整 Shot Tracer**：`track_swing_launch_with_feedback()` 約從 Impact-250ms 至 Impact+1200ms，以腕部位置決定偏側 ROI，僅將有效 airborne_points 用 Kalman 平滑回傳，沒有跨全空域重辨識、可視遮擋編輯、每點嚴格 evidence lineage 或 Studio 配方檔。
3. **「observed」標籤過度簡化**：目前返回 Kalman 修正的 `x,y`，同時保留 `raw_x/raw_y`，卻標 `point_type=observed`。Studio 要將真正 detector 座標與 Kalman filtered 位置分開，避免 filtered ≡ observation 的混淆。
4. **ROI 方向偏差**：現有 `roi_x2` 隨時間向右擴展，對左手打者／球往左側飛的場合不充分；R4 應實施雙向候選、視角與方向自適應。
5. **時鐘問題**：OpenCV `CAP_PROP_POS_MSEC` 對 VFR/HEVC/旋轉等可能有精度差異；R4 要依實際 presentation timestamp 建立時間基準，避免 `frame_idx / fps` 作為權威時鐘。
6. **匯出功能契約不一致**：`CreateExportRequest.max_length=3`，`export_swing_compilation` 最大接受 5 個 clip；舊端點保持相容，新 Studio 統一上限與 UI 文案（預設建議 1–10 球，超過上限只允許明確分批並在能力測試後擴充）。
7. **既有匯出強制 30fps、去除音訊**：`-r 30`、`-an`，只支援原始/9:16；新輸出管線要明確支援 60fps、16:9、音訊政策（保留/靜音）並驗證 A/V Sync。
8. **打包流程有破壞性動作**：`scripts/build_mac_app.sh` 執行 `rm -rf /Applications/Golf Swing Lab.app`、刪除桌面同名 bundle；升級先備份、確認目標僅為 app bundle、atomic replace 和 rollback；禁止碰 `~/.golfswinglab` 資料。
9. **Worker 負載與 fallback**：既有 inline thread fallback，R4 超長任務要引入逐段 checkpoint、記憶體限制、CPU/MPS 降級、取消/恢復，不能阻斷 R3 分析和 API。
10. **防重複**：追蹤原始資料和編輯配方分離，換 FX 不重新跑偵測；同影片不同編輯版本不可互相覆蓋。

### 1.4 改造安全政策

- 新建 `feat/r4-golf-tracer-studio` 分支，`base` 必須是合併 R3 後最新且無衝突的 `origin/main`。
- API 路由版本化，新資料表採 additive migration；舊 `/api/exports`、`exports`、`swing_scores` 等只做非破壞性相容修正。
- R4 功能採 feature flag `GSL_ENABLE_TRACER_STUDIO`，可快速關閉、且關閉後 R3 照常可用。
- 實驗性模型使用專屬 adapter；不能修改既有姿勢評分公式、示範分析與排名。
- 建立資料庫與 storage 快照、migration 升降版演練；遇不可逆 downgrade，明確記錄與設計安全補救，不得虛構成功。

---

## 2. 產品工作流程、角色、導覽與 UX

### 2.1 使用者路徑 A：長影片練習

1. 用 iPhone DTL 固定機位錄製 10–30 分鐘 `.MOV`/`.MP4`，原有 upload / analysis 處理長影片並切出 `SwingSegment`。
2. 進入現有練習場次報告，利用姿勢／節奏／收桿／IG 視覺排名選出候選球（保留原本 AI 分數語意）。
3. 點擊「製作 Tracer」進入 **Golf Tracer Studio**：預設使用該球 `segment_id`、`start_ms`、`end_ms`、已有 Impact/Top events；展示原始資料信心度。
4. 使用者選 `Swing`、`Shot` 或 `Both`；僅對選中球的 bounded ROI/時間窗口重新解碼高解析原片。先快速跑品質檢查；低信心提示進入人工校正。
5. Studio 載入結果、透明顯示點位狀態；可拖拉球/桿頭點、切換「直線/曲線/Neon」與配色，Impact 可在 Studio 單獨調整。
6. 挑選特效及預設，預覽效果（低成本即時疊圖）；產生正式精選 MP4，單球或批次合輯。
7. 保存 Project/Presets/Edits，稍後重新開啟仍可修改與重輸出，不再重跑偵測。

### 2.2 使用者路徑 B：Shot Tracer 失敗時

- 在畫面顯示 `無法可靠自動追蹤`，原因例如 `BALL_NOT_VISIBLE`、`MOTION_BLUR`、`OCCLUDED`、`CAMERA_MOVED`、`NO_VALID_LAUNCH`、`LOW_CONFIDENCE`。
- 進入 **Manual-assisted**；Impact 點、首個可見球點、其他 2–N 點；至少 2 個可見錨點才能將人工線段稱作 user-annotated，而不是 detector observed。
- 允許用「估計延伸／創作軌跡」，但 UI 明確標記／可切換虛線，輸出資訊 JSON 列出推估部分。即使使用者選擇隱藏畫面文字標籤，機器可讀報告也不得抹掉 provenance。
- 如果沒有任何真實可見點，只可作**純藝術化動畫**，不能叫「Shot Tracer 成功追蹤」。

### 2.3 Studio 編輯器資訊架構

- 左側（或窄螢幕下方）：影片庫、單球縮圖、場次推薦、球桿及 Impact 信心狀態。
- 中央：影片畫布（播放、暫停、0.25×/0.5×/1×、前後一格、拖曳時間軸）；畫布疊加 `clubhead`, `ball`, `manual`, `predicted`, `fx` 的不同顯示層。
- 右側：**Tracks**（Swing／Shot／Both）、**Inspect**（逐點位置/PTS/來源/信心）、**Style**（顏色/寬/輝光/拖尾）、**Export**（比例/FPS/音訊/品質）。
- 工具列：自動追蹤、人工點模式、擴展 ROI、重新追蹤、Undo/Redo、版本快照、原圖／效果前後對照、危險性操作確認。
- 底部：可放大多軌時間軸、Impact/Top markers、關鍵幀、人工更正紀錄；每球時間軸同時顯示原片 `PTS` 與局部 clip time。
- 空/失敗/載入/取消、模型未下載、磁碟不足、沒有可見球、FPS 異常均須有明確 UI；不得只有 spinner。

### 2.4 預設特效建議

| Preset | Swing | Shot | 用途 |
|---|---|---|---|
| `clean_analysis` | 青上桿／橘下桿、實線 | 真實軌跡單線／不外推 | 專業姿勢分析 |
| `studio_neon` | 雙色薄霓虹 | 黃綠 Glow | IG Reels |
| `minimal_white` | 白色低透明 | 白色低透明 | 乾淨球場影片 |
| `power_beam` | 橘光束與逐漸消失尾巴 | 白金拖尾 | 強烈視覺感 |
| `rainbow_arc` | 可關閉 | 漸層色與有標記的延伸 | 特效創作模式 |
| `no_fx` | 不顯示 | 不顯示 | 舊版純淨輸出 |

### 2.5 左右手及視角

- `left/right` 必須在 UI 可改；若自動判定與設定不一致，請使用者確認，不能暗中鏡像影片或強制右飛。
- DTL 為首要測試視角；Face-on 可做 2D 桿頭追蹤但 Swing Plane 解讀不同、分析標註 `view=FO`；非支援視角必須 `NOT_COMPARABLE`、不繪錯誤平面測量。
- 相機移動／搖晃超過門檻：可嘗試背景穩定化及補償（homography/feature matching），記錄可信度；不可靠則停止自動追蹤，仍可人工編輯。

---

## 3. 整體技術架構與模組介面

```text
+--------------------------------------------------------------+
| macOS Golf Swing Lab.app (native launcher + pywebview/WebKit) |
| Next.js / React / TS                                         |
| Sessions -> Swing List -> Golf Tracer Studio                 |
| Frame Editor | Track Inspect | FX Preview | Batch | Export  |
+-----------------------+--------------------------------------+
                        | authenticated REST / progress polling
+-----------------------v--------------------------------------+
| FastAPI (existing auth + owner check + new tracer router)    |
| Project, Track, Keyframes, Revision, Job, Export recipes      |
+--------+-------------------+----------------+----------------+
         |                   |                |
   PostgreSQL/Alembic    Local/Hybrid      Redis/RQ
   metadata+revisions    original media    gsl-tracer / gsl-exports
         |                   |                |
+--------v-------------------v----------------v----------------+
| Python Studio Worker                                           |
| Segment/Impact resolver -> PTS frame reader -> ROI/camera QC  |
|  (A) clubhead detector + shaft geometry + temporal tracking   |
|  (B) ball detector + optical flow + Kalman/outlier rejection  |
|  canonical track format + manual revision merge               |
|  vector compositing + FFmpeg export + media probe             |
+--------------------------------------------------------------+
```

### 3.1 新增 Python 套件結構（建議）

```text
packages/analysis/tracer/
  __init__.py
  contracts.py             # canonical track-point, status, provenance
  segment_context.py       # reuse Segment/Event; anchor override, never silently rewrite R3
  media_clock.py           # PTS, VFR, rotation, frame indexing
  frame_reader.py          # high-resolution bounded seek, streaming decoded frames
  transforms.py            # source/display/crop/output coordinates
  camera_motion.py         # camera shake detection and compensation
  roi_planner.py           # person/ball/shaft ROI, left/right handling
  clubhead_detector.py     # club head direct detection adapter
  shaft_geometry.py       # shaft endpoint estimate with uncertainty
  swing_tracker.py         # temporal tracking and phase split
  shot_detector.py         # reuse existing ball detector as an adapter
  shot_tracker.py          # observed flight, optical flow, Kalman, outliers
  reliability.py           # quality gates and calibrated confidence
  interpolation.py         # gap-fill not observed; bounded extrapolation
  edit_merge.py            # manual anchors over immutable raw detections
  fx_schema.py             # versioned visual preset contracts
  fx_renderer.py           # deterministic frame-based vector raster renderer
  compositor.py            # overlay + source frames, crop transforms
  studio_exporter.py       # audio/video, CFR 30/60, MP4, concatenate
  artifact_cache.py        # content-addressed, checkpoint and revisions
apps/api/routers/tracer_studio.py
apps/api/schemas_tracer.py
apps/worker/tracer_tasks.py
apps/api/alembic/versions/<new_revision>_tracer_studio.py
apps/web/src/components/tracer/*
apps/web/src/app/(app)/tracer-studio/[projectId]/page.tsx
apps/web/src/lib/tracer/*
tests/test_tracer_*.py
apps/web/src/components/tracer/*.test.ts(x)
scripts/verify_r4_webkit.py
scripts/evaluate_r4_real_media.py
scripts/verify_r4_export_parity.py
```

**原則**：以上為**建議路徑**，Gemini 應根據實際路由、import 與打包規則調整，不能把假路徑當現有檔案。每個主要責任單一模組，避免把 UI 再塞到 `SwingComparisonPlayer.tsx`。

### 3.2 時間座標單一事實來源（最重要）

定義 5 種時間／座標，不得混用：

1. `source_pts_us`：原始影片可呈現影格的真實 Presentation Timestamp，**整數 microseconds**，為權威時鐘。
2. `segment_start_pts_us`、`segment_end_pts_us`：R3 段落的原片範圍，從既有毫秒 Anchor 依原片 PTS 對齊，保留 rounding error。
3. `local_time_us = source_pts_us - clip_zero_pts_us`：段內時間；首格不一定精確為零，須明確規範。
4. `output_pts_us`：渲染輸出 CFR 影格的時間點；`30fps` 每格約 33333.333μs，`60fps` 每格約 16666.667μs，**不可用整數固定步長累積造成漂移**，須用整數有理數 `time_base` 或 Bresenham 類 accumulator。
5. `image-coordinate spaces`：coded pixels → display upright pixels → source normalized → crop pad/output pixels（所有變換可逆、版本化）。

建議資料契約：

```json
{
  "track_id": "uuid",
  "track_type": "club_head",
  "segment_id": "uuid",
  "source_video_id": "uuid",
  "source_pts_us": 123456789,
  "source_frame_index": 3210,
  "x_norm": 0.5112,
  "y_norm": 0.6231,
  "confidence": 0.91,
  "source_type": "detector_observed",
  "position_role": "display_smoothed",
  "raw_observation": {"x_norm": 0.51, "y_norm": 0.625, "bbox": [0.5,0.61,0.02,0.02]},
  "model_id": "model-version-or-null",
  "evidence_frame_sha256": "sha256-or-null",
  "occlusion_state": "visible",
  "error_flags": [],
  "coordinate_space_version": 1,
  "created_by": "model",
  "revision": 3
}
```

`source_type` 必須 enum：`detector_observed | shaft_geometry_estimated | optical_flow_estimated | kalman_predicted | interpolated | extrapolated | manually_annotated | artistic_only`。其中 `detector_observed` 僅指該影格模型有實際影像偵測證據，若軌跡的 `x/y` 已平滑，須額外保留 raw observation 且 `position_role=display_smoothed`，不可把預測位置直接貼上 observed。

### 3.3 座標變換鏈

- 原片 width/height/rotation 與 EXIF/QuickTime matrix 的解碼規則使用同一個 `FrameGeometry`；避免 90/270° 旋轉雙重套用。
- ROI crop：`x_source = (x_roi + crop_left) / source_display_width`，如 resize 前後需紀錄 scale；前端顯示以 CSS `object-fit: contain` 的 letterbox padding 修正點擊位置。
- Export：先將原片轉正方向，再套用 crop/contain/pad；**在 transformed coordinate 上繪製**，與 Preview 共用同一組 `transform_project_point` 測試向量。
- 9:16/16:9 支援 `contain` 與有預覽的 `cover`；預設 contain 不裁切人物，若 cover 必須可拖曳視窗並保護球路不被截掉；輸出像素保證偶數。
- 設定視角切換時不得自動將左右打者鏡像且不留下紀錄。

### 3.4 影格讀取與 IO

- 保留 `probe_video_file`，另建 `FrameReader`：優先採用 FFmpeg/ffprobe decoded frame PTS；可評估 PyAV 的 stream decode，但不可在 macOS 打包後引進不能安裝的原生依賴。
- 由 source PTS seek 至 segment 前關鍵影格，解碼到目標區間，保留 B-frame 解碼/呈現順序差異。以 PTS 排序後不得把重複 PTS 冒充不同時間。
- 避免整段 30 分鐘影片全部載入 RAM。按 clip window streaming，LIFO 解碼快取，LRU 清理；限制同時高解析 jobs。
- 影片 24、25、29.97、30、59.94、60、120fps 與 VFR 皆有時間契約；輸出 30/60 不等同讓原始 30fps 產生真實額外採樣資訊。
- 使用者挑選的 `segment_id` 作為 analysis cache key，且 key 包含原片 SHA、segment bounds、anchor revision、tracker version、model SHA、tracking settings、coordinate version。只變樣式時 cache 不失效。

---

## 4. Swing Tracer — 真正桿頭偵測與揮桿路徑

### 4.1 模型策略（先評估可行，再固定）

**首選研究原型**：`nishsm/golf-club-detection-swingtrace` YOLO11m，包含 club shaft、club head、hands，並有已公布的 club path 重建。已公布 unseen-video 測試僅 7 支影片、3018 格，直接 head detection 約 71.6%、head-or-shaft 約 93.4%，**不是對本產品素材的實測，也不能保證快速揮桿每幀可見**。模型為 AGPL-3.0、HF 權重可能需登入同意條件，不能假設可免授權自由再發布。

- 先寫 `docs/r4/DEPENDENCY_LICENSES.md` 盤點 Ultralytics 與模型權重，個人私用與未來發行／商業化風險分開；若授權不合要求，選 OpenCV 桿身線段+端點追蹤替代，或以 Apache-2.0 RF-DETR 自己合法訓練 clubhead 專用分類器；**沒有已訓練權重不能宣稱自動桿頭完成**。
- `SAM 2` 可用作選點後的人工輔助分割研究，但大模型 Apple MPS 相容、安裝體積和追蹤薄桿的可靠度必須先測；不是主流程必要依賴。
- 桿頭本體 ROI 直接模型輸出置信度；當頭失焦/遮蔽時可經桿身幾何估計端點，標 `shaft_geometry_estimated`，並附估計誤差；手腕至多輔助球桿身份關聯。

### 4.2 追蹤流程

1. 選擇 R3 單球時間窗，從 segment start 前後做 configurable padding（例如 200–400ms，**必須不超出原片**），取得 Top 與 Impact 錨點。
2. 讀取高解析 source，進行 upright 幾何及 camera motion 評估；可使用姿勢骨架建立近手/桿附近寬鬆 ROI。
3. 检测 club head、shaft（segmentation/mask 或 bounding box＋line candidates）；確保 `club_head` 與 `hands` 分類獨立。
4. 多候選關聯：時間、速度、方向、球桿長度近似範圍、hand grip 的合理距離（非速度估計）；混合人／旁觀者等候選不得接到同一軌跡。
5. 以有界的 Kalman / optical flow 填 gap；短暫遮擋標記；超過 Gap Gate 不得跨畫面直接畫實線、要斷線或用虛線預測。
6. 使用已有 event Top/Impact：`backswing` from takeaway to Top、`downswing` Top to Impact、`follow_through` Impact to finish；邊界誤差／缺失時標暫定，允許手動校正。
7. 先在**同一影像投影平面**建立曲線與可視化；指標限制為平面路徑包絡、投影軌跡相對差異、相同相機設定下 head path overlay，不能解釋成 3D 球路。
8. 低信心時讓使用者更正 1–N 影格的桿頭、shaft endpoint，從修正錨點重算局部 track；raw detector 永遠保留不變。

### 4.3 桿頭品質門檻

- `accepted observed` = 真正 clubhead 影像證據而非 wrist/shaft；`shaft_geometry_estimated` 必須計入另一 coverage，不可混為一談。
- 每個 segment 回報 direct_observation_coverage、geometry_assisted_coverage、manual_coverage、largest_gap_ms、confidence_distribution、uncertainty_px、end-to-end eligibility。
- 最嚴格的 `AUTO_TRACED` 只用可驗證的 direct/limited geometry evidence；若 gap 過長或 model wrong object → `NEEDS_REVIEW`，不出完整假的實線。
- 不因平滑使線好看而壓平真實加減速轉折；資料層 raw 路徑與效果層 smooth 可隨時切換。

### 4.4 Swing Tracer 設計選項

- 開關 `Show path`／`Show head marker`／`Show shaft detected`／`Show ghost overlay`。
- 上桿色（預設 Cyan）、下桿色（Amber）、隨揮色（Purple）；不同 phase 用對應確切 PTS 切分。
- `trail_decay_ms`／`line_width_px`／`interpolation_style`／`glow_radius_px`／`dash_style`／`smoothing`／`confidence_visualization`。
- 同畫面比較兩次 swing 時，只有相同有效坐標條件（機位、crop、影像形狀）可疊圖比較；否則要求人工對齊或標注 `NOT_COMPARABLE`。

---

## 5. Shot Tracer — 真實高爾夫球追蹤與人工可救援流程

### 5.1 使用既有演算法，不覆蓋其語意

現有 `GolfBallDetector` + `KalmanBallTracker` 可做 detection adapter/reference baseline，但既有 scanner 中它還負責輔助 Impact Refinement。Studio 新流程應：

- 只讀 `SwingSegment` 與 `SwingEvent`，獨立生成 Tracer Track；不得為了特效反向更改打球評分。
- 先讀原片高解析 ROI，確認 stationary ball → motion onset → airborne evidence；禁止將靜止球或鞋帶、白燈錯認為飛行球。
- ROI 自擊球球位向 **左、右、上方多方向**擴展，必要時用已測到的初始 motion vector 動態調整；不得簡單永遠右擴。
- 光流 `cv2.calcOpticalFlowPyrLK` 用局部連續特徵追蹤，對於高速小白球 pixel blur 需多候選、前後向一致性、光流殘差、背景動態過濾；光流僅作估計，沒有 detector evidence 不得變 observed。
- Kalman 轉移 `dt` 使用實際相鄰 PTS，不能只用影片名義 FPS；若無真實速度/世界尺標，不得加入偽造英里速度／完整物理彈道。
- Robust fit：RANSAC/Huber/medoid、加速度變化約束、前後向一致性、跨幀位置門檻。若動態場景不符簡單拋物線，不可強迫球落在漂亮拋物線上。
- 發生 loss-of-track 時先保留已觀測序列，短 gap 可以 `interpolated`，越界或長 gap `occluded`/`unobservable`；人工錨點後恢復追蹤而非一口氣幻想到落點。

### 5.2 模式定義（必須在 UI 中明確）

| Mode | 資料依據 | 可以顯示 | 禁止 |
|---|---|---|---|
| `AUTO_OBSERVED` | 直接影像球偵測與可解釋連續關聯 | 原始真球點，保守曲線 | 沒看到的點不標 observed |
| `AUTO_ASSISTED` | 部分直接觀測＋短 gap optical-flow/Kalman | 已觀測段實線；估計段虛線 | 高估可信度 |
| `MANUAL_ANCHORED` | 使用者手動選取真正可見球影格 | 修正錨點和已知人工 segment | 手動點宣稱為模型檢出 |
| `ARTISTIC_EXTENSION` | 使用者為影片美觀指定航線 | 動畫與清楚的推估／藝術化標識 | 假裝球實際飛到了該畫面位置 |
| `UNAVAILABLE` | 無足夠證據 | 明確告知不追蹤，讓使用者選擇人工 | 隨機畫一條漂亮弧線 |

`mode` 是作品語意，不是品質；同一 Track 可有多個 point source。若切換到藝術化，metadata 必須以 `artistic_only` 描述。

### 5.3 Flight truthfulness 技術細節

- 原影格上的球 bounding box、中心／半徑或小片 ROI、confidence、background rejection flags、選定球 identity 均可審核。
- 檢測與過濾採時間連續性：若連續差距超過設定 physical/motion gate（像素／時間，非米／秒），標 `TRACK_LOST`。
- 每段 track 具 `observed_range_pts`、`predicted_ranges`、`manual_anchor_count`、`accepted_status`、`confidence_reason`。
- 畫面上：實測實線、預測虛線（可選）、藝術化另色／小字；匯出作品 metadata 與旁邊 JSON 必留此資訊。
- 不基於未知軌跡畫落點、飛行距離、Spin 曲率；若要在藝術創作中做出勾球／小右曲，明確命名「自訂弧線特效」而非 shot shape measurement。
- 可以在缺乏可見球時讓使用者建立單純的 **FX animation**；這是創作功能，驗收歸 FX，不算自動 Shot Tracer pass。

### 5.4 光流與重定位模型選型

- **V1 首選**：既有 OpenCV（稀疏 LK 光流 + Kalman）和現有球 detector；足夠時局部重辨識。
- **V2 候選**：Norfair (BSD-3-Clause) 可用於同一顆球的 data association，但單目標不必為了流行而重構；性能證據不佳就不用。
- **V2 候選**：SAM2 (Apache-2.0) 經手動錨點追蹤影片 mask；小白球可能太小，需經 30/60/120fps 真實素材測試，未測不能稱可用。
- **技術對照**：`jonibek95/GolfShotTracer` 以 YOLOv5 與物理模擬疊出弧線，可借鑑畫圖演示與 pipeline，但其「估計 3D 球路」不適合直接納入本產品真實追蹤；**需要先查實際 LICENSE**，未確認則不可複製程式或權重。

---

## 6. Flight FX：預覽與正式匯出必須同源

### 6.1 Canonical render recipe

追蹤數據與效果分離，使用 `render_recipe v1`，至少：

```json
{
  "schema_version": 1,
  "project_id": "uuid",
  "track_revision_ids": ["uuid-for-swing", "uuid-for-shot"],
  "anchor_revision_id": "uuid",
  "timeline": {"start_pts_us": 10000000, "end_pts_us": 14200000},
  "layers": [
    {
      "id": "swing-main", "kind": "swing", "enabled": true,
      "style": {"type": "neon", "width_px_at_1080": 5, "colors": {"backswing":"#34D6FF","downswing":"#FFB45D"}, "glow": 0.6, "trail_ms": 450}
    },
    {
      "id": "shot-main", "kind": "shot", "enabled": true,
      "style": {"type":"beam", "width_px_at_1080":4, "color":"#EBFF8D", "glow":0.8, "trail_ms":1200},
      "estimated_style": {"dash": [8,5], "opacity": 0.45, "show_disclaimer": true}
    }
  ],
  "export": {"aspect_ratio": "9:16", "fps": 60, "crop_mode":"contain", "quality":"high", "audio":"preserve"}
}
```

- 版本化 JSON schema + Pydantic + TS 同步產生型別，保存任何使用者可調參數。
- `line_width_px_at_1080` 指可理解的參考尺寸：轉換成輸出實際畫素比例，不要 4K 和 720p 顯示完全不同視覺效果。
- 所有 easing、glow、beam tail 以**source/canonical timeline time**為依據，而非依賴 `requestAnimationFrame` 呼叫次數（會因 UI 掉幀而漂移）。

### 6.2 共同渲染核心建議

**首選**：Python 以 OpenCV / NumPy rasterize transparent RGBA overlay（可選 Pillow blur/glow），同一個純函式 `render_overlay_at_pts(recipe, tracks, pts_us, dimensions)`：

- UI 預覽：FastAPI 提供 `GET /api/tracer/projects/{id}/preview-frame?pts_us=...` 可取精確疊圖／縮圖；前端日常播放可用 TS/Canvas／Konva 的可互動近似版本（需通過 golden parity），必要時以 Python render API 作 truth preview。
- 正式匯出：同一 Python renderer 生成 overlay，疊 FFmpeg 解碼/編碼影格；與 Canvas 預覽同配方／函數意義。
- 若跨語言 renderer 做不到 pixel-perfect，則 golden test 至少確保位置、PTS、狀態/顏色/開關等價；若差異超限，以 Python renderer 預覽產出作權威。
- FX 的 Glow 可用 Gaussian alpha bloom，避免 OpenCV BGR/RGB 混色錯誤與 alpha 預乘邊緣黑框；每張 overlay 背景應 alpha 0。
- Glow/Beam/Gradient 的幾何始終受 track validity 控制；不能因特效平滑產生跨 occlusion 的假實線。
- R3 原有無特效匯出仍經原 legacy pipeline；新 Studio `no_fx` 以獨立驗收比對原片時序、音訊政策及裁切，不得偷偷額外畫線。

### 6.3 特效規格（最低必備）

| 效果 | 參數 | 動畫行為 | 技術風險 |
|---|---|---|---|
| Clean | 線寬、顏色、透明度、dash | 按時間逐步呈現／尾跡 | 端點 aliasing |
| Neon | glow radius, intensity, core width, tint | 亮芯、霓虹外暈 | bloom 溢色 |
| Beam | 尖端亮度、尾端收束、厚度 | head 隨時間移動 | 插值過衝 |
| Gradient | 2–4 色停點、循路徑漸層 | 累積色彩與 time fade | 順序不穩 |
| Tail | 衰退時間 50–3000ms、曲線 | 顯示 trailing path | 低 FPS 拖影斷裂 |
| Pulse | pulse period、半徑、亮度 | 以 PTS 可重現閃動 | 閃爍舒適度 |

支持 Swing + Shot 雙層混合／個別開關／疊圖順序／根據 top/impact 動畫觸發；相同 recipe 在不同 FPS 應得到**相同時間點**的位置，不得使用逐幀位置常數累積。

### 6.4 影音匯出

- **比例**：原始比例 `original`、16:9（1920×1080 或合理選擇）、9:16（1080×1920）、等比例調整；低資源模式可 720p。
- **幀率**：30／60fps CFR。若原檔是 29.97/59.94 或 VFR，使用 PTS 時間域重採樣。60fps 從 30fps 源只能 repeat/interpolate（預設 repeat），**不得聲稱真實 60fps 運動細節**。
- **編碼**：預設 H.264 `yuv420p` `.mp4` + `faststart`，必要時 HEVC 視 Mac 支援；保留音訊可選，原音訊對齊不許錯位；concat 前先統一 profile/fps/timebase/pixel format。
- **精準切片**：重編碼 frame-accurate trim，不以輸入快速 keyframe seek 的誤差作為最終時間；驗證第一/最後含效果的影格與 Impact ± 1 輸出 frame 內一致。
- **可取消／恢復**：渲染階段至少 segment 級 checkpoint，暫存檔 atomic rename；失敗時不能把不完整 mp4 標 completed。
- **產物**：MP4 + sidecar `*.tracer.json`（含 hash, source IDs, model version, provenance, quality, recipe, render stats）；簡短可視 Demo、contact sheets、failure clips。

---

## 7. 資料模型、交易安全與遷移

建議以**新資料表**為主，避免把長度數萬格的 JSON 塞進 `SwingSegment`。

### 7.1 最少資料表（名稱可依 ORM 慣例調整）

| Table | 重要欄位 | 目的 |
|---|---|---|
| `tracer_projects` | id, owner_id, session_id, video_id, segment_id, name, status, created_at, updated_at, row_version | 一球/工作區入口；可收藏多版本 |
| `tracer_jobs` | id, owner_id, project_id, job_type, status, progress, attempt, heartbeat, cancel_requested, input_hash, error_code, error_detail, started/finished | 追蹤與渲染獨立工作排程 |
| `tracer_track_revisions` | id, project_id, track_kind, revision_no, model_sha, algorithm_version, source_video_sha, geometry_version, source_pts_span, status, stats_json, points_storage_key, derived_from | Immutable 逐點軌跡版本 |
| `tracer_manual_edits` | id, track_revision_id, owner_id, pts_us, point_before, point_after, operation, edit_source, created_at | 編輯稽核與 Undo/Redo |
| `tracer_anchor_revisions` | id, project_id, top_pts_us, impact_pts_us, anchor_sources_json, confidence, active, created_at | 只影響 Studio 的時間點修正 |
| `tracer_render_recipes` | id, project_id, version, revision, recipe_json, recipe_sha, is_default, created_at | 非破壞式特效樣式 |
| `tracer_export_jobs` | id, owner_id, project_ids_json / selected_segments_json, recipe_hash, status, output_key, sidecar_key, format, fps, layout, duration, errors, created_at | 專用輸出，保留舊 exports |
| `tracer_model_registry` | id, name, version, sha256, license, local_path, availability, enabled, notes | 本地權重／合法來源／相容性 |

### 7.2 大量軌跡資料存放

- 建議 raw detection/track points 以 **有 schema 的壓縮 JSONL/Parquet** 存 Local/S3/Hybrid 物件儲存，DB 僅存 revision、hash、storage key、索引和統計；一個 30 分鐘 session 的每球軌跡不可都塞 DB JSON 欄位。
- 若需單格 edit 精準索引，可另 `tracer_point_edits` 表，但必須有 `track_revision_id + pts_us + operation_seq` 唯一／複合索引；禁止無限制 row per frame 污染主資料庫。
- 原始偵測點 append-only；manual revisions 以 copy-on-write 產生生效結果；每次編輯有來源、時間、操作人、base revision，支援 optimistic concurrency (`If-Match`／version) 防覆蓋。
- Media asset `storage_key` 必須由現有 `get_storage_service()` 產生與存取，避免自行拼絕對路徑造成 MinIO 舊資料遺失。
- foreign key owner / project / segment must verify ownership on every read/write/export; 不允許跨 user_id 讀取影片或下載他人輸出。單人 App 也須保留安全界線。
- 資料表／foreign key 使用 existing SQLAlchemy Base 和 Alembic；任何 schema 變動都寫 migration + test，不在 API 啟動時偷偷 `drop_all`、`create_all` 當正式遷移。

### 7.3 版本一致性、不重複分析與失效策略

`source_fingerprint = sha256(video_sha256 + segment start/end + PTS clock_version + geometry_version + anchor_rev + model_sha + tracking parameters)`。

- 只變 FX 样式：保留 `tracer_track_revision`；只更新 recipe；直接 preview/export。
- 修改手動點：產生新的 derived track revision；不重跑全片模型。
- 修改 Impact：只對相關局部窗口重新定位/追蹤，既有 raw detections 可 cache；R3 Score 不更新。
- 上傳相同影片不自動刪除已有作品；相同 job request 可回 existing result（idempotency_key + payload hash）；不同人/不同 clip 的同鍵不共用結果。
- job 失敗可 retry 且不生成重複完成紀錄，半成品有 TTL/garbage collection，永不刪使用者原片。

---

## 8. API 契約（建議最小充分集合）

保持既有端點原狀，新增 `/api/tracer/*`，Pydantic request/response + OpenAPI + 前端 TS type parity。

| Method | Path | 請求／語意 |
|---|---|---|
| `POST` | `/api/tracer/projects` | `segment_id` + name，建立 Studio 專案／原片可用性檢查 |
| `GET` | `/api/tracer/projects/{id}` | 回傳 clip/video context、anchor、tracks、recipe、quality |
| `GET` | `/api/tracer/projects?session_id=` | 當場所有作品、完成度、追蹤品質 |
| `POST` | `/api/tracer/projects/{id}/analyze` | `track_types=[club_head,ball]`、model options、idempotency key，enqueue |
| `GET` | `/api/tracer/jobs/{job_id}` | state/stage/progress/ETA 不捏造／error/diagnostics |
| `POST` | `/api/tracer/jobs/{job_id}/cancel` | best-effort cancel，確認實際 ack |
| `POST` | `/api/tracer/jobs/{job_id}/retry` | retry failed/cancelled with canonical fingerprint |
| `GET` | `/api/tracer/projects/{id}/tracks` | revisions, coverage, status, provenance summary |
| `GET` | `/api/tracer/tracks/{revision_id}/points?from_pts_us=&to_pts_us=` | 分頁/範圍讀點，最大回應大小限定 |
| `POST` | `/api/tracer/tracks/{id}/edits` | 手動點新增/移動/刪除、基準版本、幂等 |
| `POST` | `/api/tracer/projects/{id}/anchors` | Tracer-local impact/top override，保存 revision |
| `PUT` | `/api/tracer/projects/{id}/recipe` | FX schema validated、版本檢查 |
| `GET` | `/api/tracer/projects/{id}/preview-frame` | `pts_us` + output format/crop，回 frame/overlay、可 cache |
| `POST` | `/api/tracer/exports` | 多球 project_ids、recipe refs 或 per-clip recipe、aspect/fps/audio |
| `GET` | `/api/tracer/exports/{id}` | 狀態、progress、failure reasons、quality report |
| `GET` | `/api/tracer/exports/{id}/download` | auth / Range / correct MIME；不可暴露系統檔案 |
| `GET` | `/api/tracer/models/status` | 權重存在、license、hash、MPS/CPU availability |
| `GET` | `/api/tracer/health` | 各管線 dependency 可用性，未下載模型回 blocked 而非假 ready |

### 8.1 安全規定

- 新 API 套現有 `get_current_user` 和 `verify_owner`；所有 model/recipe/pts/clip bounds 輸入做嚴格欄位驗證。
- 防 prompt injection/檔名注入/路徑穿越：FFmpeg 指令以 array 執行、不可 shell interpolation；storage key 受 prefix 路徑限制。
- 防 OOM／DoS：單 clip 長度限制、點數限制、FX 參數範圍、export 時數和數量上限；暫存容量不足時 fail-fast。
- 自訂顏色使用 regex `^#[0-9a-fA-F]{6}$` 或 RGBA schema；JavaScript 前端 sanitize，後端驗證，不能允許任意 script。
- API 不應把帶授權內容的本機影片上傳給新外部 AI 服務；以 config/LLM guard 實測在 no-network 環境仍可用。

---

## 9. Worker、效能、記憶體與本機部署

### 9.1 Job 狀態機

`queued → preparing → detecting → associating → reviewing_required|ready → rendering → finalizing → completed`；任何 active state → `cancel_requested → cancelled` 或 `failed`。允許 `partial` 追蹤成果但不可標「自動已完成」。Job 日誌須具 `task_id`、`segment_id`、`stage`、elapsed_ms、CPU/GPU/peak RSS、input hash、artifact hashes。

### 9.2 Queue

- `gsl-analysis`：原本長片切球/評分，不改核心。
- `gsl-tracer`：只處理選定 clip；可配額；模型載入共享但需 thread safety。
- `gsl-exports`：繼續支援 legacy，另以 export kind routing Studio jobs；單機 CPU/VRAM 互斥，避免多個 4K job 同時爆 RAM。
- 若現有 inline fallback 適用 Studio，必須提供明確上限、取消與 HTTP 不阻塞保護；不建議長耗時渲染直接放在 FastAPI request thread。

### 9.3 本機模型與加速

- Prioritize Apple Silicon `mps` if dependency validated; fallback CPU，無 GPU 不得壞掉，不能聲稱 MPS 可用但實際 backend error。
- 每個模型 `model_registry` 綁 SHA、來源 URL、檔案大小、授權、下載權限；禁止背景靜默下載巨大模型或外傳影片。用戶需明示選擇離線安裝或模型檔來源。
- 逐 clip 視需求載入模型；研究能否使用 shared process pool，但保持 reproducibility；模型不同結果版號須新 revision。
- 建議設定 CPU threads、RAM budget、temp disk budget、max 1 tracer GPU worker，並用壓力測試調整，不硬宣稱任意 Mac 都能 30 分鐘即時處理。

### 9.4 安裝安全

- 先理解 `launcher.c`、`app.py`、WebKit 與用戶安裝方式；驗證模型權重路徑、`ffmpeg/ffprobe` 可用性、Python venv 被 launcher 找到，不能只在 VS Code terminal 成功。
- `scripts/build_mac_app.sh` 需把危險 `rm -rf` 變安全可回復安裝：檢查 bundle id、來源/目標、備份旧 App、atomic replace、rollback、禁止刪除桌面同名資料夾，除非明確確定為舊 app bundle 且備份完成。
- `~/.golfswinglab/storage`、PostgreSQL DB volume、MinIO 物件與所有用戶匯出不得被安裝腳本清理。
- Mac packager 不可將有版權爭議的第三方高爾夫影片、私有測試素材、AGPL 模型（尚未完成授權評估）直接提交 Github 或打包再散布。

---

## 10. 分階段實作，但一次連續執行（不需要中途逐輪批准）

### Phase 0 — Read-only baseline / golden snapshot（沒有通過不得開始大改）

- 查看 `origin/main`、PR #3 合併記錄、commit；`git status` 應乾淨；建立 `feat/r4-golf-tracer-studio`。
- 完整盤點 Backend/Frontend/Worker/DB/Storage/Mac launcher；產出 `docs/r4/BASELINE_AUDIT.md`（路徑、函式、現況與風險）。
- 備份資料庫與媒體（或檔案指紋＋備份驗證）；記錄至少幾支真實影片可用，沒有就列 blocker。
- 執行 R3 tests + `npm build` + existing WebKit tests，紀錄真實結果。已知歷史 135 tests 不是新 Session 可直接宣稱的 baseline。

### Phase 1 — Data/API/Editor/Manual MVP

- 建立 schema + migration + trace source type + time/geometry contracts。
- Studio Projects、Tracks/Edits/Recipe APIs，完整權限／回滾／revision 測試。
- 前端非破壞性逐格編輯器、手動點、undo/redo、影格與時間碼校正；先能製作 **Manual-assisted** path，不依賴模型。
- 交付 golden source/preview transform tests；手動點移動能即時重繪，關閉重開仍存在。

### Phase 2 — Swing Tracer

- 审核 club head 模型／授權／權重；實作 adapter、shaft geometry fallback、來源標籤與 confidence。
- 兩段/三段分色與事件錨點；遮擋/快速揮桿/左右手/30 vs 60/120fps 矩陣。
- 與人工 correction 接合；超出品質門檻不給 AUTO_TRACED；輸出可單獨測。
- 若沒有合法權重／真實標註，停在 `BLOCKED_SWING_AUTO`，不可用手腕取代。

### Phase 3 — Shot Tracer

- 既有 ball detector adapter、dual-direction ROI、局部 optical flow、PTS-aware Kalman、outlier rejection、occlusion/gap semantics。
- 高解析真球 ROI、逐點 provenance、Confidence gating；manual keyframes 有資料庫版本與局部重算。
- 至少自動／人工／純藝術化三種失敗案例都能正確標示。
- 累積真實影片對照、訓練/驗證資料**按拍攝場次/人物分離**，防止 train-test leakage。

### Phase 4 — FX / Export / Batch / Mac

- 建 deterministic renderer／前後端共同 recipe、6 效果／雙層／樣式預設。
- 原片與 FX 的可重複 30/60fps、3 比例、音訊政策、concat、下載；舊無 FX export 不能回退。
- 大量場次逐球候選→批次套用 presets→挑最佳→合輯，queue 取消/重試/復原。
- 完整 Mac App 打包與端到端 GUI 測試，保留資料與可回滾發行。

### Phase 5 — Independent red-team QA / 修復迴圈／Draft PR

- 自動測試＋實拍素材、量測誤差、preview/export golden frames 與失敗回放。
- 由獨立 QA 角色/子代理站在「使用者、電腦視覺工程師、影像編碼工程師、資安與資料庫管理員」重新審查並修補。
- 每次 `FAIL` 修復後重跑對應專項＋R3 全套回歸；記錄 fail→fix→rerun，直到全部 PASS 或合理真實外部阻擋（模型/測試素材/OS 不可用）。
- 提交**獨立 Draft PR**；禁止默默升級到 ready-for-review／合併 `main`。如所有 Gates 全通過，可在 PR 報告註記 `READY_FOR_OWNER_REVIEW`，仍維持 Draft 等候主人授權。

---

## 11. 驗收體系：不准輕易 PASS

> 下列屬於**R4 設計目標與驗收門檻，不是現階段已達成的實測結果**。數值採在固定標註集上可重現的初始嚴格標準；實作中若發現不可達，不可偷偷調降並宣稱通過，應揭露樣本/設備/物理不可觀測性，提改善方案與 FAIL/BLOCKED。

### 11.1 真實影片樣本最低集

- **至少 24 個互不重複的真實 swing clips**，涵蓋 >=6 支 30fps、>=6 支 60fps、>=3 支 >=120fps（如設備沒有高幀率樣本，必須標 NOT_RUN/BLOCKED）、>=4 左手、>=4 右手、>=5 球體消失、>=5 背景干擾、>=5 桿身遮擋/模糊；一支影片可覆蓋多個分類，但每個要求需可查證。
- **至少 3 支完整 10–30 分鐘原始影片**跑逐球批次/取消/重試/合輯流程；至少一支 VFR／旋轉 metadata 和一支 HEVC/MOV。如沒有 3 支可用，不得聲稱 batch long-video 已 full PASS。
- 人工標註：impact pts、clubhead visible center（每個可見格或合理抽樣＋所有高速區間）、球 visible centers、occluded segments、flight last-observed frame；至少 2 人交叉複核一部分樣本並紀錄分歧。
- 以 session/person/day 為隔離單位切分開發／驗收集；不得用同一影片相近格分拆 train/val/test 造成假高準確率。
- 不允許私人影片自動 push 至 GitHub、PR attachments 或公開 CDN；提交 checksum／脫敏統計與獲同意可分享的示範影片即可。真實影片可留在本機。

### 11.2 核心 CV 品質指標（量測口徑）

先對每張可觀測、人工標註的影格以「原片直立後 1080px 寬度等比標準化」計算 pixel error；P50/P95 只對匹配的**直接偵測點**計算；coverage 另計。不得用 100% 人工修正結果冒充模型 accuracy。

| Gate | 嚴格驗收目標 | 失敗標準 |
|---|---|---|
| SW-1 真桿頭辨識 | 自動 accepted **direct observed 點** precision ≥ 0.95；P50 ≤ 12px、P95 ≤ 28px；軌跡中 0 個 wrist-as-head 冒充案例 | 桿頭變成手腕、接錯球桿、無真實 evidence 或 >容許偏差 |
| SW-2 追蹤可用性 | 在可見／適用且品質合格的樣本中，≥ 80% clips 能產生可審核的部分或完整高信心路徑；不足可拒絕，但不得畫假線 | 只在一支漂亮測試片成功、未分 source/估計 |
| SW-3 phase | Top/Impact 相位斷點對 R3 event 的絕對時間差 ≤ 1 source frame（manual override另測）；每點 phase 正確 | 上下桿顏色交錯或時鐘漂移 |
| SH-1 真球偵測 | accepted observed 球點 precision ≥ 0.95；P50 ≤ 10px、P95 ≤ 25px；真/假軌跡分離 | 白燈/招牌/鞋面誤連成 flying ball |
| SH-2 軌跡誠信 | 在 no-ball/no-launch/ball invisible 失敗組**0 件**宣稱自動已完整追蹤；所有 predicted/interpolated/manual/source_type 正確 | 缺影格仍標 `observed` 或暗中延伸成全程 |
| SH-3 左右手與遮擋 | 左、右 hand 的相同可觀測條件下都能產生追蹤或正確回報失敗；無固定向右偏差；高 blur 超門檻需標 needs_review | 左打者完全無可用候選、沒有 fallback/說明 |
| MANUAL-1 編輯 | 點擊／拖動點位最大誤差 ≤ 2px（當下顯示座標）、經儲存重開位置一致；Undo/Redo 100% | 編輯消失／污染原始 detector points |
| MANUAL-2 Impact | Studio anchor 修改不更動既有 `SwingEvent`、`SwingScore`、Pose、18 reference records，除非另有明確核准 | R3 分數因製作特效改變 |

**關於 SW-2**：coverage/成功率不能以任意挑選最簡單片段作分母。須同時報全樣本、可觀測子樣本及每個失敗子群；非自動成功案例必須顯示降級狀態。不能靠改成「只通過可見影格」來逃避 `AUTO` 覆蓋率。

### 11.3 畫質／時序／輸出

| Gate | 要求 |
|---|---|
| MEDIA-1 PTS | 24/25/29.97/30/59.94/60/120fps 與 VFR 的源時間碼一致，無因 `frame_index/fps` 引入累積漂移；檢測到不可靠 PTS 需 fail closed |
| MEDIA-2 Rotation | 0/90/180/270 度與 portrait/landscape 畫面中的球/桿頭點位置一致，零二次旋轉；source→display→crop→output 反向對照誤差 ≤ 1px（純幾何 fixture） |
| MEDIA-3 Preview ↔ Export | 在 ≥20 個指定 PTS 的對應輸出影格，軌跡中心位置誤差 ≤2px@1080p（不含編碼容差），顯示／消失誤差 ≤1 個輸出 frame；每個 phase 色彩/圖層相符 |
| MEDIA-4 Output profiles | original/16:9/9:16 × 30/60fps × no_fx/Swing/Shot/Both 全矩陣測至少 24 種組合；ffprobe 視訊 playable、duration、pixel format、audio policy、非黑畫面 |
| MEDIA-5 60fps honesty | 30fps 原素材轉 60fps 要標 output resampling/repeated frames，不得聲稱真實升格球軌新資訊 |
| MEDIA-6 Pure export | `no_fx` 的舊 pipeline 保持能成功，首/尾、音訊政策、解析度未意外改變；新 `no_fx` 無 tracer 像素疊圖 |
| MEDIA-7 Concat | 至少 1/2/3/5/10 clips 合輯（新 Studio 上限依正式測試定），段落順序、FPS、audio/PTS、畫面不黑、不跳段；跨不同比例 source 可正常 compose |
| MEDIA-8 Audio | preserve/mute 兩種模式 A/V 偏差 ≤100ms，音訊不存在時優雅處理；背景聲音不越界至其他 clip |

### 11.4 批次／效能／可靠性

| Gate | 要求 |
|---|---|
| JOB-1 長片 | 三支 10–30 分鐘真影片完整 import→既有切球→逐球選取→部分/批次 Tracer→合輯輸出，未重跑整片無關 swing |
| JOB-2 消耗 | 在使用者 Mac 記錄峰值 RSS、CPU/GPU、磁碟暫存與每球耗時；不得在沒有 benchmark 的情況捏造效率改善；>=1 次記憶體壓力／磁碟不足故障注入 |
| JOB-3 Retry/Cancel | queue/processing/export stages 可 cancel；restart/retry 後不重複產物、不丟人工點、不把失敗標 completed；>=1 次 forced crash/resume |
| JOB-4 Offline | 阻斷網路、沒有新的雲 API Key，功能依已安裝本機模型正常；若模型未安裝自動模式明確 BLOCKED、人工模式與 FX 照常 |
| JOB-5 Ownership/Security | 401/403/404、越權存取、擅改 storage key、惡意 JSON 參數、SQL injection、FFmpeg argument injection 測試全過 |
| MAC-1 Native App | `/Applications/Golf Swing Lab.app` 真實啟動、Studio UI／播放／編輯／模型推論／匯出全通，不只 `localhost` web 頁面 |
| MAC-2 Data Integrity | 原 18 references、已有 media、sessions、scores、favorites、原本雙球 player 未被刪除或擅改；有備份/恢復驗證 |
| REG-1 R3 | 所有已存在 pytest、Vitest/TS build、R3 WebKit acceptance 綠燈；任何既有用例退化 = FAIL |

### 11.5 最低自動化測試組合

- Python Unit：frame PTS、旋轉、crop/coordinate round trip、source type invariants、Kalman dt、光流殘差、outlier rejection、phase classification、FX render deterministic。
- Python Integration：Postgres migration、auth/ownership、Studio routes、Local/MinIO HybridStorage、RQ enqueue/job status/cancel/retry、export recipes、多 clip concat、R3 originals unchanged。
- TS Unit/UI：Canvas click-to-source coordinate、frame stepping、Undo/Redo、autosave conflicts、type contracts、confidence/estimated legend、color/both toggle、lost-track empty state。
- E2E/WebKit：從 R3 session 中選擇某球→自動追蹤→人工修正→FX 設定→正式 MP4 download→ffprobe 解析→對照同 PTS screenshot；包含左手與失敗情境。
- Golden：各類 synthetic deterministic fixtures（單元與 invariant）；real clips（auto CV accuracy & experience），二者不能互相替代。
- Security：跨 owner 輸出下載、prefix traversal、未授權讀寫／點位 XSS/DoS、外部網路 egress fail-closed。
- Model availability：有模型與無模型兩套路徑，均有 test；無合法/可用權重不可以 `AUTO_TRACED` 回假資料。

### 11.6 交付報告一定要揭露的失敗案例

每個失敗案例必須帶：source clip hash、輸入條件、PTS 範圍、期待 vs 實際、功能是否自動/人工/藝術化、錯誤截圖/短影片（注意隱私）、判定、根因、修復 commit 或待修阻擋，以及下一個可執行動作。

成功案例：上桿/下桿雙色、可見球軌、雙層 Neon、60fps 9:16、original 無特效、2–3 球 IG 合輯。  
失敗案例：球在 Impact 後立即看不見、背景燈誤認球、桿身遮住桿頭、左手球員、晃動鏡頭、低 FPS、VFR metadata、素材遺失、模型缺席、磁碟滿、取消任務。

**不可用「全套程式碼可編譯」「展示影片漂亮」「合成畫面通過」代替上述實際驗證。**

---

## 12. 開源專案研究／授權／採用策略（截至 2026-10-31）

> 研究來源詳見同交付包 `GITHUB_OPEN_SOURCE_RESEARCH.md`；**授權為當時查到的狀態，真正下載／整合前需複核每個特定 commit、權重及其資料集的權利**。

| 項目 | GitHub | 驗證到的用途 | 授權與導入決策 |
|---|---|---|---|
| SwingTrace | https://github.com/nishsm/golf-club-detection-swingtrace | 專用 club head/shaft/hands YOLO11m，path reconstruction；最佳直接參考 | AGPL-3.0，HF gated access；**研究／原型優先，合規後才整合** |
| SwingTrace weights | https://huggingface.co/nishsm/golf-club-detection-swingtrace | 約 40MB model，作者自報 unseen-video coverage | AGPL-3.0；確認可下載及使用條款，不自動打包公開 |
| GolfShotTracer | https://github.com/jonibek95/GolfShotTracer | golf ball YOLO + 3D 物理模擬與畫線展示 | 參考演算法，**禁止將模擬軌跡冒充真實**；LICENSE 待複核 |
| OpenCV | https://github.com/opencv/opencv | LK optical flow、Kalman、RANSAC、RGBA raster | OpenCV 4.5+ Apache-2.0；現有依賴，主力 |
| Norfair | https://github.com/tryolabs/norfair | 追蹤 data association | BSD-3-Clause；可選（不要過度設計） |
| SAM 2 | https://github.com/facebookresearch/sam2 | prompted mask video propagation、手動點修正 | Apache-2.0；算力／體積評估後才用 |
| RF-DETR | https://github.com/roboflow/rf-detr | 自訓 permissive clubhead/ball detector 備選 | Nano–Large 與特定權重 Apache-2.0；Plus 型號特別授權，不能混用 |
| Konva | https://github.com/konvajs/konva | frame editor、drag points、lines | MIT；適合互動編輯器 |
| react-konva | https://github.com/konvajs/react-konva | React canvas adapter | MIT；需搭配 React 19 版本相容性確認 |
| PyAV | https://github.com/PyAV-Org/PyAV | 比 OpenCV 更精確的 FFmpeg PTS 解碼路徑候選 | BSD-3-Clause；Apple Silicon wheel/打包需實測 |
| FFmpeg | https://github.com/FFmpeg/FFmpeg | trim、overlay、encode、concat、ffprobe | LGPL/GPL 依 build；檢查 `libx264` 與再散布授權 |
| Editly | https://github.com/mifi/editly | 宣告式影片時間軸/轉場參考 | MIT；原生 headless-gl 相依可能很重，不是必選 |
| BoxMOT | https://github.com/mikel-brostrom/boxmot | 可參考可插拔 tracking 結構 | AGPL-3.0；本地單球場景先不導入龐大堆疊 |

### 12.1 授權/安全 Gate

- 純本機個人使用也須遵守適用授權；若未來開源、提供第三方下載或 SaaS，AGPL/FFmpeg/素材使用影響可能改變，需法律評估，不可自稱「個人使用就完全沒有授權要求」。
- 專用 YOLO 模型與 Ultralytics 是 AGPL 風險點；以 adapter 隔離，保留後續替換權重能力。
- 權重來源不能單憑 package license 推論，應分開記錄 **code license、weight license、training dataset license、download gated conditions、redistribution**。
- 不能把人像／球場／使用者自拍／無權再散布的示範影片提交到 public/private GitHub；私有 repo 不是內容授權的替代。

---

## 13. 現實阻擋、例外處理及誠信等級

### 13.1 自動追蹤成功的前提

影片的球頭／球體必須至少在足夠時間點存在可辨別影像資訊。對普通 30fps 手機影片，擊球後小球可能一兩格就消失，**無任何演算法可從不存在的觀測還原真正完整 3D 飛行軌跡**。因此「追蹤失敗→人工輔助／清楚標記 FX」是正確產品行為，不是 bug。誠信要求是 **拒絕假成功**，而不是所有素材 100% 自動畫出完整弧線。

### 13.2 必須停止全案 PASS 的情況

- 真實素材未能達驗收規模或沒有可信人工 ground truth。
- 專用桿頭模型下載受限、授權不明、或使用者裝置無法推論，且尚無實測替代。
- 逐格預覽與正式影片時間碼錯位超過門檻。
- 任何手動 edit 污染原 R3 事件／評分／原片。
- 在球體消失情況將幻想曲線標記為 `observed`。
- Mac App 包裝後功能不可用，而開發 Web 模式可用。
- R3 關鍵回歸失敗／資料庫遷移毀損／原始資料遺失。

### 13.3 工作輸出與證據層級

- **Level A**：本機原生 Mac App／實拍影片／人工標註／FFprobe/PTS/實際影格證據，附完整執行時間。
- **Level B**：整合測試、真 API、real storage、GUI E2E 的非假資料證據。
- **Level C**：unit test / synthetic fixture / mock；只能用於正確性局部驗證。
- **Level D**：設計描述／README／腳本存在但未執行；不算驗收成功。

報告要分每項使用的 level，不允許把 Level C 說成 Level A。

---

## 14. PR、文件與交付物格式

Gemini 必須在 repo 內提交至少：

```text
docs/r4/BASELINE_AUDIT.md
docs/r4/DEPENDENCY_LICENSES.md
docs/r4/IMPLEMENTATION_LOG.md
docs/r4/API_AND_DATA_CONTRACTS.md
docs/r4/TEST_MATRIX.md
docs/r4/REAL_MEDIA_EVALUATION.md
docs/r4/FAILURE_GALLERY.md
docs/r4/EXPORT_PARITY_REPORT.md
docs/r4/MAC_RELEASE_VERIFICATION.md
docs/r4/FINAL_DELIVERY_REPORT.md
```

由這份整合書作唯一產品需求來源。PR 必須 Draft，標題建議：`feat(r4): Golf Tracer Studio — clubhead, observed shot tracking, flight FX and native export`。

Final report 固定欄位：

- Base main SHA / Branch / Head SHA / PR URL / Diff summary / migration revisions。
- Swing Tracer 功能/自動品質/真實樣本數與失敗數。
- Shot Tracer 自動結果/手動結果/藝術效果明確分離；可信度校準與失敗案例。
- Flight FX 實測效果清單、Preview/Export parity。
- 運算/IO/Peak RAM/CPU-GPU/模型 hash/授權。
- R3 完整回歸結果/DB record counts before and after/備份證據。
- 30/60fps、原始/16:9/9:16、Single/Compilation、Mac Bundle 實際驗收。
- Red-team review P0/P1/P2 defects、修復 commit、重測結果及 **Remaining BLOCKED/FAIL**。
- Demo 影片（至少 swing path、observed ball、FX Both、failure/low-confidence、IG montage）；只在有授權時提供下載或 GitHub 產物。

**只有 QA matrix 100% 必要 gates PASS 才可標 `READY_FOR_OWNER_REVIEW`；仍不可自行 merge。**

---

## 15. Gemini 執行入口

在新的 Gemini 4 Argon Session 上傳以下三份即可：

1. 本文件：`GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md`（規格與驗收權威）
2. `GITHUB_OPEN_SOURCE_RESEARCH.md`（技術選型與開源證據）
3. `GEMINI_4_ARGON_MASTER_PROMPT.md`（自主實作命令）

`GEMINI_4_ARGON_MASTER_PROMPT.md` 明定：**先根據目前 `origin/main` 再核對一次本文件基準，接著一口氣完成所有可執行工程；不要每個 Phase 就停止、不要只交方案、不許假 PASS、不可自行合併 main。**

---

## 16. 來源與查核註記

### 本專案程式碼（2026-10-31 讀取）

- https://github.com/BDMisME/golf-swing-lab/tree/306de571d8b5983e3465432fb574112241148a5e
- `pyproject.toml`; `apps/web/package.json`; `apps/api/main.py`; `apps/api/models.py`; `apps/api/schemas.py`; `apps/api/config.py`; `apps/worker/tasks.py`; `apps/worker/main.py`; `packages/analysis/detection/scanner.py`; `packages/analysis/tracking/ball_tracker.py`; `packages/analysis/exporter.py`; `packages/analysis/probe.py`; `packages/storage/s3_client.py`; `scripts/build_mac_app.sh`。

### 外部技術與授權（2026-10-31 網路檢索）

- SwingTrace 作者模型卡：https://huggingface.co/nishsm/golf-club-detection-swingtrace
- OpenCV license：https://opencv.org/license/
- SAM2 project：https://ai.meta.com/research/sam2/ 、https://github.com/facebookresearch/sam2
- RF-DETR model/license：https://github.com/roboflow/rf-detr
- Konva / React-Konva：https://github.com/konvajs/konva 、https://github.com/konvajs/react-konva
- Norfair LICENSE：https://github.com/tryolabs/norfair/blob/master/LICENSE
- FFmpeg LICENSE：https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md
- PyAV packaging：https://github.com/PyAV-Org/PyAV
- GolfShotTracer：https://github.com/jonibek95/GolfShotTracer

**文件結束。**


<!-- END GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md -->

---


<!-- BEGIN GITHUB_OPEN_SOURCE_RESEARCH.md -->

# R4 — Golf Tracer Studio 開源研究與採用決策表

> 文件截至：2026-10-31。此文是 Gemini 4 Argon 開發的**起始研究，不是免查證引用許可**。任何下載、移植、打包前，必須比對特定 commit、LICENSE、模型權重來源、訓練資料集與依賴鏈。GitHub repo 是可供研究的候選，不等於可以在高爾夫專案直接跑通。

## 1. 評估原則

1. **已存在的 Golf Swing Lab 程式優先**。最直接且最低成本的路徑是擴充 `packages/analysis/tracking/ball_tracker.py`、`packages/analysis/detection/scanner.py`，在新的 Studio 專屬路徑中使用，不再拆掉現有評分／Impact feedback。
2. 不能拿單鏡頭 30fps 的 2D 影像聲稱 3D Carry、Spin 或球速精確量測；選源時特別排除依模擬出的漂亮全程飛行線冒充實際球軌。
3. 過度引入模型會造成 Mac App 安裝龐大、MPS 相容問題與版權風險。每新增 1 個外部依賴，必須先說明比已存在 OpenCV 做法的可測量增益。
4. 模型 weights 不能跟代碼混為一談；若無權下載或模型 gated，就將自動功能列阻擋，不能轉為假 detector。

## 2. 核心推薦選型

### A. `nishsm/golf-club-detection-swingtrace` — Swing Tracer 研究優先

- GitHub：https://github.com/nishsm/golf-club-detection-swingtrace
- 權重／模型卡：https://huggingface.co/nishsm/golf-club-detection-swingtrace
- 專案：YOLO11m，class 對應 shaft、club head、hands；提供盒框與重建桿頭路徑的程式。目標視角與使用者 DTL 固定手機拍攝高度相關。
- 作者公開結果（**非本專案實測**）：在 7 段未見過手機影片、3018 frames，直接 clubhead detection 71.6%，clubhead 或 shaft 93.4%。驗證集 mAP@50 0.918，但作者自己提醒訓練/驗證有相似相鄰影格洩漏，因此不可直接用作產品性能承諾。
- 缺陷：高速揮桿桿頭模糊、細亮條可能誤判球桿、shaft 近水平／垂直時從框的角推 head 失準；繪圖實作把整段影格放 RAM，不適合 30 分鐘影片，**只能對每球 clip 使用或重新做 streaming**。
- 授權：作者模型卡標示 AGPL-3.0（Ultralytics YOLO11）。權重在 HF 顯示 gated，要同意條件才可下載；不能假設安裝指令在無登入環境成功。
- 採用判定：`RESEARCH_FIRST`，完成 license gate、Mac MPS/CPU benchmark 和真實手機短片 head point audit 後，才可以做 production adapter。不可在未核准再散布規範前將 40MB 權重加入 Git LFS／發行包。
- 替代方案：自行使用 OpenCV 桿身線段＋端點估計並逐點標 `shaft_geometry_estimated`，或合法訓練 Apache-2.0 RF-DETR 模型；如不能取得可靠 clubhead 視覺模型，必須 `BLOCKED_SWING_AUTO`。

### B. `opencv/opencv` — 最優先利用現有依賴

- GitHub：https://github.com/opencv/opencv
- License：https://opencv.org/license/
- OpenCV 4.5+ Apache-2.0。現有套件 `opencv-python-headless` 已安裝；用 `calcOpticalFlowPyrLK`、KalmanFilter、RANSAC、homography、Canny/HoughLinesP、OpenCV RGBA drawing / Gaussian blur 就能做第一版。
- 必須用來源 PTS delta 更新 motion model；影像偵測 confidence 不代表 motion extrapolation confidence。需跟既有 `KalmanBallTracker` 對照，防止把經過平滑的座標誤貼 observed。
- 採用判定：`PRIMARY`。僅在真實 benchmark 看到關聯增益不足時才加入新 library。

### C. `tryolabs/norfair` — 多候選關聯／追蹤器可選

- GitHub：https://github.com/tryolabs/norfair
- License：https://github.com/tryolabs/norfair/blob/master/LICENSE（BSD-3-Clause）
- 用途：一個小白球從 detector candidates 中做時間關聯和 identity track；能幫忙處理不同類型的 detector。
- 注意：單顆球＋球桿的場景可能直接使用 OpenCV state tracker 更簡單，Norfair 未必能解決超小球消失問題。
- 採用判定：`OPTIONAL_MEASURED`。只有透過 ablation test 證明比現有 Kalman/data association 更好才導入。

### D. `facebookresearch/sam2` — 互動追蹤可研究，但非必要主流程

- GitHub：https://github.com/facebookresearch/sam2
- 產品研究：https://ai.meta.com/research/sam2/
- License：SAM2 code/weights Apache-2.0（依原始專案），個別資料集另確認。
- 能力：promptable frame point/box → video mask propagation；能讓人工點位提供次序追蹤。快速消失的小白球和薄桿身可能不足以可靠分割。
- 成本：需 Torch、模型權重、MPS 推論，包體與記憶體成本較高；必須 Apple Silicon 實測。
- 採用判定：`OPTIONAL_LATER`，只有在 real benchmark 明顯改善 manual-assisted recovery 時導入；主流程不可依賴。

### E. `roboflow/rf-detr` — 合法替代桿頭 detector 自訓基礎

- GitHub：https://github.com/roboflow/rf-detr
- License 詳情：https://roboflow.com/licensing（2026-10-27 更新）
- RF-DETR Nano–Large 的特定套件/模型權重為 Apache-2.0；Plus models（Atto/Femto/Pico/XL/2XL）另有 PML 授權，不能因為 package 名稱相同就宣稱全部 Apache。
- COCO 預訓練不是高爾夫 clubhead 專用 detector，**沒有專項訓練資料與訓練/驗證結果不等於可用**。
- 採用判定：`LEGAL_FALLBACK`。若 AGPL 有不被接受的未來發行風險且能取得合法標註資料，可選用進行 clubhead、shaft 兩類微調。要呈報實際训练成本、MPS 可用性和推論時間。

## 3. 畫面編輯與影音輸出

### F. `konvajs/konva` ＋ `konvajs/react-konva`

- Github：https://github.com/konvajs/konva ，https://github.com/konvajs/react-konva
- License：MIT。
- React Studio 用途：分層畫布、縮放/拖曳 point、Bezier handles、undo/redo 呈現、時間軸疊圖。畫面上的動畫以真實 source PTS 同步，不靠 requestAnimationFrame 跑過多少次推進時鐘。
- 版本注意：react-konva 最新相容 React 19 的 peer dependency 要依目前 `apps/web/package.json` 真實 React 版本選擇，不能誤安裝 incompat package。
- 採用判定：`LIKELY_UI_CHOICE`；若發現 WebKit 性能不穩，原生 Canvas + pointer events 可替代，核心 geometry 不變。

### G. `PyAV-Org/PyAV`

- GitHub：https://github.com/PyAV-Org/PyAV
- License：BSD-3-Clause（專案 pyproject 指定）；Python 3.12 新版支援。
- 用途：更直接使用 FFmpeg frame.pts/time_base 實現精準 VFR/HEVC/b-frame timing，避免 OpenCV `CAP_PROP_POS_MSEC` 偏差。
- 採用判定：`BENCHMARK_FIRST`，先用现有 FFprobe/FFmpeg 解碼證據再比較 PyAV；若包裝 Apple Silicon 依賴有問題，不能為了 PTS 讓整個 App 不能啟動。

### H. `FFmpeg/FFmpeg`

- GitHub：https://github.com/FFmpeg/FFmpeg
- License：https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md 、https://ffmpeg.org/legal.html
- 現有 exporter 已用 FFmpeg，主力編碼/trim/audio/concat。注意 FFmpeg build 有 LGPL 與 GPL 差別；`libx264` 會使完整 FFmpeg binary 的授權政策受到 GPL 影響，未來打包再散布需確認。
- 應做：使用 FFprobe 驗證 codec/fps/rotation/audio/duration；保持 FFmpeg command arguments array（禁止 shell 參數注入）；採 deterministic RGBA overlay pipeline。
- 採用判定：`PRIMARY_EXPORT`，無須引進雲端影片輸出服務。

### I. `mifi/editly`

- GitHub：https://github.com/mifi/editly
- License：MIT。
- 用途：研究宣告式影片/片段結構、轉場 API、疊圖 recipe 的設計思路。
- 缺點：Node + native headless GL 與 canvas 相依較複雜，macOS 單機打包可能增加故障面。
- 採用判定：`DESIGN_REFERENCE_ONLY`，除非能提出它比 existing Python/FFmpeg 更好的真實效能/簡化證據。

## 4. Golf Shot Tracer 參考，但不得冒用為真實觀測

### J. `jonibek95/GolfShotTracer`

- GitHub：https://github.com/jonibek95/GolfShotTracer
- 內容：YOLOv5 ball detection、初始速度與角度估計、3D 飛行物理模擬、曲線插值與 OpenCV 畫線。
- 長處：可參考 rendering/demo、使用者對 tracer 影片的表現期待。
- 致命差異：本產品只有單鏡頭影片，原始測量和後期模擬應分離，**不可把模擬物理球路直接當 observed flight**。
- License：本輪未確認完整 LICENSE 條款；**在核實前一律不得複製程式碼或模型**。
- 採用判定：`VISUAL_IDEA_ONLY`。

### K. `mikel-brostrom/boxmot`

- GitHub：https://github.com/mikel-brostrom/boxmot
- License：AGPL-3.0。具備各類 MOT algorithms、可插拔 tracker 架構，但明顯超出單球個人 app 所需。
- 採用判定：`ARCHITECTURAL_REFERENCE_ONLY`。不要為了有開源套件就把大量 ReID/torch stack 加進來。

## 5. 依優先序的組合推薦

```text
P0 必要:
  Existing Golf Swing Lab (R3) + OpenCV + FFprobe/FFmpeg + local FastAPI + Postgres
P1 推薦:
  Konva + react-konva for frame-by-frame correction editor
P1 Swing 檢驗:
  SwingTrace YOLO11m as isolated, license-reviewed prototype adapter
P2 若已證實較佳:
  Norfair for association / PyAV for PTS / SAM2 for promptable correction
P2 合法模型替代:
  RF-DETR Apache-designated weights + legitimate separately labeled dataset
不建議直接主線整合:
  GolfShotTracer 的 3D 模擬球路；BoxMOT 的大型 tracker stack；任何未知 LICENSE 模型
```

## 6. Gemini 開發前要實際跑的 License / Feasibility Checklist

- [ ] 記錄依賴 git commit/tag 和下載日期，而非 `pip install git+main` 漂浮依賴。
- [ ] 打開真正 LICENSE 與 NOTICE，查 license scope（code / weights / training dataset / model runtime / output video / distribution）。
- [ ] 對 SwingTrace 實際下載權限進行合法測試；若 gated，記錄是否需要用戶同意，不能幫使用者繞過。
- [ ] 不將原片提交上游庫、Hub、公共網路。
- [ ] 有/無 SwingTrace 模型的兩種 Mac start 測試。
- [ ] 一個未見過的用戶真實 swing clip 用四處典型模糊影格逐點檢查，並與手動標註比較。
- [ ] 對每個依賴做 CPU/MPS latency、peak RAM、installer size 測量。
- [ ] 若結論為禁止／無法整合，維持 provider adapter 並以 `BLOCKED` 明確說明，而非偷換假數據。

## 7. 原始證據連結（新 Session 請重新查核）

1. SwingTrace source/model/AGPL：https://huggingface.co/nishsm/golf-club-detection-swingtrace
2. OpenCV license：https://opencv.org/license/
3. Norfair BSD：https://github.com/tryolabs/norfair/blob/master/LICENSE
4. Meta SAM2 Apache：https://ai.meta.com/research/sam2/
5. RF-DETR component license：https://github.com/roboflow/rf-detr ; https://roboflow.com/licensing
6. Konva / React Konva MIT：https://github.com/konvajs/konva ; https://github.com/konvajs/react-konva
7. PyAV BSD：https://github.com/PyAV-Org/PyAV/blob/master/pyproject.toml
8. FFmpeg LGPL/GPL：https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md
9. Editly MIT：https://github.com/mifi/editly
10. GolfShotTracer：https://github.com/jonibek95/GolfShotTracer
11. BoxMOT AGPL：https://github.com/mikel-brostrom/boxmot

**結論：R4 真正的差異化不是「把所有 GitHub 模型都安裝」，而是「完整、可編輯、證據分級、影片時間碼正確且能在 Mac App 交付」的本機工作流程。**


<!-- END GITHUB_OPEN_SOURCE_RESEARCH.md -->

---


<!-- BEGIN GEMINI_4_ARGON_MASTER_PROMPT.md -->

# Golf Swing Lab R4 — Gemini 4 Argon Autonomous Master Prompt

> **把本文件全文作為新 Session 的開發指令，同時上傳 `GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md` 與 `GITHUB_OPEN_SOURCE_RESEARCH.md`。**  
> **角色**：具備真實程式碼操作能力的 Staff Software Engineer / CV Research Engineer / Media Pipeline Engineer / Native macOS Engineer / Database & Security Reviewer / QA Lead。  
> **工作型態**：一個 Session 連續執行規劃、建置、測試、修 Bug、獨立審查、交付 Draft PR；不是每一步都停下來等我回覆。  
> **禁止範圍**：不 merge main、不 Force Push、不刪用戶資料／原片／示範庫、不外傳私人影片、不宣稱未做的實測已通過。

---

## 我的正式任務

請你在我的私有 GitHub Repository **`BDMisME/golf-swing-lab`** 上，**一次性完成 R4 Golf Tracer Studio 的全部可執行工程開發**：

1. **Swing Tracer**：真實桿頭／桿身辨識、上桿與下桿雙色軌跡、2D 平面投影可視化、逐點檢查與人工修正。禁止拿 wrist trajectory 當 club-head trajectory。
2. **Shot Tracer**：真實可見小白球連續追蹤，使用現有 detector + Kalman，擴充光流、前後向一致性、雙向 ROI、遮擋與離群過濾、人工 correction、信心分級。完全看不見不能偽造觀測線；推估與藝術化須有 provenance。
3. **Flight FX**：Clean、Neon、Beam、Gradient、Tail、Pulse，可配置顏色/寬度/光度/拖尾/圖層，可同時疊加 Swing/Shot，預覽和 export 位置/時間須一致。
4. **Studio**：Next.js 專屬編輯器，Mac 原生 WebKit 可用，時序與座標一致，選球、逐幀、拖曳點位、手動 Anchor/Impact、Undo/Redo、FX preset、儲存和再編輯。
5. **Export/Batch**：original / 16:9 / 9:16、30/60fps、單球／合輯、選最好的球、長片 10–30 分鐘逐球批次、進度/取消/重試；保留舊無特效匯出。
6. **保護 R3**：姿勢評分、慢動作雙球比較、18 筆示範庫、資料庫、storage、原片、Mac 既有安裝都必須相容。

**主架構與所有嚴格門檻在 `GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md`。對照研究在 `GITHUB_OPEN_SOURCE_RESEARCH.md`。這兩份是你的需求來源；此 Prompt 為執行規程。沒有歷史對話也不影響理解。**

---

## A. 先準確確認 repo 的最新狀態

請實際使用你的 GitHub 與本機執行能力，而不是僅搜尋 README 或靠先前 AI 報告。

已確認資訊：2026-10-31 PR #3 已 squash-merged 至 `main`，當時合併 SHA `306de571d8b5983e3465432fb574112241148a5e`；你開始時要**重新查 `origin/main` 最新 HEAD**，若 main 後續有新 commit，不得亂 reset。GitHub 網址 `https://github.com/BDMisME/golf-swing-lab`。

如果目前工作環境無 GitHub 權限或無本機 Mac 的控制能力，**不要假裝有**；先使用你能取得的最新 repository 和工具，將確實做不到的操作標記 `BLOCKED_EXTERNAL_ACCESS`。不要上傳私人影片到第三方服務來換取分析權限。

請依序：

1. `git status --short --branch`、`git fetch origin`、`git log -n 8 --oneline`、`git branch -vv`、`git rev-parse origin/main`。
2. 確認 PR #3 已 merged；若還有 R3 release 未完成但不影響 R4 branch，記錄為 baseline issue，不得擅自覆蓋 main。
3. 建立 `feat/r4-golf-tracer-studio` 自 `origin/main`，若同名分支已存在，先查內容/差異再決定復用，不得覆蓋他人工作。
4. 盤點 `pyproject.toml`、`apps/web/package.json`、`apps/api/`、`apps/worker/`、`packages/analysis/`、`packages/storage/`、`apps/api/alembic/`、`scripts/`、Mac launcher。
5. 逐字核對已知關鍵函式／路徑：`CoarseToFineDetector`、`GolfBallDetector`、`KalmanBallTracker`、`SwingSegment`、`SwingEvent`、`PoseArtifact`、`ExportJob`、`run_video_analysis_job`、`run_export_job`、`export_swing_compilation`、`probe_video_file`、`get_storage_service`、`SwingComparisonPlayer.tsx`。
6. 確認資料庫 backup/store backup 與真的已存在的影片；不要因為 `test fixtures` 就宣稱實拍驗收足夠。
7. 跑 R3 baseline：pytest/TS/lint/Next production build/既有 WebKit GUI test（如環境支援）。若 baseline fail：記錄且先判斷是既存缺陷、測試環境問題還是 R4 引入，不能直接抹掉測試。
8. 產出 `docs/r4/BASELINE_AUDIT.md`，包含真 SHA、真路徑、測試時間、已知問題和既有資料筆數。

**在這一步不需要停下向我要求確認**，除非涉及真實不可逆破壞性操作、缺少法律授權／私人素材同意，或無法取得必要憑證。

---

## B. 架構實作目標與次序（連續跑到底）

必須按以下階段執行，每階段完成後**自動接著下一階段**；中途發現 Bug 就修，不要回報「已擬定計畫等待確認」。

**Phase 1 — Contracts/DB/API/Manual Editor**

- 設計 canonical `source_pts_us`、`source frame identity`、rotation/crop/source/display/output transforms；VFR 與 FPS 不偷用 `frame_idx/fps` 作唯一時鐘。
- 新建 Tracer Project / Job / Track Revision / Manual Edit / Anchor Revision / Recipe / Export Job / Model Registry，完成 Alembic additive migration，不能破壞現有 table。
- 以 existing FastAPI auth/ownership 實作 router，OpenAPI response 與 TS typed contracts。採 storage key/hash 管理大容量 points；保留不可變原始偵測。
- Next.js 做獨立 Studio 頁面，manual-assisted 功能先跑通，包含逐幀點選/拖拉/復原/儲存/關閉再開；舊畫面保持可用。
- 交付 frame geometry parity test、DB migration/integration test、TS editing tests。

**Phase 2 — True Swing Tracer**

- 先對 `nishsm/golf-club-detection-swingtrace` 做真實模型與授權確認，不可假設 HF gated weights 可直接下載；若可合法使用，在 provider adapter 中實測 head/shaft/hands detection，避免把第三方原始碼直接大批搬入專案。
- 若 AGPL/權重發行限制不符，研究 OpenCV shaft-line/point estimation 或 Apache-2.0 RF-DETR 專用模型訓練；若沒有足夠標註與權重仍不能有合格 auto detection，要 `BLOCKED_SWING_AUTO`。
- Club Head 點一定從**桿頭視覺證據**出發，shaft geometry fallback 應獨立標識；手腕可為 ROI 訊號但絕不能拿來當 head。
- 以 Top/Impact 的 source PTS 切 backswing / downswing / follow-through，各段雙色；結合低信心、失幀、球桿遮擋的編輯 UI。
- 加每點 confidence/source type，保留 raw vs smooth，提供 quality gating。

**Phase 3 — Shot Tracer**

- 重用現有 ball tracker/detector（以不破壞 R3 方式 adapter），新增高解析原片局部處理、左/右方向 ROI、LK optical flow、PTS Kalman、outlier/false object rejection、短 gap source types。
- 用可觀測球路作自動證據，不得預測出完整飛行距離/落點；連續性失敗時清楚顯示 `NEEDS_REVIEW`/`UNAVAILABLE`。
- 人工帧點操作與調 Impact 僅存 Studio revisions，不得重寫 R3 scores/events；人工修正局部重算而非重跑長片。
- 比較 `automatic direct`, `algorithmically estimated`, `user manually anchored`, `artistic-only`，JSON 與 UI 都要顯示。

**Phase 4 — FX + 影片匯出 + 批次 + macOS**

- 設 deterministic time-based render recipe：Clean/Neon/Beam/Gradient/Tail/Pulse；Swing/Shot 疊加及獨立開關；UI 與正式影片共用 source PTS/transform/style definitions。
- 確保只有資料已存在、可信度足夠才能顯示真實觀測段；人工/推估/藝術延伸仍以源類型顯示。
- 新 Studio Export：source high-resolution，H264 MP4/yuv420p、original/16:9/9:16 × 30/60fps、音訊保持/靜音、單球/合輯/批次；保留 old `/api/exports` 無 FX 流程，不要把 legacy 函式改壞。
- 重新確認 Mac 安裝腳本危險的 `rm -rf` 行為，先做備份與 rollback。安裝至 `/Applications/Golf Swing Lab.app` 時，不准觸碰 DB/Storage/任意桌面資料夾。
- Studio 在 Native macOS WebKit 上操作完成，不只 Next.js build PASS。

**Phase 5 — Strict QA, Fix-Verify Loop, Draft PR**

- 由至少四種視角獨立 review：CV/Physics Evidence、Video/PTS Export、Fullstack/DB/Security、Mac App/User UX。
- 對 `docs/r4/TEST_MATRIX.md` 每一 gate 填 PASS/FAIL/BLOCKED/NOT_RUN；每一 PASS 需附 command、日期、source SHA、input hash、輸出證據。
- P0/P1 Bug：重現→最小修正→專項回歸→R3 regression→Mac E2E；重複直到無未解 P0/P1。
- P2 Bug 也須列出且不能碰到正確性/資料安全 gate；對 R4 全案 pass 的必要 P2 同樣必須修。
- 產出真實可觀看 demo（4 種：Swing path、Shot observed/low confidence、Both Neon、Multi-clip IG），需有使用權；**不可用畫面合成檢查當真人模型精度證據**。
- 到完整測試/資源真正可用且所有 gate passed，保持 Draft PR 但在報告中標 `READY_FOR_OWNER_REVIEW`。
- 遇不可解除的外部阻擋，不要無限空轉，也不要 fake-pass：保留已完成實作，交付 Draft PR，`OVERALL=BLOCKED`，明列缺甚麼實際人類資源、哪些驗收未跑、哪些模組尚未完成。

---

## C. 我要求你主動修 Bug 的「停止規則」

不要反覆問我「要不要修」；在權限範圍內自己執行：

```text
inspect -> reproduce -> isolate -> patch -> unit tests -> integration tests
-> native WebKit / real video tests -> compare baseline -> review
-> if failed: repeat with evidence
-> if blocked by unavailable real-world resource: mark BLOCKED with exact dependency
-> if all mandatory gates actually pass: stop with Draft PR and proof
```

修復紀律：

1. 每個 Bug 要有可重現輸入/產出、根因與 testcase；禁止只改 snapshot 使測試變綠。
2. 不許透過跳過/刪除測試、降低 confidence gate、改小樣本分母或把手動結果混入 auto quality 讓 FAIL 假變 PASS。
3. 不許為了修 Shot Tracer 改壞既有 Impact refinement/pose scoring；R3 regression 每個大修都要跑。
4. 圖片/影片成功展示不等於模型 accuracy；獨立逐點對人工 truth 標註。
5. 過程中的重大風險要主動註記，但非破壞性修補不需要我逐項批示。
6. 若本機磁碟/模型可用性/存取權阻擋，立刻嘗試不破壞資料的替代方案；仍不可能才 `BLOCKED`，並保持對當前已完成工程的誠實紀錄。
7. **不得宣稱「100% 無幻覺」或「所有影片皆可自動追蹤」**；能保證的是 provenance 誠實、失敗能拒絕及驗收證據完整。

---

## D. 極嚴格驗收：一條不能少

### D1. 真實高爾夫影片／ground truth

以架構文件 **§11** 為唯一正式驗收矩陣。至少 24 段真實不同 swing（30/60/120fps、左右手、遮擋、球體消失、背景干擾）和三支 10–30 分鐘長片；含真實人工標註。不能用 synthetic test 代替。若沒有，不能 OVERALL PASS；記錄與實際可用影片數、未測欄位，不要自動上網搜尋並下載他人有版權的影片宣稱是專案真實素材。

### D2. Swing Tracer

- 桿頭 direct observed precision ≥95%，定位誤差 P50≤12px、P95≤28px@寬1080標準化；自動 accepted 的 eligible clips ≥80% 有可審核路徑；**0** wrist-as-head 冒充。
- phase split Top/Impact ±1 source frame；估計/遮擋能被人看出；左/右球員正確。
- 若模型不可取得、或缺高 FPS 影片做驗收，維持明確 BLOCKED／NOT_RUN。

### D3. Shot Tracer

- 真球 observed point precision ≥95%，P50≤10px、P95≤25px；在 no-ball/no-launch/invisible failure set **0** 例把沒觀察到的軌跡說成 auto-tracked。
- point provenance、PTS、raw detector 和 filtered display coordinates 必須可檢查。
- 手動點精度 ≤2px，Undo/Redo/重新開啟 100%；不得污染 R3 scores / events。

### D4. 時間碼、匯出與 FX

- Original / 16:9 / 9:16 × 30 / 60fps × no_fx / swing / shot / both，全矩陣通過 ffprobe；不同媒體條件均可解碼。
- 對至少 20 個來源 PTS，preview vs exported track center ≤2px@1080、時間 ≤1 output frame；phase 顏色與估計段樣式相同。
- Long video process/selected clip export/no-fx old export 全部驗證；音訊有/無、preserve/mute、concat 1/2/3/5/10 片段；A/V shift ≤100ms。
- 30fps source 升到 60fps 是輸出重採樣，不許聲稱觀測增加。

### D5. R3 與真實 Native App

- 原有 Postgres DB / user media / 18 reference records / favorites / pose scores / offline coach / dual comparison 不變。
- 既有後端全量 tests + TS build/tests + WebKit GUI acceptance + 新 R4 tests 皆 PASS；若環境不能跑 WebKit，即 `NOT_RUN`，全案不能 PASSED。
- 在真正 `/Applications/Golf Swing Lab.app` 可 import -> 分析 -> tracer -> manual edit -> style -> export -> downloaded MP4，並附 Mac build SHA；僅 Web 伺服器跑通不算。
- 完成授權/模型/編碼包裝審查，尤其 SwingTrace AGPL、FFmpeg GPL/LGPL 與私有影片，不能默認安全再散布。

**任何一個必要 gate FAIL/BLOCKED/NOT_RUN，`OVERALL_R4` 一律不得 PASS。** 各子模組可分別 PASS，不得借用別人 PASS 充數。所有門檻及取樣細節見架構文件。

---

## E. 組織成能審查的工程產物

請在 repository 的 Draft PR 交付：

```text
docs/r4/BASELINE_AUDIT.md
docs/r4/DEPENDENCY_LICENSES.md
docs/r4/IMPLEMENTATION_LOG.md
docs/r4/API_AND_DATA_CONTRACTS.md
docs/r4/TEST_MATRIX.md
docs/r4/REAL_MEDIA_EVALUATION.md
docs/r4/FAILURE_GALLERY.md
docs/r4/EXPORT_PARITY_REPORT.md
docs/r4/MAC_RELEASE_VERIFICATION.md
docs/r4/FINAL_DELIVERY_REPORT.md
```

執行時請把上傳的 Architecture/Research 文件原樣保存到 `docs/r4/requirements/` 供未來 source-of-truth；若需要細部修正，寫 changelog/ADR，不要默默篡改原始要求與驗收門檻。

**PR 要求**：

- 新分支 `feat/r4-golf-tracer-studio`；PR title `feat(r4): Golf Tracer Studio — observed Swing and Shot Tracers, Flight FX, and native exports`。
- Draft PR，不能合併 main；只有我明確授權才可合併。
- 每個 phase 可以提交小 commit，必須真實可追溯；不能留未提交本機-only 關鍵變更。
- 如 repo 有現存 GitHub CI，加入/擴充不危及秘密的 CI；公開 runner 不得包含私人真人媒體。
- PR description 包含通過與不通過數據、輸出影片路徑/安全存取方式、模型/開源授權、R3 regression、Mac smoke、基準 HEAD。
- 不洩露 secrets、使用者個人影片、姓名或可識別內容至外部報告。

---

## F. 最終報告模板（必須逐欄填實測）

```markdown
# Golf Swing Lab R4 — Final Delivery

## Release control
- Repo / branch / PR URL:
- Base main SHA / Head SHA / git status:
- PR type: Draft (not merged)
- R4 overall: PASS | FAIL | BLOCKED | NOT_RUN
- Auto Swing: PASS | FAIL | BLOCKED | NOT_RUN
- Auto Shot: PASS | FAIL | BLOCKED | NOT_RUN
- Manual Editor: PASS | FAIL | BLOCKED | NOT_RUN
- Flight FX: PASS | FAIL | BLOCKED | NOT_RUN
- Export: PASS | FAIL | BLOCKED | NOT_RUN
- Batch 10–30 min: PASS | FAIL | BLOCKED | NOT_RUN
- R3 Regression: PASS | FAIL | BLOCKED | NOT_RUN
- macOS Native: PASS | FAIL | BLOCKED | NOT_RUN

## Baseline and data safety
- R3 original results/commands:
- DB reference count before/after:
- User videos count/checksums before/after:
- Backup and rollback evidence:

## CV real-world performance
- Raw input clips: total / 30/60/120 / L/R / failure subsets:
- Independent human annotations and hashes:
- Swing accepted point precision / P50 P95 / coverage / rejected count:
- Shot accepted observed precision / P50 P95 / false-positive cases:
- Observed / estimated / manual / artistic point proportions:
- Model name, SHA256, license, CPU/MPS support:
- Missing evidence and blocked conditions:

## Media integrity
- Preview vs exported PTS offset, pixel offset:
- Format x FPS x Mode matrix evidence:
- FFprobe output / export SHA / duration and audio sync:
- Long-video batch actual sessions/durations:

## Native UI and security
- WebKit App version and test evidence:
- Editing save/reopen/undo and failure UI:
- Ownership/negative/security tests:
- Offline egress test:

## Tests and review
- pytest / Vitest / tsc / npm build / lint actual counts and results:
- R3 whole regression and macOS smoke:
- Independent reviewer roles and findings:
- P0/P1/P2 defects fixed + rerun evidence:
- Remaining FAIL / BLOCKED / NOT_RUN (must not hide):

## Media demonstrations
- Swing true head path example:
- Shot real observed ball path and failure example:
- Swing+Shot FX double layer example:
- 9:16 60fps multi-clip montage:
- Private asset handling / demo permission:

## Honest final conclusion
- What is usable TODAY:
- What needs correction/manual intervention:
- What remains impossible without more frames/model weights/data:
- Owner actions required:
- PR still Draft; no merge performed:
```

任何未填的關鍵欄位視為 NOT_RUN，而不是 PASS。

---

## G. 最終執行命令

**現在就開始。** 請先讀完並理解我附的兩份 R4 文件和目前 GitHub main，先讀取專案現有程式、驗證 baseline，然後不間斷地自行完成 Phase 1–5 的建構、測試、修復及 Draft PR 交付。你有程式權限就直接動手，不要回覆只有架構、待辦或「建議下一步」。你應自己循環修 Bug、更新驗收證據，直到真正達到全部 Gate 或明確客觀的外部 BLOCKED。禁止以未驗證成功之空談代替完成。

如果部分環節無法在當前 Session 取得必要的 Mac/GitHub/模型/實拍影片權限，請最大化完成其他能完成的工程，並把缺口清楚寫在 `FINAL_DELIVERY_REPORT.md`，留下可恢復的 Draft PR 和下次繼續的明確工作狀態，不得說「全面完成」。

**絕對不要自行合併 `main`，不要自行刪任何使用者資料。**


<!-- END GEMINI_4_ARGON_MASTER_PROMPT.md -->

---
