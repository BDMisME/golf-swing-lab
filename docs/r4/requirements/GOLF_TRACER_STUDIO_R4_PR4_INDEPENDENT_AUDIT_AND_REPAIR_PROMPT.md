# Golf Swing Lab R4 — PR #4 獨立審查、缺口修復與再次驗收指令

- 審查日期：2026-10-31（Asia/Taipei）
- Repository：https://github.com/BDMisME/golf-swing-lab
- Draft PR：https://github.com/BDMisME/golf-swing-lab/pull/4
- 審查基準 PR HEAD：`56e4b3349cc0a9d49b1f95a1f2720a2f5f92e0d1`
- 基準 main：`306de571d8b5983e3465432fb574112241148a5e`
- 來源：本輪從 GitHub Connector 讀取 R4 真正提交的程式碼、測試及 `docs/r4` 報告；非獨立在使用者 Mac 上跑過測試。

## A. 獨立審查結論

**本輪正式結論：FAIL / NOT READY FOR MERGE。保留 Draft PR。**

Gemini 有實作龐大的 R4 基礎，並非空殼；但「三種效果都已達到原始驗收條件」並未成立。應區分已提交、合成測試通過、實拍驗證、原生 App 驗證、全產品可用等不同證據級別。

- Gate 1 Studio Foundation / Manual Editor：已實作，**E2E 驗收不足，保留 CONDITIONAL / NOT FULL PASS**。
- Gate 2 Auto Swing Tracer：**BLOCKED**；合法可用之專用權重未就緒；實拍只有桿身幾何估計點，覆蓋率 18.18%–41.47%，`direct_observed_count = 0`，6 段均 `NEEDS_REVIEW`。不能宣稱全自動完成。
- Gate 3 Auto Shot Tracer：**NOT VALIDATED / 實拍自動可用性未通過**；6 段真實影片均 `UNAVAILABLE`、零有效飛行點。Fail-closed 防假球是好事，但不是成功追蹤。
- Gate 4 Flight FX + Export：6 個匯出配置的 FFprobe/理論座標測試有價值，但未執行原規格要求的 >=24 output combinations、>=20 指定 PTS 的實際畫面像素比較；**不能給全 Gate PASS**。
- Gate 5 Regression/Data Integrity：報告 157/157 Python、7/7 frontend，但這是本機提交者報告，非 GitHub CI；保留既有 R3 回歸通過之紀錄，並新增 R4 真正 E2E 測試。
- Gate 6 Native App：`WKWebView` 的頁面 DOM、Canvas、Console 0 errors 和截圖為 smoke evidence，未證明 `/Applications/Golf Swing Lab.app` 全流程啟動、編輯/持久化/匯出/下載、不同影片播放、和恢復流程；**不能給全 Gate PASS**。
- 整體：**FAIL / BLOCKED；不可合併 main，不可對外宣稱 R4 全數完成。**

## B. 逐項已核實的重要程式問題

### P0-1 假時間碼來源：原本沒有 R3 事件時，程式自行計算 Top/Impact

`packages/analysis/tracer/segment_context.py` 使用：

```python
top_ms = ev_map.get("top") or (start_ms + int(span_ms * 0.48))
impact_ms = ev_map.get("impact_estimated") or ev_map.get("impact") or (start_ms + int(span_ms * 0.68))
```

而 `packages/analysis/tracer/shot_tracker.py` 在 context Impact 為 None 時另以 `0.62 * start + 0.38 * end` 生成。這不符合未觀測事件必須標示估計來源的證據規則。應取消無標記替代，將時間錨點狀態區分 `observed`, `r3_estimated`, `user_manual`, `missing`；缺少可信 Impact 時，禁止宣稱自動 Shot 的精準追蹤；如保留 heuristic search window，必須將其視為搜尋提示，絕不得等同真實 Impact。

### P0-2 Parity 報告量測口徑錯誤

`packages/analysis/tracer/compositor.py:verify_preview_export_parity` 只比對同一個 `OutputLayout` 的浮點座標計算與 OpenCV 四捨五入結果，並計算追蹤點與 CFR 近鄰時間格點差異。**沒有取出實際 WebKit/瀏覽器 Canvas 的像素與最終 MP4 解碼影格進行對位**，也沒有涵蓋畫面影格渲染延遲、旋轉、HDR/色彩、尾跡時間可見性。因此 0.6647px 是 **math projection parity**，不可命名 `preview_export_visual_parity_passed`。應新增真實影像對照，最少 20 個源 PTS × 切換不同 layer/style/aspect/FPS，在同一時間碼保存 Canvas 畫面與 FFmpeg 解碼後影格，扣除編碼容差與顯示縮放量測路徑中心、出現/消失 frame、上下桿顏色、藝術虛線等。原數學測試可保留但不得取代視覺驗收。

### P0-3 Preview 使用 Proxy；Export 使用原始影片，未完成影片來源與幀對齊驗證

`apps/api/routers/tracer_studio.py:_build_project_detail_response` 同時提供 `video_stream_url` 與 `original_video_stream_url`；`apps/web/src/app/tracer-studio/[projectId]/page.tsx` 選用 `project.video_stream_url`。既有 `apps/api/main.py:/api/videos/{video_id}/stream` 若無 `?source=original`，優先提供 Proxy。Export 卻由 `apps/worker/tracer_tasks.py` / `studio_exporter.py` 使用 raw source。因此當 Proxy 在轉碼中存在旋轉、VFR/CFR、時間軸差異時，不可宣稱已證明同幀預覽/輸出；應以明確來源標籤／權威影格對照處理，必要時 preview 使用 original，或建立 Proxy↔Original PTS / transform 映射並以影像驗證。

### P0-4 Shot 0 點時，單純設定 Apex/Landing 不會產生軌跡

`apps/api/routers/tracer_studio.py:update_project_anchors` 在 `if shot_pts and (...)` 才建立重算 Shot revision。六段真實影片 `shot_pts=[]`，所以單純依照 UI 的 Apex/Landing 按鍵點選，不會產生有效的可渲染 Shot track。`apps/web/src/app/tracer-studio/[projectId]/page.tsx:handleSpatialAnchorSet` 本身只更新 anchor，沒有建立球心點。請實作明確的「零觀測點→手動建立首個球心/起飛點→Apex/落點→人工／藝術軌跡」完整流程；**無真實觀測時不得稱為 verified Shot Tracer**。檢查 0 點、1 點、2 點、多點時各種操作和輸出。

### P0-5 播放動畫不是逐幀時間驅動

`apps/web/src/components/tracer/TracerCanvasEditor.tsx` 使用 `<video onTimeUpdate>` 更新 `currentPtsUs`，`drawOverlay` 只隨 React state 更新；沒有真正 `requestVideoFrameCallback` 或 source video frame/PTS 同步架構。瀏覽器 `timeupdate` 通常不是 30/60Hz 逐幀事件，故播放中線條可能跳動、落後影片，與 `60fps Preview` 的聲稱不符。請改為支援 WebKit 的逐影格回呼（可用時 `requestVideoFrameCallback`）、必要的安全 fallback（`requestAnimationFrame` 配合 presented-frame/seek synchronization）、pause/seek/loop/slow-motion 的準確同步；提供實測分幀紀錄。

### P1-1 Anchor 更新意外重設藝術延伸

`apps/api/schemas_tracer.py:TracerAnchorUpdateRequest.artistic_extension_enabled: bool = False` 搭配 `update_project_anchors()` 對每次錨點變更使用此欄位。使用者只改 Top/Impact 時，會默默把之前打開的 artistic extension 設回 False。應改 `bool | None = None`，None 表示保留既有狀態；額外提供顯式清除 Apex/Landing/藝術延伸的操作。

### P1-2 重新分析可能忽略 Studio 人工更正 Impact

`apps/worker/tracer_tasks.py:_load_segment_context_from_db()` 只讀取 R3 `SwingEvent`，呼叫 `resolve_segment_context` 時沒有傳入 `anchor_override`；`run_tracer_analysis_job()` 把這個 context 丟給 `SwingTracerEngine` / `ShotTracerEngine`。更新 Anchor 後 `recompute_tracks` 目前主要重新分色或延伸既有點，未真正基於修正後 Impact 重新執行球體搜尋；按「重新分析」可能再次使用舊 Impact。請按 active anchor revision 傳遞 Studio 專屬錨點，並測試重新分析在時間窗內確實使用新的 PTS，不得污染 R3。

### P1-3 幀點編輯、失敗模式與特效儲存仍需真正 GUI E2E

`TracerCanvasEditor.tsx:findNearestPointAtNorm` 選取所有時間點中距離最近的點，沒有當前影格時間容忍區間；快速揮桿的投影路徑重疊時，可能選到不同格的點。必須以 `currentPtsUs/source_frame_index` 限定可選點，提供軌跡點列表、Undo/Redo 與移動預覽；在真實 Mac WebKit 中完成「選第 N 格→拖曳點→儲存→重新載入→確認落點及 revision→Undo/Redo→出片→核對點位」，不可只測 hasCanvas=true。

`page.tsx:handleRecipeChange` 在 API 失敗時繼續保留 optimistic UI，造成使用者看到的配方與後端最後匯出快照可能不同。需 rollback 或重試／顯示錯誤，不允許沉默失敗。

### P1-4 匯出矩陣尚未滿足原 R4 需求

報告測了 original / 16:9 / 9:16、30/60fps，以及部分 preserve/mute，合計 6 組，但規格要求 `original/16:9/9:16 × 30/60 × no_fx/Swing/Shot/Both` 至少 24 組（音訊再另測）。還需：1/2/3/5/10 clip concat、>=20 個實際預覽↔輸出影格檢驗、A/V 偏差<=100ms、傳統無特效輸出，24/25/29.97/30/59.94/60/120 & VFR 輸入的時間行為及 fail-closed。

### P1-5 草稿版已安裝到正式 `/Applications`

報告指出已執行 `scripts/build_mac_app.sh`，把尚未驗收的 R4 `.app` 安裝到 `/Applications/Golf Swing Lab.app`。雖有備份，但 Draft PR 未合併前不應取代穩定日用 R3。後續 R4 試跑使用隔離 Bundle 名稱與測試 Profile/DB/Storage；若需要恢復既有版本，先檢查備份與使用者資料後安全回滾，禁止無確認的破壞性覆寫。正式升級須於 Gate 全過及專案負責人授權後執行。

### P1-6 長片／Worker 行為與工程安全驗證不足

要測真正 10–30 分鐘逐球批次（不是只選長片 567s 附近的一球）、RQ queue cancel/retry、突然關閉/重開、磁碟滿、memory peak、原片遺失、storage 切換、重複點匯出及多使用者權限；測試保留不得破壞既有 552 sessions、690 segments、18 reference、原視頻、Score、双球同步比較、舊 Export。

## C. Gemini 4 Argon — 一次性連續修復 MASTER PROMPT（直接複製）

你是 Golf Swing Lab R4 的技術總負責人、Computer Vision 工程師、Python/TypeScript/Next.js/FastAPI 工程師、macOS 工程師、QA 審查者。你的任務不是重新寫設計文件，也不是只讓測試變綠，而是**修復 Draft PR #4 的真實使用缺陷並執行完整原規格驗收**。

Repository: `BDMisME/golf-swing-lab`
Draft PR: `https://github.com/BDMisME/golf-swing-lab/pull/4`
審查時 HEAD: `56e4b3349cc0a9d49b1f95a1f2720a2f5f92e0d1`
規格權威：`docs/r4/requirements/GOLF_TRACER_STUDIO_R4_ARCHITECTURE.md` §11，以及完整主控 Prompt。

### 不可違反的指令

1. 先確認 PR #4 最新 HEAD；若已變動，以實際最新 HEAD 重新分析；**繼續既有 branch 和 Draft PR，不要另建 main 修改或自行 merge**。
2. 本文件 A/B 所列每一項都必須有 ROOT CAUSE、FIX、TEST、EVIDENCE、PASS/FAIL，不得只修改 README 狀態字詞。
3. 不得以人工標點、桿身幾何 estimated 或藝術曲線替代已驗證的獨立桿頭辨識／真球自動追蹤。自動模式仍不具觀測條件，就必須標 `BLOCKED`、`NOT_VALIDATED`；自動模組不得偷換為手動功能通過。
4. 合法取得模型權重或在能取得合理授權的資料集上本機訓練/微調替代桿頭偵測器；無法取得合法權重、授權或真實影像 ground truth 時，不能自製假測試結果。對 fallback 的缺口如實揭露。
5. Shot Tracer 必須先檢查真球可見性與 Impact evidence；運用現有 YOLO、光流、時序追蹤及離群值排除，在真實可觀測片段提高有效率，保留 fail-closed。**六段實拍零自動有效球路不能當成功追蹤**。每個 rejected case 必須保留檢測點候選分析與 ground truth review，判斷是小球不可見、ROI 偏移、模型誤報、時間錨點錯、顯示旋轉錯，或物理門檻誤拒；沒有可見證據不要硬通過。
6. 修復 PTS 假錨點／來源標籤；R3 實際與估計事件必須區分，無事件不可用固定百分比假稱真實 Impact。
7. 修復原始來源與 Proxy Preview 映射，完成真正 60fps 逐格預覽；不得以同一份 Python 公式內互相計算的 parity 數字取代 GUI screenshot↔MP4 decoded frame 比對。
8. 完成 0-point Shot Track → 手動 launch/start、Apex、Landing、內插、可選藝術延伸、修訂版持久化、恢復、匯出；所有點位必須有 source type 且「手動、預測、藝術」顯著區分，無真球時不得標自動成功。
9. 修正 Anchor 狀態互相覆寫、Impact 修正後 rerun 不生效、幀點選取跨格、配方樂觀更新失敗等實際可觀察錯誤。
10. 保持 R1-R3 功能及資料庫絕不退化；測試、Mac 安裝與 DB migration 必須採可恢復方案，避免未核准的 Draft App 直接覆寫日常正式版。
11. 逐項執行原規格 §11 Gate 1–6；每個 Gate 製作原始可稽核證據，禁止用平均分數、`100%` 模糊結果或 metadata 中自行宣稱的布林值代替。
12. 測試失敗就定位根因、修復、重跑直到綠燈；對不可能憑現有輸入取得的授權權重、特定真實影片與人工 GT，請清楚標註 `BLOCKED_EXTERNAL_DEPENDENCY`，仍完成其他可做的修復。
13. 不要要求我每階段核准，不要停在架構文件；直到可執行工程部分確實結案。**不可自動合併 main、不可破壞性安裝正式 Mac App。**

### 必須執行的測試／交付物

- 至少 24 互異實拍 swing clips；含 >=6 30fps、>=6 60fps、>=3 >=120fps、>=4 左手、>=4 右手、>=5 各遮擋/背景干擾/球消失類別。沒有來源須報缺，不可補造。
- 至少 3 支 10–30min 長片端到端逐球切片→按需 tracer→精選→合輯；缺片則 BLOCKED。
- 桿頭：direct accepted precision >=.95, P50<=12px、P95<=28px（@1080 standard）、>=80% 可觀測適用片段有可審核結果，且零腕點冒充；必須有獨立人工標註。
- 小白球：direct observed precision>=.95、P50<=10px、P95<=25px（@1080 standard）；球不可見/no-ball 群零假完整軌跡。報實際分子、分母、觀測子群與拒斥子群。
- `20+` 指定 PTS 檢查實際 WebKit Canvas 與最終 MP4 解碼影格，目標 <=2px @1080 且 <=1 output frame；計算基準需能由截图/實際像素/track anchors 復算。
- `original/16:9/9:16 × 30/60fps × no_fx/Swing/Shot/Both` >=24 profiles；preserve/mute A/V drift<=100ms；1/2/3/5/10 clip concat 及舊無特效匯出。
- Mac App 必須實際啟動**測試版 Bundle**，在 WKWebView 依序完成點擊、拖曳、改 Impact、儲存重開、還原 Revision、套 FX、觸發 Export、下載、FFprobe；不能只有 hasCanvas=true。
- RQ queue/cancel/retry/forced restart、磁碟滿、worker crash、CPU/RSS/磁碟耗用及快取回收測試。
- GitHub PR 上提供：`docs/r4/POST_REVIEW_FIX_LOG.md`、`docs/r4/REAL_MEDIA_GROUND_TRUTH_RESULTS.md`、`docs/r4/ACTUAL_VISUAL_PARITY_REPORT.md`、`docs/r4/END_TO_END_WEBKIT_REPORT.md`、`docs/r4/REVISED_GATE_MATRIX.md`、失敗案例及可分享（不侵犯隱私）的短影片連結/本機路徑，含測試用 HEAD SHA、時間與乾淨/髒工作樹狀態。

### 結案判定

- `PASS`：六大 Gate 均符合原規格，且有證據能獨立重現。
- `BLOCKED/NOT_VALIDATED`：任一自動追蹤的關鍵模型、真實樣本、GT 或 Mac E2E 未達條件，雖然功能代碼已完成，**仍不得宣稱整體 R4 PASS**；保留 Draft PR，列出下一步可執行修復與清楚的外部依賴。
- `FAIL`：存在真實功能缺陷、資料污染、錯誤的驗收數據或保證性宣稱。

請現在繼續修復，直到已知可修問題都完成、測試覆蓋真正用戶路徑，沒有資料庫破壞；如有無法取得的外部依賴則保留阻擋，不得擅自降低門檻。完成後只回傳實際 GitHub HEAD、修改清單、每個 Gate 精確狀態、可重現命令及原始證據，**不要自行合併 main**。

---

備註：本審查僅透過 GitHub 最新程式、報告與 Gemini 本機輸出核對；我沒有獨立執行 macOS App、影格真值標註或所有 pytest；涉及「需要真實裝置才能證明」的部分仍必須由 Gemini 執行並保存 raw evidence。
