/**
 * apps/web/src/lib/syncEngine.ts — 揮桿時間同步引擎與等比例畫面對齊
 *
 * 核心特色：
 * 1. 支援兩種明確區分的同步播放模式：
 *    - Real-Time (真實時間模式)：保留兩人各自真實節奏，依選定錨點 (Address/Top/Impact/Finish) 時間對齊
 *    - Phase-Synchronized (階段分段線性模式)：依揮桿物理階段正規化對應，使關鍵動作同時呈現 (明確標明非真實節奏)
 * 2. 等比例畫面對齊 (Auto-Framing)：
 *    - 依據身體骨架/站姿長度計算等比例 Scale，保留長寬比不拉伸
 *    - 支援手動 Zoom、OffsetX、OffsetY 微調
 * 3. 視角相容性檢核：
 *    - 若攝影角度不符 (如 DTL vs Close-up)，產生客觀警示
 */

export type SyncMode = "real_time" | "phase_sync";
export type SyncAnchor = "impact" | "top" | "address" | "finish";
export type ComparisonLayout = "side_by_side" | "stacked" | "single_user" | "single_ref" | "ghost_overlay";

export interface SwingTimingTimeline {
  startMs: number;
  endMs: number;
  addressMs: number;
  takeawayMs: number;
  topMs: number;
  downswingMs: number;
  impactMs: number;
  followThroughMs: number;
  finishMs: number;
}

export interface FramingCalibration {
  scale: number;
  zoom: number;
  offsetX: number;
  offsetY: number;
  offset_x?: number;
  offset_y?: number;
}

export class SwingSynchronizationEngine {
  /**
   * 根據選定錨點計算 Real-Time 模式下，參考影片對應的使用者影片時間碼
   * 公式：refTimeMs = anchorRefMs + (userTimeMs - anchorUserMs) + manualOffsetMs
   */
  static computeRealTimeRefMs(
    userCurrentMs: number,
    userTimeline: SwingTimingTimeline,
    refTimeline: SwingTimingTimeline,
    anchor: SyncAnchor = "impact",
    manualOffsetMs: number = 0
  ): number {
    const userAnchorMs = this.getAnchorTimeMs(userTimeline, anchor);
    const refAnchorMs = this.getAnchorTimeMs(refTimeline, anchor);

    const deltaFromAnchor = userCurrentMs - userAnchorMs;
    const computedRefMs = refAnchorMs + deltaFromAnchor + manualOffsetMs;

    // 限制在參考影片合法時間範圍內
    return Math.max(refTimeline.startMs, Math.min(refTimeline.endMs, computedRefMs));
  }

  /**
   * 取得指定錨點的時間碼
   */
  static getAnchorTimeMs(timeline: SwingTimingTimeline, anchor: SyncAnchor): number {
    switch (anchor) {
      case "address":
        return timeline.addressMs;
      case "top":
        return timeline.topMs;
      case "finish":
        return timeline.finishMs;
      case "impact":
      default:
        return timeline.impactMs;
    }
  }

  /**
   * Phase-Synchronized (階段分段線性同步模式)：
   * 將使用者當前動作進度映射至參考影片對應階段的相同相對進度
   */
  static computePhaseSyncRefMs(
    userCurrentMs: number,
    userTimeline: SwingTimingTimeline,
    refTimeline: SwingTimingTimeline,
    manualOffsetMs: number = 0
  ): number {
    // 定義 5 大分段區間 (分段錨點)
    const userStages = [
      userTimeline.startMs,
      userTimeline.addressMs,
      userTimeline.topMs,
      userTimeline.impactMs,
      userTimeline.finishMs,
      userTimeline.endMs,
    ];

    const refStages = [
      refTimeline.startMs,
      refTimeline.addressMs,
      refTimeline.topMs,
      refTimeline.impactMs,
      refTimeline.finishMs,
      refTimeline.endMs,
    ];

    // 尋找當前使用者所在的階段索引
    let stageIdx = 0;
    for (let i = 0; i < userStages.length - 1; i++) {
      if (userCurrentMs >= userStages[i] && userCurrentMs <= userStages[i + 1]) {
        stageIdx = i;
        break;
      }
      if (userCurrentMs > userStages[i + 1]) {
        stageIdx = i;
      }
    }

    const uStart = userStages[stageIdx];
    const uEnd = userStages[stageIdx + 1];
    const uSpan = Math.max(1, uEnd - uStart);

    // 計算本階段內的線性進度 [0.0, 1.0]
    const progress = Math.max(0, Math.min(1, (userCurrentMs - uStart) / uSpan));

    // 映射至參考影片對應階段
    const rStart = refStages[stageIdx];
    const rEnd = refStages[stageIdx + 1];
    const rSpan = rEnd - rStart;

    const mappedRefMs = rStart + progress * rSpan + manualOffsetMs;
    return Math.max(refTimeline.startMs, Math.min(refTimeline.endMs, mappedRefMs));
  }

  /**
   * 自動計算畫面對齊參數 (Auto-Framing)：
   * 保留長寬比，以人體軀幹長度為基準進行等比例縮放與置中偏移
   */
  static computeAutoFraming(
    userTorsoLength: number = 115,
    refTorsoLength: number = 115
  ): { scale: number; offsetX: number; offsetY: number } {
    if (refTorsoLength <= 10) return { scale: 1.0, offsetX: 0, offsetY: 0 };
    // 依據軀幹比例放大或縮小參考影片，使兩者人體大小視覺一致
    const scale = Math.max(0.6, Math.min(1.8, userTorsoLength / refTorsoLength));
    return {
      scale: Number(scale.toFixed(2)),
      offsetX: 0,
      offsetY: 0,
    };
  }

  /**
   * 檢核相機視角相容性
   */
  static checkAngleCompatibility(
    userAngle: string = "DTL",
    refAngle: string = "DTL"
  ): { compatible: boolean; warning?: string } {
    const u = userAngle.toUpperCase();
    const r = refAngle.toUpperCase();
    if (u === r) {
      return { compatible: true };
    }
    if (r === "CLOSE_UP" || u === "CLOSE_UP") {
      return {
        compatible: false,
        warning: "示範影片為打擊區桿頭特寫，非全身 DTL 鏡頭，不可用於比較身體 2D 關節角度。",
      };
    }
    return {
      compatible: false,
      warning: `相機視角差異過大 (${userAngle} vs ${refAngle})，無法精準比較 2D 身體姿態角度。`,
    };
  }
}
