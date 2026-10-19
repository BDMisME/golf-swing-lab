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
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!swing?.keyframes?.length) return;

      const events = swing.events || [];
      const topEv = events.find((e) => e.event_name === "top");
      const impactEv = events.find(
        (e) => e.event_name === "impact_estimated" || e.event_name === "impact"
      );
      const topMs = topEv?.time_ms || (swing.start_ms + swing.end_ms) * 0.45;
      const impactMs = impactEv?.time_ms || (swing.start_ms + swing.end_ms) * 0.7;

      // 1. 繪製手腕/桿頭揮桿軌跡 (Swing Path)
      if (showSwingPath) {
        const backswingPts: Array<{ x: number; y: number }> = [];
        const downswingPts: Array<{ x: number; y: number }> = [];

        for (const kf of swing.keyframes) {
          const lms = kf.landmarks || {};
          const rw = lms["right_wrist"];
          const lw = lms["left_wrist"];
          const wrist = (rw && rw.visibility >= 0.3) ? rw : lw;
          if (wrist && wrist.visibility >= 0.3) {
            const pt = { x: wrist.x * canvas.width, y: wrist.y * canvas.height };
            if (kf.time_ms <= topMs) {
              backswingPts.push(pt);
            } else if (kf.time_ms <= impactMs) {
              downswingPts.push(pt);
            }
          }
        }

        // 上桿天藍色軌跡
        if (backswingPts.length >= 2) {
          ctx.save();
          ctx.strokeStyle = "#00f0ff";
          ctx.lineWidth = 3.5;
          ctx.shadowColor = "#00f0ff";
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.moveTo(backswingPts[0].x, backswingPts[0].y);
          for (let i = 1; i < backswingPts.length; i++) {
            ctx.lineTo(backswingPts[i].x, backswingPts[i].y);
          }
          ctx.stroke();
          ctx.restore();
        }

        // 下桿鮮紅色軌跡 (熾熱紅，強調釋放加速)
        if (downswingPts.length >= 2) {
          ctx.save();
          ctx.strokeStyle = "#ff2a5f";
          ctx.lineWidth = 4.5;
          ctx.shadowColor = "#ff2a5f";
          ctx.shadowBlur = 10;
          ctx.beginPath();
          ctx.moveTo(downswingPts[0].x, downswingPts[0].y);
          for (let i = 1; i < downswingPts.length; i++) {
            ctx.lineTo(downswingPts[i].x, downswingPts[i].y);
          }
          ctx.stroke();
          ctx.restore();
        }

        // 標記頂點 TOP 與擊球 IMPACT 光環
        if (backswingPts.length > 0) {
          const topPt = backswingPts[backswingPts.length - 1];
          ctx.save();
          ctx.fillStyle = "#00f0ff";
          ctx.shadowColor = "#00f0ff";
          ctx.shadowBlur = 12;
          ctx.beginPath();
          ctx.arc(topPt.x, topPt.y, 6, 0, Math.PI * 2);
          ctx.fill();
          ctx.font = "bold 10px sans-serif";
          ctx.fillText("TOP 上桿頂點", topPt.x + 8, topPt.y - 4);
          ctx.restore();
        }

        if (downswingPts.length > 0) {
          const impPt = downswingPts[downswingPts.length - 1];
          ctx.save();
          ctx.fillStyle = "#ff2a5f";
          ctx.shadowColor = "#ff2a5f";
          ctx.shadowBlur = 14;
          ctx.beginPath();
          ctx.arc(impPt.x, impPt.y, 7, 0, Math.PI * 2);
          ctx.fill();
          ctx.font = "bold 10px sans-serif";
          ctx.fillText("IMPACT 擊球點", impPt.x + 8, impPt.y + 4);
          ctx.restore();
        }
      }

      // 尋找最接近當前毫秒之關鍵幀
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

      // 2. 繪製頭部穩定基準圈 (Head Box)
      if (showHeadBox) {
        const firstKf = swing.keyframes[0];
        const initialNose = firstKf?.landmarks?.["nose"];
        if (initialNose && initialNose.visibility >= 0.4) {
          const hx = initialNose.x * canvas.width;
          const hy = initialNose.y * canvas.height;
          ctx.save();
          ctx.strokeStyle = "#fbbf24"; // 金黃色基準圈
          ctx.lineWidth = 2;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.arc(hx, hy, 18, 0, Math.PI * 2);
          ctx.stroke();
          ctx.font = "9px sans-serif";
          ctx.fillStyle = "#fbbf24";
          ctx.fillText("頭部基準", hx - 18, hy - 22);
          ctx.restore();

          // 當前頭部位置
          const currNose = lms["nose"];
          if (currNose && currNose.visibility >= 0.4) {
            const cx = currNose.x * canvas.width;
            const cy = currNose.y * canvas.height;
            const dist = Math.hypot(cx - hx, cy - hy);
            ctx.save();
            ctx.fillStyle = dist > 15 ? "#ef4444" : "#10b981";
            ctx.beginPath();
            ctx.arc(cx, cy, 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }
      }

      // 3. 繪製 2D 骨架連線
      if (showSkeleton) {
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

        ctx.strokeStyle = "#34d399";
        ctx.lineWidth = 2.5;
        for (const [a, b] of connections) {
          const pa = lms[a];
          const pb = lms[b];
          if (pa && pb && pa.visibility >= 0.35 && pb.visibility >= 0.35) {
            ctx.beginPath();
            ctx.moveTo(pa.x * canvas.width, pa.y * canvas.height);
            ctx.lineTo(pb.x * canvas.width, pb.y * canvas.height);
            ctx.stroke();
          }
        }

        for (const [name, pt] of Object.entries(lms)) {
          if (pt.visibility < 0.35) continue;
          ctx.fillStyle = name.includes("wrist")
            ? "#f59e0b"
            : name.includes("shoulder") || name.includes("hip")
            ? "#10b981"
            : "#6ee7b7";
          ctx.beginPath();
          ctx.arc(pt.x * canvas.width, pt.y * canvas.height, 4, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    },
    [showSkeleton, showSwingPath, showHeadBox, swing]
  );

  useEffect(() => {
    if (swing) {
      drawPoseOverlay(swing.start_ms);
    }
  }, [swing, showSkeleton, showSwingPath, showHeadBox, drawPoseOverlay]);

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
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-emerald-400">
                            {typeof sub.score === "number"
                              ? `${sub.score} 分`
                              : "資料不足"}
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedSubscore(isOpen ? null : k)
                            }
                            className="rounded border border-emerald-700/60 bg-emerald-950/50 px-2 py-0.5 text-[11px] text-emerald-300 hover:bg-emerald-800"
                          >
                            怎麼算的？
                          </button>
                        </div>
                      </div>

                      {isOpen && (
                        <div className="mt-2.5 space-y-1 border-t border-gray-800 pt-2.5 text-[11px] text-gray-300">
                          <div>
                            <strong className="text-white">
                              計算公式與依據：
                            </strong>
                            {sub.how_calculated}
                          </div>
                          <div className="flex flex-wrap gap-3 text-gray-400">
                            <span>
                              實測原始值：{sub.raw_value ?? "N/A"} {sub.unit || ""}
                            </span>
                            <span>
                              數學公式：{sub.formula || sub.ideal_range || "score-v1"}
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
                <span className="font-bold text-amber-300">
                  IG 視覺吸睛分 (ig_visual_score)
                </span>
                <span className="text-sm font-bold text-amber-300">
                  {swing.ig_visual_score ?? "N/A"} 分
                </span>
              </div>
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
