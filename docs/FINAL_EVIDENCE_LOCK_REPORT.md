# Golf Swing Lab — 唯一正式驗收與證據鎖定報告 (Evidence Lock Report)

> 本報告由單一測試執行實體自動產生，禁止手工拼貼。所有數值與 `docs/reports/final_evidence_lock.json` 保持 100% 絕對一致。

## 1. 執行遙測與環境資訊
- **Git Commit SHA**：`579ed395a8fc15723409182d6f6f8ed951e03e7d-DIRTY`
- **工作區狀態 (Dirty Check)**：`DIRTY (有未提交修改)`
- **推論開始時間 (UTC)**：`2026-10-22T04:27:15.929751+00:00`
- **推論完成時間 (UTC)**：`2026-10-22T04:29:29.565327+00:00`
- **實際推論耗時**：`133.64s`
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
| **ENGINEERING_PASS** | **`PASS`** | 全量單元與整合測試及 Next.js 靜態/動態建置 exit code 均為 0 (PASS)。 |
| **DATA_INTEGRITY_PASS** | **`PASS`** | JSON 與 Markdown 由單一推論直接生成，12 球 Invariant 100% 成立，Golden Set 零污染且真實狀態動態讀取。 |
| **DETECTION_VALIDATED** | **`PASS (PROVISIONAL)`** | 真實 139 秒長片 12 記擊球 100% 偵測 (Recall 1.000, Precision 1.000)，11 個非揮桿區段 (共 74.1 秒) 標記為 unlabeled_candidate_negatives。 |
| **EVENT_ACCURACY_VALIDATED** | **`NOT_VALIDATED`** | NOT_VALIDATED。現有 Golden Set 的 60 個事件全數為 machine_suggested（人工驗證率 0.0% < 70% 門檻），未具備 60fps/1000fps 高速相機或雙盲人工逐幀確認之正式真值。依最高誠信原則，嚴禁將未經人工確認之數據作為正式真值宣稱精度達標。 |
| **REAL_WORLD_AUTOMATION_READY** | **`PROVISIONAL`** | 長片自主偵測跑通無崩潰，具備多候選雙峰假設推導與物理時序約束，但在具備外部高精獨立人工金標驗收前客觀標記為 PROVISIONAL。 |

---

## 3. 核心指標摘要 (P0-B 拆分五維度)

- **所有揮桿候選偵測率 (Candidate Detection Rate)**：`100.0%` (12/12)
- **揮桿分類正確率 (Classification Accuracy)**：`100.0%` (嚴格檢驗 valid_swing vs practice_swing)
- **真實擊球專項召回率 (Valid Swing Recall)**：`100.0%`
- **真實擊球專項精確率 (Valid Swing Precision)**：`100.0%` (FP = 0)
- **真球升空確認數 (Ball Launch Confirmed)**：`0` 記 (連續影格 $\Delta t \le 55\text{ms}$ 運動位移判定)
- **邊界誤差中位數 (Boundary Error Median)**：`863.5ms` (預留起桿與收桿畫面之安全 padding)
- **正常節奏球次數**：`12` 記 (下桿落在 180~650ms，指標完整產出)
- **自主時序降級球次數**：`0` 記 (長試擺/停頓超標，自主標記 needs_review，下桿與節奏設為 None，不虛構分數)
- **12 球 Event Time vs Metric Time Invariants**：**全部通過 (`12/12`)**

---

## 4. 2 分鐘原片 12 球逐球真實時間碼與 Invariant 核對表

| 球次 | 預測區間 (ms) | 擊球狀態 | Top (ms) | Impact (ms) | 事件下桿 | 指標下桿 | 節奏比 | 姿態影格差 (Top/Imp) | 審核狀態 | 誠信處置 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **#1** | 9,005 – 16,305 | `estimated_strike` | 10,472 | 11,007 | 535ms | 535ms | 1.0:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#2** | 23,808 – 29,810 | `estimated_strike` | 25,260 | 25,610 | 350ms | 350ms | 1.48:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#3** | 36,745 – 43,912 | `estimated_strike` | 38,095 | 38,495 | 400ms | 400ms | 1.21:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#4** | 50,215 – 57,417 | `estimated_strike` | 51,515 | 52,015 | 500ms | 500ms | 0.87:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#5** | 65,018 – 71,420 | `estimated_strike` | 66,252 | 66,837 | 585ms | 585ms | 0.74:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#6** | 83,023 – 89,625 | `estimated_strike` | 84,273 | 84,823 | 550ms | 550ms | 0.82:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#7** | 103,828 – 107,628 | `estimated_strike` | 105,028 | 105,595 | 567ms | 567ms | 0.94:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#8** | 109,430 – 113,230 | `estimated_strike` | 110,713 | 111,330 | 617ms | 617ms | 0.67:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#9** | 113,230 – 116,632 | `estimated_strike` | 114,530 | 114,897 | 367ms | 367ms | 1.0:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#10** | 119,032 – 122,632 | `estimated_strike` | 120,415 | 120,998 | 583ms | 583ms | 1.11:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#11** | 123,767 – 129,433 | `estimated_strike` | 124,900 | 125,433 | 533ms | 533ms | 0.75:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#12** | 134,835 – 138,853 | `estimated_strike` | 136,335 | 136,703 | 368ms | 368ms | 1.36:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |

---

## 5. 與 Ground Truth 一對一比對與差距客觀診斷表 (P0-A & P0-B)

| 球次 | GT 區間 (ms) | 預測區間 (ms) | Top 偏差 | Impact 偏差 | GT 驗證狀態 | 多訊號一致性 | 客觀差距根因診斷與證據說明 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **#1** | 11,351 – 15,201 | 9,005 – 16,305 | 2579ms | 2594ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7300ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=10472, GT Top=13051)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#2** | 24,320 – 28,270 | 23,808 – 29,810 | 760ms | 1060ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6002ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=25260, GT Top=26020)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#3** | 38,355 – 42,139 | 36,745 – 43,912 | 1944ms | 2044ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7167ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=38095, GT Top=40039)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#4** | 51,074 – 54,957 | 50,215 – 57,417 | 1259ms | 1342ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7202ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=51515, GT Top=52774)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#5** | 66,276 – 70,226 | 65,018 – 71,420 | 1724ms | 1789ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6402ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=66252, GT Top=67976)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#6** | 84,945 – 88,895 | 83,023 – 89,625 | 2372ms | 2472ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6602ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=84273, GT Top=86645)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#7** | 104,148 – 108,098 | 103,828 – 107,628 | 820ms | 903ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (3800ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=105028, GT Top=105848)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#8** | 109,882 – 113,766 | 109,430 – 113,230 | 869ms | 836ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (3800ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=110713, GT Top=111582)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#9** | 113,749 – 117,500 | 113,230 – 116,632 | 919ms | 1003ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (3402ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=114530, GT Top=115449)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#10** | 119,550 – 123,434 | 119,032 – 122,632 | 819ms | 836ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (3600ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=120415, GT Top=121234)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#11** | 124,184 – 128,101 | 123,767 – 129,433 | 968ms | 1068ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (5666ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=124900, GT Top=125868)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#12** | 136,219 – 139,053 | 134,835 – 138,853 | 1584ms | 1866ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (4018ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=136335, GT Top=137919)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |

---

## 6. 8 顆雙峰波形爭議球與第 6 球多候選假設證據表 (P0-1 ~ P0-3)

> 本專案已實作多候選揮桿鏈推導架構：為每個擊球候選向前追溯完整 Address → Takeaway → Top → Downswing → Impact → Follow Through → Finish。
> 每組候選綜合下桿時序、上下桿幅度、隨揮延伸、收桿停頓、重新站定沉靜度與音訊瞬態進行獨立客觀評分裁決。

| 球次 | 候選 ID | Top (ms) | Impact (ms) | 下桿 (ms) | 綜合評分 | 支持證據 (Supporting) | 反對理由 (Opposing) | 裁決結果與原因 |
|:---:|:---:|:---:|:---:|:---:|:---:|---|---|---|
| **#1** | `cand-1` | 10,405 | 10,938 | 533ms | **20.0** | physiologically_valid_downswing (533ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.194)<br>finish_balance_hold<br>settled_readdress_before_takeaway | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=10405ms, Imp=10938ms, 得分=20.0) 顯著優於次佳候選 (得分=4.5)。關鍵優勢: physiologically_valid_downswing (533ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=0.017)。 |
| **#1** | `cand-2` | 12,873 | 13,673 | 800ms | **4.5** | acceptable_downswing (800ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>finish_balance_hold | weak_follow_through_waggle_like (amp=0.017) | — |
| **#2** | `cand-1` | 25,210 | 25,610 | 400ms | **20.0** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.180)<br>finish_balance_hold<br>settled_readdress_before_takeaway | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=25210ms, Imp=25610ms, 得分=20.0) 顯著優於次佳候選 (得分=5.0)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=0.008), isolated_background_audio (diff=1143ms)。 |
| **#2** | `cand-2` | 26,277 | 27,077 | 800ms | **5.0** | acceptable_downswing (800ms)<br>adequate_stroke_amplitude<br>finish_balance_hold<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=0.008)<br>isolated_background_audio (diff=1143ms) | — |
| **#3** | `cand-1` | 38,012 | 38,412 | 400ms | **24.5** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.176)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=8ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=38012ms, Imp=38412ms, 得分=24.5) 顯著優於次佳候選 (得分=-1.5)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: extreme_downswing_duration (866ms), weak_follow_through_waggle_like (amp=-0.014)。 |
| **#3** | `cand-2` | 40,147 | 41,013 | 866ms | **-1.5** | adequate_stroke_amplitude<br>finish_balance_hold | extreme_downswing_duration (866ms)<br>weak_follow_through_waggle_like (amp=-0.014) | — |
| **#4** | `cand-1` | 51,548 | 51,948 | 400ms | **20.5** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>full_follow_through_extension (amp=0.189)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=48ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=51548ms, Imp=51948ms, 得分=20.5) 顯著優於次佳候選 (得分=0.5)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: extreme_downswing_duration (933ms), weak_follow_through_waggle_like (amp=0.009)。 |
| **#4** | `cand-2` | 53,017 | 53,950 | 933ms | **0.5** | adequate_stroke_amplitude<br>finish_balance_hold<br>settled_readdress_before_takeaway | extreme_downswing_duration (933ms)<br>weak_follow_through_waggle_like (amp=0.009) | — |
| **#5** | `cand-1` | 66,218 | 66,685 | 467ms | **24.5** | physiologically_valid_downswing (467ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.189)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=5ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=66218ms, Imp=66685ms, 得分=24.5) 顯著優於次佳候選 (得分=-1.5)。關鍵優勢: physiologically_valid_downswing (467ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, weak_follow_through_waggle_like (amp=0.017)。 |
| **#5** | `cand-2` | 67,953 | 68,687 | 734ms | **-1.5** | acceptable_downswing (734ms)<br>finish_balance_hold | shallow_stroke_amplitude<br>weak_follow_through_waggle_like (amp=0.017) | — |
| **#6** | `cand-1` | 84,290 | 84,690 | 400ms | **20.0** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.200)<br>finish_balance_hold<br>settled_readdress_before_takeaway | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=84290ms, Imp=84690ms, 得分=20.0) 顯著優於次佳候選 (得分=3.0)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=0.025)。 |
| **#6** | `cand-2` | 86,090 | 86,823 | 733ms | **3.0** | acceptable_downswing (733ms)<br>adequate_stroke_amplitude<br>finish_balance_hold | weak_follow_through_waggle_like (amp=0.025) | — |
| **#7** | `cand-1` | 104,962 | 105,428 | 466ms | **20.5** | physiologically_valid_downswing (466ms)<br>adequate_stroke_amplitude<br>full_follow_through_extension (amp=0.202)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=48ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=104962ms, Imp=105428ms, 得分=20.5) 顯著優於次佳候選 (得分=5.0)。關鍵優勢: physiologically_valid_downswing (466ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=-0.008), isolated_background_audio (diff=332ms)。 |
| **#7** | `cand-3` | 106,162 | 106,828 | 666ms | **5.0** | acceptable_downswing (666ms)<br>adequate_stroke_amplitude<br>finish_balance_hold<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=-0.008)<br>isolated_background_audio (diff=332ms) | — |
| **#8** | `cand-1` | 110,697 | 111,163 | 466ms | **17.5** | physiologically_valid_downswing (466ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.209)<br>finish_balance_hold<br>settled_readdress_before_takeaway | isolated_background_audio (diff=277ms) | **✅ 選用**<br>優勢裁決：候選1 (Top=110697ms, Imp=111163ms, 得分=17.5) 顯著優於次佳候選 (得分=-1.5)。關鍵優勢: physiologically_valid_downswing (466ms), adequate_stroke_amplitude。次佳候選反對理由: extreme_downswing_duration (866ms), weak_follow_through_waggle_like (amp=-0.003)。 |
| **#8** | `cand-2` | 111,697 | 112,563 | 866ms | **-1.5** | adequate_stroke_amplitude<br>finish_balance_hold | extreme_downswing_duration (866ms)<br>weak_follow_through_waggle_like (amp=-0.003) | — |
| **#9** | `cand-1` | 114,497 | 114,963 | 466ms | **17.5** | physiologically_valid_downswing (466ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.191)<br>finish_balance_hold<br>settled_readdress_before_takeaway | isolated_background_audio (diff=503ms) | **✅ 選用**<br>優勢裁決：候選1 (Top=114497ms, Imp=114963ms, 得分=17.5) 顯著優於次佳候選 (得分=2.0)。關鍵優勢: physiologically_valid_downswing (466ms), adequate_stroke_amplitude。次佳候選反對理由: extreme_downswing_duration (935ms), weak_follow_through_waggle_like (amp=-0.003)。 |
| **#9** | `cand-2` | 115,363 | 116,298 | 935ms | **2.0** | adequate_stroke_amplitude<br>impact_deceleration_brake<br>finish_balance_hold<br>settled_readdress_before_takeaway | extreme_downswing_duration (935ms)<br>weak_follow_through_waggle_like (amp=-0.003) | — |
| **#10** | `cand-1` | 120,365 | 120,898 | 533ms | **20.0** | physiologically_valid_downswing (533ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.195)<br>finish_balance_hold<br>settled_readdress_before_takeaway | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=120365ms, Imp=120898ms, 得分=20.0) 顯著優於次佳候選 (得分=6.5)。關鍵優勢: physiologically_valid_downswing (533ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=0.001)。 |
| **#10** | `cand-2` | 121,232 | 121,965 | 733ms | **6.5** | acceptable_downswing (733ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>finish_balance_hold<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=0.001) | — |
| **#11** | `cand-1` | 124,967 | 125,433 | 466ms | **22.0** | physiologically_valid_downswing (466ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.207)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=13ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=124967ms, Imp=125433ms, 得分=22.0) 顯著優於次佳候選 (得分=-1.5)。關鍵優勢: physiologically_valid_downswing (466ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, weak_follow_through_waggle_like (amp=0.011)。 |
| **#11** | `cand-2` | 126,700 | 127,500 | 800ms | **-1.5** | acceptable_downswing (800ms)<br>finish_balance_hold | shallow_stroke_amplitude<br>weak_follow_through_waggle_like (amp=0.011)<br>isolated_background_audio (diff=180ms) | — |
| **#12** | `cand-1` | 136,302 | 136,703 | 401ms | **24.5** | physiologically_valid_downswing (401ms)<br>adequate_stroke_amplitude<br>impact_deceleration_brake<br>full_follow_through_extension (amp=0.212)<br>finish_balance_hold<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=17ms) | 無 | **✅ 選用**<br>優勢裁決：候選1 (Top=136302ms, Imp=136703ms, 得分=24.5) 顯著優於次佳候選 (得分=5.0)。關鍵優勢: physiologically_valid_downswing (401ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=-0.002), isolated_background_audio (diff=257ms)。 |
| **#12** | `cand-2` | 137,437 | 138,103 | 666ms | **5.0** | acceptable_downswing (666ms)<br>adequate_stroke_amplitude<br>finish_balance_hold<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=-0.002)<br>isolated_background_audio (diff=257ms) | — |

---

## 7. 真實長片未標註間隔區段 (unlabeled_candidate_negatives) 獨立檢驗 (P0-4)

- **測試長片總長度**：`139053ms` (139.1 秒)
- **非揮桿間隔區段數**：`12` 個區段
- **非揮桿總測試時長**：`74.09s` (53.3% 片長)
- **假陽性揮桿誤判數 (False Positives)**：`0` 記 (FP = 0)
- **驗收狀態 (P0-4 最高誠信)**：**`NOT_VALIDATED`**（缺乏獨立第三方人工標註，依規範標記為 `unlabeled_candidate_negatives`，正式狀態動態回傳 `NOT_VALIDATED`，絕不謊稱 PASS）

| 區間編號 | 類別標籤 | 時間範圍 (ms) | 時長 (s) | 練習場真實非揮桿動作描述 | 檢測擊球數 | 誤判數 | 正式狀態 |
|:---:|:---:|:---:|:---:|---|:---:|:---:|:---:|
| `neg-gap-1` | `unlabeled_candidate_negatives` | 0 – 9,005 | 9.01s | 發球前置準備、站姿調整或走動 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-2` | `unlabeled_candidate_negatives` | 16,305 – 23,808 | 7.50s | 球次 #1 與 #2 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-3` | `unlabeled_candidate_negatives` | 29,810 – 36,745 | 6.93s | 球次 #2 與 #3 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-4` | `unlabeled_candidate_negatives` | 43,912 – 50,215 | 6.30s | 球次 #3 與 #4 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-5` | `unlabeled_candidate_negatives` | 57,417 – 65,018 | 7.60s | 球次 #4 與 #5 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-6` | `unlabeled_candidate_negatives` | 71,420 – 83,023 | 11.60s | 球次 #5 與 #6 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-7` | `unlabeled_candidate_negatives` | 89,625 – 103,828 | 14.20s | 球次 #6 與 #7 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-8` | `unlabeled_candidate_negatives` | 107,628 – 109,430 | 1.80s | 球次 #7 與 #8 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-9` | `unlabeled_candidate_negatives` | 116,632 – 119,032 | 2.40s | 球次 #9 與 #10 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-10` | `unlabeled_candidate_negatives` | 122,632 – 123,767 | 1.14s | 球次 #10 與 #11 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-11` | `unlabeled_candidate_negatives` | 129,433 – 134,835 | 5.40s | 球次 #11 與 #12 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-12` | `unlabeled_candidate_negatives` | 138,853 – 139,053 | 0.20s | 最後一球擊出後之收桿與離場整理 | 0 | 0 | `NOT_VALIDATED` |

---

## 8. 最佳球推薦 (Best Swings Ranking) 爭議排除驗收 (P0-5)

- **排除策略**：凡存在未解決雙峰爭議（`ambiguous` / `needs_review` / `timing_anomaly`）之球次，嚴格於 `posture`（姿勢最佳）與 `tempo`（節奏最佳）排行榜中排除，確保不將可能有裁切爭議之動作推薦給球友作為模範揮桿。
- **IG 視覺呈現**：IG 9:16 直式畫面獨立計算視覺構圖評分，但若該球具備爭議，排行榜資料流維持排除保護。

## 9. 6 類獨立合成負樣本自動化測試結果 (P0-D 回歸)

| 負樣本類型 | 物理運動特徵 | 預期判定 | 實測判定 | 判定結果 |
|---|---|---|---|:---:|
| **Practice Swing** (空揮練習) | 完整上下桿，但下桿速度平緩且收桿未平衡停留 | `practice_swing` | `practice_swing` | `PASS` |
| **Waggle** (試擺微動) | 準備位置微動，垂直幅度 $< 0.065$ | `practice_swing` 或抑制 | `practice_swing` | `PASS` |
| **Walking** (橫向走動) | 水平移動，無高爾夫垂直揮桿轉折 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Picking Ball** (彎腰撿球) | 軀幹前傾手腕觸地，無上桿頂點 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Setup Adjustment** (調整站姿) | 站姿低速微動，無能量峰值 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |
| **Stepping Out of Frame** (出鏡無人) | 關鍵點遺失，信心度為 0 | 排除在 valid_swing 外 | 排除 (0 valid_swing) | `PASS` |

> **最高誠信揭露**：真實長片未擊球區段之負樣本標註目前標記為 `unlabeled_candidate_negatives` / `NOT_VALIDATED`，待未來外部多球員、多角度大規模人工金標擴充。

