# R4 — Golf Tracer Studio 開源研究與採用決策表

> 文件截至：2026-10-31。此文是 Gemini 4 Argon 開發的**起始研究，不是免查證引用許可**。任何下載、移植、打包前，必須比對特定 commit、LICENSE、模型權重來源、訓練資料集與依賴鏈。GitHub repo 是可供研究的候選，不等於可以在高爾夫專案直接跑通。

## 1. 評估原則

1. **已存在的 Golf Swing Lab 程式優先**。最直接且最低成本的路徑是擴充 `packages/analysis/tracking/ball_tracker.py`、`packages/analysis/detection/scanner.py`，在新的 Studio 專屬路徑中使用，不再拆掉現有評分／Impact feedback。
2. 不能拿單鏡頭 30fps 的 2D 影像聲稱 3D Carry、Spin 或球速精確量測；選源時特別排除依模擬出的漂亮全程飛行線冒充實際球軌。
3. 過度引入模型會造成 Mac App 安裝龐大、MPS 相容問題與版權風險。每新增 1 個外部依賴，必須先說明比已存在 OpenCV 做法的可測量增益。
4. 模型 weights 不能跟代碼混為一談；若無權下載或模型 gated，就將自動功能列阻擋，不能轉為假 detector。

## 2. 核心推薦選型

### A. `nishsm/golf-club-detection-swingtrace` — Swing Tracer 研究優先

- GitHub：https://github.com/nishsm/golf-club-detection-swingtrace
- 權重／模型卡：https://huggingface.co/nishsm/golf-club-detection-swingtrace
- 專案：YOLO11m，class 對應 shaft、club head、hands；提供盒框與重建桿頭路徑的程式。目標視角與使用者 DTL 固定手機拍攝高度相關。
- 作者公開結果（**非本專案實測**）：在 7 段未見過手機影片、3018 frames，直接 clubhead detection 71.6%，clubhead 或 shaft 93.4%。驗證集 mAP@50 0.918，但作者自己提醒訓練/驗證有相似相鄰影格洩漏，因此不可直接用作產品性能承諾。
- 缺陷：高速揮桿桿頭模糊、細亮條可能誤判球桿、shaft 近水平／垂直時從框的角推 head 失準；繪圖實作把整段影格放 RAM，不適合 30 分鐘影片，**只能對每球 clip 使用或重新做 streaming**。
- 授權：作者模型卡標示 AGPL-3.0（Ultralytics YOLO11）。權重在 HF 顯示 gated，要同意條件才可下載；不能假設安裝指令在無登入環境成功。
- 採用判定：`RESEARCH_FIRST`，完成 license gate、Mac MPS/CPU benchmark 和真實手機短片 head point audit 後，才可以做 production adapter。不可在未核准再散布規範前將 40MB 權重加入 Git LFS／發行包。
- 替代方案：自行使用 OpenCV 桿身線段＋端點估計並逐點標 `shaft_geometry_estimated`，或合法訓練 Apache-2.0 RF-DETR 模型；如不能取得可靠 clubhead 視覺模型，必須 `BLOCKED_SWING_AUTO`。

### B. `opencv/opencv` — 最優先利用現有依賴

- GitHub：https://github.com/opencv/opencv
- License：https://opencv.org/license/
- OpenCV 4.5+ Apache-2.0。現有套件 `opencv-python-headless` 已安裝；用 `calcOpticalFlowPyrLK`、KalmanFilter、RANSAC、homography、Canny/HoughLinesP、OpenCV RGBA drawing / Gaussian blur 就能做第一版。
- 必須用來源 PTS delta 更新 motion model；影像偵測 confidence 不代表 motion extrapolation confidence。需跟既有 `KalmanBallTracker` 對照，防止把經過平滑的座標誤貼 observed。
- 採用判定：`PRIMARY`。僅在真實 benchmark 看到關聯增益不足時才加入新 library。

### C. `tryolabs/norfair` — 多候選關聯／追蹤器可選

- GitHub：https://github.com/tryolabs/norfair
- License：https://github.com/tryolabs/norfair/blob/master/LICENSE（BSD-3-Clause）
- 用途：一個小白球從 detector candidates 中做時間關聯和 identity track；能幫忙處理不同類型的 detector。
- 注意：單顆球＋球桿的場景可能直接使用 OpenCV state tracker 更簡單，Norfair 未必能解決超小球消失問題。
- 採用判定：`OPTIONAL_MEASURED`。只有透過 ablation test 證明比現有 Kalman/data association 更好才導入。

### D. `facebookresearch/sam2` — 互動追蹤可研究，但非必要主流程

- GitHub：https://github.com/facebookresearch/sam2
- 產品研究：https://ai.meta.com/research/sam2/
- License：SAM2 code/weights Apache-2.0（依原始專案），個別資料集另確認。
- 能力：promptable frame point/box → video mask propagation；能讓人工點位提供次序追蹤。快速消失的小白球和薄桿身可能不足以可靠分割。
- 成本：需 Torch、模型權重、MPS 推論，包體與記憶體成本較高；必須 Apple Silicon 實測。
- 採用判定：`OPTIONAL_LATER`，只有在 real benchmark 明顯改善 manual-assisted recovery 時導入；主流程不可依賴。

### E. `roboflow/rf-detr` — 合法替代桿頭 detector 自訓基礎

- GitHub：https://github.com/roboflow/rf-detr
- License 詳情：https://roboflow.com/licensing（2026-10-27 更新）
- RF-DETR Nano–Large 的特定套件/模型權重為 Apache-2.0；Plus models（Atto/Femto/Pico/XL/2XL）另有 PML 授權，不能因為 package 名稱相同就宣稱全部 Apache。
- COCO 預訓練不是高爾夫 clubhead 專用 detector，**沒有專項訓練資料與訓練/驗證結果不等於可用**。
- 採用判定：`LEGAL_FALLBACK`。若 AGPL 有不被接受的未來發行風險且能取得合法標註資料，可選用進行 clubhead、shaft 兩類微調。要呈報實際训练成本、MPS 可用性和推論時間。

## 3. 畫面編輯與影音輸出

### F. `konvajs/konva` ＋ `konvajs/react-konva`

- Github：https://github.com/konvajs/konva ，https://github.com/konvajs/react-konva
- License：MIT。
- React Studio 用途：分層畫布、縮放/拖曳 point、Bezier handles、undo/redo 呈現、時間軸疊圖。畫面上的動畫以真實 source PTS 同步，不靠 requestAnimationFrame 跑過多少次推進時鐘。
- 版本注意：react-konva 最新相容 React 19 的 peer dependency 要依目前 `apps/web/package.json` 真實 React 版本選擇，不能誤安裝 incompat package。
- 採用判定：`LIKELY_UI_CHOICE`；若發現 WebKit 性能不穩，原生 Canvas + pointer events 可替代，核心 geometry 不變。

### G. `PyAV-Org/PyAV`

- GitHub：https://github.com/PyAV-Org/PyAV
- License：BSD-3-Clause（專案 pyproject 指定）；Python 3.12 新版支援。
- 用途：更直接使用 FFmpeg frame.pts/time_base 實現精準 VFR/HEVC/b-frame timing，避免 OpenCV `CAP_PROP_POS_MSEC` 偏差。
- 採用判定：`BENCHMARK_FIRST`，先用现有 FFprobe/FFmpeg 解碼證據再比較 PyAV；若包裝 Apple Silicon 依賴有問題，不能為了 PTS 讓整個 App 不能啟動。

### H. `FFmpeg/FFmpeg`

- GitHub：https://github.com/FFmpeg/FFmpeg
- License：https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md 、https://ffmpeg.org/legal.html
- 現有 exporter 已用 FFmpeg，主力編碼/trim/audio/concat。注意 FFmpeg build 有 LGPL 與 GPL 差別；`libx264` 會使完整 FFmpeg binary 的授權政策受到 GPL 影響，未來打包再散布需確認。
- 應做：使用 FFprobe 驗證 codec/fps/rotation/audio/duration；保持 FFmpeg command arguments array（禁止 shell 參數注入）；採 deterministic RGBA overlay pipeline。
- 採用判定：`PRIMARY_EXPORT`，無須引進雲端影片輸出服務。

### I. `mifi/editly`

- GitHub：https://github.com/mifi/editly
- License：MIT。
- 用途：研究宣告式影片/片段結構、轉場 API、疊圖 recipe 的設計思路。
- 缺點：Node + native headless GL 與 canvas 相依較複雜，macOS 單機打包可能增加故障面。
- 採用判定：`DESIGN_REFERENCE_ONLY`，除非能提出它比 existing Python/FFmpeg 更好的真實效能/簡化證據。

## 4. Golf Shot Tracer 參考，但不得冒用為真實觀測

### J. `jonibek95/GolfShotTracer`

- GitHub：https://github.com/jonibek95/GolfShotTracer
- 內容：YOLOv5 ball detection、初始速度與角度估計、3D 飛行物理模擬、曲線插值與 OpenCV 畫線。
- 長處：可參考 rendering/demo、使用者對 tracer 影片的表現期待。
- 致命差異：本產品只有單鏡頭影片，原始測量和後期模擬應分離，**不可把模擬物理球路直接當 observed flight**。
- License：本輪未確認完整 LICENSE 條款；**在核實前一律不得複製程式碼或模型**。
- 採用判定：`VISUAL_IDEA_ONLY`。

### K. `mikel-brostrom/boxmot`

- GitHub：https://github.com/mikel-brostrom/boxmot
- License：AGPL-3.0。具備各類 MOT algorithms、可插拔 tracker 架構，但明顯超出單球個人 app 所需。
- 採用判定：`ARCHITECTURAL_REFERENCE_ONLY`。不要為了有開源套件就把大量 ReID/torch stack 加進來。

## 5. 依優先序的組合推薦

```text
P0 必要:
  Existing Golf Swing Lab (R3) + OpenCV + FFprobe/FFmpeg + local FastAPI + Postgres
P1 推薦:
  Konva + react-konva for frame-by-frame correction editor
P1 Swing 檢驗:
  SwingTrace YOLO11m as isolated, license-reviewed prototype adapter
P2 若已證實較佳:
  Norfair for association / PyAV for PTS / SAM2 for promptable correction
P2 合法模型替代:
  RF-DETR Apache-designated weights + legitimate separately labeled dataset
不建議直接主線整合:
  GolfShotTracer 的 3D 模擬球路；BoxMOT 的大型 tracker stack；任何未知 LICENSE 模型
```

## 6. Gemini 開發前要實際跑的 License / Feasibility Checklist

- [ ] 記錄依賴 git commit/tag 和下載日期，而非 `pip install git+main` 漂浮依賴。
- [ ] 打開真正 LICENSE 與 NOTICE，查 license scope（code / weights / training dataset / model runtime / output video / distribution）。
- [ ] 對 SwingTrace 實際下載權限進行合法測試；若 gated，記錄是否需要用戶同意，不能幫使用者繞過。
- [ ] 不將原片提交上游庫、Hub、公共網路。
- [ ] 有/無 SwingTrace 模型的兩種 Mac start 測試。
- [ ] 一個未見過的用戶真實 swing clip 用四處典型模糊影格逐點檢查，並與手動標註比較。
- [ ] 對每個依賴做 CPU/MPS latency、peak RAM、installer size 測量。
- [ ] 若結論為禁止／無法整合，維持 provider adapter 並以 `BLOCKED` 明確說明，而非偷換假數據。

## 7. 原始證據連結（新 Session 請重新查核）

1. SwingTrace source/model/AGPL：https://huggingface.co/nishsm/golf-club-detection-swingtrace
2. OpenCV license：https://opencv.org/license/
3. Norfair BSD：https://github.com/tryolabs/norfair/blob/master/LICENSE
4. Meta SAM2 Apache：https://ai.meta.com/research/sam2/
5. RF-DETR component license：https://github.com/roboflow/rf-detr ; https://roboflow.com/licensing
6. Konva / React Konva MIT：https://github.com/konvajs/konva ; https://github.com/konvajs/react-konva
7. PyAV BSD：https://github.com/PyAV-Org/PyAV/blob/master/pyproject.toml
8. FFmpeg LGPL/GPL：https://github.com/FFmpeg/FFmpeg/blob/master/LICENSE.md
9. Editly MIT：https://github.com/mifi/editly
10. GolfShotTracer：https://github.com/jonibek95/GolfShotTracer
11. BoxMOT AGPL：https://github.com/mikel-brostrom/boxmot

**結論：R4 真正的差異化不是「把所有 GitHub 模型都安裝」，而是「完整、可編輯、證據分級、影片時間碼正確且能在 Mac App 交付」的本機工作流程。**
