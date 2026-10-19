"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE_URL, apiFetch, getAuthToken } from "@/lib/api";

export default function ExportsPage() {
  const router = useRouter();
  const [exportsList, setExportsList] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadExports = useCallback(async () => {
    try {
      const res = await apiFetch<{ items: any[] }>("/api/exports");
      setExportsList(res.items || []);
    } catch (err: any) {
      if (String(err.message).includes("401")) {
        router.push("/login");
      }
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/login");
      return;
    }
    loadExports();
  }, [loadExports, router]);

  useEffect(() => {
    const hasPending = exportsList.some((e) =>
      ["queued", "running"].includes(e.status)
    );
    if (!hasPending) return;
    const timer = setInterval(() => {
      loadExports();
    }, 2500);
    return () => clearInterval(timer);
  }, [exportsList, loadExports]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">
          精選揮桿短片匯出中心
        </h1>
        <p className="mt-1 text-xs text-gray-400">
          檢視單球剪輯與多球 Top Swings 合輯匯出進度（支援原始比例與 9:16 直式社群版 MP4 下載）。
        </p>
      </div>

      <section className="rounded-2xl border border-gray-800 bg-[#0d141a] p-5">
        {loading ? (
          <div className="py-12 text-center text-sm text-gray-400">
            載入匯出任務清單中...
          </div>
        ) : exportsList.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">
            目前尚無匯出紀錄。您可於任一練習場次詳情頁點擊「匯出精選原始比例 MP4」或「匯出 9:16 直式社群短片」。
          </div>
        ) : (
          <div className="divide-y divide-gray-800">
            {exportsList.map((exp) => {
              const st = exp.state || exp.status || "queued";
              return (
                <div
                  key={exp.id}
                  className="flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">
                        {exp.layout === "9:16"
                          ? "9:16 直式社群合輯 (720x1280)"
                          : "原始比例精選短片"}
                      </span>
                      <span className="rounded bg-emerald-950 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
                        共 {exp.segment_ids?.length || 0} 球
                      </span>
                      <span className="text-xs text-gray-400">
                        狀態：{st}
                        {exp.duration_ms
                          ? ` · 時長 ${(exp.duration_ms / 1000).toFixed(1)}s`
                          : ""}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      建立時間：{exp.created_at}
                      {exp.error_message ? ` · 錯誤：${exp.error_message}` : ""}
                    </div>
                  </div>

                  <div>
                    {st === "completed" ? (
                      <a
                        href={`${API_BASE_URL}/api/exports/${exp.id}/download`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-block rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-500"
                      >
                        下載 MP4 短片
                      </a>
                    ) : (
                      <span className="text-xs text-amber-400">
                        FFmpeg 合成處理中...
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
