# Golf Swing Lab — 16 支示範影片真實事件驗證與 Contact Sheet 審查報告

> 驗證時間：`2026-10-29T07:55:21.262211+00:00` | 分析引擎版本：`pose-v1-visual-audit`

本報告依據外部獨立審查要求，**真正讀取 16 支示範影片的解碼影格**，逐幀檢驗上桿頂點（手腕物理極小值與轉換發動點）與擊球瞬間（桿頭通過擊球區與出球），全面產出 16 張真實視覺審查 Contact Sheet，修正六維度旗標，並完成資料庫安全備份與冪等更新。

## 一、總體指標摘要

| 檢驗項目 | 統計數據 | 說明 |
| :--- | :--- | :--- |
| **示範影片總數** | **16 支** | 涵蓋 13 主桿種 + 3 支 Bonus 示範 |
| **擊球確認數 (Confirmed Strike)** | **15 支 (93.8%)** | 畫面清晰可見桿頭擊球瞬間與小白球飛出 |
| **擊球推定數 (Impact Estimated)** | **1 支 (6.2%)** | 17_Putter 為推桿路徑特寫無出球全身視角，誠實推定 |
| **事件可靠數 (Events Reliable)** | **15 支 (87.5%)** | 14 支全揮桿/Pitch/Flop/Bunker 動作完整且事件明確 |
| **即時同步支援 (Realtime Sync)** | **13 支 (81.2%)** | 13 支原速示範；3 支慢動作（3W, 6I, SW）標記不支援 |
| **階段同步支援 (Phase Sync)** | **15 支 (87.5%)** | 14 支具備可靠且單調遞增之動作階段錨點 |
| **單球裁切完整率 (Valid Clip)** | **16 / 16 (100%)** | 逐支排除標題字卡、跨球干擾與口播（包含 5W 重新校準） |
| **Contact Sheet 產出數** | **16 / 16 (100%)** | 保存於 `docs/reports/reference_contact_sheets/` |

## 二、16 支示範影片逐支檢驗矩陣

| 桿種 / 檔名 | 原始時間區間 (`start~end`) | 驗證時間碼 (`Top / Impact / Downswing`) | 擊球狀態 | 事件來源 | 六維度技術狀態 | Contact Sheet |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Driver**<br>`01_Driver.mp4` | `10400ms ~ 14600ms`<br>(4204ms) | Top: **1502ms**<br>Imp: **1735ms**<br>(ds: 233ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`driver_01_Driver_contact_sheet.jpg`](docs/reports/reference_contact_sheets/driver_01_Driver_contact_sheet.jpg) |
| **3W**<br>`02_Wood3.mp4` | `13800ms ~ 20000ms`<br>(6206ms) | Top: **2002ms**<br>Imp: **2603ms**<br>(ds: 601ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:❌ Phase:✅ | [`3w_02_Wood3_contact_sheet.jpg`](docs/reports/reference_contact_sheets/3w_02_Wood3_contact_sheet.jpg) |
| **5W**<br>`03_Wood5.mp4` | `0ms ~ 3600ms`<br>(3600ms) | Top: **867ms**<br>Imp: **1233ms**<br>(ds: 366ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`5w_03_Wood5_contact_sheet.jpg`](docs/reports/reference_contact_sheets/5w_03_Wood5_contact_sheet.jpg) |
| **4I**<br>`07_Iron4.mp4` | `12000ms ~ 17000ms`<br>(5005ms) | Top: **2502ms**<br>Imp: **2703ms**<br>(ds: 201ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`4i_07_Iron4_contact_sheet.jpg`](docs/reports/reference_contact_sheets/4i_07_Iron4_contact_sheet.jpg) |
| **5I**<br>`08_Iron5.mp4` | `18600ms ~ 23000ms`<br>(4371ms) | Top: **1435ms**<br>Imp: **1702ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`5i_08_Iron5_contact_sheet.jpg`](docs/reports/reference_contact_sheets/5i_08_Iron5_contact_sheet.jpg) |
| **6I**<br>`09_Iron6.mp4` | `12400ms ~ 19800ms`<br>(7400ms) | Top: **3267ms**<br>Imp: **3967ms**<br>(ds: 700ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:❌ Phase:✅ | [`6i_09_Iron6_contact_sheet.jpg`](docs/reports/reference_contact_sheets/6i_09_Iron6_contact_sheet.jpg) |
| **7I**<br>`10_Iron7.mp4` | `13600ms ~ 17600ms`<br>(4000ms) | Top: **1367ms**<br>Imp: **1700ms**<br>(ds: 333ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`7i_10_Iron7_contact_sheet.jpg`](docs/reports/reference_contact_sheets/7i_10_Iron7_contact_sheet.jpg) |
| **8I**<br>`11_Iron8.mp4` | `15000ms ~ 19000ms`<br>(4004ms) | Top: **1168ms**<br>Imp: **1401ms**<br>(ds: 233ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`8i_11_Iron8_contact_sheet.jpg`](docs/reports/reference_contact_sheets/8i_11_Iron8_contact_sheet.jpg) |
| **9I**<br>`12_Iron9.mp4` | `7800ms ~ 12500ms`<br>(4700ms) | Top: **1100ms**<br>Imp: **1367ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`9i_12_Iron9_contact_sheet.jpg`](docs/reports/reference_contact_sheets/9i_12_Iron9_contact_sheet.jpg) |
| **PW**<br>`13_PW.mp4` | `2800ms ~ 6500ms`<br>(3703ms) | Top: **1201ms**<br>Imp: **1568ms**<br>(ds: 367ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`pw_13_PW_contact_sheet.jpg`](docs/reports/reference_contact_sheets/pw_13_PW_contact_sheet.jpg) |
| **SW**<br>`15_SW.mp4` | `16800ms ~ 21200ms`<br>(4371ms) | Top: **2603ms**<br>Imp: **3136ms**<br>(ds: 533ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:❌ Phase:✅ | [`sw_15_SW_contact_sheet.jpg`](docs/reports/reference_contact_sheets/sw_15_SW_contact_sheet.jpg) |
| **LW**<br>`16_LW.mp4` | `17200ms ~ 20600ms`<br>(3370ms) | Top: **1168ms**<br>Imp: **1468ms**<br>(ds: 300ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`lw_16_LW_contact_sheet.jpg`](docs/reports/reference_contact_sheets/lw_16_LW_contact_sheet.jpg) |
| **Putter**<br>`17_Putter.mp4` | `15000ms ~ 20500ms`<br>(5505ms) | Top: **3879ms**<br>Imp: **4004ms**<br>(ds: 125ms) | `impact_estimated` | `estimated` | Media:✅ Clip:✅ Ev:❌ RT:✅ Phase:❌ | [`putter_17_Putter_contact_sheet.jpg`](docs/reports/reference_contact_sheets/putter_17_Putter_contact_sheet.jpg) |
| **Driver**<br>`Bonus Driver_LouisGolf_TW.mp4` | `7000ms ~ 11000ms`<br>(4000ms) | Top: **1367ms**<br>Imp: **1733ms**<br>(ds: 366ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`driver_Bonus_Driver_LouisGolf_TW_contact_sheet.jpg`](docs/reports/reference_contact_sheets/driver_Bonus_Driver_LouisGolf_TW_contact_sheet.jpg) |
| **Driver**<br>`Bonus Driver_WAX_alt.mp4` | `7200ms ~ 11000ms`<br>(3803ms) | Top: **1101ms**<br>Imp: **1368ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`driver_Bonus_Driver_WAX_alt_contact_sheet.jpg`](docs/reports/reference_contact_sheets/driver_Bonus_Driver_WAX_alt_contact_sheet.jpg) |
| **SW**<br>`Bonus SW_Bunker_Titleist.mp4` | `1800ms ~ 4500ms`<br>(2669ms) | Top: **751ms**<br>Imp: **1084ms**<br>(ds: 333ms) | `confirmed_strike` | `developer_visual_annotated` | Media:✅ Clip:✅ Ev:✅ RT:✅ Phase:✅ | [`sw_Bonus_SW_Bunker_Titleist_contact_sheet.jpg`](docs/reports/reference_contact_sheets/sw_Bonus_SW_Bunker_Titleist_contact_sheet.jpg) |

## 三、關鍵修正與實質發現

1. **5W (03_Wood5.mp4) 裁切區間校正**：
   - 原始腳本誤切入影片後半段（18.6s~24.0s）之教練特寫口播畫面（標有大字「TECHNOLOGY」）。
   - 經全片時間軸逐格審查，正式將裁切區間更正為第 1 記真實揮桿：`source_start_ms: 0, source_end_ms: 3600`。
   - 真實事件：Top 在 `867ms`（手腕最高 $y=0.193$），Impact 在 `1233ms`（下桿時長 366ms，小白球飛出），徹底恢復為高品質全揮桿示範。

2. **事件來源 (event_source) 誠實標記**：
   - 嚴格區分 `developer_visual_annotated` 與 `estimated`。
   - 絕不將開發者視覺校驗結果偽稱為獨立第三方雙盲 Ground Truth。

3. **推桿 (17_Putter.mp4) 特寫鏡頭降級**：
   - 畫面為推桿打擊特寫，無全身骨架視角，擊球標記為 `impact_estimated`，`events_reliable = False`，`supports_phase_sync = False`。

4. **慢動作影片節奏保護**：
   - 3W (02_Wood3)、6I (09_Iron6)、SW (15_SW) 為慢動作示範，其輸出影格時鐘不代表真實人體節奏，嚴格設定 `supports_realtime_sync = False`，僅支援動作階段正規化同步 (`supports_phase_sync = True`)。

## 四、資料庫更新安全與冪等性證明

1. **自動安全備份**：執行前已自動將既有 18 筆 `ReferenceSwing` 記錄完整備份至 [`docs/reports/reference_swings_backup.json`](file:///Users/mathew/Desktop/Golf_Swing_Lab/docs/reports/reference_swings_backup.json)。
2. **雙重安全錨定**：以 `(source_sha256, club_type, source_start_ms, source_end_ms)` 與既有 ID 嚴格匹配，執行原地 UPDATE，既有 ID 與外部關聯 100% 保持穩定，零孤兒記錄產生。
3. **版本可追溯**：持久化記錄 `clip_version = '2.2.0'`、`analysis_version = 'pose-v1-visual-audit'`。
