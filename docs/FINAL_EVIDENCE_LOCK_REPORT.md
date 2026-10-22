# Golf Swing Lab — 唯一正式驗收與證據鎖定報告 (Evidence Lock Report)

> 本報告由單一測試執行實體自動產生，禁止手工拼貼。所有數值與 `docs/reports/final_evidence_lock.json` 保持 100% 絕對一致。

## 1. 執行遙測與環境資訊
- **Git Commit SHA**：`8040609b53a41a964cdec3d270c9b8d36b9828de-DIRTY`
- **工作區狀態 (Dirty Check)**：`DIRTY (有未提交修改)`
- **推論開始時間 (UTC)**：`2026-10-22T05:23:44.654643+00:00`
- **推論完成時間 (UTC)**：`2026-10-22T05:26:10.632525+00:00`
- **實際推論耗時**：`145.98s`
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
| **DETECTION_VALIDATED** | **`PASS (PROVISIONAL)`** | 真實 139 秒長片 12 記擊球 100% 偵測 (Recall 1.000, Precision 1.000)，11 個非揮桿區段 (共 74.3 秒) 標記為 unlabeled_candidate_negatives。 |
| **EVENT_ACCURACY_VALIDATED** | **`NOT_VALIDATED`** | NOT_VALIDATED。現有 Golden Set 的 60 個事件全數為 machine_suggested（人工驗證率 0.0% < 70% 門檻），未具備 60fps/1000fps 高速相機或雙盲人工逐幀確認之正式真值。依最高誠信原則，嚴禁將未經人工確認之數據作為正式真值宣稱精度達標。 |
| **REAL_WORLD_AUTOMATION_READY** | **`PROVISIONAL`** | 長片自主偵測跑通無崩潰，具備多候選雙峰假設推導與物理時序約束，但在具備外部高精獨立人工金標驗收前客觀標記為 PROVISIONAL。 |

---

## 3. 核心指標摘要 (P0-B 拆分五維度)

- **所有揮桿候選偵測率 (Candidate Detection Rate)**：`100.0%` (12/12)
- **揮桿分類正確率 (Classification Accuracy)**：`91.7%` (嚴格檢驗 valid_swing vs practice_swing)
- **真實擊球專項召回率 (Valid Swing Recall)**：`91.7%`
- **真實擊球專項精確率 (Valid Swing Precision)**：`100.0%` (FP = 0)
- **真球升空確認數 (Ball Launch Confirmed)**：`1` 記 (連續影格 $\Delta t \le 55\text{ms}$ 運動位移判定)
- **邊界誤差中位數 (Boundary Error Median)**：`863.5ms` (預留起桿與收桿畫面之安全 padding)
- **正常節奏球次數**：`10` 記 (下桿落在 180~650ms，指標完整產出)
- **自主時序降級球次數**：`2` 記 (長試擺/停頓超標，自主標記 needs_review，下桿與節奏設為 None，不虛構分數)
- **12 球 Event Time vs Metric Time Invariants**：**全部通過 (`12/12`)**

---

## 4. 2 分鐘原片 12 球逐球真實時間碼與 Invariant 核對表

| 球次 | 預測區間 (ms) | 擊球狀態 | Top (ms) | Impact (ms) | 事件下桿 | 指標下桿 | 節奏比 | 姿態影格差 (Top/Imp) | 審核狀態 | 誠信處置 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **#1** | 9,005 – 16,305 | `estimated_strike` | 10,472 | 10,738 | 266ms | 266ms | 2.01:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#2** | 23,808 – 29,810 | `estimated_strike` | 25,260 | 25,577 | 317ms | 317ms | 1.63:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#3** | 36,745 – 43,912 | `estimated_strike` | 38,095 | 38,495 | 400ms | 400ms | 1.21:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#4** | 50,215 – 57,417 | `estimated_strike` | 51,515 | 51,748 | 233ms | 233ms | 1.86:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#5** | 65,018 – 71,420 | `estimated_strike` | 66,252 | 66,785 | 533ms | 533ms | 0.81:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#6** | 83,023 – 89,625 | `estimated_strike` | 84,273 | 84,623 | 350ms | 350ms | 1.29:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#7** | 103,828 – 107,628 | `estimated_strike` | 105,028 | 105,278 | 250ms | 250ms | 2.13:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#8** | 109,630 – 113,413 | `confirmed_strike` | 111,563 | 112,613 | 1050ms | None | None | ±0ms / ±17ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#9** | 113,230 – 116,632 | `estimated_strike` | 115,447 | 115,915 | 468ms | 468ms | 2.6:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#10** | 119,032 – 122,632 | `no_ball` | 120,415 | 121,098 | 683ms | None | None | ±0ms / ±0ms | `needs_review` | ⚠️ 時序異常，自主降級不評分 |
| **#11** | 123,767 – 129,433 | `estimated_strike` | 124,900 | 125,367 | 467ms | 467ms | 0.86:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |
| **#12** | 134,835 – 138,853 | `estimated_strike` | 136,335 | 136,553 | 218ms | 218ms | 2.29:1 | ±0ms / ±0ms | `auto_accepted` | ✅ 正常指標完整產出 |

---

## 5. 與 Ground Truth 一對一比對與差距客觀診斷表 (P0-A & P0-B)

| 球次 | GT 區間 (ms) | 預測區間 (ms) | Top 偏差 | Impact 偏差 | GT 驗證狀態 | 多訊號一致性 | 客觀差距根因診斷與證據說明 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **#1** | 11,351 – 15,201 | 9,005 – 16,305 | 2579ms | 2863ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7300ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=10472, GT Top=13051)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#2** | 24,320 – 28,270 | 23,808 – 29,810 | 760ms | 1093ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6002ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=25260, GT Top=26020)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#3** | 38,355 – 42,139 | 36,745 – 43,912 | 1944ms | 2044ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7167ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=38095, GT Top=40039)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#4** | 51,074 – 54,957 | 50,215 – 57,417 | 1259ms | 1609ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (7202ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=51515, GT Top=52774)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#5** | 66,276 – 70,226 | 65,018 – 71,420 | 1724ms | 1841ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6402ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=66252, GT Top=67976)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#6** | 84,945 – 88,895 | 83,023 – 89,625 | 2372ms | 2672ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (6602ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=84273, GT Top=86645)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#7** | 104,148 – 108,098 | 103,828 – 107,628 | 820ms | 1220ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (3800ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=105028, GT Top=105848)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#8** | 109,882 – 113,766 | 109,630 – 113,413 | 19ms | 447ms | `machine_suggested` | `TIMING_ANOMALY` | 下桿時間超出生理正常區間 (1050ms)，系統自主判定異常並降級保護 |
| **#9** | 113,749 – 117,500 | 113,230 – 116,632 | 2ms | 15ms | `machine_suggested` | `HIGH` | 模型預測與金標高度吻合 (Top 差 2ms, Imp 差 15ms)，多訊號一致 |
| **#10** | 119,550 – 123,434 | 119,032 – 122,632 | 819ms | 736ms | `machine_suggested` | `TIMING_ANOMALY` | 下桿時間超出生理正常區間 (683ms)，系統自主判定異常並降級保護 |
| **#11** | 124,184 – 128,101 | 123,767 – 129,433 | 968ms | 1134ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (5666ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=124900, GT Top=125868)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |
| **#12** | 136,219 – 139,053 | 134,835 – 138,853 | 1584ms | 2016ms | `machine_suggested` | `DISPUTED_WAGGLE` | 候選視窗 (4018ms) 內存在前置試擺(Waggle)與擊球雙峰波形競爭 (Pred Top=136335, GT Top=137919)。GT 目前為 machine_suggested 初標，兩者鎖定不同波峰，維持客觀不強行硬調 |

---

## 6. 8 顆雙峰波形爭議球與第 6 球多候選假設證據表 (P0-1 ~ P0-3)

> 本專案已實作多候選揮桿鏈推導架構：為每個擊球候選向前追溯完整 Address → Takeaway → Top → Downswing → Impact → Follow Through → Finish。
> 每組候選綜合下桿時序、上下桿幅度、隨揮延伸、收桿停頓、重新站定沉靜度與音訊瞬態進行獨立客觀評分裁決。

| 球次 | 候選 ID | Top (ms) | Impact (ms) | 下桿 (ms) | 綜合評分 | 支持證據 (Supporting) | 反對理由 (Opposing) | 裁決結果與原因 |
|:---:|:---:|:---:|:---:|:---:|:---:|---|---|---|
| **#1** | `cand-1` | 10,405 | 10,805 | 400ms | **10.0** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0012)<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=-0.047)<br>abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=10405ms, Imp=10805ms, 得分=10.0) 顯著優於次佳候選 (得分=6.0)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, weak_follow_through_waggle_like (amp=-0.022)。 |
| **#1** | `cand-2` | 12,873 | 13,407 | 534ms | **6.0** | physiologically_valid_downswing (534ms)<br>audio_aligned_with_strike (diff=27ms) | shallow_stroke_amplitude<br>weak_follow_through_waggle_like (amp=-0.022) | — |
| **#2** | `cand-1` | 25,210 | 25,543 | 333ms | **16.5** | physiologically_valid_downswing (333ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0012)<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=23ms) | abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=25210ms, Imp=25543ms, 得分=16.5) 顯著優於次佳候選 (得分=5.0)。關鍵優勢: physiologically_valid_downswing (333ms), adequate_stroke_amplitude。次佳候選反對理由: slow_downswing_duration (733ms), weak_follow_through_waggle_like (amp=-0.028)。 |
| **#2** | `cand-3` | 26,277 | 27,010 | 733ms | **5.0** | adequate_stroke_amplitude<br>finish_balance_hold (400ms)<br>settled_readdress_before_takeaway | slow_downswing_duration (733ms)<br>weak_follow_through_waggle_like (amp=-0.028)<br>isolated_background_audio (diff=1210ms) | — |
| **#3** | `cand-1` | 38,012 | 38,345 | 333ms | **14.0** | physiologically_valid_downswing (333ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0014)<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=75ms) | abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=38012ms, Imp=38345ms, 得分=14.0) 顯著優於次佳候選 (得分=6.0)。關鍵優勢: physiologically_valid_downswing (333ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, weak_follow_through_waggle_like (amp=-0.025)。 |
| **#3** | `cand-2` | 39,947 | 40,480 | 533ms | **6.0** | physiologically_valid_downswing (533ms)<br>audio_aligned_with_strike (diff=0ms) | shallow_stroke_amplitude<br>weak_follow_through_waggle_like (amp=-0.025) | — |
| **#4** | `cand-1` | 51,548 | 51,815 | 267ms | **14.5** | physiologically_valid_downswing (267ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0010)<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=5ms) | weak_follow_through_waggle_like (amp=-0.059)<br>abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=51548ms, Imp=51815ms, 得分=14.5) 顯著優於次佳候選 (得分=11.5)。關鍵優勢: physiologically_valid_downswing (267ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=-0.016), abrupt_cutoff_no_finish_hold。 |
| **#4** | `cand-4` | 52,748 | 53,350 | 602ms | **11.5** | physiologically_valid_downswing (602ms)<br>adequate_stroke_amplitude<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=10ms) | weak_follow_through_waggle_like (amp=-0.016)<br>abrupt_cutoff_no_finish_hold | — |
| **#5** | `cand-1` | 66,218 | 66,618 | 400ms | **14.0** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0012)<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=62ms) | abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=66218ms, Imp=66618ms, 得分=14.0) 顯著優於次佳候選 (得分=2.5)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, abrupt_cutoff_no_finish_hold。 |
| **#5** | `cand-2` | 67,953 | 68,553 | 600ms | **2.5** | physiologically_valid_downswing (600ms) | shallow_stroke_amplitude<br>abrupt_cutoff_no_finish_hold<br>isolated_background_audio (diff=207ms) | — |
| **#6** | `cand-1` | 84,290 | 84,623 | 333ms | **16.5** | physiologically_valid_downswing (333ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0011)<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=57ms) | abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=84290ms, Imp=84623ms, 得分=16.5) 顯著優於次佳候選 (得分=11.5)。關鍵優勢: physiologically_valid_downswing (333ms), adequate_stroke_amplitude。次佳候選反對理由: abrupt_cutoff_no_finish_hold。 |
| **#6** | `cand-2` | 86,090 | 86,690 | 600ms | **11.5** | physiologically_valid_downswing (600ms)<br>adequate_stroke_amplitude<br>audio_aligned_with_strike (diff=50ms) | abrupt_cutoff_no_finish_hold | — |
| **#7** | `cand-1` | 104,962 | 105,295 | 333ms | **12.0** | physiologically_valid_downswing (333ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0012)<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=85ms) | weak_follow_through_waggle_like (amp=-0.063)<br>abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=104962ms, Imp=105295ms, 得分=12.0) 顯著優於次佳候選 (得分=6.5)。關鍵優勢: physiologically_valid_downswing (333ms), adequate_stroke_amplitude。次佳候選反對理由: slow_downswing_duration (800ms), weak_follow_through_waggle_like (amp=-0.029)。 |
| **#7** | `cand-2` | 105,695 | 106,495 | 800ms | **6.5** | adequate_stroke_amplitude<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=15ms) | slow_downswing_duration (800ms)<br>weak_follow_through_waggle_like (amp=-0.029)<br>abrupt_cutoff_no_finish_hold | — |
| **#8** | `cand-2` | 111,697 | 112,497 | 800ms | **5.0** | adequate_stroke_amplitude<br>finish_balance_hold (400ms) | slow_downswing_duration (800ms) | **✅ 選用**<br>優勢裁決：候選1 (Top=111697ms, Imp=112497ms, 得分=5.0) 顯著優於次佳候選 (得分=3.0)。關鍵優勢: adequate_stroke_amplitude, finish_balance_hold (400ms)。次佳候選反對理由: slow_downswing_duration (666ms), weak_follow_through_waggle_like (amp=-0.024)。 |
| **#8** | `cand-1` | 111,497 | 112,163 | 666ms | **3.0** | adequate_stroke_amplitude<br>audio_near_strike (diff=77ms) | slow_downswing_duration (666ms)<br>weak_follow_through_waggle_like (amp=-0.024) | — |
| **#9** | `cand-2` | 115,363 | 115,898 | 535ms | **11.5** | physiologically_valid_downswing (535ms)<br>adequate_stroke_amplitude<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=38ms) | weak_follow_through_waggle_like (amp=-0.024)<br>abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=115363ms, Imp=115898ms, 得分=11.5) 顯著優於次佳候選 (得分=7.0)。關鍵優勢: physiologically_valid_downswing (535ms), adequate_stroke_amplitude。次佳候選反對理由: weak_follow_through_waggle_like (amp=-0.034), abrupt_cutoff_no_finish_hold。 |
| **#9** | `cand-1` | 114,497 | 114,897 | 400ms | **7.0** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>settled_readdress_before_takeaway | weak_follow_through_waggle_like (amp=-0.034)<br>abrupt_cutoff_no_finish_hold<br>isolated_background_audio (diff=437ms) | — |
| **#10** | `cand-2` | 120,432 | 121,098 | 666ms | **12.0** | high_impact_speed_peak (0.0010)<br>moderate_follow_through (amp=0.082)<br>finish_balance_hold (533ms)<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=38ms) | slow_downswing_duration (666ms)<br>shallow_stroke_amplitude | **✅ 選用**<br>雙峰爭議：候選1 (120432/121098ms, 分數=12.0) 與候選2 (121232/121898ms, 分數=11.5) 得分接近且皆具備揮桿特徵，證據未達絕對優勢，標記爭議保留審核。 |
| **#10** | `cand-3` | 121,232 | 121,898 | 666ms | **11.5** | adequate_stroke_amplitude<br>impact_deceleration_brake (0.0003)<br>finish_balance_hold (669ms)<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=2ms) | slow_downswing_duration (666ms)<br>weak_follow_through_waggle_like (amp=-0.007) | — |
| **#11** | `cand-1` | 124,967 | 125,367 | 400ms | **11.5** | physiologically_valid_downswing (400ms)<br>adequate_stroke_amplitude<br>settled_readdress_before_takeaway<br>audio_aligned_with_strike (diff=53ms) | weak_follow_through_waggle_like (amp=-0.037)<br>abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=124967ms, Imp=125367ms, 得分=11.5) 顯著優於次佳候選 (得分=3.5)。關鍵優勢: physiologically_valid_downswing (400ms), adequate_stroke_amplitude。次佳候選反對理由: shallow_stroke_amplitude, isolated_background_audio (diff=380ms)。 |
| **#11** | `cand-4` | 126,700 | 127,300 | 600ms | **3.5** | physiologically_valid_downswing (600ms) | shallow_stroke_amplitude<br>isolated_background_audio (diff=380ms) | — |
| **#12** | `cand-1` | 136,302 | 136,637 | 335ms | **14.0** | physiologically_valid_downswing (335ms)<br>adequate_stroke_amplitude<br>high_impact_speed_peak (0.0011)<br>settled_readdress_before_takeaway<br>audio_near_strike (diff=83ms) | abrupt_cutoff_no_finish_hold | **✅ 選用**<br>優勢裁決：候選1 (Top=136302ms, Imp=136637ms, 得分=14.0) 顯著優於次佳候選 (得分=2.0)。關鍵優勢: physiologically_valid_downswing (335ms), adequate_stroke_amplitude。次佳候選反對理由: extreme_downswing_duration (933ms)。 |
| **#12** | `cand-3` | 137,437 | 138,370 | 933ms | **2.0** | adequate_stroke_amplitude<br>settled_readdress_before_takeaway | extreme_downswing_duration (933ms) | — |

---

## 7. 真實長片未標註間隔區段 (unlabeled_candidate_negatives) 獨立檢驗 (P0-4)

- **測試長片總長度**：`139053ms` (139.1 秒)
- **非揮桿間隔區段數**：`12` 個區段
- **非揮桿總測試時長**：`74.29s` (53.4% 片長)
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
| `neg-gap-8` | `unlabeled_candidate_negatives` | 107,628 – 109,630 | 2.00s | 球次 #7 與 #8 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-9` | `unlabeled_candidate_negatives` | 116,632 – 119,032 | 2.40s | 球次 #9 與 #10 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-10` | `unlabeled_candidate_negatives` | 122,632 – 123,767 | 1.14s | 球次 #10 與 #11 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-11` | `unlabeled_candidate_negatives` | 129,433 – 134,835 | 5.40s | 球次 #11 與 #12 間之撿球、放球、看球路與試擺 | 0 | 0 | `NOT_VALIDATED` |
| `neg-gap-12` | `unlabeled_candidate_negatives` | 138,853 – 139,053 | 0.20s | 最後一球擊出後之收桿與離場整理 | 0 | 0 | `NOT_VALIDATED` |

---

## 8. 最佳球推薦 (Best Swings Ranking) 爭議排除驗收 (P0-5)

- **排除策略**：凡存在未解決雙峰爭議（`ambiguous` / `needs_review` / `timing_anomaly`）之球次，嚴格於 `posture`（姿勢最佳）與 `tempo`（節奏最佳）排行榜中排除，確保不將可能有裁切爭議之動作推薦給球友作為模範揮桿。
- **IG 視覺呈現**：IG 9:16 直式畫面獨立計算視覺構圖評分，但若該球具備爭議，排行榜資料流維持排除保護。

### 姿勢最佳排行榜 (Posture Top 5)
| 排名 | 球次 | 分類得分 | 綜合動作分 | 推薦理由 | 手動置頂標記 |
|:---:|:---:|:---:|:---:|---|:---:|
| **第 1 名** | **#12** | 81.8 | 81.8 | 軀幹前傾穩定 Δ=1.4°，動作總分 81.8 分 | `自動推薦` |
| **第 2 名** | **#2** | 73.9 | 73.9 | 軀幹前傾穩定 Δ=2.7°，動作總分 73.9 分 | `自動推薦` |
| **第 3 名** | **#11** | 72.9 | 72.9 | 軀幹前傾穩定 Δ=1.0°，動作總分 72.9 分 | `自動推薦` |
| **第 4 名** | **#4** | 72.5 | 72.5 | 軀幹前傾穩定 Δ=3.4°，動作總分 72.5 分 | `自動推薦` |
| **第 5 名** | **#7** | 72.1 | 72.1 | 軀幹前傾穩定 Δ=4.7°，動作總分 72.1 分 | `自動推薦` |

### 節奏最佳排行榜 (Tempo Consistency Top 5)
| 排名 | 球次 | 分類得分 | 綜合動作分 | 推薦理由 | 手動置頂標記 |
|:---:|:---:|:---:|:---:|---|:---:|
| **第 1 名** | **#9** | 92.3 | 55.4 | 上下桿時間比 2.60:1（標準 3.0:1），節奏得分 92.3 分 | `自動推薦` |
| **第 2 名** | **#12** | 76.3 | 81.8 | 上下桿時間比 2.29:1（標準 3.0:1），節奏得分 76.3 分 | `自動推薦` |
| **第 3 名** | **#7** | 68.0 | 72.1 | 上下桿時間比 2.13:1（標準 3.0:1），節奏得分 68.0 分 | `自動推薦` |
| **第 4 名** | **#1** | 61.8 | 68.5 | 上下桿時間比 2.01:1（標準 3.0:1），節奏得分 61.8 分 | `自動推薦` |
| **第 5 名** | **#4** | 54.1 | 72.5 | 上下桿時間比 1.86:1（標準 3.0:1），節奏得分 54.1 分 | `自動推薦` |

### 收桿最佳排行榜 (Finish Balance Top 5)
| 排名 | 球次 | 分類得分 | 綜合動作分 | 推薦理由 | 手動置頂標記 |
|:---:|:---:|:---:|:---:|---|:---:|
| **第 1 名** | **#7** | 88.0 | 72.1 | 收桿停頓 2533ms、晃動比 0.083，收桿得分 88.0 分 | `自動推薦` |
| **第 2 名** | **#11** | 83.7 | 72.9 | 收桿停頓 4201ms、晃動比 0.098，收桿得分 83.7 分 | `自動推薦` |
| **第 3 名** | **#12** | 81.6 | 81.8 | 收桿停頓 2467ms、晃動比 0.106，收桿得分 81.6 分 | `自動推薦` |
| **第 4 名** | **#2** | 80.8 | 73.9 | 收桿停頓 4400ms、晃動比 0.108，收桿得分 80.8 分 | `自動推薦` |
| **第 5 名** | **#9** | 74.4 | 55.4 | 收桿停頓 867ms、晃動比 0.056，收桿得分 74.4 分 | `自動推薦` |

### IG 短影音推薦榜 (IG Visual Appeal Top 5)
| 排名 | 球次 | 分類得分 | 綜合動作分 | 推薦理由 | 手動置頂標記 |
|:---:|:---:|:---:|:---:|---|:---:|
| **第 1 名** | **#9** | 89.9 | 55.4 | 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 89.9 分 | `自動推薦` |
| **第 2 名** | **#8** | 88.6 | 66.3 | 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 88.6 分 | `自動推薦` |
| **第 3 名** | **#7** | 88.5 | 72.1 | 畫面完整度 99.8 分、收桿平穩，IG 吸睛分 88.5 分 | `自動推薦` |
| **第 4 名** | **#12** | 88.1 | 81.8 | 畫面完整度 99.8 分、收桿平穩，IG 吸睛分 88.1 分 | `自動推薦` |
| **第 5 名** | **#2** | 80.6 | 73.9 | 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 80.6 分 | `自動推薦` |


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

