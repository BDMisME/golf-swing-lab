"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";

export type OverlayMode = "coach" | "comparison" | "pro";

interface Landmark {
  x: number;
  y: number;
  visibility: number;
}

interface Keyframe {
  time_ms: number;
  landmarks?: Record<string, Landmark>;
  pose_confidence?: number;
}

interface SwingEventItem {
  id?: string;
  event_name: string;
  time_ms: number;
  confidence: number;
  rationale?: string;
  uncertainty_ms?: number;
}

interface CleanMotionOverlayProps {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  keyframes: Keyframe[];
  events: SwingEventItem[];
  startMs: number;
  endMs: number;
  wristTrajectory?: Array<{ time_ms: number; x: number; y: number; conf: number }>;
  ballTrajectory?: Array<{ time_ms: number; x: number; y: number; point_type: string }>;
  onPhaseChange?: (phase: string) => void;
}

export function CleanMotionOverlay({
  videoRef,
  keyframes = [],
  events = [],
  startMs,
  endMs,
  wristTrajectory = [],
  ballTrajectory = [],
  onPhaseChange,
}: CleanMotionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // 檢視模式：預設為 AI 教練模式 (coach)
  const [overlayMode, setOverlayMode] = useState<OverlayMode>("coach");

  // 當前檢測到的揮桿動作階段與簡要教練指引
  const [currentPhase, setCurrentPhase] = useState<string>("address");
  const [coachTip, setCoachTip] = useState<string>("站姿設定：確認脊柱前傾與頭部穩定基準");

  // 專業分析模式 (Pro Mode) 圖層開關
  const [proShowSkeleton, setProShowSkeleton] = useState<boolean>(false);
  const [proShowHandPath, setProShowHandPath] = useState<boolean>(true);
  const [proShowTushLine, setProShowTushLine] = useState<boolean>(true);
  const [proShowHeadBox, setProShowHeadBox] = useState<boolean>(true);
  const [proShowBallTracer, setProShowBallTracer] = useState<boolean>(false);

  // 提取各關鍵事件時間碼
  const eventMap = React.useMemo(() => {
    const map: Record<string, number> = {};
    for (const ev of events) {
      map[ev.event_name] = ev.time_ms;
    }
    return map;
  }, [events]);

  const addressMs = eventMap["address"] || startMs;
  const takeawayMs = eventMap["takeaway"] || addressMs + 300;
  const topMs = eventMap["top"] || Math.round(startMs + (endMs - startMs) * 0.45);
  const impactMs =
    eventMap["impact_estimated"] ||
    eventMap["impact"] ||
    Math.round(startMs + (endMs - startMs) * 0.70);
  const finishMs = eventMap["finish"] || endMs;

  // 取得站姿基準關鍵幀 (Address Reference)
  const addressKf = React.useMemo(() => {
    if (!keyframes.length) return null;
    let closest = keyframes[0];
    let minD = Math.abs(closest.time_ms - addressMs);
    for (const kf of keyframes) {
      const d = Math.abs(kf.time_ms - addressMs);
      if (d < minD) {
        minD = d;
        closest = kf;
      }
    }
    return closest;
  }, [keyframes, addressMs]);

  // 核心渲染函式
  const renderOverlay = useCallback(
    (currentTimeMs: number) => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // 保持 Canvas 解析度與容器實體像素同步
      const rect = canvas.getBoundingClientRect();
      if (canvas.width !== Math.round(rect.width) || canvas.height !== Math.round(rect.height)) {
        canvas.width = Math.round(rect.width);
        canvas.height = Math.round(rect.height);
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const vW = video.videoWidth || 1920;
      const vH = video.videoHeight || 1080;
      const videoAspect = vW / vH;
      const containerAspect = canvas.width / canvas.height;

      let drawWidth = canvas.width;
      let drawHeight = canvas.height;
      let offsetX = 0;
      let offsetY = 0;

      if (containerAspect > videoAspect) {
        drawWidth = canvas.height * videoAspect;
        offsetX = (canvas.width - drawWidth) / 2;
      } else {
        drawHeight = canvas.width / videoAspect;
        offsetY = (canvas.height - drawHeight) / 2;
      }

      const toX = (normX: number) => offsetX + normX * drawWidth;
      const toY = (normY: number) => offsetY + normY * drawHeight;

      // 尋找最接近當前時間之關鍵幀
      if (!keyframes.length) return;
      let currentKf = keyframes[0];
      let minDiff = Math.abs(currentKf.time_ms - currentTimeMs);
      for (const kf of keyframes) {
        const d = Math.abs(kf.time_ms - currentTimeMs);
        if (d < minDiff) {
          minDiff = d;
          currentKf = kf;
        }
      }

      const lms = currentKf.landmarks || {};
      const addrLms = addressKf?.landmarks || {};

      // 揮桿時間區間防殘留保護：超出當前揮桿有效範圍 (address 前 500ms 至 finish 後 500ms) 立即清空不繪製
      if (currentTimeMs < addressMs - 500 || currentTimeMs > finishMs + 600) {
        return;
      }

      // 判定當前動作階段
      let phase = "address";
      let tip = "站姿設定：確認脊柱前傾與頭部穩定基準";

      if (currentTimeMs < takeawayMs) {
        phase = "address";
        tip = "站姿設定：維持脊柱前傾，確認站姿頭部基準";
      } else if (currentTimeMs < topMs - 60) {
        phase = "backswing";
        tip = "上桿引導：手部沿揮桿平面平穩爬升，避免手腕提早翻轉";
      } else if (currentTimeMs <= topMs + 60) {
        phase = "top";
        tip = "上桿頂點：肩膀充分轉身，頂點短暫制動蓄力";
      } else if (currentTimeMs < impactMs - 40) {
        phase = "downswing";
        tip = "下桿加速：下半身啟動引導，保持臀線與脊柱前傾角度";
      } else if (currentTimeMs <= impactMs + 80) {
        phase = "impact";
        tip = "擊球瞬間：頭部留在球後，力量向目標線完整釋放";
      } else {
        phase = "finish";
        tip = "收桿平衡：前腳支撐站定，維持身體垂直軸線平衡";
      }

      setCurrentPhase(phase);
      setCoachTip(tip);
      if (onPhaseChange) onPhaseChange(phase);

      // 共通關節輔助函數
      const getPt = (name: string, lmSource = lms) => {
        const lm = lmSource[name];
        if (!lm || lm.visibility < 0.35) return null;
        return { x: toX(lm.x), y: toY(lm.y), vis: lm.visibility };
      };

      // -------------------------------------------------------------
      // 模式 1: 預設 AI 教練模式 (畫面最多同時顯示 2 個標記)
      // 色彩語義：青綠色 (#06b6d4) 為目前觀測，金色 (#fbbf24) 為站姿參考，紅色 (#ef4444) 為異常提醒
      // -------------------------------------------------------------
      if (overlayMode === "coach") {
        const addrNose = getPt("nose", addrLms);
        const curNose = getPt("nose", lms);
        const addrHip = getPt("right_hip", addrLms) || getPt("left_hip", addrLms);
        const addrSh = getPt("right_shoulder", addrLms) || getPt("left_shoulder", addrLms);
        const curWrist = getPt("right_wrist", lms) || getPt("left_wrist", lms);

        // 估算站姿軀幹長度
        let torsoLen = 100;
        if (addrHip && addrSh) {
          torsoLen = Math.max(50, Math.hypot(addrSh.x - addrHip.x, addrSh.y - addrHip.y));
        }

        if (phase === "address") {
          // 標記 1: 站姿頭部基準金黃色虛線圈
          if (addrNose) {
            ctx.save();
            ctx.strokeStyle = "#fbbf24";
            ctx.lineWidth = 1.6;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.arc(addrNose.x, addrNose.y, torsoLen * 0.22, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
          // 標記 2: 站姿脊柱前傾基準線 (金色)
          if (addrHip && addrSh) {
            ctx.save();
            ctx.strokeStyle = "rgba(251, 191, 36, 0.75)";
            ctx.lineWidth = 2.0;
            ctx.beginPath();
            ctx.moveTo(addrHip.x, addrHip.y);
            ctx.lineTo(addrSh.x, addrSh.y);
            ctx.stroke();
            ctx.restore();
          }
        } else if (phase === "backswing") {
          // 標記 1: 上桿手部動態軌跡 (青綠色，嚴格只繪製到當前播放時間點，不劇透！)
          if (wristTrajectory.length > 1) {
            const pastPoints = wristTrajectory.filter((p) => p.time_ms <= currentTimeMs && p.time_ms >= addressMs);
            if (pastPoints.length >= 2) {
              ctx.save();
              ctx.strokeStyle = "#06b6d4";
              ctx.lineWidth = 2.5;
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.beginPath();
              ctx.moveTo(toX(pastPoints[0].x), toY(pastPoints[0].y));
              for (let i = 1; i < pastPoints.length; i++) {
                ctx.lineTo(toX(pastPoints[i].x), toY(pastPoints[i].y));
              }
              ctx.stroke();
              ctx.restore();
            }
          }
          // 標記 2: 當前手部光點
          if (curWrist) {
            ctx.save();
            ctx.fillStyle = "#06b6d4";
            ctx.shadowColor = "#06b6d4";
            ctx.shadowBlur = 6;
            ctx.beginPath();
            ctx.arc(curWrist.x, curWrist.y, 4.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        } else if (phase === "top") {
          // 標記 1: 頂點手部轉折金色光環
          if (curWrist) {
            ctx.save();
            ctx.strokeStyle = "#fbbf24";
            ctx.lineWidth = 2.2;
            ctx.shadowColor = "#fbbf24";
            ctx.shadowBlur = 8;
            ctx.beginPath();
            ctx.arc(curWrist.x, curWrist.y, 7, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
          // 標記 2: 頂點肩膀旋轉姿態線 (青綠色)
          const curLsh = getPt("left_shoulder");
          const curRsh = getPt("right_shoulder");
          if (curLsh && curRsh) {
            ctx.save();
            ctx.strokeStyle = "rgba(6, 182, 212, 0.85)";
            ctx.lineWidth = 2.0;
            ctx.beginPath();
            ctx.moveTo(curLsh.x, curLsh.y);
            ctx.lineTo(curRsh.x, curRsh.y);
            ctx.stroke();
            ctx.restore();
          }
        } else if (phase === "downswing") {
          // 標記 1: 下桿手部動態軌跡 (亮青綠色，只畫到當前播放時間)
          if (wristTrajectory.length > 1) {
            const downPoints = wristTrajectory.filter(
              (p) => p.time_ms <= currentTimeMs && p.time_ms >= topMs - 60
            );
            if (downPoints.length >= 2) {
              ctx.save();
              ctx.strokeStyle = "#00f0ff";
              ctx.lineWidth = 3.0;
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.beginPath();
              ctx.moveTo(toX(downPoints[0].x), toY(downPoints[0].y));
              for (let i = 1; i < downPoints.length; i++) {
                ctx.lineTo(toX(downPoints[i].x), toY(downPoints[i].y));
              }
              ctx.stroke();
              ctx.restore();
            }
          }
          // 標記 2: 臀部貼線參考 (Tush Line，金色虛線)
          if (addrHip) {
            ctx.save();
            ctx.strokeStyle = "rgba(251, 191, 36, 0.7)";
            ctx.lineWidth = 1.6;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(addrHip.x, addrHip.y - torsoLen * 0.4);
            ctx.lineTo(addrHip.x, addrHip.y + torsoLen * 0.8);
            ctx.stroke();
            ctx.restore();
          }
        } else if (phase === "impact") {
          // 標記 1: 擊球瞬間手部定位點 (亮青綠色)
          if (curWrist) {
            ctx.save();
            ctx.fillStyle = "#38bdf8";
            ctx.shadowColor = "#38bdf8";
            ctx.shadowBlur = 8;
            ctx.beginPath();
            ctx.arc(curWrist.x, curWrist.y, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
          // 標記 2: 頭部相對位移檢核圈 (正常為柔和青綠，若離位下沉顯著則為紅色提醒)
          if (addrNose && curNose) {
            const disp = Math.hypot(curNose.x - addrNose.x, curNose.y - addrNose.y);
            const isAnomaly = disp > torsoLen * 0.18;
            ctx.save();
            ctx.strokeStyle = isAnomaly ? "#ef4444" : "#10b981";
            ctx.lineWidth = 1.8;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.arc(curNose.x, curNose.y, torsoLen * 0.22, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        } else {
          // Finish 收桿階段
          // 標記 1: 身體前腳支撐平衡垂直軸線
          const curAnkle = getPt("left_ankle") || getPt("right_ankle") || addrHip;
          if (curNose && curAnkle) {
            ctx.save();
            ctx.strokeStyle = "rgba(16, 185, 129, 0.85)";
            ctx.lineWidth = 2.0;
            ctx.beginPath();
            ctx.moveTo(curAnkle.x, curAnkle.y);
            ctx.lineTo(curNose.x, curNose.y);
            ctx.stroke();
            ctx.restore();
          }
          // 標記 2: 收桿前腳支撐點 (青綠色)
          if (curAnkle) {
            ctx.save();
            ctx.fillStyle = "#10b981";
            ctx.beginPath();
            ctx.arc(curAnkle.x, curAnkle.y, 4.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }
      }

      // -------------------------------------------------------------
      // 模式 2: 專業分析模式 (Pro Mode - 允許手動開關多圖層與完整骨架)
      // -------------------------------------------------------------
      else if (overlayMode === "pro") {
        // 1. 人體 2D 骨架連線
        if (proShowSkeleton) {
          const SKELETON_PAIRS = [
            ["left_shoulder", "right_shoulder"],
            ["left_shoulder", "left_elbow"],
            ["left_elbow", "left_wrist"],
            ["right_shoulder", "right_elbow"],
            ["right_elbow", "right_wrist"],
            ["left_shoulder", "left_hip"],
            ["right_shoulder", "right_hip"],
            ["left_hip", "right_hip"],
            ["left_hip", "left_knee"],
            ["left_knee", "left_ankle"],
            ["right_hip", "right_knee"],
            ["right_knee", "right_ankle"],
          ];
          ctx.save();
          ctx.strokeStyle = "rgba(16, 185, 129, 0.65)";
          ctx.lineWidth = 2.0;
          for (const [p1, p2] of SKELETON_PAIRS) {
            const pt1 = getPt(p1);
            const pt2 = getPt(p2);
            if (pt1 && pt2) {
              ctx.beginPath();
              ctx.moveTo(pt1.x, pt1.y);
              ctx.lineTo(pt2.x, pt2.y);
              ctx.stroke();
            }
          }
          ctx.restore();
        }

        // 2. 完整手部軌跡 (上桿青綠 / 下桿亮紅)
        if (proShowHandPath && wristTrajectory.length > 1) {
          ctx.save();
          ctx.lineWidth = 2.5;
          ctx.lineCap = "round";

          // 上桿路徑 (Address -> Top)
          const bsPoints = wristTrajectory.filter((p) => p.time_ms >= addressMs && p.time_ms <= topMs);
          if (bsPoints.length >= 2) {
            ctx.strokeStyle = "rgba(6, 182, 212, 0.75)";
            ctx.beginPath();
            ctx.moveTo(toX(bsPoints[0].x), toY(bsPoints[0].y));
            for (let i = 1; i < bsPoints.length; i++) {
              ctx.lineTo(toX(bsPoints[i].x), toY(bsPoints[i].y));
            }
            ctx.stroke();
          }

          // 下桿路徑 (Top -> Impact)
          const dsPoints = wristTrajectory.filter((p) => p.time_ms >= topMs && p.time_ms <= impactMs);
          if (dsPoints.length >= 2) {
            ctx.strokeStyle = "rgba(239, 68, 68, 0.85)";
            ctx.beginPath();
            ctx.moveTo(toX(dsPoints[0].x), toY(dsPoints[0].y));
            for (let i = 1; i < dsPoints.length; i++) {
              ctx.lineTo(toX(dsPoints[i].x), toY(dsPoints[i].y));
            }
            ctx.stroke();
          }
          ctx.restore();
        }

        // 3. 站姿臀線 (Tush Line)
        if (proShowTushLine) {
          const addrHip = getPt("right_hip", addrLms) || getPt("left_hip", addrLms);
          if (addrHip) {
            ctx.save();
            ctx.strokeStyle = "#fbbf24";
            ctx.lineWidth = 1.8;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(addrHip.x, 0);
            ctx.lineTo(addrHip.x, canvas.height);
            ctx.stroke();
            ctx.restore();
          }
        }

        // 4. 頭部基準圈
        if (proShowHeadBox) {
          const addrNose = getPt("nose", addrLms);
          if (addrNose) {
            ctx.save();
            ctx.strokeStyle = "#fbbf24";
            ctx.lineWidth = 1.6;
            ctx.setLineDash([4, 4]);
            ctx.beginPath();
            ctx.arc(addrNose.x, addrNose.y, 25, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        }

        // 5. 真實出球動態軌跡 (若無真實觀測則不繪製)
        if (proShowBallTracer && ballTrajectory.length >= 2) {
          const curBallPts = ballTrajectory.filter((p) => p.time_ms <= currentTimeMs);
          if (curBallPts.length >= 2) {
            ctx.save();
            ctx.strokeStyle = "#39ff14";
            ctx.lineWidth = 3.5;
            ctx.shadowColor = "#39ff14";
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.moveTo(toX(curBallPts[0].x), toY(curBallPts[0].y));
            for (let i = 1; i < curBallPts.length; i++) {
              ctx.lineTo(toX(curBallPts[i].x), toY(curBallPts[i].y));
            }
            ctx.stroke();
            ctx.restore();
          }
        }
      }
    },
    [
      keyframes,
      addressKf,
      events,
      startMs,
      endMs,
      addressMs,
      takeawayMs,
      topMs,
      impactMs,
      finishMs,
      wristTrajectory,
      ballTrajectory,
      overlayMode,
      proShowSkeleton,
      proShowHandPath,
      proShowTushLine,
      proShowHeadBox,
      proShowBallTracer,
      onPhaseChange,
      videoRef,
    ]
  );

  // -------------------------------------------------------------
  // 逐幀播放器與視覺同步 (requestVideoFrameCallback 或 timeupdate 降級)
  // -------------------------------------------------------------
  useEffect(() => {
    const vid = videoRef.current;
    if (!vid) return;

    let callbackId: number | null = null;
    let isCancelled = false;

    // 優先使用 HTML5 原生 requestVideoFrameCallback
    if (typeof (vid as any).requestVideoFrameCallback === "function") {
      const handleVideoFrame = (_now: DOMHighResTimeStamp, metadata: any) => {
        if (isCancelled) return;
        const currentMs = Math.round(metadata.mediaTime * 1000);
        renderOverlay(currentMs);
        callbackId = (vid as any).requestVideoFrameCallback(handleVideoFrame);
      };
      callbackId = (vid as any).requestVideoFrameCallback(handleVideoFrame);
    } else {
      // 降級方案：監聽 timeupdate 與 requestAnimationFrame
      const onTimeUpdate = () => {
        const currentMs = Math.round(vid.currentTime * 1000);
        renderOverlay(currentMs);
      };
      vid.addEventListener("timeupdate", onTimeUpdate);
      return () => {
        vid.removeEventListener("timeupdate", onTimeUpdate);
      };
    }

    return () => {
      isCancelled = true;
      if (callbackId !== null && typeof (vid as any).cancelVideoFrameCallback === "function") {
        (vid as any).cancelVideoFrameCallback(callbackId);
      }
    };
  }, [videoRef, renderOverlay]);

  return (
    <div className="space-y-3">
      {/* 畫布覆蓋層 (掛載於播放器容器內) */}
      <canvas
        ref={canvasRef}
        width={640}
        height={480}
        className="pointer-events-none absolute inset-0 h-full w-full"
      />

      {/* 底部智慧教練 HUD 提示列 (替代原覆蓋在人體身上的雜亂標籤) */}
      <div className="flex items-center justify-between rounded-xl border border-gray-800 bg-[#0d141a]/95 px-3 py-2 text-xs backdrop-blur-md">
        <div className="flex items-center gap-2">
          <span className="flex h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="font-semibold text-cyan-300 uppercase tracking-wide">
            {currentPhase}
          </span>
          <span className="text-gray-500">|</span>
          <span className="text-gray-200">{coachTip}</span>
        </div>

        {/* 檢視模式切換器 */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setOverlayMode("coach")}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
              overlayMode === "coach"
                ? "bg-cyan-500 text-black shadow-sm"
                : "border border-gray-800 bg-black/40 text-gray-400 hover:text-white"
            }`}
          >
            AI 教練模式
          </button>
          <button
            type="button"
            onClick={() => setOverlayMode("pro")}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
              overlayMode === "pro"
                ? "bg-amber-500 text-black shadow-sm"
                : "border border-gray-800 bg-black/40 text-gray-400 hover:text-white"
            }`}
          >
            專業分析模式
          </button>
        </div>
      </div>

      {/* 專業模式專屬圖層控制列 (僅在切換至 Pro Mode 時展示) */}
      {overlayMode === "pro" && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-800 bg-[#0a0f14] p-2.5 text-xs">
          <button
            type="button"
            onClick={() => setProShowHandPath((v) => !v)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              proShowHandPath
                ? "bg-cyan-600 text-white"
                : "border border-gray-700 bg-black/40 text-gray-400"
            }`}
          >
            {proShowHandPath ? "✓ 手部雙色軌跡" : "手部軌跡"}
          </button>
          <button
            type="button"
            onClick={() => setProShowTushLine((v) => !v)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              proShowTushLine
                ? "bg-amber-600 text-white"
                : "border border-gray-700 bg-black/40 text-gray-400"
            }`}
          >
            {proShowTushLine ? "✓ 站姿臀線 (Tush Line)" : "站姿臀線"}
          </button>
          <button
            type="button"
            onClick={() => setProShowHeadBox((v) => !v)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              proShowHeadBox
                ? "bg-amber-600 text-white"
                : "border border-gray-700 bg-black/40 text-gray-400"
            }`}
          >
            {proShowHeadBox ? "✓ 頭部基準圈" : "頭部基準圈"}
          </button>
          <button
            type="button"
            onClick={() => setProShowSkeleton((v) => !v)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              proShowSkeleton
                ? "bg-emerald-600 text-white"
                : "border border-gray-700 bg-black/40 text-gray-400"
            }`}
          >
            {proShowSkeleton ? "✓ MediaPipe 33 點骨架" : "MediaPipe 33 點骨架"}
          </button>
          <button
            type="button"
            onClick={() => setProShowBallTracer((v) => !v)}
            className={`rounded-lg px-2.5 py-1 font-semibold transition ${
              ballTrajectory.length >= 2
                ? proShowBallTracer
                  ? "bg-lime-500 text-black font-bold"
                  : "border border-gray-700 bg-black/40 text-gray-300"
                : "border border-gray-800 bg-black/20 text-gray-600 cursor-not-allowed"
            }`}
            disabled={ballTrajectory.length < 2}
          >
            {ballTrajectory.length >= 2
              ? proShowBallTracer
                ? "✓ 實測出球軌跡"
                : "實測出球軌跡"
              : "無真球觀測 (不顯示假球軌)"}
          </button>
        </div>
      )}
    </div>
  );
}
