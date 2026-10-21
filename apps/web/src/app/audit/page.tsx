"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { apiFetch, API_BASE_URL, getAuthToken } from "@/lib/api";

interface SwingEventRecord {
  time_ms: number;
  frame: number;
  status: "machine_suggested" | "human_verified" | "uncertain" | "pending_human_review";
  source: string;
  confidence: number;
  rationale?: string;
  verified_by?: string | null;
  verified_at?: string | null;
  previous_value?: {
    time_ms: number;
    frame: number;
    status?: string;
    source?: string;
  } | null;
}

interface GoldenSetSwing {
  gt_id: string;
  sequence_no: number;
  start_ms: number;
  end_ms: number;
  address_ms: number;
  takeaway_ms: number;
  top_ms: number;
  impact_ms: number;
  finish_ms: number;
  downswing_ms?: number | null;
  backswing_ms?: number | null;
  tempo_ratio?: number | null;
  frames: Record<string, number>;
  events: {
    address: SwingEventRecord;
    takeaway: SwingEventRecord;
    top: SwingEventRecord;
    impact: SwingEventRecord;
    finish: SwingEventRecord;
    [key: string]: SwingEventRecord;
  };
  strike_status: string;
  label: string;
  note?: string;
}

interface GoldenSetMeta {
  golden_set_id: string;
  name: string;
  description: string;
  video_filename: string;
  video_sha256: string;
  video_duration_ms: number;
  fps: number;
  total_frames: number;
  total_swings: number;
  matched_video_id: string | null;
  swings: GoldenSetSwing[];
}

interface AudioPeak {
  time_ms: number;
  energy: number;
  frame_idx: number;
}

const EVENT_LABELS: Record<string, string> = {
  address: "Address 站姿",
  takeaway: "Takeaway 起桿",
  top: "Top 上桿頂點",
  impact: "Impact 擊球瞬間",
  finish: "Finish 收桿完成",
};

export default function GoldenAuditPage() {
  const [goldenSets, setGoldenSets] = useState<GoldenSetMeta[]>([]);
  const [activeSetId, setActiveSetId] = useState<string>("real_2min_session");
  const [selectedSwingIndex, setSelectedSwingIndex] = useState<number>(0);
  const [audioPeaks, setAudioPeaks] = useState<AudioPeak[]>([]);
  const [currentVideoTimeMs, setCurrentVideoTimeMs] = useState<number>(0);
  const [currentFrame, setCurrentFrame] = useState<number>(0);
  const [activeEventKey, setActiveEventKey] = useState<string>("impact");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<{ text: string; type: "success" | "error" | "info" } | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);

  const activeSet = goldenSets.find((g) => g.golden_set_id === activeSetId) || goldenSets[0];
  const swings = activeSet?.swings || [];
  const selectedSwing = swings[selectedSwingIndex] || swings[0];

  const fetchGoldenSets = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await apiFetch<any>("/api/audit/golden-sets");
      const list = Array.isArray(res) ? res : res.golden_sets || [];
      const normalized = list.map((g: any) => ({
        ...g,
        golden_set_id: g.golden_set_id || g.dataset_id,
        video_duration_ms: g.video_duration_ms || g.duration_ms || 0,
        swings: g.swings || g.ground_truth_swings || [],
      }));
      setGoldenSets(normalized);
      if (normalized.length > 0) {
        const found =
          normalized.find((g: any) => g.golden_set_id === activeSetId) || normalized[0];
        setActiveSetId(found.golden_set_id);
      }
    } catch (err: any) {
      setMessage({ text: `無法載入 Golden Sets: ${err.message || err}`, type: "error" });
    } finally {
      setIsLoading(false);
    }
  }, [activeSetId]);

  useEffect(() => {
    fetchGoldenSets();
  }, [fetchGoldenSets]);

  // 載入當前 Golden Set 音訊峰值
  useEffect(() => {
    if (!activeSetId) return;
    apiFetch<any>(`/api/audit/golden-sets/${activeSetId}/audio-peaks`)
      .then((res) => {
        const list = Array.isArray(res) ? res : res.peaks || [];
        const norm = list.map((p: any) => ({
          time_ms: p.time_ms,
          energy: p.rms_energy ?? p.energy ?? 0.0,
          frame_idx: p.frame_idx ?? Math.round((p.time_ms / 1000) * (activeSet?.fps || 60)),
        }));
        setAudioPeaks(norm);
      })
      .catch(() => {
        setAudioPeaks([]);
      });
  }, [activeSetId, activeSet?.fps]);

  // 監聽播放器時間更新
  const handleTimeUpdate = () => {
    if (!videoRef.current || !activeSet) return;
    const ms = Math.round(videoRef.current.currentTime * 1000);
    setCurrentVideoTimeMs(ms);
    const frame = Math.round((ms / 1000) * (activeSet.fps || 60));
    setCurrentFrame(frame);
  };

  const jumpToMs = (ms: number, evKey?: string) => {
    if (evKey) setActiveEventKey(evKey);
    if (videoRef.current) {
      videoRef.current.currentTime = Math.max(0, ms / 1000);
      setCurrentVideoTimeMs(ms);
      if (activeSet) {
        setCurrentFrame(Math.round((ms / 1000) * (activeSet.fps || 60)));
      }
    }
  };

  const stepFrame = (deltaFrames: number) => {
    if (!videoRef.current || !activeSet) return;
    const fps = activeSet.fps || 59.99;
    const deltaSec = deltaFrames / fps;
    const targetSec = Math.max(0, Math.min(activeSet.video_duration_ms / 1000, videoRef.current.currentTime + deltaSec));
    videoRef.current.currentTime = targetSec;
  };

  // 將當前播放影格設定為選定事件
  const handleSetCurrentFrameAsEvent = async (eventName: string) => {
    if (!activeSet || !selectedSwing) return;
    const fps = activeSet.fps || 60.0;
    const targetMs = currentVideoTimeMs;

    // 前端防呆：檢核不得超出影片長度
    if (targetMs < 0 || targetMs > activeSet.video_duration_ms) {
      setMessage({ text: `時間碼 ${targetMs}ms 超出影片合法長度 [0, ${activeSet.video_duration_ms}]ms`, type: "error" });
      return;
    }

    try {
      setIsSaving(true);
      setMessage(null);
      const res = await apiFetch<any>(
        `/api/audit/golden-sets/${activeSet.golden_set_id}/swings/${selectedSwing.gt_id}/events/${eventName}`,
        {
          method: "PUT",
          body: JSON.stringify({
            time_ms: targetMs,
            frame: currentFrame,
            status: "human_verified",
            rationale: `人工逐格校正於 ${new Date().toLocaleTimeString()}（第 ${currentFrame} 幀）`,
          }),
        }
      );
      const evFrame = res?.event?.frame ?? currentFrame;
      setMessage({
        text: `已成功將第 #${selectedSwing.sequence_no} 球之 ${EVENT_LABELS[eventName]} 校正為 ${targetMs}ms（第 ${evFrame} 幀，人工已確認）`,
        type: "success",
      });
      // 重新整理資料
      await fetchGoldenSets();
    } catch (err: any) {
      setMessage({ text: `儲存校正失敗: ${err.message || err}`, type: "error" });
    } finally {
      setIsSaving(false);
    }
  };

  // 撤回修改：恢復為演算法建議值
  const handleResetToMachine = async () => {
    if (!activeSet || !selectedSwing) return;
    if (!confirm(`確定要撤回第 #${selectedSwing.sequence_no} 球的所有人工校正，恢復為演算法原始建議值嗎？`)) {
      return;
    }
    try {
      setIsSaving(true);
      await apiFetch<any>(
        `/api/audit/golden-sets/${activeSet.golden_set_id}/swings/${selectedSwing.gt_id}/reset`,
        { method: "POST" }
      );
      setMessage({ text: `已撤回第 #${selectedSwing.sequence_no} 球的人工修改，恢復為演算法建議值。`, type: "info" });
      await fetchGoldenSets();
    } catch (err: any) {
      setMessage({ text: `撤回失敗: ${err.message || err}`, type: "error" });
    } finally {
      setIsSaving(false);
    }
  };

  // 計算選定球與最近音訊峰值的差距
  const impactMs = selectedSwing?.events?.impact?.time_ms || 0;
  const closestAudioPeak = audioPeaks
    .filter((p) => Math.abs(p.time_ms - impactMs) < 1500)
    .sort((a, b) => Math.abs(a.time_ms - impactMs) - Math.abs(b.time_ms - impactMs))[0];

  // 吸附至音訊峰值
  const snapToAudioPeak = () => {
    if (!closestAudioPeak) return;
    jumpToMs(closestAudioPeak.time_ms, "impact");
    setMessage({
      text: `已跳轉至最接近音訊撞擊峰值: ${closestAudioPeak.time_ms}ms（能量強度 ${closestAudioPeak.energy.toFixed(3)}）`,
      type: "info",
    });
  };

  // 節奏計算 (Backswing / Downswing: P1-4 嚴格高爾夫運動學定義)
  const calcTempoRatio = (sw: GoldenSetSwing) => {
    if (sw.tempo_ratio !== undefined && sw.tempo_ratio !== null) {
      return sw.tempo_ratio.toFixed(2);
    }
    const top = sw.events?.top?.time_ms;
    const impact = sw.events?.impact?.time_ms;
    const takeaway = sw.events?.takeaway?.time_ms;
    if (top && impact && takeaway && takeaway < top && top < impact) {
      const bs = top - takeaway;
      const ds = impact - top;
      if (ds > 0 && bs > 0) return (bs / ds).toFixed(2);
    }
    return "N/A";
  };

  if (isLoading && goldenSets.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-400">
        正在載入 Golden Set 基準資料...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 標題與基準切換 */}
      <div className="flex flex-col justify-between gap-4 border-b border-gray-800 pb-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">Golden Set 人工校核與時間碼真值確認</h1>
            <span className="rounded bg-sky-950 px-2 py-0.5 text-xs font-semibold text-sky-400 border border-sky-800">
              R13-C 互動校核
            </span>
          </div>
          <p className="mt-1 text-xs text-gray-400">
            拒絕將演算法預測直接當作 Ground Truth。每球事件具備獨立狀態（machine_suggested / human_verified），嚴格驗證真實揮桿特徵。
          </p>
        </div>

        {/* 基準資料集選擇器 */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400">基準影片：</label>
          <select
            value={activeSetId}
            onChange={(e) => {
              setActiveSetId(e.target.value);
              setSelectedSwingIndex(0);
            }}
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-white focus:border-emerald-500 focus:outline-none"
          >
            {goldenSets.map((gs) => (
              <option key={gs.golden_set_id} value={gs.golden_set_id}>
                {gs.name} ({gs.total_swings} 球)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 提示訊息 */}
      {message && (
        <div
          className={`rounded-xl border p-3 text-xs ${
            message.type === "success"
              ? "border-emerald-500/40 bg-emerald-950/40 text-emerald-300"
              : message.type === "error"
              ? "border-rose-500/40 bg-rose-950/40 text-rose-300"
              : "border-sky-500/40 bg-sky-950/40 text-sky-300"
          }`}
        >
          {message.text}
        </div>
      )}

      {/* 影片元數據卡片 */}
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs sm:grid-cols-4">
        <div>
          <span className="text-gray-500">影片檔名：</span>
          <span className="font-semibold text-gray-200 ml-1">{activeSet?.video_filename}</span>
        </div>
        <div>
          <span className="text-gray-500">FPS / 總影格：</span>
          <span className="font-semibold text-gray-200 ml-1">
            {activeSet?.fps?.toFixed(2)} fps / {activeSet?.total_frames} 幀
          </span>
        </div>
        <div>
          <span className="text-gray-500">總時長：</span>
          <span className="font-semibold text-gray-200 ml-1">
            {(activeSet?.video_duration_ms / 1000).toFixed(2)} 秒 ({activeSet?.video_duration_ms}ms)
          </span>
        </div>
        <div>
          <span className="text-gray-500">SHA-256：</span>
          <span className="font-mono text-[10px] text-gray-400 ml-1" title={activeSet?.video_sha256}>
            {activeSet?.video_sha256?.substring(0, 16)}...
          </span>
        </div>
      </div>

      {/* 主工作區：左側影格播放與校正控制，右側揮桿列表與事件細節 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* 左側：影格級播放器與標定操作 */}
        <div className="lg:col-span-7 space-y-4">
          <div className="relative overflow-hidden rounded-2xl border border-gray-800 bg-black">
            {activeSet?.matched_video_id ? (
              <video
                ref={videoRef}
                controls
                playsInline
                preload="metadata"
                onTimeUpdate={handleTimeUpdate}
                className="aspect-video w-full"
                src={`${API_BASE_URL}/api/videos/${activeSet.matched_video_id}/stream?token=${encodeURIComponent(
                  getAuthToken() || ""
                )}#t=${(selectedSwing.start_ms / 1000).toFixed(2)},${(selectedSwing.end_ms / 1000).toFixed(2)}`}
              />
            ) : (
              <div className="flex aspect-video w-full flex-col items-center justify-center p-6 text-center text-xs text-gray-400">
                <span className="text-amber-400 font-bold mb-1">未串流匹配之原始影片</span>
                <span>資料庫中尚未找到 SHA-256 完全符合 {activeSet?.video_filename} 的影片記錄。</span>
                <span className="text-gray-500 mt-2">（請至首頁或場次頁面上傳同檔名原始影片以啟動串流）</span>
              </div>
            )}
          </div>

          {/* 播放器時間與微調控制 */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-gray-400">當前位置：</span>
              <span className="font-mono text-sm font-bold text-white">
                {(currentVideoTimeMs / 1000).toFixed(3)}s
              </span>
              <span className="font-mono text-xs text-emerald-400">({currentVideoTimeMs}ms)</span>
              <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-gray-300">
                第 {currentFrame} 幀
              </span>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => stepFrame(-5)}
                className="rounded bg-gray-800 px-2 py-1 text-gray-200 hover:bg-gray-700"
                title="後退 5 幀"
              >
                -5 幀
              </button>
              <button
                type="button"
                onClick={() => stepFrame(-1)}
                className="rounded bg-gray-800 px-2 py-1 font-bold text-gray-200 hover:bg-gray-700"
                title="後退 1 幀"
              >
                ◀ -1
              </button>
              <button
                type="button"
                onClick={() => stepFrame(1)}
                className="rounded bg-gray-800 px-2 py-1 font-bold text-gray-200 hover:bg-gray-700"
                title="前進 1 幀"
              >
                +1 ▶
              </button>
              <button
                type="button"
                onClick={() => stepFrame(5)}
                className="rounded bg-gray-800 px-2 py-1 text-gray-200 hover:bg-gray-700"
                title="前進 5 幀"
              >
                +5 幀
              </button>
            </div>
          </div>

          {/* 核心校核按鈕：將目前影格設為指定事件 */}
          <div className="rounded-xl border border-emerald-600/30 bg-emerald-950/20 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold text-emerald-300 text-xs">
                🎯 影格標定操作（將目前播放位置設定為第 #{selectedSwing?.sequence_no} 球關鍵事件）：
              </span>
              <button
                type="button"
                onClick={handleResetToMachine}
                disabled={isSaving}
                className="text-[11px] text-amber-400 underline hover:text-amber-300 disabled:opacity-50"
              >
                撤回本球修改（恢復建議值）
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {(["address", "takeaway", "top", "impact", "finish"] as const).map((evKey) => {
                const evData = selectedSwing?.events?.[evKey];
                const isVerified = evData?.status === "human_verified";
                return (
                  <button
                    key={evKey}
                    type="button"
                    disabled={isSaving}
                    onClick={() => handleSetCurrentFrameAsEvent(evKey)}
                    className={`flex flex-col items-center justify-center rounded-lg border p-2 text-center transition ${
                      isVerified
                        ? "border-emerald-500 bg-emerald-900/40 text-emerald-200 hover:bg-emerald-900/60"
                        : "border-gray-700 bg-gray-900/60 text-gray-200 hover:border-emerald-500"
                    }`}
                  >
                    <span className="text-[11px] font-bold">
                      📌 設為 {evKey.toUpperCase()}
                    </span>
                    <span className="text-[10px] text-gray-400 mt-0.5">
                      {EVENT_LABELS[evKey]}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 音訊衝擊能量波形對照 */}
          <div className="rounded-xl border border-gray-800 bg-[#0d141a] p-4 text-xs space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-bold text-white">🎵 48kHz PCM 音訊衝擊能量候選峰值：</span>
                <span className="rounded bg-sky-950 px-2 py-0.5 text-[10px] text-sky-400 border border-sky-800">
                  共 {audioPeaks.length} 個峰值
                </span>
              </div>
              {closestAudioPeak && (
                <button
                  type="button"
                  onClick={snapToAudioPeak}
                  className="rounded bg-sky-600 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-sky-500"
                >
                  ⚡ 吸附至最接近峰值 ({closestAudioPeak.time_ms}ms)
                </button>
              )}
            </div>

            {closestAudioPeak ? (
              <div className="flex items-center justify-between rounded-lg bg-black/40 p-2.5 border border-gray-800">
                <div>
                  <span className="text-gray-400">目前 Impact ({impactMs}ms) 最近音訊撞擊：</span>
                  <span className="font-mono font-bold text-emerald-400 ml-1">
                    {closestAudioPeak.time_ms}ms (第 {closestAudioPeak.frame_idx} 幀)
                  </span>
                  <span className="text-gray-500 text-[10px] ml-2">
                    能量強度: {closestAudioPeak.energy.toFixed(3)}
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-gray-400">時間差：</span>
                  <span
                    className={`font-mono font-bold ml-1 ${
                      Math.abs(impactMs - closestAudioPeak.time_ms) <= 50
                        ? "text-emerald-400"
                        : "text-amber-400"
                    }`}
                  >
                    {(impactMs - closestAudioPeak.time_ms > 0 ? "+" : "") +
                      (impactMs - closestAudioPeak.time_ms)}
                    ms
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-gray-500 text-[11px]">
                Impact 附近 1.5 秒內未偵測到顯著音訊脈衝能量。
              </div>
            )}
          </div>
        </div>

        {/* 右側：12 球列表與逐球事件檢視 */}
        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4 text-xs space-y-3">
            <div className="flex items-center justify-between border-b border-gray-800 pb-2">
              <span className="font-bold text-white text-sm">
                第 #{selectedSwing?.sequence_no} 球事件細節
              </span>
              <span className="rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
                節奏比: {selectedSwing ? calcTempoRatio(selectedSwing) : "N/A"}:1
              </span>
            </div>

            {selectedSwing?.note && (
              <div className="rounded-lg bg-amber-950/30 border border-amber-800/40 p-2 text-amber-200 text-[11px] leading-relaxed">
                {selectedSwing.note}
              </div>
            )}

            {/* 各事件表格 (P0-1 嚴格前後端資料契約) */}
            <div className="space-y-2">
              {(["address", "takeaway", "top", "impact", "finish"] as const).map((evKey) => {
                const evData = selectedSwing?.events?.[evKey];
                const isVerified = evData?.status === "human_verified";
                const isUncertain = evData?.status === "uncertain";
                const origMs = evData?.previous_value ? evData.previous_value.time_ms : evData?.time_ms;
                const origFrame = evData?.previous_value ? evData.previous_value.frame : evData?.frame;
                const deltaMs = evData && origMs !== undefined ? evData.time_ms - origMs : 0;
                const deltaFrames = evData && origFrame !== undefined ? evData.frame - origFrame : 0;

                return (
                  <div
                    key={evKey}
                    className={`flex items-center justify-between rounded-lg border p-2.5 transition ${
                      activeEventKey === evKey
                        ? "border-emerald-500/80 bg-emerald-950/30"
                        : "border-gray-800 bg-gray-900/40"
                    }`}
                  >
                    <div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => evData && jumpToMs(evData.time_ms, evKey)}
                          className="font-bold text-white hover:text-emerald-400 underline"
                        >
                          {EVENT_LABELS[evKey]}
                        </button>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                            isVerified
                              ? "bg-emerald-900/80 text-emerald-300 border border-emerald-700"
                              : isUncertain
                              ? "bg-amber-950 text-amber-400 border border-amber-800"
                              : "bg-sky-950 text-sky-400 border border-sky-800"
                          }`}
                        >
                          {isVerified ? "人工已確認" : isUncertain ? "標記不確定" : "演算法建議"}
                        </span>
                      </div>
                      <div className="text-[10px] text-gray-400 mt-1">
                        依據: {evData?.rationale || "運動學動能峰值"}
                      </div>
                      {isVerified && evData?.verified_at && (
                        <div className="text-[9px] text-emerald-400">
                          校核時間: {new Date(evData.verified_at).toLocaleTimeString()}{" "}
                          {evData.verified_by ? `(${evData.verified_by})` : ""}
                        </div>
                      )}
                    </div>

                    <div className="text-right">
                      <div className="font-mono text-xs font-bold text-emerald-300">
                        {evData?.time_ms}ms
                      </div>
                      <div className="text-[10px] text-gray-400">
                        第 {evData?.frame} 幀
                      </div>
                      {isVerified && (deltaMs !== 0 || deltaFrames !== 0) && (
                        <div className="font-mono text-[9px] text-amber-400">
                          Δ {deltaMs > 0 ? `+${deltaMs}` : deltaMs}ms (
                          {deltaFrames > 0 ? `+${deltaFrames}` : deltaFrames}f)
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 全場次揮桿切換選單 */}
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4 text-xs space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white">全場揮桿列表 ({swings.length} 球)：</span>
              <span className="text-[10px] text-gray-400">點擊選取進行逐格校核</span>
            </div>

            <div className="max-h-72 overflow-y-auto space-y-1.5 pr-1">
              {swings.map((sw, idx) => {
                const isSelected = idx === selectedSwingIndex;
                const verifiedCount = Object.values(sw.events || {}).filter(
                  (e) => e.status === "human_verified"
                ).length;
                return (
                  <button
                    key={sw.gt_id}
                    type="button"
                    onClick={() => {
                      setSelectedSwingIndex(idx);
                      jumpToMs(sw.start_ms, "impact");
                    }}
                    className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition ${
                      isSelected
                        ? "border-emerald-500 bg-emerald-950/40 text-white"
                        : "border-gray-800 bg-gray-900/40 text-gray-300 hover:border-gray-700"
                    }`}
                  >
                    <div>
                      <span className="font-bold">第 #{sw.sequence_no} 球</span>
                      <span className="text-gray-500 text-[10px] ml-2">
                        {sw.start_ms}ms - {sw.end_ms}ms
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-gray-400">
                        {calcTempoRatio(sw)}:1
                      </span>
                      <span
                        className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${
                          verifiedCount > 0
                            ? "bg-emerald-900/60 text-emerald-300"
                            : "bg-gray-800 text-gray-400"
                        }`}
                      >
                        {verifiedCount}/5 確認
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
