"""
Golf Tracer Studio R4 — Flight FX & Render Recipe Schema (`fx_schema.py`).
定義與前端 Preview、後端 Export 及 `.tracer.json` Sidecar 共用之決定論渲染配方契約 (`RenderRecipeV1`)。
支援：
- 6 種基礎風格 (`Clean`, `Neon`, `Beam`, `Gradient`, `Tail`, `Pulse`)
- 6 組官方預設 (`clean_analysis`, `studio_neon`, `minimal_white`, `power_beam`, `rainbow_arc`, `no_fx`)
- Swing Tracer 與 Shot Tracer 獨立開關、粗細、光暈、分段顏色、虛線預測段與不確定度帶設定
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TracerStyleName(StrEnum):
    CLEAN = "Clean"
    NEON = "Neon"
    BEAM = "Beam"
    GRADIENT = "Gradient"
    TAIL = "Tail"
    PULSE = "Pulse"


class ExportAspectRatio(StrEnum):
    ORIGINAL = "original"
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"


class AudioMode(StrEnum):
    PRESERVE = "preserve"
    MUTE = "mute"


class SwingTracerLayerConfig(BaseModel):
    enabled: bool = True
    style: TracerStyleName = TracerStyleName.NEON
    backswing_color_hex: str = "#38BDF8"      # 亮天藍 (Backswing: Address -> Top)
    downswing_color_hex: str = "#F97316"      # 熾熱橘紅 (Downswing: Top -> Impact)
    follow_through_color_hex: str = "#A855F7" # 電光紫 (Follow-through: Impact -> Finish)
    core_width_px_at_1080: float = Field(default=5.0, ge=1.0, le=28.0)
    glow_radius_px_at_1080: float = Field(default=14.0, ge=0.0, le=64.0)
    glow_intensity: float = Field(default=0.72, ge=0.0, le=1.0)
    opacity: float = Field(default=0.94, ge=0.0, le=1.0)
    tail_decay_ms: int = Field(default=950, ge=100, le=5000)
    show_top_marker: bool = True
    show_impact_marker: bool = True
    show_predicted_dashed: bool = True
    show_uncertainty_band: bool = False


class ShotTracerLayerConfig(BaseModel):
    enabled: bool = True
    style: TracerStyleName = TracerStyleName.BEAM
    primary_color_hex: str = "#22D3EE"        # 青色雷射核心
    secondary_color_hex: str = "#F43F5E"      # 漸層尾端玫紅
    core_width_px_at_1080: float = Field(default=6.5, ge=1.0, le=32.0)
    glow_radius_px_at_1080: float = Field(default=18.0, ge=0.0, le=72.0)
    glow_intensity: float = Field(default=0.82, ge=0.0, le=1.0)
    opacity: float = Field(default=0.96, ge=0.0, le=1.0)
    taper_start_ratio: float = Field(default=0.55, ge=0.1, le=1.0)
    taper_end_ratio: float = Field(default=0.25, ge=0.05, le=1.0)
    tail_decay_ms: int = Field(default=1800, ge=150, le=8000)
    pulse_speed_hz: float = Field(default=3.0, ge=0.5, le=12.0)
    show_apex_marker: bool = True
    show_impact_flash: bool = True
    show_landing_ring: bool = True
    show_predicted_dashed: bool = True
    show_uncertainty_band: bool = False


class ExportFormatConfig(BaseModel):
    aspect_ratio: ExportAspectRatio = ExportAspectRatio.ORIGINAL
    fps: int = Field(default=60, description="支援 30 或 60 CFR")
    audio_mode: AudioMode = AudioMode.PRESERVE
    crf: int = Field(default=18, ge=10, le=30)
    show_provenance_watermark: bool = False


class RenderRecipeV1(BaseModel):
    """Studio 渲染配方 v1 完整結構。"""

    recipe_version: int = 1
    preset_id: str = "studio_neon"
    name: str = "Studio Neon"
    swing_tracer: SwingTracerLayerConfig = Field(default_factory=SwingTracerLayerConfig)
    shot_tracer: ShotTracerLayerConfig = Field(default_factory=ShotTracerLayerConfig)
    export_format: ExportFormatConfig = Field(default_factory=ExportFormatConfig)


BUILTIN_RENDER_PRESETS: dict[str, RenderRecipeV1] = {
    "clean_analysis": RenderRecipeV1(
        preset_id="clean_analysis",
        name="Clean 工程檢視",
        swing_tracer=SwingTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.CLEAN,
            backswing_color_hex="#0EA5E9",
            downswing_color_hex="#EA580C",
            follow_through_color_hex="#10B981",
            core_width_px_at_1080=4.0,
            glow_radius_px_at_1080=0.0,
            glow_intensity=0.0,
            opacity=0.95,
            show_predicted_dashed=True,
            show_uncertainty_band=True,
        ),
        shot_tracer=ShotTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.CLEAN,
            primary_color_hex="#FACC15",
            secondary_color_hex="#F97316",
            core_width_px_at_1080=5.0,
            glow_radius_px_at_1080=0.0,
            glow_intensity=0.0,
            opacity=0.95,
            show_predicted_dashed=True,
            show_uncertainty_band=True,
        ),
    ),
    "studio_neon": RenderRecipeV1(
        preset_id="studio_neon",
        name="Studio 霓虹雙軌",
        swing_tracer=SwingTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.NEON,
            backswing_color_hex="#38BDF8",
            downswing_color_hex="#F97316",
            follow_through_color_hex="#A855F7",
            core_width_px_at_1080=5.5,
            glow_radius_px_at_1080=16.0,
            glow_intensity=0.78,
        ),
        shot_tracer=ShotTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.NEON,
            primary_color_hex="#22D3EE",
            secondary_color_hex="#EC4899",
            core_width_px_at_1080=6.5,
            glow_radius_px_at_1080=20.0,
            glow_intensity=0.85,
        ),
    ),
    "minimal_white": RenderRecipeV1(
        preset_id="minimal_white",
        name="Minimal 極簡純白",
        swing_tracer=SwingTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.TAIL,
            backswing_color_hex="#E2E8F0",
            downswing_color_hex="#FFFFFF",
            follow_through_color_hex="#94A3B8",
            core_width_px_at_1080=4.5,
            glow_radius_px_at_1080=8.0,
            glow_intensity=0.40,
            tail_decay_ms=650,
        ),
        shot_tracer=ShotTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.TAIL,
            primary_color_hex="#FFFFFF",
            secondary_color_hex="#CBD5E1",
            core_width_px_at_1080=5.5,
            glow_radius_px_at_1080=10.0,
            glow_intensity=0.45,
            tail_decay_ms=1100,
        ),
    ),
    "power_beam": RenderRecipeV1(
        preset_id="power_beam",
        name="Power 高能光束",
        swing_tracer=SwingTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.BEAM,
            backswing_color_hex="#60A5FA",
            downswing_color_hex="#EF4444",
            follow_through_color_hex="#F59E0B",
            core_width_px_at_1080=6.5,
            glow_radius_px_at_1080=22.0,
            glow_intensity=0.88,
        ),
        shot_tracer=ShotTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.BEAM,
            primary_color_hex="#EF4444",
            secondary_color_hex="#FBBF24",
            core_width_px_at_1080=8.0,
            glow_radius_px_at_1080=26.0,
            glow_intensity=0.92,
        ),
    ),
    "rainbow_arc": RenderRecipeV1(
        preset_id="rainbow_arc",
        name="Gradient 漸層電弧",
        swing_tracer=SwingTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.GRADIENT,
            backswing_color_hex="#06B6D4",
            downswing_color_hex="#F43F5E",
            follow_through_color_hex="#8B5CF6",
            core_width_px_at_1080=5.5,
            glow_radius_px_at_1080=14.0,
            glow_intensity=0.70,
        ),
        shot_tracer=ShotTracerLayerConfig(
            enabled=True,
            style=TracerStyleName.PULSE,
            primary_color_hex="#10B981",
            secondary_color_hex="#3B82F6",
            core_width_px_at_1080=6.5,
            glow_radius_px_at_1080=18.0,
            glow_intensity=0.80,
            pulse_speed_hz=3.5,
        ),
    ),
    "no_fx": RenderRecipeV1(
        preset_id="no_fx",
        name="關閉特效 (原片對照)",
        swing_tracer=SwingTracerLayerConfig(enabled=False),
        shot_tracer=ShotTracerLayerConfig(enabled=False),
    ),
}


def get_preset_recipe(preset_id: str) -> RenderRecipeV1:
    preset = BUILTIN_RENDER_PRESETS.get(preset_id)
    if preset is None:
        return BUILTIN_RENDER_PRESETS["studio_neon"].model_copy(deep=True)
    return preset.model_copy(deep=True)


def parse_hex_to_bgr(color_hex: str) -> tuple[int, int, int]:
    """將 `#RRGGBB` 轉換為 OpenCV `(B, G, R)` 整數元組。"""
    clean = color_hex.strip().lstrip("#")
    if len(clean) == 3:
        clean = "".join(c * 2 for c in clean)
    if len(clean) != 6:
        return (255, 200, 50)
    try:
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
        return (b, g, r)
    except ValueError:
        return (255, 200, 50)


def blend_bgr(
    bgr1: tuple[int, int, int],
    bgr2: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    alpha = max(0.0, min(1.0, float(t)))
    return (
        int(round((1.0 - alpha) * bgr1[0] + alpha * bgr2[0])),
        int(round((1.0 - alpha) * bgr1[1] + alpha * bgr2[1])),
        int(round((1.0 - alpha) * bgr1[2] + alpha * bgr2[2])),
    )
