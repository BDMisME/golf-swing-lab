"use client";

import React, { useCallback, useEffect, useRef, useState, useMemo } from "react";
import {
  API_BASE_URL,
  apiFetch,
  formatMsToTimestamp,
  getAuthToken,
  SwingSegmentItem,
} from "@/lib/api";
import {
  AutoFramingResult,
  ComparisonLayout,
  FramingCalibration,
  PlaybackDriftController,
  PoseLandmarks,
  SwingSynchronizationEngine,
  SwingTimingTimeline,
  SyncAnchor,
  SyncMode,
} from "@/lib/syncEngine";
import { CleanMotionOverlay } from "@/components/CleanMotionOverlay";

export interface ReferenceSwingData {
  id: string;
  club_type: string;
  handedness: string;
  camera_angle: string;
  shot_type: string;
  title: string;
  reference_author: string;
  source_url: string;
  content_license: string;
  storage_key: string;
  thumbnail_url: string | null;
  verified_club: boolean;
  verified_camera_angle: boolean;
  analysis_status: string;
  reference_category: "professional_standard" | "community_reference" | "test_fixture";
  is_verified_standard: boolean;
  verification_notes: string;
  source_type: string;
  fps: number;
  duration_ms: number;
  sha256: string;
  event_timestamps: Record<string, number>;
  pose_artifact: Record<string, any>;
  calibration_params: FramingCalibration & {
    torso_length?: number;
    is_slow_motion?: boolean;
    source_start_ms?: number;
    source_end_ms?: number;
    source_sha256?: string;
  };
  is_default: boolean;
  notes: string;
  stream_url: string;
  media_processed?: boolean;
  pose_analyzed?: boolean;
  is_valid_clip?: boolean;
  events_reliable?: boolean;
  supports_realtime_sync?: boolean;
  supports_phase_sync?: boolean;
}

export interface ClubCatalogItem {
  club_type: string;
  status: "available" | "missing_reference";
  reference_count: number;
  default_reference?: ReferenceSwingData | null;
}

export interface PostureMetricItem {
  id: string;
  phase: string;
  phase_label: string;
  name: string;
  user_value: number | null;
  ref_value: number | null;
  diff: number | null;
  unit: string;
  description: string;
  reliability: "high" | "medium" | "low" | "unreliable";
  target_ms: number;
  status: "good" | "warning" | "needs_work" | "unknown";
}

export interface PriorityFixItem {
  phase: string;
  metric_name: string;
  diff_str: string;
  reliability: string;
  advice: string;
  drill_name: string;
  drill_steps: string[];
  retest_target: string;
}

export interface QuantitativePostureReport {
  swing_id: string;
  ref_id?: string;
  ref_title?: string;
  club_type: string;
  is_offline_mode: boolean;
  overall_reliability: string;
  metrics: PostureMetricItem[];
  priority_fix?: PriorityFixItem;
  disclaimer: string;
}

interface SwingComparisonPlayerProps {
  userSwing: SwingSegmentItem;
  defaultClub?: string;
  onClose?: () => void;
}

const ALL_CLUBS = [
  "Driver", "3W", "5W", "7W",
  "3H", "4H", "5H", "Hybrid",
  "3I", "4I", "5I", "6I", "7I", "8I", "9I",
  "PW", "GW/AW", "SW", "LW",
  "Putter",
];

const SPEED_OPTIONS = [
  { label: "0.25× 超慢", value: 0.25 },
  { label: "0.5× 慢放", value: 0.5 },
  { label: "0.75× 慢速", value: 0.75 },
  { label: "1.0× 原速", value: 1.0 },
];

export function SwingComparisonPlayer({
  userSwing,
  defaultClub = "7I",
  onClose,
}: SwingComparisonPlayerProps) {
  // 1. 目錄與球桿選擇狀態
  const [clubsCatalog, setClubsCatalog] = useState<ClubCatalogItem[]>([]);
  const [selectedClub, setSelectedClub] = useState<string>(defaultClub);
  const [refSwing, setRefSwing] = useState<ReferenceSwingData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  // 2. 佈局與播放控制狀態 (R3: 預設 0.5x 慢動作播放，支援同步與獨立模式)
  const [layout, setLayout] = useState<ComparisonLayout>("side_by_side");
  const [syncMode, setSyncMode] = useState<SyncMode>("real_time");
  const [syncAnchor, setSyncAnchor] = useState<SyncAnchor>("impact");
  const [manualOffsetMs, setManualOffsetMs] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(0.5); // 預設 0.5x 慢放
  const [ghostOpacity, setGhostOpacity] = useState<number>(0.5);

  // 控制模式：同步控制 vs 獨立檢視
  const [controlMode, setControlMode] = useState<"sync" | "independent">("sync");
  const [userSpeed, setUserSpeed] = useState<number>(0.5);
  const [refSpeed, setRefSpeed] = useState<number>(0.5);

  // 3. 畫面對齊 (Auto-Framing & Manual Calibration)
  const [calibration, setCalibration] = useState<FramingCalibration>({
    scale: 1.0,
    zoom: 1.0,
    offsetX: 0,
    offsetY: 0,
  });
  const [autoFramingStatus, setAutoFramingStatus] = useState<AutoFramingResult | null>(null);

  // 個人影片 Zoom & Pan
  const [userZoom, setUserZoom] = useState<number>(1.0);
  const [userOffsetX, setUserOffsetX] = useState<number>(0);
  const [userOffsetY, setUserOffsetY] = useState<number>(0);

  // 4. 骨架顯示開關
  const [showSkeleton, setShowSkeleton] = useState<boolean>(true);

  // 5. 當前播放時間 (ms)
  const [userCurrentMs, setUserCurrentMs] = useState<number>(userSwing.start_ms);
  const [refCurrentMs, setRefCurrentMs] = useState<number>(0);

  // 6. 影片 Element 參照
  const userVideoRef = useRef<HTMLVideoElement | null>(null);
  const refVideoRef = useRef<HTMLVideoElement | null>(null);

  // 7. 量化姿勢比較報告狀態 (P2)
  const [postureReport, setPostureReport] = useState<QuantitativePostureReport | null>(null);
  const [postureLoading, setPostureLoading] = useState<boolean>(false);
  const [postureError, setPostureError] = useState<string | null>(null);

  // 8. 手動匯入 / 上傳 Modal 狀態
  const [showImportModal, setShowImportModal] = useState<boolean>(false);
  const [importMode, setImportMode] = useState<"path" | "file">("file");
  const [importFilePath, setImportFilePath] = useState<string>("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [importTitle, setImportTitle] = useState<string>("");
  const [importAuthor, setImportAuthor] = useState<string>("社群使用者");
  const [importLicense, setImportLicense] = useState<string>("個人學習參考");
  const [importSourceUrl, setImportSourceUrl] = useState<string>("");
  const [importing, setImporting] = useState<boolean>(false);
  const [importError, setImportError] = useState<string | null>(null);

  // 載入 17 種球桿目錄與當前球桿示範影片
  const fetchCatalog = useCallback(async () => {
    try {
      setLoading(true);
      setCatalogError(null);
      const res = await apiFetch<{ clubs: ClubCatalogItem[]; references: ReferenceSwingData[] }>(
        "/api/reference-swings"
      );
      setClubsCatalog(res.clubs || []);

      const currentItem = res.clubs.find((c) => c.club_type === selectedClub);
      if (currentItem && currentItem.default_reference) {
        setRefSwing(currentItem.default_reference);
        const cal = currentItem.default_reference.calibration_params;
        setCalibration({
          scale: cal?.scale ?? 1.0,
          zoom: cal?.zoom ?? 1.0,
          offsetX: cal?.offsetX ?? cal?.offset_x ?? 0,
          offsetY: cal?.offsetY ?? cal?.offset_y ?? 0,
        });
      } else {
        setRefSwing(null);
      }
    } catch (err: any) {
      setCatalogError(err.message || "載入示範揮桿目錄失敗");
    } finally {
      setLoading(false);
    }
  }, [selectedClub]);

  useEffect(() => {
    fetchCatalog();
  }, [fetchCatalog]);

  // 切換球桿
  const handleSelectClub = (club: string) => {
    setSelectedClub(club);
    const item = clubsCatalog.find((c) => c.club_type === club);
    if (item && item.default_reference) {
      setRefSwing(item.default_reference);
      const cal = item.default_reference.calibration_params;
      setCalibration({
        scale: cal?.scale ?? 1.0,
        zoom: cal?.zoom ?? 1.0,
        offsetX: cal?.offsetX ?? cal?.offset_x ?? 0,
        offsetY: cal?.offsetY ?? cal?.offset_y ?? 0,
      });
    } else {
      setRefSwing(null);
    }
  };

  // 載入離線量化姿勢比較報告 (P2)
  const fetchPostureComparison = useCallback(async () => {
    try {
      setPostureLoading(true);
      setPostureError(null);
      const queryParams = new URLSearchParams();
      if (refSwing?.id) queryParams.set("ref_id", refSwing.id);
      queryParams.set("club_type", selectedClub);

      const res = await apiFetch<QuantitativePostureReport>(
        `/api/swings/${userSwing.id}/posture-comparison?${queryParams.toString()}`
      );
      setPostureReport(res);
    } catch (err: any) {
      setPostureError(err.message || "載入量化姿勢比較失敗");
    } finally {
      setPostureLoading(false);
    }
  }, [userSwing.id, refSwing?.id, selectedClub]);

  useEffect(() => {
    fetchPostureComparison();
  }, [fetchPostureComparison]);

  // 建立兩方時間軸對照模型
  const userTimeline = useMemo<SwingTimingTimeline>(() => {
    const evMap: Record<string, number> = {};
    (userSwing.events || []).forEach((e) => {
      evMap[e.event_name] = e.time_ms;
    });

    const startMs = userSwing.start_ms;
    const endMs = userSwing.end_ms;
    const addr = evMap["address"] || startMs;
    const takeaway = evMap["takeaway"] || addr + 300;
    const top = evMap["top"] || startMs + Math.round((endMs - startMs) * 0.45);
    const impact = evMap["impact_estimated"] || evMap["impact"] || startMs + Math.round((endMs - startMs) * 0.7);
    const finish = evMap["finish"] || endMs;
    const downswing = evMap["downswing"] || Math.round((top + impact) / 2);
    const follow = evMap["follow_through"] || Math.round((impact + finish) / 2);

    return {
      startMs,
      endMs,
      addressMs: addr,
      takeawayMs: takeaway,
      topMs: top,
      downswingMs: downswing,
      impactMs: impact,
      followThroughMs: follow,
      finishMs: finish,
    };
  }, [userSwing]);

  const refTimeline = useMemo<SwingTimingTimeline>(() => {
    if (!refSwing) {
      return {
        startMs: 0,
        endMs: 3000,
        addressMs: 300,
        takeawayMs: 700,
        topMs: 1400,
        downswingMs: 1600,
        impactMs: 1800,
        followThroughMs: 2200,
        finishMs: 2800,
      };
    }
    const ts = refSwing.event_timestamps || {};
    const dur = refSwing.duration_ms || 3500;
    return {
      startMs: 0,
      endMs: dur,
      addressMs: ts["address"] || 0,
      takeawayMs: ts["takeaway"] || 0,
      topMs: ts["top"] || 0,
      downswingMs: ts["downswing"] || 0,
      impactMs: ts["impact"] || 0,
      followThroughMs: ts["follow_through"] || 0,
      finishMs: ts["finish"] || 0,
    };
  }, [refSwing]);

  // 檢核 Phase Sync 是否合法
  const phaseValidation = useMemo(() => {
    return SwingSynchronizationEngine.validatePhaseTimeline(refTimeline);
  }, [refTimeline]);

  const isPhaseSyncValid = phaseValidation.valid;

  // 視角相容性檢核
  const angleCheck = useMemo(() => {
    if (!refSwing) return { compatible: true };
    return SwingSynchronizationEngine.checkAngleCompatibility(
      "DTL",
      refSwing.camera_angle
    );
  }, [refSwing]);

  // 2D 姿態驅動 Auto-Framing
  useEffect(() => {
    if (!refSwing) {
      setAutoFramingStatus(null);
      return;
    }

    const userPose = (userSwing.keyframes?.[0]?.landmarks as PoseLandmarks) || null;
    const refPose = (refSwing.pose_artifact?.landmarks as PoseLandmarks) || null;

    const result = SwingSynchronizationEngine.computeAutoFramingFromPose(
      userPose,
      refPose,
      "DTL",
      refSwing.camera_angle
    );
    setAutoFramingStatus(result);

    if (result.status === "auto_computed") {
      setCalibration((prev) => ({
        ...prev,
        scale: result.scale,
        offsetX: result.offsetX,
        offsetY: result.offsetY,
      }));
    }
  }, [refSwing, userSwing]);

  // 計算參考影片理論目標時間 (ms)
  const computeExpectedRefMs = useCallback(
    (uMs: number) => {
      if (!refSwing) return 0;
      if (syncMode === "phase_sync" && isPhaseSyncValid) {
        return SwingSynchronizationEngine.computePhaseSyncRefMs(
          uMs,
          userTimeline,
          refTimeline,
          manualOffsetMs
        );
      }
      return SwingSynchronizationEngine.computeRealTimeRefMs(
        uMs,
        userTimeline,
        refTimeline,
        syncAnchor,
        manualOffsetMs
      );
    },
    [refSwing, syncMode, isPhaseSyncValid, userTimeline, refTimeline, syncAnchor, manualOffsetMs]
  );

  // 影片元數據載入時進行初始定位
  const handleUserLoadedMetadata = useCallback(() => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    const targetSec = userTimeline.startMs / 1000;
    if (uVid.currentTime < targetSec - 0.1 || uVid.currentTime > userTimeline.endMs / 1000) {
      uVid.currentTime = targetSec;
    }
    uVid.playbackRate = controlMode === "independent" ? userSpeed : playbackSpeed;
    setUserCurrentMs(userTimeline.startMs);
  }, [userTimeline.startMs, userTimeline.endMs, controlMode, userSpeed, playbackSpeed]);

  const handleRefLoadedMetadata = useCallback(() => {
    const rVid = refVideoRef.current;
    if (!rVid || !refSwing) return;
    const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
    const targetSec = targetRefMs / 1000;
    if (Math.abs(rVid.currentTime - targetSec) > 0.1) {
      rVid.currentTime = targetSec;
    }
    rVid.playbackRate = controlMode === "independent" ? refSpeed : playbackSpeed;
    setRefCurrentMs(targetRefMs);
  }, [refSwing, userTimeline.startMs, computeExpectedRefMs, controlMode, refSpeed, playbackSpeed]);

  // 切換揮桿或球桿時重置定位
  const prevSwingKeyRef = useRef<string>(`${userSwing.id}_${selectedClub}`);
  useEffect(() => {
    const currentKey = `${userSwing.id}_${selectedClub}`;
    if (prevSwingKeyRef.current !== currentKey) {
      prevSwingKeyRef.current = currentKey;
      const uVid = userVideoRef.current;
      if (uVid && uVid.readyState >= 1) {
        uVid.currentTime = userTimeline.startMs / 1000;
        uVid.playbackRate = controlMode === "independent" ? userSpeed : playbackSpeed;
        setUserCurrentMs(userTimeline.startMs);
      }
      const rVid = refVideoRef.current;
      if (rVid && rVid.readyState >= 1 && refSwing) {
        const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
        rVid.currentTime = targetRefMs / 1000;
        rVid.playbackRate = controlMode === "independent" ? refSpeed : playbackSpeed;
        setRefCurrentMs(targetRefMs);
      }
    }
  }, [userSwing.id, selectedClub, refSwing, userTimeline.startMs, computeExpectedRefMs, controlMode, userSpeed, refSpeed, playbackSpeed]);

  // 慢動作速度變更控制 (P1: 不暫停、不 reload、不跳 0、不重設 zoom/pan)
  const handleSpeedChange = (speed: number) => {
    setPlaybackSpeed(speed);
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (uVid) {
      uVid.playbackRate = speed;
    }
    if (rVid && controlMode === "sync") {
      rVid.playbackRate = speed;
    }
  };

  // 同步播放生命週期控制：同時發動 play()
  const handlePlay = useCallback(async () => {
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    if (uVid.currentTime >= userTimeline.endMs / 1000 - 0.05 || uVid.currentTime < userTimeline.startMs / 1000) {
      uVid.currentTime = userTimeline.startMs / 1000;
    }

    const curUMs = Math.round(uVid.currentTime * 1000);
    setUserCurrentMs(curUMs);

    if (rVid && refSwing) {
      const targetRefMs = computeExpectedRefMs(curUMs);
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(targetRefMs);
      rVid.playbackRate = playbackSpeed;
    }

    uVid.playbackRate = playbackSpeed;

    try {
      if (rVid && refSwing) {
        await Promise.all([uVid.play(), rVid.play()]);
      } else {
        await uVid.play();
      }
      setIsPlaying(true);
    } catch (err) {
      console.warn("同步播放發動:", err);
    }
  }, [userTimeline, refSwing, computeExpectedRefMs, playbackSpeed]);

  // 同步暫停：同時 pause()
  const handlePause = useCallback(() => {
    userVideoRef.current?.pause();
    refVideoRef.current?.pause();
    setIsPlaying(false);
  }, []);

  const toggleSyncPlay = () => {
    if (isPlaying) {
      handlePause();
    } else {
      handlePlay();
    }
  };

  // 同步重播
  const handleSyncReplay = () => {
    handlePause();
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    uVid.currentTime = userTimeline.startMs / 1000;
    setUserCurrentMs(userTimeline.startMs);

    if (rVid && refSwing) {
      const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(targetRefMs);
    }
    handlePlay();
  };

  // 一鍵回到雙影片同步 (P1)
  const handleReturnToSync = () => {
    setControlMode("sync");
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    const curUMs = Math.round(uVid.currentTime * 1000);
    if (rVid && refSwing) {
      const targetRefMs = computeExpectedRefMs(curUMs);
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(targetRefMs);
      rVid.playbackRate = playbackSpeed;
    }
    uVid.playbackRate = playbackSpeed;
  };

  // 同步跳轉至指定關鍵事件錨點
  const jumpSyncAnchor = (anchor: SyncAnchor) => {
    handlePause();
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    const targetUserMs = SwingSynchronizationEngine.getAnchorTimeMs(userTimeline, anchor);
    uVid.currentTime = targetUserMs / 1000;
    setUserCurrentMs(targetUserMs);

    if (rVid && refSwing) {
      const targetRefMs = SwingSynchronizationEngine.computeRealTimeRefMs(
        targetUserMs,
        userTimeline,
        refTimeline,
        anchor,
        manualOffsetMs
      );
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(targetRefMs);
    }
  };

  // 一鍵停格：Top 停格 / Impact 停格 (P1)
  const freezeAtAnchor = (anchor: "top" | "impact") => {
    handlePause();
    jumpSyncAnchor(anchor);
  };

  // 同步逐格步進 (依使用者與示範各自真實 FPS 計算單影格時間)
  const stepSyncFrame = (deltaFrames: number) => {
    handlePause();
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    const uFps = (userSwing as any).fps || 30.0;
    const uFrameSec = 1.0 / uFps;
    const curSec = uVid.currentTime;
    const nextSec = Math.max(
      userTimeline.startMs / 1000,
      Math.min(userTimeline.endMs / 1000, curSec + deltaFrames * uFrameSec)
    );
    uVid.currentTime = nextSec;
    const uMs = Math.round(nextSec * 1000);
    setUserCurrentMs(uMs);

    if (rVid && refSwing) {
      const targetRefMs = computeExpectedRefMs(uMs);
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(Math.round(targetRefMs));
    }
  };

  // 單獨控制個人影片 (Individual User Video Controls)
  const toggleUserPlay = () => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    if (uVid.paused) {
      uVid.playbackRate = userSpeed;
      uVid.play().catch(() => {});
    } else {
      uVid.pause();
    }
  };

  const stepUserFrame = (deltaFrames: number) => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.pause();
    setIsPlaying(false);
    const uFps = (userSwing as any).fps || 30.0;
    const uFrameSec = 1.0 / uFps;
    const curSec = uVid.currentTime;
    const nextSec = Math.max(
      userTimeline.startMs / 1000,
      Math.min(userTimeline.endMs / 1000, curSec + deltaFrames * uFrameSec)
    );
    uVid.currentTime = nextSec;
    setUserCurrentMs(Math.round(nextSec * 1000));
  };

  const replayUser = () => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.currentTime = userTimeline.startMs / 1000;
    setUserCurrentMs(userTimeline.startMs);
    uVid.playbackRate = userSpeed;
    uVid.play().catch(() => {});
  };

  const handleUserSpeedChange = (speed: number) => {
    setUserSpeed(speed);
    if (userVideoRef.current) {
      userVideoRef.current.playbackRate = speed;
    }
  };

  // 單獨控制示範影片 (Individual Reference Video Controls)
  const toggleRefPlay = () => {
    const rVid = refVideoRef.current;
    if (!rVid) return;
    if (rVid.paused) {
      rVid.playbackRate = refSpeed;
      rVid.play().catch(() => {});
    } else {
      rVid.pause();
    }
  };

  const stepRefFrame = (deltaFrames: number) => {
    const rVid = refVideoRef.current;
    if (!rVid) return;
    rVid.pause();
    setIsPlaying(false);
    const rFps = refSwing?.fps || 30.0;
    const rFrameSec = 1.0 / rFps;
    const curSec = rVid.currentTime;
    const durSec = (refSwing?.duration_ms || 3000) / 1000;
    const nextSec = Math.max(0, Math.min(durSec, curSec + deltaFrames * rFrameSec));
    rVid.currentTime = nextSec;
    setRefCurrentMs(Math.round(nextSec * 1000));
  };

  const replayRef = () => {
    const rVid = refVideoRef.current;
    if (!rVid) return;
    rVid.currentTime = 0;
    setRefCurrentMs(0);
    rVid.playbackRate = refSpeed;
    rVid.play().catch(() => {});
  };

  const handleRefSpeedChange = (speed: number) => {
    setRefSpeed(speed);
    if (refVideoRef.current) {
      refVideoRef.current.playbackRate = speed;
    }
  };

  // 畫面位置與等比例縮放微調
  const adjustScale = (delta: number) => {
    setCalibration((prev) => ({
      ...prev,
      scale: Math.max(0.5, Math.min(2.0, parseFloat((prev.scale + delta).toFixed(2)))),
    }));
  };

  const adjustOffsetX = (delta: number) => {
    setCalibration((prev) => ({
      ...prev,
      offsetX: prev.offsetX + delta,
    }));
  };

  const adjustOffsetY = (delta: number) => {
    setCalibration((prev) => ({
      ...prev,
      offsetY: prev.offsetY + delta,
    }));
  };

  const resetAlignment = () => {
    setCalibration({
      scale: 1.0,
      zoom: 1.0,
      offsetX: 0,
      offsetY: 0,
    });
    setUserZoom(1.0);
    setUserOffsetX(0);
    setUserOffsetY(0);
    setManualOffsetMs(0);
  };

  // 點擊量化項目跳轉慢放 (P2 & P3)
  const jumpAndSlowPlayMetric = (targetMs: number, speed: number = 0.5) => {
    handlePause();
    setControlMode("sync");
    setPlaybackSpeed(speed);

    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    uVid.currentTime = targetMs / 1000;
    setUserCurrentMs(targetMs);
    uVid.playbackRate = speed;

    if (rVid && refSwing) {
      const targetRefMs = computeExpectedRefMs(targetMs);
      rVid.currentTime = targetRefMs / 1000;
      setRefCurrentMs(targetRefMs);
      rVid.playbackRate = speed;
    }

    setTimeout(async () => {
      try {
        if (rVid && refSwing) {
          await Promise.all([uVid.play(), rVid.play()]);
        } else {
          await uVid.play();
        }
        uVid.playbackRate = speed;
        if (rVid) rVid.playbackRate = speed;
        setIsPlaying(true);
      } catch (e) {
        console.warn("慢放跳轉播放失敗:", e);
      }
    }, 150);
  };

  // 核心時鐘監聽與平滑漂移校正循環 (Drift Monitor Loop via requestAnimationFrame)
  useEffect(() => {
    if (!isPlaying) return;
    let animId: number;

    const syncTick = () => {
      const uVid = userVideoRef.current;
      const rVid = refVideoRef.current;
      if (!uVid) return;

      const uCurSec = uVid.currentTime;
      const uMs = Math.round(uCurSec * 1000);
      setUserCurrentMs(uMs);

      // 單球播放循環或結束判定
      if (uCurSec >= userTimeline.endMs / 1000) {
        if (isLooping) {
          uVid.currentTime = userTimeline.startMs / 1000;
          if (rVid && refSwing && controlMode === "sync") {
            const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
            rVid.currentTime = targetRefMs / 1000;
          }
          uVid.playbackRate = playbackSpeed;
          uVid.play().catch(() => {});
          if (controlMode === "sync") {
            rVid?.play().catch(() => {});
          }
        } else {
          uVid.pause();
          rVid?.pause();
          setIsPlaying(false);
          return;
        }
      }

      // 只有在「同步模式」下才執行漂移校正 (獨立檢視模式下嚴格停用，防止強行覆蓋)
      if (controlMode === "sync" && rVid && refSwing && !rVid.paused) {
        const expectedRefSec = computeExpectedRefMs(uMs) / 1000;
        setRefCurrentMs(Math.round(rVid.currentTime * 1000));

        const driftRes = PlaybackDriftController.evaluateDrift(
          rVid.currentTime,
          expectedRefSec,
          playbackSpeed
        );

        if (driftRes.action === "adjust_rate") {
          rVid.playbackRate = driftRes.recommendedPlaybackRate;
        } else if (driftRes.action === "hard_seek") {
          rVid.currentTime = driftRes.targetRefTimeSec;
          rVid.playbackRate = playbackSpeed;
        } else {
          if (Math.abs(rVid.playbackRate - playbackSpeed) > 0.01) {
            rVid.playbackRate = playbackSpeed;
          }
        }
      }

      animId = requestAnimationFrame(syncTick);
    };

    animId = requestAnimationFrame(syncTick);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, isLooping, userTimeline, refSwing, computeExpectedRefMs, controlMode, playbackSpeed]);

  // 手動匯入 / 上傳示範影片表單送出
  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setImporting(true);
    setImportError(null);

    try {
      if (importMode === "file" && uploadFile) {
        const formData = new FormData();
        formData.append("file", uploadFile);
        formData.append("club_type", selectedClub);
        formData.append("handedness", "right");
        formData.append("camera_angle", "DTL");
        formData.append("title", importTitle || `標準 ${selectedClub} 示範揮桿`);
        formData.append("reference_author", importAuthor);
        formData.append("content_license", importLicense);
        formData.append("source_url", importSourceUrl);
        formData.append("is_default", "true");

        const token = getAuthToken();
        const res = await fetch(`${API_BASE_URL}/api/reference-swings/upload`, {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `上傳失敗 (${res.status})`);
        }
      } else {
        if (!importFilePath) throw new Error("請輸入合法的本機影片檔案路徑");
        await apiFetch("/api/reference-swings/import-local", {
          method: "POST",
          body: JSON.stringify({
            file_path: importFilePath,
            club_type: selectedClub,
            handedness: "right",
            camera_angle: "DTL",
            shot_type: "full_swing",
            title: importTitle || `標準 ${selectedClub} 示範揮桿`,
            reference_author: importAuthor,
            content_license: importLicense,
            source_url: importSourceUrl,
            is_default: true,
          }),
        });
      }

      setShowImportModal(false);
      setUploadFile(null);
      setImportFilePath("");
      await fetchCatalog();
    } catch (err: any) {
      setImportError(err.message || "匯入示範影片失敗");
    } finally {
      setImporting(false);
    }
  };

  const userVideoSrc = useMemo(() => {
    const token = getAuthToken() || "";
    return `${API_BASE_URL}/api/videos/${userSwing.video_id}/stream${
      token ? `?token=${encodeURIComponent(token)}` : ""
    }`;
  }, [userSwing.video_id]);

  const refVideoSrc = useMemo(() => {
    if (!refSwing) return "";
    const token = getAuthToken() || "";
    return `${API_BASE_URL}${refSwing.stream_url}${
      token ? `?token=${encodeURIComponent(token)}` : ""
    }`;
  }, [refSwing?.id, refSwing?.stream_url]);

  // 計算當前動作階段
  const currentPhaseName = useMemo(() => {
    if (userCurrentMs < userTimeline.takeawayMs) return "Address (站姿設定)";
    if (userCurrentMs < userTimeline.topMs - 80) return "Backswing (上桿引導)";
    if (userCurrentMs <= userTimeline.topMs + 80) return "Top (上桿頂點)";
    if (userCurrentMs < userTimeline.impactMs - 50) return "Downswing (下桿加速)";
    if (userCurrentMs <= userTimeline.impactMs + 50) return "Impact (擊球瞬間)";
    if (userCurrentMs < userTimeline.finishMs - 200) return "Follow Through (送桿)";
    return "Finish (收桿平衡)";
  }, [userCurrentMs, userTimeline]);

  return (
    <div className="rounded-2xl border border-sky-800/80 bg-gradient-to-b from-[#0a141f] to-[#070d14] p-4 text-white shadow-xl space-y-4">
      {/* 頂部標題與狀態列 (P0-3 誠信標題 + 離線模式提示) */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex h-3 w-3 rounded-full bg-cyan-400 animate-pulse" />
          <h2 className="text-base font-bold text-white tracking-wide">
            {refSwing?.is_verified_standard
              ? "已驗證職業示範對照"
              : "揮桿雙影片對照 (Dual Swing Comparison)"}
          </h2>
          <span className="rounded bg-sky-950 px-2 py-0.5 text-xs text-sky-300 font-mono border border-sky-800/50">
            {controlMode === "sync" ? "雙影片同步模式" : "獨立檢視模式"}
          </span>
          <span className="rounded bg-emerald-950/80 px-2 py-0.5 text-xs text-emerald-300 font-semibold border border-emerald-800/40">
            🔒 離線量化姿勢教練 (Offline Mode)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {controlMode === "independent" && (
            <button
              type="button"
              onClick={handleReturnToSync}
              className="rounded-lg border border-cyan-500 bg-cyan-950/70 px-2.5 py-1 text-xs font-bold text-cyan-300 hover:bg-cyan-900 transition shadow-[0_0_8px_rgba(6,182,212,0.3)]"
            >
              🔗 一鍵回到雙影片同步
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-700 bg-gray-900/80 px-2.5 py-1 text-xs text-gray-300 hover:bg-gray-800 hover:text-white transition"
              title="關閉比較對照模式"
            >
              ✕ 返回單球播放
            </button>
          )}
        </div>
      </div>

      {/* 球桿選擇器與三態統計 (誠信原則透明揭露) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-gray-400 flex-wrap gap-2">
          <span className="font-semibold text-gray-300">選擇球桿參考 ({ALL_CLUBS.length} 種分類)：</span>
          <div className="flex items-center gap-3 text-[11px] flex-wrap">
            <span>
              可用示範影片：
              <strong className="text-emerald-400 font-bold">
                {clubsCatalog.filter((c) => c.status === "available").length}
              </strong>{" "}
              / {ALL_CLUBS.length} 種
            </span>
            <span>
              全身姿勢比對：
              <strong className="text-cyan-400 font-bold">
                {
                  clubsCatalog.filter(
                    (c) =>
                      c.default_reference &&
                      c.default_reference.camera_angle?.toLowerCase() === "dtl"
                  ).length
                }
              </strong>{" "}
              / {ALL_CLUBS.length} 種
            </span>
            <span className="text-amber-400 font-semibold">
              已驗證職業標準：
              <strong>
                {
                  clubsCatalog.filter(
                    (c) => Boolean(c.default_reference?.is_verified_standard)
                  ).length
                }
              </strong>{" "}
              支 (尚無)
            </span>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 p-1 bg-black/40 rounded-xl border border-gray-800/80">
          {ALL_CLUBS.map((club) => {
            const catalogItem = clubsCatalog.find((c) => c.club_type === club);
            const isAvailable = catalogItem?.status === "available";
            const isSelected = selectedClub === club;

            return (
              <button
                key={club}
                type="button"
                onClick={() => handleSelectClub(club)}
                className={`relative px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
                  isSelected
                    ? "bg-cyan-500 text-black border-cyan-400 font-bold shadow-[0_0_8px_rgba(6,182,212,0.4)]"
                    : isAvailable
                    ? "bg-gray-900/90 text-cyan-200 border-cyan-900/60 hover:border-cyan-700"
                    : "bg-gray-950/60 text-gray-500 border-gray-900 hover:border-gray-800"
                }`}
                title={
                  isAvailable
                    ? `${club} (已收錄示範影片)`
                    : `${club} (尚無示範素材，點擊可手動匯入)`
                }
              >
                <span>{club}</span>
                {isAvailable && !isSelected && (
                  <span className="absolute -top-1 -right-1 h-2 w-2 rounded-full bg-emerald-400" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 視角與素材限制警示 */}
      {!angleCheck.compatible && angleCheck.warning && (
        <div className="flex items-center gap-2 rounded-xl bg-amber-950/70 border border-amber-700/60 p-2.5 text-xs text-amber-200">
          <span className="text-base">⚠️</span>
          <span>{angleCheck.warning}</span>
        </div>
      )}

      {/* 示範影片資訊列與六維度狀態標記 */}
      {refSwing ? (
        <div className="flex flex-col gap-2 rounded-xl bg-black/40 border border-gray-800/80 px-3 py-2 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-cyan-300">示範素材：{refSwing.title}</span>
              <span className="text-gray-400">作者：{refSwing.reference_author}</span>

              {refSwing.reference_category === "test_fixture" && (
                <span className="rounded bg-amber-950/80 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-700/60 flex items-center gap-1">
                  ⚠️ 技術測試素材 (Test Fixture)
                </span>
              )}
              {refSwing.camera_angle.toLowerCase() === "close_up" && (
                <span className="rounded bg-rose-950/80 px-2 py-0.5 text-[10px] font-bold text-rose-300 border border-rose-700/60 flex items-center gap-1">
                  ⚠️ 打擊區特寫 (非完整 DTL)
                </span>
              )}
              {!refSwing.is_verified_standard && (
                <span className="rounded bg-gray-900 px-1.5 py-0.5 text-[10px] text-gray-400 border border-gray-800">
                  未經認證參考
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] text-gray-400">
              <span>授權：{refSwing.content_license}</span>
              <span>FPS: {refSwing.fps}</span>
              <button
                type="button"
                onClick={() => setShowImportModal(true)}
                className="text-cyan-400 hover:underline"
              >
                更換示範影片
              </button>
            </div>
          </div>

          {/* 六維度技術狀態徽章 */}
          <div className="flex items-center gap-1.5 flex-wrap pt-1 border-t border-gray-800/60">
            <span className="text-[10px] text-gray-400 font-semibold mr-1">狀態驗證：</span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.media_processed !== false
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-800/40"
                  : "bg-rose-950/80 text-rose-300 border-rose-800/40"
              }`}
            >
              {refSwing.media_processed !== false ? "✓ 媒體處理" : "✗ 媒體待轉碼"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.pose_analyzed !== false
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-800/40"
                  : "bg-amber-950/80 text-amber-300 border-amber-800/40"
              }`}
            >
              {refSwing.pose_analyzed !== false ? "✓ 2D骨架" : "⚠️ 骨架待抽"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.is_valid_clip !== false
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-800/40"
                  : "bg-amber-950/80 text-amber-300 border-amber-800/40"
              }`}
            >
              {refSwing.is_valid_clip !== false ? "✓ 單球剪輯" : "⚠️ 範圍待修"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.events_reliable
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-800/40"
                  : "bg-amber-950/80 text-amber-300 border-amber-800/40"
              }`}
            >
              {refSwing.events_reliable ? "✓ 事件可信" : "⚠️ 待手動校正"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.supports_realtime_sync
                  ? "bg-cyan-950/80 text-cyan-300 border-cyan-800/40"
                  : "bg-amber-950/80 text-amber-300 border-amber-800/40"
              }`}
            >
              {refSwing.supports_realtime_sync ? "✓ 原速同步" : "⏱️ 慢動作 (僅階段對齊)"}
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold border ${
                refSwing.supports_phase_sync
                  ? "bg-purple-950/80 text-purple-300 border-purple-800/40"
                  : "bg-rose-950/80 text-rose-300 border-rose-800/40"
              }`}
            >
              {refSwing.supports_phase_sync ? "✓ 階段對齊" : "✗ 無法階段對齊"}
            </span>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-gray-900/60 border border-dashed border-gray-700 p-3 text-xs text-gray-400">
          <div className="flex items-center gap-2">
            <span>
              ℹ️ 目前球桿 ({selectedClub}) 尚未收錄標準示範影片 (missing_reference)
              {selectedClub === "Hybrid" && " — 系統支援 3H/4H/5H，通用 Hybrid 暫無明確號數示範，請選擇具體號數或手動匯入。"}
              {["3H", "4H", "5H"].includes(selectedClub) && ` — ${selectedClub} 示範影片待補，不可拿通用 Hybrid 混充，可手動匯入。`}
              {selectedClub === "7W" && " — 7號木桿示範影片待補，可手動匯入。"}
              {selectedClub === "3I" && " — 3號鐵桿示範影片待補，可手動匯入。"}
              {selectedClub === "GW/AW" && " — GW/AW (50~52°) 示範影片待補，可手動匯入。"}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowImportModal(true)}
            className="rounded-lg bg-cyan-700/80 hover:bg-cyan-600 px-3 py-1 font-semibold text-white transition text-xs"
          >
            ＋ 匯入此球桿的示範影片
          </button>
        </div>
      )}

      {/* 動作階段高亮條 (Progress Phase Indicator) */}
      <div className="rounded-xl bg-black/60 border border-gray-800 px-3 py-2 text-xs flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">當前動作階段：</span>
          <span className="font-bold text-cyan-300 bg-cyan-950/80 px-2 py-0.5 rounded border border-cyan-800/50">
            {currentPhaseName}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => freezeAtAnchor("top")}
            className="rounded-lg border border-cyan-800/60 bg-cyan-950/40 px-2 py-1 text-xs font-semibold text-cyan-300 hover:bg-cyan-900/60 transition"
            title="一鍵雙側暫停並停格在 Top 上桿頂點"
          >
            🎯 Top 停格比對
          </button>
          <button
            type="button"
            onClick={() => freezeAtAnchor("impact")}
            className="rounded-lg border border-amber-800/60 bg-amber-950/40 px-2 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-900/60 transition"
            title="一鍵雙側暫停並停格在 Impact 擊球瞬間"
          >
            💥 Impact 停格比對
          </button>
          <button
            type="button"
            onClick={() => setShowSkeleton(!showSkeleton)}
            className={`rounded-lg border px-2 py-1 text-xs font-semibold transition ${
              showSkeleton
                ? "border-emerald-600 bg-emerald-950/60 text-emerald-300"
                : "border-gray-800 bg-black/40 text-gray-500 hover:border-gray-700"
            }`}
          >
            {showSkeleton ? "🦴 骨架標記：開啟" : "🦴 骨架標記：隱藏"}
          </button>
        </div>
      </div>

      {/* 影片播放區域 (單一 DOM 樹架構，維持 object-contain 原始長寬比防拉伸) */}
      <div className="relative rounded-xl overflow-hidden bg-black border border-gray-800">
        <div
          className={
            layout === "side_by_side"
              ? "grid grid-cols-1 md:grid-cols-2 gap-1 bg-gray-950"
              : layout === "stacked"
              ? "flex flex-col gap-1 bg-gray-950"
              : "relative aspect-video bg-black flex items-center justify-center overflow-hidden"
          }
        >
          {/* 示範影片容器 (左側 / 上方 / 疊影層) */}
          <div
            className={
              layout === "ghost_overlay"
                ? "absolute inset-0 w-full h-full z-10 pointer-events-none mix-blend-screen overflow-hidden"
                : layout === "stacked"
                ? "relative aspect-[21/9] md:aspect-video bg-black flex items-center justify-center overflow-hidden"
                : "relative aspect-video bg-black flex items-center justify-center overflow-hidden"
            }
            style={layout === "ghost_overlay" ? { opacity: ghostOpacity } : undefined}
          >
            {layout !== "ghost_overlay" && (
              <div className="absolute top-2 left-2 z-10 flex flex-col gap-1 items-start">
                <span className="rounded bg-black/75 px-2 py-0.5 text-[11px] font-bold text-cyan-300 border border-cyan-800/40">
                  {refSwing?.reference_category === "test_fixture"
                    ? `技術測試基準 (${selectedClub})`
                    : refSwing?.is_verified_standard
                    ? `已驗證職業示範 (${selectedClub})`
                    : `示範對照 (${selectedClub})`}
                </span>
                {Boolean(refSwing?.calibration_params?.is_slow_motion || (refSwing?.pose_artifact as any)?.is_slow_motion) && (
                  <span className="rounded bg-amber-950/80 px-2 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-800/40">
                    ⏱️ 慢動作示範 (僅供姿勢影格比較，不計真實節奏)
                  </span>
                )}
              </div>
            )}
            {refSwing ? (
              <video
                ref={refVideoRef}
                src={refVideoSrc}
                playsInline
                muted
                preload="auto"
                crossOrigin="anonymous"
                onLoadedMetadata={handleRefLoadedMetadata}
                onCanPlay={handleRefLoadedMetadata}
                className="w-full h-full object-contain"
                style={{
                  transform: `scale(${calibration.scale * calibration.zoom}) translate(${
                    calibration.offsetX
                  }px, ${calibration.offsetY}px)`,
                }}
              />
            ) : (
              <div className="text-gray-500 text-xs text-center p-4">
                尚無此球桿示範影片 (missing_reference)
              </div>
            )}
          </div>

          {/* 個人揮桿容器 (右側 / 下方 / 底層) */}
          <div
            className={
              layout === "ghost_overlay"
                ? "absolute inset-0 w-full h-full z-0 overflow-hidden"
                : layout === "stacked"
                ? "relative aspect-[21/9] md:aspect-video bg-black flex items-center justify-center overflow-hidden"
                : "relative aspect-video bg-black flex items-center justify-center overflow-hidden"
            }
          >
            {layout !== "ghost_overlay" ? (
              <span className="absolute top-2 left-2 z-10 rounded bg-black/70 px-2 py-0.5 text-[11px] font-bold text-emerald-300 border border-emerald-800/40">
                個人揮桿 (Swing #{userSwing.sequence_no})
              </span>
            ) : (
              <span className="absolute top-2 left-2 z-20 rounded bg-black/75 px-2.5 py-1 text-xs font-bold text-cyan-300 border border-cyan-700/60">
                疊影對照 · 示範透明度 {Math.round(ghostOpacity * 100)}%
              </span>
            )}
            <video
              ref={userVideoRef}
              src={userVideoSrc}
              playsInline
              muted
              preload="auto"
              crossOrigin="anonymous"
              onLoadedMetadata={handleUserLoadedMetadata}
              onCanPlay={handleUserLoadedMetadata}
              className="w-full h-full object-contain"
              style={{
                transform: `scale(${userZoom}) translate(${userOffsetX}px, ${userOffsetY}px)`,
              }}
            />
            {showSkeleton && (
              <CleanMotionOverlay
                videoRef={userVideoRef}
                keyframes={(userSwing.keyframes as any) || []}
                events={userSwing.events || []}
                startMs={userTimeline.startMs}
                endMs={userTimeline.endMs}
              />
            )}
          </div>
        </div>
      </div>

      {/* 慢動作與同步播放控制台 (P1 強化版) */}
      <div className="space-y-3 bg-black/50 p-3 rounded-xl border border-gray-800/80">
        {/* 進度顯示與時鐘狀態 */}
        <div className="flex flex-wrap items-center justify-between text-xs text-gray-300 gap-2 font-mono">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 font-bold">
              你：{formatMsToTimestamp(userCurrentMs)}
            </span>
            <span className="text-gray-500">|</span>
            <span className="text-cyan-400 font-bold">
              示範：{formatMsToTimestamp(refCurrentMs)}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {controlMode === "independent" && (
              <span className="text-[11px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40 font-sans">
                ⚡ 獨立檢視模式中（停用自動漂移校正）
              </span>
            )}
            {syncMode === "phase_sync" && controlMode === "sync" && (
              <span className="text-[11px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40 font-sans">
                ⚡ 時間正規化比較中（各動作階段強制同步，非真實揮桿速度）
              </span>
            )}
            <span className="text-gray-400 text-[11px]">
              偏移: {manualOffsetMs > 0 ? `+${manualOffsetMs}` : manualOffsetMs}ms
            </span>
          </div>
        </div>

        {/* 慢動作速度選項群 (P1: 0.25x / 0.5x (預設) / 0.75x / 1.0x / 一鍵回復 1.0x) */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-gray-800 text-xs">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-gray-400 font-semibold mr-1">慢動作播放速度：</span>
            {SPEED_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => handleSpeedChange(opt.value)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
                  playbackSpeed === opt.value
                    ? "bg-cyan-500 text-black border-cyan-400 font-bold shadow-[0_0_8px_rgba(6,182,212,0.4)]"
                    : "bg-black/60 text-gray-300 border-gray-800 hover:border-gray-600"
                }`}
              >
                {opt.label}
              </button>
            ))}
            {playbackSpeed !== 1.0 && (
              <button
                type="button"
                onClick={() => handleSpeedChange(1.0)}
                className="px-2 py-1 rounded-lg text-xs font-semibold border border-gray-700 bg-gray-900 text-gray-300 hover:text-white transition"
                title="一鍵回復原速 (1.0x)"
              >
                ↺ 回復 1.0×
              </button>
            )}
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-gray-400 font-semibold mr-1">控制模式：</span>
            <button
              type="button"
              onClick={() => {
                if (controlMode === "independent") {
                  handleReturnToSync();
                } else {
                  setControlMode("sync");
                }
              }}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
                controlMode === "sync"
                  ? "bg-sky-600 text-white border-sky-500 font-bold"
                  : "bg-black/60 text-gray-400 border-gray-800 hover:border-gray-700"
              }`}
            >
              雙影片同步
            </button>
            <button
              type="button"
              onClick={() => setControlMode("independent")}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition border ${
                controlMode === "independent"
                  ? "bg-amber-600 text-white border-amber-500 font-bold"
                  : "bg-black/60 text-gray-400 border-gray-800 hover:border-gray-700"
              }`}
              title="展開各影片獨立控制"
            >
              {controlMode === "independent" ? "獨立檢視" : "展開各影片獨立控制"}
            </button>
          </div>
        </div>

        {/* 同步模式主控制按鈕群 */}
        {controlMode === "sync" ? (
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-gray-800">
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={toggleSyncPlay}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 font-bold text-white hover:bg-emerald-500 transition shadow-sm text-xs"
                title={isPlaying ? "暫停同步播放" : "啟動雙影片同步播放"}
              >
                <span>{isPlaying ? "❚❚ 暫停" : `▶ 同步播放 (${playbackSpeed}×)`}</span>
              </button>

              <button
                type="button"
                onClick={handleSyncReplay}
                className="flex items-center gap-1 rounded-lg border border-cyan-700/60 bg-cyan-950/40 px-2.5 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-900/60 transition"
                title="兩段影片同步由對齊起點重新播放"
              >
                <span>↺ 重新播放</span>
              </button>

              <button
                type="button"
                onClick={() => setIsLooping(!isLooping)}
                className={`rounded-lg px-2.5 py-1.5 text-xs font-semibold transition border ${
                  isLooping
                    ? "border-emerald-500 bg-emerald-950/60 text-emerald-300 shadow-[0_0_8px_rgba(16,185,129,0.3)]"
                    : "border-gray-800 bg-black/40 text-gray-400 hover:border-gray-700"
                }`}
                title="開啟/關閉同步循環播放"
              >
                {isLooping ? "⟲ 循環開啟" : "⟲ 循環關閉"}
              </button>
            </div>

            {/* 逐幀步進 (±1f, ±5f) */}
            <div className="flex items-center gap-1 text-xs">
              <button
                type="button"
                onClick={() => stepSyncFrame(-5)}
                className="rounded-lg border border-gray-800 bg-black/60 px-2 py-1 text-gray-300 hover:border-gray-600"
                title="後退 5 幀 (~167ms)"
              >
                &larr; -5f
              </button>
              <button
                type="button"
                onClick={() => stepSyncFrame(-1)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2 py-1 font-semibold text-white hover:border-cyan-500"
                title="後退 1 幀 (~33ms)"
              >
                &larr; -1f
              </button>
              <button
                type="button"
                onClick={() => stepSyncFrame(1)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2 py-1 font-semibold text-white hover:border-cyan-500"
                title="前進 1 幀 (~33ms)"
              >
                +1f &rarr;
              </button>
              <button
                type="button"
                onClick={() => stepSyncFrame(5)}
                className="rounded-lg border border-gray-800 bg-black/60 px-2 py-1 text-gray-300 hover:border-gray-600"
                title="前進 5 幀 (~167ms)"
              >
                +5f &rarr;
              </button>
            </div>

            {/* 佈局切換 */}
            <div className="flex items-center gap-1 bg-black/60 p-0.5 rounded-lg border border-gray-800 text-xs">
              <button
                type="button"
                onClick={() => setLayout("side_by_side")}
                className={`px-2 py-1 rounded ${
                  layout === "side_by_side" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
                }`}
              >
                左右並列
              </button>
              <button
                type="button"
                onClick={() => setLayout("stacked")}
                className={`px-2 py-1 rounded ${
                  layout === "stacked" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
                }`}
              >
                上下堆疊
              </button>
              <button
                type="button"
                onClick={() => setLayout("ghost_overlay")}
                className={`px-2 py-1 rounded ${
                  layout === "ghost_overlay" ? "bg-cyan-600 text-white font-bold" : "text-gray-400 hover:text-white"
                }`}
              >
                疊影透視
              </button>
            </div>
          </div>
        ) : (
          /* 獨立檢視模式控制面板 (P1) */
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1 border-t border-gray-800 text-xs">
            {/* 示範影片獨立控制 */}
            <div className="p-2.5 rounded-lg bg-cyan-950/20 border border-cyan-900/40 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-cyan-300 font-bold text-xs">示範影片 ({selectedClub}) 獨立控制</span>
                <span className="text-gray-400 font-mono text-[11px]">{formatMsToTimestamp(refCurrentMs)}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  type="button"
                  onClick={toggleRefPlay}
                  className="rounded bg-cyan-800 px-3 py-1 font-semibold text-white hover:bg-cyan-700"
                >
                  ▶/⏸ 播放/暫停
                </button>
                <button
                  type="button"
                  onClick={() => stepRefFrame(-1)}
                  className="rounded bg-black/60 px-2 py-1 border border-gray-800 text-gray-300 hover:border-cyan-500"
                >
                  -1f
                </button>
                <button
                  type="button"
                  onClick={() => stepRefFrame(1)}
                  className="rounded bg-black/60 px-2 py-1 border border-gray-800 text-gray-300 hover:border-cyan-500"
                >
                  +1f
                </button>
                <button
                  type="button"
                  onClick={replayRef}
                  className="rounded bg-cyan-950 px-2 py-1 border border-cyan-800 text-cyan-300"
                >
                  ↺ 重播
                </button>
                <div className="flex items-center gap-1 ml-auto">
                  <span className="text-gray-400 text-[10px]">速度:</span>
                  {[0.25, 0.5, 1.0].map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => handleRefSpeedChange(s)}
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        refSpeed === s ? "bg-cyan-500 text-black font-bold" : "bg-black/50 text-gray-400"
                      }`}
                    >
                      {s}x
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* 個人影片獨立控制 */}
            <div className="p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-900/40 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-emerald-300 font-bold text-xs">個人揮桿 (#{userSwing.sequence_no}) 獨立控制</span>
                <span className="text-gray-400 font-mono text-[11px]">{formatMsToTimestamp(userCurrentMs)}</span>
              </div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <button
                  type="button"
                  onClick={toggleUserPlay}
                  className="rounded bg-emerald-800 px-3 py-1 font-semibold text-white hover:bg-emerald-700"
                >
                  ▶/⏸ 播放/暫停
                </button>
                <button
                  type="button"
                  onClick={() => stepUserFrame(-1)}
                  className="rounded bg-black/60 px-2 py-1 border border-gray-800 text-gray-300 hover:border-emerald-500"
                >
                  -1f
                </button>
                <button
                  type="button"
                  onClick={() => stepUserFrame(1)}
                  className="rounded bg-black/60 px-2 py-1 border border-gray-800 text-gray-300 hover:border-emerald-500"
                >
                  +1f
                </button>
                <button
                  type="button"
                  onClick={replayUser}
                  className="rounded bg-emerald-950 px-2 py-1 border border-emerald-800 text-emerald-300"
                >
                  ↺ 重播
                </button>
                <div className="flex items-center gap-1 ml-auto">
                  <span className="text-gray-400 text-[10px]">速度:</span>
                  {[0.25, 0.5, 1.0].map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => handleUserSpeedChange(s)}
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        userSpeed === s ? "bg-emerald-500 text-black font-bold" : "bg-black/50 text-gray-400"
                      }`}
                    >
                      {s}x
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 關鍵事件錨點跳轉與同步模式切換 */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-800/60 text-xs">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-gray-400">對齊錨點：</span>
            {(["address", "top", "impact", "finish"] as SyncAnchor[]).map((anc) => (
              <button
                key={anc}
                type="button"
                onClick={() => {
                  setSyncAnchor(anc);
                  jumpSyncAnchor(anc);
                }}
                className={`px-2 py-0.5 rounded border text-[11px] font-semibold transition ${
                  syncAnchor === anc
                    ? "border-cyan-500 bg-cyan-950/80 text-cyan-300 font-bold"
                    : "border-gray-800 bg-black/40 text-gray-400 hover:border-gray-700"
                }`}
              >
                {anc.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-gray-400">同步演算法：</span>
            <div className="flex rounded-lg border border-gray-800 bg-black/60 p-0.5 text-[11px]">
              <button
                type="button"
                onClick={() => setSyncMode("real_time")}
                className={`px-2 py-0.5 rounded transition ${
                  syncMode === "real_time"
                    ? "bg-sky-600 text-white font-bold"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                自然節奏 (Mode A)
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!isPhaseSyncValid) {
                    alert(`無法切換至階段同步：${phaseValidation.reason || "示範影片缺少完整事件標記"}`);
                    return;
                  }
                  setSyncMode("phase_sync");
                }}
                className={`px-2 py-0.5 rounded transition ${
                  syncMode === "phase_sync"
                    ? "bg-purple-600 text-white font-bold"
                    : !isPhaseSyncValid
                    ? "text-gray-600 cursor-not-allowed"
                    : "text-gray-400 hover:text-white"
                }`}
                title={
                  !isPhaseSyncValid
                    ? `示範影片缺少事件標記，暫時無法啟用階段同步`
                    : "強制將雙方各動作階段進度對齊（非真實速度比較）"
                }
              >
                階段同步 (Mode B)
              </button>
            </div>
          </div>
        </div>

        {/* 疊影模式透明度滑桿 */}
        {layout === "ghost_overlay" && (
          <div className="flex items-center gap-3 pt-2 border-t border-gray-800/60 text-xs">
            <span className="text-gray-400">疊影透光度：</span>
            <input
              type="range"
              min="0.1"
              max="0.9"
              step="0.05"
              value={ghostOpacity}
              onChange={(e) => setGhostOpacity(parseFloat(e.target.value))}
              className="w-48 accent-cyan-400"
            />
            <span className="text-cyan-300 font-mono">{Math.round(ghostOpacity * 100)}%</span>
          </div>
        )}

        {/* 等比例畫面對齊與雙側 Zoom / Pan 控制 */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-800/60 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">畫面對齊狀態：</span>
            {autoFramingStatus?.status === "auto_computed" ? (
              <span className="rounded bg-emerald-950 px-2 py-0.5 text-[11px] font-bold text-emerald-300 border border-emerald-800/50">
                📐 2D Pose 自動對齊 ({autoFramingStatus.scale}x)
              </span>
            ) : autoFramingStatus?.status === "incompatible_angle" ? (
              <span className="rounded bg-rose-950 px-2 py-0.5 text-[11px] font-bold text-rose-300 border border-rose-800/50">
                ⚠️ 視角不相容
              </span>
            ) : (
              <span className="rounded bg-amber-950 px-2 py-0.5 text-[11px] font-bold text-amber-300 border border-amber-800/50">
                🖐️ 手動微調模式
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-[11px] flex-wrap">
            <span>示範縮放: {calibration.scale.toFixed(2)}x</span>
            <button
              type="button"
              onClick={() => adjustScale(-0.05)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              -
            </button>
            <button
              type="button"
              onClick={() => adjustScale(0.05)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              +
            </button>

            <span className="ml-2">個人縮放: {userZoom.toFixed(2)}x</span>
            <button
              type="button"
              onClick={() => setUserZoom((prev) => Math.max(0.6, parseFloat((prev - 0.05).toFixed(2))))}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              -
            </button>
            <button
              type="button"
              onClick={() => setUserZoom((prev) => Math.min(2.0, parseFloat((prev + 0.05).toFixed(2))))}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              +
            </button>

            <span className="ml-2">時間微偏:</span>
            <button
              type="button"
              onClick={() => setManualOffsetMs((prev) => prev - 50)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              -50ms
            </button>
            <button
              type="button"
              onClick={() => setManualOffsetMs(0)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600 text-gray-400"
            >
              歸零
            </button>
            <button
              type="button"
              onClick={() => setManualOffsetMs((prev) => prev + 50)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              +50ms
            </button>

            <span className="ml-2">位置:</span>
            <button
              type="button"
              onClick={() => adjustOffsetX(-8)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600 text-gray-300"
              title="示範影片向左移"
            >
              ←X
            </button>
            <button
              type="button"
              onClick={() => adjustOffsetX(8)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600 text-gray-300"
              title="示範影片向右移"
            >
              X→
            </button>
            <button
              type="button"
              onClick={() => adjustOffsetY(-8)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600 text-gray-300"
              title="示範影片向上移"
            >
              ↑Y
            </button>
            <button
              type="button"
              onClick={() => adjustOffsetY(8)}
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600 text-gray-300"
              title="示範影片向下移"
            >
              Y↓
            </button>

            <button
              type="button"
              onClick={resetAlignment}
              className="rounded bg-black px-1.5 py-0.5 border border-cyan-900/60 text-cyan-400 hover:border-cyan-600 text-[10px] ml-2"
              title="重設位置與縮放"
            >
              全部重設
            </button>
          </div>
        </div>
      </div>

      {/* P2: 離線量化姿勢比較表 (Quantitative Posture Comparison Table) */}
      <div className="rounded-xl border border-sky-800/60 bg-black/60 p-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
          <div className="flex items-center gap-2">
            <span className="text-cyan-400 text-base">📊</span>
            <h3 className="font-bold text-white text-sm">
              離線量化姿勢比較 (Quantitative Posture Comparison)
            </h3>
            <span className="text-[10px] bg-sky-950 text-sky-300 px-2 py-0.5 rounded border border-sky-800/50">
              Address / Top / Impact / Finish 四大階段
            </span>
          </div>
          <div className="text-[11px] text-gray-400 flex items-center gap-2">
            <span>可信度：</span>
            <strong className="text-emerald-400">
              {postureReport?.overall_reliability === "high" ? "高度可信 (High)" : "中度可信 (Medium)"}
            </strong>
          </div>
        </div>

        {/* Priority Fix (唯一改善重點卡片 - P3) */}
        {postureReport?.priority_fix && (
          <div className="rounded-xl border border-amber-600/70 bg-gradient-to-r from-amber-950/40 to-black/60 p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-amber-400 font-bold text-xs flex items-center gap-1.5">
                <span>🎯</span>
                <span>本球唯一改善重點 (Priority Fix)：{postureReport.priority_fix.metric_name}</span>
              </span>
              <span className="text-[10px] bg-amber-900/60 text-amber-200 px-2 py-0.5 rounded border border-amber-700/40">
                階段：{postureReport.priority_fix.phase.toUpperCase()} · 差異：{postureReport.priority_fix.diff_str}
              </span>
            </div>
            <p className="text-xs text-gray-200 leading-relaxed">
              {postureReport.priority_fix.advice}
            </p>
            <div className="p-2.5 rounded-lg bg-black/50 border border-amber-900/40 space-y-1">
              <div className="text-[11px] font-bold text-amber-300">
                推薦練習：{postureReport.priority_fix.drill_name}
              </div>
              <ul className="list-disc list-inside text-[11px] text-gray-300 space-y-0.5">
                {postureReport.priority_fix.drill_steps.map((step, idx) => (
                  <li key={idx}>{step}</li>
                ))}
              </ul>
              <div className="text-[10px] text-gray-400 pt-1">
                下次重測目標：<span className="text-emerald-400">{postureReport.priority_fix.retest_target}</span>
              </div>
            </div>
          </div>
        )}

        {/* 量化指標清單表格 */}
        {postureLoading ? (
          <div className="text-center py-6 text-gray-400 text-xs animate-pulse">
            正在計算離線 2D 骨架幾何量測數值...
          </div>
        ) : postureReport?.metrics && postureReport.metrics.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 text-gray-400 text-[11px]">
                  <th className="py-2 px-2 font-semibold">動作階段</th>
                  <th className="py-2 px-2 font-semibold">檢測項目</th>
                  <th className="py-2 px-2 font-semibold">我的數值</th>
                  <th className="py-2 px-2 font-semibold">示範數值</th>
                  <th className="py-2 px-2 font-semibold">幾何差異</th>
                  <th className="py-2 px-2 font-semibold">可信度</th>
                  <th className="py-2 px-2 font-semibold text-right">慢動作跳轉</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60 font-mono">
                {postureReport.metrics.map((m: any) => {
                  const phaseLabel = m.phase_label || m.phase_zh || m.phase;
                  const metricName = m.name || m.metric_name;
                  const diffVal = m.diff !== undefined ? m.diff : m.delta;
                  const unitStr = m.unit === "deg_2d" ? "°" : m.unit === "torso_pct" ? "%" : m.unit === "ratio" ? "" : m.unit === "score" ? "分" : m.unit || "";
                  const userValStr = m.user_value_display || (m.user_value !== null ? `${m.user_value} ${unitStr}` : "N/A");
                  const refValStr = m.ref_value_display || (m.ref_value !== null ? `${m.ref_value} ${unitStr}` : "N/A");
                  const diffStr = m.delta_display || (diffVal !== null ? `${diffVal > 0 ? "+" : ""}${diffVal} ${unitStr}` : "無法比對");
                  const targetMs = m.target_jump_ms || m.target_ms || userTimeline.startMs;
                  const descStr = m.description || m.evaluation_text || "";
                  const isHighReliability = m.reliability === "high" || (m.confidence !== undefined && m.confidence >= 0.85);

                  return (
                    <tr key={m.id} className="hover:bg-white/[0.02] transition">
                      <td className="py-2 px-2 font-sans text-gray-300 font-semibold">
                        {phaseLabel}
                      </td>
                      <td className="py-2 px-2 font-sans text-white">
                        <div>{metricName}</div>
                        <div className="text-[10px] text-gray-500 font-normal">{descStr}</div>
                      </td>
                      <td className="py-2 px-2 text-emerald-400 font-bold">
                        {userValStr}
                      </td>
                      <td className="py-2 px-2 text-cyan-400">
                        {refValStr}
                      </td>
                      <td className="py-2 px-2">
                        <span
                          className={`font-bold ${
                            diffVal === null
                              ? "text-gray-500"
                              : Math.abs(diffVal) < 2
                              ? "text-emerald-400"
                              : Math.abs(diffVal) < 5
                              ? "text-amber-400"
                              : "text-rose-400"
                          }`}
                        >
                          {diffStr}
                        </span>
                      </td>
                      <td className="py-2 px-2 font-sans">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            isHighReliability
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/40"
                              : "bg-amber-950/80 text-amber-300 border border-amber-800/40"
                          }`}
                        >
                          {isHighReliability ? "高" : "中"}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-right">
                        <button
                          type="button"
                          onClick={() => jumpAndSlowPlayMetric(targetMs, 0.5)}
                          className="rounded bg-sky-900/60 hover:bg-sky-800 border border-sky-700/60 px-2 py-1 text-[11px] font-semibold text-sky-200 transition"
                          title="跳轉至該動作階段並以 0.5x 慢放"
                        >
                          ▶ 慢放跳轉
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-4 text-gray-500 text-xs">
            {postureError || "暫無量化數據（可點擊上方球桿選擇或重新載入）"}
          </div>
        )}

        {/* 誠信原則免責聲明 */}
        <div className="rounded-lg bg-gray-950/70 border border-gray-800/80 p-2.5 text-[11px] text-gray-400 leading-relaxed">
          <span className="text-gray-300 font-bold">誠信說明：</span>
          {postureReport?.disclaimer ||
            "本分析嚴格基於 2D DTL 影像之可觀測人體骨架幾何，以雙肩雙髖軀幹長度正規化。本系統不推算球速、桿頭速度、飛行距離、甜蜜點或精確桿面角度。"}
        </div>
      </div>

      {/* 手動匯入 / 上傳示範影片 Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fadeIn">
          <div className="w-full max-w-md rounded-2xl border border-sky-800/80 bg-gradient-to-b from-[#0b1724] to-[#070e17] p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-800 pb-3">
              <h3 className="font-bold text-white text-sm">
                匯入 {selectedClub} 示範揮桿影片
              </h3>
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="text-gray-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* 匯入方式 Toggle */}
            <div className="flex rounded-lg border border-gray-800 bg-black/40 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setImportMode("file")}
                className={`flex-1 py-1 rounded text-center transition ${
                  importMode === "file" ? "bg-cyan-600 text-white font-bold" : "text-gray-400"
                }`}
              >
                選擇影片檔案直傳
              </button>
              <button
                type="button"
                onClick={() => setImportMode("path")}
                className={`flex-1 py-1 rounded text-center transition ${
                  importMode === "path" ? "bg-cyan-600 text-white font-bold" : "text-gray-400"
                }`}
              >
                本機安全目錄路徑
              </button>
            </div>

            {importError && (
              <div className="rounded-lg bg-red-950/80 border border-red-800 p-2.5 text-xs text-red-200">
                {importError}
              </div>
            )}

            <form onSubmit={handleImportSubmit} className="space-y-3 text-xs">
              {importMode === "file" ? (
                <div>
                  <label className="block text-gray-300 mb-1">
                    選擇影片檔案 (*.mp4 / *.mov，上限 500MB) <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime,video/x-m4v"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white file:mr-3 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-cyan-900 file:text-cyan-200 hover:file:bg-cyan-800"
                    required
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-gray-300 mb-1">
                    本機白名單路徑 (assets/ / storage_data/ 等) <span className="text-red-400">*</span>
                  </label>
                  <input
                    type="text"
                    placeholder="assets/reference_videos/my_swing.mp4"
                    value={importFilePath}
                    onChange={(e) => setImportFilePath(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white placeholder-gray-600"
                    required
                  />
                </div>
              )}

              <div>
                <label className="block text-gray-300 mb-1">
                  示範影片標題 <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder={`標準 ${selectedClub} DTL 示範揮桿`}
                  value={importTitle}
                  onChange={(e) => setImportTitle(e.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-300 mb-1">示範選手 / 教練</label>
                  <input
                    type="text"
                    value={importAuthor}
                    onChange={(e) => setImportAuthor(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-1">授權模式說明</label>
                  <input
                    type="text"
                    value={importLicense}
                    onChange={(e) => setImportLicense(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-gray-300 mb-1">原始出處或連結 (選填)</label>
                <input
                  type="text"
                  placeholder="https://..."
                  value={importSourceUrl}
                  onChange={(e) => setImportSourceUrl(e.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                />
              </div>

              <div className="p-2 rounded bg-amber-950/40 border border-amber-900/40 text-[11px] text-amber-200">
                ℹ️ 匯入後影片狀態將設為「待校準 (needs_calibration)」，未經人工校正前不會生成捏造的時間碼。
              </div>

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="rounded-lg border border-gray-700 px-4 py-2 text-gray-300 hover:border-gray-500"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={importing}
                  className="rounded-lg bg-emerald-600 px-5 py-2 font-bold text-white hover:bg-emerald-500 disabled:opacity-50"
                >
                  {importing ? "上傳並分析中..." : "確認匯入"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default SwingComparisonPlayer;
