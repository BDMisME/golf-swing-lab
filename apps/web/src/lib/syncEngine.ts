/**
 * apps/web/src/lib/syncEngine.ts — 揮桿時間同步引擎與等比例畫面對齊
 *
 * 核心功能：
 * 1. 雙影片連續播放時鐘同步與平滑漂移校正 (PlaybackDriftController)：
 *    - 拒絕每影格強制 seek，兩段影片真正同時調用 play() 播放
 *    - 微幅漂移 (<= 60ms)：無感保持，零卡頓
 *    - 中度漂移 (60ms ~ 250ms)：以 playbackRate (±8%) 微幅動態平滑追趕，無黑畫面
 *    - 重大偏差 (> 250ms，如拖曳進度條或跳轉)：執行單次精準 hard seek
 * 2. 階段同步模式 (Phase Sync Mode)：
 *    - 嚴格驗證原影片與參考影片事件完整性與時序單調性 (Address < Top < Impact < Finish)
 *    - 缺失事件時安全降級並警示，嚴禁以百分比偷偷假裝已對齊
 *    - 明確標記時間正規化比較，非真實揮桿速度
 * 3. 2D 姿態驅動等比例畫面對齊 (Auto-Framing)：
 *    - 真正從雙方 MediaPipe 2D Pose 計算真實軀幹長度 (肩中心至髖中心) 與骨盆中心
 *    - 等比例縮放，保留原始長寬比，不拉伸畫面
 *    - 姿態資料不足時明確降級為手動校準，不偽稱自動對齊成功
 *    - 視角不相容 (如 close_up 特寫) 明確發出警示
 */

export type SyncMode = "real_time" | "phase_sync";
export type SyncAnchor = "impact" | "top" | "address" | "finish";
export type ComparisonLayout = "side_by_side" | "stacked" | "single_user" | "single_ref" | "ghost_overlay";

export interface NormalizedLandmark {
  x: number;
  y: number;
  z?: number;
  visibility?: number;
}

export type PoseLandmarks = Record<string, NormalizedLandmark>;

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

export interface AutoFramingResult {
  scale: number;
  offsetX: number;
  offsetY: number;
  status: "auto_computed" | "manual_required" | "incompatible_angle";
  warning?: string;
  userTorsoLength?: number;
  refTorsoLength?: number;
}

export interface DriftCorrectionResult {
  action: "none" | "adjust_rate" | "hard_seek";
  targetRefTimeSec: number;
  recommendedPlaybackRate: number;
  driftMs: number;
}

export class PlaybackDriftController {
  static DRIFT_TOLERANCE_MS = 60; // 60ms 內無需調整
  static DRIFT_SMOOTH_SEEK_MS = 250; // 60ms~250ms 以微幅調速平滑修正

  /**
   * 評估參考影片相較於理論目標時間的漂移量，給出平滑調速或單次 seek 決策
   */
  static evaluateDrift(
    refCurrentSec: number,
    expectedRefSec: number,
    basePlaybackRate: number = 1.0
  ): DriftCorrectionResult {
    const driftSec = refCurrentSec - expectedRefSec;
    const driftMs = Math.round(driftSec * 1000);

    // 1. 微幅漂移區間：人眼幾乎無感，維持基準速率，絕不 seek
    if (Math.abs(driftMs) <= this.DRIFT_TOLERANCE_MS) {
      return {
        action: "none",
        targetRefTimeSec: expectedRefSec,
        recommendedPlaybackRate: basePlaybackRate,
        driftMs,
      };
    }

    // 2. 中度漂移區間：微幅調整播放速度 (±8%)，平滑追趕，不破壞解碼 buffer
    if (Math.abs(driftMs) <= this.DRIFT_SMOOTH_SEEK_MS) {
      const rateAdjustment = driftMs < 0 ? 1.08 : 0.92;
      return {
        action: "adjust_rate",
        targetRefTimeSec: expectedRefSec,
        recommendedPlaybackRate: Number((basePlaybackRate * rateAdjustment).toFixed(2)),
        driftMs,
      };
    }

    // 3. 重大偏差區間 (> 250ms)：通常為使用者主動 seek，執行單次精確硬同步
    return {
      action: "hard_seek",
      targetRefTimeSec: expectedRefSec,
      recommendedPlaybackRate: basePlaybackRate,
      driftMs,
    };
  }
}

export class SwingSynchronizationEngine {
  /**
   * 驗證階段同步時序之合法性
   */
  static validatePhaseTimeline(timeline: SwingTimingTimeline): { valid: boolean; reason?: string } {
    if (!timeline) return { valid: false, reason: "時間軸不存在" };
    const { startMs, addressMs, topMs, impactMs, finishMs, endMs } = timeline;

    if (addressMs <= 0 || topMs <= 0 || impactMs <= 0) {
      return { valid: false, reason: "缺少核心動作事件 (Address, Top 或 Impact)" };
    }

    if (!(startMs <= addressMs && addressMs < topMs && topMs < impactMs)) {
      return { valid: false, reason: "動作事件時序異常 (Top 必須晚於 Address 且早於 Impact)" };
    }

    if (finishMs > 0 && impactMs > finishMs) {
      return { valid: false, reason: "收桿時間 (Finish) 必須晚於擊球 (Impact)" };
    }

    return { valid: true };
  }

  /**
   * 根據選定錨點計算 Real-Time 自然時間模式下，參考影片對應的使用者影片時間碼
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
        return timeline.finishMs > 0 ? timeline.finishMs : timeline.impactMs + 800;
      case "impact":
      default:
        return timeline.impactMs;
    }
  }

  /**
   * Phase-Synchronized (階段分段線性同步模式)：
   * 依據 5 大分段錨點進行分段線性進度映射
   */
  static computePhaseSyncRefMs(
    userCurrentMs: number,
    userTimeline: SwingTimingTimeline,
    refTimeline: SwingTimingTimeline,
    manualOffsetMs: number = 0
  ): number {
    const userStages = [
      userTimeline.startMs,
      userTimeline.addressMs,
      userTimeline.topMs,
      userTimeline.impactMs,
      userTimeline.finishMs > 0 ? userTimeline.finishMs : userTimeline.impactMs + 800,
      userTimeline.endMs,
    ];

    const refStages = [
      refTimeline.startMs,
      refTimeline.addressMs,
      refTimeline.topMs,
      refTimeline.impactMs,
      refTimeline.finishMs > 0 ? refTimeline.finishMs : refTimeline.impactMs + 800,
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
   * 真正從雙方真實 2D Pose 關鍵點計算等比例畫面對齊參數 (Auto-Framing)
   */
  static computeAutoFramingFromPose(
    userPose?: PoseLandmarks | null,
    refPose?: PoseLandmarks | null,
    userAngle: string = "DTL",
    refAngle: string = "DTL",
    containerWidth: number = 640,
    containerHeight: number = 360
  ): AutoFramingResult {
    // 1. 檢核相機視角
    const angleCheck = this.checkAngleCompatibility(userAngle, refAngle);
    if (!angleCheck.compatible) {
      return {
        scale: 1.0,
        offsetX: 0,
        offsetY: 0,
        status: "incompatible_angle",
        warning: angleCheck.warning,
      };
    }

    // 2. 檢驗是否具備足夠骨架關鍵點
    if (!userPose || !refPose) {
      return {
        scale: 1.0,
        offsetX: 0,
        offsetY: 0,
        status: "manual_required",
        warning: "缺少雙方 2D 骨架數據，已降級為手動校準。",
      };
    }

    // 輔助計算軀幹長度 (肩中點至髖中點歐幾里得距離)
    const getTorsoMetric = (pose: PoseLandmarks) => {
      const ls = pose["left_shoulder"] || pose["11"];
      const rs = pose["right_shoulder"] || pose["12"];
      const lh = pose["left_hip"] || pose["23"];
      const rh = pose["right_hip"] || pose["24"];

      if (!ls || !rs || !lh || !rh) return null;

      const shoulderMid = { x: (ls.x + rs.x) / 2, y: (ls.y + rs.y) / 2 };
      const hipMid = { x: (lh.x + rh.x) / 2, y: (lh.y + rh.y) / 2 };

      const dx = shoulderMid.x - hipMid.x;
      const dy = shoulderMid.y - hipMid.y;
      const length = Math.sqrt(dx * dx + dy * dy);

      return {
        torsoLength: length,
        hipCenter: hipMid,
      };
    };

    const userMetric = getTorsoMetric(userPose);
    const refMetric = getTorsoMetric(refPose);

    if (!userMetric || !refMetric || userMetric.torsoLength <= 0.02 || refMetric.torsoLength <= 0.02) {
      return {
        scale: 1.0,
        offsetX: 0,
        offsetY: 0,
        status: "manual_required",
        warning: "關鍵軀幹點能見度不足，已切換為手動微調模式。",
      };
    }

    // 依據真實軀幹比例計算縮放 (保留長寬比)
    const rawScale = userMetric.torsoLength / refMetric.torsoLength;
    const clampedScale = Math.max(0.65, Math.min(1.65, rawScale));

    // 計算骨盆中心位移 (使兩人腰部/重心在畫面上大致居中重合)
    const diffX = (userMetric.hipCenter.x - refMetric.hipCenter.x) * containerWidth;
    const diffY = (userMetric.hipCenter.y - refMetric.hipCenter.y) * containerHeight;

    return {
      scale: Number(clampedScale.toFixed(2)),
      offsetX: Math.round(diffX),
      offsetY: Math.round(diffY),
      status: "auto_computed",
      userTorsoLength: Number((userMetric.torsoLength * 1000).toFixed(1)),
      refTorsoLength: Number((refMetric.torsoLength * 1000).toFixed(1)),
    };
  }

  /**
   * 舊版簡化介面相容方法
   */
  static computeAutoFraming(
    userTorsoLength: number = 115,
    refTorsoLength: number = 115
  ): { scale: number; offsetX: number; offsetY: number } {
    if (refTorsoLength <= 10) return { scale: 1.0, offsetX: 0, offsetY: 0 };
    const scale = Math.max(0.65, Math.min(1.65, userTorsoLength / refTorsoLength));
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
    const u = (userAngle || "DTL").toUpperCase();
    const r = (refAngle || "DTL").toUpperCase();
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
