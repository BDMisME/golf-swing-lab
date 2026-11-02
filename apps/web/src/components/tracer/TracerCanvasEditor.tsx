"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  catmullRomSubdivide,
  computeOutputLayout,
  findFrameScopedNearestPoint,
  projectUprightNormToOutputPx,
  scaleWidthAt1080,
  unprojectOutputPxToUprightNorm,
} from "../../lib/tracer/transforms";
import type {
  CanonicalTrackPoint,
  ExportAspectRatio,
  RenderRecipeV1,
  TrackType,
} from "../../lib/tracer/types";

export type StudioEditToolMode =
  | "inspect"
  | "add_point"
  | "move_point"
  | "delete_point"
  | "set_launch"
  | "set_apex"
  | "set_landing";

interface TracerCanvasEditorProps {
  videoUrl: string;
   fallbackVideoUrl?: string;
  onVideoSourceFallback?: () => void;
  uprightWidth: number;
  uprightHeight: number;
  clipStartPtsUs: number;
  clipEndPtsUs: number;
  currentPtsUs: number;
  onPtsUsChange: (ptsUs: number) => void;
  isPlaying: boolean;
  onPlayingChange: (playing: boolean) => void;
  recipe: RenderRecipeV1;
  previewAspect: ExportAspectRatio;
  swingPoints: CanonicalTrackPoint[];
  shotPoints: CanonicalTrackPoint[];
  topPtsUs: number | null;
  impactPtsUs: number | null;
  activeTrackType: TrackType;
  toolMode: StudioEditToolMode;
  showAnchorPoints: boolean;
  onPointEdit: (op: {
    op: "add" | "move" | "delete";
    source_pts_us: number;
    x_norm?: number;
    y_norm?: number;
  }) => void;
  onSpatialAnchorSet: (
    kind: "launch" | "apex" | "landing",
    xyNorm: [number, number]
  ) => void;
}

const DIRECT_PROVENANCE = new Set(["detector_observed", "manually_annotated"]);

function resolveSwingPhaseColor(
  phase: string,
  cfg: RenderRecipeV1["swing_tracer"]
): string {
  const p = (phase || "").toLowerCase();
  if (p === "address" || p === "takeaway" || p === "backswing" || p === "top") {
    return cfg.backswing_color_hex;
  }
  if (p === "downswing" || p === "impact") {
    return cfg.downswing_color_hex;
  }
  return cfg.follow_through_color_hex;
}

function blendHexColors(hex1: string, hex2: string, factor: number): string {
  const f = Math.max(0.0, Math.min(1.0, factor));
  const h1 = (hex1 || "#FFFFFF").replace("#", "");
  const h2 = (hex2 || "#FFFFFF").replace("#", "");
  const r1 = parseInt(h1.substring(0, 2), 16) || 255;
  const g1 = parseInt(h1.substring(2, 4), 16) || 255;
  const b1 = parseInt(h1.substring(4, 6), 16) || 255;
  const r2 = parseInt(h2.substring(0, 2), 16) || 255;
  const g2 = parseInt(h2.substring(2, 4), 16) || 255;
  const b2 = parseInt(h2.substring(4, 6), 16) || 255;
  const r = Math.round(r1 + (r2 - r1) * f);
  const g = Math.round(g1 + (g2 - g1) * f);
  const b = Math.round(b1 + (b2 - b1) * f);
  return `rgb(${r}, ${g}, ${b})`;
}

export default function TracerCanvasEditor({
  videoUrl,
  fallbackVideoUrl,
  onVideoSourceFallback,
  uprightWidth,
  uprightHeight,
  clipStartPtsUs,
  clipEndPtsUs,
  currentPtsUs,
  onPtsUsChange,
  isPlaying,
  onPlayingChange,
  recipe,
  previewAspect,
  swingPoints,
  shotPoints,
  topPtsUs,
  impactPtsUs,
  activeTrackType,
  toolMode,
  showAnchorPoints,
  onPointEdit,
  onSpatialAnchorSet,
}: TracerCanvasEditorProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const currentPtsRef = useRef<number>(currentPtsUs);
  currentPtsRef.current = currentPtsUs;

  const [hoveredPoint, setHoveredPoint] = useState<CanonicalTrackPoint | null>(
    null
  );
  const [draggingPointPts, setDraggingPointPts] = useState<number | null>(null);
  const [dragPreviewNorm, setDragPreviewNorm] = useState<
    [number, number] | null
  >(null);

  const layout = computeOutputLayout(
    uprightWidth || 1080,
    uprightHeight || 1920,
    previewAspect
  );

  // 繪製 Canvas 特效疊圖（支援直接傳入 renderPtsUs 以供 requestVideoFrameCallback 零延遲重繪）
  const drawOverlay = useCallback(
    (
      overridePtsUs?: number,
      skipUiHandles: boolean = false,
      overrideRecipe?: RenderRecipeV1
    ) => {
      const renderPtsUs =
        typeof overridePtsUs === "number"
          ? overridePtsUs
          : currentPtsRef.current;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const activeRecipe = overrideRecipe || recipe;

      if (
        canvas.width !== layout.outputWidth ||
        canvas.height !== layout.outputHeight
      ) {
        canvas.width = layout.outputWidth;
        canvas.height = layout.outputHeight;
      }
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // 繪製 Letterbox / Pillarbox 安全邊界遮罩 (非純畫布校驗模式下)
      if (!skipUiHandles && (layout.padX > 0 || layout.padY > 0)) {
        ctx.fillStyle = "rgba(9, 13, 22, 0.86)";
        if (layout.padX > 0) {
          ctx.fillRect(0, 0, layout.padX, layout.outputHeight);
          ctx.fillRect(
            layout.outputWidth - layout.padX,
            0,
            layout.padX,
            layout.outputHeight
          );
        }
        if (layout.padY > 0) {
          ctx.fillRect(0, 0, layout.outputWidth, layout.padY);
          ctx.fillRect(
            0,
            layout.outputHeight - layout.padY,
            layout.outputWidth,
            layout.padY
          );
        }
      }

      // 若正在拖曳移動某點，套用即時預覽座標 (P1-3 Drag Preview)
      const effectiveSwingPoints =
        draggingPointPts !== null &&
        dragPreviewNorm !== null &&
        activeTrackType === "club_head"
          ? swingPoints.map((p) =>
              p.source_pts_us === draggingPointPts
                ? {
                    ...p,
                    x_norm: dragPreviewNorm[0],
                    y_norm: dragPreviewNorm[1],
                  }
                : p
            )
          : swingPoints;

      const effectiveShotPoints =
        draggingPointPts !== null &&
        dragPreviewNorm !== null &&
        activeTrackType === "ball"
          ? shotPoints.map((p) =>
              p.source_pts_us === draggingPointPts
                ? {
                    ...p,
                    x_norm: dragPreviewNorm[0],
                    y_norm: dragPreviewNorm[1],
                  }
                : p
            )
          : shotPoints;

      // 1. 繪製 Swing Tracer
      const swingCfg = activeRecipe.swing_tracer;
      if (swingCfg.enabled && effectiveSwingPoints.length > 0) {
        const visibleSwing = effectiveSwingPoints.filter(
          (p) => p.source_pts_us <= renderPtsUs
        );
        const coreW = scaleWidthAt1080(layout, swingCfg.core_width_px_at_1080);
        const glowR = scaleWidthAt1080(layout, swingCfg.glow_radius_px_at_1080);
        const tailDecayUs = Math.max(100_000, swingCfg.tail_decay_ms * 1000);

        for (let i = 0; i < visibleSwing.length - 1; i++) {
          const p1 = visibleSwing[i];
          const p2 = visibleSwing[i + 1];
          const ageUs = Math.max(0, renderPtsUs - p2.source_pts_us);
          if (swingCfg.style === "Tail" && ageUs > tailDecayUs) continue;

          const tailFactor =
            swingCfg.style === "Tail"
              ? Math.max(0.08, 1.0 - ageUs / tailDecayUs)
              : Math.max(
                  0.28,
                  1.0 - (0.55 * ageUs) / Math.max(tailDecayUs, 1_500_000)
                );

          const [x1, y1] = projectUprightNormToOutputPx(
            p1.x_norm,
            p1.y_norm,
            layout
          );
          const [x2, y2] = projectUprightNormToOutputPx(
            p2.x_norm,
            p2.y_norm,
            layout
          );
          const segColor = resolveSwingPhaseColor(p2.phase, swingCfg);
          const isPred =
            !DIRECT_PROVENANCE.has(p1.source_type) ||
            !DIRECT_PROVENANCE.has(p2.source_type);
          if (swingCfg.show_predicted_dashed && isPred && i % 2 === 1) {
            continue;
          }

          ctx.save();
          ctx.lineCap = "round";
          ctx.lineJoin = "round";
          ctx.strokeStyle = segColor;
          ctx.lineWidth = Math.max(1.5, coreW * (0.55 + 0.45 * tailFactor));
          ctx.globalAlpha =
            swingCfg.opacity * tailFactor * (isPred ? 0.68 : 1.0);
          if (swingCfg.style !== "Clean" && glowR > 0) {
            ctx.shadowColor = segColor;
            ctx.shadowBlur = glowR * swingCfg.glow_intensity;
          }

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();

          if (swingCfg.style === "Beam") {
            ctx.strokeStyle = "#FFFFFF";
            ctx.lineWidth = Math.max(1, ctx.lineWidth * 0.45);
            ctx.shadowBlur = 0;
            ctx.stroke();
          }
          ctx.restore();
        }

        // Top / Impact 節點標記
        if (swingCfg.show_top_marker && topPtsUs !== null) {
          const topPt = visibleSwing.find(
            (p) => Math.abs(p.source_pts_us - topPtsUs) <= 65_000
          );
          if (topPt) {
            const [tx, ty] = projectUprightNormToOutputPx(
              topPt.x_norm,
              topPt.y_norm,
              layout
            );
            ctx.save();
            ctx.strokeStyle = swingCfg.backswing_color_hex;
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.arc(tx, ty, scaleWidthAt1080(layout, 9), 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        }

        if (swingCfg.show_impact_marker && impactPtsUs !== null) {
          const impPt = visibleSwing.find(
            (p) => Math.abs(p.source_pts_us - impactPtsUs) <= 65_000
          );
          if (impPt) {
            const [ix, iy] = projectUprightNormToOutputPx(
              impPt.x_norm,
              impPt.y_norm,
              layout
            );
            ctx.save();
            ctx.strokeStyle = "#FFFFFF";
            ctx.shadowColor = swingCfg.downswing_color_hex;
            ctx.shadowBlur = 16;
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.arc(ix, iy, scaleWidthAt1080(layout, 11), 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        }
      }

      // 2. 繪製 Shot Tracer
      const shotCfg = activeRecipe.shot_tracer;
      if (shotCfg.enabled && effectiveShotPoints.length > 0) {
        const visibleShot = effectiveShotPoints.filter(
          (p) => p.source_pts_us <= renderPtsUs
        );
        const nonArtistic = visibleShot.filter(
          (p) => p.source_type !== "artistic_only"
        );
        const artisticPts = visibleShot.filter(
          (p) => p.source_type === "artistic_only"
        );
        const coreW = scaleWidthAt1080(layout, shotCfg.core_width_px_at_1080);
        const glowR = scaleWidthAt1080(layout, shotCfg.glow_radius_px_at_1080);

        if (nonArtistic.length >= 2) {
          const rawXY = nonArtistic.map((p) =>
            projectUprightNormToOutputPx(p.x_norm, p.y_norm, layout)
          );
          const smoothXY = catmullRomSubdivide(rawXY, 6);
          const m = smoothXY.length;

          for (let j = 0; j < m - 1; j++) {
            const prog = j / Math.max(1, m - 1);
            const origIdx = Math.min(
              nonArtistic.length - 1,
              Math.floor(prog * nonArtistic.length)
            );
            const refPt = nonArtistic[origIdx];
            const isPred = !DIRECT_PROVENANCE.has(refPt.source_type);
            if (shotCfg.show_predicted_dashed && isPred && j % 3 === 1) {
              continue;
            }

            let taper =
              shotCfg.taper_start_ratio +
              (1.0 - shotCfg.taper_start_ratio) * Math.sin(prog * Math.PI);
            if (prog > 0.85) {
              taper *=
                shotCfg.taper_end_ratio +
                (1.0 - shotCfg.taper_end_ratio) * ((1.0 - prog) / 0.15);
            }

            const segW = Math.max(1, Math.round(coreW * Math.max(0.35, taper)));
            const segCol = blendHexColors(
              shotCfg.primary_color_hex,
              shotCfg.secondary_color_hex,
              prog
            );

            ctx.save();
            ctx.lineCap = "round";
            ctx.strokeStyle = segCol;
            ctx.lineWidth = segW;
            ctx.globalAlpha = shotCfg.opacity * (isPred ? 0.75 : 1.0);

            if (shotCfg.style !== "Clean" && glowR > 0) {
              ctx.shadowColor = segCol;
              ctx.shadowBlur = glowR * shotCfg.glow_intensity;
            }

            ctx.beginPath();
            ctx.moveTo(smoothXY[j][0], smoothXY[j][1]);
            ctx.lineTo(smoothXY[j + 1][0], smoothXY[j + 1][1]);
            ctx.stroke();

            if (shotCfg.style === "Beam") {
              ctx.strokeStyle = "#FFFFFF";
              ctx.lineWidth = Math.max(1, Math.floor(segW * 0.48));
              ctx.shadowBlur = 0;
              ctx.stroke();
            }
            ctx.restore();
          }
        }

        // 藝術延伸段強制虛線
        if (artisticPts.length > 0) {
          const chain =
            nonArtistic.length > 0
              ? [nonArtistic[nonArtistic.length - 1], ...artisticPts]
              : artisticPts;
          ctx.save();
          ctx.strokeStyle = shotCfg.secondary_color_hex;
          ctx.lineWidth = Math.max(1.5, coreW * 0.65);
          ctx.globalAlpha = shotCfg.opacity * 0.55;
          ctx.setLineDash([coreW * 2.2, coreW * 1.8]);
          ctx.beginPath();
          chain.forEach((pt, idx) => {
            const [px, py] = projectUprightNormToOutputPx(
              pt.x_norm,
              pt.y_norm,
              layout
            );
            if (idx === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
          });
          ctx.stroke();
          ctx.restore();
        }

        // Impact Flash 起飛擊球閃光
        if (shotCfg.show_impact_flash && effectiveShotPoints.length > 0) {
          const launchPt = effectiveShotPoints[0];
          if (Math.abs(renderPtsUs - launchPt.source_pts_us) <= 180_000) {
            const [lx, ly] = projectUprightNormToOutputPx(
              launchPt.x_norm,
              launchPt.y_norm,
              layout
            );
            const flashR = Math.max(6, scaleWidthAt1080(layout, 14.0));
            ctx.save();
            ctx.fillStyle = shotCfg.primary_color_hex;
            ctx.globalAlpha = shotCfg.opacity * 0.45;
            ctx.beginPath();
            ctx.arc(lx, ly, flashR * 2, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = "#FFFFFF";
            ctx.globalAlpha = shotCfg.opacity;
            ctx.beginPath();
            ctx.arc(lx, ly, Math.max(2, Math.floor(flashR / 2)), 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }

        // Apex 最高點標記
        if (shotCfg.show_apex_marker && effectiveShotPoints.length >= 2) {
          const apexPt = effectiveShotPoints.reduce((best, cur) =>
            cur.y_norm < best.y_norm ? cur : best
          );
          if (renderPtsUs >= apexPt.source_pts_us) {
            const [ax, ay] = projectUprightNormToOutputPx(
              apexPt.x_norm,
              apexPt.y_norm,
              layout
            );
            ctx.save();
            ctx.strokeStyle = "#FFFFFF";
            ctx.lineWidth = 2.0;
            ctx.beginPath();
            ctx.arc(ax, ay, scaleWidthAt1080(layout, 8), 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }
        }

        // Landing Ring 落地光環
        if (
          shotCfg.show_landing_ring &&
          effectiveShotPoints.length > 0 &&
          renderPtsUs >=
            effectiveShotPoints[effectiveShotPoints.length - 1].source_pts_us
        ) {
          const endPt =
            effectiveShotPoints[effectiveShotPoints.length - 1];
          const [ex, ey] = projectUprightNormToOutputPx(
            endPt.x_norm,
            endPt.y_norm,
            layout
          );
          const ringW = Math.max(8, scaleWidthAt1080(layout, 16.0));
          const ringH = Math.max(4, scaleWidthAt1080(layout, 7.0));
          ctx.save();
          ctx.strokeStyle = shotCfg.secondary_color_hex;
          ctx.lineWidth = 2.0;
          ctx.globalAlpha = shotCfg.opacity;
          ctx.beginPath();
          ctx.ellipse(ex, ey, ringW, ringH, 0, 0, Math.PI * 2);
          ctx.stroke();
          ctx.restore();
        }
      }

      // 3. 繪製可互動編輯錨點圓點 (供 Studio 逐幀精修，當前幀圓點高亮放大)
      if (showAnchorPoints && !skipUiHandles) {
        const targetPoints =
          activeTrackType === "club_head"
            ? effectiveSwingPoints
            : effectiveShotPoints;
        targetPoints.forEach((pt) => {
          const [px, py] = projectUprightNormToOutputPx(
            pt.x_norm,
            pt.y_norm,
            layout
          );
          const dtUs = Math.abs(pt.source_pts_us - renderPtsUs);
          const isCurrentFrame = dtUs <= 18_000;
          const isSelectableWindow = dtUs <= 45_000;
          const isManual = pt.source_type === "manually_annotated";
          const isObserved = pt.source_type === "detector_observed";

          ctx.save();
          ctx.globalAlpha = isCurrentFrame
            ? 1.0
            : isSelectableWindow
            ? 0.85
            : 0.35;
          ctx.beginPath();
          ctx.arc(px, py, isCurrentFrame ? 9 : 4.5, 0, Math.PI * 2);
          ctx.fillStyle = isManual
            ? "#10B981"
            : isObserved
            ? "#38BDF8"
            : "#F59E0B";
          ctx.fill();
          ctx.lineWidth = isCurrentFrame ? 2.5 : 1.2;
          ctx.strokeStyle = isCurrentFrame ? "#FFFFFF" : "rgba(15,23,42,0.85)";
          ctx.stroke();
          ctx.restore();
        });
      }
    },
    [
      layout,
      recipe,
      swingPoints,
      shotPoints,
      topPtsUs,
      impactPtsUs,
      showAnchorPoints,
      activeTrackType,
      draggingPointPts,
      dragPreviewNorm,
    ]
  );

  useEffect(() => {
    drawOverlay(currentPtsUs);
  }, [drawOverlay, currentPtsUs]);

  // P0-5: 使用 requestVideoFrameCallback + requestAnimationFrame 實作真正 60fps 呈現幀同步
  useEffect(() => {
    const v = videoRef.current as
      | (HTMLVideoElement & {
          requestVideoFrameCallback?: (
            cb: (now: number, metadata: { mediaTime: number; presentedFrames?: number }) => void
          ) => number;
          cancelVideoFrameCallback?: (handle: number) => void;
        })
      | null;
    if (!v) return;

    let rvfcId: number | null = null;
    let rafId: number | null = null;
    let cancelled = false;
    let lastCallbackPerfMs: number | null = null;

    if (typeof window !== "undefined") {
      (window as any).__GSL_FRAME_SYNC_STATS__ = (window as any)
        .__GSL_FRAME_SYNC_STATS__ || {
        rvfcSupported: typeof v.requestVideoFrameCallback === "function",
        callbackCount: 0,
        lastMediaTimeUs: currentPtsRef.current,
        recentMediaTimesUs: [] as number[],
        frameIntervalsMs: [] as number[],
        meanIntervalMs: 0,
        estimatedFps: 0,
      };
    }

    const recordFrameSync = (mediaTimeSec: number, perfNow: number) => {
      const nowUs = Math.round(mediaTimeSec * 1_000_000);
      if (typeof window !== "undefined") {
        const stats = (window as any).__GSL_FRAME_SYNC_STATS__;
        if (stats) {
          stats.callbackCount += 1;
          stats.lastMediaTimeUs = nowUs;
          stats.recentMediaTimesUs = stats.recentMediaTimesUs || [];
          stats.recentMediaTimesUs.push(nowUs);
          if (stats.recentMediaTimesUs.length > 60) {
            stats.recentMediaTimesUs.shift();
          }
          if (lastCallbackPerfMs !== null) {
            const dtMs = perfNow - lastCallbackPerfMs;
            if (dtMs > 2 && dtMs < 250) {
              stats.frameIntervalsMs.push(Number(dtMs.toFixed(2)));
              if (stats.frameIntervalsMs.length > 120) {
                stats.frameIntervalsMs.shift();
              }
              const avg =
                stats.frameIntervalsMs.reduce(
                  (a: number, b: number) => a + b,
                  0
                ) / stats.frameIntervalsMs.length;
              stats.meanIntervalMs = Number(avg.toFixed(2));
              stats.estimatedFps = Number((1000.0 / Math.max(1, avg)).toFixed(1));
            }
          }
          lastCallbackPerfMs = perfNow;
        }
      }

      if (isPlaying && nowUs >= clipEndPtsUs) {
        v.currentTime = clipStartPtsUs / 1_000_000.0;
        currentPtsRef.current = clipStartPtsUs;
        onPtsUsChange(clipStartPtsUs);
        drawOverlay(clipStartPtsUs);
      } else if (Math.abs(nowUs - currentPtsRef.current) >= 1_000) {
        currentPtsRef.current = nowUs;
        onPtsUsChange(nowUs);
        drawOverlay(nowUs);
      } else {
        drawOverlay(nowUs);
      }
    };

    if (typeof v.requestVideoFrameCallback === "function") {
      const onVideoFrame = (
        now: number,
        metadata: { mediaTime: number; presentedFrames?: number }
      ) => {
        if (cancelled) return;
        recordFrameSync(metadata.mediaTime, now);
        if (typeof v.requestVideoFrameCallback === "function") {
          rvfcId = v.requestVideoFrameCallback(onVideoFrame);
        }
      };
      rvfcId = v.requestVideoFrameCallback(onVideoFrame);
    }

    // 同時配置 rAF 高頻補幀迴圈，確保在暫停拖拉或無 rVFC 環境下亦保持 60Hz 同步
    const onAnimationFrame = (perfNow: number) => {
      if (cancelled) return;
      if (isPlaying && typeof v.requestVideoFrameCallback !== "function") {
        recordFrameSync(v.currentTime, perfNow);
      }
      rafId = window.requestAnimationFrame(onAnimationFrame);
    };
    if (isPlaying) {
      rafId = window.requestAnimationFrame(onAnimationFrame);
    }

    return () => {
      cancelled = true;
      if (
        rvfcId !== null &&
        typeof v.cancelVideoFrameCallback === "function"
      ) {
        v.cancelVideoFrameCallback(rvfcId);
      }
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [isPlaying, clipStartPtsUs, clipEndPtsUs, onPtsUsChange, drawOverlay]);

  // P0-2: 暴露 WebKit 實機指定 PTS 畫布擷取輔助函式供真實像素級 Parity 驗證腳本呼叫
  useEffect(() => {
    if (typeof window === "undefined") return;
    (window as any).__GSL_RENDER_AND_CAPTURE_CANVAS__ = (
      targetPtsUs: number,
      skipUiHandles: boolean = true,
      overrideRecipe?: any
    ) => {
      currentPtsRef.current = targetPtsUs;
      onPtsUsChange(targetPtsUs);
      drawOverlay(targetPtsUs, skipUiHandles, overrideRecipe);
      const c = canvasRef.current;
      if (!c) return null;
      return {
        ptsUs: targetPtsUs,
        width: c.width,
        height: c.height,
        dataUrl: c.toDataURL("image/png"),
      };
    };
  }, [drawOverlay, onPtsUsChange]);

  // 同步外部 currentPtsUs 至 <video>
  useEffect(() => {
    const v = videoRef.current;
    if (!v || isPlaying) return;
    const targetSec = currentPtsUs / 1_000_000.0;
    if (Math.abs(v.currentTime - targetSec) > 0.008) {
      try {
        v.currentTime = targetSec;
      } catch {
        // ignore seek before metadata loaded
      }
    }
  }, [currentPtsUs, isPlaying]);

  // 控制播放與區間循環
  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    if (isPlaying) {
      const startSec = clipStartPtsUs / 1_000_000.0;
      const endSec = clipEndPtsUs / 1_000_000.0;
      if (v.currentTime < startSec || v.currentTime >= endSec) {
        v.currentTime = startSec;
      }
      v.play().catch(() => onPlayingChange(false));
    } else {
      v.pause();
    }
  }, [isPlaying, clipStartPtsUs, clipEndPtsUs, onPlayingChange]);

  const resolveCanvasEventNorm = (
    e: React.MouseEvent<HTMLCanvasElement>
  ): [number, number] => {
    const canvas = canvasRef.current;
    if (!canvas) return [0.5, 0.5];
    const rect = canvas.getBoundingClientRect();
    const scaleX = layout.outputWidth / Math.max(1, rect.width);
    const scaleY = layout.outputHeight / Math.max(1, rect.height);
    const outX = (e.clientX - rect.left) * scaleX;
    const outY = (e.clientY - rect.top) * scaleY;
    return unprojectOutputPxToUprightNorm(outX, outY, layout);
  };

  // P1-3: 使用時間窗限定選點 (±45ms，約 ±1~2 幀)，避免誤選其他揮桿階段重疊路徑上的點
  const findNearestPointAtCurrentFrame = (
    xNorm: number,
    yNorm: number,
    maxDistNorm: number = 0.048
  ): CanonicalTrackPoint | null => {
    const pts = activeTrackType === "club_head" ? swingPoints : shotPoints;
    return findFrameScopedNearestPoint(
      pts,
      xNorm,
      yNorm,
      currentPtsUs,
      maxDistNorm,
      45_000
    );
  };

  const handleCanvasMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const [xNorm, yNorm] = resolveCanvasEventNorm(e);

    if (toolMode === "set_launch") {
      onSpatialAnchorSet("launch", [xNorm, yNorm]);
      return;
    }
    if (toolMode === "set_apex") {
      onSpatialAnchorSet("apex", [xNorm, yNorm]);
      return;
    }
    if (toolMode === "set_landing") {
      onSpatialAnchorSet("landing", [xNorm, yNorm]);
      return;
    }
    if (toolMode === "add_point") {
      onPointEdit({
        op: "add",
        source_pts_us: currentPtsUs,
        x_norm: xNorm,
        y_norm: yNorm,
      });
      return;
    }

    const nearest = findNearestPointAtCurrentFrame(xNorm, yNorm);
    if (toolMode === "delete_point" && nearest) {
      onPointEdit({
        op: "delete",
        source_pts_us: nearest.source_pts_us,
      });
      return;
    }
    if (toolMode === "move_point" && nearest) {
      setDraggingPointPts(nearest.source_pts_us);
      setDragPreviewNorm([xNorm, yNorm]);
      onPtsUsChange(nearest.source_pts_us);
      return;
    }
    if (nearest) {
      setHoveredPoint(nearest);
      onPtsUsChange(nearest.source_pts_us);
    }
  };

  const handleCanvasMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const [xNorm, yNorm] = resolveCanvasEventNorm(e);
    if (draggingPointPts !== null) {
      setDragPreviewNorm([xNorm, yNorm]);
      return;
    }
    const nearest = findNearestPointAtCurrentFrame(xNorm, yNorm, 0.038);
    setHoveredPoint(nearest);
  };

  const handleCanvasMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (draggingPointPts !== null) {
      const [xNorm, yNorm] = resolveCanvasEventNorm(e);
      onPointEdit({
        op: "move",
        source_pts_us: draggingPointPts,
        x_norm: xNorm,
        y_norm: yNorm,
      });
      setDraggingPointPts(null);
      setDragPreviewNorm(null);
    }
  };

  return (
    <div className="relative flex flex-col items-center justify-center bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
      <div
        className="relative w-full max-h-[72vh] flex items-center justify-center bg-black"
        style={{
          aspectRatio: `${layout.outputWidth} / ${layout.outputHeight}`,
        }}
      >
        <video
          ref={videoRef}
          src={videoUrl}
          playsInline
          preload="auto"
          className="w-full h-full object-contain pointer-events-none select-none"
          onError={() => {
            if (fallbackVideoUrl && onVideoSourceFallback) {
              onVideoSourceFallback();
            }
          }}
          onSeeked={(e) => {
            const nowUs = Math.round(e.currentTarget.currentTime * 1_000_000);
            drawOverlay(nowUs);
          }}
        />
        <canvas
          ref={canvasRef}
          data-testid="tracer-studio-canvas"
          onMouseDown={handleCanvasMouseDown}
          onMouseMove={handleCanvasMouseMove}
          onMouseUp={handleCanvasMouseUp}
          className={`absolute inset-0 w-full h-full object-contain ${
            toolMode === "inspect" ? "cursor-pointer" : "cursor-crosshair"
          }`}
        />

        {/* 點位證據懸浮檢視氣泡 */}
        {hoveredPoint && (
          <div
            data-testid="point-provenance-tooltip"
            className="absolute top-3 left-3 bg-slate-900/95 border border-slate-700 text-xs text-slate-100 px-3 py-2 rounded-xl shadow-lg pointer-events-none space-y-0.5"
          >
            <div className="font-semibold text-cyan-400">
              {hoveredPoint.track_type === "club_head"
                ? "桿頭點位"
                : "小白球點位"}{" "}
              · Frame #{hoveredPoint.source_frame_index}
            </div>
            <div>
              來源:{" "}
              <span className="font-mono text-amber-300">
                {hoveredPoint.source_type}
              </span>{" "}
              ({hoveredPoint.position_role})
            </div>
            <div>
              PTS: <span className="font-mono">{hoveredPoint.source_pts_us} us</span>{" "}
              · 信心度: {(hoveredPoint.confidence * 100).toFixed(0)}% · ±
              {hoveredPoint.uncertainty_px.toFixed(1)}px
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
