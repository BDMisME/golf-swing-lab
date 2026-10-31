/**
 * Golf Tracer Studio R4 — TypeScript Canonical Contracts (`apps/web/src/lib/tracer/types.ts`).
 */

export type TrackType = "club_head" | "ball";

export type TrackSourceType =
  | "detector_observed"
  | "shaft_geometry_estimated"
  | "optical_flow_estimated"
  | "kalman_predicted"
  | "interpolated"
  | "extrapolated"
  | "manually_annotated"
  | "artistic_only";

export type PositionRole =
  | "raw_observation"
  | "display_smoothed"
  | "manual_anchor"
  | "artistic_control"
  | "estimated_path";

export type OcclusionState =
  | "visible"
  | "occluded"
  | "blurred"
  | "out_of_frame"
  | "unobservable";

export type ShotTrackMode =
  | "AUTO_OBSERVED"
  | "AUTO_ASSISTED"
  | "MANUAL_ANCHORED"
  | "ARTISTIC_EXTENSION"
  | "UNAVAILABLE";

export type SwingTrackStatus =
  | "AUTO_TRACED"
  | "NEEDS_REVIEW"
  | "MANUAL_ASSISTED"
  | "MODEL_UNAVAILABLE"
  | "NOT_COMPARABLE";

export type TracerStyleName =
  | "Clean"
  | "Neon"
  | "Beam"
  | "Gradient"
  | "Tail"
  | "Pulse";

export type ExportAspectRatio = "original" | "16:9" | "9:16";
export type AudioMode = "preserve" | "mute";

export interface CanonicalTrackPoint {
  track_id: string;
  track_type: TrackType;
  segment_id: string;
  source_video_id: string;
  source_pts_us: number;
  source_frame_index: number;
  x_norm: number;
  y_norm: number;
  confidence: number;
  source_type: TrackSourceType;
  position_role: PositionRole;
  raw_observation?: {
    x_norm: number;
    y_norm: number;
    bbox?: number[];
    uncertainty_px?: number;
    detector_confidence?: number;
    evidence_kind?: string;
  } | null;
  phase: string;
  model_id?: string | null;
  evidence_frame_sha256?: string | null;
  occlusion_state: OcclusionState;
  uncertainty_px: number;
  error_flags: string[];
  coordinate_space_version: number;
  created_by: string;
  revision: number;
}

export interface TrackQualitySummary {
  track_type: TrackType;
  status: string;
  total_frames: number;
  total_points: number;
  direct_observed_count: number;
  geometry_estimated_count: number;
  optical_flow_count: number;
  kalman_predicted_count: number;
  interpolated_count: number;
  extrapolated_count: number;
  manual_count: number;
  artistic_count: number;
  direct_observation_coverage: number;
  geometry_assisted_coverage: number;
  manual_coverage: number;
  largest_gap_ms: number;
  mean_confidence: number;
  p50_uncertainty_px: number;
  p95_uncertainty_px: number;
  observed_range_pts_us: number[];
  predicted_ranges_pts_us: number[][];
  rejection_reasons: string[];
  end_to_end_eligible: boolean;
  view_angle: string;
  handedness: string;
  camera_motion_score: number;
  notes: string;
}

export interface SwingTracerLayerConfig {
  enabled: boolean;
  style: TracerStyleName;
  backswing_color_hex: string;
  downswing_color_hex: string;
  follow_through_color_hex: string;
  core_width_px_at_1080: number;
  glow_radius_px_at_1080: number;
  glow_intensity: number;
  opacity: number;
  tail_decay_ms: number;
  show_top_marker: boolean;
  show_impact_marker: boolean;
  show_predicted_dashed: boolean;
  show_uncertainty_band: boolean;
}

export interface ShotTracerLayerConfig {
  enabled: boolean;
  style: TracerStyleName;
  primary_color_hex: string;
  secondary_color_hex: string;
  core_width_px_at_1080: number;
  glow_radius_px_at_1080: number;
  glow_intensity: number;
  opacity: number;
  taper_start_ratio: number;
  taper_end_ratio: number;
  tail_decay_ms: number;
  pulse_speed_hz: number;
  show_apex_marker: boolean;
  show_impact_flash: boolean;
  show_landing_ring: boolean;
  show_predicted_dashed: boolean;
  show_uncertainty_band: boolean;
}

export interface ExportFormatConfig {
  aspect_ratio: ExportAspectRatio;
  fps: number;
  audio_mode: AudioMode;
  crf: number;
  show_provenance_watermark: boolean;
}

export interface RenderRecipeV1 {
  recipe_version: number;
  preset_id: string;
  name: string;
  swing_tracer: SwingTracerLayerConfig;
  shot_tracer: ShotTracerLayerConfig;
  export_format: ExportFormatConfig;
}

export interface TracerTrackRevision {
  id: string;
  project_id: string;
  track_type: TrackType;
  revision: number;
  parent_revision: number | null;
  status: string;
  point_count: number;
  points: CanonicalTrackPoint[];
  quality_summary: TrackQualitySummary;
  created_by: string;
  note: string;
  created_at: string;
}

export interface TracerAnchorRevision {
  id: string;
  project_id: string;
  revision: number;
  address_pts_us: number | null;
  top_pts_us: number | null;
  impact_pts_us: number | null;
  finish_pts_us: number | null;
  launch_pts_us: number | null;
  apex_pts_us: number | null;
  landing_pts_us: number | null;
  anchors_json: {
    artistic_extension_enabled?: boolean;
    apex_xy_norm?: [number, number] | null;
    landing_xy_norm?: [number, number] | null;
    [key: string]: any;
  };
  created_by: string;
  created_at: string;
}

export interface TracerProjectDetail {
  id: string;
  owner_id: string;
  session_id: string | null;
  video_id: string;
  segment_id: string;
  title: string;
  status: string;
  swing_status: SwingTrackStatus;
  shot_mode: ShotTrackMode;
  active_swing_revision: number;
  active_shot_revision: number;
  active_anchor_revision: number;
  active_recipe_id: string | null;
  source_video_sha256: string;
  coordinate_space_version: number;
  video_stream_url: string;
  original_video_stream_url: string;
  clip_start_pts_us: number;
  clip_end_pts_us: number;
  geometry: {
    coded_width: number;
    coded_height: number;
    rotation_deg: number;
    upright_width: number;
    upright_height: number;
    fps: number;
    is_vfr: boolean;
  };
  anchors: TracerAnchorRevision | null;
  recipe: RenderRecipeV1;
  swing_track: TracerTrackRevision | null;
  shot_track: TracerTrackRevision | null;
  metadata_json: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface TracerExportItem {
  id: string;
  owner_id: string;
  project_id: string | null;
  project_ids: string[];
  segment_ids: string[];
  aspect_ratio: ExportAspectRatio;
  fps: number;
  audio_mode: AudioMode;
  state: string;
  download_url: string | null;
  sidecar_url: string | null;
  mp4_sha256: string | null;
  sidecar_sha256: string | null;
  size_bytes: number;
  duration_ms: number;
  output_width: number;
  output_height: number;
  has_audio_stream: boolean;
  parity_report: {
    aspect_ratio?: string;
    fps?: number;
    checked_point_count?: number;
    max_coordinate_error_px?: number;
    mean_coordinate_error_px?: number;
    max_frame_pts_delta_us?: number;
    max_frame_delta_frames?: number;
    coordinate_parity_passed?: boolean;
    pts_parity_passed?: boolean;
  };
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface TracerModelItem {
  id: string;
  model_role: string;
  display_name: string;
  weights_path: string;
  weights_sha256: string | null;
  license_spdx: string;
  availability_status: string;
  metadata: Record<string, any>;
  updated_at: string;
}
