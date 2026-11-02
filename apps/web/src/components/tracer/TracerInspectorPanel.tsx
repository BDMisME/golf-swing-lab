"use client";

import React from "react";
import type {
  TrackType,
  TracerModelItem,
  TracerProjectDetail,
} from "../../lib/tracer/types";
import type { StudioEditToolMode } from "./TracerCanvasEditor";

interface TracerInspectorPanelProps {
  project: TracerProjectDetail;
  models: TracerModelItem[];
  activeTrackType: TrackType;
  onActiveTrackTypeChange: (trackType: TrackType) => void;
  toolMode: StudioEditToolMode;
  onToolModeChange: (mode: StudioEditToolMode) => void;
  showAnchorPoints: boolean;
  onShowAnchorPointsChange: (show: boolean) => void;
  onReanalyze: () => void;
  onRollbackToRevision1: (trackType: TrackType) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  onClearShotAnchors?: () => void;
  onJumpToPtsUs?: (ptsUs: number) => void;
  onDeletePointAtPtsUs?: (ptsUs: number) => void;
  currentPtsUs?: number;
  isBusy: boolean;
}

export default function TracerInspectorPanel({
  project,
  models,
  activeTrackType,
  onActiveTrackTypeChange,
  toolMode,
  onToolModeChange,
  showAnchorPoints,
  onShowAnchorPointsChange,
  onReanalyze,
  onRollbackToRevision1,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  onClearShotAnchors,
  onJumpToPtsUs,
  onDeletePointAtPtsUs,
  currentPtsUs = 0,
  isBusy,
}: TracerInspectorPanelProps) {
  const swingSummary = project.swing_track?.quality_summary;
  const shotSummary = project.shot_track?.quality_summary;
  const activePoints =
    activeTrackType === "club_head"
      ? project.swing_track?.points || []
      : project.shot_track?.points || [];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-4 text-xs text-slate-200">
      {/* 標題與重新執行高解析原片分析 */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white">
            可觀測性與逐幀精修工具箱
          </h3>
          <p className="text-[11px] text-slate-400">
            Copy-on-Write 修訂版保護 · 絕不覆寫 R3 原始分析與 Revision 1
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {onUndo && (
            <button
              type="button"
              data-testid="btn-undo-edit"
              disabled={isBusy || !canUndo}
              onClick={onUndo}
              className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold border border-slate-700 disabled:opacity-40"
              title="復原上一步修訂"
            >
              ↩ 復原
            </button>
          )}
          {onRedo && (
            <button
              type="button"
              data-testid="btn-redo-edit"
              disabled={isBusy || !canRedo}
              onClick={onRedo}
              className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold border border-slate-700 disabled:opacity-40"
              title="重做下一步修訂"
            >
              ↪ 重做
            </button>
          )}
          <button
            type="button"
            data-testid="btn-reanalyze-highres"
            disabled={isBusy}
            onClick={onReanalyze}
            className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-cyan-300 font-semibold border border-cyan-500/30 disabled:opacity-50"
          >
            {isBusy ? "處理中..." : "↻ 重新掃描高解析原片"}
          </button>
        </div>
      </div>

      {/* 編輯目標軌道與工具選擇 */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-slate-300">目前編輯軌道</span>
          <label className="flex items-center gap-1.5 cursor-pointer text-slate-300">
            <input
              type="checkbox"
              checked={showAnchorPoints}
              onChange={(e) => onShowAnchorPointsChange(e.target.checked)}
              className="accent-cyan-400"
            />
            <span>顯示逐幀控制點</span>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            data-testid="select-track-club-head"
            onClick={() => onActiveTrackTypeChange("club_head")}
            className={`py-2 px-3 rounded-xl font-semibold border text-left transition ${
              activeTrackType === "club_head"
                ? "bg-sky-500/20 border-sky-400 text-sky-200"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <div>🏌️ Swing 桿頭軌跡</div>
            <div className="text-[10px] opacity-80 font-mono">
              Rev #{project.active_swing_revision} · {project.swing_status}
            </div>
          </button>

          <button
            type="button"
            data-testid="select-track-ball"
            onClick={() => onActiveTrackTypeChange("ball")}
            className={`py-2 px-3 rounded-xl font-semibold border text-left transition ${
              activeTrackType === "ball"
                ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                : "bg-slate-950/60 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <div>⚪ Shot 飛球軌跡</div>
            <div className="text-[10px] opacity-80 font-mono">
              Rev #{project.active_shot_revision} · {project.shot_mode}
            </div>
          </button>
        </div>

        <div className="grid grid-cols-3 gap-1.5 pt-1">
          {[
            { id: "inspect", label: "🔍 檢視點位" },
            { id: "add_point", label: "➕ 新增當前幀點" },
            { id: "move_point", label: "✥ 拖曳當前幀點" },
            { id: "delete_point", label: "🗑️ 刪除當前幀點" },
            { id: "set_launch", label: "🚀 標定起飛球位" },
            { id: "set_apex", label: "⛰️ 標定最高點" },
            { id: "set_landing", label: "🎯 標定落點" },
          ].map((tool) => (
            <button
              key={tool.id}
              type="button"
              data-testid={`tool-${tool.id}`}
              onClick={() => onToolModeChange(tool.id as StudioEditToolMode)}
              className={`py-1.5 px-2 rounded-lg border text-[11px] font-medium transition ${
                toolMode === tool.id
                  ? "bg-emerald-500/20 border-emerald-400 text-emerald-200"
                  : "bg-slate-950/60 border-slate-800 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {tool.label}
            </button>
          ))}
          {onClearShotAnchors && (
            <button
              type="button"
              data-testid="btn-clear-shot-anchors"
              disabled={isBusy}
              onClick={onClearShotAnchors}
              className="col-span-2 py-1.5 px-2 rounded-lg border border-rose-500/30 bg-rose-950/30 hover:bg-rose-900/40 text-rose-200 text-[11px] font-medium transition disabled:opacity-50"
            >
              🧹 清除飛球空間錨點 (Launch/Apex/落點)
            </button>
          )}
        </div>
      </div>

      {/* P1-3: 當前軌道逐幀點位清單 (支援點擊跳幀與刪除) */}
      <div
        data-testid="inspector-point-list"
        className="bg-slate-950/80 border border-slate-800 rounded-xl p-2.5 space-y-1.5"
      >
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-semibold text-slate-300">
            軌道點位清單 ({activePoints.length} 點 · 僅當前幀 ±45ms 可直接拖拉)
          </span>
          <span className="font-mono text-slate-400">
            當前 PTS: {currentPtsUs} us
          </span>
        </div>
        {activePoints.length > 0 ? (
          <div className="max-h-28 overflow-y-auto space-y-1 pr-1">
            {activePoints.slice(0, 40).map((pt) => {
              const isNear = Math.abs(pt.source_pts_us - currentPtsUs) <= 45_000;
              return (
                <div
                  key={`${pt.source_pts_us}-${pt.revision}`}
                  className={`flex items-center justify-between px-2 py-1 rounded text-[10px] font-mono ${
                    isNear
                      ? "bg-cyan-500/20 border border-cyan-500/40 text-cyan-200"
                      : "bg-slate-900/80 text-slate-300"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onJumpToPtsUs && onJumpToPtsUs(pt.source_pts_us)}
                    className="text-left hover:underline"
                  >
                    F#{pt.source_frame_index} · {pt.source_pts_us}us · (
                    {pt.x_norm.toFixed(3)}, {pt.y_norm.toFixed(3)}) [
                    {pt.source_type}]
                  </button>
                  {onDeletePointAtPtsUs && (
                    <button
                      type="button"
                      onClick={() => onDeletePointAtPtsUs(pt.source_pts_us)}
                      className="text-rose-300 hover:text-rose-200 px-1"
                      title="刪除此點"
                    >
                      ✕
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-[11px] text-slate-500">
            目前軌道為 0 點；可使用「🚀 標定起飛球位 → ⛰️ 標定最高點 → 🎯 標定落點」或「➕ 新增當前幀點」建立人工軌跡。
          </div>
        )}
      </div>

      {/* Swing Tracer 證據與品質摘要卡 */}
      <div
        data-testid="swing-quality-card"
        className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 space-y-2"
      >
        <div className="flex items-center justify-between">
          <span className="font-bold text-sky-300">
            Swing Tracer 觀測品質 ({project.swing_status})
          </span>
          {project.active_swing_revision > 1 && (
            <button
              type="button"
              data-testid="btn-rollback-swing-rev1"
              disabled={isBusy}
              onClick={() => onRollbackToRevision1("club_head")}
              className="text-[11px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/30"
            >
              ↩ 還原自動推論 Rev 1
            </button>
          )}
        </div>
        {swingSummary ? (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-300">
            <div>
              直接桿頭觀測率:{" "}
              <span className="font-mono text-white">
                {(swingSummary.direct_observation_coverage * 100).toFixed(1)}%
              </span>{" "}
              ({swingSummary.direct_observed_count}/{swingSummary.total_frames})
            </div>
            <div>
              桿身幾何端點輔助:{" "}
              <span className="font-mono text-amber-300">
                {swingSummary.geometry_estimated_count} 點
              </span>
            </div>
            <div>
              人工校準錨點:{" "}
              <span className="font-mono text-emerald-300">
                {swingSummary.manual_count} 點
              </span>
            </div>
            <div>
              不確定度 P50/P95:{" "}
              <span className="font-mono">
                ±{swingSummary.p50_uncertainty_px} / ±
                {swingSummary.p95_uncertainty_px} px
              </span>
            </div>
            <div className="col-span-2 text-slate-400 pt-0.5">
              說明: {swingSummary.notes}
            </div>
          </div>
        ) : (
          <div className="text-slate-500">尚無 Swing 軌跡資料</div>
        )}
      </div>

      {/* Shot Tracer 證據與品質摘要卡 */}
      <div
        data-testid="shot-quality-card"
        className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 space-y-2"
      >
        <div className="flex items-center justify-between">
          <span className="font-bold text-cyan-300">
            Shot Tracer 飛球模式 ({project.shot_mode})
          </span>
          {project.active_shot_revision > 1 && (
            <button
              type="button"
              data-testid="btn-rollback-shot-rev1"
              disabled={isBusy}
              onClick={() => onRollbackToRevision1("ball")}
              className="text-[11px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/30"
            >
              ↩ 還原自動推論 Rev 1
            </button>
          )}
        </div>
        {shotSummary ? (
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-slate-300">
            <div>
              直接真球偵測點:{" "}
              <span className="font-mono text-white">
                {shotSummary.direct_observed_count} 幀
              </span>
            </div>
            <div>
              光流 / 卡爾曼補幀:{" "}
              <span className="font-mono text-amber-300">
                {shotSummary.optical_flow_count} /{" "}
                {shotSummary.kalman_predicted_count} 幀
              </span>
            </div>
            <div>
              人工錨點 / 藝術延伸:{" "}
              <span className="font-mono text-emerald-300">
                {shotSummary.manual_count} / {shotSummary.artistic_count} 點
              </span>
            </div>
            <div>
              平均信心度:{" "}
              <span className="font-mono">
                {(shotSummary.mean_confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="col-span-2 text-slate-400 pt-0.5">
              說明: {shotSummary.notes}
            </div>
          </div>
        ) : (
          <div className="text-slate-500">尚無 Shot 軌跡資料</div>
        )}
      </div>

      {/* 本機 CV 模型權重與誠信揭露面板 */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-2.5 space-y-1.5">
        <div className="font-semibold text-slate-300 text-[11px]">
          本機電腦視覺模型註冊狀態 (Model Provenance)
        </div>
        {models.map((m) => (
          <div
            key={m.id}
            className="flex items-center justify-between text-[10px] py-0.5 border-b border-slate-900 last:border-0"
          >
            <span className="text-slate-300">{m.display_name}</span>
            <span
              className={`px-1.5 py-0.5 rounded font-mono ${
                m.availability_status === "READY"
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-amber-500/20 text-amber-300"
              }`}
            >
              {m.availability_status}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
