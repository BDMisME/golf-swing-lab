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
}

export interface ClubCatalogItem {
  club_type: string;
  status: "available" | "missing_reference";
  reference_count: number;
  default_reference?: ReferenceSwingData | null;
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

  // 2. 佈局與播放控制狀態
  const [layout, setLayout] = useState<ComparisonLayout>("side_by_side");
  const [syncMode, setSyncMode] = useState<SyncMode>("real_time");
  const [syncAnchor, setSyncAnchor] = useState<SyncAnchor>("impact");
  const [manualOffsetMs, setManualOffsetMs] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [isLooping, setIsLooping] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [ghostOpacity, setGhostOpacity] = useState<number>(0.5);
  const [showIndividualControls, setShowIndividualControls] = useState<boolean>(false);

  // 3. 畫面對齊 (Auto-Framing & Manual Calibration)
  const [calibration, setCalibration] = useState<FramingCalibration>({
    scale: 1.0,
    zoom: 1.0,
    offsetX: 0,
    offsetY: 0,
  });
  const [autoFramingStatus, setAutoFramingStatus] = useState<AutoFramingResult | null>(null);

  // 4. 當前播放時間 (ms)
  const [userCurrentMs, setUserCurrentMs] = useState<number>(userSwing.start_ms);
  const [refCurrentMs, setRefCurrentMs] = useState<number>(0);

  // 5. 影片 Element 參照
  const userVideoRef = useRef<HTMLVideoElement | null>(null);
  const refVideoRef = useRef<HTMLVideoElement | null>(null);

  // 6. 手動匯入 / 上傳 Modal 狀態
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

  // 7. 載入 17 種球桿目錄與當前球桿示範影片
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

  // 檢核 Phase Sync 是否合法（若示範片無事件標籤，強制降級為 real_time）
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
    setUserCurrentMs(userTimeline.startMs);
  }, [userTimeline.startMs, userTimeline.endMs]);

  const handleRefLoadedMetadata = useCallback(() => {
    const rVid = refVideoRef.current;
    if (!rVid || !refSwing) return;
    const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
    const targetSec = targetRefMs / 1000;
    if (Math.abs(rVid.currentTime - targetSec) > 0.1) {
      rVid.currentTime = targetSec;
    }
    setRefCurrentMs(targetRefMs);
  }, [refSwing, userTimeline.startMs, computeExpectedRefMs]);

  // 當 userSwing.id 或 selectedClub 改變時，主動確保定位在 startMs
  const prevSwingKeyRef = useRef<string>(`${userSwing.id}_${selectedClub}`);
  useEffect(() => {
    const currentKey = `${userSwing.id}_${selectedClub}`;
    if (prevSwingKeyRef.current !== currentKey) {
      prevSwingKeyRef.current = currentKey;
      const uVid = userVideoRef.current;
      if (uVid && uVid.readyState >= 1) {
        uVid.currentTime = userTimeline.startMs / 1000;
        setUserCurrentMs(userTimeline.startMs);
      }
      const rVid = refVideoRef.current;
      if (rVid && rVid.readyState >= 1 && refSwing) {
        const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
        rVid.currentTime = targetRefMs / 1000;
        setRefCurrentMs(targetRefMs);
      }
    }
  }, [userSwing.id, selectedClub, refSwing, userTimeline.startMs, computeExpectedRefMs]);

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

  // 同步逐格步進
  const stepSyncFrame = (deltaFrames: number) => {
    handlePause();
    const uVid = userVideoRef.current;
    const rVid = refVideoRef.current;
    if (!uVid) return;

    const frameMs = 33.333;
    const curSec = uVid.currentTime;
    const nextSec = Math.max(
      userTimeline.startMs / 1000,
      Math.min(userTimeline.endMs / 1000, curSec + (deltaFrames * frameMs) / 1000)
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
    const frameMs = 33.333;
    const curSec = uVid.currentTime;
    const nextSec = Math.max(
      userTimeline.startMs / 1000,
      Math.min(userTimeline.endMs / 1000, curSec + (deltaFrames * frameMs) / 1000)
    );
    uVid.currentTime = nextSec;
    setUserCurrentMs(Math.round(nextSec * 1000));
  };

  const replayUser = () => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.currentTime = userTimeline.startMs / 1000;
    setUserCurrentMs(userTimeline.startMs);
    uVid.play().catch(() => {});
  };

  // 單獨控制示範影片 (Individual Reference Video Controls)
  const toggleRefPlay = () => {
    const rVid = refVideoRef.current;
    if (!rVid) return;
    if (rVid.paused) {
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
    const frameMs = 33.333;
    const curSec = rVid.currentTime;
    const durSec = (refSwing?.duration_ms || 3000) / 1000;
    const nextSec = Math.max(0, Math.min(durSec, curSec + (deltaFrames * frameMs) / 1000));
    rVid.currentTime = nextSec;
    setRefCurrentMs(Math.round(nextSec * 1000));
  };

  const replayRef = () => {
    const rVid = refVideoRef.current;
    if (!rVid) return;
    rVid.currentTime = 0;
    setRefCurrentMs(0);
    rVid.play().catch(() => {});
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
    setManualOffsetMs(0);
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
          if (rVid && refSwing) {
            const targetRefMs = computeExpectedRefMs(userTimeline.startMs);
            rVid.currentTime = targetRefMs / 1000;
          }
          uVid.play().catch(() => {});
          rVid?.play().catch(() => {});
        } else {
          uVid.pause();
          rVid?.pause();
          setIsPlaying(false);
          return;
        }
      }

      // 若有參考影片，進行平滑漂移校正（拒絕無條件 seek，以調速平滑修正）
      if (rVid && refSwing && !rVid.paused) {
        const expectedRefSec = computeExpectedRefMs(uMs) / 1000;
        setRefCurrentMs(Math.round(rVid.currentTime * 1000));

        const driftRes = PlaybackDriftController.evaluateDrift(
          rVid.currentTime,
          expectedRefSec,
          uVid.playbackRate
        );

        if (driftRes.action === "adjust_rate") {
          rVid.playbackRate = driftRes.recommendedPlaybackRate;
        } else if (driftRes.action === "hard_seek") {
          rVid.currentTime = driftRes.targetRefTimeSec;
          rVid.playbackRate = uVid.playbackRate;
        } else {
          if (Math.abs(rVid.playbackRate - uVid.playbackRate) > 0.01) {
            rVid.playbackRate = uVid.playbackRate;
          }
        }
      }

      animId = requestAnimationFrame(syncTick);
    };

    animId = requestAnimationFrame(syncTick);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, isLooping, userTimeline, refSwing, computeExpectedRefMs]);

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

  return (
    <div className="rounded-2xl border border-sky-800/80 bg-gradient-to-b from-[#0a141f] to-[#070d14] p-4 text-white shadow-xl space-y-4">
      {/* 頂部標題與關閉列 (P0-3 誠信標題) */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="flex h-3 w-3 rounded-full bg-cyan-400 animate-pulse" />
          <h2 className="text-base font-bold text-white tracking-wide">
            {refSwing?.is_verified_standard
              ? "已驗證職業示範對照"
              : "揮桿雙影片對照 (Dual Swing Comparison)"}
          </h2>
          <span className="rounded bg-sky-950 px-2 py-0.5 text-xs text-sky-300 font-mono border border-sky-800/50">
            Mode: {syncMode === "real_time" ? "自然時間同步" : "階段線性同步"}
          </span>
        </div>

        <div className="flex items-center gap-2">
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

      {/* 示範影片資訊列與真偽標記 */}
      {refSwing ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-black/40 border border-gray-800/80 px-3 py-2 text-xs">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-cyan-300">示範素材：{refSwing.title}</span>
            <span className="text-gray-400">作者：{refSwing.reference_author}</span>

            {/* 素材分類標籤 (恪守最高誠信原則) */}
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
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-gray-900/60 border border-dashed border-gray-700 p-3 text-xs text-gray-400">
          <div className="flex items-center gap-2">
            <span>
              ℹ️ 目前球桿 ({selectedClub}) 尚未收錄標準示範影片 (missing_reference)
              {selectedClub === "Hybrid" && " — 系統支援 3H/4H/5H，通用 Hybrid 暫無明確號數示範，請選擇具體號數或手動匯入。"}
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

      {/* 影片播放區域 (單一 DOM 樹架構，切換 layout 永不銷毀重建物件，防止黑屏) */}
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
                {refSwing?.shot_type && refSwing.shot_type !== "full_swing" && (
                  <span className="rounded bg-purple-950/80 px-2 py-0.5 text-[10px] font-semibold text-purple-300 border border-purple-800/40">
                    ⚠️ 非全揮桿 ({refSwing.shot_type === "pitch_90yd" ? "90碼 Pitch" : refSwing.shot_type === "flop_shot" ? "高拋 Flop" : refSwing.shot_type === "putt" ? "推桿特寫" : refSwing.shot_type === "bunker_shot" ? "沙坑示範" : refSwing.shot_type})
                  </span>
                )}
                {refSwing?.camera_angle && refSwing.camera_angle !== "DTL" && (
                  <span className="rounded bg-blue-950/80 px-2 py-0.5 text-[10px] font-semibold text-blue-300 border border-blue-800/40">
                    📷 非標準 DTL ({refSwing.camera_angle})
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
            />
          </div>
        </div>
      </div>

      {/* 播放控制與時間軸 */}
      <div className="space-y-3 bg-black/50 p-3 rounded-xl border border-gray-800/80">
        {/* 進度顯示列 */}
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
            {/* 階段線性同步警告或資訊 */}
            {syncMode === "phase_sync" && (
              <span className="text-[11px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40 font-sans">
                ⚡ 時間正規化比較中（各動作階段強制同步，非真實揮桿速度）
              </span>
            )}
            <span className="text-gray-400 text-[11px]">
              偏移: {manualOffsetMs > 0 ? `+${manualOffsetMs}` : manualOffsetMs}ms
            </span>
          </div>
        </div>

        {/* 控制按鈕群 */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-gray-800">
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={toggleSyncPlay}
              className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 font-bold text-white hover:bg-emerald-500 transition shadow-sm text-xs"
              title={isPlaying ? "暫停同步播放" : "啟動雙影片同步播放"}
            >
              <span>{isPlaying ? "❚❚ 暫停" : "▶ 同步播放"}</span>
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

        {/* 雙影片個別獨立控制開關與面板 */}
        <div className="flex items-center justify-between pt-1 border-t border-gray-800/40 text-xs">
          <button
            type="button"
            onClick={() => setShowIndividualControls(!showIndividualControls)}
            className="flex items-center gap-1 text-[11px] font-semibold text-gray-400 hover:text-cyan-300 transition"
          >
            <span>{showIndividualControls ? "▾ 收起各影片獨立控制" : "▸ 展開各影片獨立控制 (個別播放/逐格/重播)"}</span>
          </button>
        </div>

        {showIndividualControls && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 p-2 bg-black/40 rounded-lg border border-gray-800/60 text-xs">
            {/* 示範影片獨立控制 */}
            <div className="flex items-center justify-between p-1.5 rounded bg-cyan-950/20 border border-cyan-900/30">
              <span className="text-cyan-300 font-semibold text-[11px]">示範影片 ({selectedClub})</span>
              <div className="flex items-center gap-1 text-[11px]">
                <button
                  type="button"
                  onClick={toggleRefPlay}
                  className="rounded bg-cyan-900/50 px-2 py-0.5 text-cyan-200 hover:bg-cyan-800"
                >
                  ▶/⏸
                </button>
                <button
                  type="button"
                  onClick={() => stepRefFrame(-1)}
                  className="rounded bg-black/60 px-1.5 py-0.5 border border-gray-800 text-gray-300 hover:border-cyan-500"
                >
                  -1f
                </button>
                <button
                  type="button"
                  onClick={() => stepRefFrame(1)}
                  className="rounded bg-black/60 px-1.5 py-0.5 border border-gray-800 text-gray-300 hover:border-cyan-500"
                >
                  +1f
                </button>
                <button
                  type="button"
                  onClick={replayRef}
                  className="rounded bg-cyan-950 px-1.5 py-0.5 border border-cyan-800 text-cyan-300"
                >
                  ↺ 重播
                </button>
              </div>
            </div>

            {/* 個人影片獨立控制 */}
            <div className="flex items-center justify-between p-1.5 rounded bg-emerald-950/20 border border-emerald-900/30">
              <span className="text-emerald-300 font-semibold text-[11px]">個人揮桿 (#{userSwing.sequence_no})</span>
              <div className="flex items-center gap-1 text-[11px]">
                <button
                  type="button"
                  onClick={toggleUserPlay}
                  className="rounded bg-emerald-900/50 px-2 py-0.5 text-emerald-200 hover:bg-emerald-800"
                >
                  ▶/⏸
                </button>
                <button
                  type="button"
                  onClick={() => stepUserFrame(-1)}
                  className="rounded bg-black/60 px-1.5 py-0.5 border border-gray-800 text-gray-300 hover:border-emerald-500"
                >
                  -1f
                </button>
                <button
                  type="button"
                  onClick={() => stepUserFrame(1)}
                  className="rounded bg-black/60 px-1.5 py-0.5 border border-gray-800 text-gray-300 hover:border-emerald-500"
                >
                  +1f
                </button>
                <button
                  type="button"
                  onClick={replayUser}
                  className="rounded bg-emerald-950 px-1.5 py-0.5 border border-emerald-800 text-emerald-300"
                >
                  ↺ 重播
                </button>
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
            <span className="text-gray-400">同步模式：</span>
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

        {/* 等比例畫面對齊 (Auto-Framing) 與手動微調控制項 */}
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

          <div className="flex items-center gap-2 text-[11px]">
            <span>縮放: {calibration.scale.toFixed(2)}x</span>
            <button
              type="button"
              onClick={() =>
                setCalibration((prev) => ({ ...prev, scale: Math.max(0.6, prev.scale - 0.05) }))
              }
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              -
            </button>
            <button
              type="button"
              onClick={() =>
                setCalibration((prev) => ({ ...prev, scale: Math.min(1.8, prev.scale + 0.05) }))
              }
              className="rounded bg-black px-1.5 py-0.5 border border-gray-800 hover:border-gray-600"
            >
              +
            </button>

            <span className="ml-2">手動時間偏移:</span>
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
              className="rounded bg-black px-1.5 py-0.5 border border-cyan-900/60 text-cyan-400 hover:border-cyan-600 text-[10px]"
              title="重設位置與縮放"
            >
              重設
            </button>
          </div>

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
