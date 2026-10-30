# IMPLEMENTATION_STATE.md — 專案實作狀態與中斷恢復紀錄

## 最新修復狀態（Round 23: Golf Swing Lab R3 — Final Scientific Integrity & Merge Gate）
1. **第一階段：骨盆 2D 平面幾何指標運動學誠信修正（Pelvic 2D Displacement Scientific Integrity）**：`PASS`
   - **客觀物理意義更名**：將 `impact_hip_clearance` 名稱由「擊球骨盆深度開放比」修正為「擊球骨盆2D相對位移比」（保留 `id="impact_hip_clearance"` 以確保 API 與前端契約相容性）。
   - **移除單向 `is_higher_better` 假設**：2D 影像雙髖中點歐氏距離大小無法區分左臀後移（Clearance）或骨盆前頂（Early Extension），更無法推論 3D 骨盆旋轉角度，故移除越大越好假設，設置中性容許範圍（8.0%~18.0% 身長）。
   - **假旋轉 Drill 徹底拔除**：移除「左臀後退清開空間 Drill」，當此指標作為觀察項目時安全降級為純客觀幾何觀察（`actionable_drill = None`），並在 summary 與 docstring 明確揭露 2D 歐氏距離無法推論旋轉之局限。
   - **合成驗證**：新增 `test_pelvic_displacement_isotropic_direction_invariance`，驗證向前頂、向後退、下蹲、拔起四種不同方向之等距位移百分比完全相等，演算法不誤判旋轉度數。
2. **第二階段：Optimal 判定與實驗性參考區間雙軸分離（Dual-Axis Optimal & Benchmark Evaluation）**：`PASS`
   - **雙軸獨立評估架構**：
     - 軸 1：`relative_status`（相對於示範選手差異：`aligned` / `moderate_diff` / `significant_diff`）。
     - 軸 2：`benchmark_status`（相對於常模區間：`within_benchmark` / `outside_benchmark` / `not_applicable`）。
   - **防止盲目認定 Optimal**：在越小越好指標（`top_spine_retention`, `top_head_displacement`, `impact_spine_delta`, `finish_spine_angle`）中，若使用者數值小於示範選手但超出實驗性參考區間（例如頭部位移 11.1% < 28.8% 但 > 8.0%），系統絕不給予 `optimal`，而是標註為 `moderate_diff`，並客觀說明「較示範小但仍超出實驗性參考區間」。
   - **合成驗證**：新增 `test_optimal_requires_within_benchmark_even_if_better_than_ref`，驗證超出區間時不蓋章 optimal，僅在落在區間內時始得 optimal。
3. **第三階段：Priority Fix 可診斷性與適用性優先排序（Priority Fix Diagnosability & Precedence）**：`PASS`
   - **可行動 Drill 候選優先**：建立 `ACTIONABLE_DRILL_METRICS`（站姿前傾、頂點維持、頂點頭部、擊球前傾維持、節奏比、收桿直立）與 `OBSERVATION_ONLY_METRICS`（手腕高度、骨盆平面位移）。
   - **動作缺陷篩選防護**：排除使用者表現優於或等於示範球員之項目（`delta <= 0` 且 lower_better），不誤導使用者修改更穩定的動作。
   - **可診斷性優先序**：優先從具備 Actionable Drill 之動作缺陷中依無量綱嚴重度排序挑選；純觀察指標降級（`actionable_drill = None`）；若無可靠缺陷則回傳 `None`。
   - **7I 與 Driver 真實 API 對齊**：
     - 7I：精準判定為節奏轉換與站姿前傾缺陷，不被純觀察指標干擾。
     - Driver：手腕設定差異降級為純觀察，`actionable_drill = null`，無任何假 Drill。
4. **第四階段：報告一致性與單一真實來源（Single Source of Truth & Full Audit）**：`PASS`
   - `docs/reports/real_api_posture_comparison_report.json` 包含動態 UTC 時間、Git SHA、Branch、工作樹狀態，各項度量數值與單位 100% 由真實 API 自動對齊。
5. **第五階段：全矩陣自動化驗收與原生 WebKit 驗證**：`PASS`
   - 專項測試：`tests/test_quantitative_posture_comparison.py` **25 / 25 PASSED (100%)**。
   - 離線 LLM 守衛：`tests/test_offline_llm_guard.py` **9 / 9 PASSED (100%)**。
   - 示範素材庫完整性：`scripts/verify_18_reference_swings.py` 18 / 18 示範資料庫記錄 100% 完整無缺。
   - 後端全套測試：**129 / 129 PASSED (100%)**（包含 2 分鐘長影片 12 球全量 CV 基準評估）。
   - Next.js 15.5.28 正式建置：**9 / 9 靜態路由編譯無誤 (0 錯誤)**。
   - WebKit 原生視窗實測：`scripts/verify_webkit_r3_slowmo_and_coach.py` 7 大步驟 100% 全數通過（PASS），產出 10 張真實 WebKit 截圖存證與完整報告。
- **最後更新時間**：2026-10-31T04:05:00+08:00
- **當前分支**：`feat/r3-offline-coach-and-slow-motion`
- **正式判定**：**Personal Beta READY FOR MERGE (嚴禁自行合併 main，已推送到 PR #3 分支，等待專案負責人最後授權合併)**

## 前期重大里程碑狀態（Round 22: Golf Swing Lab R3 — Final Coaching Logic Hotfix）

## 前期重大里程碑狀態（Round 21: Golf Swing Lab R3 — Final Release Audit & PR #3 Merge Readiness）

## 前期重大里程碑狀態（Round 20: Golf Swing Lab R3 — Final Geometry Integrity & Merge Gate）
1. **P0-A 2D 影像長寬比等比例校正（Isotropic Coordinate Space）**：`PASS`
   - 重構 `packages/analysis/posture_comparison.py`，全面實作等比例影像座標系轉換：
     $$x_{\text{iso}} = x_{\text{norm}} \cdot \frac{W_{\text{display}}}{H_{\text{display}}} = x_{\text{norm}} \cdot A, \quad y_{\text{iso}} = y_{\text{norm}}$$
   - 徹底根除 iPhone 直式（如 1080×1920, $A=0.5625$）與示範影片橫式（如 640×360, $A=1.7778$）之間直接使用歸一化座標造成高達 $20^\circ \sim 30^\circ$ 的幾何拉伸失真（實測相同 30° 前傾動作，未校正前角度差距高達 $27.75^\circ$，校正後真實差距降至 $<0.1^\circ$）。
   - 支援 iPhone 影片旋轉 Metadata（90° / 270°）自動交換寬高，動態解析真實顯示長寬比。
   - 尺度不變性（Scale Invariance）：實測 1080×1920 與 540×960（相同長寬比）在等比例座標系下前傾角與位移比誤差為 $0.00^\circ$。
   - 軀幹長度正規化：所有位移與距離皆在等比例座標系下以雙肩中點至雙髖中點歐氏長度無量綱化，嚴禁未標定之公分或英吋。
   - 缺少寬高或長寬比資訊時，系統優雅降級為 `status="insufficient_evidence"`、`delta=None`，絕不崩潰或妄斷差異。
2. **P0-B 跨長寬比與解析度幾何不變性專項測試**：`PASS`
   - `tests/test_quantitative_posture_comparison.py` 新增 4 項專項幾何測試：
     - `test_cross_aspect_ratio_invariance_portrait_vs_landscape`: 直式 iPhone vs 橫式示範真實前傾角一致性驗證。
     - `test_resolution_scaling_invariance`: 1080×1920 vs 540×960 尺度不變性驗證。
     - `test_rotation_metadata_dimension_swap`: 1920×1080 帶 rotation: 90/270 自動對調直式驗證。
     - `test_missing_resolution_graceful_handling`: 缺少長寬比時優雅降級驗證。
3. **P0-C 時序邊界與事件互斥收緊**：`PASS`
   - Top 與 Impact 互斥約束：實作 `forbidden_times`，Top 不得借用 Impact 影格，Impact 亦不得借用 Top 影格。單一影格影片中，Impact 找不到獨立影格時誠實回報缺少證據，絕不捏造相同姿勢。
   - 移除所有假時間偏移：缺少 Top 或 Impact 時間碼時，絕不私自使用固定偏移（如 +333ms, +1200ms），相關指標誠實標記為 `insufficient_evidence`。
   - 證據精確追蹤：`user_evidence` 與 `ref_evidence` 嚴格記錄選用影格時間碼與事件標註時間之誤差 `frame_time_error_ms`。
4. **P1-A 量化可信度與元資料揭露**：`PASS`
   - 報告元資料注入 `geometry_calibration` 物件（記錄雙方解析度、長寬比、座標系標籤與長寬比校正免責聲明）。
   - 理論常模明確標註為「實驗性參考區間（非專業認證標準）」。
5. **P1-B 前端 UI 幾何校正提示**：`PASS`
   - `SwingComparisonPlayer.tsx` 整合 `geometry_calibration`，頂部即時呈現「📐 2D 影像長寬比等比例校正已啟用（Isotropic Coordinate Space）」徽章與雙方長寬比數值展示。
6. **P1-C 端到端全量驗證與 WebKit 實測**：`PASS`
   - 專項測試：`tests/test_quantitative_posture_comparison.py` 17 / 17 PASSED (100%)。
   - 全套後端測試套件：**121 / 121 PASSED (100%)** in 210.96s。
   - Next.js 15.5.28 正式建置：**9 / 9 靜態路由編譯無誤 (0 錯誤)**。
   - macOS 原生 WebKit WKWebView 6 大步驟實測全數通過（PASS），產出真實截圖與報告 `docs/reports/swing_comparison_r3_report.json`。
- **最後更新時間**：2026-10-30T18:05:00+08:00
- **當前分支**：`feat/r3-offline-coach-and-slow-motion`
- **正式判定**：**READY FOR PR REVIEW (嚴禁自行合併 main，等待使用者授權)**

## 前期重大里程碑狀態（Round 19: Golf Swing Lab R3 — Real Pose Evidence & Offline Integrity 修復）
1. **P0-A 真實 Pose 幾何量測與假常數徹底拔除**：`PASS`
   - 重構 `packages/analysis/posture_comparison.py`，徹底移除所有寫死假常數（`ref_addr_tilt=40.0`, `ref_spine_delta=1.8`, `ref_head_top_pct=3.5`, `ref_tempo=3.0`, `user_hip_clear=11.5`, `ref_hip_clear=14.0`, `ref_finish_score=95.0` 等）。
   - 純粹從雙方真實關鍵影格（`keyframes_json` / `landmarks`）計算，包含雙肩中點、雙髖中點、手腕中點、頭部鼻尖。
   - 尺標正規化：以雙肩中點至雙髖中點之 2D 歐氏長度（軀幹長度 Torso Length）為標準尺規進行無量綱計算（手腕高度比、頭部位移比、骨盆深度位移比），嚴禁未標定之公分或英吋。
   - 缺少 Pose 或關鍵點可見度不足（< 0.35）時，一律誠實標註為 `N/A`、`status="insufficient_evidence"`，絕不湊數。
   - 鏡頭視角檢查：比對示範影片與使用者視角，非標準 DTL（如 LW 後斜、Putter 特寫）標註 `not_comparable`，不推算 2D 平面幾何差異。
2. **P0-B 移除假標準與可信度動態分級**：`PASS`
   - 理論常模分離：建立獨立欄位 `general_benchmark_range`（如站姿前傾 36°~44°、頂點維持 ≤4°、節奏比 2.7~3.3:1），與示範球員實際量測數值 (`ref_value`) 嚴格區隔。
   - 可信度動態評定：`overall_reliability` 不再固定為 `high`，而是依有效比對指標數與平均信心度動態評估（high/moderate/low/unreliable）。
   - 恪守誠信：明確標記 2D 平面幾何量測限制，禁止由單一 2D 變化妄斷 3D 力學。
3. **P0-C Reference 選擇嚴格跟隨使用者指定，杜絕隱性 Fallback**：`PASS`
   - 修改 `apps/api/main.py` 之 `get_swing_posture_comparison`：當使用者指定 `ref_id` 或 `club_type` 時嚴格檢索，若無對應示範影片**絕不偷偷 fallback 到 7I**，而是回傳 `overall_status="reference_missing"` 與提示。
   - 預設查詢球桿示範時優先挑選具備真實骨架關鍵點之正式示範（`order_by(desc(is_default), desc(imported_at))`）。
4. **P0-D Priority Fix 唯一改善重點建立在真實證據上**：`PASS`
   - 只有在 `is_comparable=True`、`is_reliable=True` 且落入 `significant_diff` 或 `moderate_diff` 時才選出改善重點並產出 Drill。
   - 各項指標都在相容區間內或證據不足時，`priority_fix_id` 誠實回傳 `None`，提示無顯著幾何異常或證據不足，絕不編造假缺陷與隨機 Drill。
5. **P1-A 離線守衛加固與 Fail-Closed 阻斷**：`PASS`
   - 於 `packages/analysis/coach.py` 實作 `is_external_llm_allowed()`，當 `enable_external_llm=False` 或組態載入例外時 Fail-Closed 阻斷。
   - 徹底移除 `and self.transport is None` 繞過漏洞，即使外部傳入 transport 或 API Key 亦 100% 阻斷外部連線。
   - `tests/test_offline_llm_guard.py` 新增阻斷與例外防禦測試，**9 / 9 PASSED (100%)**。
6. **P1-B 慢動作示範素材節奏保護**：`PASS`
   - 示範素材若為慢動作 (`is_slow_motion=True`)，其 tempo 明確標示為 `N/A (慢動作素材不提供假Tempo)`，不推算假數值。
7. **P1-C 自動化驗收與品質保證**：`PASS`
   - `tests/test_quantitative_posture_comparison.py` 全面重構並擴充 9 項專項測試，**9 / 9 PASSED (100%)**。
   - 全套後端測試套件：**113 / 113 PASSED (100%)** in 206.28s。
   - Next.js 15.5.28 正式建置：**9/9 靜態路由編譯無誤 (0 錯誤)**。
   - WebKit 原生端到端實測：`scripts/verify_webkit_r3_slowmo_and_coach.py` 6 大步驟全數通過（PASS），產出真實截圖與報告 `docs/reports/swing_comparison_r3_report.json`。
- **最後更新時間**：2026-10-30T13:15:00+08:00
- **當前分支**：`feat/r3-offline-coach-and-slow-motion`
- **正式判定**：**READY FOR PR REVIEW (嚴禁自行合併 main，等待使用者授權)**

## 前期重大里程碑狀態（Round 18: Golf Swing Lab R3 — 離線量化姿勢教練與慢動作雙影片比較）
1. **P0 離線守衛與全域外部 LLM 請求阻斷**：`PASS`
   - 後端統一定義 `GSL_ENABLE_EXTERNAL_LLM=false`（`apps/api/config.py`）。
   - `packages/analysis/coach.py` 中 `OpenAICompatibleCoachProvider` 與 `GeminiCoachProvider` 全面防禦攔截，未顯式設定時一律安全回退為 `RuleBasedCoachProvider`，禁止任何對外 HTTP 請求。
   - `generate_deep_vision_insight` 強制回退為規則式幾何運動學解析，絕不發起外部 Vision 呼叫。
   - `/api/settings` 即時回傳離線狀態，前端設定頁透明顯示「本機離線模式（無外部 LLM 請求）」。
   - 單元測試 `tests/test_offline_llm_guard.py` 6/6 全數通過。
2. **P1 雙影片同步慢動作播放器升級**：`PASS`
   - 速度選項：`0.25× 超慢`, `0.5× 慢放 (預設)`, `0.75× 慢速`, `1.0× 原速`，附「↺ 回復 1.0×」。
   - 切換速度不暫停、不重載、不跳回 0 秒、不重設 pan/zoom、不遺失 Top/Impact 對齊、保留重播循環。
   - 控制模式分離：雙影片同步模式（Play 同步推進、時鐘平滑追趕）vs 獨立檢視模式（單側獨立操作，自動停用漂移校正），附「🔗 一鍵回到雙影片同步」。
   - 一鍵停格比對：「🎯 Top 停格比對」與「💥 Impact 停格比對」，精準跳轉並暫停於頂點與擊球瞬間。
   - 骨架標記開關：「🦴 骨架標記：開啟 / 隱藏」按鈕，自由切換 Clean Motion Canvas 疊圖與真實解碼畫面。
   - 長寬比防拉伸：全面採用 `object-contain`，配合雙側獨立 Zoom/Pan，保護原始相機幾何比例。
3. **P2 離線量化姿勢比較表與慢放跳轉**：`PASS`
   - 核心量化比較引擎 `packages/analysis/posture_comparison.py`，涵蓋 4 大階段（Address, Top, Impact, Finish）8 項可觀測運動學指標（脊柱前傾、手腕基準高度、頂點前傾角、頭部相對位移比例、擊球前傾變化、節奏比、收桿直立角、收桿平衡晃動比）。
   - 後端 API 端點 `GET /api/swings/{swing_id}/posture-comparison` 回傳結構化差異與信賴區間。
   - 前端量化表格清晰展示我的數值、示範數值、差異、可信度與「▶ 慢放跳轉」。點擊按鈕自動精準定位至該階段並以 0.5x 慢動作播放。
4. **P3 Priority Fix 唯一改善重點與 Drill 練習**：`PASS`
   - 智慧演算法過濾選定單一最核心改善項目，提供「體感口訣」、「三步驟 Drill 練習」與「下次量化目標」。
   - 恪守最高誠信原則：嚴禁推論未經雷達量測之球速、桿頭速度、飛行距離、甜蜜點、桿面角與 3D 角度。
5. **WebKit 原生端到端 GUI 實測**：`PASS`
   - 執行 `scripts/verify_webkit_r3_slowmo_and_coach.py`，6/6 步驟全數通過。
   - 雙影片 0.5x 慢動作同步播放推進流暢，Top/Impact 停格對齊誤差 0ms，Priority Fix 卡片與姿勢比較表成功渲染。
   - 驗收報告存於 `docs/reports/swing_comparison_r3_report.json`。
6. **全套後端測試套件**：`PASS`
   - 執行 `uv run pytest tests/` 全數 PASSED。
- **最後更新時間**：2026-10-30T03:10:00+08:00
- **當前分支**：`feat/r3-offline-coach-and-slow-motion`
- **正式判定**：**READY FOR PR REVIEW (嚴禁自行合併 main，等待使用者授權)**

## 前期重大里程碑狀態（Round 17: PR #2 正式授權合併、Mac 原生 App 更新與 Personal Beta 正式部署）
1. **GitHub PR #2 Squash and Merge**：`PASS`
   - 依專案負責人明確授權，執行 `gh pr merge 2 --squash`。
   - PR #2 成功合併至 `main` 分支。
   - GitHub Merge Commit SHA：`8e369b47c841b6c286a8905fc15b5a98300b75de`。
   - 本機 `main` 分支已完全同步至最新 HEAD，零二進制媒體殘留進入歷史。
2. **Mac 原生 App 重新編譯與安裝**：`PASS`
   - 執行 `scripts/build_mac_app.sh`，使用 `clang` 編譯原生 arm64 Mach-O 二進制 Launcher (`GolfSwingLab`)。
   - 封裝並安裝至 `/Applications/Golf Swing Lab.app`。
   - 通過 macOS Ad-hoc codesign 驗證與 LaunchServices 註冊。
3. **Reference Library 18 筆資料與檔案完整性核對**：`PASS`
   - 執行 `scripts/verify_18_reference_swings.py` 逐筆驗證資料庫與儲存庫。
   - 18 筆示範檔案全數存在、`ffprobe` 100% 成功解碼（0 缺失、0 解碼錯誤）。
   - 16 支正式 bundle 中：11 支 `confirmed_strike`（來源 `developer_visual_annotated`），5 支 `impact_estimated`（來源 `estimated`），0 支 `unresolved`。
   - 2 支既有 fixture 為 `confirmed_strike`（`fixture_default`）。
   - 18 筆示範皆具備可靠同步錨點（`impact_ms > top_ms`）。
   - 產出詳細驗證報告 `docs/reports/reference_library_18_verification.json`。
4. **前端與後端服務驗收**：`PASS`
   - Next.js 15.5.28 正式建置通過（9/9 靜態路由編譯無誤）。
   - 後端 FastAPI (port 28000) 與前端 Next.js (port 23000) 最新 main 程式碼熱啟動，`/healthz` 與 `/readyz` 100% 通過。
5. **WebKit 原生 GUI 端到端驗收**：`PASS`
   - 執行 `scripts/verify_webkit_comparison_and_coach.py`，12/12 步驟全數通過（PASS）。
   - 雙影片同步播放時鐘漂移僅 2.6ms（遠低於 150ms 閾值），Top/Impact 跳轉精準度誤差 0ms。
   - 左右並排與上下堆疊兩側均非黑畫面（User mean 111.5, Ref mean 135.0）。
   - 驗收報告 `docs/reports/swing_comparison_r2_report.json` 脫敏完成，Token 零洩漏。
6. **全套後端測試套件**：`PASS`
   - 執行 `uv run pytest tests/`：**95 / 95 PASSED (100%)** in 216.56s。
- **最後更新時間**：2026-10-30T02:12:00+08:00
- **當前分支**：`main`
- **當前 Commit**：`8e369b47c841b6c286a8905fc15b5a98300b75de`
- **正式判定**：**GOLF SWING LAB R2 — PERSONAL BETA DEPLOYED**

## 前期重大里程碑狀態（Round 16: PR #2 最終合併前素材清理與 Git 差異純淨化）
1. **P0 移除依然追蹤的示範媒體與截圖**：`PASS`
   - **本機永久安全保留**：將 `assets/reference_videos/` 內 12 個檔案（含 2 支舊測試 MP4 與 10 張縮圖）完整備份至 `~/.golfswinglab/assets_reference_videos_backup/`；將包含使用者/第三方原片影格的 15 張 WebKit 快照備份至 `~/.golfswinglab/webkit_r2_screenshots/`。
   - **自 Git 追蹤乾淨移除**：執行 `git rm --cached` 移除這 12 個媒體檔案與 `docs/screenshots/webkit_r2/` 全部 15 張截圖，從 PR 發行差異中徹底排除未授權再散布影像。
   - **防護規則持久化**：更新 `.gitignore` 加入 `assets/reference_videos/*.mp4`, `*.jpg`, `*.png` 與 `docs/screenshots/webkit_r2/`，杜絕再次提交。
   - **發行差異純淨化**：實測 `git diff main assets/ docs/screenshots/webkit_r2/` 輸出為空（差異完全為 0），PR 合併至 main 時零二進制冗餘素材。
2. **P0 腳本無素材安全跳過防護**：`PASS`
   - 更新 `scripts/seed_reference_library.py`，當工作目錄不存在內建 MP4 時，明確日誌輸出並優雅跳過（Exit Code 0），不影響 Docker 部署或無素材環境執行。
3. **P0 本機 Storage 與串流播放驗證**：`PASS`
   - 核驗本機 `~/.golfswinglab/storage/references/` 下 16 支正式示範影片 100% 存在且大小健全。
   - 透過 API 實測 7I、Driver、3W 的 HTTP 206 Partial Content Range 串流，均回傳 HTTP 206 OK。
4. **P1 精度成果與資料庫一致性百分之百鎖定**：`PASS`
   - 資料庫、API 與報告維持 0ms 漂移一致性（`tests/test_reference_events_consistency.py` 5/5 PASSED）。
   - 11 支 `confirmed_strike`（來源標記 `developer_visual_annotated`）、5 支 `impact_estimated`（含 03_Wood5 30fps 快門間隙出球 Frame 38 1267ms 診斷結論）、0 支 `unresolved`。
5. **全量品質保證驗收**：`PASS`
   - 後端測試套件：**95 / 95 PASSED (100%)** in 220.91s。
   - 前端 Next.js 15.5.28 建置：**9/9 靜態路由 0 錯誤**。
   - WebKit 原生 GUI 端到端實測：12/12 步驟全數通過（時鐘同步漂移僅 2.9ms，Top/Impact 誤差 0ms，雙側非黑畫面 Mean 111.5 / 135.0，Token 零洩漏）。
- **最後更新時間**：2026-10-29T17:35:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`
- **合併判定**：**READY FOR PERSONAL BETA MERGE**（請使用者於 GitHub PR #2 點選 Squash and merge，嚴禁自行合併 main）。

## 前期重大里程碑狀態（Round 15: PR #2 資料一致性、真值擊球確認、本機素材隔離與個人 Beta 釋出治理）
1. **P0-1 驗證時間碼單一事實來源寫回資料庫**：`PASS`
   - **徹底消除報告與資料庫時間碼漂移**：建立單一權威事實來源字典 `STRIKE_EVIDENCE_MAP`，將審查確認之 Top 與 Impact 錨點直接綁定為 active events，並在 `scripts/verify_reference_events_and_generate_sheets.py` 中 100% 寫回 PostgreSQL。
   - **完全保留原始 Candidate Events**：`calibration_params["candidate_events"]` 忠實記錄初始粗估值，`calibration_params["active_events"]` 與 `event_timestamps` 100% 同步且誤差為 **0ms**。
   - **資料庫筆數與 ID 恆定**：示範影片記錄恆定為 18 筆（16 支新 bundle + 2 支既有 fixture），維持原有 UUID，無重複記錄或垃圾資料膨脹。
   - **自動化一致性回歸測試**：撰寫 `tests/test_reference_events_consistency.py`（5 項專案測試），逐支核驗 16 支影片之 DB、報告與 `/api/reference-swings`，測試結果 **5 / 5 PASSED (100%)**。
2. **P0-2 擊球確認真值分類與 5W 快門間隙診斷**：`PASS`
   - **移除按球桿名批量推論邏輯**：嚴格依真實影像證據判定，16 支影片分類為：
     - `confirmed_strike`（11 支，68.8%）：桿頭過球與小白球飛出瞬間清晰可見（01_Driver, 02_Wood3, 07_Iron4, 08_Iron5, 09_Iron6, 10_Iron7, 11_Iron8, 12_Iron9, 15_SW, Bonus Driver TW, Bonus Driver WAX）。
     - `impact_estimated`（5 支，31.2%）：5W (快門間隙出球)、13_PW (後斜非正 DTL)、16_LW (後斜高拋非全揮桿)、17_Putter (特寫無全身)、Bonus SW Bunker (炸沙擊球)。
     - `unresolved`：0 支。
   - **03_Wood5.mp4 專項影格診斷**：實測解碼 Frame 37 (1233ms) 桿身在腰部下桿中段，Frame 38 (1267ms) 桿頭接近球位，Frame 39 (1300ms) 球已飛出。確認擊球發生於 30fps 快門間隙，時間碼校正為 Frame 38 (1267ms)，標記為 `impact_estimated`，徹底排除假 confirmed。
   - **Contact Sheet 文字標籤反映真實狀態**：第 8 格清晰標註 `8. [CONFIRMED_STRIKE]` 或 `8. [IMPACT_ESTIMATED]`。
3. **P0-3 隔離本機素材與 Git 追蹤清理**：`PASS`
   - **本機永久安全備份**：16 張 Contact Sheet JPG 已安全備份至 `~/.golfswinglab/reference_contact_sheets/`，資料庫備份保存於 `~/.golfswinglab/backups/reference_swings_backup.json`，絕不遺失。
   - **Git 追蹤清理與忽略**：以 `git rm --cached` 移除 `docs/reports/reference_contact_sheets/*.jpg` 與 `docs/reports/reference_swings_backup.json`，並更新 `.gitignore`。
   - **PR 分支歷史評估**：嚴格禁止 Force Push 與 Hard Reset，在最新 Commit 中乾淨移除追蹤；評估既有歷史 Commit 殘留素材僅佔用數 MB，不影響程式碼運作，建議合併時在 GitHub 採用 **Squash and merge**，將整個 PR 壓縮為單一乾淨 Commit 進入 main。
4. **WebKit 原生 GUI 雙影片比較端到端驗收**：`PASS`
   - 執行 `scripts/verify_webkit_comparison_and_coach.py` 12 步驟全數通過（Top/Impact 誤差 0ms、兩側解碼非黑畫面 Mean 111.5 / 135.0、時鐘同步漂移僅 2.5ms、Token 零洩漏）。
5. **全量品質保證驗收**：`PASS`
   - 後端測試套件：**95 / 95 PASSED (100%)** in 200.41s。
   - 前端打包：Next.js 15.5.28 **9/9 靜態路由 0 錯誤**。
- **最後更新時間**：2026-10-29T16:48:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`
- **合併判定**：**READY FOR PERSONAL BETA MERGE**（請使用者於 GitHub PR #2 點選 Squash and merge）。

## 前期重大里程碑狀態（Round 14: 16 支示範影片真實事件影格驗證、Contact Sheet 生成、安全備份與可信度修復交付）
1. **P0-A 16 支影片真實事件影格驗證與視覺接觸表生成**：`PASS`
   - **實體逐幀解碼運動學驗證**：撰寫並執行 `scripts/verify_reference_events_and_generate_sheets.py`，真正解碼 16 支 MP4，檢驗手腕最高 $y$ 極小值（Top 頂點與轉換啟動）與擊球區桿頭過球（Impact 觸球出球）。
   - **產出 16 張 3x3 高解析 Contact Sheet**：全部存於 `docs/reports/reference_contact_sheets/*.jpg`，並產出結構化檢驗總報告 `docs/reports/reference_events_verification.json` 與 Markdown 審查報告 `docs/reports/reference_events_verification.md`。
   - **重大錯誤修正（5W 重新校準）**：查明先前 03_Wood5 裁切區間誤切入 18.6s~24.0s 口播廣告，重新校準為第 1 記真實揮桿（`0ms ~ 3600ms`，Top 867ms, Impact 1233ms, Downswing 366ms），恢復高品質全揮桿。
   - **事件來源誠信標記**：嚴格標註 `event_sources` 為 `developer_visual_annotated` 或 `estimated`，絕不將自我校驗偽稱為第三方雙盲 Ground Truth。
2. **P0-B 六維度狀態旗標修正與節奏保護**：`PASS`
   - **擊球狀態統計**：Confirmed Strike 15 支 (93.8%)，Impact Estimated 1 支 (6.2%，17_Putter 特寫無出球視角)。
   - **事件可靠度**：14 支可信全揮桿與劈起/高拋/沙坑 (87.5%)；17_Putter 誠實標記 `events_reliable = False`。
   - **節奏保護**：慢動作示範（3W, 6I, SW）標記 `supports_realtime_sync = False`、`supports_phase_sync = True`，防止自然 1:1 時鐘被拉偏。
   - **單球裁切完整性**：16/16 (100%) 通過，排除標題字卡、跨球與口播。
3. **P0-C 資料庫安全備份與冪等更新**：`PASS`
   - 執行前自動將 18 筆既有資料安全備份至 `docs/reports/reference_swings_backup.json`。
   - 以 `(source_sha256, club_type, source_start_ms, source_end_ms)` 與既有 ID 嚴格雙向錨定，原地 UPDATE，保證 UUID 100% 恆定，無孤兒數據。
   - 版本持久化為 `clip_version = '2.2.0'`、`analysis_version = 'pose-v1-visual-audit'`。
4. **P1-A WebKit 雙影片比較端到端驗收更新**：`PASS`
   - 執行 `scripts/verify_webkit_comparison_and_coach.py` 12 步驟全數通過（Top/Impact 誤差 0ms、兩側解碼非黑畫面 Mean 111.5 / 135.0、時鐘同步漂移 2.8ms、Token 零洩漏）。
   - 產出 11 張 GPU 快照與脫敏結構化報告 `docs/reports/swing_comparison_r2_report.json`。
5. **全量品質保證測試**：`PASS`
   - 後端測試：**90 / 90 PASSED (100%)** in 211.88s。
   - 前端打包：Next.js 15.5.28 **9/9 靜態路由 0 錯誤**。
- **最後更新時間**：2026-10-29T16:05:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`

## 前期重大里程碑狀態（Round 13: 16 支示範影片獨立精度修復與真實 FPS 步進全面通過）
1. **P0 根除固定假時間碼與真實運動學狀態機定位**：`PASS`
   - **徹底根除寫死偏移**：移除了先前所有寫死之固定偏移量（Top+300ms、慢動作Top+1200ms、時長百分比）。
   - **真實狀態機與運動學定位**：採用 `CoarseToFineDetector` 狀態機與 2D 骨架手腕物理軌跡（Top 頂點手腕最高 $y$ 局部極小值、Impact 觸球區）真實定位。
   - **6 維度狀態持久化**：封裝並持久化 `media_processed`, `pose_analyzed`, `is_valid_clip`, `events_reliable`, `supports_realtime_sync`, `supports_phase_sync` 於 `calibration_params` 與 API 頂層欄位。
2. **P0 重新確立乾淨單球邊界**：`PASS`
   - 逐支重新檢查全部 16 支 MP4，確立乾淨單球邊界（Address 前站定緩衝 -> 上桿 -> Top -> 擊球 -> 收桿平衡 Finish），徹底排除跨球、走動、口播或標題卡。
   - 7I 示範片截取 DJ Watts 第 2 球乾淨單球（`13600ms ~ 17600ms`，Top 14967ms 映射為 1367ms，Impact 15300ms 映射為 1700ms，Downswing 333ms，手腕最高點 $y=0.315$，擊球點 $y=0.504$）。
3. **P0 冪等更新機制與資料清理**：`PASS`
   - 以 `(source_sha256, club_type, source_start_ms, source_end_ms)` 與邏輯對照為依據原地更新既有記錄，徹底清理 3 筆歷史舊假數據，資料庫無垃圾 UUID 膨脹。
4. **P1 逐格控制依據真實 FPS**：`PASS`
   - `SwingComparisonPlayer.tsx` 移除固定 33.333ms，改依兩側各自真實 FPS 計算單影格步進（$\Delta t = 1/\text{FPS}$），按鈕動態呈現對應毫秒數。
5. **P1 球桿覆蓋率與缺桿誠信標記**：`PASS`
   - 完整支援 19 類球桿，缺少 6 桿（7W, 3H, 4H, 5H, 3I, GW/AW）誠實標示 `missing_reference`，絕不拿通用 Hybrid 混充 3H/4H/5H。
   - 示範影片資訊列加入六維度技術狀態徽章。
6. **全鏈路驗收與 WebKit 實測**：`PASS`
   - WebKit 原生 GUI 12 步驟端到端實測 100% 通過（Top/Impact 誤差 0ms、兩側解碼非黑畫面、同步時鐘漂移 2.4ms、無任何 Token 洩漏）。
   - 後端全量測試：**90 / 90 PASSED (100%)** in 202.29s。
   - 前端打包：Next.js 15.5.28 **9/9 靜態路由 0 錯誤**。
- **最後更新時間**：2026-10-29T13:25:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`

## 前期重大里程碑狀態（Round 12: PR #2 最後視覺驗收與 Beta 收斂 — 全流程實測通過）
1. **P0-1 真正證明雙影片同步播放成功**：`PASS`
   - **黑畫面真實根因排查與徹底修復**：查明先前本地 NVMe 存儲缺失 `video_2min.mov` 與 `proxy.mp4` 導致串流 404 Not Found 之根因。實體還原真實 139 秒 iPhone 錄影 (`4993a3b6...`)，生成 Safari 相容之 30fps H.264 proxy.mp4 (57MB) 與縮圖，驗證 HTTP 206 Partial Content Range 串流成功。
   - **單一 DOM 樹架構重構**：重構 `<SwingComparisonPlayer>` 為單一 DOM 容器，佈局切換（左右並排 / 上下堆疊 / 疊影對照）時使用 CSS 控制顯示，**不銷毀重建 `<video>` 節點**，徹底消除了切換佈局導致解碼器 buffer 重置與黑畫面的缺陷。
   - **Canvas 畫素非黑畫面驗證**：在 WebKit 中實時以 32x32 Canvas 取樣計算兩側影片畫面之像素平均亮度 (Mean) 與標準差 (Std)。實測個人影片 Mean=111.5, Std=64.5，示範影片 Mean=115.8, Std=64.4（遠大於黑畫面門檻 Mean>5.0, Std>2.0），客觀證明兩側皆非黑畫面且畫面具有高度動態色差細節。
   - **播放中截圖與解碼推進**：點擊「雙影片同步播放」，等待 1.2 秒後在**播放進行中**擷取快照 (`04_comparison_playing_side_by_side.png`)。實測個人揮桿時間自 120.034s 前進至 121.044s (Δ=1.010s)，示範影片時間自 0.957s 前進至 1.959s (Δ=1.002s)，時鐘同步漂移僅 **8.1ms** (遠低於 150ms 門檻)。
   - **上下堆疊切換與播放中截圖**：切換為上下堆疊佈局，在播放進行中擷取快照 (`05_comparison_playing_stacked.png`)，DOM flex-col 正常且影片持續流暢解碼。
   - **TOP / IMPACT 錨點跳轉與重設 Bug 修復**：查明先前 `useEffect` 因依賴 `computeExpectedRefMs` 在錨點切換時過度觸發並將示範片重設回 0 秒之根因，修正為 `prevSwingKeyRef` 守衛並於 `jumpSyncAnchor` 直接傳入 anchor 計算目標時間。實測點擊 TOP 錨點跳轉（User=120600ms, Ref=1533ms，誤差 0ms），點擊 IMPACT 錨點跳轉（User=120967ms, Ref=1900ms，誤差 0ms），快照 `06_comparison_jump_top.png` 與 `07_comparison_jump_impact.png` 精準呈現頂點與擊球瞬間。
2. **P0-2 移除假 PASS 與動態脫敏報告**：`PASS`
   - **移除寬鬆 fallback**：徹底移除 `else "PASS" if has_comp_header else "FAIL"`，所有斷言（解碼進展、非全黑畫面、尺寸、漂移）嚴格檢驗，未達標一律 FAIL。
   - **動態驗收報告**：報告 `docs/reports/swing_comparison_r2_report.json` 包含 Git SHA (`9ac6b3ed...`)、Dirty 狀態、時間戳、影片 SHA-256、解碼狀態、兩側尺寸與同步漂移。
   - **全面脫敏安全**：所有 URL 之 `token` 均替換為 `[REDACTED]`，杜絕任何 Token 洩漏。
3. **P0-3 示範影片真偽及 UI 語意一致**：`PASS`
   - 取消將 7I `test_fixture` 顯示為「標準參考」，改為「技術測試基準 (7I)」或中立的「揮桿雙影片對照」。
   - 統計區塊明確區分三態：可用示範影片 2 / 17、全身姿勢比對 1 / 17、已驗證職業標準示範 0 / 17（尚無）。
4. **P1 AI 教練功能誠實標示**：`PASS`
   - 規則式分析明確標記幾何提示與「ℹ️ 規則式幾何運動學引擎生成 (未調用多模態 AI 影像模型)」。
   - 杜絕不可觀測之物理因果臆測。
5. **P1 示範影片素材管理與串流匯入**：`PASS`
   - 更新 `docs/REFERENCE_CLUB_LIBRARY.md`，清楚列出 4 種分類現狀。
   - 示範影片上傳與本地匯入全面改為 `storage.put_file` 串流拷貝，徹底解決 500MB 大檔整支讀入記憶體 OOM 問題。
6. **全鏈路驗收證據**：`PASS`
   - 後端測試套件：**90 / 90 PASSED (100%)** in 214s。
   - 前端打包：Next.js 15.5.28 **9/9 靜態路由頁面 0 錯誤**。
   - WebKit 原生 GUI 驗收：`scripts/verify_webkit_comparison_and_coach.py` 9 大步驟全數 PASS，產出 8 張真實 GPU 渲染截圖與結構化脫敏報告。
- **最後更新時間**：2026-10-29T02:48:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`

## 前期重大里程碑狀態（Round 11: PR #2 Independent Audit Remediation — 解除 NO-GO 判定）

## 前期重大里程碑狀態（Round 10: Swing Comparison & Evidence-Based Coaching R2）
1. **P0 單球播放器修復與體驗升級**：`PASS`
   - **自然結束重播機制**：影片自然結束或進度條拖曳至末端後，點擊 Play 自動重設回 `start_ms / 1000` 並從頭流暢起播，解決舊版畫面卡死問題。
   - **顯著重播與循環控制**：新增顯著「↺ 重新播放 (Replay)」與「⟲ 循環播放 (Loop)」Toggle 按鈕（預設關閉，開啟時呈翡翠綠發光標記）。
   - **真實 FPS 逐幀步進與邊界防呆**：逐幀步進嚴格依據影片真實 FPS（30fps 每次 `±33.3ms`，5f 每次 `±166.7ms`），並嚴格鎖定在 `[start_ms, end_ms]` 區間內，絕不溢出至前後其他球。
   - **時間軸與事件動態跟隨**：新增青光進度條與階段游標；9 大事件按鈕隨時間碼動態高亮青光指示燈；未確認擊球標註「推估擊球瞬間」與信心度。
2. **P1 專業揮桿比較 (Professional Swing Comparison)**：`PASS`
   - **17 種完整球桿分類支援**：資料模型與前端全數支援 `Driver`, `3W`, `5W`, `3H`, `4H`, `5H`, `4I`, `5I`, `6I`, `7I`, `8I`, `9I`, `PW`, `GW/AW`, `SW`, `LW`, `Putter`。
   - **示範影片資料庫模型與 API**：新增 `ReferenceSwing` 模型、PostgreSQL 資料表與完整 REST API (`/api/reference-swings`, 支援 HTTP 206 Partial Content Range 串流與本機匯入)。
   - **標準素材庫與誠信原則**：從標準原片中精準裁切 7I DTL 高清示範影片 (`ref_7i_dtl_standard.mp4`, 1080x1920 60fps) 作為基準；Driver 擊球特寫影片標記 `close_up` 與 `verified=false` 並觸發視角差異警示；其餘 15 種球桿誠實標記 `missing_reference`，絕不將鐵桿冒充其他球桿，並提供手動匯入引導。
   - **雙影片比較播放器組件 (`<SwingComparisonPlayer>`)**：支援左右並列 (side-by-side)、上下堆疊 (stacked)、半透明疊影 (ghost overlay)。
   - **揮桿同步引擎 (`SwingSynchronizationEngine`)**：支援 Mode A（自然節奏，保留原始速度，依 Impact 或 Top 錨點對齊）與 Mode B（動作階段分段線性對齊）；提供等比例 Auto-Framing 縮放與置中（保護身體不被拉伸）以及手動微調。
3. **P2 動作差異分析 AI Coach (Evidence-Based Action Differences)**：`PASS`
   - **移除空泛分數卡片**：將原先大篇幅生硬分數改為精煉的「動作差異分析」卡片（最多 1~2 項具有真實影像證據之具體動作差異）。
   - **精準影格對齊**：每項標明關鍵階段標籤 (`[TOP]`, `[IMPACT]`)、時間碼（如 `120600ms`）、偏差幅度（如 `前傾角變化 9.4°` 或 `上下桿比例 2.00:1`）與客觀影像測量證據。
   - **一鍵跳轉對齊**：提供「🎯 影格 ({time_ms}ms)」按鈕，點擊後單球播放器立即跳轉至該關鍵影格。
   - **深入分析此差異 (Vision AI 解讀)**：提供專屬非同步分析按鈕與 API (`POST /api/swings/{id}/deep-insight`)，展開運動學深度解析報告（2D 骨架關節運動趨勢、動力鏈影響、分步 Drill 課表、最高誠信原則免責聲明）。
4. **全鏈路驗證證據**：`PASS`
   - 後端專項測試：`tests/test_swing_comparison_and_coach.py` 4/4 PASSED (100%)。
   - 回歸測試：26/26 PASSED (100%)。
   - 前端打包：`npm run build` 9/9 靜態路由 0 錯誤。
   - WebKit 原生 GUI 驗收：`scripts/verify_webkit_comparison_and_coach.py` 6 大步驟全數 PASS，生成 6 張真實 GPU 渲染截圖與結構化 JSON 報告。
   - 文件產出：`docs/REFERENCE_CLUB_LIBRARY.md` 與 `docs/reports/swing_comparison_r2_report.json`。
- **最後更新時間**：2026-10-28T20:41:00+08:00
- **當前分支**：`feat/swing-comparison-and-evidence-coach`

## 前期重大里程碑狀態（Round 9: 大影片分段上傳與登入憑證失效處理修復）
1. **P0 大檔案（1.38GB）分段上傳 85% 失敗根因與修復**：`PASS`
   - **根本原因**：Docker Desktop 虛擬機磁碟空間被多專案映像檔佔滿（剩餘 257MB），MinIO 寫入時觸發 `XMinioStorageFull`。舊版 `HybridStorageService` 在捕獲 S3 錯誤後錯誤地將後續分段寫入 LocalStorage，造成分段在 S3 與本地兩端分裂；當前端呼叫 `/complete` 時，在本地端找不到前面的分段而拋出 `FileNotFoundError`。
   - **分段上傳單一物理後端綁定**：徹底移除 `put_part_bytes` 與 `complete_multipart_upload` 的非法降級邏輯，新增 `_get_backend_for_upload(s3_upload_id)`，以 `upload_id` 嚴格綁定單一存儲後端（`local_up_` 開頭走 LocalStorage，其餘走 S3/MinIO），杜絕分段分裂。
   - **啟用 Mac 本機 NVMe 大容量存儲模式**：更新 `apps/api/config.py`，支援 `LOCAL_STORAGE_DIR`（預設為 `~/.golfswinglab/storage`，享有 160GB+ 高速空間），繞過 Docker VM 磁碟配額限制。
   - **雙向向後相容讀取 Fallback**：在 `head_object`、`download_to_path`、`get_object_range`、`generate_presigned_get_url` 加入雙向 fallback。既有存在 MinIO 的 340 筆歷史場次影片無縫串流，新上傳影片全數寫入本地高速磁碟。
   - **端到端實測**：使用真實 24MB iPhone MOV 影片（分 5 段）發起完整 multipart 流程，上傳、分段合併、ffprobe 解析、背景 Worker 分析（100% 完成度，耗時 9.9 秒）與 HTTP 206 Range 串流讀取 100% 驗證通過。
2. **P0 舊憑證失效與首頁錯誤導航修復**：`PASS`
   - **根本原因**：金鑰輪替後，使用者瀏覽器 LocalStorage 仍殘留舊 Token。API 回傳 401（message: `登入憑證簽章驗證失敗`），前端先前的檢查為 `String(err.message).includes("401")`，因中文訊息未帶有 401 字樣而未被攔截，停留在無資料畫面並顯示紅色錯誤。
   - **前端自動清理與登入導引**：在 `apps/web/src/lib/api.ts` 的 `apiFetch` 中攔截 `res.status === 401`，自動調用 `clearAuthToken()` 清除無效 Token 並重定向至 `/login?expired=1`；在 `apps/web/src/app/page.tsx` 中增加對 401 狀態碼與中文憑證錯誤的匹配跳轉，並在錯誤介面新增「重新登入」與「重新整理」按鈕。
3. **全鏈路與回歸品質保證**：`PASS`
   - 後端測試套件：核心測試全數通過（單元、整合、動作評分、Swing 10 回歸）。
   - 前端打包：Next.js 15.5.28 **9/9 靜態路由頁面 0 錯誤**。
   - 服務健康度：`/healthz` (200 OK), `/readyz` (postgres: true, redis: true, storage: true)。
- **最後更新時間**：2026-10-28T19:25:00+08:00
- **當前分支**：`main`
- **正式驗收證據**：真實 iPhone 11s.mov 5 分段上傳合併分析串流驗收通過、Next.js 9/9 靜態頁面編譯通過

## 前期重大里程碑狀態（Round 8: PR #1 Final UI Event Verification & Local Secret Fail-Closed Gate）

## 前期重大里程碑狀態（Round 7: PR #1 Final Security & Visual Smoke Gate）

## 前期重大里程碑狀態（Round 6: Beta Release & Merge Preparation）

## 前期重大里程碑狀態（Final Reliability Gate）
1. **P0-1：Top 重對齊邏輯修復與候選順序不變性**：`PASS`
   - 修復 `packages/analysis/events/state_machine.py` 中 `_validate_and_realign_swing_timing` 的迴圈變數洩漏問題（原使用迴圈最後殘留的 `zc_bonus`，修正為追蹤最佳候選 `best_cand` 自身之 `best_cand_has_zc` 與運動學特徵）。
   - 新增 `test_top_realignment_candidate_order_invariance_and_zc_isolation` 單元測試，驗證候選順序反轉或變更時，最佳 Top 候選判定 100% 一致。
   - 尊重 180–650ms 作為常見參考，無客觀證據時不強行將不可靠事件移入正常區間。
2. **P0-2：切球成功率五維度獨立拆分與分類感知驗收**：`PASS`
   - 重構 `packages/analysis/evaluation/golden_eval.py` 與 `tests/test_r2_long_video_accuracy.py`，將單一 IoU 評估拆分：
     1. 候選片段偵測率（Candidate Window Detection Rate）：100.0% (12/12)
     2. 動作分類正確率（Action Classification Accuracy）：100.0% (12/12)
     3. 擊球專項 Recall / Precision（Valid Swing Specific）：Recall 100.0% / Precision 100.0%
     4. 關鍵事件定位品質（Top, Impact, Finish 定位誤差分佈）
     5. 真球起飛確認率（Confirmed Strike Rate）與邊界誤差（Boundary Error Median 894.5ms，保留安全緩衝區間）
   - 嚴格同步註解與 assert 門檻（Recall >= 0.90, Precision >= 0.85），絕不用較低門檻冒充達標。
3. **P0-3：異常時序自主降級與不可評分保護**：`PASS`
   - 審核 2 分鐘影片逐球表現：Ball 1 (1783ms)、Ball 6 (2118ms)、Ball 11 (2233ms)、Ball 12 (783ms) 存在起桿前長試擺或停頓。
   - 局部重分析若無法將時序收斂至生理範圍，標記 `timing_anomaly_detected`，`review_status` 降級為 `needs_review`，旗標加入 `timing_anomaly`。
   - `compute_observable_metrics` 依誠信原則將 `downswing_ms`、`backswing_ms` 與 `backswing_downswing_ratio`（tempo）的 `value` 設為 `None`，絕不捏造不可靠分數。
4. **P0-4：局部高 FPS 精修影格傳遞與時序防呆（Finalized Event Frame Mapping）**：`PASS`
   - `_refine_event_local_high_fps` 增強 Impact 減速峰值門檻，精修結果若違反生理下桿極限則保守拒絕，保留真實事件。
   - 精修產生的高 FPS 真實影格 (`FramePoseResult`) 封裝傳遞至 `finalized_event_frames`，優先供 `compute_observable_metrics` 與 Keyframe 提取使用，杜絕影格與 PTS 時間碼脫節。
5. **真球升空相鄰影格時間連續性強化**：`PASS`
   - `analyze_ball_launch_continuity` 要求至少存在一對時間連續相鄰（$\Delta t \le 55\text{ms}$）且位移遞增/高度遞減的連續 2 影格觀測點，杜絕時間不相鄰的兩點誤判。
6. **全量品質與回歸驗證**：`PASS`
   - 後端全量測試：**58 / 58 PASSED (100%)**（包含全新 8 項專項測試與真實長短片基準測試）。
   - 前端打包：`npm run build` 9/9 靜態路由頁面打包成功（0 錯誤）。
   - 正式真值校驗：`tests/golden/real_2min_session_gt.json` SHA-256 0 污染。
- **最後更新時間**：2026-10-21T20:28:00+08:00
- **最新驗收報告**：`docs/FINAL_RELIABILITY_GATE_REPORT.md` 與 `docs/TEST_REPORT.md`

## 前期重大里程碑狀態（Auto Precision & Clean Motion UI Redesign）
1. **多訊號融合自動事件判定（Multi-Signal Event Detection）**：`PASS`
   - 重構 `SwingPhaseStateMachine` 與 `scanner.py`，整合手腕速度零交越、Top Pause 最小速度、肩部/骨盆旋轉反轉、下桿制動峰值、48kHz 音訊瞬態衝擊（0.18s 極速抽取）與真球出發點。
   - 每個偵測事件包含客觀來源 (`detection_sources`) 與合理不確定區間 (`uncertainty_ms`)，擊球狀態標示為 `confirmed_strike` 或 `estimated_strike`。
2. **Waggle / Practice Lift 抑制機制（Settled Address Anchor）**：`PASS`
   - 辨識起桿前微小晃動、試擺與靜止等待，鎖定起桿前最後靜止基準點（Settled Address），徹底排除瞄球微晃動與前置假動作，鎖定真實上桿發起點。
3. **極簡動態輔助線 Clean Motion UI（CleanMotionOverlay）**：`PASS`
   - 全新獨立組件 `apps/web/src/components/CleanMotionOverlay.tsx`，徹底解決五顏六色骨架與繁雜輔助線問題。
   - 預設「AI 教練模式」最多同時顯示 2 個標記，依 Address/Top/Downswing/Impact/Finish 自動流轉主題：
     - Address：金黃色站姿穩定框（頭部/臀部）與脊椎軸線
     - Top：手腕頂點位置與轉肩參考線
     - Downswing：手部動態路徑（$t \le \text{currentTime}$，不劇透未來）
     - Impact：桿身釋放平面與出球觀測點（嚴守誠信原則：無真球不畫假球軌）
     - Finish：收桿平衡金黃色垂直平衡軸
   - 徹底移除直接疊在人體關節上的交錯文字標籤與左上角常駐 5 色圖例，資訊移至底部 Coach HUD 提示列。
   - 統一色彩語義：青綠觀測點 (`#00f5d4`)、金黃站姿參考 (`#ffd166`)、亮紅超標警示 (`#ff5470`)。
   - 保留「專業模式 (Pro Mode)」開關，供深度分析者自選 33 點完整骨架、雙色手部軌跡、Tush Line 與即時數值儀表板。
4. **個人化體感教練體驗升級**：`PASS`
   - 單球側邊欄自動提煉每球最關鍵 1~2 項體感動作核心問題（如：骨盆旋轉不足、收桿提前煞車、頭部側移），並配對 2 項針對性實體自主 Drill。
5. **逐幀播放器與視覺同步**：`PASS`
   - 支援 `requestVideoFrameCallback` 零延遲繪製對齊，支援精確 `±1f / ±5f` 步進控制。
6. **全量品質與回歸驗證**：`PASS`
   - 後端全量測試：**45 / 45 PASSED (100%)** in 177.49s（包含真實 11 秒短片與 2 分鐘 139 秒長片 12/12 切球測試全數通過）。
   - 正式真值校驗：`tests/golden/real_2min_session_gt.json` 於測試前後 SHA-256 恆為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`（0 污染）。
   - 前端打包：`npm run build` 9/9 靜態路由頁面打包成功。
   - 視覺存證：改版前後各階段畫面截圖完整留存於 `docs/screenshots/baseline_clean_redesign/` 與 `docs/screenshots/redesign_clean_motion/`。
- **最後更新時間**：2026-10-21T12:00:00+08:00
- **最新驗收報告**：`docs/CLEAN_MOTION_REDESIGN_REPORT.md`、`docs/R13_GOLDEN_INTEGRITY_REPORT.md` 與 `docs/TEST_REPORT.md`

## 前期重大里程碑狀態（R13.1: Final Integrity Hotfix）
1. **P0-1 前後端事件契約與狀態完全統一**：`PASS`
   - 後端統一以 `status` (machine_suggested / human_verified / uncertain)、`source`、`frame`、`verified_at` 為權威契約。
   - 前端 `/audit` 修正舊欄位誤用，支援即時人工確認標記、影格號顯示、更新時間戳記與相對演算法原始值的偏移量（`Δ +xx ms (+xf)`）。
   - 經瀏覽器實測驗證，確認後重新整理頁面狀態持久保留，微調按鈕與 Snap 音訊吸附即時反映。

2. **P0-2 禁止測試污染正式 Golden Set 與完整 Round-Trip 重置**：`PASS`
   - 備份正式真值檔至 `tests/golden/backups/real_2min_session_gt.backup.json`，清理先前殘留之 6 筆測試 history，鎖定乾淨真值基準 SHA-256 為 `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`。
   - 所有具寫入行為之 API 與整合測試全面改用 pytest `tmp_path` 與 FastAPI `dependency_overrides[get_audit_registry]`，正式檔案在測試執行前後 SHA-256 保持完全一致（0 污染）。
   - 修復 `reset_swing_to_machine()`，重置時完整同步恢復 `events` 內部時間與影格、頂層快捷欄位 (`impact_ms` 等)、`start_ms`/`end_ms`、`downswing_ms`/`backswing_ms` 與 `tempo_ratio`，Round-Trip 測試 `test_golden_set_reset_round_trip` 實測 100% 通過。

3. **P0-3 嚴格修正 Event Accuracy 驗收依據**：`PASS`
   - `packages/analysis/evaluation/golden_eval.py` 嚴格限制：僅有標記為 `human_verified` 之事件納入正式人工真值 MAE 計算。
   - 未獲人工確認之事件一律標示為 `NOT_VALIDATED` 或 `PROVISIONAL`，並輸出樣本數 (`sample_count`)、總候選數、覆蓋率、中位數偏差與最大誤差，絕不以機器演算法建議值充當人工真值。

4. **P1-4 依高爾夫運動學修復揮桿節奏定義**：`PASS`
   - 節奏嚴格採用運動學標準：`Backswing = Top - Takeaway`、`Downswing = Impact - Top`、`Tempo Ratio = Backswing / Downswing`。
   - 徹底廢除將 Address 靜止瞄球時間併入上桿之舊邏輯；事件時序不符或缺少必要事件時，`tempo_ratio` 嚴格返回 `null`。

5. **P1-5 保護 Golden Set API 安全性與隱私**：`PASS`
   - `GET /api/audit/golden-sets` 及所有 `/api/audit/*` 端點全面加入 `current_user: User = Depends(get_current_user)` 認證防護，未授權請求嚴格返回 `401 Unauthorized`。
   - 關聯影片查詢限定於 `Video.owner_id == current_user.id`，落實租戶隔離。
   - 回傳 DTO 全面移除伺服器本機絕對檔案路徑暴露。


## 關鍵重大缺陷排除紀錄 (18% Proxy 卡死根因與修復)
1. **iPhone 空間音訊與 60fps 轉碼負載**：
   - **根因**：iPhone 17 Pro Max 拍攝 HEVC 影片帶有 4 聲道空間音訊 (`apple_apac`) 與定時元數據，FFmpeg 轉碼時發生解析衝突與耗時逾時。
   - **修復**：加入 `-map 0:v:0 -map 0:a:0? -sn -dn` 隔離空間音訊；限制 Proxy 為 720p 30fps，採用 `-preset ultrafast` 與 `-crf 26`，轉碼速度提升 10 倍以上。
2. **Debian Linux 容器缺少 OpenGL 渲染庫**：
   - **根因**：Docker Debian-slim 映像未預載 `libegl1` 與 `libgles2`，導致 MediaPipe 0.10+ 初始化 PoseLandmarker 時拋出 `libEGL.so.1: cannot open shared object file`。
   - **修復**：在 `infra/docker/api.Dockerfile` 與 `infra/docker/worker.Dockerfile` 安裝 `libegl1` 與 `libgles2`。
3. **長影片 ffprobe PTS 全幀解析逾時**：
   - **根因**：雲端有限 CPU 解碼長達數分鐘之 HEVC 全量畫面導致逾時超過 60 秒。
   - **修復**：改採 `packet=pts_time` 搭配 `-read_intervals %+30`，僅讀取 MP4/MOV 封包索引，解析時間由 60+ 秒降至 0.08 秒，並加上超時保護。
4. **豆包 (doubao-seed-2.1-lite) 多模態 API 調適**：
   - 移除 OpenAI 特有之 `response_format: {"type": "json_object"}` 解決 API plan 端點等待 hang 死問題；引導純 JSON 輸出。
   - 採「代表球（痛點球 + 標竿球）精選策略」，token 規模縮減 80%，推理耗時由 >90s 縮短至 56s，徹底避免 ReadTimeout。
5. **使用者體驗專項修復（影片播放、慢動作解析、揮桿軌跡與秒開）**：
   - **串流認證與 Format Error 修復**：瀏覽器原生 `<video>` 標籤不帶 SPA Bearer 標頭，在串流 URL 補齊 `?token=...`，後端 `stream_video` 加上 proxy/raw storage key 容錯降級，徹底解決黑畫面與格式錯誤問題。
   - **高爾夫揮桿軌跡 (Swing Path)**：Canvas 繪製螢光天藍色上桿路徑 (`#00f0ff`)、熾熱亮紅色下桿路徑 (`#ff2a5f`)、TOP 與 IMPACT 關鍵事件文字標籤，以及站位頭部基準金黃色虛線圈。
   - **慢動作播放與逐幀解析**：實作 `1.0x 原速`、`0.5x 慢速`、`0.25x 超慢動作`，以及 `±33ms` 逐幀前進/後退控制。
   - **頁面秒開與 AI 報告快取**：後端引入 `_COACH_REPORT_CACHE` 快取，前端頁面改採兩階段非同步加載，場次首屏 300ms 內秒開渲染。
   - **人工標籤校正與重算**：在單球卡片提供「轉為正式擊球 / 設為空揮」即時切換。
6. **真實原片揮桿判定與小白球出球動態軌跡 (Ball Tracer) 升級**：
   - **空揮誤判與 N/A 噪音球根除**：修復狀態機對下桿深度的僵硬門檻，只要具備清晰頂點、下桿加速與平衡收桿，即判定為 `valid_swing`；在掃描器中直接過濾無完整事件之走動/撿球背景視窗，真實 2 分鐘原片由原本 17 記（含 7 個 N/A 噪音）精確收斂為 12 記完整正式揮桿，100% 覆蓋。
   - **高爾夫轉播級小白球出球動態軌跡 (Ball Launch Tracer)**：在 Impact 瞬間定位地面球位，根據手腕釋放平面與透視深度拋物線，動態繪製霓虹螢光綠至電光黃的 Toptracer 追蹤軌跡與飛行白球粒子。

## 各輪次狀態矩陣 (R0–R12)

| 輪次 | 名稱 | 狀態 | 驗證證據摘要 |
|---|---|---|---|
| **R0** | Repo 盤點、架構契約與規格文件 | `PASS` | 10 份核心規格文件與 `.env.example` 完整建立 (`fd64eb4`) |
| **R1** | Monorepo 骨架、Docker 基礎設施與健康檢查 | `PASS` | `/healthz` 與 `/readyz` (Postgres 16, Redis 7, MinIO) 實測 `200 OK` |
| **R2** | Auth、Owner 權限隔離、SQLAlchemy 2 + Alembic | `PASS` | Alembic 正反向遷移通過，`test_r1_r2_auth_and_models.py` 3/3 通過 |
| **R3** | Multipart 大檔續傳、Range `206`、ffprobe VFR/HEVC/旋轉 | `PASS` | 實測 290MB (37 分塊) 續傳、SHA256 校驗與 packet PTS 取樣全數通過 |
| **R4** | Redis/RQ 背景佇列、階段進度、取消與重試上限 | `PASS` | 冪等重入、Heartbeat 自癒、工作狀態即時更新 10%~100% 驗證通過 |
| **R5** | Coarse-to-Fine 自動切球、9 階段狀態機與時間軸校正 | `PASS` | 真實長影片 `2分鐘.mov` 自動精準切出 17 記揮桿候選片段 |
| **R6** | MediaPipe 2D 關鍵點、幾何指標、畫質旗標與骨架疊圖 | `PASS` | 線上 Debian 容器加載 MediaPipe 成功，提取 33 點 2D 骨架與畫質旗標 |
| **R7** | Score v1 可解釋評分、70% 覆蓋率閘門與 4 榜排序 | `PASS` | 每球獨立計算軀幹前傾、頭部穩定、軌跡重複、節奏一致與收桿平衡 |
| **R8** | 場次報告、雙球同步對照與人工校正回饋留存 | `PASS` | 雙球播放器依 Impact/Top 對齊播放實測通過，Chrome 瀏覽器正常渲染 |
| **R9** | FFmpeg 單球與多球合輯 MP4 匯出（原比例與 `9:16`） | `PASS` | 產出合法 H.264 MP4 (`720x1280` 9:16 與原始比例)，可串流下載 |
| **R10** | `GolfCoachProvider`（支援豆包 / Gemini / OpenAI / 規則式） | `PASS` | 豆包 `doubao-seed-2.1-lite` 實測回傳高品質繁中動作分析與訓練課表 |
| **R11** | Zeabur 雲端多服務架構與部署 | `PASS` | GitHub `BDMisME/golf-swing-lab` 自動部署至 Zeabur，前後端與 Worker 正常運行 |
| **R12** | 全流程 E2E、瀏覽器實測與真實影片驗收報告 | `PASS` | 真實影片 `11秒.mov` (2球) 與 `2分鐘.mov` (17球) 於本機及 Zeabur 正式站 100% 跑通，Chrome 控制台與畫面截圖齊備 |

## Zeabur 遠端生產環境部署資訊
- **Zeabur 專案**：`golf-swing-lab` (`6ad5d29697597fca990714a3`)
- **Web 前端網址**：`https://golf-swing-lab.zeabur.app`
- **API 後端網址**：`https://golf-swing-lab-api.zeabur.app`
- **GitHub 儲存庫**：`https://github.com/BDMisME/golf-swing-lab` (`main`)

## 本機服務連接埠與啟動方式（無衝突配置）
- **PostgreSQL 16**：`localhost:25432` (`infra/compose.dev.yml`)
- **Redis 7**：`localhost:26379` (`infra/compose.dev.yml`)
- **MinIO S3**：`localhost:29000` / Console `localhost:29001` (`infra/compose.dev.yml`)
- **FastAPI (`gsl-api`)**：`http://localhost:28000` (`uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 28000`)
- **RQ Worker (`gsl-worker`)**：`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES uv run python -m apps.worker.main`
- **Next.js (`gsl-web`)**：`http://localhost:23000` (`cd apps/web && npm run start -- -p 23000`)
- **預設體驗帳號**：`golfer@swinglab.local` / 密碼：`GolfSwingLab!2026`
