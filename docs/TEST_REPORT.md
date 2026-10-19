# TEST_REPORT.md — 自動化測試與實測證據報告

> 本報告隨 R0–R12 每輪測試實際執行結果動態更新。所有紀錄皆來自真實執行之命令與輸出，絕不虛構。

## 1. 測試環境資訊
- **作業系統**：macOS (`aarch64-apple-darwin`)
- **Python 環境**：Python 3.12 (`uv` 虛擬環境管理)
- **Node / 前端環境**：Node.js v24.21.0, pnpm 11.9.0
- **媒體工具**：FFmpeg / ffprobe 9.0.2_1 (含 `libx264`, `libx265`)
- **容器環境**：Docker Desktop (PostgreSQL 16, Redis 7, MinIO)

## 2. 各輪次測試摘要

| 輪次 | 測試範圍 | 執行指令 | 通過 / 失敗 | 性質 (Real / Mock) | 狀態 |
|---|---|---|---|---|---|
| R0 | 架構文件、合約與環境工具鏈盤點 | `ls` / `git status` / `ffmpeg -version` | 100% 齊全 | Real | `PASS` |
| R1 | Monorepo 骨架、基礎設施與健康檢查 | 待執行 | - | - | `PENDING` |
| R2 | Auth、權限隔離、Alembic Migration、API 合約 | 待執行 | - | - | `PENDING` |
| R3 | Multipart 大檔直傳續傳、ffprobe VFR/旋轉/HEVC、Proxy | 待執行 | - | - | `PENDING` |
| R4 | 背景佇列、進度、重試/取消、Worker 恢復 | 待執行 | - | - | `PENDING` |
| R5 | Coarse-to-Fine 揮桿候選偵測、狀態機、時間軸校正 | 待執行 | - | - | `PENDING` |
| R6 | MediaPipe 2D 關鍵點、DTL 幾何指標、骨架疊圖與低光/遮擋測試 | 待執行 | - | - | `PENDING` |
| R7 | Score v1 可解釋評分、70% 覆蓋率閘門、IG 排序 | 待執行 | - | - | `PENDING` |
| R8 | 場次報告、雙球同步對照、人工回饋留存 | 待執行 | - | - | `PENDING` |
| R9 | 單球與 2–3 球合輯匯出（原比例與 9:16） | 待執行 | - | - | `PENDING` |
| R10 | LLM Coach Adapter（`none` 與 `openai-compatible` Mock） | 待執行 | - | - | `PENDING` |
| R11 | Dockerfiles 與 Zeabur 部署規格驗證 | 待執行 | - | - | `PENDING` |
| R12 | 全流程 E2E、瀏覽器驗收與 Golden Set 基準報告 | 待執行 | - | - | `PENDING` |
