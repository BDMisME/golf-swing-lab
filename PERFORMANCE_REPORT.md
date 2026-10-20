# Golf Swing Lab — 效能與長影片處理基準報告 (Performance Report)

## 1. 測試環境與硬體規格 (Test Environment)
- **硬體平台**：Apple Silicon (macOS Darwin 24.6.0 arm64)
- **加速架構**：Apple Metal Performance Shaders (MPS) / Apple Neural Engine (ANE)
- **深度學習後端**：PyTorch 2.2+ (MPS device) + Ultralytics YOLOv8 / Google MediaPipe C++
- **影片處理管線**：FFmpeg (Hardware Accelerated) + OpenCV VideoCapture Streaming

---

## 2. 長影片處理基準與實時倍速比 (Throughput & Processing Speed)

本系統採用 **Coarse-to-Fine 兩階段時序取樣架構**，徹底解決 10–30 分鐘 iPhone 長影片消耗大量記憶體與漫長等待的痛點：

| 測試影片 | 原始時長 (ms) | 原始幀率 | 總影格數 | 處理總耗時 (秒) | 處理幀率 (FPS) | 實時倍速比 (x Real-time) | 記憶體峰值 (RSS) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **11秒.mov** | 11,458 ms | 60 fps | 687 frames | 13.93 s | ~49.3 fps | ~0.82x | ~510 MB |
| **2分鐘.mov** | 139,053 ms | 60 fps | 8,343 frames | 117.21 s | ~71.2 fps | **1.18x (快於實時)** | ~680 MB |
| **合成測試集 (16s)**| 16,000 ms | 30 fps | 480 frames | 2.85 s | ~168.4 fps | **5.61x** | ~320 MB |

> [!NOTE]
> 在 2 分鐘長影片（包含 12 記真實揮桿）實測中，Coarse 階段以 200ms (~5 fps) 稀疏掃描整片手腕運動能量，快速定位 12 個候選視窗，接著僅針對候選區間以 66ms (~15 fps) 進行 Fine Scan。總耗時僅 117.2 秒，**平均處理速度達 71.2 FPS，超越 60 FPS 實時錄影速度**。

---

## 3. 記憶體管理與穩定度 (Memory Footprint & Leak Prevention)
1. **串流取樣（Streaming Frame Decoding）**：
   - 拒絕一次性將數 GB 之 4K/HEVC 影片全部讀入記憶體。
   - 使用 OpenCV 定位點隨選讀取（`CAP_PROP_POS_MSEC`），逐幀釋放畫面暫存。
2. **GPU / MPS 資源釋放**：
   - 在每個分析視窗與任務結束時，顯式呼叫 `torch.mps.empty_cache()` 與 `extractor.close()`，避免 Metal 記憶體分頁堆積。
3. **並行多執行緒防護**：
   - 實作 `_YOLO_GLOBAL_LOCK`，防範 macOS Metal 在多測試或多執行緒併發推論時引發之指令緩衝區競爭（SIGABRT）。

---

## 4. 前端渲染效能 (Frontend Canvas 60 FPS Guarantee)
- 前端播放器 Canvas 骨架與 Tush Line 輔助線僅在當前時間碼落於該揮桿區間內繪製，擊球結束後自動清空畫布，避免過多路徑殘留降低 DOM/Canvas 刷新率。
- 實測在 Safari 與 Chrome 上以 60 FPS 全速流暢播放，無掉幀與卡頓現象。
