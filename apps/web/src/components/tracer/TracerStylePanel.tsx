"use client";

import React from "react";
import type {
  RenderRecipeV1,
  TracerAnchorRevision,
  TracerStyleName,
} from "../../lib/tracer/types";

interface TracerStylePanelProps {
  recipe: RenderRecipeV1;
  presets: RenderRecipeV1[];
  anchors: TracerAnchorRevision | null;
  onSelectPreset: (presetId: string) => void;
  onRecipeChange: (updated: RenderRecipeV1) => void;
  onToggleArtisticExtension: (enabled: boolean) => void;
  isBusy: boolean;
}

const STYLE_OPTIONS: TracerStyleName[] = [
  "Clean",
  "Neon",
  "Beam",
  "Gradient",
  "Tail",
  "Pulse",
];

export default function TracerStylePanel({
  recipe,
  presets,
  anchors,
  onSelectPreset,
  onRecipeChange,
  onToggleArtisticExtension,
  isBusy,
}: TracerStylePanelProps) {
  const artisticEnabled = Boolean(
    anchors?.anchors_json?.artistic_extension_enabled
  );

  const updateSwing = (
    patch: Partial<RenderRecipeV1["swing_tracer"]>
  ) => {
    onRecipeChange({
      ...recipe,
      swing_tracer: {
        ...recipe.swing_tracer,
        ...patch,
      },
    });
  };

  const updateShot = (
    patch: Partial<RenderRecipeV1["shot_tracer"]>
  ) => {
    onRecipeChange({
      ...recipe,
      shot_tracer: {
        ...recipe.shot_tracer,
        ...patch,
      },
    });
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-4 space-y-4 text-xs text-slate-200">
      <div>
        <h3 className="text-sm font-bold text-white">
          Flight FX 視覺特效與分色配方
        </h3>
        <p className="text-[11px] text-slate-400">
          Preview 與 Export 共用同一組 RenderRecipeV1 決定論參數
        </p>
      </div>

      {/* 6 組官方預設快速切換 */}
      <div className="space-y-1.5">
        <div className="font-semibold text-slate-300">快速套用預設配方</div>
        <div className="grid grid-cols-3 gap-1.5">
          {presets.map((p) => (
            <button
              key={p.preset_id}
              type="button"
              data-testid={`preset-btn-${p.preset_id}`}
              disabled={isBusy}
              onClick={() => onSelectPreset(p.preset_id)}
              className={`py-1.5 px-2 rounded-xl border text-[11px] font-medium transition ${
                recipe.preset_id === p.preset_id
                  ? "bg-cyan-500/20 border-cyan-400 text-cyan-200"
                  : "bg-slate-950/60 border-slate-800 text-slate-300 hover:bg-slate-800"
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      {/* Swing Tracer 細部控制 */}
      <div className="bg-slate-950/75 border border-slate-800 rounded-xl p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 font-bold text-sky-300 cursor-pointer">
            <input
              type="checkbox"
              data-testid="toggle-swing-tracer"
              checked={recipe.swing_tracer.enabled}
              onChange={(e) => updateSwing({ enabled: e.target.checked })}
              className="accent-sky-400"
            />
            <span>Swing Tracer 揮桿軌跡</span>
          </label>
          <select
            data-testid="select-swing-style"
            value={recipe.swing_tracer.style}
            onChange={(e) =>
              updateSwing({ style: e.target.value as TracerStyleName })
            }
            className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-100"
          >
            {STYLE_OPTIONS.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <label className="space-y-1">
            <span className="text-[10px] text-slate-400">上桿色 (Backswing)</span>
            <input
              type="color"
              value={recipe.swing_tracer.backswing_color_hex}
              onChange={(e) =>
                updateSwing({ backswing_color_hex: e.target.value })
              }
              className="w-full h-7 rounded bg-slate-900 border border-slate-700 cursor-pointer"
            />
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-slate-400">下桿色 (Downswing)</span>
            <input
              type="color"
              value={recipe.swing_tracer.downswing_color_hex}
              onChange={(e) =>
                updateSwing({ downswing_color_hex: e.target.value })
              }
              className="w-full h-7 rounded bg-slate-900 border border-slate-700 cursor-pointer"
            />
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-slate-400">收桿色 (Follow)</span>
            <input
              type="color"
              value={recipe.swing_tracer.follow_through_color_hex}
              onChange={(e) =>
                updateSwing({ follow_through_color_hex: e.target.value })
              }
              className="w-full h-7 rounded bg-slate-900 border border-slate-700 cursor-pointer"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span>線條粗細 (@1080p)</span>
              <span className="font-mono">
                {recipe.swing_tracer.core_width_px_at_1080}px
              </span>
            </div>
            <input
              type="range"
              min={2}
              max={18}
              step={0.5}
              value={recipe.swing_tracer.core_width_px_at_1080}
              onChange={(e) =>
                updateSwing({ core_width_px_at_1080: Number(e.target.value) })
              }
              className="w-full accent-sky-400"
            />
          </label>
          <label className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span>光暈半徑 (@1080p)</span>
              <span className="font-mono">
                {recipe.swing_tracer.glow_radius_px_at_1080}px
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={40}
              step={1}
              value={recipe.swing_tracer.glow_radius_px_at_1080}
              onChange={(e) =>
                updateSwing({ glow_radius_px_at_1080: Number(e.target.value) })
              }
              className="w-full accent-sky-400"
            />
          </label>
        </div>
      </div>

      {/* Shot Tracer 細部控制 */}
      <div className="bg-slate-950/75 border border-slate-800 rounded-xl p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 font-bold text-cyan-300 cursor-pointer">
            <input
              type="checkbox"
              data-testid="toggle-shot-tracer"
              checked={recipe.shot_tracer.enabled}
              onChange={(e) => updateShot({ enabled: e.target.checked })}
              className="accent-cyan-400"
            />
            <span>Shot Tracer 飛球彈道</span>
          </label>
          <select
            data-testid="select-shot-style"
            value={recipe.shot_tracer.style}
            onChange={(e) =>
              updateShot({ style: e.target.value as TracerStyleName })
            }
            className="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-100"
          >
            {STYLE_OPTIONS.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <label className="space-y-1">
            <span className="text-[10px] text-slate-400">主核心色</span>
            <input
              type="color"
              value={recipe.shot_tracer.primary_color_hex}
              onChange={(e) =>
                updateShot({ primary_color_hex: e.target.value })
              }
              className="w-full h-7 rounded bg-slate-900 border border-slate-700 cursor-pointer"
            />
          </label>
          <label className="space-y-1">
            <span className="text-[10px] text-slate-400">漸層尾翼色</span>
            <input
              type="color"
              value={recipe.shot_tracer.secondary_color_hex}
              onChange={(e) =>
                updateShot({ secondary_color_hex: e.target.value })
              }
              className="w-full h-7 rounded bg-slate-900 border border-slate-700 cursor-pointer"
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <label className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span>彈道粗細 (@1080p)</span>
              <span className="font-mono">
                {recipe.shot_tracer.core_width_px_at_1080}px
              </span>
            </div>
            <input
              type="range"
              min={2}
              max={20}
              step={0.5}
              value={recipe.shot_tracer.core_width_px_at_1080}
              onChange={(e) =>
                updateShot({ core_width_px_at_1080: Number(e.target.value) })
              }
              className="w-full accent-cyan-400"
            />
          </label>
          <label className="space-y-1">
            <div className="flex justify-between text-[11px]">
              <span>光暈半徑 (@1080p)</span>
              <span className="font-mono">
                {recipe.shot_tracer.glow_radius_px_at_1080}px
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={48}
              step={1}
              value={recipe.shot_tracer.glow_radius_px_at_1080}
              onChange={(e) =>
                updateShot({ glow_radius_px_at_1080: Number(e.target.value) })
              }
              className="w-full accent-cyan-400"
            />
          </label>
        </div>

        {/* 藝術延伸彈道開關 (強制揭露非實測) */}
        <div className="pt-1 border-t border-slate-800/80">
          <label className="flex items-start gap-2 cursor-pointer">
            <input
              type="checkbox"
              data-testid="toggle-artistic-extension"
              checked={artisticEnabled}
              onChange={(e) => onToggleArtisticExtension(e.target.checked)}
              className="mt-0.5 accent-pink-400"
            />
            <div>
              <div className="font-semibold text-pink-300">
                啟用遠端落點藝術延伸 (ARTISTIC_EXTENSION)
              </div>
              <div className="text-[10px] text-slate-400">
                超出真球可觀測範圍後之延伸弧線將強制標記為{" "}
                <code className="text-pink-300">artistic_only</code>{" "}
                並以虛線繪製，絕不混充實際觀測落點。
              </div>
            </div>
          </label>
        </div>
      </div>
    </div>
  );
}
