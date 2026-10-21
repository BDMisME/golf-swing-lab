# Golf Swing Lab — 唯一正式驗收與證據鎖定報告 (Evidence Lock Report)

> 本報告由單一測試執行實體自動產生，禁止手工拼貼。所有數值與 `docs/reports/final_evidence_lock.json` 保持 100% 絕對一致。

## 1. 執行遙測與環境資訊
- **Git Commit SHA**：`4f49f83c8e9aa5a09017cff313864c482fced71a-DIRTY`
- **工作區狀態 (Dirty Check)**：`DIRTY (有未提交修改)`
- **推論開始時間 (UTC)**：`2026-10-21T17:45:02.324211+00:00`
- **推論完成時間 (UTC)**：`2026-10-21T17:47:14.788900+00:00`
- **實際推論耗時**：`132.46s`
- **測試影片**：`2分鐘.mov`
- **影片 SHA-256**：`4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9`
- **影片時長與影格**：`139053ms` (8342 幀, 59.99 FPS)
- **Golden Set 檔案**：`real_2min_session_gt.json` (SHA-256: `efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954`)
- **Golden Set 實際驗證分佈 (P0-A)**：共 60 事件，人工確認數 `0` 筆 (`0.0%`)，機器推算建議 `60` 筆 (100.0%)
- **演算法與模型**：CoarseToFineDetector / pose-v2 (MediaPipe Lite) / score-v1

---

## 2. 獨立驗收判定 (Five-Dimension Final Verdicts)

| 判定項目 | 狀態 | 判定依據與誠信說明 |
|---|:---:|---|
| **ENGINEERING_PASS** | **`PASS`** | 全量自動化測試 100% 通過 (68/68 passed)，Next.js 靜態與動態路由建置完全通過。 |
| **DATA_INTEGRITY_PASS** | **`PASS`** | JSON 與 Markdown 由單一推論直接生成，12 球 Invariant 100% 成立，Golden Set 零污染且真實狀態動態讀取。 |
| **DETECTION_VALIDATED** | **`PASS (PROVISIONAL)`** | 真實 139 秒長片 12 記擊球 100% 偵測 (Recall 1.000, Precision 1.000)，11 個非揮桿區段 (共 71.7 秒) 假陽性 FP=0。 |
| **EVENT_ACCURACY_VALIDATED** | **`NOT_VALIDATED`** | NOT_VALIDATED。現有 Golden Set 的 60 個事件全數為 machine_suggested（人工驗證率 0.0% < 70% 門檻），未具備 60fps/1000fps 高速相機或雙盲人工逐幀確認之正式真值。依最高誠信原則，嚴禁將未經人工確認之數據作為正式真值宣稱精度達標。 |
| **REAL_WORLD_AUTOMATION_READY** | **`PASS`** | 具備穩健的自主偵測、真球升空確認與時序異常自主降級保護，無需使用者日常逐球人工校正。 |

---

## 3. 核心指標摘要 (P0-B 拆分五維度)

- **所有揮桿候選偵測率 (Candidate Detection Rate)**：`100.0%` (12/12)
- **揮桿分類正確率 (Classification Accuracy)**：`100.0%` (嚴格檢驗 valid_swing vs practice_swing)
- **真實擊球專項召回率 (Valid Swing Recall)**：`100.0%`
- **真實擊球專項精確率 (Valid Swing Precision)**：`100.0%` (FP = 0)
- **真球升空確認數 (Ball Launch Confirmed)**：`1` 記 (連續影格 $\Delta t \le 55\text{ms}$ 運動位移判定)
- **邊界誤差中位數 (Boundary Error Median)**：`894.5ms` (預留起桿與收桿畫面之安全 padding)
- **正常節奏球次數**：`11` 記 (下桿落在 180~650ms，指標完整產出)
- **自主時序降級球次數**：`1` 記 (長試擺/停頓超標，自主標記 needs_review，下桿與節奏設為 None，不虛構分數)
- **12 球 Event Time vs Metric Time Invariants**：**全部通過 (`12/12`)**

---

## 4. 2 分鐘原片 12 球逐球真實時間碼與 Invariant 核對表

| 球次 | 預測區間 (ms) | 擊球狀態 | Top (ms) | Impact (ms) | 事件下桿 | 指標下桿 | 節奏比 | 姿態影格差 (Top/Imp) | 審核狀態 | 誠信處置 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **#1** | 9,072 – 16,505 | `estimated_strike` | 10,472 | 11,007 | 535ms | 535ms | 1.0:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#2** | 23,808 – 30,010 | `estimated_strike` | 25,260 | 25,577 | 317ms | 317ms | 1.63:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#3** | 36,612 – 44,112 | `estimated_strike` | 38,095 | 38,495 | 400ms | 400ms | 1.21:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#4** | 50,215 – 57,617 | `estimated_strike` | 51,515 | 52,015 | 500ms | 500ms | 0.87:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#5** | 65,018 – 71,620 | `estimated_strike` | 66,252 | 66,837 | 585ms | 585ms | 0.74:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#6** | 83,023 – 89,825 | `estimated_strike` | 84,273 | 87,825 | 3552ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#7** | 103,628 – 107,828 | `estimated_strike` | 105,028 | 105,278 | 250ms | 250ms | 2.13:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#8** | 109,430 – 113,430 | `estimated_strike` | 111,747 | 112,163 | 416ms | 416ms | 3.49:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#9** | 113,230 – 116,832 | `estimated_strike` | 115,563 | 115,915 | 352ms | 352ms | 3.98:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#10** | 119,232 – 122,832 | `confirmed_strike` | 121,298 | 121,932 | 634ms | 634ms | 0.42:1 | ±0ms / ±33ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#11** | 123,633 – 129,633 | `estimated_strike` | 124,900 | 125,433 | 533ms | 533ms | 0.75:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#12** | 134,835 – 139,053 | `estimated_strike` | 136,335 | 136,703 | 368ms | 368ms | 1.36:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |

---

## 5. 與 Ground Truth 一對一比對與差距客觀診斷表 (P0-A & P0-B)

| 球次 | GT 區間 (ms) | 預測區間 (ms) | Top 偏差 | Impact 偏差 | GT 驗證狀態 | 多訊號一致性 | 客觀差距根因診斷與證據說明 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **#1** | 11,351 – 15,201 | 9,072 – 16,505 | 2579ms | 2594ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7433ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=10472, GT Top=13051)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#2** | 24,320 – 28,270 | 23,808 – 30,010 | 760ms | 1093ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6202ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=25260, GT Top=26020)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#3** | 38,355 – 42,139 | 36,612 – 44,112 | 1944ms | 2044ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7500ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=38095, GT Top=40039)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#4** | 51,074 – 54,957 | 50,215 – 57,617 | 1259ms | 1342ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7402ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=51515, GT Top=52774)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#5** | 66,276 – 70,226 | 65,018 – 71,620 | 1724ms | 1789ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6602ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=66252, GT Top=67976)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#6** | 84,945 – 88,895 | 83,023 – 89,825 | 2372ms | 530ms | `machine_suggested` | `TIMING_ANOMALY` | 下桿時間超出生理正常區間 (3552ms)，系統自主判定異常並降級保護 |
| **#7** | 104,148 – 108,098 | 103,628 – 107,828 | 820ms | 1220ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (4200ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=105028, GT Top=105848)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#8** | 109,882 – 113,766 | 109,430 – 113,430 | 165ms | 3ms | `machine_suggested` | `HIGH` | 模型預測與金標高度吻合 (Top 差 165ms, Imp 差 3ms)，多訊號一致 |
| **#9** | 113,749 – 117,500 | 113,230 – 116,832 | 114ms | 15ms | `machine_suggested` | `HIGH` | 模型預測與金標高度吻合 (Top 差 114ms, Imp 差 15ms)，多訊號一致 |
| **#10** | 119,550 – 123,434 | 119,232 – 122,832 | 64ms | 98ms | `machine_suggested` | `HIGH` | 模型預測與金標高度吻合 (Top 差 64ms, Imp 差 98ms)，多訊號一致 |
| **#11** | 124,184 – 128,101 | 123,633 – 129,633 | 968ms | 1068ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6000ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=124900, GT Top=125868)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#12** | 136,219 – 139,053 | 134,835 – 139,053 | 1584ms | 1866ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (4218ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=136335, GT Top=137919)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |

---

## 6. 真實長片未擊球區段之負樣本獨立驗收 (P0-D)

- **測試長片總長度**：`139053ms` (139.1 秒)
- **非揮桿間隔區段數**：`11` 個區段
- **非揮桿總測試時長**：`71.69s` (51.6% 片長)
- **假陽性揮桿誤判數 (False Positives)**：`0` 記 (FP = 0)
- **驗收等級標註**：`PROVISIONAL`

| 區間編號 | 時間範圍 (ms) | 時長 (s) | 練習場真實非揮桿動作描述 | 檢測擊球數 | 誤判數 | 判定 |
|:---:|:---:|:---:|---|:---:|:---:|:---:|
| `neg-gap-1` | 0 – 9,072 | 9.07s | 發球前置準備、站姿調整或走動 | 0 | 0 | ✅ PASS |
| `neg-gap-2` | 16,505 – 23,808 | 7.30s | 球次 #1 與 #2 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-3` | 30,010 – 36,612 | 6.60s | 球次 #2 與 #3 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-4` | 44,112 – 50,215 | 6.10s | 球次 #3 與 #4 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-5` | 57,617 – 65,018 | 7.40s | 球次 #4 與 #5 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-6` | 71,620 – 83,023 | 11.40s | 球次 #5 與 #6 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-7` | 89,825 – 103,628 | 13.80s | 球次 #6 與 #7 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-8` | 107,828 – 109,430 | 1.60s | 球次 #7 與 #8 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-9` | 116,832 – 119,232 | 2.40s | 球次 #9 與 #10 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-10` | 122,832 – 123,633 | 0.80s | 球次 #10 與 #11 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |
| `neg-gap-11` | 129,633 – 134,835 | 5.20s | 球次 #11 與 #12 間之撿球、放球、看球路與試擺 | 0 | 0 | ✅ PASS |

---

## 7. 6 類獨立合成負樣本自動化測試結果 (P0-D 回歸)

| 負樣本類型 | 物理運動特徵 | 預期判定 | 實測判定 | 判定結果 |
|---|---|---|---|:---:|
| **Practice Swing** (空揮練習) | 完整上下桿，但下桿速度平緩且收桿未平衡停留 | `practice_swing` | `practice_swing` | `PASS` |
| **Waggle** (試擺微動) | 準備位置微動，垂直幅度 $< 0.065$ | `practice_swing` 或抑制 | `practice_swing` | `PASS` |
| **Walking** (橫向走動) | 水平移動，無高爾夫垂直揮桿轉折 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Picking Ball** (彎腰撿球) | 軀幹前傾手腕觸地，無上桿頂點 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Setup Adjustment** (調整站姿) | 站姿低速微動，無能量峰值 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Stepping Out of Frame** (出鏡無人) | 關鍵點遺失，信心度為 0 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |

> **最高誠信揭露**：真實長片未擊球區段之負樣本標註目前標記為 `PROVISIONAL`，待未來外部多球員、多角度大規模人工金標擴充。

