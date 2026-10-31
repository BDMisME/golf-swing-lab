"use client";

import React from "react";
import { formatPtsUsToTimecode } from "../../lib/tracer/transforms";
import type {
  CanonicalTrackPoint,
  TracerAnchorRevision,
} from "../../lib/tracer/types";

interface TracerTimelineProps {
  clipStartPtsUs: number;
  clipEndPtsUs: number;
  currentPtsUs: number;
  fps: number;
  isPlaying: boolean;
  onPlayingChange: (playing: boolean) => void;
  onPtsUsChange: (ptsUs: number) => void;
  anchors: TracerAnchorRevision | null;
  onSetTemporalAnchorAtCurrentPts: (
    anchorKey:
      | "address_pts_us"
      | "top_pts_us"
      | "impact_pts_us"
      | "finish_pts_us"
      | "launch_pts_us"
  ) => void;
  swingPoints: CanonicalTrackPoint[];
  shotPoints: CanonicalTrackPoint[];
}

export default function TracerTimeline({
  clipStartPtsUs,
  clipEndPtsUs,
  currentPtsUs,
  fps,
  isPlaying,
  onPlayingChange,
  onPtsUsChange,
  anchors,
  onSetTemporalAnchorAtCurrentPts,
  swingPoints,
  shotPoints,
}: TracerTimelineProps) {
  const frameStepUs = Math.max(4_000, Math.round(1_000_000 / Math.max(15, fps)));
  const spanUs = Math.max(100_000, clipEndPtsUs - clipStartPtsUs);

  const stepFrames = (deltaFrames: number) => {
    onPlayingChange(false);
    const next = Math.min(
      clipEndPtsUs,
      Math.max(clipStartPtsUs, currentPtsUs + deltaFrames * frameStepUs)
    );
    onPtsUsChange(next);
  };

  const anchorBadges: Array<{
    key:
      | "address_pts_us"
      | "top_pts_us"
      | "impact_pts_us"
      | "finish_pts_us"
      | "launch_pts_us";
    label: string;
    ptsUs: number | null | undefined;
    color: string;
  }> = [
    {
      key: "address_pts_us",
      label: "Address 準備",
      ptsUs: anchors?.address_pts_us,
      color: "bg-sky-500/20 text-sky-300 border-sky-500/40",
    },
    {
      key: "top_pts_us",
      label: "Top 頂點",
      ptsUs: anchors?.top_pts_us,
      color: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
    },
    {
      key: "impact_pts_us",
      label: "Impact 擊球",
      ptsUs: anchors?.impact_pts_us,
      color: "bg-orange-500/20 text-orange-300 border-orange-500/40",
    },
    {
      key: "launch_pts_us",
      label: "Launch 起飛",
      ptsUs: anchors?.launch_pts_us,
      color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
    },
    {
      key: "finish_pts_us",
      label: "Finish 收桿",
      ptsUs: anchors?.finish_pts_us,
      color: "bg-purple-500/20 text-purple-300 border-purple-500/40",
    },
  ];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-3">
      {/* 頂部時間碼與逐幀步進控制列 */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="btn-play-pause"
            onClick={() => onPlayingChange(!isPlaying)}
            className="px-3.5 py-1.5 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-semibold text-xs transition"
          >
            {isPlaying ? "⏸ 暫停" : "▶ 播放"}
          </button>
          <button
            type="button"
            data-testid="btn-step-prev-5"
            onClick={() => stepFrames(-5)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono"
          >
            -5F
          </button>
          <button
            type="button"
            data-testid="btn-step-prev-1"
            onClick={() => stepFrames(-1)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono"
          >
            -1F
          </button>
          <button
            type="button"
            data-testid="btn-step-next-1"
            onClick={() => stepFrames(1)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono"
          >
            +1F
          </button>
          <button
            type="button"
            data-testid="btn-step-next-5"
            onClick={() => stepFrames(5)}
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono"
          >
            +5F
          </button>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono text-slate-300">
          <span data-testid="current-pts-display" className="text-cyan-400 font-semibold">
            PTS: {formatPtsUsToTimecode(currentPtsUs)} ({currentPtsUs} us)
          </span>
          <span className="text-slate-500">|</span>
          <span>
            區間: {formatPtsUsToTimecode(clipStartPtsUs)} –{" "}
            {formatPtsUsToTimecode(clipEndPtsUs)}
          </span>
        </div>
      </div>

      {/* 主時間軸滑桿 */}
      <div className="space-y-1.5">
        <input
          type="range"
          data-testid="timeline-scrubber"
          min={clipStartPtsUs}
          max={clipEndPtsUs}
          step={Math.max(1000, Math.round(frameStepUs / 2))}
          value={Math.min(clipEndPtsUs, Math.max(clipStartPtsUs, currentPtsUs))}
          onChange={(e) => {
            onPlayingChange(false);
            onPtsUsChange(Number(e.target.value));
          }}
          className="w-full accent-cyan-400 cursor-pointer"
        />

        {/* 雙軌觀測密度視覺條 */}
        <div className="relative h-4 bg-slate-950 rounded-lg overflow-hidden border border-slate-800/80">
          {swingPoints.map((pt) => {
            const leftPct = Math.min(
              100,
              Math.max(0, ((pt.source_pts_us - clipStartPtsUs) / spanUs) * 100)
            );
            return (
              <div
                key={`s_${pt.source_pts_us}`}
                style={{ left: `${leftPct}%` }}
                className={`absolute top-0.5 w-1 h-1.5 rounded-full ${
                  pt.source_type === "detector_observed"
                    ? "bg-sky-400"
                    : pt.source_type === "manually_annotated"
                    ? "bg-emerald-400"
                    : "bg-amber-400/75"
                }`}
              />
            );
          })}
          {shotPoints.map((pt) => {
            const leftPct = Math.min(
              100,
              Math.max(0, ((pt.source_pts_us - clipStartPtsUs) / spanUs) * 100)
            );
            return (
              <div
                key={`b_${pt.source_pts_us}`}
                style={{ left: `${leftPct}%` }}
                className={`absolute bottom-0.5 w-1.5 h-1.5 rounded-full ${
                  pt.source_type === "detector_observed"
                    ? "bg-cyan-300"
                    : pt.source_type === "manually_annotated"
                    ? "bg-emerald-300"
                    : "bg-pink-400/80"
                }`}
              />
            );
          })}
        </div>
      </div>

      {/* 關鍵事件錨點快速跳轉與「設為當前幀」按鈕列 */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {anchorBadges.map((item) => (
          <div
            key={item.key}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-xl border text-xs ${item.color}`}
          >
            <button
              type="button"
              disabled={item.ptsUs == null}
              onClick={() => {
                if (item.ptsUs != null) {
                  onPlayingChange(false);
                  onPtsUsChange(item.ptsUs);
                }
              }}
              className="font-medium hover:underline disabled:opacity-50"
            >
              {item.label}:{" "}
              {item.ptsUs != null
                ? formatPtsUsToTimecode(item.ptsUs)
                : "未設定"}
            </button>
            <button
              type="button"
              data-testid={`set-anchor-${item.key}`}
              onClick={() => onSetTemporalAnchorAtCurrentPts(item.key)}
              title="將此事件錨點設為目前時間碼 (僅更新 Studio 修訂版，不影響 R3 主報告)"
              className="px-1.5 py-0.5 rounded bg-slate-950/60 hover:bg-slate-950 text-[10px] text-slate-200 border border-slate-700/60"
            >
              設為當前幀
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
