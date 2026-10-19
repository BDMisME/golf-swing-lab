"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE_URL, apiFetch, computeChunkPlan, getAuthToken } from "@/lib/api";

interface UploadFileState {
  file: File;
  progress: number;
  status: "pending" | "uploading" | "completed" | "error";
  videoId?: string;
  jobId?: string;
  error?: string;
}

export default function NewSessionPage() {
  const router = useRouter();
  const [title, setTitle] = useState("夜間練習場 7 號鐵定點訓練");
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [club, setClub] = useState("7I");
  const [handedness, setHandedness] = useState<"right" | "left">("right");
  const [cameraAngle, setCameraAngle] = useState("DTL");
  const [notes, setNotes] = useState("後方飛球線 DTL 固定腳架拍攝");
  const [files, setFiles] = useState<UploadFileState[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    const selected = Array.from(e.target.files).map((f) => ({
      file: f,
      progress: 0,
      status: "pending" as const,
    }));
    setFiles(selected);
  };

  const uploadSingleFile = async (
    sessionId: string,
    item: UploadFileState,
    index: number
  ): Promise<string> => {
    const f = item.file;
    const partSize = 8 * 1024 * 1024;
    const idemKey = `web-${sessionId}-${f.name}-${f.size}-${f.lastModified}`;

    setFiles((prev) =>
      prev.map((p, idx) =>
        idx === index ? { ...p, status: "uploading", progress: 5 } : p
      )
    );

    const initRes = await apiFetch<{
      upload_id: string;
      video_id: string;
      part_size_bytes: number;
      uploaded_parts: Array<{ part_number: number; etag: string }>;
    }>("/api/uploads/initiate", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        filename: f.name,
        mime_type: f.type || "video/mp4",
        size_bytes: f.size,
        part_size_bytes: partSize,
        idempotency_key: idemKey,
      }),
    });

    const existingMap = new Map<number, string>();
    for (const up of initRes.uploaded_parts || []) {
      existingMap.set(up.part_number, up.etag);
    }

    const chunks = computeChunkPlan(f.size, initRes.part_size_bytes);
    const completedParts: Array<{ part_number: number; etag: string }> = [];
    const token = getAuthToken();

    for (let i = 0; i < chunks.length; i++) {
      const c = chunks[i];
      if (existingMap.has(c.partNumber)) {
        completedParts.push({
          part_number: c.partNumber,
          etag: existingMap.get(c.partNumber)!,
        });
      } else {
        const blob = f.slice(c.start, c.end);
        const putRes = await fetch(
          `${API_BASE_URL}/api/uploads/${initRes.upload_id}/parts/${c.partNumber}/content`,
          {
            method: "PUT",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: blob,
            credentials: "include",
          }
        );
        if (!putRes.ok) {
          const errData = await putRes.json().catch(() => ({}));
          throw new Error(errData.message || `分段 #${c.partNumber} 上傳失敗`);
        }
        const putJson = await putRes.json();
        completedParts.push({
          part_number: c.partNumber,
          etag: putJson.etag,
        });
      }

      const pct = Math.min(90, Math.round(((i + 1) / chunks.length) * 85));
      setFiles((prev) =>
        prev.map((p, idx) => (idx === index ? { ...p, progress: pct } : p))
      );
    }

    await apiFetch(`/api/uploads/${initRes.upload_id}/complete`, {
      method: "POST",
      body: JSON.stringify({ parts: completedParts }),
    });

    const jobRes = await apiFetch<{ job_id: string }>(
      `/api/videos/${initRes.video_id}/analyze`,
      { method: "POST" }
    );

    setFiles((prev) =>
      prev.map((p, idx) =>
        idx === index
          ? {
              ...p,
              status: "completed",
              progress: 100,
              videoId: initRes.video_id,
              jobId: jobRes.job_id,
            }
          : p
      )
    );

    return initRes.video_id;
  };

  const handleStartSession = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setGlobalError(null);

    try {
      const session = await apiFetch<{ id: string }>("/api/sessions", {
        method: "POST",
        body: JSON.stringify({
          title,
          date,
          club,
          handedness,
          camera_angle: cameraAngle,
          notes,
        }),
      });

      for (let i = 0; i < files.length; i++) {
        await uploadSingleFile(session.id, files[i], i);
      }

      router.push(`/sessions/${session.id}`);
    } catch (err: any) {
      setGlobalError(err.message || "建立場次或上傳影片失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">
          新增練習場次與長影片上傳
        </h1>
        <p className="mt-1 text-xs text-gray-400">
          支援 iPhone 拍攝之 .MOV / .MP4 (H.264 / HEVC)、分段可續傳上傳與自動觸發背景切球分析。
        </p>
      </div>

      {globalError && (
        <div
          role="alert"
          className="rounded-xl border border-red-500/40 bg-red-950/50 p-4 text-xs text-red-200"
        >
          {globalError}
        </div>
      )}

      <form
        onSubmit={handleStartSession}
        className="space-y-5 rounded-2xl border border-gray-800 bg-[#0d141a] p-6"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              場次標題
            </label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              練習日期
            </label>
            <input
              type="date"
              required
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              使用球桿
            </label>
            <select
              value={club}
              onChange={(e) => setClub(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="7I">7 號鐵桿 (7I)</option>
              <option value="Driver">1 號木桿 (Driver)</option>
              <option value="PW">劈起桿 (PW)</option>
              <option value="5I">5 號鐵桿 (5I)</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              慣用手
            </label>
            <select
              value={handedness}
              onChange={(e) => setHandedness(e.target.value as "right" | "left")}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="right">右手擊球 (Right)</option>
              <option value="left">左手擊球 (Left)</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              拍攝視角
            </label>
            <select
              value={cameraAngle}
              onChange={(e) => setCameraAngle(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            >
              <option value="DTL">後方飛球線 (DTL - 推薦主視角)</option>
              <option value="Face-On">正面視角 (Face-On - 實驗性)</option>
            </select>
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-300">
            練習備註
          </label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <div className="rounded-xl border border-dashed border-emerald-700/60 bg-emerald-950/10 p-5">
          <label className="block cursor-pointer text-center">
            <span className="text-sm font-semibold text-emerald-300">
              選擇練習場影片檔案（支援多選 .MOV / .MP4）
            </span>
            <p className="mt-1 text-xs text-gray-400">
              自動依 8MB 分段續傳，網路瞬斷可憑 Idempotency Key 續傳已完成區段
            </p>
            <input
              type="file"
              multiple
              accept=".mp4,.mov,.m4v,video/mp4,video/quicktime"
              onChange={handleFileChange}
              className="mt-3 block w-full text-xs text-gray-300 file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-600 file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-white hover:file:bg-emerald-500"
            />
          </label>

          {files.length > 0 && (
            <div className="mt-4 space-y-2">
              {files.map((item, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-gray-800 bg-black/50 p-3 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-white">
                      {item.file.name} ({(item.file.size / (1024 * 1024)).toFixed(2)} MB)
                    </span>
                    <span className="text-emerald-400">
                      {item.status === "pending" && "準備上傳"}
                      {item.status === "uploading" && `上傳中 ${item.progress}%`}
                      {item.status === "completed" && "已完成並排入分析"}
                      {item.status === "error" && "上傳失敗"}
                    </span>
                  </div>
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
                    <div
                      className="h-full bg-emerald-500 transition-all"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-xl bg-emerald-600 py-3 text-sm font-bold text-white shadow-lg transition hover:bg-emerald-500 disabled:opacity-50"
        >
          {submitting
            ? "分段上傳與建立分析工作佇列中..."
            : files.length > 0
              ? `建立場次並上傳 ${files.length} 部影片`
              : "先建立空白練習場次"}
        </button>
      </form>
    </div>
  );
}
