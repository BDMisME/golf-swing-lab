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
  ComparisonLayout,
  FramingCalibration,
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
  fps: number;
  duration_ms: number;
  sha256: string;
  event_timestamps: Record<string, number>;
  pose_artifact: Record<string, any>;
  calibration_params: FramingCalibration & { torso_length?: number };
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
  "Driver", "3W", "5W",
  "3H", "4H", "5H",
  "4I", "5I", "6I", "7I", "8I", "9I",
  "PW", "GW/AW", "SW", "LW",
  "Putter",
];

export function SwingComparisonPlayer({
  userSwing,
  defaultClub = "7I",
  onClose,
}: SwingComparisonPlayerProps) {
  // 影片 refs
  const userVideoRef = useRef<HTMLVideoElement | null>(null);
  const refVideoRef = useRef<HTMLVideoElement | null>(null);

  // 狀態
  const [selectedClub, setSelectedClub] = useState<string>(defaultClub);
  const [catalog, setCatalog] = useState<ClubCatalogItem[]>([]);
  const [refSwing, setRefSwing] = useState<ReferenceSwingData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [syncMode, setSyncMode] = useState<SyncMode>("real_time");
  const [syncAnchor, setSyncAnchor] = useState<SyncAnchor>("impact");
  const [layout, setLayout] = useState<ComparisonLayout>("side_by_side");
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [manualOffsetMs, setManualOffsetMs] = useState<number>(0);
  const [ghostOpacity, setGhostOpacity] = useState<number>(0.5);

  // 時間追蹤
  const [userCurrentMs, setUserCurrentMs] = useState<number>(userSwing.start_ms);
  const [refCurrentMs, setRefCurrentMs] = useState<number>(0);

  // 畫面校正
  const [refZoom, setRefZoom] = useState<number>(1.0);
  const [refOffsetX, setRefOffsetX] = useState<number>(0);
  const [refOffsetY, setRefOffsetY] = useState<number>(0);

  // 手動匯入 Modal
  const [showImportModal, setShowImportModal] = useState<boolean>(false);
  const [importFilePath, setImportFilePath] = useState<string>("");
  const [importTitle, setImportTitle] = useState<string>("");
  const [importAuthor, setImportAuthor] = useState<string>("Professional Standard");
  const [importSourceUrl, setImportSourceUrl] = useState<string>("");
  const [importLicense, setImportLicense] = useState<string>("Educational Reference");
  const [importNotes, setImportNotes] = useState<string>("");
  const [importing, setImporting] = useState<boolean>(false);
  const [importError, setImportError] = useState<string | null>(null);

  // 1. 載入示範揮桿目錄與指定球桿影片
  const loadCatalogAndReference = useCallback(async (club: string) => {
    setLoading(true);
    try {
      const catRes = await apiFetch<{
        clubs: ClubCatalogItem[];
        references: ReferenceSwingData[];
      }>("/api/reference-swings");
      setCatalog(catRes.clubs);

      // 取得該球桿示範影片
      const clubInfo = catRes.clubs.find((c) => c.club_type === club);
      if (clubInfo && clubInfo.default_reference) {
        const cal = clubInfo.default_reference.calibration_params;
        setRefSwing(clubInfo.default_reference);
        setRefZoom(cal?.zoom ?? 1.0);
        setRefOffsetX(cal?.offsetX ?? cal?.offset_x ?? 0);
        setRefOffsetY(cal?.offsetY ?? cal?.offset_y ?? 0);
      } else {
        setRefSwing(null);
      }
    } catch (err) {
      console.error("載入示範揮桿資料庫失敗:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCatalogAndReference(selectedClub);
  }, [selectedClub, loadCatalogAndReference]);

  // 2. 構建時間軸 Timelines
  const userTimeline = useMemo<SwingTimingTimeline>(() => {
    const evMap: Record<string, number> = {};
    for (const ev of userSwing.events || []) {
      evMap[ev.event_name] = ev.time_ms;
    }
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
      addressMs: ts["address"] || Math.round(dur * 0.15),
      takeawayMs: ts["takeaway"] || Math.round(dur * 0.28),
      topMs: ts["top"] || Math.round(dur * 0.5),
      downswingMs: ts["downswing"] || Math.round(dur * 0.58),
      impactMs: ts["impact"] || Math.round(dur * 0.65),
      followThroughMs: ts["follow_through"] || Math.round(dur * 0.75),
      finishMs: ts["finish"] || Math.round(dur * 0.9),
    };
  }, [refSwing]);

  // 3. 視角相容性檢核
  const angleCheck = useMemo(() => {
    if (!refSwing) return { compatible: true };
    return SwingSynchronizationEngine.checkAngleCompatibility(
      "DTL",
      refSwing.camera_angle
    );
  }, [refSwing]);

  // 4. 同步時間映射核心邏輯
  const syncRefToUser = useCallback(
    (uMs: number) => {
      if (!refVideoRef.current || !refSwing) return;
      let targetRefMs: number;
      if (syncMode === "real_time") {
        targetRefMs = SwingSynchronizationEngine.computeRealTimeRefMs(
          uMs,
          userTimeline,
          refTimeline,
          syncAnchor,
          manualOffsetMs
        );
      } else {
        targetRefMs = SwingSynchronizationEngine.computePhaseSyncRefMs(
          uMs,
          userTimeline,
          refTimeline,
          manualOffsetMs
        );
      }
      refVideoRef.current.currentTime = targetRefMs / 1000;
      setRefCurrentMs(Math.round(targetRefMs));
    },
    [refSwing, syncMode, syncAnchor, userTimeline, refTimeline, manualOffsetMs]
  );

  // 監聽使用者影片播放進行同步驅動
  useEffect(() => {
    const uVid = userVideoRef.current;
    if (!uVid) return;

    const onTimeUpdate = () => {
      const cur = uVid.currentTime;
      const ms = Math.round(cur * 1000);
      setUserCurrentMs(ms);
      syncRefToUser(ms);

      // 單球播放循環或結束判定
      if (cur >= userTimeline.endMs / 1000) {
        uVid.pause();
        uVid.currentTime = userTimeline.startMs / 1000;
        setIsPlaying(false);
      }
    };

    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);

    uVid.addEventListener("timeupdate", onTimeUpdate);
    uVid.addEventListener("play", onPlay);
    uVid.addEventListener("pause", onPause);

    return () => {
      uVid.removeEventListener("timeupdate", onTimeUpdate);
      uVid.removeEventListener("play", onPlay);
      uVid.removeEventListener("pause", onPause);
    };
  }, [syncRefToUser, userTimeline]);

  // 控制：同步播放/暫停
  const toggleSyncPlay = () => {
    const uVid = userVideoRef.current;
    if (!uVid) return;

    if (uVid.paused || uVid.ended) {
      if (uVid.currentTime >= userTimeline.endMs / 1000 - 0.05) {
        uVid.currentTime = userTimeline.startMs / 1000;
      }
      uVid.playbackRate = playbackSpeed;
      uVid.play().catch(() => {});
    } else {
      uVid.pause();
    }
  };

  // 控制：同步重播
  const handleSyncReplay = () => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.pause();
    uVid.currentTime = userTimeline.startMs / 1000;
    syncRefToUser(userTimeline.startMs);
    uVid.playbackRate = playbackSpeed;
    uVid.play().catch(() => {});
  };

  // 控制：同步跳轉至指定關鍵錨點
  const jumpSyncAnchor = (anchor: SyncAnchor) => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.pause();
    const targetUserMs = SwingSynchronizationEngine.getAnchorTimeMs(userTimeline, anchor);
    uVid.currentTime = targetUserMs / 1000;
    setUserCurrentMs(targetUserMs);
    syncRefToUser(targetUserMs);
  };

  // 控制：同步逐格步進
  const stepSyncFrame = (deltaFrames: number) => {
    const uVid = userVideoRef.current;
    if (!uVid) return;
    uVid.pause();
    const frameMs = 33.333;
    const curSec = uVid.currentTime;
    const nextSec = Math.max(
      userTimeline.startMs / 1000,
      Math.min(userTimeline.endMs / 1000, curSec + (deltaFrames * frameMs) / 1000)
    );
    uVid.currentTime = nextSec;
    const ms = Math.round(nextSec * 1000);
    setUserCurrentMs(ms);
    syncRefToUser(ms);
  };

  // 控制：示範影片單獨前後一幀
  const stepRefFrame = (deltaFrames: number) => {
    const rVid = refVideoRef.current;
    if (!rVid || !refSwing) return;
    rVid.pause();
    const frameMs = 1000 / (refSwing.fps || 30);
    const nextSec = Math.max(0, Math.min(refSwing.duration_ms / 1000, rVid.currentTime + (deltaFrames * frameMs) / 1000));
    rVid.currentTime = nextSec;
    setRefCurrentMs(Math.round(nextSec * 1000));
  };

  // 變更播放速度
  const handleSpeedChange = (speed: number) => {
    setPlaybackSpeed(speed);
    if (userVideoRef.current) userVideoRef.current.playbackRate = speed;
  };

  // 自動畫面對齊 (Auto-Framing)
  const handleAutoFraming = () => {
    if (!refSwing) return;
    const res = SwingSynchronizationEngine.computeAutoFraming(115, refSwing.calibration_params?.torso_length || 115);
    setRefZoom(res.scale);
    setRefOffsetX(0);
    setRefOffsetY(0);
  };

  // 匯入新示範影片
  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!importFilePath || !importTitle) {
      setImportError("請輸入檔案路徑與標題");
      return;
    }
    setImporting(true);
    setImportError(null);
    try {
      await apiFetch("/api/reference-swings/import-local", {
        method: "POST",
        body: JSON.stringify({
          file_path: importFilePath,
          club_type: selectedClub,
          handedness: "right",
          camera_angle: "DTL",
          shot_type: "full_swing",
          title: importTitle,
          reference_author: importAuthor,
          source_url: importSourceUrl,
          content_license: importLicense,
          verified_club: true,
          verified_camera_angle: true,
          is_default: true,
          notes: importNotes,
        }),
      });
      setShowImportModal(false);
      setImportFilePath("");
      setImportTitle("");
      await loadCatalogAndReference(selectedClub);
    } catch (err: any) {
      setImportError(err.message || "匯入失敗");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-cyan-800/80 bg-[#0a1219] p-5 shadow-2xl space-y-4">
      {/* 頂部標頭與佈局切換 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-3 w-3 rounded-full bg-cyan-400 animate-pulse" />
            <h2 className="text-lg font-bold text-white">
              與示範揮桿比較 (Professional Swing Comparison)
            </h2>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            左側：我的揮桿（第 #{userSwing.sequence_no} 球） · 右側：{selectedClub} 示範標準
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* 佈局切換 */}
          <div className="flex rounded-lg border border-gray-800 bg-black/60 p-0.5 text-xs">
            {[
              { id: "side_by_side", label: "左右並列" },
              { id: "stacked", label: "上下堆疊" },
              { id: "ghost_overlay", label: "半透明疊影" },
            ].map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setLayout(m.id as ComparisonLayout)}
                className={`rounded-md px-2.5 py-1 font-semibold transition ${
                  layout === m.id
                    ? "bg-cyan-500 text-black shadow-sm"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-700 bg-black/40 px-3 py-1 text-xs text-gray-300 hover:border-gray-500"
            >
              ✕ 收合比較
            </button>
          )}
        </div>
      </div>

      {/* 球桿選擇器列 (完整 17 種球桿分類) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span className="font-semibold text-gray-300">選擇示範球桿 (17 種分類支援)：</span>
          {refSwing ? (
            <span className="text-[11px] text-emerald-400">
              ● 已載入示範：{refSwing.reference_author} ({refSwing.content_license})
            </span>
          ) : (
            <span className="text-[11px] text-amber-400">
              ⚠ 目前尚無該球桿示範 (missing_reference)
            </span>
          )}
        </div>
        <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin">
          {ALL_CLUBS.map((club) => {
            const item = catalog.find((c) => c.club_type === club);
            const isAvail = item && item.status === "available";
            const isSel = selectedClub === club;
            return (
              <button
                key={club}
                type="button"
                onClick={() => setSelectedClub(club)}
                className={`flex items-center gap-1 shrink-0 rounded-lg px-2.5 py-1 text-xs font-semibold transition border ${
                  isSel
                    ? "border-cyan-400 bg-cyan-950/80 text-cyan-200 ring-1 ring-cyan-400"
                    : isAvail
                    ? "border-emerald-800/60 bg-emerald-950/30 text-emerald-300 hover:border-emerald-500"
                    : "border-gray-800 bg-black/40 text-gray-500 hover:border-gray-700"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${isAvail ? "bg-emerald-400" : "bg-gray-600"}`} />
                <span>{club}</span>
                {item && item.reference_count > 0 && (
                  <span className="text-[9px] text-emerald-400/80">({item.reference_count})</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 視角不匹配警告 */}
      {!angleCheck.compatible && angleCheck.warning && (
        <div className="rounded-xl border border-amber-500/50 bg-amber-950/40 p-3 text-xs text-amber-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span>⚠</span>
            <span>{angleCheck.warning}</span>
          </div>
          <span className="text-[10px] text-amber-300 bg-amber-900/60 px-2 py-0.5 rounded">
            誠信原則：禁止 2D 角度混淆
          </span>
        </div>
      )}

      {/* 同步模式與錨點選擇 */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-800 bg-black/40 p-3 text-xs">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <span className="text-gray-400">同步演算法:</span>
            <button
              type="button"
              onClick={() => setSyncMode("real_time")}
              className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                syncMode === "real_time"
                  ? "bg-cyan-500 text-black shadow-sm"
                  : "border border-gray-700 text-gray-400 hover:text-white"
              }`}
              title="保留兩人原始揮桿節奏，依指定錨點時間同步"
            >
              A. 真實時間 (自然節奏)
            </button>
            <button
              type="button"
              onClick={() => setSyncMode("phase_sync")}
              className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                syncMode === "phase_sync"
                  ? "bg-emerald-500 text-black shadow-sm"
                  : "border border-gray-700 text-gray-400 hover:text-white"
              }`}
              title="將各階段進度正規化線性對齊，使對應動作同時呈現 (非真實節奏)"
            >
              B. 動作階段同步 (分段對應)
            </button>
          </div>

          {syncMode === "real_time" && (
            <div className="flex items-center gap-1 pl-2 border-l border-gray-800">
              <span className="text-gray-400 text-[11px]">對齊錨點:</span>
              {[
                { id: "impact", label: "Impact" },
                { id: "top", label: "Top" },
                { id: "address", label: "Address" },
                { id: "finish", label: "Finish" },
              ].map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setSyncAnchor(a.id as SyncAnchor)}
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold transition ${
                    syncAnchor === a.id
                      ? "bg-cyan-900/80 text-cyan-200 border border-cyan-400"
                      : "text-gray-400 hover:text-gray-200"
                  }`}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 手動微調時間偏移 */}
        <div className="flex items-center gap-1.5 text-[11px]">
          <span className="text-gray-400">手動時間偏移:</span>
          <button
            type="button"
            onClick={() => setManualOffsetMs((prev) => prev - 100)}
            className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
          >
            -100ms
          </button>
          <button
            type="button"
            onClick={() => setManualOffsetMs((prev) => prev - 33)}
            className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
          >
            -33ms
          </button>
          <span className="font-mono text-cyan-300 w-12 text-center">
            {manualOffsetMs >= 0 ? `+${manualOffsetMs}` : manualOffsetMs}ms
          </span>
          <button
            type="button"
            onClick={() => setManualOffsetMs((prev) => prev + 33)}
            className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
          >
            +33ms
          </button>
          <button
            type="button"
            onClick={() => setManualOffsetMs((prev) => prev + 100)}
            className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
          >
            +100ms
          </button>
          {manualOffsetMs !== 0 && (
            <button
              type="button"
              onClick={() => setManualOffsetMs(0)}
              className="text-gray-500 hover:text-gray-300 text-[10px] underline ml-1"
            >
              歸零
            </button>
          )}
        </div>
      </div>

      {/* 雙影片主播放區 */}
      {refSwing ? (
        <div
          className={`grid gap-4 ${
            layout === "stacked"
              ? "grid-cols-1"
              : layout === "ghost_overlay"
              ? "grid-cols-1"
              : "grid-cols-1 lg:grid-cols-2"
          }`}
        >
          {/* 左側/上方：我的影片 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-bold text-cyan-300">
                👤 我的揮桿 (第 #{userSwing.sequence_no} 球)
              </span>
              <span className="font-mono text-gray-400">
                {formatMsToTimestamp(userCurrentMs)}
              </span>
            </div>
            <div className="relative overflow-hidden rounded-xl border border-gray-800 bg-black aspect-video">
              <video
                ref={userVideoRef}
                playsInline
                muted
                preload="auto"
                crossOrigin="anonymous"
                src={`${API_BASE_URL}/api/videos/${userSwing.video_id}/stream?token=${encodeURIComponent(
                  getAuthToken() || ""
                )}#t=${(userSwing.start_ms / 1000).toFixed(2)},${(userSwing.end_ms / 1000).toFixed(2)}`}
                className="w-full h-full object-contain"
              />
            </div>
          </div>

          {/* 右側/下方：示範影片 */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-emerald-300">
                  🏌️‍♂️ {refSwing.title}
                </span>
                <span className="rounded bg-emerald-950/80 border border-emerald-800 px-1.5 py-0.2 text-[10px] text-emerald-400">
                  {refSwing.camera_angle}
                </span>
              </div>
              <span className="font-mono text-gray-400">
                {formatMsToTimestamp(refCurrentMs)}
              </span>
            </div>
            <div className="relative overflow-hidden rounded-xl border border-gray-800 bg-black aspect-video">
              <video
                ref={refVideoRef}
                playsInline
                muted
                preload="auto"
                crossOrigin="anonymous"
                src={`${API_BASE_URL}${refSwing.stream_url}?token=${encodeURIComponent(
                  getAuthToken() || ""
                )}`}
                style={{
                  transform: `scale(${refZoom}) translate(${refOffsetX}px, ${refOffsetY}px)`,
                  transition: "transform 100ms ease-out",
                }}
                className="w-full h-full object-contain"
              />
            </div>
          </div>
        </div>
      ) : (
        /* 當前球桿暫無示範影片 (missing_reference) 狀態提示卡片 */
        <div className="rounded-xl border border-dashed border-gray-800 bg-black/30 p-8 text-center space-y-3">
          <div className="text-3xl">🏌️</div>
          <h3 className="text-base font-bold text-white">
            {selectedClub} 目前尚無已確認的示範揮桿影片 (missing_reference)
          </h3>
          <p className="text-xs text-gray-400 max-w-md mx-auto leading-relaxed">
            系統依最高誠信原則，絕不拿其他鐵桿或休閒揮桿冒充該球桿之職業標準。您可以自行匯入有權使用的本機 DTL 影片，或參考外部合法教學來源。
          </p>
          <div className="pt-2 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => setShowImportModal(true)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500 transition shadow"
            >
              ＋ 匯入此球桿的示範影片
            </button>
            <button
              type="button"
              onClick={() => setSelectedClub("7I")}
              className="rounded-lg border border-gray-700 bg-black/50 px-4 py-2 text-xs font-semibold text-gray-300 hover:border-gray-500"
            >
              切換至已有示範的 7I 鐵桿
            </button>
          </div>
        </div>
      )}

      {/* 雙影片同步播放控制器 */}
      {refSwing && (
        <div className="space-y-3 pt-2">
          {/* 同步控制列 */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={toggleSyncPlay}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-4 py-1.5 font-bold text-white hover:bg-emerald-500 transition shadow-sm"
              >
                <span>{isPlaying ? "❚❚ 同步暫停" : "▶ 同步播放"}</span>
              </button>
              <button
                type="button"
                onClick={handleSyncReplay}
                className="flex items-center gap-1 rounded-lg border border-cyan-700/60 bg-cyan-950/40 px-3 py-1.5 font-semibold text-cyan-300 hover:bg-cyan-900/60 transition"
              >
                <span>↺ 同步重播</span>
              </button>

              {/* 一鍵跳轉關鍵同步點 */}
              <div className="flex items-center gap-1 pl-2 border-l border-gray-800">
                <span className="text-gray-400 text-[11px]">一鍵同步:</span>
                {[
                  { id: "address", label: "Address" },
                  { id: "top", label: "Top" },
                  { id: "impact", label: "Impact" },
                  { id: "finish", label: "Finish" },
                ].map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => jumpSyncAnchor(a.id as SyncAnchor)}
                    className="rounded border border-gray-700 bg-black/60 px-2 py-1 text-[11px] font-semibold text-gray-200 hover:border-cyan-400 hover:text-cyan-300 transition"
                  >
                    {a.label}
                  </button>
                ))}
              </div>
            </div>

            {/* 同步逐幀步進與速度 */}
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <span className="text-gray-400 text-[11px]">同步逐幀:</span>
                <button
                  type="button"
                  onClick={() => stepSyncFrame(-1)}
                  className="rounded border border-gray-700 bg-black/60 px-2 py-1 text-gray-200 hover:border-cyan-400"
                >
                  &larr; -1f
                </button>
                <button
                  type="button"
                  onClick={() => stepSyncFrame(1)}
                  className="rounded border border-gray-700 bg-black/60 px-2 py-1 text-gray-200 hover:border-cyan-400"
                >
                  +1f &rarr;
                </button>
              </div>

              <div className="flex items-center gap-1">
                {[
                  { label: "1.0x", val: 1.0 },
                  { label: "0.5x", val: 0.5 },
                  { label: "0.25x", val: 0.25 },
                ].map((sp) => (
                  <button
                    key={sp.val}
                    type="button"
                    onClick={() => handleSpeedChange(sp.val)}
                    className={`rounded px-2 py-0.5 font-semibold transition ${
                      playbackSpeed === sp.val
                        ? "bg-cyan-500 text-black shadow-sm"
                        : "border border-gray-700 text-gray-400 hover:text-white"
                    }`}
                  >
                    {sp.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* 畫面縮放與等比例校正控制列 */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-800/80 bg-black/30 p-2.5 text-xs text-gray-400">
            <div className="flex items-center gap-2">
              <span className="text-gray-300 font-semibold">示範畫面對齊:</span>
              <button
                type="button"
                onClick={handleAutoFraming}
                className="rounded bg-sky-950/60 border border-sky-800 px-2.5 py-1 text-sky-300 hover:bg-sky-900 transition"
                title="以人體軀幹等比例自動縮放"
              >
                自動等比例縮放
              </button>
            </div>

            <div className="flex items-center gap-3">
              <label className="flex items-center gap-1.5">
                <span>縮放:</span>
                <input
                  type="range"
                  min="0.7"
                  max="1.5"
                  step="0.05"
                  value={refZoom}
                  onChange={(e) => setRefZoom(Number(e.target.value))}
                  className="w-20"
                />
                <span className="font-mono text-[11px] text-gray-200">{refZoom.toFixed(2)}x</span>
              </label>

              <label className="flex items-center gap-1.5">
                <span>X 軸:</span>
                <input
                  type="range"
                  min="-100"
                  max="100"
                  step="5"
                  value={refOffsetX}
                  onChange={(e) => setRefOffsetX(Number(e.target.value))}
                  className="w-16"
                />
              </label>

              <label className="flex items-center gap-1.5">
                <span>Y 軸:</span>
                <input
                  type="range"
                  min="-100"
                  max="100"
                  step="5"
                  value={refOffsetY}
                  onChange={(e) => setRefOffsetY(Number(e.target.value))}
                  className="w-16"
                />
              </label>

              {(refZoom !== 1.0 || refOffsetX !== 0 || refOffsetY !== 0) && (
                <button
                  type="button"
                  onClick={() => {
                    setRefZoom(1.0);
                    setRefOffsetX(0);
                    setRefOffsetY(0);
                  }}
                  className="text-gray-500 hover:text-gray-300 text-[10px] underline"
                >
                  重設
                </button>
              )}
            </div>

            {/* 示範單獨微調按鈕 */}
            <div className="flex items-center gap-1 text-[11px]">
              <span>示範單獨:</span>
              <button
                type="button"
                onClick={() => stepRefFrame(-1)}
                className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
              >
                -1f
              </button>
              <button
                type="button"
                onClick={() => stepRefFrame(1)}
                className="rounded border border-gray-800 bg-black/60 px-1.5 py-0.5 text-gray-300 hover:border-gray-600"
              >
                +1f
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 匯入示範影片彈窗 (Modal) */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="max-w-md w-full rounded-2xl border border-gray-800 bg-[#0d141a] p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-white">
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

            {importError && (
              <div className="rounded-lg bg-red-950/80 border border-red-800 p-2.5 text-xs text-red-200">
                {importError}
              </div>
            )}

            <form onSubmit={handleImportSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-gray-300 mb-1">
                  本機影片檔案絕對路徑 (*.mp4 / *.mov) <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="/Users/username/Desktop/my_7i_dtl.mp4"
                  value={importFilePath}
                  onChange={(e) => setImportFilePath(e.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white placeholder-gray-600"
                  required
                />
              </div>

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
                  <label className="block text-gray-300 mb-1">版權授權說明</label>
                  <input
                    type="text"
                    value={importLicense}
                    onChange={(e) => setImportLicense(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block text-gray-300 mb-1">原始出處 / 參考連結 (選填)</label>
                <input
                  type="text"
                  placeholder="https://..."
                  value={importSourceUrl}
                  onChange={(e) => setImportSourceUrl(e.target.value)}
                  className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-2 text-white"
                />
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
                  {importing ? "分析並匯入中..." : "確認匯入"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
