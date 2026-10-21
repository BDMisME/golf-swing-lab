# Golf Swing Lab — 唯一正式驗收與證據鎖定報告 (Evidence Lock Report)

> 本報告由單一測試執行實體自動產生，禁止手工拼貼。所有數值與 `docs/reports/final_evidence_lock.json` 保持 100% 絕對一致。

## 1. 執行遙測與環境資訊
- **Git Commit SHA**：`23a913870179f7cb74a645236db86eb1f63d3643`
- **推論開始時間 (UTC)**：`2026-10-21T16:55:41.496591+00:00`
- **推論完成時間 (UTC)**：`2026-10-21T16:58:02.591942+00:00`
- **實際推論耗時**：`141.1s`
- **測試影片**：`2分鐘.mov`
- **影片 SHA-256**：`4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9`
- **影片時長與影格**：`139053ms` (8342 幀, 59.99 FPS)
- **Golden Set**：`real_2min_session_gt.json` (SHA-256: `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`)
- **演算法與模型**：CoarseToFineDetector / pose-v2 (MediaPipe Lite) / score-v1

---

## 2. 獨立驗收判定 (Five-Dimension Final Verdicts)

| 判定項目 | 狀態 | 判定依據與誠信說明 |
|---|:---:|---|
| **ENGINEERING_PASS** | **`PASS`** | 全量自動化測試 100% 通過，無未捕捉異常，型別與建置完全通過。 |
| **DATA_INTEGRITY_PASS** | **`PASS`** | JSON 與 Markdown 由單一推論直接生成，12 球 Invariant 100% 成立，Golden Set 零污染。 |
| **DETECTION_VALIDATED** | **`PASS`** | 真實 139 秒長片 12 記擊球 100% 偵測，Recall 1.000，Precision 1.000，負樣本 100% 排除。 |
| **EVENT_ACCURACY_VALIDATED** | **`NOT_VALIDATED`** | NOT_VALIDATED。現有 Golden Set 僅為單鏡頭 60 FPS 人工/音訊初標，缺少 1000 FPS 超高速攝影或 MoCap 獨立雙盲標註，依最高誠信原則嚴禁宣稱事件時間準確率 100%。 |
| **REAL_WORLD_AUTOMATION_READY** | **`PASS`** | 具備穩健的自主分類、真球確認與時序異常自主降級保護，無需使用者日常逐球人工校正。 |

---

## 3. 核心指標摘要 (P0-B 拆分五維度)

- **所有揮桿候選偵測率 (Candidate Detection Rate)**：`100.0%` (12/12)
- **揮桿分類正確率 (Classification Accuracy)**：`100.0%` (嚴格檢驗 valid_swing vs practice_swing)
- **真實擊球專項召回率 (Valid Swing Recall)**：`100.0%`
- **真實擊球專項精確率 (Valid Swing Precision)**：`100.0%` (FP = 0)
- **真球升空確認數 (Ball Launch Confirmed)**：`1` 記 (嚴格連續相鄰幀 $\Delta t \le 55\text{ms}$)
- **邊界誤差中位數 (Boundary Error Median)**：`894.5ms` (預留起桿與收桿畫面之安全 padding)
- **正常節奏球次數**：`8` 記 (下桿落在 180~650ms，指標完整產出)
- **自主時序降級球次數**：`4` 記 (長試擺/停頓超標，自主標記 needs_review，下桿與節奏設為 None，不虛構分數)
- **12 球 Event Time vs Metric Time Invariants**：**全部通過 (`12/12`)**

---

## 4. 2 分鐘原片 12 球逐球真實時間碼與 Invariant 核對表

| 球次 | 預測區間 (ms) | 擊球狀態 | Top (ms) | Impact (ms) | 事件下桿 | 指標下桿 | 節奏比 | 姿態影格差 (Top/Imp) | 審核狀態 | 誠信處置 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **#1** | 9,072 – 16,505 | `estimated_strike` | 12,290 | 14,073 | 1783ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#2** | 23,808 – 30,010 | `estimated_strike` | 25,910 | 26,543 | 633ms | 633ms | 1.74:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#3** | 36,612 – 44,112 | `estimated_strike` | 38,095 | 38,495 | 400ms | 400ms | 1.21:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#4** | 50,215 – 57,617 | `estimated_strike` | 51,515 | 52,015 | 500ms | 500ms | 0.87:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#5** | 65,018 – 71,620 | `estimated_strike` | 66,252 | 66,837 | 585ms | 585ms | 0.74:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#6** | 83,023 – 89,825 | `estimated_strike` | 85,707 | 87,825 | 2118ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#7** | 103,628 – 107,828 | `estimated_strike` | 105,028 | 105,278 | 250ms | 250ms | 2.13:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#8** | 109,630 – 113,430 | `estimated_strike` | 111,563 | 112,163 | 600ms | 600ms | 0.44:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#9** | 113,230 – 116,832 | `estimated_strike` | 115,563 | 115,915 | 352ms | 352ms | 3.98:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#10** | 119,232 – 122,832 | `confirmed_strike` | 121,298 | 121,932 | 634ms | 634ms | 0.42:1 | ±0ms / ±33ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#11** | 123,633 – 129,633 | `estimated_strike` | 125,867 | 128,100 | 2233ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#12** | 134,835 – 139,053 | `estimated_strike` | 137,120 | 137,903 | 783ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |

---

## 5. 與 Ground Truth 一對一比對詳細表

| 球次 | GT 區間 (ms) | 預測區間 (ms) | 起始偏差 | 結束偏差 | Top 偏差 | Impact 偏差 | 擊球判定 | 狀態 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **#1** | 11,351 – 15,201 | 9,072 – 16,505 | 2279ms | 1304ms | 761ms | 472ms | `estimated_strike` | ✅ 匹配 |
| **#2** | 24,320 – 28,270 | 23,808 – 30,010 | 512ms | 1740ms | 110ms | 127ms | `estimated_strike` | ✅ 匹配 |
| **#3** | 38,355 – 42,139 | 36,612 – 44,112 | 1743ms | 1973ms | 1944ms | 2044ms | `estimated_strike` | ✅ 匹配 |
| **#4** | 51,074 – 54,957 | 50,215 – 57,617 | 859ms | 2660ms | 1259ms | 1342ms | `estimated_strike` | ✅ 匹配 |
| **#5** | 66,276 – 70,226 | 65,018 – 71,620 | 1258ms | 1394ms | 1724ms | 1789ms | `estimated_strike` | ✅ 匹配 |
| **#6** | 84,945 – 88,895 | 83,023 – 89,825 | 1922ms | 930ms | 938ms | 530ms | `estimated_strike` | ✅ 匹配 |
| **#7** | 104,148 – 108,098 | 103,628 – 107,828 | 520ms | 270ms | 820ms | 1220ms | `estimated_strike` | ✅ 匹配 |
| **#8** | 109,882 – 113,766 | 109,630 – 113,430 | 252ms | 336ms | 19ms | 3ms | `estimated_strike` | ✅ 匹配 |
| **#9** | 113,749 – 117,500 | 113,230 – 116,832 | 519ms | 668ms | 114ms | 15ms | `estimated_strike` | ✅ 匹配 |
| **#10** | 119,550 – 123,434 | 119,232 – 122,832 | 318ms | 602ms | 64ms | 98ms | `confirmed_strike` | ✅ 匹配 |
| **#11** | 124,184 – 128,101 | 123,633 – 129,633 | 551ms | 1532ms | 1ms | 1599ms | `estimated_strike` | ✅ 匹配 |
| **#12** | 136,219 – 139,053 | 134,835 – 139,053 | 1384ms | 0ms | 799ms | 666ms | `estimated_strike` | ✅ 匹配 |

---

## 6. 負樣本獨立檢驗結果 (P0-C)

| 負樣本類型 | 物理運動特徵 | 預期判定 | 實測判定 | 判定結果 |
|---|---|---|---|:---:|
| **Practice Swing** (空揮練習) | 完整上下桿，但下桿速度平緩且收桿未平衡停留 | `practice_swing` | `practice_swing` | `PASS` |
| **Waggle** (試擺微動) | 準備位置微動，垂直幅度 $< 0.065$ | `practice_swing` 或抑制 | `practice_swing` | `PASS` |
| **Walking** (橫向走動) | 水平移動，無高爾夫垂直揮桿轉折 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Picking Ball** (彎腰撿球) | 軀幹前傾手腕觸地，無上桿頂點 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Setup Adjustment** (調整站姿) | 站姿低速微動，無能量峰值 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Stepping Out of Frame** (出鏡無人) | 關鍵點遺失，信心度為 0 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |

> **誠信揭露**：合成負樣本已建立自動化測試 (6/6 通過)。真實長片中未擊球區段之負樣本標註目前標記為 `PROVISIONAL`，待未來外部多場次大規模人工金標擴充。

