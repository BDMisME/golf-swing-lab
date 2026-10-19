# GOLDEN_DATASET.md — 標註規範、評估方法與驗收門檻

## 1. Golden Dataset 設計目的
為驗證長影片揮桿偵測演算法之真實表現，避免「以假資料宣稱高準確率」，本系統定義標準化之 Golden Set JSON Schema 與評估腳本（`packages/analysis/evaluation/golden_eval.py`）。

## 2. 標註檔案格式（`tests/golden/*.json`）
每個標註檔對應一部練習影片（私人原片存放於安全路徑或 S3，不進 Git 版控；Git 僅保存匿名 metadata 與合成測試樣本）：

```json
{
  "dataset_version": "golden-v1",
  "video_id": "sample_dtl_session_01",
  "fps": 30.0,
  "duration_ms": 24000,
  "camera_angle": "DTL",
  "handedness": "right",
  "ground_truth_swings": [
    {
      "gt_id": "gt-1",
      "start_ms": 2000,
      "end_ms": 5800,
      "top_ms": 3700,
      "impact_ms": 4100,
      "label": "valid_swing",
      "ball_strike": "yes",
      "quality": "good"
    }
  ]
}
```

## 3. 驗收指標計算公式
1. **配對規則（Matching）**：預測片段 $[s_p, e_p]$ 與真值片段 $[s_g, e_g]$ 之時間交集比 $\text{IoU} = \frac{\max(0, \min(e_p, e_g) - \max(s_p, s_g))}{\max(e_p, e_g) - \min(s_p, s_g)} \ge 0.30$（或中心點距離 $\le 1500\text{ms}$）視為成功配對（True Positive, TP），一對一貪婪配對。
2. **Recall（召回率）**：$\frac{\text{TP}}{\text{TP} + \text{FN}}$，首版驗收目標 $\ge 90\%$。
3. **Precision（精確率）**：$\frac{\text{TP}}{\text{TP} + \text{FP}}$，首版驗收目標 $\ge 85\%$。
4. **邊界時間誤差中位數（Boundary Error Median）**：對所有 TP 計算 $|s_p - s_g|$ 與 $|e_p - e_g|$ 之中位數，首版目標 $\le 500\text{ms}$（0.5 秒）。

## 4. 誠信標記原則
- 在合成測試影片（Synthetic Fixtures）通過時，系統自動驗證 pipeline 與評估器邏輯正確，標記為 `SYNTHETIC_PASS`。
- 在使用者提供 **5–10 段真實 iPhone DTL 影片（至少 100 次人工可數揮桿）** 前，真實場景準確率必須誠實標記為 `NOT_VALIDATED`，不得偽稱為真實 Golden Set 已達標。
