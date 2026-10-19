export interface UserOut {
  id: string;
  email: string;
  username: string;
  role: string;
}

export interface VideoJobSummary {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  progress: number;
  error_code?: string | null;
  error_message?: string | null;
}

export interface VideoItem {
  id: string;
  original_name: string;
  mime: string;
  size_bytes: number;
  duration_ms: number;
  width: number;
  height: number;
  rotation: number;
  fps: number;
  is_vfr: boolean;
  codec: string;
  ingest_status: string;
  quality_flags: Record<string, unknown>;
  latest_job?: VideoJobSummary | null;
}

export interface PracticeSessionItem {
  id: string;
  owner_id: string;
  title: string;
  date: string;
  club: string;
  handedness: "right" | "left";
  camera_angle: "DTL";
  notes: string;
  status: string;
  created_at: string;
  video_count: number;
  total_swings: number;
  valid_swings: number;
  needs_review_count: number;
  average_score: number | null;
  best_score: number | null;
  videos: VideoItem[];
}

export interface SwingEventItem {
  id: string;
  event_name: string;
  time_ms: number;
  confidence: number;
  detection_source: string;
  model_version: string;
  rationale: string;
}

export interface SwingMetricItem {
  metric_key: string;
  value: number | null;
  unit: string;
  confidence: number;
  source: string;
  observability: "observed_2d" | "estimated" | "unobservable";
}

export interface SubscoreDetail {
  label: string;
  score: number | null;
  weight: number;
  raw_value: number | null;
  unit: string;
  confidence: number;
  formula: string;
  how_calculated: string;
}

export interface SwingSegmentItem {
  id: string;
  video_id: string;
  sequence_no: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  label: "valid_swing" | "practice_swing" | "swing_candidate" | "rejected";
  ball_strike_status: "confirmed_strike" | "estimated_strike" | "strike_unknown" | "no_ball";
  confidence: number;
  review_status: "auto_accepted" | "needs_review" | "confirmed" | "rejected";
  review_flags: string[];
  version: string;
  manual_override: boolean;
  notes: string;
  top_time_ms?: number | null;
  impact_time_ms?: number | null;
  overall_score: number | null;
  ig_visual_score: number | null;
  partial_score: boolean;
  coverage: number;
  score_version: string;
  score_explanation: string;
  subscores: Record<string, SubscoreDetail | Record<string, unknown>>;
  events: SwingEventItem[];
  metrics: SwingMetricItem[];
  pose_artifact?: {
    quality_metadata: Record<string, unknown>;
    keyframes: Array<{
      time_ms: number;
      frame_idx: number;
      pose_confidence: number;
      landmarks: Record<string, { x: number; y: number; visibility: number }>;
    }>;
  };
  feedback_history?: Array<{
    id: string;
    category: string;
    before: Record<string, unknown>;
    after: Record<string, unknown>;
    note: string;
    created_at: string;
  }>;
}
