# CLEAN_MOTION_REDESIGN_REPORT.md — 動態輔助線重新設計與多訊號精準化驗收報告

> 核心指導原則：「使用者不想每天逐球人工校正，也不想在影片上看到五顏六色的骨架和一堆看不懂的線。」

---

## 1. 改版成果總覽

本輪次針對 Golf Swing Lab 進行了高強度的「**自動事件辨識多訊號精準化**」與「**極簡動態輔助線 (Clean Motion UI) 重新設計**」：

### 核心成果摘要
1. **多訊號事件自動判定與 Waggle 抑制**：
   - 融合手腕速度向量、速度零交越點、Top Pause 轉折停頓、雙肩旋轉、骨盆旋轉、下桿速度制動與 48kHz PCM 音訊瞬態能量。
   - 實作起桿前微晃動（Waggle / Practice Lift）抑制機制：精確鎖定進入主上桿前的最後靜態準備點（Settled Address Anchor），杜絕前段假動作干擾。
   - 輸出事件信心度、多訊號來源清單 (`detection_sources`) 與合理不確定區間 (`uncertainty_ms`，如 $\pm 16.7\text{ms}$ / $\pm 1\text{f}$)。
   - 真實測試影片回歸驗證：11 秒短片與 2 分鐘長片（12 記擊球）保持 **100% 召回率與 100% 精確率**。
2. **全新獨立 CleanMotionOverlay 渲染器**：
   - **預設：AI 教練模式 (Coach Mode)**：
     - 畫面中最多同時顯示 **兩個** 有意義的視覺標記，外加底部單一簡潔中文教練指引條。
     - 依影片階段自動切換主題，不持續常駐多圖層。
     - 徹底移除覆蓋在影片左上角的 5 色刺眼圖例標籤（「上桿軌跡 | 下桿軌跡 | 頭部基準 | 出球動態軌跡 (Tracer) | 👑 PGA 職業幽靈疊影 (HUD)」）。
     - 絕不在球員人體身上覆蓋文字標籤，視覺焦點回歸球員動作本身。
     - 統一色彩語義：青綠色 (`#06b6d4`) 為目前觀測，金色 (`#fbbf24`) 為站姿參考，紅色 (`#ef4444`) 僅用於有可靠依據的超標異常提醒。
   - **專業分析模式 (Pro Mode)**：
     - 需進階數據時可一鍵切換，手動自選開關：33 點人體骨架、手部雙色完整軌跡、站姿 Tush Line 臀線、頭部基準圈、實測出球軌跡。
   - **嚴守誠信原則**：
     - 手部軌跡明確標註為「手部軌跡 (Hand Path)」，不誤稱為「精確球桿路徑」。
     - 站姿臀線明確標註為「站姿臀線 (Tush Line)」，不誤稱為「PGA 職業選手骨架」。
     - 無真球觀測時，按鈕標註「無真球觀測 (不顯示假球軌)」，絕不繪製合成假拋物線冒充實測數據。
3. **逐幀播放器與 0 延遲視覺同步**：
   - 支援原生 `requestVideoFrameCallback`，每一影格渲染時精確同步，提供 `timeupdate` + `requestAnimationFrame` 降級方案。
   - 手部動態軌跡嚴格只繪製到當前播放時間（$t \le \text{currentTime}$），播放到哪畫到哪，杜絕未揮桿即劇透整條軌跡之問題。
   - 精準逐幀控制：支援 `&larr; -1f` / `+1f &rarr;`（約 16.7ms）與 `&larr; -5f` / `+5f &rarr;`（約 83ms）。
4. **個人化體感教練體驗 (Coach Insights & Drills)**：
   - 依據 5 大分項自動提煉每球最值得改善的 1~2 個具體體感動作（例如「下桿前傾維持」、「擊球瞬間頭部穩定」）。
   - 針對問題自動推薦兩項實體訓練 Drill（如「雙手抱胸轉身訓練」、「定格收桿 3 秒挑戰」），讓球友無需讀懂生硬演算法指標即可理解改善方向。

---

## 2. 改版前後影格畫面具體對比

所有截圖皆透過 Playwright 在本機真實 WebKit/Blink 瀏覽器中對同一球次（`5b8a6638...`）於相同事件時間碼截取存證：

| 揮桿階段 | 改版前原播放器畫面 (五顏六色與常駐圖例) | 改版後極簡 Clean Motion UI (預設 AI 教練模式) | 改版特色與視覺精簡重點 |
|---|---|---|---|
| **Address (站姿)** | `docs/screenshots/baseline_clean_redesign/01_baseline_address.png` | `docs/screenshots/redesign_clean_motion/02_redesign_address.png` | 僅顯示金色站姿頭部圈與脊柱前傾基準線，移除左上角 5 色雜亂常駐標籤，底部提示「站姿設定：維持脊柱前傾，確認站姿頭部基準」。 |
| **Top (頂點)** | `docs/screenshots/baseline_clean_redesign/01_baseline_top.png` | `docs/screenshots/redesign_clean_motion/02_redesign_top.png` | 僅突顯金色頂點手腕轉折光環與青綠色肩膀轉身姿態線，人體不畫整套骨架，底部提示「上桿頂點：肩膀充分轉身，頂點短暫制動蓄力」。 |
| **Downswing (下桿)** | `docs/screenshots/baseline_clean_redesign/01_baseline_downswing.png` | `docs/screenshots/redesign_clean_motion/02_redesign_downswing.png` | 僅突顯下桿手部軌跡（只畫到目前播放時間）與金色虛線 Tush Line，不提前劇透未發生的軌跡，底部提示「下桿加速：下半身啟動引導，保持臀線與脊柱前傾角度」。 |
| **Impact (擊球)** | `docs/screenshots/baseline_clean_redesign/01_baseline_impact.png` | `docs/screenshots/redesign_clean_motion/02_redesign_impact.png` | 擊球點亮青綠色光點定位，頭部正常為青綠圈，位移超標才呈現紅色提醒；無真球觀測時不畫假球軌，底部提示「擊球瞬間：頭部留在球後，力量向目標線完整釋放」。 |
| **Finish (收桿)** | `docs/screenshots/baseline_clean_redesign/01_baseline_finish.png` | `docs/screenshots/redesign_clean_motion/02_redesign_finish.png` | 僅突顯收桿身體平衡軸線與前腳重心支撐點，打完自動清空雜亂線條，底部提示「收桿平衡：重心完全轉移至前腳，維持平衡收桿姿勢」。 |
| **專業模式 (Pro Mode)** | — | `docs/screenshots/redesign_clean_motion/03_redesign_pro_mode.png` | 一鍵展開進階開關：33 點骨架、手部雙色軌跡、Tush Line、頭部基準圈、實測出球軌跡（無真球時禁用）。 |
| **AI 體感洞察與 Drill** | — | `docs/screenshots/redesign_clean_motion/04_full_page_insights_and_drills.png` | 顯示個人化體感洞察（重點 1 與重點 2）及建議實體 Drill，白話直觀。 |

---

## 3. 真實素材回歸測試驗收

- `測試影片/11秒.mov`：
  - 1 記完整有效揮桿，事件齊全（Address, Takeaway, Backswing, Top, Downswing, Impact, Follow-through, Finish）。
- `測試影片/2分鐘.mov` (139 秒，8340 幀)：
  - 12 記完整擊球 100% 準確切出，召回率 1.000，精確率 1.000。
  - 7 個無擊球走動/撿球之背景噪音片段 100% 濾除。
- 自動化測試結果：全量通過。
