"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, setAuthToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("golfer@swinglab.local");
  const [password, setPassword] = useState("GolfSwingLab!2026");
  const [displayName, setDisplayName] = useState("高爾夫球友");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const endpoint =
        mode === "login" ? "/api/auth/login" : "/api/auth/register";
      const body =
        mode === "login"
          ? { email, password }
          : { email, password, display_name: displayName };
      const data = await apiFetch<{
        access_token: string;
        user: { id: string; email: string; display_name: string };
      }>(endpoint, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setAuthToken(data.access_token, data.user);
      router.push("/");
    } catch (err: any) {
      setError(err.message || "登入失敗，請檢查帳號密碼");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto mt-10 max-w-md rounded-2xl border border-emerald-900/50 bg-[#0d151b] p-6 shadow-2xl">
      <div className="mb-6 text-center">
        <h1 className="text-2xl font-bold text-white">
          {mode === "login" ? "登入 Golf Swing Lab" : "註冊新球友帳號"}
        </h1>
        <p className="mt-1 text-xs text-gray-400">
          個人練習場長影片自動切球、2D 骨架追蹤與可解釋評分平台
        </p>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-2 rounded-xl bg-black/40 p-1">
        <button
          type="button"
          onClick={() => setMode("login")}
          className={`rounded-lg py-2 text-xs font-semibold transition ${
            mode === "login"
              ? "bg-emerald-600 text-white"
              : "text-gray-400 hover:text-white"
          }`}
        >
          帳號登入
        </button>
        <button
          type="button"
          onClick={() => setMode("register")}
          className={`rounded-lg py-2 text-xs font-semibold transition ${
            mode === "register"
              ? "bg-emerald-600 text-white"
              : "text-gray-400 hover:text-white"
          }`}
        >
          註冊新帳號
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-xl border border-red-500/40 bg-red-950/50 px-3 py-2.5 text-xs text-red-200"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === "register" && (
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              球友暱稱
            </label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
            />
          </div>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-300">
            電子信箱 (Email)
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-300">
            密碼
          </label>
          <input
            type="password"
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-xl border border-gray-700 bg-black/40 px-3.5 py-2.5 text-sm text-white focus:border-emerald-500 focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-xl bg-emerald-600 py-3 text-sm font-bold text-white shadow-lg transition hover:bg-emerald-500 disabled:opacity-50"
        >
          {loading
            ? "處理中..."
            : mode === "login"
              ? "進入分析實驗室"
              : "建立球友帳號"}
        </button>
      </form>

      <div className="mt-4 rounded-xl border border-emerald-900/40 bg-emerald-950/20 p-3 text-[11px] text-gray-400">
        預設本機體驗帳號：<code className="text-emerald-300">golfer@golfswinglab.local</code> / 密碼：<code className="text-emerald-300">GolfSwingLab2026!</code>
      </div>
    </div>
  );
}
