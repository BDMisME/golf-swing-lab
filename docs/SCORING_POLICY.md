# SCORING_POLICY.md — 可解釋動作評分與信心度政策（`score-v1`）

## 1. 評分哲學與定位聲明
- 本系統之動作評分（0–100）為 **Golf Swing Lab 內部定義之 2D DTL（後方視角）動作檢核指標**。
- 分數僅反映「該球在 2D 後方影像中可觀測之身體穩定度、節奏與同場重複性」，**絕不等同於職業教練認證、亦不代表實際擊球飛行距離、球速或方向**。
- 每筆評分必須附帶：
  - `score_version`（初版為 `score-v1`）
  - `overall_nullable`（`float | null`，當有效權重覆蓋率 `< 0.70` 時必須為 `null`）
  - `partial_score`（`bool`，若任一分項缺值但覆蓋率 `>= 0.70` 則為 `true`）
  - `coverage`（`0.0 ~ 1.0`，已有效觀測之分項權重總和除以 100）
  - `confidence`（`0.0 ~ 1.0`，整體評分信心度）
  - `subscores_json`（各分項原始量測值、正規化分數、權重、信心度與「怎麼算的？」繁體中文說明）
  - `explanation`（人類可讀之計分與扣分依據摘要）

## 2. 動作評分五大分項與公式（`score-v1`）

| 分項代號 | 名稱 | 預設權重 | 輸入指標 (`swing_metrics`) | 100 分基準與扣分函數 | 觀測不足條件 |
|---|---|---:|---|---|---|
| `spine_tilt_stability` | 軀幹前傾穩定 | 25% | `spine_tilt_delta_deg`（Address 至 Impact/Downswing 之 2D 軀幹傾角變化絕對值，單位：度） | $\Delta \le 2.5^\circ \Rightarrow 100$；線性遞減至 $\Delta \ge 15.0^\circ \Rightarrow 20$：$S = \text{clip}(100 - \frac{\Delta - 2.5}{12.5}\times 80, 0, 100)$ | 肩或髖關鍵點於 Address 或 Downswing 可見度 $< 0.50$ |
| `head_stability` | 頭部相對位移 | 15% | `head_displacement_ratio`（Address 至 Impact 期間，鼻/耳中心相對於軀幹長度之最大 2D 位移比例） | $r \le 0.06 \Rightarrow 100$；線性遞減至 $r \ge 0.28 \Rightarrow 20$：$S = \text{clip}(100 - \frac{r - 0.06}{0.22}\times 80, 0, 100)$ | 頭部或軀幹基準長度可見度 $< 0.50$ |
| `path_repeatability` | 身體與手部軌跡重複性 | 20% | `hand_path_deviation_ratio`（同場同視角下，手腕於 Takeaway/Top/Downswing 歸一化座標與場次中位數軌跡之偏差；若全場僅 1 球則以單球上/下桿平面差距 `plane_gap_ratio` 評估） | $d \le 0.05 \Rightarrow 100$；線性遞減至 $d \ge 0.25 \Rightarrow 25$ | 手腕關鍵點可見度 $< 0.50$ |
| `tempo_consistency` | 上下桿節奏一致性 | 20% | `backswing_downswing_ratio`（Takeaway→Top 時間除以 Top→Impact_Estimated 時間，理想區間 $2.6 \sim 3.4$）及與同場中位數之偏差 | 偏離理想中心 $3.0$ 之誤差 $e = |ratio - 3.0|$：$e \le 0.25 \Rightarrow 100$，線性遞減至 $e \ge 1.8 \Rightarrow 20$ | 無法定位 Takeaway、Top 或 Impact_Estimated 時間點 |
| `finish_balance` | 收桿姿勢穩定 | 20% | `finish_hold_ms`（收桿維持穩定時間）與 `finish_sway_ratio`（收桿期間重心/踝部晃動比） | Hold $\ge 1200\text{ms}$ 且晃動 $\le 0.05 \Rightarrow 100$；依穩定停留時間與晃動扣分 | 收桿階段身體出鏡或關鍵點可見度 $< 0.50$ |

## 3. 缺失值與 70% 覆蓋率閘門（Coverage Gate）
1. 設有效分項集合為 $V = \{i \mid \text{confidence}_i \ge 0.50 \land \text{value}_i \neq \text{null}\}$。
2. 計算覆蓋率 $\text{coverage} = \frac{\sum_{i \in V} w_i}{100}$。
3. **若 $\text{coverage} < 0.70$**：
   - `overall_nullable = null`
   - `partial_score = true`
   - 介面明確顯示 **「無法可靠評分（資料覆蓋率不足）」**，絕不強行湊出總分。
4. **若 $0.70 \le \text{coverage} < 1.00$**：
   - 依有效分項權重等比例重正規化：$\text{overall} = \text{round}\left(\frac{\sum_{i \in V} w_i \cdot S_i}{\sum_{i \in V} w_i}, 1\right)$
   - `partial_score = true`
5. **若 $\text{coverage} = 1.00$**：
   - `partial_score = false`
   - $\text{overall} = \text{round}\left(\sum_i \frac{w_i}{100} S_i, 1\right)$

## 4. IG 視覺呈現分數（`ig_visual_score`，完全獨立）
- 用途：協助球友挑選**畫面完整、收桿平穩、節奏流暢、清晰可剪輯**的社群分享片段，嚴禁宣稱為「打最好或打最遠的一球」。
- 權重組合：
  1. 全身入鏡完整度（Framing Completeness）：30%
  2. 平穩收桿（Finish Stability）：25%
  3. 節奏流暢觀感（Tempo Visual Flow）：20%
  4. 畫面清晰與穩定度（Sharpness & Camera Stability）：15%
  5. 起迄剪輯緩衝完整性（Clip Margin Completeness）：10%
