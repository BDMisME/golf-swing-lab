# Golf Swing Lab — 專業示範揮桿庫 (Reference Swings) 逐支素材驗收矩陣表

## 一、驗收總覽

- **素材來源**：`~/Downloads/GSL_reference_videos_bundle_20261029.zip`
- **匯入暫存**：`~/.golfswinglab/reference_import_staging/`
- **本機隔離儲存庫**：`~/.golfswinglab/storage/references/<club_slug>/`
- **驗收狀態**：**全數 16 支素材檔案（100% SHA-256 吻合）成功完成切片、姿態分析與入庫**
- **資料庫記錄**：共 18 筆示範揮桿記錄（涵蓋 13 種主要球桿 + 3 支 Bonus，Driver 3 筆、7I 2 筆、SW 2 筆）
- **球桿分類覆蓋**：完整支援 19 類球桿（Driver ~ Putter）+ 通用 Hybrid 選擇器。4 桿無合法教練 DTL 示範之球桿（3I, 7W, Hybrid, GW）維持 `missing_reference` 狀態，提供透明缺桿提示與手動匯入導引。

---

## 二、逐支素材驗收清單 (16 支 MP4)

| 項次 | 原始檔名 | 桿種 | 視角標記 | 實際揮桿數 | 可否比較 | 是否需人工確認 | 來源授權狀態 | 匯入結果與系統標籤 |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
| **01** | `01_Driver.mp4` | **Driver** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (DJ Watts / WAX Golf) · 待使用者商業授權確認 | `completed` · 預設 Driver 示範 · 原速 5.0s |
| **02** | `02_Wood3.mp4` | **3W** | DTL | 1 記全揮桿 | **可比較 (姿勢)** | 是 (慢動作) | YouTube (Milo Lines) · 待使用者商業授權確認 | `completed` · 預設 3W · 標註 `⏱️ 慢動作示範` (240fps，不計入自然節奏) |
| **03** | `03_Wood5.mp4` | **5W** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (Giles Gill) · 待使用者商業授權確認 | `completed` · 預設 5W · 裁切右半 5W 揮桿段，切除口播 |
| **04** | `07_Iron4.mp4` | **4I** | DTL | 1 記全揮桿 | **可比較** | **是 (桿號推定)** | YouTube (DJ Watts) · 待使用者商業授權確認 | `needs_calibration` · 與 7I 合輯，桿號依標題順序推定 |
| **05** | `08_Iron5.mp4` | **5I** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (DJ Watts) · 待使用者商業授權確認 | `completed` · 預設 5I · 乾淨原速 DTL 全揮桿 |
| **06** | `09_Iron6.mp4` | **6I** | rear_indoor | 1 記全揮桿 | **可比較 (姿勢)** | **是 (視角/慢動作)** | YouTube (Freddie Meikle PGA) · 待使用者商業授權確認 | `needs_calibration` · 直式 360x640 室內模擬器慢動作 · 標註 `⏱️ 慢動作` 與 `📷 非標準 DTL` |
| **07** | `10_Iron7.mp4` | **7I** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (DJ Watts) · 待使用者商業授權確認 | `completed` · 預設 7I · 原片含桿號標籤，原速 DTL 全揮桿 |
| **08** | `11_Iron8.mp4` | **8I** | DTL | 1 記全揮桿 | **可比較** | **是 (桿號推定)** | YouTube (DJ Watts) · 待使用者商業授權確認 | `needs_calibration` · 與 5I 合輯，DTL 段依標題順序推定為 8I，建議目視複核 |
| **09** | `12_Iron9.mp4` | **9I** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (DJ Watts) · 待使用者商業授權確認 | `completed` · 預設 9I · 片頭標籤明示 9 Iron，原速 DTL 全揮桿 |
| **10** | `13_PW.mp4` | **PW** | rear_oblique | 1 記全揮桿 | **可比較** | **是 (視角微偏斜)** | YouTube (Robin Rosado) · 待使用者商業授權確認 | `needs_calibration` · 後方視角微偏斜，球桿依配套文章認定 · 標註 `📷 非標準 DTL` |
| **11** | `15_SW.mp4` | **SW** | DTL | 1 記 Pitch | **可比較 (姿勢)** | **是 (慢動作/Pitch)** | YouTube (Milo Lines) · 待使用者商業授權確認 | `completed` · 預設 SW · 標註 `⏱️ 慢動作` 與 `⚠️ 非全揮桿 (90碼 Pitch)` |
| **12** | `16_LW.mp4` | **LW** | rear_oblique | 1 記 Flop | **可比較 (特殊)** | **是 (Flop視角)** | YouTube (A.J. Nelson PGA) · 待使用者商業授權確認 | `needs_calibration` · 標註 `⚠️ 非全揮桿 (高拋 Flop)` 與 `📷 非標準 DTL` |
| **13** | `17_Putter.mp4` | **Putter** | close_up | 1 記推桿 | **可比較 (推桿)** | **是 (推桿特寫)** | YouTube (Titleist) · 待使用者商業授權確認 | `needs_calibration` · 標註 `⚠️ 非全揮桿 (推桿特寫)` 與 `📷 非標準 DTL`，需推桿專屬模型 |
| **14** | `Bonus Driver_LouisGolf_TW.mp4` | **Driver** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | 台灣教練 Louis Golf · 待授權確認 | `completed` · 備選 Driver 示範 · 直式 360x640 台灣教練原速 DTL |
| **15** | `Bonus Driver_WAX_alt.mp4` | **Driver** | DTL | 1 記全揮桿 | **可比較** | 否 (已驗證) | YouTube (DJ Watts) · 待使用者商業授權確認 | `completed` · 備選 Driver 示範 · MCS Classic 版原速 DTL |
| **16** | `Bonus SW_Bunker_Titleist.mp4` | **SW** | side_oblique | 1 記沙坑球 | **僅限特殊情境** | **是 (沙坑側面)** | YouTube (Trillium Rose LPGA) · 待使用者商業授權確認 | `needs_calibration` · 備選 SW 示範 · 標註 `⚠️ 非全揮桿 (沙坑示範)` 與 `📷 非標準 DTL` |

---

## 三、缺桿現狀說明（4 桿：3I, 7W, Hybrid, GW）

1. **現況調查結論**：
   - 經三路研究檢索與抽幀驗證，YouTube 及主流教學頻道上目前「教練本人＋DTL 正後方視角＋純動作示範無口播遮擋」的短片在 3I、7W、通用 Hybrid 與 50°–52° GW 實質不存在合格素材。
   - 大多數素材為口播講解、正面切球教學、或業餘學員測試，無法作為標準技術示範。
2. **系統防禦機制**：
   - 系統依據最高誠信原則，**嚴禁拿其他鐵桿（如 4I/7I）改名充當 3I 或 GW**，亦嚴禁拿 5W 改名冒充 7W。
   - 在前端切換至 7W、3I、GW 或 Hybrid 時，明確標示 `尚無此球桿示範影片 (missing_reference)`，並展示友好導引與使用者自訂上傳按鈕，支援使用者日後自行匯入合規素材。

---

## 四、慢動作與非全揮桿素材之使用規範

1. **慢動作影片規範（3W, 6I, SW）**：
   - 來源為 240fps 高速攝影或慢動作後製。
   - 系統在前端播放器左上角明確標示 `⏱️ 慢動作示範 (僅供姿勢影格比較，不計真實節奏)`。
   - 系統**嚴禁**將慢動作影片之時間碼用於計算自然節奏比例（Tempo Ratio 3:1 等），僅供在各關鍵影格進行骨架幾何與肢體對照。
2. **特殊動作與非全揮桿規範（SW 90碼 Pitch、LW 高拋球、Putter 推桿、SW 沙坑）**：
   - 系統在資料庫中標記 `shot_type`，並在前端播放器提示 `⚠️ 非全揮桿` 與 `📷 非標準 DTL`。
   - 絕不將特殊短桿或推桿動作冒充為標準 DTL 全揮桿，避免誤導球友。

---

## 五、著作權與資料治理合規說明

1. **本機獨立儲存**：
   - 所有第三方示範影片實體檔案均存於使用者的本機快取目錄 `~/.golfswinglab/storage/references/`，**未將任何影片二進位大檔加入 Git 版控或推送到 GitHub 遠端倉庫**。
   - `.gitignore` 嚴格排除各類媒體檔案（`.mp4`, `.mov`, `.zip`）。
2. **版權授權宣告**：
   - 系統內部將此批素材標註為 `reference_category: test_fixture`（個人技術測試與研究用途），來源類型標為 `local_fixture`。
   - 系統明確標註 `is_verified_standard = false`，不宣稱為官方商業認證或巡迴賽標準。若未來需正式商業釋出，需取得各原創頻道或教練之商業授權。
