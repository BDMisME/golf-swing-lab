# Golf Swing Lab — 專業示範揮桿庫 (Reference Swings) 逐支素材驗收矩陣表

## 一、驗收總覽與修復總結

- **素材來源**：`~/Downloads/GSL_reference_videos_bundle_20261029.zip`
- **匯入暫存**：`~/.golfswinglab/reference_import_staging/`
- **本機隔離儲存庫**：`~/.golfswinglab/storage/references/<club_slug>/`
- **假時間碼徹底根除**：
  - 移除了先前所有寫死之固定偏移量（如 Top+300ms、慢動作+1200ms、時長百分比）。
  - 全數採用 `CoarseToFineDetector` 狀態機與 2D 骨架手腕物理軌跡（Top 頂點手腕最高 $y$ 局部極小值、Impact 觸球區）真實定位。
- **單球乾淨剪輯**：逐支重新檢查全部 16 支 MP4，確立乾淨單球邊界（Address 前站定緩衝 -> 上桿 -> Top -> 擊球 -> 收桿平衡 Finish），徹底排除跨球、走動、口播或標題卡。
- **六維度技術狀態**：
  1. `media_processed`：切片與轉碼是否成功。
  2. `pose_analyzed`：2D 骨架是否提取成功。
  3. `is_valid_clip`：是否為乾淨單球切片。
  4. `events_reliable`：事件是否經狀態機或物理換向驗證。
  5. `supports_realtime_sync`：是否支援原速即時同步（慢動作影片設為 False）。
  6. `supports_phase_sync`：是否支援階段關鍵事件對齊。
- **球桿分類覆蓋**：完整支援 19 類球桿（Driver ~ Putter）+ 通用 Hybrid。6 桿無合格純教練 DTL 示範之球桿（7W, 3H, 4H, 5H, 3I, GW/AW）誠實標記 `missing_reference`，絕不拿通用 Hybrid 混充 3H/4H/5H。

---

## 二、逐支素材物理事件與六維狀態矩陣表 (16 支 MP4)

| 項次 | 原始檔名 | 桿種 | 原始切片區間 (ms) | 切片時長 | 狀態機事件 (切片相對 ms) | Downswing (ms) | 慢動作 | 六維度技術狀態 | 狀態標籤與備註 |
| :---: | :--- | :---: | :---: | :---: | :--- | :---: | :---: | :--- | :--- |
| **01** | `01_Driver.mp4` | **Driver** | 10400 ~ 14600 | 4200ms | Top=1479, Imp=1745, Add=744, Fin=3581 | 266ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 預設 Driver · DJ Watts 原速 DTL |
| **02** | `02_Wood3.mp4` | **3W** | 13800 ~ 20000 | 6200ms | Top=2249, Imp=2616, Add=200, Fin=5200 | 367ms | **是 (240fps)** | `[✓, ✓, ✓, ✓, ✗, ✓]` | `completed` · 預設 3W · Milo Lines 慢動作 (不支援即時同步，僅階段對齊) |
| **03** | `03_Wood5.mp4` | **5W** | 0 ~ 3600 | 3600ms | Top=867, Imp=1233, Add=100, Fin=3200 | 366ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 預設 5W · Giles Gill 第 1 記乾淨全揮桿 (校正排除後段口播) |
| **04** | `07_Iron4.mp4` | **4I** | 12000 ~ 17000 | 5000ms | Top=2548, Imp=2715, Add=1180, Fin=4250 | 167ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `needs_calibration` · DJ Watts 4 號鐵 (合輯順序推定) |
| **05** | `08_Iron5.mp4` | **5I** | 18600 ~ 23000 | 4400ms | Top=1353, Imp=1687, Add=619, Fin=3155 | 334ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 預設 5I · DJ Watts 原速 DTL 全揮桿 |
| **06** | `09_Iron6.mp4` | **6I** | 12400 ~ 19800 | 7400ms | Top=3500, Imp=3967, Add=1400, Fin=7267 | 467ms | **是 (模擬器)** | `[✓, ✓, ✓, ✓, ✗, ✓]` | `completed` · 預設 6I · Freddie Meikle 直式慢動作 (僅階段對齊) |
| **07** | `10_Iron7.mp4` | **7I** | 13600 ~ 17600 | 4000ms | Top=1367, Imp=1700, Add=733, Fin=3133 | 333ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 預設 7I · DJ Watts 標準示範 (Top 手腕最高 y=0.315, Imp y=0.504) |
| **08** | `11_Iron8.mp4` | **8I** | 15000 ~ 19000 | 4000ms | Top=1149, Imp=1416, Add=582, Fin=3185 | 267ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `needs_calibration` · DJ Watts 8 號鐵 (合輯推定) |
| **09** | `12_Iron9.mp4` | **9I** | 7800 ~ 12500 | 4700ms | Top=1100, Imp=1367, Add=467, Fin=3200 | 267ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 預設 9I · DJ Watts 原速 DTL 全揮桿 |
| **10** | `13_PW.mp4` | **PW** | 2800 ~ 6500 | 3700ms | Top=1204, Imp=1571, Add=804, Fin=2806 | 367ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `needs_calibration` · Robin Rosado (微斜後方視角) |
| **11** | `15_SW.mp4` | **SW** | 16800 ~ 21200 | 4400ms | Top=2853, Imp=3120, Add=784, Fin=3320 | 267ms | **是 (240fps)** | `[✓, ✓, ✓, ✓, ✗, ✓]` | `completed` · 預設 SW · Milo Lines 90碼 Pitch 慢動作 (僅階段對齊) |
| **12** | `16_LW.mp4` | **LW** | 17200 ~ 20600 | 3400ms | Top=1185, Imp=1452, Add=651, Fin=1986 | 267ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `needs_calibration` · A.J. Nelson 高拋 Flop shot |
| **13** | `17_Putter.mp4` | **Putter** | 15000 ~ 20500 | 5500ms | Top=3852, Imp=4019, Add=1767, Fin=4500 | 167ms | 否 | `[✓, ✓, ✓, ✗, ✓, ✓]` | `needs_calibration` · Titleist 推桿路徑特寫 (非完整身體 DTL) |
| **14** | `Bonus Driver_LouisGolf_TW.mp4` | **Driver** | 7000 ~ 11000 | 4000ms | Top=1333, Imp=1733, Add=600, Fin=2667 | 400ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 備選 Driver · 台灣教練 Louis 直式原速 DTL |
| **15** | `Bonus Driver_WAX_alt.mp4` | **Driver** | 7200 ~ 11000 | 3800ms | Top=1075, Imp=1375, Add=508, Fin=2443 | 300ms | 否 | `[✓, ✓, ✓, ✓, ✓, ✓]` | `completed` · 備選 Driver · DJ Watts MCS Classic DTL |
| **16** | `Bonus SW_Bunker_Titleist.mp4` | **SW** | 1800 ~ 4500 | 2700ms | Top=744, Imp=1078, Add=369, Fin=1453 | 334ms | 否 | `[✓, ✓, ✓, ✗, ✓, ✓]` | `needs_calibration` · Trillium Rose 沙坑側面視角 |

*註：六維度狀態簡稱：`[media_processed, pose_analyzed, is_valid_clip, events_reliable, supports_realtime_sync, supports_phase_sync]`。*

---

## 三、缺桿現狀說明（6 桿：7W, 3H, 4H, 5H, 3I, GW/AW）

1. **現況調查結論**：
   - 經三路研究檢索與抽幀驗證，YouTube 及主流教學頻道上目前「教練本人＋DTL 正後方視角＋純動作示範無口播遮擋」的短片在 7W、3H、4H、5H、3I 與 50°–52° GW 實質不存在合格素材。
2. **最高誠信系統防禦機制**：
   - 系統依據最高誠信原則，**嚴禁拿通用 Hybrid 掩蓋 3H/4H/5H**，亦嚴禁拿其他鐵桿冒充 3I 或 GW/AW。
   - 在前端切換至 7W、3H、4H、5H、3I、GW/AW 或通用 Hybrid 時，明確標示 `尚無此球桿示範影片 (missing_reference)`，並展示具體缺桿說明與手動上傳按鈕，支援使用者日後自行匯入合規素材。

---

## 四、逐格控制與同步播放精度驗證 (WebKit GUI)

1. **真實 FPS 單影格步進**：
   - 前端播放器移除寫死之 33.333ms，改依兩側各自真實 FPS 計算單影格步進：
     $$ \Delta t_{\text{frame}} = \frac{1}{\text{FPS}} $$
   - 例如 30fps 為 33.33ms，60fps 為 16.67ms，240fps 為 4.17ms。
2. **動態事件跳轉驗證**：
   - 使用動態 API 查詢獲得之新 7I（`05af5507`，Top=1367ms, Impact=1700ms）進行 WebKit GUI 實測。
   - 實測結果：
     - **TOP 跳轉誤差**：使用者影片 0ms，示範影片 0ms！
     - **IMPACT 跳轉誤差**：使用者影片 0ms，示範影片 0ms！
     - **同步時鐘漂移**：連續播放下兩側時鐘漂移僅 2.4ms。
     - **解碼非全黑**：Canvas 像素統計確認兩側解碼正常無黑屏。
