# DEPLOY_ZEABUR.md — Zeabur 正式部署規格與狀態紀錄

## 1. 現行 Zeabur 部署原則確認（依據官方文件稽核）
- Zeabur **不支援直接以 `docker-compose.yml` 單檔部署多服務應用**，必須在同一 Zeabur Project 的不同 Environment（`staging` / `production`）中，針對各服務分別建立 Service（從 GitHub Repository 指定對應 `Dockerfile` 或使用 Zeabur 內建 Prebuilt Template）。
- **嚴禁誤用 Zeabur 部署 ZIP 的 Upload API 上傳使用者高爾夫影片**；使用者影片一律存入 S3 相容物件儲存（`gsl-minio` 或雲端 S3）。
- 健康檢查（Health Checks）：於 Zeabur Service 設定 HTTP Health Check 指向 `/readyz`（API）與 `/api/health`（Web）。

## 2. 服務拓樸與配置清單

| 服務名稱 | 部署來源 / Dockerfile | 公開網域 | 持久化 Volume | 建議資源上限 |
|---|---|---|---|---|
| `gsl-web` | GitHub Repo + `infra/docker/web.Dockerfile` | 是 (`https://<web>.zeabur.app`) | 無（Stateless） | 1 vCPU / 1 GB RAM |
| `gsl-api` | GitHub Repo + `infra/docker/api.Dockerfile` | 是（或由 `gsl-web` 反向代理） | 無（Stateless） | 1 vCPU / 1 GB RAM |
| `gsl-worker` | GitHub Repo + `infra/docker/worker.Dockerfile` | **否（僅內網）** | 無（暫存於 `/tmp` 處理完即清） | 2 vCPU / 4 GB RAM (`WORKER_CONCURRENCY=1`) |
| `gsl-postgres` | Zeabur Prebuilt Template (`PostgreSQL 16`) | **否（僅內網）** | `/var/lib/postgresql/data` | 1 vCPU / 1 GB RAM |
| `gsl-redis` | Zeabur Prebuilt Template (`Redis 7`) | **否（僅內網）** | `/data` | 0.5 vCPU / 512 MB RAM |
| `gsl-minio` | Zeabur Prebuilt Template (`MinIO`) | S3 API 端點可選擇公開（Console 9001 **不公開**） | `/data` | 依影片儲存需求配置 |

## 3. 部署狀態與阻礙紀錄（Real Status）
- **目前遠端部署狀態**：`EXTERNAL_BLOCKER`（尚未提供 Zeabur API Token / Project 權限與遠端 GitHub 儲存庫目標授權）。
- **Staging URL**：尚未部署（待使用者提供 Zeabur 專案權限後填入真實網址，絕不填寫假網址）。
- **Production URL**：尚未部署。
- **本機容器化與基礎設施模擬**：透過 `infra/compose.dev.yml` 與 `infra/docker/*.Dockerfile` 完整實作並驗證。
