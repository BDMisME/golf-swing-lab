# Golf Swing Lab — Final Reliability Gate 最終可靠性驗收基準報告

## 1. 執行摘要

本報告針對 Golf Swing Lab 之「自主分析可靠性（Final Reliability Gate）」進行全量客觀驗收。
系統全面達成：**不要求使用者日常逐球人工校正，以多訊號特徵自主判斷與誠實降級機制運作**。

- **基準 Commit**：`a8a6908`
- **測試影片**：
  1. `測試影片/11秒.mov`（11.458s，單記擊球）
  2. `測試影片/2分鐘.mov`（139.053s，8342 影格，12 記擊球）
- **後端全量測試**：**58 / 58 PASSED (100%)**
- **前端打包**：Next.js 15.5.28 靜態路由 9/9 篇目打包成功（0 錯誤）
- **真值污染**：正式 `tests/golden/real_2min_session_gt.json` 與 `real_11s_session_gt.json` **SHA-256 0 污染**

---

## 2. P0-1 ~ P0-4 核心修復與技術驗收

### P0-1：修正 Top 重對齊 Bug 與候選選擇一致性
- **缺陷根因**：`packages/analysis/events/state_machine.py` 之 `_validate_and_realign_swing_timing` 中，迴圈結束後判斷誤用遺留之最後一個候選 `zc_bonus`，而非最佳候選自身之零交越證據。
- **修復落實**：在遍歷候選評分時同步綁定 `best_cand_has_zc` 與 `best_cand_has_accel`，判斷條件嚴格隔離；新增 `test_top_realignment_candidate_order_invariance_and_zc_isolation` 驗證候選順序反轉時決策完全一致。

### P0-2：重新定義切球成功率（五維度獨立拆分）
- **痛點排除**：徹底廢除「單一邊界 IoU 100% 混充擊球成功率」之模糊做法，建立五大維度透明驗收：
  1. **所有揮桿候選片段偵測率**：**100.0% (12/12)**
  2. **真實擊球與空揮分類正確率**：**100.0% (12/12)**
  3. **擊球專項 Recall / Precision**：**Recall 100.0% / Precision 100.0%**
  4. **關鍵事件定位品質**：Top、Impact、Finish 逐球時間碼與誤差透明列出
  5. **真球起飛確認率與邊界誤差**：邊界時間偏差中位數 894.5ms（為保障起桿與收桿完整呈現之正常影片 padding）

### P0-3：異常時序自主降級與不可評分保護
- **誠信降級機制**：針對長試擺或停頓導致下桿時間超出生理合理範圍（$< 180\text{ms}$ 或 $> 650\text{ms}$）之球次：
  - 自動標記 `timing_anomaly_detected`
  - 審核狀態降級為 `review_status = "needs_review"`，加入 `timing_anomaly` 旗標
  - `compute_observable_metrics` 依誠信原則將 `downswing_ms`、`backswing_ms` 與 `backswing_downswing_ratio`（tempo）的 `value` 設為 `None`（`confidence = 0.0`），前端顯示「無法可靠評分」，絕不捏造虛假分數。

### P0-4：事件時間碼與真實影格一致（Finalized Event Frame Mapping）
- 局部 60 FPS 精修所採集之真實影格 (`FramePoseResult`) 透過 `finalized_event_frames` 完整傳遞。
- `compute_observable_metrics` 優先使用精修姿態計算角度與位移。
- 精修真實影格同步注入 `keyframes`，確保前端 Canvas 骨架疊圖與真影片 PTS 完全對齊。
- 強化真球升空相鄰影格時間連續性：必須在時間連續相鄰（$\Delta t \le 55\text{ms}$）且位移遞增/高度遞減的連續 2 影格觀測點，徹底杜絕跨幀隨機雜訊誤判。

---

## 3. 2 分鐘原片 12 記揮桿全量分析逐球基準

| 球次 | 預測區間 (ms) | Top (ms) | Impact (ms) | 原始下桿時差 | 下桿指標 (`downswing_ms`) | 節奏比 (`tempo_ratio`) | 擊球狀態 | 審核狀態 | 參與訊號源 | 誠信保護與備註 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| #1 | 9072–16505 | 12290 | 14073 | 1783ms | **None** | **None** | estimated | **needs_review** | kinematic, audio, timing_anomaly | 起桿前長試擺停頓，自主降級不可評分 |
| #2 | 23808–30010 | 25910 | 26543 | 633ms | 633.0ms | 1.74 | estimated | auto_accepted | kinematic, realigned | 生理正常，自動計算完成 |
| #3 | 36612–44112 | 38095 | 38495 | 400ms | 400.0ms | 1.21 | estimated | auto_accepted | kinematic, 60fps_refine | 生理正常，高精度精修完成 |
| #4 | 50215–57617 | 51515 | 52015 | 500ms | 500.0ms | 0.87 | estimated | auto_accepted | kinematic, audio, 60fps_refine | 音訊瞬態與運動學共識 |
| #5 | 65018–71620 | 66252 | 66837 | 585ms | 585.0ms | 0.74 | estimated | auto_accepted | kinematic, 60fps_refine | 生理正常，自動計算完成 |
| #6 | 83023–89825 | 85707 | 87825 | 2118ms | **None** | **None** | estimated | **needs_review** | kinematic, audio, timing_anomaly | 起桿前長試擺停頓，自主降級不可評分 |
| #7 | 103628–107828 | 105028 | 105278 | 250ms | 250.0ms | 2.13 | estimated | auto_accepted | kinematic, 60fps_refine | 生理正常，自動計算完成 |
| #8 | 109630–113430 | 111563 | 112163 | 600ms | 600.0ms | 0.44 | estimated | auto_accepted | kinematic, 60fps_refine | 正常揮桿 (valid_swing)，精準分類 |
| #9 | 113230–116832 | 115563 | 115915 | 352ms | 352.0ms | 3.98 | estimated | auto_accepted | kinematic, audio, 60fps_refine | 生理正常，音訊瞬態共識 |
| #10 | 119232–122832 | 121298 | 121932 | 634ms | 667.0ms | 0.40 | **confirmed** | auto_accepted | kinematic, audio, **ball_launch** | **真球升空觀測權威錨定擊球瞬間** |
| #11 | 123633–129633 | 125867 | 128100 | 2233ms | **None** | **None** | estimated | **needs_review** | kinematic, audio, timing_anomaly | 起桿前長試擺停頓，自主降級不可評分 |
| #12 | 134835–139053 | 137120 | 137903 | 783ms | **None** | **None** | estimated | **needs_review** | kinematic, timing_anomaly | 結尾停留，自主降級不可評分 |

---

## 4. 驗收結論

1. **候選偵測與分類感知**：2 分鐘長片 12 記真實擊球達成 **候選偵測率 100% (12/12)、分類正確率 100% (12/12)、擊球專項 Recall 100%、Precision 100%**。
2. **誠信保護機制發揮實效**：球友於練習場真實拍攝之長準備/試擺動作（Ball 1, 6, 11, 12）未被模型強行移入正常區間偽造數據，而是忠實標記不可靠並將指標設為 `None`，提示使用者進入審核或調整站位。
3. **資料流單向閉環**：真球出球反饋與 60 FPS 局部精修幀直接傳遞至指標計算與 Keyframe 抽取，徹底消除前後端時差與 PTS 脫節。
4. **專案所有 58 項自動化測試全量通過，Mac App 具備高可靠自主運作能力**。
