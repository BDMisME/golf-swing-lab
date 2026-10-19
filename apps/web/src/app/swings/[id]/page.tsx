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

  // 繪製 2D 骨架疊圖於 Canvas
  const drawPoseOverlay = useCallback(
    (currentTimeMs: number) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (!showSkeleton || !swing?.keyframes?.length) return;

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
      const connections: Array<[string, string]> = [
        ["left_shoulder", "right_shoulder"],
        ["left_shoulder", "left_hip"],
        ["right_shoulder", "right_hip"],
        ["left_hip", "right_hip"],
        ["right_shoulder", "right_elbow"],
        ["right_elbow", "right_wrist"],
        ["right_hip", "right_knee"],
        ["right_knee", "right_ankle"],
      ];

      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 3;
      for (const [a, b] of connections) {
        const pa = lms[a];
        const pb = lms[b];
        if (pa && pb && pa.visibility >= 0.4 && pb.visibility >= 0.4) {
          ctx.beginPath();
          ctx.moveTo(pa.x * canvas.width, pa.y * canvas.height);
          ctx.lineTo(pb.x * canvas.width, pb.y * canvas.height);
          ctx.stroke();
        }
      }

      for (const [name, pt] of Object.entries(lms)) {
        if (pt.visibility < 0.4) continue;
        ctx.fillStyle = name.includes("wrist") ? "#f59e0b" : "#34d399";
        ctx.beginPath();
        ctx.arc(pt.x * canvas.width, pt.y * canvas.height, 5, 0, Math.PI * 2);
        ctx.fill();
      }
    },
    [showSkeleton, swing]
  );

  useEffect(() => {
    if (swing) {
      drawPoseOverlay(swing.start_ms);
    }
  }, [swing, showSkeleton, drawPoseOverlay]);

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
              preload="metadata"
              onTimeUpdate={(e) =>
                drawPoseOverlay(Math.round(e.currentTarget.currentTime * 1000))
              }
              src={`${API_BASE_URL}/api/videos/${swing.video_id}/stream#t=${(swing.start_ms / 1000).toFixed(2)},${(swing.end_ms / 1000).toFixed(2)}`}
              className="aspect-video w-full"
            />
            <canvas
              ref={canvasRef}
              width={480}
              height={360}
              className="pointer-events-none absolute inset-0 h-full w-full"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => stepFrame(-33)}
                className="rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 font-semibold text-white hover:border-emerald-500"
              >
                &larr; 前一幀 (-33ms)
              </button>
              <button
                type="button"
                onClick={() => stepFrame(33)}
                className="rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 font-semibold text-white hover:border-emerald-500"
              >
                後一幀 (+33ms) &rarr;
              </button>
            </div>

            <button
              type="button"
              onClick={() => setShowSkeleton((v) => !v)}
              className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                showSkeleton
                  ? "bg-emerald-600 text-white"
                  : "border border-gray-700 text-gray-300"
              }`}
            >
              {showSkeleton ? "隱藏 2D 骨架疊圖" : "顯示 2D 骨架疊圖"}
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
