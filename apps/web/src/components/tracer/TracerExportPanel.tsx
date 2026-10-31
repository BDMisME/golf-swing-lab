"use client";

import React from "react";
import { buildAuthenticatedMediaUrl } from "../../lib/tracer/transforms";
import type {
  AudioMode,
  ExportAspectRatio,
  TracerExportItem,
} from "../../lib/tracer/types";

interface TracerExportPanelProps {
  previewAspect: ExportAspectRatio;
  onPreviewAspectChange: (aspect: ExportAspectRatio) => void;
  exportFps: 30 | 60;
  onExportFpsChange: (fps: 30 | 60) => void;
  audioMode: AudioMode;
  onAudioModeChange: (mode: AudioMode) => void;
  onTriggerExport: () => void;
  latestExport: TracerExportItem | null;
  isExporting: boolean;
}

export default function TracerExportPanel({
  previewAspect,
  onPreviewAspectChange,
  exportFps,
  onExportFpsChange,
  audioMode,
  onAudioModeChange,
  onTriggerExport,
  latestExport,
  isExporting,
}: TracerExportPanelProps) {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-4 text-xs text-slate-200">
      <div>
        <h3 className="text-sm font-bold text-white">
          高畫質特效影片匯出與對齊驗證
        </h3>
        <p className="text-[11px] text-slate-400">
          輸出 H.264 (yuv420p, +faststart) MP4 與 .tracer.json 完整溯源 Sidecar
        </p>
      </div>

      {/* 構圖比例、FPS、音訊設定 */}
      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1">
          <div className="text-[11px] text-slate-400 font-medium">構圖比例</div>
          <div className="flex flex-col gap-1">
            {(["original", "9:16", "16:9"] as ExportAspectRatio[]).map(
              (ratio) => (
                <button
                  key={ratio}
                  type="button"
                  data-testid={`export-aspect-${ratio}`}
                  onClick={() => onPreviewAspectChange(ratio)}
                  className={`py-1.5 px-2 rounded-lg border text-left font-mono transition ${
                    previewAspect === ratio
                      ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                      : "bg-slate-950/60 border-slate-800 text-slate-400"
                  }`}
                >
                  {ratio === "original" ? "Original 原始" : ratio}
                </button>
              )
            )}
          </div>
        </div>

        <div className="space-y-1">
          <div className="text-[11px] text-slate-400 font-medium">輸出幀率 (CFR)</div>
          <div className="flex flex-col gap-1">
            {([60, 30] as Array<30 | 60>).map((fpsVal) => (
              <button
                key={fpsVal}
                type="button"
                data-testid={`export-fps-${fpsVal}`}
                onClick={() => onExportFpsChange(fpsVal)}
                className={`py-1.5 px-2 rounded-lg border text-left font-mono transition ${
                  exportFps === fpsVal
                    ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                    : "bg-slate-950/60 border-slate-800 text-slate-400"
                }`}
              >
                {fpsVal} FPS ({fpsVal}/1)
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <div className="text-[11px] text-slate-400 font-medium">擊球音訊</div>
          <div className="flex flex-col gap-1">
            {(["preserve", "mute"] as AudioMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                data-testid={`export-audio-${mode}`}
                onClick={() => onAudioModeChange(mode)}
                className={`py-1.5 px-2 rounded-lg border text-left transition ${
                  audioMode === mode
                    ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                    : "bg-slate-950/60 border-slate-800 text-slate-400"
                }`}
              >
                {mode === "preserve" ? "🔊 保留擊球原音" : "🔇 靜音輸出"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 觸發匯出按鈕 */}
      <button
        type="button"
        data-testid="btn-start-tracer-export"
        disabled={isExporting}
        onClick={onTriggerExport}
        className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-cyan-500 to-sky-500 hover:from-cyan-400 hover:to-sky-400 text-slate-950 font-bold text-xs shadow-lg disabled:opacity-50 transition"
      >
        {isExporting
          ? "⏳ 正在逐幀渲染雙軌特效並驗證對齊..."
          : `🎬 立即匯出 ${previewAspect} · ${exportFps}fps MP4`}
      </button>

      {/* 最新匯出成果與 Parity 證據卡 */}
      {latestExport && (
        <div
          data-testid="export-result-card"
          className="bg-slate-950/90 border border-slate-800 rounded-xl p-3 space-y-2"
        >
          <div className="flex items-center justify-between">
            <span className="font-bold text-emerald-300">
              匯出狀態: {latestExport.state.toUpperCase()}
            </span>
            <span className="font-mono text-[11px] text-slate-400">
              {latestExport.output_width}x{latestExport.output_height} ·{" "}
              {latestExport.fps}fps ·{" "}
              {(latestExport.size_bytes / 1024).toFixed(1)} KB
            </span>
          </div>

          {latestExport.parity_report && (
            <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-900/80 p-2 rounded-lg border border-slate-800">
              <div>
                Preview/Export 最大像素差:{" "}
                <span className="font-mono text-cyan-300">
                  {latestExport.parity_report.max_coordinate_error_px ?? 0} px
                </span>{" "}
                (門檻 ≤2.0px)
              </div>
              <div>
                PTS 最大幀差:{" "}
                <span className="font-mono text-cyan-300">
                  {latestExport.parity_report.max_frame_delta_frames ?? 0} F
                </span>{" "}
                (門檻 ≤1.0F)
              </div>
            </div>
          )}

          {latestExport.state === "completed" && latestExport.download_url && (
            <div className="flex items-center gap-2 pt-1">
              <a
                href={buildAuthenticatedMediaUrl(latestExport.download_url)}
                download
                data-testid="link-download-tracer-mp4"
                className="flex-1 text-center py-1.5 px-3 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 font-semibold"
              >
                ⬇ 下載特效 MP4
              </a>
              {latestExport.sidecar_url && (
                <a
                  href={buildAuthenticatedMediaUrl(latestExport.sidecar_url)}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="link-download-tracer-sidecar"
                  className="py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-mono text-[11px]"
                >
                  📄 .tracer.json 溯源檔
                </a>
              )}
            </div>
          )}

          {latestExport.error_message && (
            <div className="text-rose-400 text-[11px]">
              錯誤: {latestExport.error_message}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
