# Golf Swing Lab — Release Candidate (RC) 產品驗收評估摘要

> 本報告由 `scripts/run_production_acceptance.py` 自行推論產生之 `production_acceptance_report.json` 100% 動態生成，並通過自動完整性斷言檢核（杜絕人工修改或文字寫死）。

## 0. 測試環境與版本證據
- **測試執行時間 (UTC)**: `2026-10-28T10:45:35.870184+00:00`
- **分析程式版本**: `2.1.0-beta`
- **測試影片**: `2分鐘.mov`
- **影片 SHA-256**: `4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9`
- **Git 分支**: `main`
- **Git Commit SHA**: `275254e9786fba948688490f8c8d7e5e0c71eb23`
- **工作樹狀態**: `clean`
- **Ground Truth 屬性**: `developer_assisted_visual_annotation`（Development Set Alignment，非外部獨立盲測）

## 1. 核心指標對比（30fps 正式 Worker Proxy vs 60fps 原片）

| 評估維度 | 30fps 正式 Worker Proxy (主要驗收路徑) | 60fps 原片 (Development Set Alignment) | 狀態 |
| :--- | :---: | :---: | :---: |
| **揮桿分類正確率** | **100.0%** (12/12) | **100.0%** (12/12) | PASS |
| **自動通過率 (Auto-Accepted)** | **91.7%** (11/12 球) | **83.3%** (10/12 球) | PASS |
| **Impact MAE** | **30.5 ms** (0.9 frames @ 30fps) | **22.2 ms** (1.3 frames @ 60fps) | PASS |
| **Top MAE** | **86.1 ms** (2.6 frames @ 30fps) | **90.4 ms** (5.4 frames @ 60fps) | PASS |
| **生理下桿符合率 (180–480ms)** | **100.0%** | **100.0%** | PASS |
| **時序異常球數 (Timing Anomaly)** | **0 球** | **0 球** | PASS |

## 2. 逐球對比與審查狀態 (30fps Proxy)

| 球號 | 標籤 | GT Top->Imp (ds) | 預測 Top->Imp (ds) | Top 偏差 | Imp 偏差 | 審查狀態 | 標記 (Flags) | 動作總分 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| #1 | `valid_swing` | 10672->10938 (266ms) | 10533->10933 (400ms) | 139ms (4.2f) | 5ms (0.1f) | `auto_accepted` | `ambient_audio_rejected` | 54.0分 |
| #2 | `valid_swing` | 25310->25610 (300ms) | 25267->25633 (366ms) | 43ms (1.3f) | 23ms (0.7f) | `auto_accepted` | `ambient_audio_rejected` | 62.1分 |
| #3 | `valid_swing` | 38178->38478 (300ms) | 38067->38433 (366ms) | 111ms (3.3f) | 45ms (1.3f) | `auto_accepted` | `none` | 59.0分 |
| #4 | `valid_swing` | 51682->51915 (233ms) | 51533->51933 (400ms) | 149ms (4.5f) | 18ms (0.5f) | `needs_review` | `audio_kinematic_conflict` | 57.5分 |
| #5 | `valid_swing` | 66435->66702 (267ms) | 66333->66733 (400ms) | 102ms (3.1f) | 31ms (0.9f) | `auto_accepted` | `ambient_audio_rejected` | 55.1分 |
| #6 | `valid_swing` | 84340->84673 (333ms) | 84367->84733 (366ms) | 27ms (0.8f) | 60ms (1.8f) | `auto_accepted` | `ambient_audio_rejected` | 49.4分 |
| #7 | `valid_swing` | 105112->105412 (300ms) | 105067->105433 (366ms) | 45ms (1.3f) | 21ms (0.6f) | `auto_accepted` | `ambient_audio_rejected` | 54.3分 |
| #8 | `valid_swing` | 110780->111147 (367ms) | 110833->111200 (367ms) | 53ms (1.6f) | 53ms (1.6f) | `auto_accepted` | `ambient_audio_rejected` | 62.2分 |
| #9 | `valid_swing` | 114780->115013 (233ms) | 114700->115067 (367ms) | 80ms (2.4f) | 54ms (1.6f) | `auto_accepted` | `none` | 68.6分 |
| #10 | `valid_swing` | 120682->120915 (233ms) | 120600->120967 (367ms) | 82ms (2.5f) | 52ms (1.6f) | `auto_accepted` | `ambient_audio_rejected` | 56.1分 |
| #11 | `valid_swing` | 125200->125467 (267ms) | 125100->125467 (367ms) | 100ms (3.0f) | 0ms (0.0f) | `auto_accepted` | `ambient_audio_rejected` | 68.5分 |
| #12 | `valid_swing` | 136502->136737 (235ms) | 136400->136733 (333ms) | 102ms (3.1f) | 4ms (0.1f) | `auto_accepted` | `none` | 66.2分 |

## 3. 正式 rank_session_swings() 排行榜結果 (30fps Proxy)

### POSTURE TOP 5 精選球
- **Rank #1**: Swing #11 (Score=84.8) — 軀幹前傾穩定 Δ=1.8°、頭部位移 r=0.131，姿勢得分 84.8 分
- **Rank #2**: Swing #9 (Score=83.1) — 軀幹前傾穩定 Δ=2.8°、頭部位移 r=0.118，姿勢得分 83.1 分
- **Rank #3**: Swing #8 (Score=78.9) — 軀幹前傾穩定 Δ=3.2°、頭部位移 r=0.128，姿勢得分 78.9 分
- **Rank #4**: Swing #12 (Score=77.9) — 軀幹前傾穩定 Δ=0.3°、頭部位移 r=0.167，姿勢得分 77.9 分
- **Rank #5**: Swing #3 (Score=77.5) — 軀幹前傾穩定 Δ=3.0°、頭部位移 r=0.141，姿勢得分 77.5 分

### TEMPO TOP 5 精選球
- **Rank #1**: Swing #10 (Score=52.8) — 上下桿時間比 2.00:1（標準 3.0:1），節奏得分 52.8 分
- **Rank #2**: Swing #12 (Score=27.6) — （本場相對最佳）上下桿時間比 1.60:1（標準 3.0:1），節奏得分 27.6 分
- **Rank #3**: Swing #11 (Score=23.8) — （本場相對最佳）上下桿時間比 1.54:1（標準 3.0:1），節奏得分 23.8 分
- **Rank #4**: Swing #7 (Score=18.8) — （本場相對最佳）上下桿時間比 1.46:1（標準 3.0:1），節奏得分 18.8 分
- **Rank #5**: Swing #1 (Score=15.0) — （本場相對最佳）上下桿時間比 1.33:1（標準 3.0:1），節奏得分 15.0 分

### FINISH TOP 5 精選球
- **Rank #1**: Swing #9 (Score=90.4) — 收桿停頓 2133ms、晃動比 0.065，收桿得分 90.4 分
- **Rank #2**: Swing #7 (Score=86.6) — 收桿停頓 2333ms、晃動比 0.074，收桿得分 86.6 分
- **Rank #3**: Swing #10 (Score=85.2) — 收桿停頓 2200ms、晃動比 0.078，收桿得分 85.2 分
- **Rank #4**: Swing #8 (Score=79.9) — 收桿停頓 2200ms、晃動比 0.091，收桿得分 79.9 分
- **Rank #5**: Swing #12 (Score=77.4) — 收桿停頓 2334ms、晃動比 0.098，收桿得分 77.4 分

### IG TOP 5 精選球
- **Rank #1**: Swing #10 (Score=84.4) — 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 84.4 分
- **Rank #2**: Swing #7 (Score=77.4) — 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 77.4 分
- **Rank #3**: Swing #9 (Score=77.2) — 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 77.2 分
- **Rank #4**: Swing #12 (Score=76.1) — 畫面完整度 99.8 分、收桿平穩，IG 吸睛分 76.1 分
- **Rank #5**: Swing #11 (Score=75.8) — 畫面完整度 99.9 分、收桿平穩，IG 吸睛分 75.8 分

