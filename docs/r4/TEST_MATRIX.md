# Golf Swing Lab R4 — 全量自動化測試矩陣報告 (`TEST_MATRIX.md`)

- **執行日期**：2026-10-31 (Asia/Taipei)
- **分支**：`feat/r4-golf-tracer-studio`
- **Python 後端與演算法全量測試 (`.venv/bin/pytest -q`)**：**`157 passed, 2 warnings in 236.67s`**（135 項 R1–R3 測試 + 22 項 R4 新增測試 100% 通過）
- **前端單元與元件契約測試 (`npm --prefix apps/web test -- --run`)**：**`2 test files, 7 passed`**
- **前端型別與生產建置 (`npm --prefix apps/web run lint` & `npm --prefix apps/web run build`)**：**`PASS`**（0 errors，包含 `/tracer-studio/[projectId]` 路由）

---

## 1. R4 專屬測試套件明細

### 1.1 契約、數學轉換、內插與特效合成測試 ([test_tracer_contracts_and_math.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/tests/test_tracer_contracts_and_math.py)) — `13 passed`
| 測試案例名稱 | 驗證目標與反造假門檻 | 結果 |
|---|---|---|
| `test_canonical_track_point_rejects_wrist_as_clubhead` | 驗證當 `track_type=CLUB_HEAD` 且 `created_by="wrist"` 或 `note` 含 `wrist_as_head` 時，Pydantic 強制拋出 `ValidationError` | `PASS` |
| `test_canonical_track_point_rejects_fake_detector_observed` | 驗證 `interpolator` / `user` 或 `artistic_control` 標為 `detector_observed` 時強制拋出 `ValidationError` | `PASS` |
| `test_canonical_track_point_valid_raw_and_smoothed` | 驗證 `raw_observation` 與 `position_role=DISPLAY_SMOOTHED` 並存契約 | `PASS` |
| `test_frame_geometry_rotations_and_pixel_roundtrip` | 驗證 `0° / 90° / 180° / 270°` 四種旋轉角度之直立寬高與 `< 0.5px` 像素座標雙向轉換 | `PASS` |
| `test_output_layout_aspect_ratios_and_preview_export_parity` | 驗證 `original`, `16:9` (`1920x1080`), `9:16` (`1080x1920`) 縮放與黑邊置中逆轉換誤差 `< 1e-6` | `PASS` |
| `test_rational_cfr_timeline_30_and_60_fps_monotonic_and_snap` | 驗證 `30/1` 與 `60/1` 微秒格點嚴格遞增且 `snap_ms_to_pts_us` 誤差 `<= 0.5 frame` | `PASS` |
| `test_interpolation_strict_200ms_and_6frame_gate` | 驗證 `<=200ms` 且 `<=6 frames` 才允許三次樣條內插 (`source_type=INTERPOLATED`)；超過 `200ms` 嚴格回傳空列表 (`[]`) 不跨缺口硬連 | `PASS` |
| `test_artistic_ballistic_extension_marks_artistic_only` | 驗證開啟藝術延伸時，產出點 100% 標記 `source_type=ARTISTIC_ONLY` 與 `position_role=ARTISTIC_CONTROL` | `PASS` |
| `test_copy_on_write_manual_edits_preserve_parent_revision` | 驗證新增/移動/刪除點位後，`Revision 1` 原點位列表 100% 未被變動，`Revision 2` 正確套用並標記 `MANUALLY_ANNOTATED` | `PASS` |
| `test_reliability_gates_swing_and_shot_classification` | 驗證 `AUTO_TRACED` (`>=85%` 覆蓋率)、`NEEDS_REVIEW`、`AUTO_OBSERVED`、`MANUAL_ANCHORED`、`ARTISTIC_EXTENSION` 判定邏輯 | `PASS` |
| `test_render_recipe_presets_and_validation` | 驗證 6 組內建預設 (`pro_clean`, `studio_neon`, `broadcast_beam`, `sunset_gradient`, `comet_tail`, `cyber_pulse`) 結構完整性 | `PASS` |
| `test_fx_renderer_all_6_styles_and_uncertainty_dashed_band` | 驗證 `clean`, `neon`, `beam`, `gradient`, `tail`, `pulse` 6 種渲染風格與預測區段虛線/半透明帶正常繪製於直立畫布 | `PASS` |
| `test_compositor_and_preview_export_parity_under_2px_and_1frame` | 驗證 `compose_output_frame` 與 `verify_preview_export_parity` 在 `original`/`16:9`/`9:16` × `30`/`60fps` 下最大座標誤差 `< 2.0px` 且最大時間差 `<= 1.0 frame` | `PASS` |

### 1.2 Swing Tracer、Shot Tracer 與高解析串流讀取測試 ([test_tracer_engines.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/tests/test_tracer_engines.py)) — `7 passed`
| 測試案例名稱 | 驗證目標與反造假門檻 | 結果 |
|---|---|---|
| `test_bounded_frame_reader_rejects_missing_proxy_and_low_res` | 驗證遺失原片、`_proxy.mp4` 代理檔與短邊 `<600p` 低解析檔強制拋出 `SourceUnavailableError` | `PASS` |
| `test_swing_tracer_without_club_weights_never_uses_wrist_as_head_and_marks_needs_review` | 驗證無 `swingtrace-yolo11m.pt` 時退回 `shaft_geometry_estimated`、標記 `NEEDS_REVIEW`、0 點使用手腕座標且與手腕距離 `>= 0.08` | `PASS` |
| `test_swing_tracer_with_mock_clubhead_detector_achieves_auto_traced_and_phase_split` | 驗證注入高覆蓋率桿頭偵測器時達 `AUTO_TRACED`、正確切分 `backswing`/`downswing`/`follow_through` 並分離 `raw_observation` 與 `display_smoothed` | `PASS` |
| `test_swing_tracer_rejects_non_comparable_view` | 驗證非標準視角 (`OVERHEAD_DRONE`) 回傳 `NOT_COMPARABLE` (0 點) | `PASS` |
| `test_shot_tracer_stationary_ball_and_practice_swing_rejection` | 驗證空揮或僅有打擊墊原地靜止球/背景固定亮點時，100% 拒絕並回傳 `UNAVAILABLE` (0 假彈道點) | `PASS` |
| `test_shot_tracer_bidirectional_right_and_left_flight_detection` | 驗證右飛與左飛雙向球路皆可透過雙向升空 ROI 偵測升空軌跡 (`AUTO_OBSERVED` / `AUTO_ASSISTED`) | `PASS` |
| `test_artifact_cache_gzip_jsonl_roundtrip_and_sha256_verification` | 驗證 `.jsonl.gz` 壓縮軌跡儲存、SHA256 完整性驗證與篡改偵測 | `PASS` |

### 1.3 API 生命週期、安全權限 (401/403 IDOR/503)、R3 零干擾與匯出測試 ([test_tracer_api_and_security.py](file:///Users/mathew/Desktop/Golf_Swing_Lab/tests/test_tracer_api_and_security.py)) — `2 passed`
| 測試案例名稱 | 驗證目標與反造假門檻 | 結果 |
|---|---|---|
| `test_tracer_api_unauthenticated_and_feature_flag_guard` | 驗證未登入請求回傳 `401`；`GSL_ENABLE_TRACER_STUDIO=false` 時回傳 `503 TRACER_STUDIO_DISABLED` | `PASS` |
| `test_tracer_full_lifecycle_idor_isolation_r3_non_interference_and_exports` | 驗證：1. 建立專案與自動分析；2. 跨使用者 IDOR 存取全數攔截 (`403 FORBIDDEN`)；3. 手動點位編輯 (`Revision 2`) 與非破壞性回滾 (`Revision 3`)；4. Studio 錨點調整與藝術延伸**完全不改動 R3 `SwingEvent` 與 `SwingScore`**；5. 單球 `9:16 60fps mute` 與 2 球合輯 `16:9 30fps preserve` 匯出 MP4 + `.tracer.json` Sidecar 通過 `ffprobe` 與 Parity 檢驗 | `PASS` |

### 1.4 前端座標轉換與模式徽章測試 ([tracer_studio.test.ts](file:///Users/mathew/Desktop/Golf_Swing_Lab/apps/web/src/__tests__/tracer_studio.test.ts)) — `4 passed`
| 測試案例名稱 | 驗證目標 | 結果 |
|---|---|---|
| `computes identical OutputLayout and roundtrips normalized <-> canvas coordinates within 0.001px` | 驗證前端 `computeOutputLayout`、`normToCanvasPx`、`canvasPxToNorm` 與後端 Python 轉換 100% 對齊 | `PASS` |
| `snaps arbitrary PTS to nearest frame PTS and steps frame-by-frame accurately` | 驗證逐幀步進 (`-5F`, `-1F`, `+1F`, `+5F`) 與微秒時間軸吸附 | `PASS` |
| `distinguishes observed vs predicted/manual/artistic point styles honestly` | 驗證直接觀測點實線 vs 預測/內插/手動/藝術延伸點虛線樣式區分 | `PASS` |
| `formats microsecond PTS into MM:SS.mmm display string` | 驗證 `formatPtsUs` 微秒時間碼格式化 | `PASS` |
