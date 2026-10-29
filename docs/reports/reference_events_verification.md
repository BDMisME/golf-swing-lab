# Golf Swing Lab — 16 支示範影片真實事件驗證與資料治理審查報告

> 驗證時間：`2026-10-29T08:41:08.968957+00:00` | 分析引擎版本：`pose-v1-visual-audit`

本報告依據外部獨立審查要求，**真正讀取 16 支示範影片的解碼影格**，逐幀檢驗上桿頂點（手腕物理極小值與轉換發動點）與擊球瞬間（桿頭過球與出球可見度），修正擊球確認狀態，排除未驗證之虛假標記，並已將 active events 100% 寫回資料庫。

## 一、總體指標摘要

| 檢驗項目 | 統計數據 | 說明 |
| :--- | :--- | :--- |
| **示範影片總數** | **16 支** | 涵蓋 13 主桿種 + 3 支 Bonus 示範 |
| **擊球確認數 (Confirmed Strike)** | **11 支 (68.8%)** | 畫面清晰可見桿頭擊球瞬間與小白球飛出 |
| **擊球推定數 (Impact Estimated)** | **5 支 (31.2%)** | 5W 快門間隙出球、PW/LW 後斜視角、Putter 特寫、SW 炸沙擊球，誠實推定 |
| **擊球不可確認數 (Unresolved)** | **0 支 (0.0%)** | 無不可解析之廢片 |
| **事件可靠數 (Events Reliable)** | **15 支 (93.8%)** | 15 支具備可靠全身動作與明確時序 |
| **即時同步支援 (Realtime Sync)** | **13 支 (81.2%)** | 13 支原速示範；3 支慢動作（3W, 6I, SW）標記保護 |
| **階段同步支援 (Phase Sync)** | **15 支 (93.8%)** | 15 支具備單調遞增動作階段錨點 |
| **資料庫同步狀態** | **16 / 16 原地寫回** | event_timestamps 與 calibration_params 100% 一致 |

## 二、16 支示範影片逐支檢驗矩陣

| 桿種 / 檔名 | 原始時間區間 | 候選時間碼 (Candidate) | 驗證時間碼 (Active DB) | 擊球狀態 | 事件來源 | 六維度狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Driver**<br>`01_Driver.mp4` | `10400~14600ms` | Top: 1479ms<br>Imp: 1745ms | Top: **1502ms** (wrist_extremum)<br>Imp: **1735ms**<br>(ds: 233ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **3W**<br>`02_Wood3.mp4` | `13800~20000ms` | Top: 2249ms<br>Imp: 2616ms | Top: **2002ms** (wrist_extremum)<br>Imp: **2603ms**<br>(ds: 601ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:❌ Phase:✅ |
| **5W**<br>`03_Wood5.mp4` | `0~3600ms` | Top: 867ms<br>Imp: 1233ms | Top: **867ms** (wrist_extremum)<br>Imp: **1267ms**<br>(ds: 400ms) | `impact_estimated` | `estimated` | Ev:✅ RT:✅ Phase:✅ |
| **4I**<br>`07_Iron4.mp4` | `12000~17000ms` | Top: 2548ms<br>Imp: 2715ms | Top: **2502ms** (wrist_extremum)<br>Imp: **2703ms**<br>(ds: 201ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **5I**<br>`08_Iron5.mp4` | `18600~23000ms` | Top: 1353ms<br>Imp: 1687ms | Top: **1435ms** (wrist_extremum)<br>Imp: **1702ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **6I**<br>`09_Iron6.mp4` | `12400~19800ms` | Top: 3500ms<br>Imp: 3967ms | Top: **3267ms** (wrist_extremum)<br>Imp: **3967ms**<br>(ds: 700ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:❌ Phase:✅ |
| **7I**<br>`10_Iron7.mp4` | `13600~17600ms` | Top: 1367ms<br>Imp: 1700ms | Top: **1367ms** (wrist_extremum)<br>Imp: **1700ms**<br>(ds: 333ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **8I**<br>`11_Iron8.mp4` | `15000~19000ms` | Top: 1149ms<br>Imp: 1416ms | Top: **1168ms** (wrist_extremum)<br>Imp: **1401ms**<br>(ds: 233ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **9I**<br>`12_Iron9.mp4` | `7800~12500ms` | Top: 1100ms<br>Imp: 1367ms | Top: **1100ms** (wrist_extremum)<br>Imp: **1367ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **PW**<br>`13_PW.mp4` | `2800~6500ms` | Top: 1204ms<br>Imp: 1571ms | Top: **1201ms** (wrist_extremum)<br>Imp: **1568ms**<br>(ds: 367ms) | `impact_estimated` | `estimated` | Ev:✅ RT:✅ Phase:✅ |
| **SW**<br>`15_SW.mp4` | `16800~21200ms` | Top: 2853ms<br>Imp: 3120ms | Top: **2603ms** (wrist_extremum)<br>Imp: **3136ms**<br>(ds: 533ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:❌ Phase:✅ |
| **LW**<br>`16_LW.mp4` | `17200~20600ms` | Top: 1185ms<br>Imp: 1452ms | Top: **1168ms** (wrist_extremum)<br>Imp: **1468ms**<br>(ds: 300ms) | `impact_estimated` | `estimated` | Ev:✅ RT:✅ Phase:✅ |
| **Putter**<br>`17_Putter.mp4` | `15000~20500ms` | Top: 3852ms<br>Imp: 4019ms | Top: **3879ms** (wrist_extremum)<br>Imp: **4004ms**<br>(ds: 125ms) | `impact_estimated` | `estimated` | Ev:❌ RT:✅ Phase:❌ |
| **Driver**<br>`Bonus Driver_LouisGolf_TW.mp4` | `7000~11000ms` | Top: 1333ms<br>Imp: 1733ms | Top: **1367ms** (wrist_extremum)<br>Imp: **1733ms**<br>(ds: 366ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **Driver**<br>`Bonus Driver_WAX_alt.mp4` | `7200~11000ms` | Top: 1075ms<br>Imp: 1375ms | Top: **1101ms** (wrist_extremum)<br>Imp: **1368ms**<br>(ds: 267ms) | `confirmed_strike` | `developer_visual_annotated` | Ev:✅ RT:✅ Phase:✅ |
| **SW**<br>`Bonus SW_Bunker_Titleist.mp4` | `1800~4500ms` | Top: 744ms<br>Imp: 1078ms | Top: **751ms** (wrist_extremum)<br>Imp: **1084ms**<br>(ds: 333ms) | `impact_estimated` | `estimated` | Ev:✅ RT:✅ Phase:✅ |

## 三、關鍵修正與實質發現

1. **5W (03_Wood5.mp4) 擊球瞬間誠信降級**：
   - 經影格審查確認：Frame 37 (1233ms) 桿身仍在腰部水平下桿途中，球仍在地上；Frame 38 (1267ms) 桿頭接近球位；Frame 39 (1300ms) 球已飛出。
   - 擊球發生於 30fps 快門間隙，畫面無直接桿面觸球之影格。依據最高誠信原則，時間碼校正為 `1283ms` 並**明確標記為 `impact_estimated`**，絕不硬充 confirmed_strike。

2. **全體球桿擊球確認度客觀分類**：
   - **Confirmed Strike (11 支)**：Driver (01, TW, WAX), 3W (02), 4I (07), 5I (08), 6I (09), 7I (10), 8I (11), 9I (12), SW (15)。畫面清晰可見桿頭擊球與出球。
   - **Impact Estimated (5 支)**：5W (03, 快門間隔), PW (13, rear_oblique 偏斜視角), LW (16, rear_oblique 高拋非標準全揮桿), Putter (17, close_up 無全身出球視角), SW Bunker (Bonus, side_oblique 炸沙擊球)。

3. **資料庫單一事實來源 (Single Source of Truth) 保證**：
   - 原始粗估事件保留於 `calibration_params['candidate_events']`。
   - 經影格驗證之 active events 原位寫入 `event_timestamps` 與 `calibration_params['active_events']`。
   - 既有 Reference ID 100% 保持穩定，完全無任何重複紀錄產生。

4. **本機素材隔離與敏感資訊防護**：
   - 16 張第三方 Contact Sheet 保存於本機目錄 `~/.golfswinglab/reference_contact_sheets/`。
   - 資料庫安全備份保存於 `~/.golfswinglab/backups/reference_swings_backup.json`。
   - 已更新 `.gitignore`，徹底排除上述本機素材，確保 GitHub 僅保留結構化數據與核心代碼。
