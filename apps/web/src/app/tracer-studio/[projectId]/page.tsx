"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import React, { useCallback, useEffect, useState } from "react";
import TracerCanvasEditor, {
  type StudioEditToolMode,
} from "../../../components/tracer/TracerCanvasEditor";
import TracerExportPanel from "../../../components/tracer/TracerExportPanel";
import TracerInspectorPanel from "../../../components/tracer/TracerInspectorPanel";
import TracerStylePanel from "../../../components/tracer/TracerStylePanel";
import TracerTimeline from "../../../components/tracer/TracerTimeline";
import {
  analyzeTracerProject,
  applyTracerManualEdits,
  buildAuthenticatedMediaUrl,
  createOrGetTracerProject,
  createTracerExport,
  getTracerProjectDetail,
  listTracerModels,
  listTracerPresets,
  rollbackTracerRevision,
  updateTracerAnchors,
  updateTracerRecipe,
} from "../../../lib/tracer/transforms";
import type {
  AudioMode,
  ExportAspectRatio,
  RenderRecipeV1,
  TrackType,
  TracerExportItem,
  TracerModelItem,
  TracerProjectDetail,
} from "../../../lib/tracer/types";

export default function TracerStudioProjectPage() {
  const params = useParams();
  const router = useRouter();
  const rawProjectId = String(params?.projectId || "");

  const [project, setProject] = useState<TracerProjectDetail | null>(null);
  const [presets, setPresets] = useState<RenderRecipeV1[]>([]);
  const [models, setModels] = useState<TracerModelItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [busy, setBusy] = useState<boolean>(false);
  const [exporting, setExporting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const [currentPtsUs, setCurrentPtsUs] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [activeTrackType, setActiveTrackType] =
    useState<TrackType>("club_head");
  const [toolMode, setToolMode] = useState<StudioEditToolMode>("inspect");
  const [showAnchorPoints, setShowAnchorPoints] = useState<boolean>(true);

  const [previewAspect, setPreviewAspect] =
    useState<ExportAspectRatio>("original");
  const [exportFps, setExportFps] = useState<30 | 60>(60);
  const [audioMode, setAudioMode] = useState<AudioMode>("preserve");
  const [latestExport, setLatestExport] = useState<TracerExportItem | null>(
    null
  );
  const [videoSourceMode, setVideoSourceMode] = useState<
    "ORIGINAL" | "PROXY_FALLBACK"
  >("ORIGINAL");
  const [undoStack, setUndoStack] = useState<
    Array<{ trackType: TrackType; fromRev: number; toRev: number }>
  >([]);
  const [redoStack, setRedoStack] = useState<
    Array<{ trackType: TrackType; fromRev: number; toRev: number }>
  >([]);

  const loadWorkspace = useCallback(async () => {
    if (!rawProjectId) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      let projData: TracerProjectDetail;
      if (rawProjectId.startsWith("seg_")) {
        const segId = rawProjectId.slice(4);
        projData = await createOrGetTracerProject({
          segment_id: segId,
          auto_analyze: true,
        });
        router.replace(`/tracer-studio/${projData.id}`);
      } else {
        try {
          projData = await getTracerProjectDetail(rawProjectId);
        } catch {
          // 若傳入為 segment_id，自動建立對應專案
          projData = await createOrGetTracerProject({
            segment_id: rawProjectId,
            auto_analyze: true,
          });
        }
      }

      const [presetRes, modelRes] = await Promise.all([
        listTracerPresets(),
        listTracerModels(),
      ]);

      setProject(projData);
      if (projData.recipe?.export_format?.aspect_ratio) {
        setPreviewAspect(projData.recipe.export_format.aspect_ratio);
      }
      setVideoSourceMode(
        projData.original_video_stream_url ? "ORIGINAL" : "PROXY_FALLBACK"
      );
      setPresets(presetRes.presets || []);
      setModels(modelRes.models || []);
      const defaultPts =
        projData.anchors?.impact_pts_us ||
        projData.clip_start_pts_us ||
        0;
      setCurrentPtsUs(defaultPts);
    } catch (err: any) {
      setErrorMsg(err?.message || "無法載入 Golf Tracer Studio 專案");
    } finally {
      setLoading(false);
    }
  }, [rawProjectId, router]);

  useEffect(() => {
    loadWorkspace();
  }, [loadWorkspace]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      (window as any).__GSL_SET_PREVIEW_ASPECT__ = (aspect: ExportAspectRatio) => {
        setPreviewAspect(aspect);
      };
    }
  }, []);

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 4000);
  };

  const handleReanalyze = async () => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const res = await analyzeTracerProject(project.id, {
        run_swing_tracer: true,
        run_shot_tracer: true,
        run_sync: true,
      });
      if (res.project) {
        setProject(res.project);
      } else {
        const refreshed = await getTracerProjectDetail(project.id);
        setProject(refreshed);
      }
      showToast("已完成原始高解析影片雙軌重新掃描（套用當前 Studio 錨點）");
    } catch (err: any) {
      setErrorMsg(err?.message || "重新分析失敗");
    } finally {
      setBusy(false);
    }
  };

  const handlePointEdit = async (op: {
    op: "add" | "move" | "delete";
    source_pts_us: number;
    x_norm?: number;
    y_norm?: number;
  }) => {
    if (!project) return;
    const prevRev =
      activeTrackType === "club_head"
        ? project.active_swing_revision
        : project.active_shot_revision;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await applyTracerManualEdits(project.id, {
        track_type: activeTrackType,
        edits: [
          {
            op: op.op,
            source_pts_us: op.source_pts_us,
            x_norm: op.x_norm,
            y_norm: op.y_norm,
            point_role: "manual_anchor",
            note: `Studio ${op.op} at ${op.source_pts_us}us`,
          },
        ],
        recompute_between_manual_anchors: true,
        note: `Studio ${op.op} point`,
      });
      const nextRev =
        activeTrackType === "club_head"
          ? updated.active_swing_revision
          : updated.active_shot_revision;
      setUndoStack((prev) => [
        ...prev,
        { trackType: activeTrackType, fromRev: prevRev, toRev: nextRev },
      ]);
      setRedoStack([]);
      setProject(updated);
      showToast(
        `已建立 Copy-on-Write 新修訂版 (${
          activeTrackType === "club_head"
            ? `Swing Rev #${updated.active_swing_revision}`
            : `Shot Rev #${updated.active_shot_revision}`
        })`
      );
    } catch (err: any) {
      setErrorMsg(err?.message || "套用手動編輯失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleUndo = async () => {
    if (!project || undoStack.length === 0) return;
    const last = undoStack[undoStack.length - 1];
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await rollbackTracerRevision(
        project.id,
        last.trackType,
        last.fromRev
      );
      setUndoStack((prev) => prev.slice(0, -1));
      setRedoStack((prev) => [...prev, last]);
      setProject(updated);
      showToast(
        `已復原 ${last.trackType} 至修訂版 Rev #${last.fromRev}`
      );
    } catch (err: any) {
      setErrorMsg(err?.message || "復原修訂版失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleRedo = async () => {
    if (!project || redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await rollbackTracerRevision(
        project.id,
        next.trackType,
        next.toRev
      );
      setRedoStack((prev) => prev.slice(0, -1));
      setUndoStack((prev) => [...prev, next]);
      setProject(updated);
      showToast(
        `已重做 ${next.trackType} 至修訂版 Rev #${next.toRev}`
      );
    } catch (err: any) {
      setErrorMsg(err?.message || "重做修訂版失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleSpatialAnchorSet = async (
    kind: "launch" | "apex" | "landing",
    xyNorm: [number, number]
  ) => {
    if (!project) return;
    const prevShotRev = project.active_shot_revision;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await updateTracerAnchors(project.id, {
        ...(kind === "launch"
          ? { launch_xy_norm: xyNorm, launch_pts_us: currentPtsUs }
          : kind === "apex"
          ? { apex_xy_norm: xyNorm, apex_pts_us: currentPtsUs }
          : {
              landing_xy_norm: xyNorm,
              landing_pts_us: currentPtsUs,
              artistic_extension_enabled: true,
            }),
        recompute_tracks: true,
      });
      if (updated.active_shot_revision !== prevShotRev && prevShotRev >= 1) {
        setUndoStack((prev) => [
          ...prev,
          {
            trackType: "ball",
            fromRev: prevShotRev,
            toRev: updated.active_shot_revision,
          },
        ]);
        setRedoStack([]);
      }
      setProject(updated);
      setToolMode("inspect");
      showToast(
        kind === "launch"
          ? "已設定起飛球位 (Launch XY) 基準錨點"
          : kind === "apex"
          ? "已設定彈道最高點 (Apex) 錨點"
          : "已設定落點錨點並啟用虛線藝術延伸段"
      );
    } catch (err: any) {
      setErrorMsg(err?.message || "設定空間錨點失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleClearShotAnchors = async () => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await updateTracerAnchors(project.id, {
        clear_launch: true,
        clear_apex: true,
        clear_landing: true,
        artistic_extension_enabled: false,
        recompute_tracks: true,
      });
      setProject(updated);
      showToast("已清除飛球 Launch / Apex / 落點空間錨點");
    } catch (err: any) {
      setErrorMsg(err?.message || "清除飛球空間錨點失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleSetTemporalAnchorAtCurrentPts = async (
    anchorKey:
      | "address_pts_us"
      | "top_pts_us"
      | "impact_pts_us"
      | "finish_pts_us"
      | "launch_pts_us"
  ) => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await updateTracerAnchors(project.id, {
        [anchorKey]: currentPtsUs,
        recompute_tracks: true,
      });
      setProject(updated);
      showToast(`已更新 Studio 錨點 ${anchorKey} = ${currentPtsUs} us`);
    } catch (err: any) {
      setErrorMsg(err?.message || "更新時間錨點失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleRollbackToRevision1 = async (trackType: TrackType) => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await rollbackTracerRevision(project.id, trackType, 1);
      setProject(updated);
      showToast(`已將 ${trackType} 軌道還原至自動推論 Revision 1`);
    } catch (err: any) {
      setErrorMsg(err?.message || "還原修訂版失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleSelectPreset = async (presetId: string) => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const updated = await updateTracerRecipe(project.id, {
        preset_id: presetId,
      });
      setProject(updated);
      showToast(`已切換特效配方為 ${updated.recipe.name}`);
    } catch (err: any) {
      setErrorMsg(err?.message || "切換預設配方失敗");
    } finally {
      setBusy(false);
    }
  };

  // P1-3: 移除靜默吞錯，若 PUT /api/tracer/projects/{id}/recipe 失敗立即回滾 UI 狀態並顯示明確錯誤橫幅
  const handleRecipeChange = async (nextRecipe: RenderRecipeV1) => {
    if (!project) return;
    const previousRecipe = project.recipe;
    setErrorMsg(null);
    setProject({
      ...project,
      recipe: nextRecipe,
    });
    try {
      const updated = await updateTracerRecipe(project.id, {
        recipe: nextRecipe,
      });
      setProject(updated);
    } catch (err: any) {
      setProject((cur) => (cur ? { ...cur, recipe: previousRecipe } : cur));
      setErrorMsg(
        err?.message || "儲存渲染配方失敗，已自動回滾至前一個配方狀態"
      );
    }
  };

  const handleToggleArtisticExtension = async (enabled: boolean) => {
    if (!project) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const existingLanding =
        project.anchors?.anchors_json?.landing_xy_norm || [0.58, 0.42];
      const updated = await updateTracerAnchors(project.id, {
        artistic_extension_enabled: enabled,
        landing_xy_norm: enabled
          ? (existingLanding as [number, number])
          : undefined,
        recompute_tracks: true,
      });
      setProject(updated);
      showToast(
        enabled
          ? "已啟用遠端落點藝術延伸 (虛線標示為 artistic_only)"
          : "已關閉藝術延伸，僅顯示實測與物理追蹤段"
      );
    } catch (err: any) {
      setErrorMsg(err?.message || "切換藝術延伸失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleTriggerExport = async () => {
    if (!project) return;
    setExporting(true);
    setErrorMsg(null);
    try {
      const expRes = await createTracerExport({
        project_id: project.id,
        aspect_ratio: previewAspect,
        fps: exportFps,
        audio_mode: audioMode,
        recipe_override: project.recipe,
        run_sync: true,
      });
      setLatestExport(expRes);
      showToast("特效 MP4 與 .tracer.json Sidecar 匯出完成！");
    } catch (err: any) {
      setErrorMsg(err?.message || "匯出特效影片失敗");
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100">
        <div className="max-w-7xl mx-auto px-4 py-12 text-center text-sm text-slate-400">
          正在載入 Golf Tracer Studio 高解析度雙軌工作區...
        </div>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100">
        <div className="max-w-3xl mx-auto px-4 py-12 space-y-4">
          <div className="bg-rose-950/60 border border-rose-700 text-rose-200 p-4 rounded-2xl text-sm">
            {errorMsg || "找不到指定的 Golf Tracer Studio 專案"}
          </div>
          <Link
            href="/"
            className="inline-block px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
          >
            ← 返回練習場列表
          </Link>
        </div>
      </div>
    );
  }

  const swingPts = project.swing_track?.points || [];
  const shotPts = project.shot_track?.points || [];
  // P0-3: Studio 預覽優先載入 original_video_stream_url (?source=original)，確保與匯出原片完全同源
  const primaryStreamPath =
    videoSourceMode === "ORIGINAL" && project.original_video_stream_url
      ? project.original_video_stream_url
      : project.video_stream_url;
  const streamUrl = buildAuthenticatedMediaUrl(primaryStreamPath);
  const fallbackProxyUrl = buildAuthenticatedMediaUrl(project.video_stream_url);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 pb-16">
      <main className="max-w-[1440px] mx-auto px-4 py-5 space-y-4">
        {/* 頂部專案標題與誠信狀態橫幅 */}
        <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-900/90 border border-slate-800 px-4 py-3 rounded-2xl">
          <div className="flex items-center gap-3">
            <Link
              href={`/swings/${project.segment_id}`}
              className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 font-medium"
            >
              ← 返回單球分析
            </Link>
            <div>
              <h1
                data-testid="tracer-project-title"
                className="text-base font-bold text-white flex items-center gap-2"
              >
                <span>✨ {project.title}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-mono">
                  R4 Tracer Studio
                </span>
              </h1>
              <p className="text-[11px] text-slate-400 font-mono">
                原片 SHA256: {project.source_video_sha256.slice(0, 16)}... ·
                正向解析度: {project.geometry.upright_width}x
                {project.geometry.upright_height} @{" "}
                {Number(project.geometry.fps || 60).toFixed(2)}fps
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span
              data-testid="badge-video-source"
              className={`px-2.5 py-1 rounded-xl font-mono font-semibold border ${
                videoSourceMode === "ORIGINAL"
                  ? "bg-indigo-500/20 border-indigo-400/40 text-indigo-200"
                  : "bg-amber-500/20 border-amber-400/40 text-amber-200"
              }`}
            >
              Source: {videoSourceMode}
            </span>
            <span
              data-testid="badge-swing-status"
              className={`px-2.5 py-1 rounded-xl font-mono font-semibold border ${
                project.swing_status === "AUTO_TRACED" ||
                project.swing_status === "MANUAL_ASSISTED"
                  ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
                  : "bg-amber-500/20 border-amber-500/40 text-amber-300"
              }`}
            >
              Swing: {project.swing_status} (Rev #{project.active_swing_revision})
            </span>
            <span
              data-testid="badge-shot-mode"
              className={`px-2.5 py-1 rounded-xl font-mono font-semibold border ${
                project.shot_mode === "AUTO_OBSERVED" ||
                project.shot_mode === "MANUAL_ANCHORED"
                  ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-300"
                  : project.shot_mode === "ARTISTIC_EXTENSION"
                  ? "bg-pink-500/20 border-pink-500/40 text-pink-300"
                  : "bg-slate-800 border-slate-700 text-slate-300"
              }`}
            >
              Shot: {project.shot_mode} (Rev #{project.active_shot_revision})
            </span>
          </div>
        </div>

        {errorMsg && (
          <div
            data-testid="studio-error-banner"
            className="bg-rose-950/70 border border-rose-700 text-rose-200 px-4 py-2.5 rounded-xl text-xs"
          >
            ⚠️ {errorMsg}
          </div>
        )}
        {toastMsg && (
          <div
            data-testid="studio-toast"
            className="bg-emerald-950/80 border border-emerald-600 text-emerald-200 px-4 py-2.5 rounded-xl text-xs font-medium"
          >
            ✅ {toastMsg}
          </div>
        )}

        {/* 主工作區雙欄佈局 */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
          {/* 左側：雙軌特效畫布與真實 PTS 逐幀時間軸 (7 cols) */}
          <div className="lg:col-span-7 space-y-3">
            <TracerCanvasEditor
              videoUrl={streamUrl}
              fallbackVideoUrl={fallbackProxyUrl}
              onVideoSourceFallback={() => {
                if (videoSourceMode === "ORIGINAL") {
                  setVideoSourceMode("PROXY_FALLBACK");
                }
              }}
              uprightWidth={project.geometry.upright_width || 1080}
              uprightHeight={project.geometry.upright_height || 1920}
              clipStartPtsUs={project.clip_start_pts_us}
              clipEndPtsUs={project.clip_end_pts_us}
              currentPtsUs={currentPtsUs}
              onPtsUsChange={setCurrentPtsUs}
              isPlaying={isPlaying}
              onPlayingChange={setIsPlaying}
              recipe={project.recipe}
              previewAspect={previewAspect}
              swingPoints={swingPts}
              shotPoints={shotPts}
              topPtsUs={project.anchors?.top_pts_us ?? null}
              impactPtsUs={project.anchors?.impact_pts_us ?? null}
              activeTrackType={activeTrackType}
              toolMode={toolMode}
              showAnchorPoints={showAnchorPoints}
              onPointEdit={handlePointEdit}
              onSpatialAnchorSet={handleSpatialAnchorSet}
            />

            <TracerTimeline
              clipStartPtsUs={project.clip_start_pts_us}
              clipEndPtsUs={project.clip_end_pts_us}
              currentPtsUs={currentPtsUs}
              fps={project.geometry.fps || 60}
              isPlaying={isPlaying}
              onPlayingChange={setIsPlaying}
              onPtsUsChange={setCurrentPtsUs}
              anchors={project.anchors}
              onSetTemporalAnchorAtCurrentPts={
                handleSetTemporalAnchorAtCurrentPts
              }
              swingPoints={swingPts}
              shotPoints={shotPts}
            />
          </div>

          {/* 右側：逐幀檢查工具箱 + Flight FX 配方 + 影片匯出面板 (5 cols) */}
          <div className="lg:col-span-5 space-y-4">
            <TracerInspectorPanel
              project={project}
              models={models}
              activeTrackType={activeTrackType}
              onActiveTrackTypeChange={setActiveTrackType}
              toolMode={toolMode}
              onToolModeChange={setToolMode}
              showAnchorPoints={showAnchorPoints}
              onShowAnchorPointsChange={setShowAnchorPoints}
              onReanalyze={handleReanalyze}
              onRollbackToRevision1={handleRollbackToRevision1}
              onUndo={handleUndo}
              onRedo={handleRedo}
              canUndo={undoStack.length > 0}
              canRedo={redoStack.length > 0}
              onClearShotAnchors={handleClearShotAnchors}
              onJumpToPtsUs={(pts) => {
                setIsPlaying(false);
                setCurrentPtsUs(pts);
              }}
              onDeletePointAtPtsUs={(pts) =>
                handlePointEdit({ op: "delete", source_pts_us: pts })
              }
              currentPtsUs={currentPtsUs}
              isBusy={busy}
            />

            <TracerStylePanel
              recipe={project.recipe}
              presets={presets}
              anchors={project.anchors}
              onSelectPreset={handleSelectPreset}
              onRecipeChange={handleRecipeChange}
              onToggleArtisticExtension={handleToggleArtisticExtension}
              isBusy={busy}
            />

            <TracerExportPanel
              previewAspect={previewAspect}
              onPreviewAspectChange={setPreviewAspect}
              exportFps={exportFps}
              onExportFpsChange={setExportFps}
              audioMode={audioMode}
              onAudioModeChange={setAudioMode}
              onTriggerExport={handleTriggerExport}
              latestExport={latestExport}
              isExporting={exporting}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
