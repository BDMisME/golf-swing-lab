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
