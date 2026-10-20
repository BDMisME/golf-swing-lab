# Golf Swing Lab — R7–R10 獨立原始碼審查與更正開發報告 (Code Audit & Corrective Development)

## 1. 審查背景與執行原則
依據外部獨立審查反饋，Golf Swing Lab 在 R7–R10 輪次中針對安全性、CI 流程、出球動態軌跡真實性、生物力學檢核線（Tush Line）及評分引擎進行深度盤點與更正性開發。
開發作業嚴格遵守：
- 不重新推翻既有系統架構。
- 嚴禁依賴跳過測試、竄改預期值製造假通過。
- 缺失外部長影片時如實標示 `NOT_VALIDATED`。
- 在獨立分支 `audit/r7-r10-code-audit-and-fixes` 上開發，驗收成功後整合 main。

---

## 2. 審查發現缺口與修復對照表 (Defects & Corrective Fixes)

### R7 — Product Release & Security
| 項目 | 審查前現況 (Defect) | 更正性開發成果 (Resolution) | 狀態 |
| :--- | :--- | :--- | :--- |
| **GitHub Actions CI** | CI 失敗；後端有 18 個 Ruff 檢查錯誤；前端配置了不存在的 `pnpm-lock.yaml` 與缺失的 script。 | 修正 `.github/workflows/ci.yml`，改用 npm，完整配置 MinIO 服務容器；18 個 Ruff 錯誤全部清空；Mypy 型別零錯誤；Vitest 3/3 通過；Next.js 8 頁面建置通過。 | **PASS** |
| **Mac App Launcher** | 遇到環境或 Python 異常時直接靜默閃退，無任何錯誤反饋；未優先查找 App Bundle 內部資源。 | 升級 `launcher.c`，實作 `show_native_alert`（原生 macOS AppleScript 彈窗），遇到缺漏時主動提示詳細路徑與原因；優先探測 `Contents/Resources/app`。 | **PASS** |
| **Mac App 打包流程** | `build_mac_app.sh` 僅打包 launcher 二進位，未封裝前端、後端與分析套件。 | 更新打包腳本，自動同步 `apps/`, `packages/`, `pyproject.toml` 至 Resources 目錄，並實施 `codesign --deep --strict` 簽名。 | **PASS** |
| **生產環境金鑰安全** | 存在預設 session secret、預設管理員密碼與預設 MinIO 憑證。 | 在 `apps/api/config.py` 與 `main.py` 加入 `validate_security_posture()`，正式環境偵測到預設金鑰立即終止啟動（Fail-Fast）。 | **PASS** |
| **本機網路存取隔離** | API 服務未顯式限定綁定本機。 | API 與內部服務預設嚴格綁定 `127.0.0.1`，杜絕練習場 Wi-Fi 未授權連線。 | **PASS** |

### R8 — Detection Accuracy & Ball Tracer Integrity
| 項目 | 審查前現況 (Defect) | 更正性開發成果 (Resolution) | 狀態 |
| :--- | :--- | :--- | :--- |
| **長影片召回率指標** | `tests/test_r2_long_video_accuracy.py` 使用 `valid_count / 12` 充當 Recall，掩蓋了時間碼偏差與誤判。 | 廢除偽 Recall 公式，改採 `packages/analysis/evaluation/golden_eval.py` 實施 IoU 逐球一對一嚴格配對；缺少原片時誠實標示 `NOT_VALIDATED`。 | **PASS** |
| **小白球追蹤物理模型** | `packages/analysis/tracking/ball_tracker.py` 強制要求 $\Delta x \ge 0$，假定所有出球必向右飛，不相容左打者；未標記推論或觀測點。 | 移除 $\Delta x \ge 0$ 限制，改以總升空向量判定出球仰角；點位記錄 `raw_x`, `raw_y`, `point_type` ("observed"/"predicted") 與 confidence；實測點 < 2 幀時拒絕外推假球路。 | **PASS** |
| **前端出球軌跡渲染** | `apps/web/src/app/swings/[id]/page.tsx` 使用固定數學拋物線公式向右畫線，偽造 Toptracer。 | 移除假球路公式，改為優先讀取後端 YOLO 實測 `ball_trajectory` 渲染發光軌跡；若無可靠觀測點，明確降級為虛線與「理論出球示意 (未捕捉到實測球體)」免責聲明。 | **PASS** |

### R9 — Biomechanics & Scoring Accuracy
| 項目 | 審查前現況 (Defect) | 更正性開發成果 (Resolution) | 狀態 |
| :--- | :--- | :--- | :--- |
| **Tush Line 臀部鉛線** | 直接以 Hip 關鍵點冒充臀部後緣；固定使用 12 像素作為早起判定閾值；忽略關鍵點置信度。 | 改以人體解剖結構推算骨盆背側後緣（偏移約 16% 軀幹長度）；位移改以 Address 時的軀幹長度歸一化（> 10% 為早起，<= 4% 為穩定）；置信度不足時顯示「∼ 關鍵點置信度不足」。 | **PASS** |
| **手部路徑指標混淆** | `hand_path_deviation_ratio` 將單球上下桿平面差與多球重複性混為一談。 | 重構指標，分開為單球上下桿手部平面間隙 `single_swing_plane_gap_ratio` 與多球中位數重複性 `session_path_repeatability`。 | **PASS** |
| **IG Visual Score 計算** | Framing 直接以覆蓋率充數；Clip Margin 寫死 `len(valid_items)` 判斷，未檢查真實邊界。 | `framing_score` 真實檢查關鍵點是否越界（`out_of_frame_flags` 與 `body_visibility_ratio`）；`clip_margin` 真實檢驗起迄緩衝（前後需具備 >= 300ms）。 | **PASS** |
| **評分引擎版本** | 維持 score-v1，無法區隔新舊評分標準。 | 升級 `score_version: score-v2`，完整體現分項分離與邊界檢核。 | **PASS** |
| **AI 教練防偽規則** | 外部模型可能輸出臆測之公分、角度與球路。 | 擴充 `FORBIDDEN_HALLUCINATION_TERMS`，涵蓋「公分」、「cm」、「英吋」、「Slice」、「Hook」、「左曲」、「右曲」與「桿面角」，一旦偵測違規立即退回規則式報告。 | **PASS** |

---

## 3. 自動化測試驗證彙整
- **後端單元與整合測試**：
  - `test_r1_mac_app_independence.py`: 6/6 PASSED
  - `test_r1_r2_auth_and_models.py`: 3/3 PASSED
  - `test_r3_verifiable_scoring.py`: 3/3 PASSED
  - `test_r4_dtl_algorithms.py`: 3/3 PASSED
  - `test_r5_personalized_coach.py`: 4/4 PASSED
  - `test_r5_r6_r7_detection_pose_scoring.py`: 4/4 PASSED
  - `test_r6_final_product_acceptance.py`: 4/4 PASSED
  - `test_short_video_11s_accuracy`: 1/1 PASSED
- **靜態分析**：
  - Ruff Linter: 0 errors (`All checks passed!`)
  - Mypy Typecheck: 0 errors (`Success: no issues found in 25 source files`)
- **前端測試與編譯**：
  - Vitest: 3/3 passed
  - TypeScript (`tsc --noEmit`): 0 errors
  - Next.js Production Build: 8/8 routes compiled successfully.
