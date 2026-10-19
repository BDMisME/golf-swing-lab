function resolveApiBaseUrl(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (envUrl && !envUrl.includes("localhost")) {
    return envUrl;
  }
  if (
    typeof window !== "undefined" &&
    window.location.hostname.endsWith(".zeabur.app")
  ) {
    return "https://golf-swing-lab-api.zeabur.app";
  }
  return envUrl || "http://localhost:28000";
}

export const API_BASE_URL = resolveApiBaseUrl();

export interface UserProfile {
  id: string;
  email: string;
  display_name: string;
}

export interface PracticeSession {
  id: string;
  title: string;
  date: string;
  club: string;
  handedness: "right" | "left";
  camera_angle: string;
  notes: string;
  video_count: number;
  swing_count: number;
  average_overall_score: number | null;
  best_swing_id: string | null;
  created_at: string;
}

export interface SubscoreDetail {
  key: string;
  label_zh: string;
  score: number | null;
  weight: number;
  effective_weight: number;
  raw_value: number | null;
  unit: string;
  ideal_range: string;
  confidence: number;
  observability: "observed_2d" | "estimated";
  source: string;
  how_calculated: string;
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
  id: string;
  metric_key: string;
  value: number | null;
  unit: string;
  confidence: number;
  source: string;
  observability: string;
}

export interface SwingSegmentItem {
  id: string;
  video_id: string;
  session_id: string;
  sequence_no: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  label: string;
  ball_strike_status: string;
  confidence: number;
  review_status: string;
  review_flags: string[];
  manual_override: boolean;
  notes: string;
  overall_score: number | null;
  ig_visual_score: number | null;
  coverage_ratio: number;
  score_version: string;
  model_version: string;
  subscores: Record<string, SubscoreDetail>;
  events: SwingEventItem[];
  metrics: SwingMetricItem[];
  keyframes?: Array<{
    time_ms: number;
    frame_idx: number;
    pose_confidence: number;
    landmarks: Record<string, { x: number; y: number; visibility: number }>;
  }>;
  ball_trajectory?: Array<{ time_ms: number; x: number; y: number }>;
  feedback_history?: Array<{
    id: string;
    category: string;
    previous_start_ms: number | null;
    previous_end_ms: number | null;
    new_start_ms: number | null;
    new_end_ms: number | null;
    notes: string;
    created_at: string;
  }>;
}

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("gsl_token");
}

export function setAuthToken(token: string, user?: UserProfile): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem("gsl_token", token);
  if (user) {
    window.localStorage.setItem("gsl_user", JSON.stringify(user));
  }
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem("gsl_token");
  window.localStorage.removeItem("gsl_user");
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (netErr: any) {
    const rawMsg = String(netErr?.message || netErr);
    if (rawMsg.includes("Load failed") || rawMsg.includes("Failed to fetch") || rawMsg.includes("NetworkError")) {
      throw new Error(`無法連線至 API 伺服器 (${API_BASE_URL})，請確認網路連線或伺服器正在重新啟動中`);
    }
    throw netErr;
  }

  if (!res.ok) {
    let errPayload: any = null;
    try {
      errPayload = await res.json();
    } catch {
      errPayload = { message: res.statusText };
    }
    throw new Error(errPayload?.message || `API 請求失敗 (${res.status})`);
  }

  return res.json() as Promise<T>;
}

export function formatMsToTimestamp(ms: number): string {
  const safeMs = Math.max(0, Math.round(ms));
  const totalSec = Math.floor(safeMs / 1000);
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  const tenths = Math.floor((safeMs % 1000) / 100);
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${tenths}`;
}

export function computeChunkPlan(
  fileSizeBytes: number,
  partSizeBytes: number = 8 * 1024 * 1024
): Array<{ partNumber: number; start: number; end: number; size: number }> {
  const safePart = Math.max(5 * 1024 * 1024, partSizeBytes);
  const chunks: Array<{
    partNumber: number;
    start: number;
    end: number;
    size: number;
  }> = [];
  let offset = 0;
  let partNumber = 1;
  while (offset < fileSizeBytes || partNumber === 1) {
    const end = Math.min(fileSizeBytes, offset + safePart);
    chunks.push({
      partNumber,
      start: offset,
      end,
      size: end - offset,
    });
    offset = end;
    partNumber += 1;
    if (offset >= fileSizeBytes) break;
  }
  return chunks;
}

export function formatCoverageStatus(
  overallScore: number | null | undefined,
  coverageRatio: number | null | undefined
): {
  displayScore: string;
  badgeText: string;
  isInsufficient: boolean;
} {
  const safeCov = typeof coverageRatio === "number" ? coverageRatio : 0;
  if (typeof overallScore !== "number" || safeCov < 0.7) {
    return {
      displayScore: "資料不足 (N/A)",
      badgeText: `指標覆蓋率 ${Math.round(safeCov * 100)}% (<70%)`,
      isInsufficient: true,
    };
  }
  return {
    displayScore: overallScore.toFixed(1),
    badgeText: `覆蓋率 ${Math.round(safeCov * 100)}%`,
    isInsufficient: false,
  };
}
