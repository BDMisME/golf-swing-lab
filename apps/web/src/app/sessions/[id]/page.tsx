"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  API_BASE_URL,
  apiFetch,
  formatCoverageStatus,
  formatMsToTimestamp,
  getAuthToken,
  SwingSegmentItem,
} from "@/lib/api";

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const sessionId = params.id;

  const [sessionData, setSessionData] = useState<any>(null);
  const [swings, setSwings] = useState<SwingSegmentItem[]>([]);
  const [report, setReport] = useState<any>(null);
  const [rankingTab, setRankingTab] = useState<
    "posture" | "tempo" | "finish" | "ig"
  >("posture");
  const [compareIds, setCompareIds] = useState<[string, string]>(["", ""]);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [manualStartMs, setManualStartMs] = useState(1000);
  const [manualEndMs, setManualEndMs] = useState(4200);
  const [exportMsg, setExportMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reportLoading, setReportLoading] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const s = await apiFetch<any>(`/api/sessions/${sessionId}`);
      setSessionData(s);

      if (s.videos && s.videos.length > 0) {
        const firstVid = s.videos[0];
        const swRes = await apiFetch<{ items: SwingSegmentItem[] }>(
          `/api/videos/${firstVid.id}/swings`
        );
        const list = swRes.items || [];
        setSwings(list);
        if (list.length >= 2 && (!compareIds[0] || !compareIds[1])) {
          setCompareIds([list[0].id, list[1].id]);
        } else if (list.length === 1 && !compareIds[0]) {
          setCompareIds([list[0].id, list[0].id]);
        }
      }

      // 立即解鎖時間軸與切球清單渲染！
      setLoading(false);

      // 異步背景獲取教練報告，不阻斷主畫面互動
      setReportLoading(true);
      apiFetch<any>(`/api/sessions/${sessionId}/report`)
        .then((rep) => setReport(rep))
        .catch(() => {})
        .finally(() => setReportLoading(false));
    } catch (err: any) {
      if (String(err.message).includes("401")) {
        router.push("/login");
      }
      setLoading(false);
    }
  }, [sessionId, router, compareIds]);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/login");
      return;
    }
    loadAll();
  }, [loadAll, router]);

  useEffect(() => {
    const hasPendingJob = sessionData?.videos?.some(
      (v: any) =>
        v.latest_job &&
        ["queued", "running"].includes(v.latest_job.status)
    );
    if (!hasPendingJob) return;
    const timer = setInterval(() => {
      loadAll();
    }, 2500);
    return () => clearInterval(timer);
  }, [sessionData, loadAll]);

  const handleTriggerAnalyze = async (videoId: string, force = false) => {
    await apiFetch(`/api/videos/${videoId}/analyze?force=${force}`, {
      method: "POST",
    });
    await loadAll();
  };

  const handleToggleLabel = async (swId: string, currentLabel: string) => {
    const nextLabel = currentLabel === "practice_swing" ? "valid_swing" : "practice_swing";
    await apiFetch(`/api/swings/${swId}`, {
      method: "PATCH",
      body: JSON.stringify({ label: nextLabel }),
    });
    await loadAll();
  };

  const handleAddManualSwing = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sessionData?.videos?.length) return;
    const vidId = sessionData.videos[0].id;
    await apiFetch(`/api/videos/${vidId}/swings`, {
      method: "POST",
      body: JSON.stringify({
        start_ms: Number(manualStartMs),
        end_ms: Number(manualEndMs),
        label: "valid_swing",
        ball_strike_status: "confirmed_strike",
        notes: "使用者於時間軸手動新增片段",
      }),
    });
    await loadAll();
  };

  const handleDeleteSwing = async (swingId: string) => {
    await apiFetch(`/api/swings/${swingId}`, { method: "DELETE" });
    await loadAll();
  };

  const handleExportHighlight = async (layout: "original" | "9:16") => {
    const validIds = swings
      .filter((s) => s.label !== "practice_swing")
      .slice(0, 3)
      .map((s) => s.id);
    const targetIds = validIds.length > 0 ? validIds : swings.slice(0, 2).map((s) => s.id);
    if (targetIds.length === 0) return;

    setExportMsg("正在建立 MP4 匯出任務...");
    const exp = await apiFetch<{ id: string; status: string }>("/api/exports", {
      method: "POST",
      body: JSON.stringify({
        segment_ids: targetIds,
        layout,
        format: "mp4",
      }),
    });
    setExportMsg(
      `已建立匯出任務 (${layout === "9:16" ? "9:16 直式社群版" : "原始比例"})，狀態：${exp.status}。可至「匯出中心」下載 MP4。`
    );
  };

  if (loading) {
    return (
      <div className="py-16 text-center text-sm text-gray-400">
        載入練習場次與時間軸分析資料中...
      </div>
    );
  }

  if (!sessionData) {
    return (
      <div className="py-16 text-center text-sm text-red-300">
        找不到該練習場次資料
      </div>
    );
  }

  const primaryVideo = sessionData.videos?.[0];
  const durationMs = Math.max(1000, primaryVideo?.duration_ms || 16000);
  const swingA = swings.find((s) => s.id === compareIds[0]);
  const swingB = swings.find((s) => s.id === compareIds[1]);
  const currentRankList: any[] = report?.rankings?.[rankingTab] || [];

  return (
    <div className="space-y-6">
      {/* 場次標頭 */}
      <section className="flex flex-col justify-between gap-4 rounded-2xl border border-emerald-900/60 bg-[#0d151c] p-5 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-emerald-600/20 px-2 py-0.5 text-xs font-bold text-emerald-300 border border-emerald-500/40">
              {sessionData.club}
            </span>
            <span className="text-xs text-gray-400">
              {sessionData.date} · {sessionData.handedness === "right" ? "右打" : "左打"} · {sessionData.camera_angle} 視角
            </span>
          </div>
          <h1 className="mt-1 text-xl font-bold text-white">
            {sessionData.title}
          </h1>
          <p className="mt-0.5 text-xs text-gray-400">
            {sessionData.notes || "系統僅計算 2D 畫面可觀測之幾何指標，不捏造球速、距離與飛行弧線"}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {primaryVideo && (
            <button
              onClick={() => handleTriggerAnalyze(primaryVideo.id, true)}
              className="rounded-xl border border-emerald-600/50 bg-emerald-950/50 px-3 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-600 hover:text-white"
            >
              重新掃描分析 (保留人工校正)
            </button>
          )}
          <button
            onClick={() => handleExportHighlight("original")}
            disabled={swings.length === 0}
            className="rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-40"
          >
            匯出精選原始比例 MP4
          </button>
          <button
            onClick={() => handleExportHighlight("9:16")}
            disabled={swings.length === 0}
            className="rounded-xl bg-amber-600 px-3 py-2 text-xs font-bold text-white hover:bg-amber-500 disabled:opacity-40"
          >
            匯出 9:16 直式社群短片
          </button>
        </div>
      </section>

      {exportMsg && (
        <div className="flex items-center justify-between rounded-xl border border-emerald-500/40 bg-emerald-950/40 px-4 py-3 text-xs text-emerald-200">
          <span>{exportMsg}</span>
          <Link href="/exports" className="font-bold underline">
            前往匯出中心 &rarr;
          </Link>
        </div>
      )}

      {/* 影片與佇列狀態 */}
      {primaryVideo?.latest_job && (
        <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-white">
              分析工作狀態：{primaryVideo.latest_job.status}（階段：{primaryVideo.latest_job.stage}）
            </span>
            <span className="text-emerald-400">
              {primaryVideo.latest_job.progress_pct}% · {primaryVideo.latest_job.message}
            </span>
          </div>
          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-800">
            <div
              className="h-full bg-emerald-500 transition-all"
              style={{ width: `${primaryVideo.latest_job.progress_pct || 0}%` }}
            />
          </div>
        </section>
      )}

      {/* 互動式時間軸與人工切球區 */}
      <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-4">
        <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-base font-bold text-white">
              練習場影片時間軸 (Coarse-to-Fine 自動切球 + 人工微調)
            </h2>
            <p className="text-xs text-gray-400">
              綠色代表正式揮桿、黃色代表需人工複核、灰色代表空揮練習。點擊任一球可進入單球逐幀骨架檢視。
            </p>
          </div>
          <span className="text-xs text-gray-400">
            總片長：{formatMsToTimestamp(durationMs)} · 共 {swings.length} 球
          </span>
        </div>

        {/* 視覺化時間軸軌道 */}
        <div className="relative h-14 w-full overflow-hidden rounded-xl border border-gray-700 bg-black/60">
          {swings.map((sw) => {
            const leftPct = Math.min(98, Math.max(0, (sw.start_ms / durationMs) * 100));
            const widthPct = Math.max(
              3,
              Math.min(100 - leftPct, ((sw.end_ms - sw.start_ms) / durationMs) * 100)
            );
            const isPractice = sw.label === "practice_swing";
            const needsRev = sw.review_status === "needs_review";
            const bgClass = isPractice
              ? "bg-gray-600/70 border-gray-400"
              : needsRev
                ? "bg-amber-600/75 border-amber-400"
                : "bg-emerald-600/80 border-emerald-400";

            return (
              <Link
                key={sw.id}
                href={`/swings/${sw.id}`}
                style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                className={`absolute top-2 bottom-2 flex flex-col items-center justify-center rounded-lg border px-1 text-[10px] font-bold text-white shadow transition hover:brightness-125 ${bgClass}`}
                title={`#${sw.sequence_no} (${formatMsToTimestamp(sw.start_ms)} - ${formatMsToTimestamp(sw.end_ms)})`}
              >
                <span>#{sw.sequence_no}</span>
                <span className="text-[9px] opacity-90">
                  {sw.overall_score !== null ? `${sw.overall_score}分` : "N/A"}
                </span>
              </Link>
            );
          })}
        </div>

        {/* 手動新增揮桿區段表單 */}
        <form
          onSubmit={handleAddManualSwing}
          className="flex flex-wrap items-end gap-3 rounded-xl border border-gray-800 bg-black/30 p-3 text-xs"
        >
          <div>
            <label className="block text-[11px] text-gray-400">手動新增起點 (ms)</label>
            <input
              type="number"
              min={0}
              value={manualStartMs}
              onChange={(e) => setManualStartMs(Number(e.target.value))}
              className="mt-1 w-28 rounded-lg border border-gray-700 bg-black/60 px-2.5 py-1.5 text-white"
            />
          </div>
          <div>
            <label className="block text-[11px] text-gray-400">手動新增終點 (ms)</label>
            <input
              type="number"
              min={500}
              value={manualEndMs}
              onChange={(e) => setManualEndMs(Number(e.target.value))}
              className="mt-1 w-28 rounded-lg border border-gray-700 bg-black/60 px-2.5 py-1.5 text-white"
            />
          </div>
          <button
            type="submit"
            className="rounded-lg border border-emerald-600/60 bg-emerald-600/20 px-3 py-1.5 font-semibold text-emerald-300 hover:bg-emerald-600 hover:text-white"
          >
            + 手動新增揮桿片段
          </button>
        </form>

        {/* 每一球列表 */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {swings.map((sw) => {
            const cov = formatCoverageStatus(sw.overall_score, sw.coverage_ratio);
            return (
              <div
                key={sw.id}
                className="flex flex-col justify-between rounded-xl border border-gray-800 bg-black/40 p-4"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white">
                      第 #{sw.sequence_no} 球
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 text-[10px] font-semibold ${
                        sw.label === "practice_swing"
                          ? "bg-gray-800 text-gray-300"
                          : sw.review_status === "needs_review"
                            ? "bg-amber-950 text-amber-300 border border-amber-700/50"
                            : "bg-emerald-950 text-emerald-300 border border-emerald-700/50"
                      }`}
                    >
                      {sw.label === "practice_swing"
                        ? "空揮 (Practice)"
                        : sw.review_status === "needs_review"
                          ? "建議複核"
                          : "正式揮桿"}
                    </span>
                  </div>

                  <div className="mt-1 text-xs text-gray-400">
                    時間碼：{formatMsToTimestamp(sw.start_ms)} – {formatMsToTimestamp(sw.end_ms)}
                  </div>

                  <div className="mt-3 flex items-baseline justify-between">
                    <div>
                      <div className="text-[11px] text-gray-400">綜合動作分</div>
                      <div className="text-xl font-bold text-emerald-400">
                        {cov.displayScore}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-[11px] text-gray-400">IG 吸睛分 (獨立)</div>
                      <div className="text-sm font-semibold text-amber-300">
                        {sw.ig_visual_score ?? "N/A"}
                      </div>
                    </div>
                  </div>
                  <div className="mt-1 text-[11px] text-gray-500">
                    {cov.badgeText} · 信心度 {(sw.confidence * 100).toFixed(0)}%
                    {sw.manual_override && " · 已人工校正"}
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-gray-800/80 pt-3">
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/swings/${sw.id}`}
                      className="rounded-lg bg-emerald-600/20 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-600 hover:text-white"
                    >
                      單球詳情與軌跡 &rarr;
                    </Link>
                    <button
                      type="button"
                      onClick={() => handleToggleLabel(sw.id, sw.label)}
                      className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                        sw.label === "practice_swing"
                          ? "border border-emerald-600/60 bg-emerald-950/40 text-emerald-400 hover:bg-emerald-900/60"
                          : "border border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200"
                      }`}
                      title={sw.label === "practice_swing" ? "點擊將此球轉為正式揮桿並重新計分" : "點擊將此球設為空揮練習"}
                    >
                      {sw.label === "practice_swing" ? "轉為正式擊球" : "設為空揮"}
                    </button>
                  </div>
                  <button
                    onClick={() => handleDeleteSwing(sw.id)}
                    className="text-xs text-gray-500 hover:text-red-400"
                  >
                    刪除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Top 3 / Top 5 多維排行榜 */}
      <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-4">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h2 className="text-base font-bold text-white">
              本場次最佳揮桿排行榜 (Top Swings)
            </h2>
            <p className="text-xs text-gray-400">
              自動排除空揮與指標覆蓋率未達 70% 之低信心片段；IG 視覺吸睛分獨立排名。
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              { key: "posture", label: "姿勢與動作最佳" },
              { key: "tempo", label: "節奏最流暢" },
              { key: "finish", label: "收桿最平衡" },
              { key: "ig", label: "最適合發 IG" },
            ].map((t) => (
              <button
                key={t.key}
                onClick={() => setRankingTab(t.key as any)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  rankingTab === t.key
                    ? "bg-emerald-600 text-white"
                    : "bg-black/40 text-gray-400 hover:text-white"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {currentRankList.length === 0 ? (
          <div className="py-6 text-center text-xs text-gray-500">
            此分類尚無符合 70% 覆蓋率門檻之有效揮桿
          </div>
        ) : (
          <div className="divide-y divide-gray-800">
            {currentRankList.map((item: any, idx: number) => {
              const segId = item.segment_id || item.id;
              return (
                <div
                  key={segId}
                  className="flex items-center justify-between py-2.5 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-600/20 font-bold text-emerald-300">
                      {idx + 1}
                    </span>
                    <Link
                      href={`/swings/${segId}`}
                      className="font-bold text-white hover:text-emerald-400"
                    >
                      第 #{item.sequence_no} 球 ({formatMsToTimestamp(item.start_ms)} –{" "}
                      {formatMsToTimestamp(item.end_ms)})
                    </Link>
                  </div>
                  <div className="font-bold text-emerald-400">
                    分類得分 {item.category_score ?? item.overall_score ?? "N/A"} 分 · 綜合{" "}
                    {item.overall_score ?? "N/A"} 分
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* 雙球同步對照比較器 (2-Swing Comparison) */}
      {swings.length >= 1 && (
        <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-4">
          <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-base font-bold text-white">
                雙球同步對照比較 (2-Swing Side-by-Side Comparison)
              </h2>
              <p className="text-xs text-gray-400">
                可選擇本場次任意兩球對照 5 項子分數、階段時間差與穩定度變化
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <select
                value={compareIds[0]}
                onChange={(e) => setCompareIds([e.target.value, compareIds[1]])}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
              >
                {swings.map((s) => (
                  <option key={s.id} value={s.id}>
                    基準球：第 #{s.sequence_no} 球 ({s.overall_score ?? "N/A"}分)
                  </option>
                ))}
              </select>
              <span className="text-gray-500">vs</span>
              <select
                value={compareIds[1]}
                onChange={(e) => setCompareIds([compareIds[0], e.target.value])}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1.5 text-white"
              >
                {swings.map((s) => (
                  <option key={s.id} value={s.id}>
                    對照球：第 #{s.sequence_no} 球 ({s.overall_score ?? "N/A"}分)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 雙球慢動作控制列 */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-800 bg-black/60 p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-gray-400 font-semibold">雙球播放速度:</span>
              {[
                { label: "1.0x 原速", val: 1.0 },
                { label: "0.5x 慢速", val: 0.5 },
                { label: "0.25x 超慢動作", val: 0.25 },
              ].map((sp) => (
                <button
                  key={sp.val}
                  type="button"
                  onClick={() => {
                    setPlaybackSpeed(sp.val);
                    const vids = document.querySelectorAll<HTMLVideoElement>(".compare-video");
                    vids.forEach((v) => {
                      v.playbackRate = sp.val;
                    });
                  }}
                  className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                    playbackSpeed === sp.val
                      ? "bg-emerald-500 text-black shadow-sm"
                      : "border border-gray-700 bg-black/40 text-gray-300 hover:border-gray-500"
                  }`}
                >
                  {sp.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  const vids = document.querySelectorAll<HTMLVideoElement>(".compare-video");
                  const allPaused = Array.from(vids).every((v) => v.paused);
                  vids.forEach((v) => {
                    if (allPaused) v.play();
                    else v.pause();
                  });
                }}
                className="rounded-lg border border-emerald-600 bg-emerald-950/40 px-3 py-1 font-semibold text-emerald-400 hover:bg-emerald-900/50"
              >
                ▶/⏸ 雙球同步播放 / 暫停
              </button>
            </div>
          </div>

          {swingA && swingB && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {[swingA, swingB].map((sw, idx) => (
                <div
                  key={`${sw.id}-${idx}`}
                  className="rounded-xl border border-gray-800 bg-black/40 p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white">
                      {idx === 0 ? "基準球 (A)" : "對照球 (B)"}：第 #{sw.sequence_no} 球
                    </span>
                    <span className="text-sm font-bold text-emerald-400">
                      綜合 {sw.overall_score ?? "N/A"} 分
                    </span>
                  </div>
                  {primaryVideo && (
                    <video
                      controls
                      playsInline
                      preload="metadata"
                      src={`${API_BASE_URL}/api/videos/${primaryVideo.id}/stream?token=${encodeURIComponent(getAuthToken() || "")}#t=${(sw.start_ms / 1000).toFixed(2)},${(sw.end_ms / 1000).toFixed(2)}`}
                      className="compare-video w-full rounded-lg border border-gray-800 bg-black"
                    />
                  )}
                  <div className="space-y-1.5 text-xs">
                    {Object.entries(sw.subscores || {})
                      .filter(
                        ([k, sub]: [string, any]) =>
                          k !== "ig_visual_breakdown" &&
                          sub &&
                          typeof sub.weight === "number"
                      )
                      .map(([k, sub]: [string, any]) => (
                        <div
                          key={k}
                          className="flex items-center justify-between text-gray-300"
                        >
                          <span>{sub.label_zh || sub.label || k}</span>
                          <span className="font-semibold text-white">
                            {typeof sub.score === "number"
                              ? `${sub.score} 分`
                              : "缺資料"}{" "}
                            (原始值: {sub.raw_value ?? "N/A"} {sub.unit || ""})
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* 規則式 / AI 教練總結報告 (含骨架波紋加載狀態) */}
      {reportLoading && !report?.coach_report && (
        <section className="animate-pulse rounded-2xl border border-gray-800 bg-[#0d161d] p-5 space-y-3">
          <div className="h-4 w-48 rounded bg-gray-700" />
          <div className="h-3 w-72 rounded bg-gray-800" />
          <div className="h-16 w-full rounded-xl bg-gray-800/50" />
        </section>
      )}

      {report?.coach_report && (
        <section className="rounded-2xl border border-emerald-900/60 bg-[#0d161d] p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-white">
                練習場次動作診斷與訓練處方
              </h2>
              <p className="text-xs text-emerald-400">
                {report.coach_report.notice}
              </p>
            </div>
            <span className="rounded-lg border border-emerald-700/50 bg-emerald-950/60 px-2.5 py-1 text-[11px] text-emerald-300">
              Provider: {report.coach_report.provider}
            </span>
          </div>

          <p className="rounded-xl bg-black/40 p-3.5 text-xs leading-relaxed text-gray-200">
            {report.coach_report.summary}
          </p>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-gray-300">
                關鍵指標觀測證據 (可點擊時間碼驗證)
              </h3>
              {(report.coach_report.observations || []).map(
                (obs: any, i: number) => (
                  <div
                    key={i}
                    className="rounded-xl border border-gray-800 bg-black/40 p-3 text-xs"
                  >
                    <div className="font-bold text-white">{obs.title}</div>
                    <p className="mt-1 text-gray-400">{obs.detail}</p>
                    <div className="mt-1.5 text-[11px] text-emerald-400">
                      指標：{obs.metric_key} = {obs.metric_value ?? "N/A"} · 時間點：
                      {formatMsToTimestamp(obs.time_ms)} · 信心度{" "}
                      {Math.round((obs.confidence || 0) * 100)}%
                    </div>
                  </div>
                )
              )}
            </div>

            <div className="space-y-2">
              <h3 className="text-xs font-bold text-gray-300">
                優先修正項目與練習法 (Priority Fixes)
              </h3>
              {(report.coach_report.priority_fixes || []).map(
                (fix: any, i: number) => (
                  <div
                    key={i}
                    className="rounded-xl border border-gray-800 bg-black/40 p-3 text-xs"
                  >
                    <div className="font-bold text-amber-300">
                      {fix.focus_area}
                    </div>
                    <div className="mt-1 text-gray-200">
                      動作提示：{fix.action_cue}
                    </div>
                    <div className="mt-1 text-gray-400">
                      訓練處方：{fix.drill_steps}
                    </div>
                    <div className="mt-1 text-[11px] text-emerald-400">
                      目標範圍：{fix.target_metric}
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
