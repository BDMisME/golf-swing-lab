"""
Golf Tracer Studio R4 — Core Analysis, Tracking, Rendering & Export Package (`packages/analysis/tracer`).
"""

from packages.analysis.tracer.artifact_cache import (
    deserialize_track_points_gzip_jsonl,
    load_track_revision_artifact,
    save_track_revision_artifact,
    serialize_track_points_gzip_jsonl,
)
from packages.analysis.tracer.camera_motion import CameraMotionEstimate, CameraMotionTracker
from packages.analysis.tracer.clubhead_detector import ClubDetectionResult, ClubheadDetector, detect_compute_device
from packages.analysis.tracer.compositor import (
    ParityCheckReport,
    compose_output_frame,
    verify_preview_export_parity,
)
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    OcclusionState,
    PositionRole,
    RawObservationEvidence,
    ShotTrackMode,
    SwingPhase,
    SwingTrackStatus,
    TrackQualitySummary,
    TrackSourceType,
    TrackType,
    validate_track_point_invariants,
)
from packages.analysis.tracer.edit_merge import (
    ManualPointEditOp,
    StudioAnchorOverrides,
    apply_manual_edits_copy_on_write,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader, DecodedUprightFrame
from packages.analysis.tracer.fx_renderer import (
    project_track_point_to_output_px,
    render_tracer_layers_onto_bgr,
)
from packages.analysis.tracer.fx_schema import (
    BUILTIN_RENDER_PRESETS,
    AudioMode,
    ExportAspectRatio,
    ExportFormatConfig,
    RenderRecipeV1,
    ShotTracerLayerConfig,
    SwingTracerLayerConfig,
    TracerStyleName,
    get_preset_recipe,
)
from packages.analysis.tracer.interpolation import (
    catmull_rom_subdivide,
    generate_artistic_ballistic_extension,
    interpolate_pts_gap,
)
from packages.analysis.tracer.media_clock import (
    FrameClockEntry,
    MediaClockTimeline,
    build_rational_cfr_timeline,
    compute_local_time_us,
    extract_clip_pts_timeline,
    generate_cfr_output_pts_us,
)
from packages.analysis.tracer.reliability import recompute_track_quality_summary
from packages.analysis.tracer.roi_planner import PlannedROI, is_view_comparable, plan_ball_flight_roi, plan_club_roi
from packages.analysis.tracer.segment_context import (
    ResolvedSegmentContext,
    SourceUnavailableError,
    classify_swing_phase_at_pts,
    resolve_segment_context,
)
from packages.analysis.tracer.shaft_geometry import ShaftEndpointEstimate, ShaftGeometryEstimator
from packages.analysis.tracer.shot_detector import BallDetectionCandidate, ShotBallDetector
from packages.analysis.tracer.shot_tracker import (
    ShotTraceResult,
    ShotTracerEngine,
    validate_ball_launch_physics,
)
from packages.analysis.tracer.studio_exporter import (
    ClipExportSpec,
    StudioExportArtifact,
    export_batch_tracer_compilation,
    export_single_tracer_clip,
)
from packages.analysis.tracer.swing_tracker import PTSKalman2D, SwingTraceResult, SwingTracerEngine
from packages.analysis.tracer.transforms import (
    FrameGeometry,
    OutputLayout,
    canvas_click_to_upright_norm,
    coded_px_to_upright_norm,
    compute_output_layout,
    project_upright_norm_to_output_px,
    roi_px_to_upright_norm,
    rotate_coded_frame_to_upright,
    scale_width_at_1080,
    unproject_output_px_to_upright_norm,
    upright_norm_to_coded_px,
)

__all__ = [
    "AudioMode",
    "BUILTIN_RENDER_PRESETS",
    "BallDetectionCandidate",
    "BoundedFrameReader",
    "CameraMotionEstimate",
    "CameraMotionTracker",
    "CanonicalTrackPoint",
    "ClipExportSpec",
    "ClubDetectionResult",
    "ClubheadDetector",
    "DecodedUprightFrame",
    "ExportAspectRatio",
    "ExportFormatConfig",
    "FrameClockEntry",
    "FrameGeometry",
    "ManualPointEditOp",
    "MediaClockTimeline",
    "OcclusionState",
    "OutputLayout",
    "PTSKalman2D",
    "ParityCheckReport",
    "PlannedROI",
    "PositionRole",
    "RawObservationEvidence",
    "RenderRecipeV1",
    "ResolvedSegmentContext",
    "ShaftEndpointEstimate",
    "ShaftGeometryEstimator",
    "ShotBallDetector",
    "ShotTraceResult",
    "ShotTracerEngine",
    "ShotTracerLayerConfig",
    "ShotTrackMode",
    "SourceUnavailableError",
    "StudioAnchorOverrides",
    "StudioExportArtifact",
    "SwingPhase",
    "SwingTraceResult",
    "SwingTracerEngine",
    "SwingTracerLayerConfig",
    "SwingTrackStatus",
    "TracerStyleName",
    "TrackQualitySummary",
    "TrackSourceType",
    "TrackType",
    "apply_manual_edits_copy_on_write",
    "build_rational_cfr_timeline",
    "canvas_click_to_upright_norm",
    "catmull_rom_subdivide",
    "classify_swing_phase_at_pts",
    "coded_px_to_upright_norm",
    "compose_output_frame",
    "compute_local_time_us",
    "compute_output_layout",
    "deserialize_track_points_gzip_jsonl",
    "detect_compute_device",
    "export_batch_tracer_compilation",
    "export_single_tracer_clip",
    "extract_clip_pts_timeline",
    "generate_artistic_ballistic_extension",
    "generate_cfr_output_pts_us",
    "get_preset_recipe",
    "interpolate_pts_gap",
    "is_view_comparable",
    "load_track_revision_artifact",
    "plan_ball_flight_roi",
    "plan_club_roi",
    "project_track_point_to_output_px",
    "project_upright_norm_to_output_px",
    "recompute_track_quality_summary",
    "render_tracer_layers_onto_bgr",
    "resolve_segment_context",
    "roi_px_to_upright_norm",
    "rotate_coded_frame_to_upright",
    "save_track_revision_artifact",
    "scale_width_at_1080",
    "serialize_track_points_gzip_jsonl",
    "unproject_output_px_to_upright_norm",
    "upright_norm_to_coded_px",
    "validate_ball_launch_physics",
    "validate_track_point_invariants",
    "verify_preview_export_parity",
]
