# Golf Swing Lab R4 — 修訂後品質門禁矩陣 (REVISED_GATE_MATRIX.md)

**修訂日期**：2026-11-02  
**審查標準**：《Golf Swing Lab R4 — 第三輪獨立審查暨 Beta 發行前最後驗收指令》及《Golf Tracer Studio R4 架構書》§11  
**分支**：`feat/r4-golf-tracer-studio`  
**PR**：Draft PR #4 (`https://github.com/BDMisME/golf-swing-lab/pull/4`)  
**最高誠信原則**：真實性與反幻覺原則（Truthfulness & Anti-Hallucination）。未達門檻絕不偽稱通過，外部相依性缺失一律標記 `BLOCKED` / `NOT_VALIDATED`。嚴格禁止宣告 `R4_FULL_PASS`。

---

## 1. 終局判定結論 (Final Release Determination)

> ### 判定結果：**`MANUAL_STUDIO_BETA_READY`**
>
> 1. **發行範圍**：本判定僅核准「**Golf Tracer Studio 人工球路編輯器與 Flight FX 視覺特效個人測試版（Personal Beta）**」具備發行就緒條件。
> 2. **嚴格禁止宣稱**：**嚴格禁止宣告 `R4_FULL_PASS`**。Gate 2 (Swing Tracer 自動追蹤) 與 Gate 3 (Shot Tracer 自動追蹤) 實拍自動追蹤因缺乏外部商用模型與高速快門 Ground Truth，恪守誠信原則維持 **`BLOCKED` / `NOT_VALIDATED`**。
> 3. **安全邊界保證**：
>    - 正式版 `/Applications/Golf Swing Lab.app` 維持 `v1.0.0`，測試前後 Info.plist 與 binary 之 SHA256 100% 恆等（Untouched）。
>    - 測試版 `/tmp/Golf Swing Lab R4 Test.app` 為 `repo-dependent developer Mac app`，以獨立 Bundle ID `com.golfswinglab.desktop.r4test` 運行。
>    - 徹底拔除驗收腳本之暴力 kill-9，改用 loopback 探測與專屬進程生命週期管理，既有伺服器程序 0 干擾。
>    - 歷史資料庫 620 場次、797 切片、4,480 事件與 18 支示範影片 100% 完整無損。

---

## 2. 門禁總覽表 (Gate Matrix Summary)

| 門禁代號 | 門禁名稱 | 狀態判定 | 核心依據與可重現證據 |
|---|---|---|---|
| **Gate 1** | Studio 核心合約與座標系 | **`PASS`** | 100% 一致之正向歸一化座標系 (`Upright Normalized Space [0,1]`)；6 組官方預設集；Catmull-Rom 插值與 Hermite 補間。單元測試通過。 |
| **Gate 2** | Swing Tracer 自動追蹤實測 | **`BLOCKED`** / **`NOT_VALIDATED`** | `BLOCKED_EXTERNAL_DEPENDENCY`：商業授權 `swingtrace-yolo11m.pt` 模型權重未開源；25 支實拍切片中 22 支落入 `NEEDS_REVIEW`（純幾何輔助覆蓋率約 39.7%，直接桿頭覆蓋率 0.00，P50 不確定度約 8.6px~11.7px），3 支落入 `MODEL_UNAVAILABLE`。系統誠實判定，絕不以手腕座標冒充。 |
| **Gate 3** | Shot Tracer 自動追蹤實測 | **`BLOCKED`** / **`NOT_VALIDATED`** | `BLOCKED_EXTERNAL_DEPENDENCY`：缺少 $\ge 120\text{ fps}$ 高速快門攝影機與雙重標註球路 Ground Truth；實拍 25 支切片全數落入 `UNAVAILABLE`，物理過濾器 100% 攔截雜訊，0 假球道。堅決不以藝術延伸動畫混充自動追蹤。 |
| **Gate 4** | 空間錨點與逐格編輯器 | **`PASS`** | 0 點切片支援「🚀 標定起飛球位」手動三點錨定 (`MANUAL_ANCHORED` / `ARTISTIC_EXTENSION`)；逐格拖拉微調、點位新增/刪除、Undo/Redo、F5 重載持久化與 Copy-on-Write 修訂版號。 |
| **Gate 5** | 資料庫隔離與向後相容性 | **`PASS`** | Studio 擊球時間覆寫記錄於 `TracerAnchorRevision`，既有 R3 `SwingEvent` 時間戳記 0 修改；歷史 620 場次、797 切片、4,480 事件資料完整無損。 |
| **Gate 6** | 24 種匯出矩陣與 A/V 同步 | **`PASS`** | 24 種配置 (original/16:9/9:16 × 30/60fps × none/swing/shot/both) 100% 成功；1/2/3/5/10 連續合輯 A/V 容器對齊實測全數為 `0.0 ms` ($\le 100\text{ ms}$)；知覺同步誠實標記 `NOT_VALIDATED_PERCEPTUAL_SYNC`；無音訊或靜音時明確標記 `NOT_APPLICABLE`。 |
| **Gate 7** | 原生 macOS 測試版 App Bundle 實機運行 | **`PASS`** | `scripts/verify_r4_mac_bundle.py` 以二進位檔實機啟動測試版 App (PID 74137)，Bundle ID `com.golfswinglab.desktop.r4test`，版本 `1.4.0-r4test`，架構屬性誠實記錄為 `repo-dependent developer Mac app`；無損原片串流 (`Source: ORIGINAL` 徽章，HTTP 響應頭 `x-gsl-media-source: original`)；`requestVideoFrameCallback` 計數 > 0 且 PTS 單調遞增；退出後子進程徹底清理，28000/23000 端口安全釋放。 |
| **Gate 8** | 真實像素級 Visual Parity 檢驗 | **`PASS`** | 24 個指定 PTS Checkpoints，WebKit Canvas PNG 與 FFmpeg 解碼 MP4 幀之法向量截面強度差分質心最大偏移量為 **`1.312 px`** ($\le 2.0\text{ px}$)，平均偏移量 **`0.401 px`**，影格時間差 **`0.0 幀`**，階段顏色與虛線特徵 100% 通過（24/24 PASS，`all_passed: true`）。Sabotage 破壞模式語意分離，CLI sabotage 觸發 fail-closed 退出碼 1，正常通過退出碼 0。 |
| **Gate 9** | 程式碼品質與測試覆蓋率 | **`PASS`** | Python 後端全量測試 **167 passed, 1 skipped** (0 failed)；前端 Vitest **8 passed** (0 failed)；Next.js 15.5.28 正式建置 10/10 路由 0 錯誤 0 警告；嚴格遵守繁體中文規範與防呆架構。 |
| **Gate 10** | 既有資產與正式 App 零破壞 | **`PASS`** | 正式 `/Applications/Golf Swing Lab.app` 維持 `v1.0.0` 零修改（測試前後 SHA256 100% 恆等）；拔除暴力殺 Port 邏輯，佔用時安全退出 `BLOCKED_PORT_IN_USE`（`tests/test_no_port_kill_guards.py` 2 passed）；R3 無特效單球與合輯匯出管線正常；Worker 缺檔安全防護生效。 |

---

## 3. 門禁詳細說明與審查依據

### Gate 1: Studio 核心合約與座標系 (`PASS`)
- **合約定義**：所有點位座標均以正向原片為基準，歸一化至 $[0.0, 1.0]$，完全隔離旋轉中繼資料（`rotation=90/180/270`）造成的座標混淆。
- **預設風格**：實作 6 組官方渲染預設集（`clean_analysis`, `studio_neon`, `minimal_white`, `power_beam`, `rainbow_arc`, `no_fx`）。
- **驗證證據**：`tests/test_tracer_contracts_and_math.py` 8 項測試全數通過。

### Gate 2: Swing Tracer 自動追蹤實測 (`BLOCKED` / `NOT_VALIDATED`)
- **阻擋原因 (Blocker)**：
  - 缺乏合法商業授權之 YOLO11m 桿頭權重（`swingtrace-yolo11m.pt`）。
  - 單鏡頭 2D DTL 實拍在下桿階段伴隨劇烈動態模糊（Motion Blur）與軀幹遮擋，純幾何輔助（`shaft_geometry_estimated`）之覆蓋率約 39.7%，直接桿頭覆蓋率為 0.00，P50 不確定度約 8.6px~11.7px，無法達到 1080p 下 $\le 5.0\text{ px}$ 的商用全自動合格標準。
- **處理原則**：系統嚴格依照最高誠信原則，將實拍切片標記為 `NEEDS_REVIEW`（22 支）或 `MODEL_UNAVAILABLE`（3 支），要求使用者透過 Studio 逐格編輯器手動校正，絕不以手腕頂點或假數據冒充。

### Gate 3: Shot Tracer 自動追蹤實測 (`BLOCKED` / `NOT_VALIDATED`)
- **阻擋原因 (Blocker)**：
  - 一般 30/60fps 攝影機在高速擊球瞬間，小白球於 1~2 幀內即飛出視角或融入背景雜訊。目前開源社群與學術界缺乏單鏡頭 60fps DTL 下之可靠無標記球路追蹤模型。
  - 缺乏 $\ge 120\text{ fps}$ 高速快門攝影機與雙重標註球路真實資料集。
- **處理原則**：系統之物理過濾器精準攔截雜訊，將 25 支實拍切片全數判定為 `UNAVAILABLE`，絕不自動生成任何虛假飛行軌跡。系統提供使用者啟動「🚀 標定起飛球位」手動設定或藝術延伸模式，保持全流程誠實可信。

### Gate 4: 空間錨點與逐格編輯器 (`PASS`)
- **0 點切片手動標定**：提供「`🚀 標定起飛球位`」功能，使用者可於畫布上標定起飛點 (Launch)、最高點 (Apex) 與落地點 (Landing)，後端自動生成平滑物理拋物線並轉為 `MANUAL_ANCHORED` 或 `ARTISTIC_EXTENSION` 模式。
- **拖拉與精修**：畫布提供即時拖拉預覽把手，放開後自動送出 Copy-on-Write 儲存，版號安全遞增。
- **驗證證據**：WKWebView 原生環境測試證實點位落庫（`rev_landing`）、手動加點（`rev_add`）、微調拖曳坐標變更（$\Delta > 0$）、Undo 回退、Redo 恢復與 F5 重載持久化 100% 正常。

### Gate 5: 資料庫隔離與向後相容性 (`PASS`)
- **讀寫隔離**：Studio 中所有錨點修改（包含擊球時間 `impact_pts_us` 覆寫）均儲存於 `TracerAnchorRevision` 表，完全不更動既有 R3 系統之 `SwingEvent` 與 `SwingSegment` 資料表。
- **資產無損**：620 場次、797 切片、4,480 事件與 18 支參考示範庫 100% 完整無損。

### Gate 6: 24 種匯出配置矩陣與 A/V 同步 (`PASS`)
- **匯出矩陣**：24 種規格（3 種比例 × 2 種 FPS × 4 種特效組合）100% 產出合規 MP4 與 Sidecar JSON。
- **音畫同步**：1 / 2 / 3 / 5 / 10 連續精選合輯透過 FFmpeg 重取樣 (`aresample=async=1` + `atrim`)，實測 A/V 容器漂移全數為 **`0.0 ms`**（遠優於 $\le 100\text{ ms}$ 之門檻）。
- **音訊模式區分**：`audio_mode == "preserve"` 且有音軌時確保音畫同步；原片無音訊或 `audio_mode == "mute"` 時明確標記為 `NOT_APPLICABLE`；知覺同步誠實標記 `NOT_VALIDATED_PERCEPTUAL_SYNC`。

### Gate 7: 原生 macOS 測試版 App Bundle 實機運行 (`PASS`)
- **測試版 App 實機啟動**：`scripts/verify_r4_mac_bundle.py` 透過 Mach-O 二進位檔實機啟動 `/tmp/Golf Swing Lab R4 Test.app/Contents/MacOS/GolfSwingLab`（PID 74137）。
- **架構屬性誠實記錄**：該 launcher 透過搜尋專案目錄與 `.venv` 執行，架構屬性誠實記錄為 `repo-dependent developer Mac app`，不宣稱為 standalone。
- **原片無損串流**：確認載入 `/stream?source=original`，畫面顯示「`Source: ORIGINAL`」綠色徽章，HTTP 響應頭包含 `x-gsl-media-source: original`，畫布解析度為 `1080x1920`。
- **高頻幀同步**：`requestVideoFrameCallback` 真正收到回調且計數 > 0，PTS 序列嚴格單調遞增，全流程 0 JS 拋錯。
- **乾淨釋放**：App 退出後，Sidecar 子進程徹底終止，28000 與 23000 端口 100% 釋放，無孤兒進程。

### Gate 8: 真實像素級 Visual Parity 檢驗 (`PASS`)
- **實體影像比對**：由 WKWebView 擷取真實 Canvas PNG，比對 FFmpeg 解碼之 MP4 影格。
- **實測數據**：24 個指定 PTS 檢查點中，最大中心線像素偏移量為 **`1.312 px`**（$\le 2.0\text{ px}$），平均偏移量 **`0.401 px`**，影格時間差 **`0.0 幀`**，階段分色與藝術延伸虛線檢驗 100% 通過（24/24 PASS，`all_passed: true`）。
- **破壞模式語意分離**：CLI `--sabotage` 破壞模式在檢測到異常時由驗證器自身以退出碼 1 退出（Fail-Closed）；正常驗收通過以退出碼 0 退出。`tests/test_parity_sabotage_and_guards.py` 6 項測試全數通過。

### Gate 9: 程式碼品質與測試覆蓋率 (`PASS`)
- **測試覆蓋**：Python 後端全量測試 **167 passed, 1 skipped**（涵蓋合約、數學、影像、API、安全、Sabotage 與端口守衛）；前端 Vitest **8 passed** (0 failed)。
- **構建狀態**：Next.js 15.5.28 生產建置 100% 成功，10/10 路由 0 語法錯誤，0 類型錯誤。

### Gate 10: 既有資產與正式 App 零破壞 (`PASS`)
- **應用程式隔離**：正式版 `/Applications/Golf Swing Lab.app` 維持 `v1.0.0`，測試前後 Info.plist 與 binary 之 SHA256 100% 恆等（Untouched）。測試作業僅在 `/tmp/Golf Swing Lab R4 Test.app` 獨立執行。
- **移除暴力殺 Port 邏輯**：徹底拔除 `lsof -ti :28000 | xargs kill -9`，改用 loopback 探測與專屬進程管理，端口被佔用時安全退出 `BLOCKED_PORT_IN_USE`（`tests/test_no_port_kill_guards.py` 2 passed）。
- **非特效匯出零回歸**：R3 原生非特效單球與合輯匯出正常產生。
- **Worker 缺檔防護**：原片缺失時安全拋出 `SOURCE_UNAVAILABLE`，拒絕降級使用低畫質 Proxy。

---

## 4. 審查結論與交付狀態

本專案在實施第三輪修復後，**所有工程架構、Studio 逐格編輯器、影片匯出矩陣、影音同步、原生 macOS 測試版 App Bundle 實機運行、無暴力殺 Port 安全進程管理、真實狀態變更校驗、破壞模式語意分離與真實像素級 Parity 檢驗均已達到 100% 交付水準（PASS）**。

終局判定核定為 **`MANUAL_STUDIO_BETA_READY`**。

同時，針對目前因缺乏外部商用模型與高速標註數據集而受限之 Gate 2 (Swing Tracer) 與 Gate 3 (Shot Tracer)，本系統恪守最高誠信原則，如實標記為 **`BLOCKED` / `NOT_VALIDATED` (`BLOCKED_EXTERNAL_DEPENDENCY`)**，絕不欺瞞使用者或以合成飛行動畫冒充真實自動追蹤，絕不宣稱 `R4_FULL_PASS`。
