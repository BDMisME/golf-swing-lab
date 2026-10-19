"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, getAuthToken, PracticeSession } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<PracticeSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push("/login");
      return;
    }
    apiFetch<{ items: PracticeSession[] }>("/api/sessions")
      .then((res) => {
        setSessions(res.items || []);
      })
      .catch((err) => {
        if (String(err.message).includes("401")) {
          router.push("/login");
        } else {
          setError(err.message);
        }
      })
      .finally(() => setLoading(false));
  }, [router]);

  const totalSwings = sessions.reduce((acc, s) => acc + (s.swing_count || 0), 0);
  const scoredSessions = sessions.filter(
    (s) => typeof s.average_overall_score === "number"
  );
  const avgScore =
    scoredSessions.length > 0
      ? (
          scoredSessions.reduce(
            (acc, s) => acc + (s.average_overall_score || 0),
            0
          ) / scoredSessions.length
        ).toFixed(1)
      : "N/A";

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 rounded-2xl border border-emerald-900/60 bg-gradient-to-br from-[#0e1b20] to-[#0a1116] p-6 sm:flex-row sm:items-center">
        <div>
          <span className="inline-block rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-300">
            Down-the-Line (DTL) 2D 實測版
          </span>
          <h1 className="mt-2 text-2xl font-bold text-white">
            高爾夫揮桿分析總覽
          </h1>
          <p className="mt-1 text-xs text-gray-400">
            自動從練習場長影片偵測每一球、提取 9 階段事件與 2D 幾何指標，不捏造球速與飛行軌跡。
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/sessions/new"
            className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white shadow-lg transition hover:bg-emerald-500"
          >
            + 新增練習場次與上傳影片
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
          <div className="text-xs text-gray-400">累計練習場次</div>
          <div className="mt-1 text-2xl font-bold text-white">
            {sessions.length} <span className="text-xs font-normal text-gray-400">場</span>
          </div>
        </div>
        <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
          <div className="text-xs text-gray-400">累計切出揮桿球數</div>
          <div className="mt-1 text-2xl font-bold text-emerald-400">
            {totalSwings} <span className="text-xs font-normal text-gray-400">球</span>
          </div>
        </div>
        <div className="rounded-2xl border border-gray-800 bg-[#0d141a] p-4">
          <div className="text-xs text-gray-400">歷史場次平均綜合動作分</div>
          <div className="mt-1 text-2xl font-bold text-amber-400">
            {avgScore}
          </div>
          <div className="mt-0.5 text-[11px] text-gray-500">
            依據 score-v1 (僅統計覆蓋率 ≥ 70% 之有效球)
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-950/40 p-4 text-xs text-red-200">
          載入失敗：{error}
        </div>
      )}

      <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-bold text-white">最近練習場次</h2>
          <Link
            href="/sessions/new"
            className="text-xs font-semibold text-emerald-400 hover:underline"
          >
            上傳新影片 &rarr;
          </Link>
        </div>

        {loading ? (
          <div className="py-12 text-center text-sm text-gray-400">
            載入練習場次資料中...
          </div>
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-gray-800 py-12 text-center">
            <p className="text-sm text-gray-300">目前尚無練習場次紀錄</p>
            <p className="mt-1 text-xs text-gray-500">
              支援 iPhone .MOV / .MP4 (H.264 / HEVC) 大檔分段續傳與背景自動切球
            </p>
            <Link
              href="/sessions/new"
              className="mt-4 inline-block rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500"
            >
              立即建立第一場練習
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-gray-800/80">
            {sessions.map((s) => (
              <div
                key={s.id}
                className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/sessions/${s.id}`}
                      className="text-sm font-bold text-white hover:text-emerald-400"
                    >
                      {s.title}
                    </Link>
                    <span className="rounded bg-emerald-950 px-2 py-0.5 text-[11px] font-medium text-emerald-300 border border-emerald-800/60">
                      {s.club}
                    </span>
                    <span className="rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
                      {s.handedness === "right" ? "右打" : "左打"} · {s.camera_angle}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    練習日期：{s.date} · 影片 {s.video_count} 部 · 偵測 {s.swing_count} 球
                    {s.notes ? ` · ${s.notes}` : ""}
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-[11px] text-gray-400">平均動作分</div>
                    <div className="text-base font-bold text-emerald-400">
                      {typeof (s.average_overall_score ?? (s as any).average_score) ===
                      "number"
                        ? Number(
                            s.average_overall_score ?? (s as any).average_score
                          ).toFixed(1)
                        : "待分析"}
                    </div>
                  </div>
                  <Link
                    href={`/sessions/${s.id}`}
                    className="rounded-xl border border-emerald-600/50 bg-emerald-600/10 px-3.5 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-600 hover:text-white"
                  >
                    檢視時間軸與報告
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
