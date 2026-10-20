"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  API_BASE_URL,
  apiFetch,
  formatCoverageStatus,
  formatMsToTimestamp,
  getAuthToken,
  SwingSegmentItem,
} from "@/lib/api";

export default function SwingDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const swingId = params.id;

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const [swing, setSwing] = useState<SwingSegmentItem | null>(null);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showSwingPath, setShowSwingPath] = useState(true);
  const [showHeadBox, setShowHeadBox] = useState(true);
  const [showBallTracer, setShowBallTracer] = useState(true);
  const [showProGhost, setShowProGhost] = useState(true);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [expandedSubscore, setExpandedSubscore] = useState<string | null>(
    "spine_tilt_stability"
  );
  const [startMs, setStartMs] = useState(0);
  const [endMs, setEndMs] = useState(0);
  const [label, setLabel] = useState("valid_swing");
  const [ballStrike, setBallStrike] = useState("estimated_strike");
  const [notes, setNotes] = useState("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveBanner, setSaveBanner] = useState<string | null>(null);

  const loadSwing = useCallback(async () => {
    try {
      const data = await apiFetch<SwingSegmentItem>(`/api/swings/${swingId}`);
      setSwing(data);
      setStartMs(data.start_ms);
      setEndMs(data.end_ms);
      setLabel(data.label);
      setBallStrike(data.ball_strike_status);
      setNotes(data.notes || "");
    } catch (err: any) {
      if (String(err.message).includes("401")) {
        router.push("/login");
      }
    }
  }, [swingId, router]);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/login");
      return;
    }
    loadSwing();
  }, [loadSwing, router]);

  // 繪製高爾夫專業 2D 揮桿軌跡 (Swing Path Arc) 與人體骨架疊圖
  const drawPoseOverlay = useCallback(
    (currentTimeMs: number) => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!swing?.keyframes?.length) return;

      // 鐵律 1: 時間窗口嚴格防呆 (只在該球有效揮桿期間顯示，打完轉身走開自動乾淨清空)
      const bufferBefore = 300;
      const bufferAfter = 500;
      if (
        currentTimeMs < swing.start_ms - bufferBefore ||
        currentTimeMs > swing.end_ms + bufferAfter
      ) {
        return; // 完全清空畫布，呈現 100% 乾淨原片
      }

      // 鐵律 2: 螢幕解析度與 Letterbox 視訊真實畫面 1:1 精確映射
      const rect = video.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        if (canvas.width !== Math.round(rect.width) || canvas.height !== Math.round(rect.height)) {
          canvas.width = Math.round(rect.width);
          canvas.height = Math.round(rect.height);
        }
      }

      const vW = video.videoWidth || 1920;
      const vH = video.videoHeight || 1080;
      const videoAspect = vW / vH;
      const containerAspect = canvas.width / canvas.height;

      let drawWidth = canvas.width;
      let drawHeight = canvas.height;
      let offsetX = 0;
      let offsetY = 0;

      if (containerAspect > videoAspect) {
        // 容器比影片寬 (常見於橫屏容器播放直式 9:16 影片) -> 左右黑邊
        drawWidth = canvas.height * videoAspect;
        offsetX = (canvas.width - drawWidth) / 2;
      } else {
        // 容器比影片高 -> 上下黑邊
        drawHeight = canvas.width / videoAspect;
        offsetY = (canvas.height - drawHeight) / 2;
      }

      // 歸一化座標 (0~1) 映射至 Canvas 實際畫面像素座標
      const toX = (normX: number) => offsetX + normX * drawWidth;
      const toY = (normY: number) => offsetY + normY * drawHeight;

      const events = swing.events || [];
      const addressEv = events.find(
        (e) => e.event_name === "address" || e.event_name.includes("address")
      );
      const topEv = events.find((e) => e.event_name === "top");
      const impactEv = events.find(
        (e) => e.event_name === "impact_estimated" || e.event_name === "impact"
      );
      const addressMs = addressEv?.time_ms || swing.start_ms;
      const topMs = topEv?.time_ms || (swing.start_ms + swing.end_ms) * 0.45;
      const impactMs = impactEv?.time_ms || (swing.start_ms + swing.end_ms) * 0.7;

      // 取得 Address (站姿) 關鍵幀作為穩定的高爾夫幾何基準
      let addressKf = swing.keyframes.find(
        (kf) => Math.abs(kf.time_ms - addressMs) < 250
      );
      if (!addressKf) {
        addressKf = swing.keyframes.filter((kf) => kf.time_ms <= topMs)[0] || swing.keyframes[0];
      }
      const addressLms = addressKf?.landmarks || {};

      // 尋找最接近當前時間之關鍵幀姿態
      let nearest = swing.keyframes[0];
      let minDiff = Math.abs(nearest.time_ms - currentTimeMs);
      for (const kf of swing.keyframes) {
        const d = Math.abs(kf.time_ms - currentTimeMs);
        if (d < minDiff) {
          minDiff = d;
          nearest = kf;
        }
      }
      const lms = nearest.landmarks || {};

      // 1. 專業 PGA 教練檢核線 (臀部鉛線 Tush Line & 脊柱傾角線)
      if (showProGhost) {
        const addrHip = addressLms["right_hip"] || addressLms["left_hip"];
        const addrSh = addressLms["right_shoulder"] || addressLms["left_shoulder"];
        if (addrHip && addrSh && addrHip.visibility >= 0.40 && addrSh.visibility >= 0.40) {
          const torsoLength = Math.hypot(toX(addrHip.x) - toX(addrSh.x), toY(addrHip.y) - toY(addrSh.y));
          // 骨盆背側後緣推定：DTL 視角下臀部外緣位於髖關節中心背後約 16% 軀幹長度
          // 依據肩部相對於髖部 X 座標判斷目標朝向
          const isFacingRight = addrSh.x > addrHip.x;
          const buttOffset = (isFacingRight ? -1 : 1) * torsoLength * 0.16;
          const tushX = toX(addrHip.x) + buttOffset;
          const tushTopY = toY(Math.max(0.1, addrHip.y - 0.25));
          const tushBotY = toY(Math.min(0.95, addrHip.y + 0.35));

          ctx.save();
          ctx.strokeStyle = "rgba(251, 191, 36, 0.75)";
          ctx.lineWidth = 1.8;
          ctx.setLineDash([6, 5]);
          ctx.beginPath();
          ctx.moveTo(tushX, tushTopY);
          ctx.lineTo(tushX, tushBotY);
          ctx.stroke();

          ctx.font = "bold 10px sans-serif";
          ctx.fillStyle = "#fbbf24";
          ctx.fillText("PGA 鉛線 (Tush Line)", isFacingRight ? tushX - 125 : tushX + 8, tushTopY + 14);

          const currHip = lms["right_hip"] || lms["left_hip"];
          if (currentTimeMs >= topMs) {
            if (currHip && currHip.visibility >= 0.40) {
              const curHipEstimatedButtX = toX(currHip.x) + buttOffset;
              // 依軀幹長度歸一化之位移比例，不使用粗糙像素
              const normDisplacement = isFacingRight
                ? (curHipEstimatedButtX - tushX) / torsoLength
                : (tushX - curHipEstimatedButtX) / torsoLength;

              // 位移離開基準線超過 10% 軀幹長度判定為早起
              const isEarlyExtension = normDisplacement > 0.10;
              const isStable = normDisplacement <= 0.04;

              ctx.fillStyle = isEarlyExtension ? "#ef4444" : isStable ? "#10b981" : "#fbbf24";
              ctx.font = "bold 9px sans-serif";
              const labelText = isEarlyExtension
                ? `⚠ 早起 (離開鉛線 ${(normDisplacement * 100).toFixed(0)}%)`
                : isStable
                ? "✓ 臀部維持在線 (穩定)"
                : "∼ 輕微位移 (在容許範圍)";

              ctx.fillText(labelText, tushX + (isFacingRight ? 8 : -140), toY(currHip.y));
            } else {
              ctx.fillStyle = "#94a3b8";
              ctx.font = "italic 9px sans-serif";
              ctx.fillText("∼ 關鍵點置信度不足 (無可靠早起判定)", tushX + 8, toY(addrHip.y));
            }
          }
          ctx.restore();
        } else if (addrHip) {
          ctx.save();
          ctx.font = "italic 9px sans-serif";
          ctx.fillStyle = "#94a3b8";
          ctx.fillText("Tush Line: 姿態置信度不足", toX(addrHip.x) - 40, toY(addrHip.y));
          ctx.restore();
        }

        const curSh = lms["right_shoulder"] || lms["left_shoulder"];
        const curHip = lms["right_hip"] || lms["left_hip"];
        if (curSh && curHip && curSh.visibility >= 0.3 && curHip.visibility >= 0.3) {
          ctx.save();
          ctx.strokeStyle = "rgba(16, 185, 129, 0.65)";
          ctx.lineWidth = 1.5;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(toX(curHip.x), toY(curHip.y));
          ctx.lineTo(toX(curSh.x), toY(curSh.y));
          ctx.stroke();
          ctx.restore();
        }
      }

      // 2. 頭部穩定基準圈 (Head Box) - 精確鎖定 Address 站位，擊球後自動淡出！
      if (showHeadBox) {
        const nose = addressLms["nose"];
        const le = addressLms["left_eye"];
        const re = addressLms["right_eye"];
        const headRef = nose || le || re;

        if (headRef && headRef.visibility >= 0.3 && currentTimeMs <= impactMs + 250) {
          const hx = toX(headRef.x);
          const hy = toY(headRef.y);
          const headRadius = Math.max(14, drawHeight * 0.035);

          ctx.save();
          ctx.strokeStyle = "#fbbf24";
          ctx.lineWidth = 1.8;
          ctx.setLineDash([5, 4]);
          ctx.beginPath();
          ctx.arc(hx, hy, headRadius, 0, Math.PI * 2);
          ctx.stroke();

          ctx.font = "bold 9px sans-serif";
          ctx.fillStyle = "#fbbf24";
          ctx.fillText("頭部基準", hx - 18, hy - headRadius - 6);

          const currNose = lms["nose"] || lms["left_eye"];
          if (currNose && currNose.visibility >= 0.3) {
            const cx = toX(currNose.x);
            const cy = toY(currNose.y);
            const dist = Math.hypot(cx - hx, cy - hy);
            ctx.fillStyle = dist > headRadius * 0.7 ? "#ef4444" : "#10b981";
            ctx.beginPath();
            ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
            ctx.fill();
          }
          ctx.restore();
        }
      }

      // 3. 小白球出球動態軌跡 (Ball Tracer) - 嚴格基於後端 AI 觀測資料渲染
      if (showBallTracer) {
        const timeSinceImpact = currentTimeMs - impactMs;
        const realTrajectory: any[] = (swing as any).ball_trajectory || (swing as any).pose_artifact?.quality_metadata?.ball_trajectory || [];

        if (realTrajectory && realTrajectory.length >= 2) {
          // A. 真正的 AI 觀測出球軌跡渲染
          const firstPt = realTrajectory[0];
          const lastPt = realTrajectory[realTrajectory.length - 1];
          const trajStartMs = firstPt.time_ms;
          const trajEndMs = lastPt.time_ms + 400;

          if (currentTimeMs >= trajStartMs - 100 && currentTimeMs <= trajEndMs) {
            ctx.save();
            const activePts = realTrajectory.filter((p: any) => p.time_ms <= currentTimeMs);

            if (activePts.length >= 1) {
              ctx.shadowColor = "#39ff14";
              ctx.shadowBlur = 10;
              ctx.lineWidth = 2.5;

              ctx.beginPath();
              for (let i = 0; i < activePts.length; i++) {
                const px = toX(activePts[i].x);
                const py = toY(activePts[i].y);
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
              }
              const curPt = activePts[activePts.length - 1];
              const curX = toX(curPt.x);
              const curY = toY(curPt.y);

              const grad = ctx.createLinearGradient(toX(firstPt.x), toY(firstPt.y), curX, curY);
              grad.addColorStop(0, "rgba(57, 255, 20, 0.4)");
              grad.addColorStop(1, "#39ff14");
              ctx.strokeStyle = grad;
              ctx.stroke();

              // 繪製發光白球
              ctx.fillStyle = "#ffffff";
              ctx.shadowColor = "#ffffff";
              ctx.shadowBlur = 12;
              ctx.beginPath();
              ctx.arc(curX, curY, 3.5, 0, Math.PI * 2);
              ctx.fill();

              ctx.font = "bold 9px sans-serif";
              ctx.fillStyle = "#39ff14";
              ctx.fillText(
                curPt.point_type === "predicted" ? "AI 預測延伸" : "AI 實測出球 (Toptracer)",
                curX + 8,
                curY - 4
              );
            }
            ctx.restore();
          }
        } else if (timeSinceImpact >= -100 && timeSinceImpact <= 1100) {
          // B. 誠實降級：無可靠 AI 球體觀測時，僅顯示半透明虛線示意動畫，並明確標註免責聲明
          const addrW = addressLms["right_wrist"] || addressLms["left_wrist"];
          const addrAnk = addressLms["right_ankle"] || addressLms["left_ankle"];
          const groundY = addrAnk ? toY(addrAnk.y) : toY(0.85);
          const ballX = addrW ? toX(addrW.x) : toX(0.5);
          const ballY = Math.min(canvas.height - 10, groundY - 5);

          ctx.save();
          if (timeSinceImpact < 0) {
            ctx.fillStyle = "rgba(255, 255, 255, 0.6)";
            ctx.beginPath();
            ctx.arc(ballX, ballY, 3, 0, Math.PI * 2);
            ctx.fill();
          } else {
            const progress = Math.min(1.0, timeSinceImpact / 1000);
            const numSteps = 20;
            const currentStep = Math.max(1, Math.floor(progress * numSteps));

            ctx.lineWidth = 1.5;
            ctx.setLineDash([4, 4]); // 虛線表示示意
            ctx.strokeStyle = "rgba(160, 174, 192, 0.6)";

            ctx.beginPath();
            let curBallX = ballX;
            let curBallY = ballY;

            for (let step = 0; step <= currentStep; step++) {
              const t = step / numSteps;
              const flightX = ballX + drawWidth * 0.25 * t;
              const parabola = 4 * t * (1 - t * 0.55);
              const flightY = ballY - drawHeight * 0.32 * parabola;

              if (step === 0) ctx.moveTo(flightX, flightY);
              else ctx.lineTo(flightX, flightY);

              if (step === currentStep) {
                curBallX = flightX;
                curBallY = flightY;
              }
            }
            ctx.stroke();

            ctx.fillStyle = "rgba(255, 255, 255, 0.8)";
            ctx.beginPath();
            ctx.arc(curBallX, curBallY, 2.5, 0, Math.PI * 2);
            ctx.fill();

            ctx.font = "italic 9px sans-serif";
            ctx.fillStyle = "rgba(203, 213, 225, 0.85)";
            ctx.fillText("理論出球示意 (未捕捉到實測球體)", curBallX + 8, curBallY - 4);
          }
          ctx.restore();
        }
      }

      // 4. 人體骨架連線 (2D Pose) - 細緻半透明，只在有效揮桿區間內顯示！
      if (showSkeleton && currentTimeMs >= swing.start_ms && currentTimeMs <= swing.end_ms + 200) {
        const connections: Array<[string, string]> = [
          ["left_shoulder", "right_shoulder"],
          ["left_shoulder", "left_hip"],
          ["right_shoulder", "right_hip"],
          ["left_hip", "right_hip"],
          ["right_shoulder", "right_elbow"],
          ["right_elbow", "right_wrist"],
          ["left_shoulder", "left_elbow"],
          ["left_elbow", "left_wrist"],
          ["right_hip", "right_knee"],
          ["right_knee", "right_ankle"],
          ["left_hip", "left_knee"],
          ["left_knee", "left_ankle"],
        ];

        ctx.save();
        ctx.strokeStyle = "rgba(52, 211, 153, 0.65)";
        ctx.lineWidth = 1.5;
        for (const [a, b] of connections) {
          const pa = lms[a];
          const pb = lms[b];
          if (pa && pb && pa.visibility >= 0.35 && pb.visibility >= 0.35) {
            ctx.beginPath();
            ctx.moveTo(toX(pa.x), toY(pa.y));
            ctx.lineTo(toX(pb.x), toY(pb.y));
            ctx.stroke();
          }
        }

        for (const [name, pt] of Object.entries(lms)) {
          if (pt.visibility < 0.35) continue;
          if (!name.includes("wrist") && !name.includes("shoulder") && !name.includes("hip") && !name.includes("knee")) {
            continue;
          }
          ctx.fillStyle = name.includes("wrist") ? "#f59e0b" : "#10b981";
          ctx.beginPath();
          ctx.arc(toX(pt.x), toY(pt.y), 2.5, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.restore();
      }

      // 5. 揮桿手腕軌跡 (Swing Path)
      if (showSwingPath && currentTimeMs >= swing.start_ms && currentTimeMs <= swing.end_ms + 300) {
        const backswingPts: Array<{ x: number; y: number }> = [];
        const downswingPts: Array<{ x: number; y: number }> = [];

        for (const kf of swing.keyframes) {
          const klms = kf.landmarks || {};
          const rw = klms["right_wrist"];
          const lw = klms["left_wrist"];
          const wrist = rw && rw.visibility >= 0.3 ? rw : lw;
          if (wrist && wrist.visibility >= 0.3) {
            const pt = { x: toX(wrist.x), y: toY(wrist.y) };
            if (kf.time_ms <= topMs) {
              backswingPts.push(pt);
            } else if (kf.time_ms <= impactMs) {
              downswingPts.push(pt);
            }
          }
        }

        ctx.save();
        if (backswingPts.length >= 2) {
          ctx.strokeStyle = "rgba(0, 240, 255, 0.75)";
          ctx.lineWidth = 2.0;
          ctx.beginPath();
          ctx.moveTo(backswingPts[0].x, backswingPts[0].y);
          for (let i = 1; i < backswingPts.length; i++) {
            ctx.lineTo(backswingPts[i].x, backswingPts[i].y);
          }
          ctx.stroke();
        }
        if (downswingPts.length >= 2) {
          ctx.strokeStyle = "rgba(255, 42, 95, 0.85)";
          ctx.lineWidth = 2.2;
          ctx.beginPath();
          ctx.moveTo(downswingPts[0].x, downswingPts[0].y);
          for (let i = 1; i < downswingPts.length; i++) {
            ctx.lineTo(downswingPts[i].x, downswingPts[i].y);
          }
          ctx.stroke();
        }
        ctx.restore();
      }
    },
    [showSkeleton, showSwingPath, showHeadBox, showBallTracer, showProGhost, swing]
  );

  useEffect(() => {
    if (swing) {
      drawPoseOverlay(swing.start_ms);
    }
  }, [swing, showSkeleton, showSwingPath, showHeadBox, showBallTracer, showProGhost, drawPoseOverlay]);

  const changePlaybackSpeed = (speed: number) => {
    setPlaybackSpeed(speed);
    if (videoRef.current) {
      videoRef.current.playbackRate = speed;
    }
  };

  const stepFrame = (deltaMs: number) => {
    if (!videoRef.current) return;
    const nextSec = Math.max(0, videoRef.current.currentTime + deltaMs / 1000);
    videoRef.current.currentTime = nextSec;
    drawPoseOverlay(Math.round(nextSec * 1000));
  };

  const jumpToEvent = (timeMs: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = timeMs / 1000;
    }
    drawPoseOverlay(timeMs);
  };

  const getSubscoreJumpTimeMs = (subKey: string): number | null => {
    if (!swing || !swing.events) return null;
    const evMap: Record<string, number> = {};
    for (const ev of swing.events) {
      evMap[ev.event_name] = ev.time_ms;
    }
    if (subKey === "spine_tilt_stability") return evMap["top"] || evMap["address"] || swing.start_ms;
    if (subKey === "head_stability") return evMap["impact_estimated"] || evMap["impact"] || evMap["top"] || swing.start_ms;
    if (subKey === "path_repeatability") return evMap["downswing"] || evMap["top"] || swing.start_ms;
    if (subKey === "tempo_consistency") return evMap["top"] || swing.start_ms;
    if (subKey === "finish_balance") return evMap["finish"] || evMap["follow_through"] || swing.end_ms;
    return null;
  };


  const handleSaveCalibration = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveBanner(null);
    try {
      const updated = await apiFetch<SwingSegmentItem>(
        `/api/swings/${swingId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            start_ms: Number(startMs),
            end_ms: Number(endMs),
            label,
            ball_strike_status: ballStrike,
            notes,
            feedback_category: "manual_calibration",
            feedback_note: feedbackNote || "使用者於單球詳情頁微調時間碼與標記",
          }),
        }
      );
      setSwing(updated);
      setSaveBanner("已儲存人工校正並即時更新可解釋評分與回饋紀錄！");
    } finally {
      setSaving(false);
    }
  };

  if (!swing) {
    return (
      <div className="py-16 text-center text-sm text-gray-400">
        載入單球揮桿分析資料中...
      </div>
    );
  }

  const cov = formatCoverageStatus(swing.overall_score, swing.coverage_ratio);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            href={`/sessions/${swing.session_id}`}
            className="text-xs font-semibold text-emerald-400 hover:underline"
          >
            &larr; 返回練習場次時間軸
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-white">
            第 #{swing.sequence_no} 球 — 2D 動作指標與可解釋評分
          </h1>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-400">
            評分版本：{swing.score_version} · 模型：{swing.model_version}
          </div>
          <div className="text-xl font-bold text-emerald-400">
            綜合動作分：{cov.displayScore}
          </div>
        </div>
      </div>

      {/* 播放器、骨架 Canvas 疊圖與逐幀控制 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7 space-y-3">
          <div className="relative overflow-hidden rounded-2xl border border-gray-800 bg-black">
            <video
              ref={videoRef}
              controls
              playsInline
              preload="metadata"
              onTimeUpdate={(e) =>
                drawPoseOverlay(Math.round(e.currentTarget.currentTime * 1000))
              }
              src={`${API_BASE_URL}/api/videos/${swing.video_id}/stream?token=${encodeURIComponent(getAuthToken() || "")}#t=${(swing.start_ms / 1000).toFixed(2)},${(swing.end_ms / 1000).toFixed(2)}`}
              className="aspect-video w-full"
            />
            <canvas
              ref={canvasRef}
              width={640}
              height={480}
              className="pointer-events-none absolute inset-0 h-full w-full"
            />
            {/* 軌跡圖例與提示 */}
            <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap items-center gap-2 rounded-lg bg-black/60 px-2.5 py-1.5 text-[11px] backdrop-blur-sm">
              <span className="flex items-center gap-1 text-[#00f0ff] font-bold">
                <span className="inline-block h-2 w-3 rounded-sm bg-[#00f0ff]" />
                上桿軌跡
              </span>
              <span className="text-gray-500">|</span>
              <span className="flex items-center gap-1 text-[#ff2a5f] font-bold">
                <span className="inline-block h-2 w-3 rounded-sm bg-[#ff2a5f]" />
                下桿軌跡
              </span>
              <span className="text-gray-500">|</span>
              <span className="flex items-center gap-1 text-amber-400 font-bold">
                <span className="inline-block h-2 w-2 rounded-full border border-amber-400" />
                頭部基準
              </span>
              <span className="text-gray-500">|</span>
              <span className="flex items-center gap-1 text-[#39ff14] font-bold">
                <span className="inline-block h-2 w-2 rounded-full bg-[#39ff14]" />
                出球動態軌跡 (Tracer)
              </span>
              <span className="text-gray-500">|</span>
              <span className="flex items-center gap-1 text-[#fbbf24] font-bold">
                <span className="inline-block h-2 w-3 rounded-sm border border-dashed border-[#fbbf24] bg-[#fbbf24]/20" />
                👑 PGA 職業幽靈疊影 (HUD)
              </span>
            </div>
          </div>

          {/* 慢動作播放與逐幀控制列 */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-gray-400 font-medium">播放速度:</span>
              {[
                { label: "1.0x 原速", val: 1.0 },
                { label: "0.5x 慢速", val: 0.5 },
                { label: "0.25x 超慢動作", val: 0.25 },
              ].map((sp) => (
                <button
                  key={sp.val}
                  type="button"
                  onClick={() => changePlaybackSpeed(sp.val)}
                  className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                    playbackSpeed === sp.val
                      ? "bg-emerald-500 text-black shadow-sm"
                      : "border border-gray-700 bg-black/40 text-gray-300 hover:border-gray-500"
                  }`}
                >
                  {sp.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => stepFrame(-33)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1 font-semibold text-white hover:border-emerald-500"
              >
                &larr; -33ms (前一幀)
              </button>
              <button
                type="button"
                onClick={() => stepFrame(33)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1 font-semibold text-white hover:border-emerald-500"
              >
                +33ms (後一幀) &rarr;
              </button>
            </div>
          </div>

          {/* 視覺圖層開關 */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <button
              type="button"
              onClick={() => setShowSwingPath((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showSwingPath
                  ? "bg-cyan-600 text-white"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showSwingPath ? "✓ 顯示揮桿軌跡 (上桿藍/下桿紅)" : "隱藏揮桿軌跡"}
            </button>
            <button
              type="button"
              onClick={() => setShowHeadBox((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showHeadBox
                  ? "bg-amber-600 text-white"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showHeadBox ? "✓ 顯示頭部穩定基準圈" : "隱藏頭部基準圈"}
            </button>
            <button
              type="button"
              onClick={() => setShowSkeleton((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showSkeleton
                  ? "bg-emerald-600 text-white"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showSkeleton ? "✓ 顯示人體骨架連線" : "隱藏人體骨架"}
            </button>
            <button
              type="button"
              onClick={() => setShowBallTracer((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showBallTracer
                  ? "bg-lime-500 text-black font-bold shadow-sm"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showBallTracer ? "✓ 顯示出球動態軌跡 (Ball Tracer)" : "隱藏出球動態軌跡"}
            </button>
            <button
              type="button"
              onClick={() => setShowProGhost((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showProGhost
                  ? "bg-gradient-to-r from-amber-500 to-yellow-500 text-black font-bold shadow-md"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showProGhost ? "✓ 👑 PGA 職業幽靈疊影 (HUD)" : "👑 PGA 職業幽靈疊影"}
            </button>
          </div>

          {/* 9 階段關鍵事件跳轉按鈕 */}
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
            <h2 className="mb-2.5 text-xs font-bold text-gray-300">
              揮桿關鍵階段事件 (點擊跳轉對應時間碼；Impact 明確標記為 estimated)
            </h2>
            <div className="flex flex-wrap gap-2">
              {(swing.events || []).map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => jumpToEvent(ev.time_ms)}
                  className="rounded-xl border border-emerald-800/60 bg-emerald-950/30 px-3 py-1.5 text-left text-xs transition hover:border-emerald-400 hover:bg-emerald-900/40"
                >
                  <div className="font-bold text-emerald-300">
                    {ev.event_name}
                  </div>
                  <div className="text-[10px] text-gray-400">
                    {formatMsToTimestamp(ev.time_ms)} · 信心{" "}
                    {Math.round(ev.confidence * 100)}%
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 右側：5 子分數與「怎麼算的？」展開說明 */}
        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white">
                5 項可解釋動作子分數
              </h2>
              <span className="rounded bg-emerald-950 px-2 py-0.5 text-[11px] text-emerald-300">
                {cov.badgeText}
              </span>
            </div>

            {cov.isInsufficient && (
              <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 p-3 text-xs text-amber-200">
                此球有效 2D 指標權重覆蓋率低於 70%，系統依誠實門檻不輸出綜合總分 (overall_score = null)，僅顯示已觀測之單項指標。
              </div>
            )}

            <div className="space-y-2.5">
              {Object.entries(swing.subscores || {})
                .filter(
                  ([k, sub]: [string, any]) =>
                    k !== "ig_visual_breakdown" &&
                    sub &&
                    typeof sub.weight === "number"
                )
                .map(([k, sub]: [string, any]) => {
                  const isOpen = expandedSubscore === k;
                  const jumpMs = getSubscoreJumpTimeMs(k);
                  const isNullScore = sub.score === null || sub.score === undefined;
                  return (
                    <div
                      key={k}
                      className="rounded-xl border border-gray-800 bg-black/40 p-3.5 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-bold text-white">
                            {sub.label_zh || sub.label || k}
                          </span>
                          <span className="ml-2 text-[11px] text-gray-400">
                            (權重{" "}
                            {Math.round(
                              (sub.weight || 0) > 1
                                ? sub.weight
                                : (sub.weight || 0) * 100
                            )}
                            %)
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-sm font-bold ${
                              isNullScore ? "text-gray-500 italic" : "text-emerald-400"
                            }`}
                          >
                            {!isNullScore ? `${sub.score} 分` : "無法評分 (null)"}
                          </span>
                          {jumpMs !== null && (
                            <button
                              type="button"
                              onClick={() => jumpToEvent(jumpMs)}
                              className="rounded border border-sky-800/60 bg-sky-950/40 px-2 py-0.5 text-[10px] font-semibold text-sky-300 hover:bg-sky-900/60 transition"
                              title="跳轉至對應關鍵檢核影格"
                            >
                              🎯 影格
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedSubscore(isOpen ? null : k)
                            }
                            className="rounded border border-emerald-700/60 bg-emerald-950/50 px-2 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-800 transition"
                          >
                            怎麼算的？
                          </button>
                        </div>
                      </div>

                      {isOpen && (
                        <div className="mt-2.5 space-y-1.5 border-t border-gray-800 pt-2.5 text-[11px] text-gray-300">
                          <div>
                            <strong className="text-white">
                              計算公式與依據：
                            </strong>
                            <p className="mt-0.5 text-gray-300 leading-relaxed">
                              {sub.how_calculated}
                            </p>
                          </div>
                          {isNullScore && (
                            <div className="rounded bg-amber-950/30 p-2 text-[10px] text-amber-200 border border-amber-900/40">
                              ⚠ 依誠實原則不虛構分數：{sub.how_calculated}
                            </div>
                          )}
                          <div className="flex flex-wrap gap-3 text-gray-400">
                            <span>
                              實測原始值：{sub.raw_value !== null && sub.raw_value !== undefined ? sub.raw_value : "無可靠觀測"} {sub.unit || ""}
                            </span>
                            <span>
                              數學公式：{sub.formula || sub.ideal_range || "score-v2"}
                            </span>
                            <span>
                              信心度：{Math.round((sub.confidence || 0) * 100)}%
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>

            <div className="mt-3 rounded-xl border border-amber-800/40 bg-amber-950/20 p-3 text-xs">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-bold text-amber-300">
                    IG 視覺吸睛分 (ig_visual_score)
                  </span>
                  <span className="ml-2 text-[10px] text-gray-400">
                    (構圖 30% · 收桿 25% · 節奏 20% · 畫質 15% · 剪輯 10%)
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-bold text-amber-300">
                    {swing.ig_visual_score !== null && swing.ig_visual_score !== undefined
                      ? `${swing.ig_visual_score} 分`
                      : "資料不足 (null)"}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedSubscore(expandedSubscore === "ig" ? null : "ig")
                    }
                    className="rounded border border-amber-700/60 bg-amber-950/50 px-2 py-0.5 text-[10px] text-amber-300 hover:bg-amber-800"
                  >
                    細項
                  </button>
                </div>
              </div>

              {expandedSubscore === "ig" && (
                <div className="mt-2.5 space-y-1.5 border-t border-amber-900/40 pt-2 text-[11px] text-gray-300">
                  <div className="text-amber-200 font-semibold">真實 IG 構圖與視覺檢核分解：</div>
                  {(() => {
                    const igBk = (swing.subscores as any)?.ig_visual_breakdown;
                    if (!igBk) return <div className="text-gray-500">尚無詳細視覺拆解資料</div>;
                    return (
                      <div className="space-y-1 text-gray-400">
                        <div>· 畫面完整度 (30%)：{igBk.framing_30 ?? "無真實人體入鏡數據"} 分</div>
                        <div>· 收桿流暢度 (25%)：{igBk.finish_25 ?? "無"} 分</div>
                        <div>· 節奏觀感 (20%)：{igBk.tempo_20 ?? "無"} 分</div>
                        <div>· 清晰與晃動 (15%)：{igBk.clarity_15 ?? "無"} 分</div>
                        <div>· 剪輯緩衝 (10%)：{igBk.clip_margin_10 ?? "無"} 分</div>
                        {igBk.details?.out_of_frame_flags?.length > 0 && (
                          <div className="text-red-400">
                            ⚠ 出界扣分項目：{igBk.details.out_of_frame_flags.join(", ")}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}
              <p className="mt-1 text-[11px] text-gray-400">
                獨立評量畫面構圖、亮度清晰度與收桿流暢度，絕不混入技術動作總分。
              </p>
            </div>
          </div>

          {/* 人工校正與回饋表單 */}
          <form
            onSubmit={handleSaveCalibration}
            className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-3 text-xs"
          >
            <h2 className="text-sm font-bold text-white">
              人工時間軸校正與標記回饋
            </h2>
            {saveBanner && (
              <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/50 p-2.5 text-emerald-200">
                {saveBanner}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-gray-400">起點 (start_ms)</label>
                <input
                  type="number"
                  value={startMs}
                  onChange={(e) => setStartMs(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
                />
              </div>
              <div>
                <label className="block text-gray-400">終點 (end_ms)</label>
                <input
                  type="number"
                  value={endMs}
                  onChange={(e) => setEndMs(Number(e.target.value))}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-gray-400">揮桿分類</label>
                <select
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
                >
                  <option value="valid_swing">正式揮桿 (valid_swing)</option>
                  <option value="practice_swing">空揮練習 (practice_swing)</option>
                </select>
              </div>
              <div>
                <label className="block text-gray-400">擊球狀態</label>
                <select
                  value={ballStrike}
                  onChange={(e) => setBallStrike(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
                >
                  <option value="confirmed_strike">確認擊球 (confirmed_strike)</option>
                  <option value="estimated_strike">疑似擊球 (estimated_strike)</option>
                  <option value="no_ball">空揮無球 (no_ball)</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-gray-400">本球筆記</label>
              <input
                type="text"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="例如：收桿平衡良好、擊球紮實"
                className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
              />
            </div>

            <div>
              <label className="block text-gray-400">
                校正原因備註 (寫入 SegmentFeedback 訓練回饋紀錄)
              </label>
              <input
                type="text"
                value={feedbackNote}
                onChange={(e) => setFeedbackNote(e.target.value)}
                placeholder="例如：微調起桿前 50ms 準備緩衝"
                className="mt-1 w-full rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="w-full rounded-xl bg-emerald-600 py-2.5 font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {saving ? "儲存並重新計算中..." : "儲存人工校正並更新評分"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
