"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch, getAuthToken } from "@/lib/api";

export default function SettingsPage() {
  const router = useRouter();
  const [defaultClub, setDefaultClub] = useState("7I");
  const [handedness, setHandedness] = useState<"right" | "left">("right");
  const [cameraAngle, setCameraAngle] = useState("DTL");
  const [weights, setWeights] = useState({
    spine_tilt_stability: 0.25,
    head_stability: 0.15,
    path_repeatability: 0.2,
    tempo_consistency: 0.2,
    finish_balance: 0.2,
  });
  const [llmProvider, setLlmProvider] = useState<
    "none" | "gemini" | "openai-compatible"
  >("none");
  const [llmBaseUrl, setLlmBaseUrl] = useState("https://api.openai.com/v1");
  const [llmModel, setLlmModel] = useState("gpt-4o-mini");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [hasSavedKey, setHasSavedKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  useEffect(() => {
    if (!getAuthToken()) {
      router.push("/login");
      return;
    }
    apiFetch<any>("/api/settings")
      .then((s) => {
        setDefaultClub(s.default_club || "7I");
        setHandedness(s.handedness || "right");
        setCameraAngle(s.camera_angle || "DTL");
        if (s.score_weights) {
          setWeights((prev) => ({ ...prev, ...s.score_weights }));
        }
        setLlmProvider(s.llm_provider || "none");
        setLlmBaseUrl(s.llm_base_url || "https://api.openai.com/v1");
        setLlmModel(s.llm_model || "gpt-4o-mini");
        setHasSavedKey(Boolean(s.has_llm_api_key));
      })
      .catch(() => {});
  }, [router]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setBanner(null);
    try {
      const payload: any = {
        default_club: defaultClub,
        handedness,
        camera_angle: cameraAngle,
        score_weights: weights,
        llm_provider: llmProvider,
        llm_base_url: llmBaseUrl,
        llm_model: llmModel,
      };
      if (llmApiKey.trim()) {
        payload.llm_api_key = llmApiKey.trim();
      }
      const res = await apiFetch<any>("/api/settings", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setWeights(res.score_weights);
      setHasSavedKey(Boolean(res.has_llm_api_key));
      setLlmApiKey("");
      setBanner(
        "已儲存個人球桿設定與評分權重（系統已自動正規化權重總和為 100% 並重算所有現有揮桿分數）！"
      );
    } finally {
      setSaving(false);
    }
  };

  const weightMeta: Array<{ key: keyof typeof weights; label: string }> = [
    { key: "spine_tilt_stability", label: "軀幹前傾穩定度 (Spine Tilt, 預設 25%)" },
    { key: "head_stability", label: "頭部相對位移穩定 (Head Stability, 預設 15%)" },
    { key: "path_repeatability", label: "身體與手部軌跡重複性 (Path Repeatability, 預設 20%)" },
    { key: "tempo_consistency", label: "上下桿節奏一致性 (Tempo Consistency, 預設 20%)" },
    { key: "finish_balance", label: "收桿姿勢穩定 (Finish Balance, 預設 20%)" },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">
          個人球桿偏好、評分權重與 AI 教練設定
        </h1>
        <p className="mt-1 text-xs text-gray-400">
          調整 5 項動作子分數權重後，後端會即時重新計算所有歷史場次之 score-v1 分數。API Key 僅保存於伺服器端，絕不回傳至瀏覽器。
        </p>
      </div>

      {banner && (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-950/50 p-4 text-xs text-emerald-200">
          {banner}
        </div>
      )}

      <form
        onSubmit={handleSave}
        className="space-y-6 rounded-2xl border border-gray-800 bg-[#0d141a] p-6"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              預設球桿
            </label>
            <select
              value={defaultClub}
              onChange={(e) => setDefaultClub(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-sm text-white"
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
              onChange={(e) =>
                setHandedness(e.target.value as "right" | "left")
              }
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-sm text-white"
            >
              <option value="right">右打 (Right)</option>
              <option value="left">左打 (Left)</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-300">
              預設拍攝視角
            </label>
            <select
              value={cameraAngle}
              onChange={(e) => setCameraAngle(e.target.value)}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-sm text-white"
            >
              <option value="DTL">後方飛球線 (DTL)</option>
              <option value="Face-On">正面視角 (Face-On)</option>
            </select>
          </div>
        </div>

        {/* 5 子分數權重滑桿 */}
        <div className="space-y-3 border-t border-gray-800 pt-4">
          <h2 className="text-sm font-bold text-white">
            score-v1 動作子分數權重配置 (儲存時自動正規化總和為 100%)
          </h2>
          {weightMeta.map((m) => {
            const rawVal = weights[m.key] || 20;
            const pctVal = rawVal <= 1 ? Math.round(rawVal * 100) : Math.round(rawVal);
            return (
              <div key={m.key} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-300">{m.label}</span>
                  <span className="font-bold text-emerald-400">{pctVal}%</span>
                </div>
                <input
                  type="range"
                  min={5}
                  max={60}
                  step={5}
                  value={pctVal}
                  onChange={(e) =>
                    setWeights((prev) => ({
                      ...prev,
                      [m.key]: parseFloat(e.target.value),
                    }))
                  }
                  className="w-full accent-emerald-500"
                />
              </div>
            );
          })}
        </div>

        {/* 可插拔教練提供者設定 */}
        <div className="space-y-4 border-t border-gray-800 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-white">
              教練摘要與姿勢分析模式
            </h2>
            <span className="rounded-full bg-emerald-950/80 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300 border border-emerald-800/60">
              🔒 離線量化教練模式
            </span>
          </div>

          <div className="rounded-xl border border-emerald-900/40 bg-emerald-950/20 p-3 text-xs leading-relaxed text-emerald-200">
            <p className="font-semibold text-emerald-300">
              ⚡️ 已啟用 100% 本機離線量化姿勢教練 (GSL_ENABLE_EXTERNAL_LLM=false)
            </p>
            <p className="mt-1 text-gray-300">
              系統在您的 Mac 本機即時運算 2D 骨架關節幾何與運動學指標，不需也不會傳輸任何影片或影格至外部大型語言模型（LLM）。預設完全不需 API Key，保障個人揮桿隱私與高速體驗。
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs text-gray-300">
              教練回饋模式
            </label>
            <select
              value={llmProvider}
              onChange={(e) => {
                const val = e.target.value as any;
                setLlmProvider(val);
                if (val === "gemini") {
                  setLlmModel("gemini-3.8-flash");
                }
              }}
              className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-sm text-white"
            >
              <option value="none">
                預設離線量化教練 (none — 100% 本機幾何推算，免外部 API Key，零隱私外洩)
              </option>
              <option value="gemini">
                Google Gemini 3.8 Flash (離線防護開啟時將強制於本機安全降級)
              </option>
              <option value="openai-compatible">
                OpenAI 相容教練 (離線防護開啟時將強制於本機安全降級)
              </option>
            </select>
          </div>

          {llmProvider === "gemini" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-gray-400">
                  Gemini 模型名稱 (預設 gemini-3.8-flash)
                </label>
                <input
                  type="text"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  placeholder="gemini-3.8-flash"
                  className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-xs text-white"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-gray-400">
                  Google Gemini API Key{" "}
                  {hasSavedKey && "(伺服器已綁定金鑰，留空即保留原金鑰)"}
                </label>
                <input
                  type="password"
                  value={llmApiKey}
                  onChange={(e) => setLlmApiKey(e.target.value)}
                  placeholder="AIzaSy..."
                  className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-xs text-white"
                />
              </div>
            </div>
          )}

          {llmProvider === "openai-compatible" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-gray-400">
                  API Base URL
                </label>
                <input
                  type="url"
                  value={llmBaseUrl}
                  onChange={(e) => setLlmBaseUrl(e.target.value)}
                  className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-xs text-white"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-400">
                  模型名稱 (Model)
                </label>
                <input
                  type="text"
                  value={llmModel}
                  onChange={(e) => setLlmModel(e.target.value)}
                  className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-xs text-white"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="mb-1 block text-xs text-gray-400">
                  Server-only API Key{" "}
                  {hasSavedKey && "(伺服器已綁定金鑰，留空即保留原金鑰)"}
                </label>
                <input
                  type="password"
                  value={llmApiKey}
                  onChange={(e) => setLlmApiKey(e.target.value)}
                  placeholder="sk-..."
                  className="w-full rounded-xl border border-gray-700 bg-black/40 px-3 py-2 text-xs text-white"
                />
              </div>
            </div>
          )}
        </div>

        <button
          type="submit"
          disabled={saving}
          className="w-full rounded-xl bg-emerald-600 py-3 text-sm font-bold text-white shadow-lg hover:bg-emerald-500 disabled:opacity-50"
        >
          {saving ? "儲存並重新計算分數中..." : "儲存設定並即時重算場次評分"}
        </button>
      </form>
    </div>
  );
}
