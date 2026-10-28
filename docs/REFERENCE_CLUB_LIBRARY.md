# Golf Swing Lab — 完整球桿示範影片資料庫規範與清單 (Reference Swing Library)

**版本**：v2.0 (Swing Comparison & Evidence-Based Coaching R2)  
**更新日期**：2026-10-28  
**最高原則**：
1. **球桿分類真實性**：嚴禁將某支鐵桿影片改名冒充另一支球桿。
2. **標準等級真實性**：嚴禁將未經認證的一般練習者或不明球桿影片標註為「已驗證職業標準」。
3. **視角真實性**：非全身後方視角（DTL）之影片（如桿頭特寫或半身鏡頭）嚴禁宣告為全身 DTL 標準，系統必須標記 `verified_camera_angle = false` 並在比較播放時給予視角相容性警示。
4. **著作權合規**：僅在具備合法授權（如 CC0 / Pexels License / 內部基線素材）時方實體下載打包；受版權保護之外部教學資源僅追蹤來源與作者；目前尚未取得合格授權素材之球桿一律誠實標註 `missing_reference`，並提供標準化本機匯入流程。

---

## 一、17 種球桿支援分類與現行狀態總表

| 球桿代碼 | 球桿名稱 | 類別 | 現行狀態 | 示範影片檔案 / 來源 | 視角與驗證狀態 | 示範類別與說明 | 揮桿時間同步支援 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Driver** | 1號木桿 | 木桿 | `available` (特寫) | `ref_driver_closeup.mp4` (Pexels 6541451) | Close-up (打擊特寫，非全身 DTL，`verified=false`) | `ordinary_reference` (一般公開特寫素材，非職業標準) | 支援自然節奏對齊 (附視角與未驗證警示) |
| **3W** | 3號球道木桿 | 木桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **5W** | 5號球道木桿 | 木桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **3H** | 3號鐵木桿 / 混血桿 | 鐵木桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **4H** | 4號鐵木桿 / 混血桿 | 鐵木桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **5H** | 5號鐵木桿 / 混血桿 | 鐵木桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **4I** | 4號長鐵桿 | 鐵桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **5I** | 5號長鐵桿 | 鐵桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **6I** | 6號中鐵桿 | 鐵桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **7I** | 7號中鐵桿 | 鐵桿 | `available` (技術測試基準) | `ref_7i_dtl_standard.mp4` (內部測試錄影) | DTL 全身 (1080x1920 60fps，`verified_club=false`, `is_verified_standard=false`) | `test_fixture` (僅供管線技術測試，非職業標準) | 支援 Mode A 自然節奏與 Mode B 階段同步 |
| **8I** | 8號中鐵桿 | 鐵桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **9I** | 9號短鐵桿 | 鐵桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **PW** | 劈起挖起桿 (Pitching Wedge) | 挖起桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **GW/AW** | 間隙/接近挖起桿 (Gap/Approach) | 挖起桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **SW** | 沙坑挖起桿 (Sand Wedge) | 挖起桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **LW** | 高拋挖起桿 (Lob Wedge) | 挖起桿 | `missing_reference` | 待合法 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |
| **Putter** | 推桿 | 推桿 | `missing_reference` | 待合法推桿 DTL 素材匯入 | 無 | 待授權匯入 (`needs_calibration`) | 支援手動匯入與自訂時間碼 |

---

## 二、外部候選來源研究與評估記錄

本專案依照使用者指示，針對以下公開及專業來源進行深入調研與法律/技術評估：

### 1. Ignition Golf — Paul's Swing Rear
- **來源網址**：`https://ignitiongolf.com/pauls-swing-rear/`
- **影片內容**：PGA 教練 Paul Wilson 之純後方視角（DTL）示範揮桿。
- **球桿推估**：鐵桿（典型中鐵桿）。
- **畫質與幀率**：標清/高清、慢動作播放。
- **評估結論**：具有極佳的示範教學價值。惟其網站版權歸 Ignition Golf 所有，未具備 CC0 或明確商用轉散佈授權，依著作權合規原則，系統保留其作者與來源記錄（Author: Paul Wilson），未直接違法打包下載其原始影片檔；使用者可透過本機匯入功能將合法購買或快取之檔案載入。

### 2. Edouard Laflamme Golf 2026
- **來源網址**：`https://www.edouardlaflammegolf2026.com/videos`
- **影片內容**：青少年/專業培訓選手 Edouard Laflamme 之比賽與練習紀錄。
- **球桿推估**：Driver 與多種鐵桿。
- **評估結論**：多數為競賽現場或個人訓練視角，包含斜角與變動鏡頭；且屬於私人選手肖像與版權，不可在未獲正式書面授權下直接作為公開預設庫。

### 3. Pexels 免費影片庫
- **Pexels 6541451 (Driver 打擊區特寫)**：
  - **實際內容**：由打擊墊後下方近距離拍攝球桿與小白球之擊球特寫，未拍到球員上半身與頭部。
  - **處理決策**：合法取得並實體裁切儲存於 `assets/reference_videos/ref_driver_closeup.mp4`。依誠信原則，在資料庫中明確標記 `camera_angle="close_up"`，`verified_camera_angle=false`，並在前端播放時觸發「非全身 DTL 鏡頭，不可用於比較身體 2D 關節角度」警示。
- **Pexels 6256584**：
  - **實際內容**：球場休閒打球側面特寫，下半身與站姿未完整入鏡。
  - **處理決策**：不符合 DTL 全身標準，不予收錄。
- **Pexels 6541976**：
  - **實際內容**：女子於肩膀後方持桿之熱身與伸展鏡頭，非真實打擊揮桿。
  - **處理決策**：不符合揮桿動作標準，不予收錄。

### 4. ShinGolf / GolfBoy JP
- **來源網址**：`https://shingolf.golfboy.jp/en`
- **評估結論**：高爾夫科技應用與感測器示範，非開放原始碼自由版權庫。保留來源索引供使用者參考。

---

## 三、7I 技術測試基準素材規格 (Test Fixture)

已正式打包並內建於專案庫存（僅作為工程管線技術測試與雙影片播放對齊之 baseline fixture，非職業教練標準）：
- **素材類別**：`test_fixture`（`is_verified_standard=false`，`verified_club=false`）
- **實體路徑**：`assets/reference_videos/ref_7i_dtl_standard.mp4`
- **儲存物件鍵**：`reference_swings/7i/ref_7i_dtl_standard.mp4`
- **SHA-256**：`080c98f98ec5172283a21644e5ce6c9b33a04a0e38685e1975e533036881938b`
- **視訊規格**：1080 x 1920（9:16 直式），59.94 fps，H.264
- **有效時長**：7,200 ms（7.2 秒完整揮桿歷程）
- **關鍵事件時間碼**：
  - `address`: 700 ms
  - `takeaway`: 1,100 ms
  - `backswing`: 1,367 ms
  - `top`: 1,633 ms
  - `downswing`: 1,833 ms
  - `impact_estimated`: 2,033 ms
  - `follow_through`: 2,500 ms
  - `finish`: 4,433 ms
- **自動對齊參數 (Framing Calibration)**：
  - `torso_length`: 0.385 (正規化身長比例)
  - `scale`: 1.00
  - `zoom`: 1.00
  - `offset_x`: 0.00
  - `offset_y`: 0.00

---

## 四、資料模型與後端 API 規格

### 1. 資料模型 `reference_swings`
已建立於 PostgreSQL 資料庫中，包含欄位：
- `id`: UUID Primary Key
- `club_type`: 17 種球桿列舉字串
- `handedness`: `right` / `left`
- `camera_angle`: `dtl` / `fo` / `close_up`
- `shot_type`: `full_swing` / `pitch` / `chip` / `putt`
- `title`, `reference_author`, `source_url`, `content_license`
- `storage_key`, `thumbnail_url`
- `verified_club`: Boolean（是否經過確認為該指定球桿）
- `verified_camera_angle`: Boolean（是否經過確認為合規全身 DTL）
- `fps`: 視訊精確幀率
- `duration_ms`: 總長度毫秒數
- `sha256`: 視訊完整性雜湊
- `event_timestamps_json`: 包含 9 階段事件時間碼之 JSON 物件
- `pose_artifact_json`: 包含 MediaPipe 2D 關鍵骨架點
- `calibration_params_json`: 包含 Auto-Framing 縮放與置中參數
- `is_default`: Boolean

### 2. REST API 端點
- `GET /api/reference-swings`：取得全部 17 種球桿之目前可用狀態、示範影片數量與預設示範物件。
- `GET /api/reference-swings/default/{club_type}`：取得指定球桿之預設示範揮桿詳情。
- `GET /api/reference-swings/{id}`：取得特定示範揮桿完整資料。
- `GET /api/reference-swings/{id}/stream`：支援 HTTP 206 Partial Content Range 請求之高品質視訊串流。
- `POST /api/reference-swings/import-local`：支援使用者本機匯入特定球桿之示範影片並自動建立時間戳記與校正參數。

---

## 五、手動匯入其他球桿示範影片流程

當使用者選擇標記為 `missing_reference` 之球桿（例如 3W、5W、PW 等）時：
1. **介面提示**：系統在比較視圖中明確提示「該球桿目前尚無已確認的示範揮桿影片 (missing_reference)」，並顯示「＋ 匯入此球桿的示範影片」按鈕。
2. **匯入對話窗**：點擊後彈出匯入 Modal，允許輸入：
   - 影片檔案路徑 / URL
   - 授權與作者說明（例如自製拍攝、合法購買之教學素材）
   - 各階段時間碼（Address, Top, Impact, Finish）或由系統自動執行粗精偵測。
3. **儲存與即時比較**：匯入成功後立即寫入 `reference_swings` 資料庫與本機儲存，即刻刷新比較播放器，無縫進入雙影片同步比對模式。
