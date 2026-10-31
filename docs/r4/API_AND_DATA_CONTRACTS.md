# Golf Swing Lab R4 — API、資料庫與座標/時間契約規格書 (`API_AND_DATA_CONTRACTS.md`)

---

## 1. 權威時間與直立正規化空間契約

### 1.1 單一時間權威 (`source_pts_us`)
- **微秒整數時間戳 (`source_pts_us: int`)**：全系統（FFprobe 解析、BoundedFrameReader 解碼、Swing/Shot 追蹤、前端 Canvas 播放頭、FFmpeg CFR 匯出）統一使用原始媒體流之 Presentation Timestamp 微秒整數。
- **CFR 輸出時間軸生成 (`generate_cfr_output_pts_us`)**：
  - 30fps：嚴格有理數 `30/1`（步進約 `33,333 us`）
  - 60fps：嚴格有理數 `60/1`（步進約 `16,667 us`）

### 1.2 單一空間權威 (`Normalized Upright Display Space`)
- 所有軌跡點 `(x_norm, y_norm)` 定義於**套用完原始影片旋轉 metadata (`0°/90°/180°/270°`) 後的直立顯示畫面**，範圍 `[0.0, 1.0]`。
- 前後端共享完全一致的 `OutputLayout` 等比縮放與置中黑邊轉換公式（前端 [transforms.ts](file:///Users/mathew/Desktop/Golf_Swing_Lab/apps/web/src/lib/tracer/transforms.ts)、後端 [transforms.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/packages/analysis/tracer/transforms.py)），確保 `original`、`16:9` (`1920x1080`)、`9:16` (`1080x1920`) 預覽與匯出像素誤差 `<= 2.0 px` (@1080p)。

### 1.3 `CanonicalTrackPoint` 契約欄位（[contracts.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/packages/analysis/tracer/contracts.py)）
| 欄位 | 型別 | 規範說明 |
|---|---|---|
| `track_id` | `str` | 軌跡唯一識別碼 |
| `segment_id` | `str` | 對應 `swing_segments.id` |
| `source_video_id` | `str` | 對應 `videos.id` |
| `track_type` | `club_head \| club_shaft \| ball` | 軌跡對象類別 |
| `phase` | `address \| backswing \| top \| downswing \| impact \| follow_through \| finish \| ball_flight` | 揮桿或飛球階段 |
| `source_frame_index` | `int` | 原片解碼格索引 |
| `source_pts_us` | `int` | 原片權威時間戳（微秒） |
| `x_norm`, `y_norm` | `float` (`0.0..1.0`) | 直立顯示座標 |
| `raw_observation` | `RawObservation \| None` | 保留未平滑之原始偵測 `(x_norm, y_norm, bbox_norm)` |
| `position_role` | `raw_detected \| display_smoothed \| manual_anchor \| artistic_control` | 區分原始偵測點、平滑顯示點與手動控制點 |
| `confidence` | `float` (`0.0..1.0`) | 點位信心度 |
| `uncertainty_px` | `float` | 1080p 基準像素不確定度半徑 |
| `source_type` | `detector_observed \| shaft_geometry_estimated \| optical_flow_tracked \| kalman_predicted \| interpolated \| extrapolated \| manually_annotated \| artistic_only` | **嚴禁將預測、內插、人工或藝術延伸點標為 `detector_observed`** |
| `created_by` | `model \| tracker \|interpolator \| user` | 產生來源（**嚴禁 `wrist`**） |
| `revision` | `int` | Copy-on-Write 修訂版號（初始為 `1`） |

---

## 2. 新增資料庫結構（Alembic `0003_tracer_studio.py`）

所有新增資料表皆為純加法擴充（Additive Migration），不刪除、不破壞 R1–R3 既有 10 張資料表與資料列：

1. `tracer_projects`：Studio 專案主表（綁定 `owner_id`, `segment_id`, `video_id`, `swing_status`, `shot_mode`, `active_swing_revision`, `active_shot_revision`, `active_anchor_revision`, `active_recipe_id`）。
2. `tracer_track_revisions`：Copy-on-Write 不可變軌跡修訂版（儲存 `track_type`, `revision`, `parent_revision`, `status`, `storage_key` (`.jsonl.gz`), `artifact_sha256`, `points_inline_json`, `quality_summary_json`）。
3. `tracer_anchor_revisions`：Studio 專屬時間與空間錨點修訂版（`address_pts_us`, `top_pts_us`, `impact_pts_us`, `finish_pts_us`, `launch_pts_us`, `apex_pts_us`, `landing_pts_us`, `anchors_json`），**與 R3 `swing_events` 完全隔離**。
4. `tracer_render_recipes`：`RenderRecipeV1` 樣式與匯出規格版本表。
5. `tracer_jobs`：自動分析背景任務狀態表。
6. `tracer_export_jobs`：單球與 1–10 球合輯匯出任務表（含 `mp4_storage_key`, `sidecar_storage_key`, `mp4_sha256`, `sidecar_sha256`, `parity_report_json`, `sidecar_payload_json`）。
7. `tracer_feedback_events`：使用者修正與品質回饋事件表。
8. `tracer_model_registry`：本機 CV 模型權重清冊與 SHA256/授權狀態表。

---

## 3. REST API 端點規格（`/api/tracer/*`）

所有端點皆受 `get_current_user` 身分驗證、Owner IDOR 隔離（跨帳號回傳 `403 FORBIDDEN`）與 `GSL_ENABLE_TRACER_STUDIO` 功能旗標（關閉時回傳 `503 TRACER_STUDIO_DISABLED`）保護：

- `GET /api/tracer/models`：列出本機 CV 模型權重狀態（`golf_ball_yolov8n`、`yolov8x_pose`、`swingtrace_yolo11m`）。
- `GET /api/tracer/presets`：列出 6 組內建 `RenderRecipeV1` 特效預設。
- `POST /api/tracer/projects`：為指定 `segment_id` 建立或取得 Studio 專案並觸發自動分析。
- `GET /api/tracer/projects/{project_id}`：取得專案詳情、最新 Swing/Shot 軌跡點、品質摘要、錨點與樣式配方。
- `POST /api/tracer/projects/{project_id}/analyze`：重新執行自動 Swing / Shot 追蹤推論。
- `GET /api/tracer/projects/{project_id}/tracks/{track_type}/revisions`：列出指定軌跡之所有歷史修訂版。
- `PUT /api/tracer/projects/{project_id}/tracks/{track_type}`：提交逐幀手動點位編輯 (`add` / `move` / `delete`)，建立新 Copy-on-Write 修訂版。
- `POST /api/tracer/projects/{project_id}/tracks/{track_type}/rollback/{target_revision}`：非破壞性回滾至指定歷史修訂版（複製目標版本點位為最新修訂版）。
- `PUT /api/tracer/projects/{project_id}/anchors`：更新 Studio 時間/空間錨點與可選藝術延伸開關並重算軌跡。
- `PUT /api/tracer/projects/{project_id}/recipe`：儲存自訂或預設 `RenderRecipeV1` 視覺樣式。
- `POST /api/tracer/projects/{project_id}/exports`：建立單球特效匯出任務（支援 `original`/`16:9`/`9:16` × `30`/`60fps` × `preserve`/`mute`）。
- `POST /api/tracer/exports/batch`：建立 1–10 球多球連續合輯匯出任務。
- `GET /api/tracer/exports/{export_id}`：查詢匯出進度、Parity 報告、MP4 與 `.tracer.json` Sidecar 下載連結。
- `GET /api/tracer/exports/{export_id}/download` / `GET /api/tracer/exports/{export_id}/sidecar`：串流下載 MP4 與 `.tracer.json` 溯源檔案。
