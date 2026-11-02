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
