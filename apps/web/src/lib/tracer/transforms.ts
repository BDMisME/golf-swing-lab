/**
 * Golf Tracer Studio R4 — Shared Coordinate Space Transforms & API Client (`apps/web/src/lib/tracer/transforms.ts`).
 * 與後端 `packages/analysis/tracer/transforms.py` 保持 1:1 數學對等，
 * 確保前端 Canvas 預覽與後端 FFmpeg 匯出之像素誤差 <= 2.0 px (@1080p)。
 */

import { API_BASE_URL, apiFetch, getAuthToken } from "../api";
import type {
  AudioMode,
  ExportAspectRatio,
  RenderRecipeV1,
  TrackType,
  TracerExportItem,
  TracerModelItem,
  TracerProjectDetail,
} from "./types";

export interface OutputLayout {
  uprightWidth: number;
  uprightHeight: number;
  outputWidth: number;
  outputHeight: number;
  scale: number;
  padX: number;
  padY: number;
  targetAspect: ExportAspectRatio;
}

export function clamp01(val: number): number {
  if (val < 0.0) return 0.0;
  if (val > 1.0) return 1.0;
  return val;
}

export function computeOutputLayout(
  uprightWidth: number,
  uprightHeight: number,
  targetAspect: ExportAspectRatio = "original",
  fixedOutputSize?: [number, number]
): OutputLayout {
  const uw = Math.max(2, Math.round(uprightWidth));
  const uh = Math.max(2, Math.round(uprightHeight));

  let outW = uw;
  let outH = uh;
  if (fixedOutputSize) {
    outW = fixedOutputSize[0];
    outH = fixedOutputSize[1];
  } else if (targetAspect === "original") {
    outW = uw % 2 === 0 ? uw : uw + 1;
    outH = uh % 2 === 0 ? uh : uh + 1;
  } else if (targetAspect === "16:9") {
    outW = 1920;
    outH = 1080;
  } else if (targetAspect === "9:16") {
    outW = 1080;
    outH = 1920;
  }

  const scale = Math.min(outW / uw, outH / uh);
  const contentW = uw * scale;
  const contentH = uh * scale;
  const padX = (outW - contentW) / 2.0;
  const padY = (outH - contentH) / 2.0;

  return {
    uprightWidth: uw,
    uprightHeight: uh,
    outputWidth: outW,
    outputHeight: outH,
    scale,
    padX,
    padY,
    targetAspect,
  };
}

export function projectUprightNormToOutputPx(
  xNorm: number,
  yNorm: number,
  layout: OutputLayout
): [number, number] {
  const contentW = layout.uprightWidth * layout.scale;
  const contentH = layout.uprightHeight * layout.scale;
  const xPx = layout.padX + clamp01(xNorm) * contentW;
  const yPx = layout.padY + clamp01(yNorm) * contentH;
  return [xPx, yPx];
}

export function unprojectOutputPxToUprightNorm(
  xPx: number,
  yPx: number,
  layout: OutputLayout
): [number, number] {
  const contentW = Math.max(1e-6, layout.uprightWidth * layout.scale);
  const contentH = Math.max(1e-6, layout.uprightHeight * layout.scale);
  const xNorm = clamp01((xPx - layout.padX) / contentW);
  const yNorm = clamp01((yPx - layout.padY) / contentH);
  return [xNorm, yNorm];
}

export function canvasClickToUprightNorm(
  clientX: number,
  clientY: number,
  rectLeft: number,
  rectTop: number,
  rectWidth: number,
  rectHeight: number,
  uprightWidth: number,
  uprightHeight: number
): [number, number] {
  if (rectWidth <= 0 || rectHeight <= 0) {
    return [0.5, 0.5];
  }
  const layout = computeOutputLayout(
    uprightWidth,
    uprightHeight,
    "original",
    [Math.max(2, Math.round(rectWidth)), Math.max(2, Math.round(rectHeight))]
  );
  const localX = clientX - rectLeft;
  const localY = clientY - rectTop;
  return unprojectOutputPxToUprightNorm(localX, localY, layout);
}

export function scaleWidthAt1080(layout: OutputLayout, widthPxAt1080: number): number {
  const shortSide = Math.min(layout.outputWidth, layout.outputHeight);
  const scaled = widthPxAt1080 * (shortSide / 1080.0);
  return Math.max(1, Math.round(scaled));
}

export function catmullRomSubdivide(
  xyPoints: Array<[number, number]>,
  subdivisionsPerSegment: number = 6
): Array<[number, number]> {
  const n = xyPoints.length;
  if (n <= 2 || subdivisionsPerSegment <= 1) {
    return [...xyPoints];
  }
  const result: Array<[number, number]> = [];
  for (let i = 0; i < n - 1; i++) {
    const p0 = xyPoints[Math.max(0, i - 1)];
    const p1 = xyPoints[i];
    const p2 = xyPoints[i + 1];
    const p3 = xyPoints[Math.min(n - 1, i + 2)];

    for (let step = 0; step < subdivisionsPerSegment; step++) {
      const t = step / subdivisionsPerSegment;
      const t2 = t * t;
      const t3 = t2 * t;
      const b0 = -0.5 * t3 + t2 - 0.5 * t;
      const b1 = 1.5 * t3 - 2.5 * t2 + 1.0;
      const b2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t;
      const b3 = 0.5 * t3 - 0.5 * t2;
      result.push([
        b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
        b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1],
      ]);
    }
  }
  result.push(xyPoints[n - 1]);
  return result;
}

export function formatPtsUsToTimecode(ptsUs: number): string {
  const safeUs = Math.max(0, Math.round(ptsUs));
  const totalMs = safeUs / 1000.0;
  const secs = Math.floor(totalMs / 1000);
  const msRem = Math.floor(totalMs % 1000);
  const mins = Math.floor(secs / 60);
  const secRem = secs % 60;
  return `${String(mins).padStart(2, "0")}:${String(secRem).padStart(2, "0")}.${String(msRem).padStart(3, "0")}`;
}

export function buildAuthenticatedMediaUrl(path: string): string {
  const token = getAuthToken();
  const base = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
  if (!token) return base;
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}token=${encodeURIComponent(token)}`;
}

// ============================================================================
// Typed API Client Helpers (`/api/tracer/*`)
// ============================================================================

export async function createOrGetTracerProject(params: {
  segment_id: string;
  title?: string;
  preset_id?: string;
  auto_analyze?: boolean;
}): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>("/api/tracer/projects", {
    method: "POST",
    body: JSON.stringify({
      segment_id: params.segment_id,
      title: params.title,
      preset_id: params.preset_id || "studio_neon",
      auto_analyze: params.auto_analyze ?? true,
    }),
  });
}

export async function getTracerProjectDetail(
  projectId: string
): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>(`/api/tracer/projects/${projectId}`);
}

export async function analyzeTracerProject(
  projectId: string,
  options?: {
    run_swing_tracer?: boolean;
    run_shot_tracer?: boolean;
    run_sync?: boolean;
  }
): Promise<{
  job_id: string;
  job_state: string;
  error_code?: string | null;
  project?: TracerProjectDetail;
}> {
  return apiFetch(`/api/tracer/projects/${projectId}/analyze`, {
    method: "POST",
    body: JSON.stringify({
      run_swing_tracer: options?.run_swing_tracer ?? true,
      run_shot_tracer: options?.run_shot_tracer ?? true,
      force_recompute: true,
      run_sync: options?.run_sync ?? true,
    }),
  });
}

export async function applyTracerManualEdits(
  projectId: string,
  params: {
    track_type: TrackType;
    edits: Array<{
      op: "add" | "move" | "delete";
      source_pts_us: number;
      source_frame_index?: number;
      x_norm?: number;
      y_norm?: number;
      point_role?: "manual_anchor" | "artistic_control";
      note?: string;
    }>;
    recompute_between_manual_anchors?: boolean;
    note?: string;
  }
): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>(
    `/api/tracer/projects/${projectId}/edits`,
    {
      method: "POST",
      body: JSON.stringify(params),
    }
  );
}

export async function rollbackTracerRevision(
  projectId: string,
  trackType: TrackType,
  revision: number
): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>(
    `/api/tracer/projects/${projectId}/tracks/${trackType}/rollback/${revision}`,
    {
      method: "POST",
    }
  );
}

export async function updateTracerAnchors(
  projectId: string,
  params: {
    address_pts_us?: number | null;
    top_pts_us?: number | null;
    impact_pts_us?: number | null;
    finish_pts_us?: number | null;
    launch_pts_us?: number | null;
    apex_pts_us?: number | null;
    landing_pts_us?: number | null;
    apex_xy_norm?: [number, number] | null;
    landing_xy_norm?: [number, number] | null;
    artistic_extension_enabled?: boolean;
    recompute_tracks?: boolean;
  }
): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>(
    `/api/tracer/projects/${projectId}/anchors`,
    {
      method: "PUT",
      body: JSON.stringify(params),
    }
  );
}

export async function updateTracerRecipe(
  projectId: string,
  params: {
    preset_id?: string;
    name?: string;
    recipe?: RenderRecipeV1;
  }
): Promise<TracerProjectDetail> {
  return apiFetch<TracerProjectDetail>(
    `/api/tracer/projects/${projectId}/recipe`,
    {
      method: "PUT",
      body: JSON.stringify(params),
    }
  );
}

export async function createTracerExport(params: {
  project_id?: string;
  project_ids?: string[];
  segment_ids?: string[];
  aspect_ratio: ExportAspectRatio;
  fps: 30 | 60;
  audio_mode: AudioMode;
  preset_id?: string;
  recipe_override?: RenderRecipeV1;
  run_sync?: boolean;
}): Promise<TracerExportItem> {
  return apiFetch<TracerExportItem>("/api/tracer/exports", {
    method: "POST",
    body: JSON.stringify({
      ...params,
      run_sync: params.run_sync ?? true,
    }),
  });
}

export async function listTracerPresets(): Promise<{
  presets: RenderRecipeV1[];
}> {
  return apiFetch<{ presets: RenderRecipeV1[] }>("/api/tracer/presets");
}

export async function listTracerModels(): Promise<{
  models: TracerModelItem[];
}> {
  return apiFetch<{ models: TracerModelItem[] }>("/api/tracer/models");
}
