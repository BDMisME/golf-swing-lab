# Golf Swing Lab R4 — Phase 0 基準盤點報告 (`BASELINE_AUDIT.md`)

- **盤點時間**：2026-10-31T16:31:00+08:00 (Asia/Taipei)
- **目標儲存庫**：`https://github.com/BDMisME/golf-swing-lab`
- **基準分支 (`origin/main`) SHA**：`306de571d8b5983e3465432fb574112241148a5e` (`feat(r3): offline posture coach, slow motion comparison, and truthful dual-axis evaluation (#3)`)
- **R4 開發分支**：`feat/r4-golf-tracer-studio`（自 `origin/main` 建立）
- **上傳規格保存位置**：`docs/r4/requirements/`（原樣保存 `GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md`、`GITHUB_OPEN_SOURCE_RESEARCH.md`、`GEMINI_4_ARGON_MASTER_PROMPT.md`、`GOLF_TRACER_STUDIO_R4_COMPLETE_INTEGRATION_AND_PROMPT.md`、`README_START_HERE.md`）

---

## 1. 資料庫與本機資產盤點暨非破壞性備份

### 1.1 PostgreSQL 資料表基準筆數（修改前）
| 資料表 (`__tablename__`) | 筆數 (Before R4) | 備註 |
|---|---:|---|
| `users` | 6 | 含預設管理員與測試帳號 |
| `practice_sessions` | 552 | 歷史練習場次與測試場次 |
| `videos` | 450 | 原始與測試影片紀錄 |
| `swing_segments` | 690 | 已切球之揮桿片段 |
| `swing_events` | 4,036 | 9 階段揮桿事件時間碼 |
| `pose_artifacts` | 603 | 2D 骨架關鍵點與品質 metadata |
| `swing_scores` | 596 | Score v1/v2.1 動作評分與 IG 視覺分 |
| `reference_swings` | 18 | 17 支球桿分類＋沙坑示範揮桿庫（100% 完整保留） |
| `exports` | 120 | 既有單球與多球合輯匯出紀錄 |
| `favorites` | 0 | 精選球收藏表 |

### 1.2 變更前完整資料庫備份證據
- **備份檔案路徑**：`/Users/mathew/.golfswinglab/backups/pre_r4_baseline_20261031.dump`
- **檔案大小**：`3.3 MB`
- **SHA256**：`4ccc46b156ee4b2eaf7d817514256f5479e40820e6a287023c159534c80a94eb`
- **還原指令**：`pg_restore -U gsl -d golf_swing_lab --clean --if-exists ~/.golfswinglab/backups/pre_r4_baseline_20261031.dump`

### 1.3 本機儲存 (`~/.golfswinglab/storage`) 與真實媒體盤點
1. **真實 iPhone 錄製原片 (`raw/`)**：
   - `IMG_0995.mov` (`1381.58 MB`, `duration_ms=659575` ≈ 11 分鐘, `1920x1080` `rotation=270` 直立後 `1080x1920`, `59.96 fps`, `HEVC`, `has_audio=True`) — **1 支真實 10–30 分鐘長片**
   - `video_2min.mov` (`290.18 MB`, `duration_ms=139053` ≈ 2 分 19 秒, `1080x1920` `rotation=0`, `59.99 fps`, `is_vfr=True`, `HEVC`, `has_audio=True`, `sha256=4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9`)
   - `11s_iphone.mov` / `11s_iphone_e2e.mov` (`23.90 MB`, `duration_ms=11458` ≈ 11.5 秒, `1080x1920` `rotation=0`, `60.04 fps`, `HEVC`, `has_audio=True`)
   - `iphone_rotated.mov` (`duration_ms=6000`, `480x360` `rotation=90`, `30.00 fps`)
2. **專業與參考示範影片 (`references/`)**：
   - 共 18 筆 `ReferenceSwing` 對應之真實影片，涵蓋 `23.98 fps` (`24000/1001`)、`25.00 fps`、`29.97 fps` (`30000/1001`)、`30.00 fps`、`59.94 fps` (`60000/1001`, `dev_fixture_dtl_7iron.mp4` `1080x1920`)。
3. **本機 AI 模型權重 (`~/Library/Application Support/GolfSwingLab/models/`)**：
   - `golf_ball_yolov8n.pt`：大小 `24,458,339 bytes`，`sha256=45e8f8bd8975dc7f437919a11c3f6ee1fe7c8ae40b0f49910d0677d1c0326791`，類別 `{0: 'golf_ball'}`（已存在可用）。
   - `yolov8x-pose.pt`：大小 `139,420,105 bytes`，`sha256=7a9bf952c2fc1c07d4a1da00dbb4cfab5ed71f89cbe8824d51a8f7a61cee5825`（已存在可用）。
   - `swingtrace-yolo11m.pt`（專用桿頭/桿身模型）：**本機未安裝**；經查 HuggingFace `nishsm/golf-club-detection-swingtrace` 為 `gated: auto`（未登入下載回傳 `HTTP 401 GatedRepo`），且授權為 `AGPL-3.0`。
4. **真實影片驗收樣本缺口（誠實揭露）**：
   - 現有環境具備 >24 段真實揮桿片段（含 `IMG_0995.mov` 多球、`video_2min.mov` 多球、`11s_iphone.mov` 與 18 支示範庫），但：
     1. 缺少 `>= 120fps` 實拍高幀率影片（0 支，門檻需 `>= 3` 支）。
     2. 缺少左打者 (`handedness=left`) 實拍原片（0 支，門檻需 `>= 4` 支）。
     3. 10–30 分鐘完整長片目前僅 1 支 (`IMG_0995.mov`, 11 分鐘)，門檻需 `>= 3` 支不同長片。
     4. 缺少 2 人獨立交叉標註之逐幀桿頭/球心 Ground Truth 檔案。

---

## 2. 既有關鍵檔案與函式核對表

| 模組領域 | 實際檔案路徑 | 已核實關鍵類別／函式 | R4 整合與隔離方式 |
|---|---|---|---|
| 切球與事件狀態機 | `packages/analysis/detection/scanner.py` | `CoarseToFineDetector.analyze_video`, `analyze_single_window` | 重用 `SwingSegment.start_ms/end_ms` 與 `SwingEvent`；絕不因 Studio 覆寫 R3 事件或評分 |
| 初始球體追蹤 | `packages/analysis/tracking/ball_tracker.py` | `GolfBallDetector.detect_in_roi`, `track_swing_launch_with_feedback`, `KalmanBallTracker` | 保留原檔供 R3 scanner 使用；於 `packages/analysis/tracer/` 建立支援雙向 ROI、LK 光流、PTS `dt` Kalman 與嚴格 `source_type` 區分之 Studio Shot Tracker |
| 媒體探測與 PTS | `packages/analysis/probe.py` | `probe_video_file`, `VideoMetadata`, `generate_proxy_and_thumbnail` | 保留原函式；新增 `packages/analysis/tracer/media_clock.py` 與 `frame_reader.py`，以整數微秒 `source_pts_us` 為單一時間權威 |
| 影片匯出 | `packages/analysis/exporter.py` | `export_swing_compilation` | 原封不動保留 legacy 無特效匯出；新增 `packages/analysis/tracer/studio_exporter.py` 與 `compositor.py` 支援原片高畫質、original/16:9/9:16、30/60fps、音訊保留/靜音與 1–10 球合輯 |
| 物件儲存 | `packages/storage/s3_client.py` | `get_storage_service`, `HybridStorageService`, `LocalStorageService` | 全面透過 `get_storage_service()` 讀寫原片、壓縮軌跡點 (`jsonl.gz`)、預覽與匯出 MP4 + `.tracer.json` sidecar |
| 後端 API 與資料模型 | `apps/api/main.py`, `apps/api/models.py`, `apps/api/schemas.py` | `Video`, `SwingSegment`, `SwingEvent`, `PoseArtifact`, `SwingScore`, `ExportJob` | 新增 8 張 `tracer_*` 資料表與 Alembic migration `0003_tracer_studio.py`（位於 `apps/api/migrations/versions/`）；新增 `apps/api/routers/tracer_studio.py` |
| 背景任務 Worker | `apps/worker/main.py`, `apps/worker/tasks.py` | `run_video_analysis_job`, `run_export_job` | 新增 `apps/worker/tracer_tasks.py` (`run_tracer_analysis_job`, `run_tracer_export_job`)，支援 `gsl-tracer` 佇列與可取消/重試之背景執行 |
| 前端介面 | `apps/web/src/app/`, `apps/web/src/components/SwingComparisonPlayer.tsx` | 場次報告、單球檢視、雙球慢動作比較 | 不膨脹 `SwingComparisonPlayer.tsx`；新增獨立路由 `/tracer-studio/[projectId]` 與 `apps/web/src/components/tracer/*` 模組化編輯器 |
| Mac 原生應用與安裝 | `launcher.c`, `desktop_app.py`, `scripts/build_mac_app.sh` | `build_mac_app.sh`, `launch_desktop_window` | 修復 `build_mac_app.sh` 中危險 `rm -rf` 操作，改為檢查 Bundle ID、先備份舊版 `.app`、atomic replace 與 rollback，絕不觸碰 `~/.golfswinglab` |

---

## 3. R3 Baseline 測試結果

- **前端型別檢查 (`npm run lint` / `tsc --noEmit`)**：`PASS`（0 errors）
- **前端單元測試 (`npm test` / `vitest run`)**：`PASS`（1 file, 3 passed, 431ms）
- **前端生產建置 (`npm run build` / `next build`)**：`PASS`（9 routes compiled successfully）
- **後端與演算法全量測試 (`.venv/bin/pytest -q`)**：`PASS`（`135 passed, 2 warnings in 214.55s`）
