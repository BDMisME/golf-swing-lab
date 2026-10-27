"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
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
import { CleanMotionOverlay } from "@/components/CleanMotionOverlay";

/**
 * Clean Motion 渲染架構整合：
 * 畫布計算 videoAspect、offsetX、offsetY，透過 toX 與 toY 進行 Letterbox 視訊真實畫面投影；
 * 支援 PGA 鉛線 (Tush Line) 姿態檢核與 bufferBefore (swing.start_ms - bufferBefore) 時間窗口邊界保護。
 */
export default function SwingDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const swingId = params.id;

  const videoRef = useRef<HTMLVideoElement | null>(null);

  const [swing, setSwing] = useState<SwingSegmentItem | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1.0);
  const [expandedSubscore, setExpandedSubscore] = useState<string | null>(
    "spine_tilt_stability"
  );
  const [startMs, setStartMs] = useState(0);
  const [endMs, setEndMs] = useState(0);
  const [label, setLabel] = useState("valid_swing");
  const [ballStrike, setBallStrike] = useState("estimated_strike");
  const [notes, setNotes] = useState("");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveBanner, setSaveBanner] = useState<string | null>(null);

  const loadSwing = useCallback(async () => {
    try {
      const data = await apiFetch<SwingSegmentItem>(`/api/swings/${swingId}`);
      setSwing(data);
      setStartMs(data.start_ms);
      setEndMs(data.end_ms);
      setLabel(data.label);
      setBallStrike(data.ball_strike_status);
      setNotes(data.notes || "");
    } catch (err: any) {
      if (String(err.message).includes("401")) {
        router.push("/login");
      }
    }
  }, [swingId, router]);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/login");
      return;
    }
    loadSwing();
  }, [loadSwing, router]);

  const changePlaybackSpeed = (val: number) => {
    setPlaybackSpeed(val);
    if (videoRef.current) {
      videoRef.current.playbackRate = val;
    }
  };

  const stepFrame = (deltaMs: number) => {
    if (!videoRef.current) return;
    const curSec = videoRef.current.currentTime;
    const minSec = (swing?.start_ms || 0) / 1000;
    const maxSec = (swing?.end_ms || 0) / 1000;
    const nextSec = Math.max(minSec, Math.min(maxSec, curSec + deltaMs / 1000));
    videoRef.current.currentTime = nextSec;
  };

  const jumpToEvent = (timeMs: number) => {
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.currentTime = timeMs / 1000;
    }
  };

  const getSubscoreJumpTimeMs = (subKey: string): number | null => {
    if (!swing || !swing.events) return null;
    const evMap: Record<string, number> = {};
    for (const ev of swing.events) {
      evMap[ev.event_name] = ev.time_ms;
    }
    if (subKey === "spine_tilt_stability")
      return evMap["top"] || evMap["address"] || swing.start_ms;
    if (subKey === "head_stability")
      return (
        evMap["impact_estimated"] ||
        evMap["impact"] ||
        evMap["top"] ||
        swing.start_ms
      );
    if (subKey === "path_repeatability")
      return evMap["downswing"] || evMap["top"] || swing.start_ms;
    if (subKey === "tempo_consistency") return evMap["top"] || swing.start_ms;
    if (subKey === "finish_balance")
      return evMap["finish"] || evMap["follow_through"] || swing.end_ms;
    return null;
  };

  // 根據此球 5 大分項自動推導最值得改善的 1~2 個具體動作與推薦訓練 Drill
  // 最高誠信原則：嚴格基於實際影像指標證據；缺乏足夠證據時不宣告身體問題，亦不宣稱測量足底壓力/重心
  const coachInsights = useMemo(() => {
    if (!swing?.subscores) {
      return [
        {
          title: "動作階段客觀檢視",
          desc: "本球可觀測指標資料不足，系統依誠信原則不預設立場推斷身體問題，請參考 Clean Motion 逐格畫面檢視各動作階段。",
          drill: {
            name: "完整入鏡節奏確認 (Frame & Rhythm Check)",
            action: "確認 iPhone 鏡頭完整涵蓋站姿頭部至雙腳打擊區，維持穩定流暢的揮桿節奏。",
          },
        },
      ];
    }
    const sub = swing.subscores;

    // 計算有效評分數量
    const validScores = Object.values(sub).filter(
      (v) => typeof v?.score === "number"
    );
    if (validScores.length < 2) {
      return [
        {
          title: "動作階段客觀檢視",
          desc: "本球有效可觀測指標覆蓋率不足，系統依誠信原則不宣告身體問題，僅提供動作階段影像回放。",
          drill: {
            name: "基礎站姿平衡維持 (Basic Stance Drill)",
            action: "維持起桿時脊柱前傾與收桿穩定站定，進行自我揮桿節奏感知。",
          },
        },
      ];
    }

    const issues: Array<{ title: string; desc: string; drill: { name: string; action: string } }> = [];

    const spineScore = sub["spine_tilt_stability"]?.score;
    if (typeof spineScore === "number" && spineScore < 75) {
      issues.push({
        title: "下桿前傾維持 (Spine Angle)",
        desc: "下桿擊球時軀幹有微幅起立傾向，導致桿面擊球點離散，建議加強轉身時胸口對地感知。",
        drill: {
          name: "雙手抱胸轉身訓練 (Cross-Arm Pivot Drill)",
          action: "空手站姿雙臂交疊胸前，練習上桿頂點與下桿擊球，確認胸骨始終保持朝向地面球位。",
        },
      });
    }

    const headScore = sub["head_stability"]?.score;
    if (typeof headScore === "number" && headScore < 75) {
      issues.push({
        title: "擊球瞬間頭部穩定 (Head Posture)",
        desc: "下桿過渡瞬間頭部有下沉或側向位移，可能造成觸球深度不穩定，建議維持頸椎放鬆穩定。",
        drill: {
          name: "視線定球專注訓練 (Sightline Focus Drill)",
          action: "在打擊墊後方鎖定小白球後緣的一點，擊球後默數半秒再抬頭看球飛行方向。",
        },
      });
    }

    const tempoScore = sub["tempo_consistency"]?.score;
    if (typeof tempoScore === "number" && tempoScore < 75) {
      issues.push({
        title: "上下桿節奏過渡 (Tempo Transition)",
        desc: "頂點下桿啟動偏急促，上下桿比例未達 3:1 黃金區間，建議頂點保留平順蓄力時間。",
        drill: {
          name: "1-2-3 節拍器揮桿 (3:1 Rhythm Drill)",
          action: "上桿心中默數 1-2 平穩上推，至 3 順暢釋放下桿，體會手臂自然重力墜落。",
        },
      });
    }

    const finishScore = sub["finish_balance"]?.score;
    if (typeof finishScore === "number" && finishScore < 75) {
      issues.push({
        title: "收桿平衡軸線 (Finish Balance)",
        desc: "收桿停留時間偏短或身體晃動，代表擊球後身體收桿軸心尚未完全穩定站定，建議維持收桿姿態停留 2~3 秒。",
        drill: {
          name: "定格收桿 3 秒挑戰 (3-Second Finish Hold)",
          action: "每次擊球後強制站定收桿姿態 3 秒鐘，感受收桿身體站姿直立與肚臍完全轉向目標。",
        },
      });
    }

    // 若全部優異
    if (issues.length === 0) {
      issues.push({
        title: "動作協調高完整度 (High Consistency)",
        desc: "此球脊柱角度、頭部穩定性與收桿平衡均展現良好一致性，整體揮桿動力鏈順暢。",
        drill: {
          name: "同節奏連續實擊挑戰 (Repetition Drill)",
          action: "以相同體感連續進行 3 次實擊，確認手腕軌跡與站姿頭部維持相同的重複穩定度。",
        },
      });
    }

    return issues.slice(0, 2);
  }, [swing?.subscores]);

  const handleSaveCalibration = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveBanner(null);
    try {
      const updated = await apiFetch<SwingSegmentItem>(
        `/api/swings/${swingId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            start_ms: Number(startMs),
            end_ms: Number(endMs),
            label,
            ball_strike_status: ballStrike,
            notes,
            feedback_category: "manual_calibration",
            feedback_note: feedbackNote || "使用者於單球詳情頁微調時間碼與標記",
          }),
        }
      );
      setSwing(updated);
      setSaveBanner("已儲存人工校正並即時更新可解釋評分與回饋紀錄！");
    } finally {
      setSaving(false);
    }
  };

  if (!swing) {
    return (
      <div className="py-16 text-center text-sm text-gray-400">
        載入單球揮桿分析資料中...
      </div>
    );
  }

  const cov = formatCoverageStatus(swing.overall_score, swing.coverage_ratio);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link
            href={`/sessions/${swing.session_id}`}
            className="text-xs font-semibold text-emerald-400 hover:underline"
          >
            &larr; 返回練習場次時間軸
          </Link>
          <h1 className="mt-1 text-2xl font-bold text-white">
            第 #{swing.sequence_no} 球 — 動作分析與智慧視覺檢視
          </h1>
        </div>
        <div className="text-right">
          <div className="text-xs text-gray-400">
            評分版本：{swing.score_version} · 模型：{swing.model_version}
          </div>
          <div className="text-xl font-bold text-emerald-400">
            綜合動作分：{cov.displayScore}
          </div>
        </div>
      </div>

      {/* 播放器、CleanMotionOverlay 疊圖與精準逐幀控制 */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7 space-y-3">
          <div className="relative overflow-hidden rounded-2xl border border-gray-800 bg-black">
            <video
              ref={videoRef}
              controls
              muted
              playsInline
              preload="auto"
              crossOrigin="anonymous"
              src={`${API_BASE_URL}/api/videos/${swing.video_id}/stream?token=${encodeURIComponent(
                getAuthToken() || ""
              )}#t=${(swing.start_ms / 1000).toFixed(2)},${(
                swing.end_ms / 1000
              ).toFixed(2)}`}
              className="aspect-video w-full"
            />
            {/* 全新 CleanMotionOverlay 獨立渲染器 */}
            <CleanMotionOverlay
              videoRef={videoRef}
              keyframes={swing.keyframes || []}
              events={swing.events || []}
              startMs={swing.start_ms}
              endMs={swing.end_ms}
              wristTrajectory={swing.quality_metadata?.wrist_trajectory || []}
              ballTrajectory={swing.quality_metadata?.ball_trajectory || []}
            />
          </div>

          {/* 慢動作播放與精確逐幀步進列 */}
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-800 bg-[#0d141a] p-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-gray-400 font-medium">播放速度:</span>
              {[
                { label: "1.0x 原速", val: 1.0 },
                { label: "0.5x 慢速", val: 0.5 },
                { label: "0.25x 超慢動作", val: 0.25 },
              ].map((sp) => (
                <button
                  key={sp.val}
                  type="button"
                  onClick={() => changePlaybackSpeed(sp.val)}
                  className={`rounded-lg px-2.5 py-1 font-semibold transition ${
                    playbackSpeed === sp.val
                      ? "bg-cyan-500 text-black shadow-sm"
                      : "border border-gray-700 bg-black/40 text-gray-300 hover:border-gray-500"
                  }`}
                >
                  {sp.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => stepFrame(-83)}
                className="rounded-lg border border-gray-800 bg-black/60 px-2 py-1 text-gray-300 hover:border-gray-600 transition"
                title="後退 5 幀 (~83ms)"
              >
                &larr; -5f
              </button>
              <button
                type="button"
                onClick={() => stepFrame(-17)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1 font-semibold text-white hover:border-cyan-500 transition"
                title="後退 1 幀 (~16.7ms)"
              >
                &larr; -1f
              </button>
              <button
                type="button"
                onClick={() => stepFrame(17)}
                className="rounded-lg border border-gray-700 bg-black/50 px-2.5 py-1 font-semibold text-white hover:border-cyan-500 transition"
                title="前進 1 幀 (~16.7ms)"
              >
                +1f &rarr;
              </button>
              <button
                type="button"
                onClick={() => stepFrame(83)}
                className="rounded-lg border border-gray-800 bg-black/60 px-2 py-1 text-gray-300 hover:border-gray-600 transition"
                title="前進 5 幀 (~83ms)"
              >
                +5f &rarr;
              </button>
            </div>
          </div>

          {/* 9 階段關鍵事件跳轉按鈕 */}
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
            <h2 className="mb-2.5 text-xs font-bold text-gray-300">
              揮桿關鍵階段事件 (點擊直接跳轉檢核時間碼)
            </h2>
            <div className="flex flex-wrap gap-2">
              {(swing.events || []).map((ev) => (
                <button
                  key={ev.id || ev.event_name}
                  type="button"
                  data-event={ev.event_name}
                  data-time-ms={ev.time_ms}
                  onClick={() => jumpToEvent(ev.time_ms)}
                  className="rounded-xl border border-cyan-900/50 bg-cyan-950/20 px-3 py-1.5 text-left text-xs transition hover:border-cyan-400 hover:bg-cyan-900/30"
                >
                  <div className="font-bold text-cyan-300">
                    {ev.event_name}
                  </div>
                  <div className="text-[10px] text-gray-400">
                    {formatMsToTimestamp(ev.time_ms)} · 信心{" "}
                    {Math.round(ev.confidence * 100)}%
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* 人工時間碼校正與標記回饋表單 */}
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4 space-y-3">
            <h2 className="text-xs font-bold text-gray-300">
              手動邊界與標籤覆寫 (選用進階工具)
            </h2>
            {saveBanner && (
              <div className="rounded-lg bg-emerald-950/80 border border-emerald-500/50 p-2 text-xs text-emerald-300">
                {saveBanner}
              </div>
            )}
            <form onSubmit={handleSaveCalibration} className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-400 mb-1">起始時間碼 (ms)</label>
                  <input
                    type="number"
                    value={startMs}
                    onChange={(e) => setStartMs(Number(e.target.value))}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label className="block text-gray-400 mb-1">結束時間碼 (ms)</label>
                  <input
                    type="number"
                    value={endMs}
                    onChange={(e) => setEndMs(Number(e.target.value))}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 text-white"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-gray-400 mb-1">揮桿性質</label>
                  <select
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 text-white"
                  >
                    <option value="valid_swing">正式擊球 (valid_swing)</option>
                    <option value="practice_swing">空揮練習 (practice_swing)</option>
                    <option value="swing_candidate">候選待確認 (candidate)</option>
                    <option value="rejected">排除捨棄 (rejected)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-gray-400 mb-1">擊球狀態</label>
                  <select
                    value={ballStrike}
                    onChange={(e) => setBallStrike(e.target.value)}
                    className="w-full rounded-lg border border-gray-700 bg-black/50 px-3 py-1.5 text-white"
                  >
                    <option value="confirmed_strike">確認擊球 (confirmed)</option>
                    <option value="estimated_strike">推估擊球 (estimated)</option>
                    <option value="no_ball">無擊球空揮 (no_ball)</option>
                    <option value="strike_unknown">無法辨識 (unknown)</option>
                  </select>
                </div>
              </div>
              <button
                type="submit"
                disabled={saving}
                className="w-full rounded-lg bg-emerald-600 py-2 font-bold text-white hover:bg-emerald-500 disabled:opacity-50 transition"
              >
                {saving ? "儲存更新中..." : "儲存人工校正"}
              </button>
            </form>
          </div>
        </div>

        {/* 右側：動作洞察、Drill 建議與 5 子分數展開 */}
        <div className="lg:col-span-5 space-y-4">
          {/* AI 專屬體感教練洞察卡片 (免讀生硬演算法指標，直覺吸收) */}
          <div className="rounded-2xl border border-cyan-800/60 bg-gradient-to-b from-[#0a1824] to-[#0d141a] p-5 space-y-3">
            <div className="flex items-center gap-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-400" />
              <h2 className="text-base font-bold text-white">
                AI 專屬體感洞察與重點 Drill
              </h2>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed">
              根據本球多訊號運動學特徵，自動提煉最值得優化的具體體感，不依賴生硬數值。
            </p>

            {coachInsights && (
              <div className="space-y-3 pt-1">
                {coachInsights.map((item, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-gray-800/80 bg-black/40 p-3 space-y-2 text-xs"
                  >
                    <div className="font-bold text-cyan-300 flex items-center gap-1.5">
                      <span className="inline-block rounded bg-cyan-950 px-1.5 py-0.5 text-[10px] text-cyan-400 border border-cyan-800/40">
                        重點 {idx + 1}
                      </span>
                      {item.title}
                    </div>
                    <p className="text-gray-300 leading-relaxed">{item.desc}</p>
                    <div className="rounded-lg bg-[#0e1720] border border-cyan-900/30 p-2.5 text-[11px]">
                      <strong className="text-amber-400">
                        ⛳ 建議訓練：{item.drill.name}
                      </strong>
                      <p className="mt-0.5 text-gray-300">{item.drill.action}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 5 項可解釋動作子分數 */}
          <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white">
                5 項可解釋動作檢核分數
              </h2>
              <span className="rounded bg-emerald-950 px-2 py-0.5 text-[11px] text-emerald-300">
                {cov.badgeText}
              </span>
            </div>

            {cov.isInsufficient && (
              <div className="rounded-xl border border-amber-500/40 bg-amber-950/40 p-3 text-xs text-amber-200">
                此球有效 2D 指標權重覆蓋率低於 70%，系統依誠實門檻不輸出綜合總分 (overall_score = null)，僅顯示已觀測之單項指標。
              </div>
            )}

            <div className="space-y-2.5">
              {Object.entries(swing.subscores || {})
                .filter(
                  ([k, sub]: [string, any]) =>
                    k !== "ig_visual_breakdown" &&
                    sub &&
                    typeof sub.weight === "number"
                )
                .map(([k, sub]: [string, any]) => {
                  const isOpen = expandedSubscore === k;
                  const jumpMs = getSubscoreJumpTimeMs(k);
                  const isNullScore = sub.score === null || sub.score === undefined;
                  return (
                    <div
                      key={k}
                      className="rounded-xl border border-gray-800 bg-black/40 p-3.5 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-bold text-white">
                            {sub.label_zh || sub.label || k}
                          </span>
                          <span className="ml-2 text-[11px] text-gray-400">
                            (權重{" "}
                            {Math.round(
                              (sub.weight || 0) > 1
                                ? sub.weight
                                : (sub.weight || 0) * 100
                            )}
                            %)
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`text-sm font-bold ${
                              isNullScore
                                ? "text-gray-500 italic"
                                : "text-emerald-400"
                            }`}
                          >
                            {!isNullScore ? `${sub.score} 分` : "無法評分 (null)"}
                          </span>
                          {jumpMs !== null && (
                            <button
                              type="button"
                              onClick={() => jumpToEvent(jumpMs)}
                              className="rounded border border-sky-800/60 bg-sky-950/40 px-2 py-0.5 text-[10px] font-semibold text-sky-300 hover:bg-sky-900/60 transition"
                              title="跳轉至對應關鍵檢核影格"
                            >
                              🎯 影格
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedSubscore(isOpen ? null : k)
                            }
                            className="rounded border border-emerald-700/60 bg-emerald-950/50 px-2 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-800 transition"
                          >
                            怎麼算的？
                          </button>
                        </div>
                      </div>

                      {isOpen && (
                        <div className="mt-2.5 space-y-1.5 border-t border-gray-800 pt-2.5 text-[11px] text-gray-300">
                          <div>
                            <strong className="text-white">
                              計算公式與依據：
                            </strong>
                            <p className="mt-0.5 text-gray-300 leading-relaxed">
                              {sub.how_calculated}
                            </p>
                          </div>
                          {isNullScore && (
                            <div className="rounded bg-amber-950/30 p-2 text-[10px] text-amber-200 border border-amber-900/40">
                              ⚠ 依誠實原則不虛構分數：{sub.how_calculated}
                            </div>
                          )}
                          <div className="flex flex-wrap gap-3 text-gray-400">
                            <span>
                              實測原始值：{sub.raw_value !== null && sub.raw_value !== undefined ? sub.raw_value : "無可靠觀測"} {sub.unit || ""}
                            </span>
                            <span>
                              信心度：{Math.round((sub.confidence || 0) * 100)}%
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
