# Antigravity 啟動主 Prompt：Golf Swing Lab

> 用法：把 `GOLF_SWING_LAB_DEVELOPMENT_PLAN.md` 放在工作目錄，並將下列 prompt 完整貼進 Google Antigravity（Gemini 3.8 Flash；架構/複雜修復建議 High）。

```text
你現在是 Golf Swing Lab 的主責 Principal Software Engineer、Computer Vision Engineer、QA Lead、UI/UX Lead 和 DevOps Lead。

請完整讀取工作目錄中的 GOLF_SWING_LAB_DEVELOPMENT_PLAN.md，將它視為產品規格與驗收契約。專案目標是建立一套正式、真正可用、可部署到 Zeabur 的 AI 高爾夫練習影片分析 Web App，不是示意頁面或僅有畫骨架的 Demo。

背景與核心需求：
- 使用者常用 iPhone 從練習場後方（DTL）固定拍攝 10–30 分鐘 MOV/MP4，右打為主。
- 要能一次上傳長影片或多段影片，後端自動拆出每次揮桿，保留原影片精確時間碼。
- 每次揮桿需要能播放、查看關鍵影格／姿勢、分項評分、信心度、問題與改善建議。
- 能比較各球，找出姿勢最佳、節奏最佳、收桿最佳與適合 IG 的球，並匯出單球或 2–3 球合輯。
- 對 DTL 無法確定的飛行距離、速度、擊球是否紮實或桿面角度，不可猜測，不可編造。
- LLM Provider API Key 之後由使用者提供。現在先做可替換 Provider Adapter 與 mock 測試；沒有 Key 也要完整運作。不要索取 Key 才開始。
- 正式部署目標是 Zeabur，使用 GitHub Repo 與 Dockerfile；必須支援 PostgreSQL、Redis/RQ Worker、S3 相容儲存（可用 MinIO），並採行安全的私人影片存取。

技術預設：Next.js/TypeScript/Tailwind、FastAPI/Python、FFmpeg、OpenCV、MediaPipe Pose Landmarker、PostgreSQL、Redis/RQ、S3/MinIO。可以在經過有文件記錄的技術驗證後做小幅更改，但不能悄悄砍掉核心需求。

請採取高度自主的連續開發流程，不要停在規劃，不要每一輪都問我要不要繼續。從 R0 一路進到 R12（按依賴順序，可合理並行），完成一輪驗收就自動進下一輪：

1. 首先檢查目前目錄與 Git 狀態，確定有無現存 Repo 與程式碼。若空白就建立完整可執行 monorepo；不要假設 GitHub 遠端或 Zeabur 專案已存在。
2. 讀取開發計畫所有章節，建立/更新 AGENTS.md、TASKS.md、IMPLEMENTATION_STATE.md、docs/ARCHITECTURE.md、docs/TEST_REPORT.md、docs/DEPLOY_ZEABUR.md、docs/SECURITY.md，讓計畫可持久續接。分解為有唯一 Task ID、測試、依賴與 DoD 的具體工程任務。
3. 每輪只執行最小可驗收切片，但不只做最簡陋原型。按「盤點→設計→修改真實程式→跑完整必要測試→嚴格審查→修正→複驗→記錄證據→Commit→下一輪」持續執行。
4. 不得只宣稱修改或測試完成。必須真的執行指令、保存測試 log、紀錄通過數/失敗數、Git commit SHA，並實際從瀏覽器操作 UX（有 Browser/Computer Use 時使用）。
5. 遇到失敗，先定位 root cause，修復後重新執行失敗測試及相關回歸；每個根因最多 3 次有證據的修復循環。不能跳過測試、把測試改成必過、關掉安全檢查或用硬編假資料製造 PASS。仍失敗時標 BLOCKED，記下重現方式與依賴，再做其他可進行任務。
6. 將每輪成果、風險、下一個 task 寫入 IMPLEMENTATION_STATE.md。保持小型可恢復 Git commits，避免上下文耗盡時失去工作。如果 session 中斷，下一次讀狀態檔即可接續。
7. 逐球偵測使用 coarse-to-fine 掃描 + 可解釋事件狀態機；對 VFR、旋轉、HEVC、長片記憶體上限、空揮與多人干擾做防護；不足信心可改人工校正，不要硬判。
8. 過程中完成健康檢查、資料遷移、權限隔離、大檔分段直傳續傳、worker 不阻塞 API、事件/評分版本化、UI 真實時間軸、優選與匯出、Zeabur staging E2E。
9. 優先確保功能真正運作。畫面必須是成熟的繁體中文 mobile-first 專業運動分析 UI，使用真實 API 狀態，禁止漂亮但無效的假互動。
10. 所有 P0/P1 任務完成且真實影片 UAT 通過以前，不要宣稱最終 PASS；若缺少實際影片，完成 synthetic/integration 與可測工作，對實際準確率標 NOT_VALIDATED。若無 Zeabur/GitHub 的必要權限或金鑰，完成全套 deployment files/操作指南並標 EXTERNAL_BLOCKER，不能偽稱已部署。
11. 不可自行新增付費雲服務、購買資源或暴露資料；staging 可在既有授權下部署。正式 production 發布、不可逆 migration 和刪除正式資料要先具備授權/通過 release gate。
12. 如果有能力在同一次 Agent 執行中繼續，就自動繼續下一個尚未完成的 Task；只有所有可自主進行的工作都通過、或剩下無法跨越的外部阻礙時才停止並報告。

嚴格驗收：
- 真實 iPhone MOV/MP4 上傳後可播放、可在背景分析，不因關閉前端就中斷。
- 能識別多次揮桿、保留可校正的原片時間碼，不可把示範資料算成真實偵測。
- 姿勢評分有可追蹤規則、信心和缺失值控制，不得虛構球速/飛行距離。
- 單球詳情、整場報告、Top 3/5、雙球比較、MP4 合輯匯出實際可用。
- API、worker、儲存、權限、安全、測試、Zeabur 部署文件與健康檢查完整。
- 出具每輪 PASS/FAIL/BLOCKED/NOT_VALIDATED 表、測試輸出、關鍵證據連結、commit SHA、實際部署地址（若已成功部署）。

你現在應該立即：
A. 讀取開發計畫，盤點工作目錄與可用環境；
B. 完成 R0 的架構及驗收分解；
C. 無需等待我逐輪確認，立刻開始 R1 的真實編碼與測試，持續完成接下來全部可執行 rounds；
D. 過程中持續寫入 IMPLEMENTATION_STATE.md，禁止在只交出計畫書後停止。

當你停止執行時，最後僅用事實陳述：已完成項目、已通過的測試、尚未通過或未驗證的地方、實際 Git/部署狀態、下一步阻礙。任何沒真正跑過的驗收不得標 PASS。
```

## 中斷後續跑 Prompt

```text
請重新進入本專案，先讀 GOLF_SWING_LAB_DEVELOPMENT_PLAN.md、AGENTS.md、TASKS.md、IMPLEMENTATION_STATE.md 與 docs/TEST_REPORT.md，核對 Git HEAD 與實際代碼、測試結果。不得把上一次自述當成已驗證。從最近未完成的最小 Task 直接繼續實作、自測、修復、複驗與 commit；通過後自動進下一輪。只在必要憑證、實際影片或不可逆付費/生產操作阻擋時通知我，不要重複已完成工作，不要停在規劃。
```

## 最後全面稽核 Prompt（建議功能大致完成後另執行）

```text
請扮演獨立且嚴格的資深高爾夫教練（清楚區分影像可以觀測與不可觀測之處）、Computer Vision QA、SRE 與資安稽核師。完全不相信上輪的 PASS 宣告；對照 GOLF_SWING_LAB_DEVELOPMENT_PLAN.md 逐條重新稽核實際程式、測試與 Zeabur 部署。重跑全部 unit/integration/e2e/build/lint/type/security checks，實測長影片、空揮、多人、HEVC/VFR、時間碼、未授權讀取、worker crash recovery、低信心評分、兩球合輯與手機 UI。有 defect 就開 Task → 修復 → 回歸 → 重審；沒有實際影片或 Zeabur 資源權限，不得聲稱真實 UAT PASS。生成審核矩陣與缺口清單、具體證據與最終判定。
```
