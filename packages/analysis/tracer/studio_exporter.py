"""
Golf Tracer Studio R4 — Deterministic Frame-Accurate Exporter & Batch Compiler (`studio_exporter.py`).
負責：
1. 單球特效影片匯出 (`export_single_tracer_clip`)：
   - 支援 `original`, `16:9`, `9:16` 比例 × `30`, `60` CFR × 音訊 `preserve`, `mute`
   - 採用 `generate_cfr_output_pts_us` 產生嚴格有理數時間格點 (`30/1` 或 `60/1`)
   - 每幀呼叫 `compose_output_frame` 合成，確保與前端 Canvas 預覽誤差 `<= 2.0 px` (@1080p) 且時間差 `<= 1 frame`
   - 輸出 QuickTime / Safari / WebKit 100% 相容之 H.264 (`libx264`, `yuv420p`, `+faststart`) MP4
   - 同步產出 `.tracer.json` 證據與溯源 Sidecar 檔案
2. 多球合輯匯出 (`export_batch_tracer_compilation`, 1–10 球)：
   - 自動統一解析度、幀率與音訊軌道（若開啟 `preserve` 且部分片段無音軌，自動補齊靜音 AAC 音軌），無縫串接為單一合輯 MP4。
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from packages.analysis.probe import probe_video_file
from packages.analysis.tracer.compositor import (
    ParityCheckReport,
    compose_output_frame,
    verify_preview_export_parity,
)
from packages.analysis.tracer.contracts import (
    CanonicalTrackPoint,
    TrackQualitySummary,
)
from packages.analysis.tracer.frame_reader import BoundedFrameReader, DecodedUprightFrame
from packages.analysis.tracer.fx_schema import (
    AudioMode,
    RenderRecipeV1,
)
from packages.analysis.tracer.media_clock import generate_cfr_output_pts_us
from packages.analysis.tracer.transforms import (
    FrameGeometry,
    OutputLayout,
    compute_output_layout,
)

logger = logging.getLogger(__name__)


@dataclass
class ClipExportSpec:
    """單一片段匯出輸入規格。"""

    project_id: str
    segment_id: str
    source_video_id: str
    source_video_path: Path
    source_video_sha256: str | None
    geometry: FrameGeometry
    start_pts_us: int
    end_pts_us: int
    top_pts_us: int | None
    impact_pts_us: int | None
    swing_points: list[CanonicalTrackPoint]
    shot_points: list[CanonicalTrackPoint]
    swing_quality: TrackQualitySummary
    shot_quality: TrackQualitySummary
    recipe: RenderRecipeV1
    has_audio_stream: bool = True


@dataclass
class StudioExportArtifact:
    """匯出完成之影片與 Sidecar 實證結構。"""

    output_mp4_path: Path
    sidecar_json_path: Path
    mp4_sha256: str
    sidecar_sha256: str
    mp4_size_bytes: int
    output_width: int
    output_height: int
    fps: int
    aspect_ratio: str
    audio_mode: str
    has_audio_in_output: bool
    duration_ms: int
    frame_count: int
    parity_report: ParityCheckReport
    sidecar_payload: dict[str, Any]


def _check_source_has_audio(video_path: Path) -> bool:
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
        return "audio" in (res.stdout or "").lower()
    except Exception:
        return False


def _compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def export_single_tracer_clip(
    spec: ClipExportSpec,
    output_mp4_path: str | Path,
    sidecar_json_path: str | Path | None = None,
    allow_low_res_test: bool = False,
) -> StudioExportArtifact:
    """
    將單一 `ClipExportSpec` 渲染為帶雙軌特效之 H.264 MP4 與 `.tracer.json` 溯源檔案。
    """
    out_mp4 = Path(output_mp4_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_sidecar = (
        Path(sidecar_json_path)
        if sidecar_json_path is not None
        else out_mp4.with_suffix(".tracer.json")
    )

    fps = 30 if int(spec.recipe.export_format.fps) == 30 else 60
    aspect_str = spec.recipe.export_format.aspect_ratio.value
    audio_mode_str = spec.recipe.export_format.audio_mode.value

    layout: OutputLayout = compute_output_layout(
        geometry=spec.geometry,
        target_aspect=aspect_str,
    )

    reader = BoundedFrameReader(
        source_path=spec.source_video_path,
        geometry=spec.geometry,
        require_high_res=not allow_low_res_test,
    )
    all_track_pts = spec.swing_points + spec.shot_points
    reader_start_us = min([spec.start_pts_us] + [p.source_pts_us for p in all_track_pts])
    reader_end_us = max([spec.end_pts_us] + [p.source_pts_us for p in all_track_pts])

    decoded_frames: list[DecodedUprightFrame] = list(
        reader.iter_frames(start_pts_us=reader_start_us, end_pts_us=reader_end_us)
    )
    if not decoded_frames:
        raise RuntimeError(
            f"無法從原片解碼區間 [{spec.start_pts_us}, {spec.end_pts_us}] us 之任何影格: {spec.source_video_path}"
        )

    actual_start_us = min(reader_start_us, decoded_frames[0].source_pts_us)
    actual_end_us = max(reader_end_us, decoded_frames[-1].source_pts_us)
    if actual_end_us <= actual_start_us:
        actual_end_us = actual_start_us + int(round(1_000_000.0 / fps))

    output_pts_grid = generate_cfr_output_pts_us(
        clip_start_pts_us=actual_start_us,
        clip_end_pts_us=actual_end_us,
        target_fps=fps,
    )

    # 先將已旋轉之原片渲染至暫存無聲視訊檔，再依 audio_mode 合成音軌
    with tempfile.TemporaryDirectory(prefix="gsl_tracer_exp_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        video_only_mp4 = tmp_dir / "video_rendered.mp4"

        encode_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-vcodec",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{layout.output_width}x{layout.output_height}",
            "-r",
            f"{fps}/1",
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            str(int(spec.recipe.export_format.crf)),
            "-pix_fmt",
            "yuv420p",
            "-r",
            f"{fps}/1",
            "-fps_mode",
            "cfr",
            "-movflags",
            "+faststart",
            str(video_only_mp4),
        ]

        proc = subprocess.Popen(
            encode_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None

        # 建立快速最近鄰影格索引
        frame_pts_arr = [f.source_pts_us for f in decoded_frames]
        cursor = 0
        n_decoded = len(decoded_frames)

        try:
            for out_pts in output_pts_grid:
                while (
                    cursor + 1 < n_decoded
                    and abs(frame_pts_arr[cursor + 1] - out_pts) <= abs(frame_pts_arr[cursor] - out_pts)
                ):
                    cursor += 1
                src_frame = decoded_frames[cursor]
                # 使用真實輸出格點時間與原片影格 PTS 之較大者確保軌跡隨畫面推進
                render_pts_us = max(out_pts, src_frame.source_pts_us)
                composed = compose_output_frame(
                    upright_bgr=src_frame.image_bgr,
                    layout=layout,
                    current_pts_us=render_pts_us,
                    recipe=spec.recipe,
                    swing_points=spec.swing_points,
                    shot_points=spec.shot_points,
                    top_pts_us=spec.top_pts_us,
                    impact_pts_us=spec.impact_pts_us,
                )
                proc.stdin.write(composed.tobytes())
        finally:
            proc.stdin.close()

        stderr_bytes = proc.stderr.read() if proc.stderr else b""
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        proc.wait(timeout=180)
        if proc.returncode != 0 or not video_only_mp4.exists():
            err_msg = stderr_bytes.decode("utf-8", errors="replace")[-800:]
            raise RuntimeError(f"FFmpeg 視訊渲染失敗 (exit={proc.returncode}): {err_msg}")

        source_has_audio = spec.has_audio_stream and _check_source_has_audio(spec.source_video_path)
        has_audio_in_output = False

        if audio_mode_str == AudioMode.PRESERVE.value and source_has_audio:
            start_sec = max(0.0, actual_start_us / 1_000_000.0)
            dur_sec = max(0.1, (actual_end_us - actual_start_us) / 1_000_000.0)
            mux_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_only_mp4),
                "-ss",
                f"{start_sec:.6f}",
                "-t",
                f"{dur_sec:.6f}",
                "-i",
                str(spec.source_video_path),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0?",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-shortest",
                "-movflags",
                "+faststart",
                str(out_mp4),
            ]
            mux_res = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=60, check=False)
            if mux_res.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 1024:
                has_audio_in_output = _check_source_has_audio(out_mp4)
            else:
                shutil.copy2(video_only_mp4, out_mp4)
        else:
            shutil.copy2(video_only_mp4, out_mp4)

    # 驗證輸出 MP4 與計算 Preview/Export Parity
    probe_meta = probe_video_file(out_mp4)
    all_pts = sorted(spec.swing_points + spec.shot_points, key=lambda p: p.source_pts_us)
    parity = verify_preview_export_parity(
        points=all_pts,
        layout=layout,
        fps=fps,
        export_output_pts_us=output_pts_grid,
    )

    mp4_sha256 = _compute_file_sha256(out_mp4)
    mp4_size = out_mp4.stat().st_size

    sidecar_payload: dict[str, Any] = {
        "schema_version": "r4_tracer_sidecar_v1",
        "project_id": spec.project_id,
        "segment_id": spec.segment_id,
        "source_video_id": spec.source_video_id,
        "source_video_sha256": spec.source_video_sha256,
        "clip_range_pts_us": [actual_start_us, actual_end_us],
        "anchors_pts_us": {
            "top_pts_us": spec.top_pts_us,
            "impact_pts_us": spec.impact_pts_us,
        },
        "output_video": {
            "sha256": mp4_sha256,
            "size_bytes": mp4_size,
            "width": probe_meta.width,
            "height": probe_meta.height,
            "fps": fps,
            "aspect_ratio": aspect_str,
            "audio_mode": audio_mode_str,
            "has_audio_stream": has_audio_in_output,
            "duration_ms": probe_meta.duration_ms,
            "frame_count": len(output_pts_grid),
            "codec_name": probe_meta.codec,
            "pix_fmt": "yuv420p",
        },
        "render_recipe": spec.recipe.model_dump(mode="json"),
        "swing_quality": spec.swing_quality.model_dump(mode="json"),
        "shot_quality": spec.shot_quality.model_dump(mode="json"),
        "parity_report": asdict(parity),
    }

    sidecar_bytes = json.dumps(sidecar_payload, ensure_ascii=False, indent=2).encode("utf-8")
    out_sidecar.write_bytes(sidecar_bytes)
    sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()

    return StudioExportArtifact(
        output_mp4_path=out_mp4,
        sidecar_json_path=out_sidecar,
        mp4_sha256=mp4_sha256,
        sidecar_sha256=sidecar_sha256,
        mp4_size_bytes=mp4_size,
        output_width=probe_meta.width,
        output_height=probe_meta.height,
        fps=fps,
        aspect_ratio=aspect_str,
        audio_mode=audio_mode_str,
        has_audio_in_output=has_audio_in_output,
        duration_ms=probe_meta.duration_ms,
        frame_count=len(output_pts_grid),
        parity_report=parity,
        sidecar_payload=sidecar_payload,
    )


def export_batch_tracer_compilation(
    clip_specs: list[ClipExportSpec],
    output_mp4_path: str | Path,
    sidecar_json_path: str | Path | None = None,
    allow_low_res_test: bool = False,
) -> StudioExportArtifact:
    """
    將 1 至 10 支 `ClipExportSpec` 批次渲染並串接為單一合輯 MP4 + `.tracer.json` Sidecar。
    """
    if not (1 <= len(clip_specs) <= 10):
        raise ValueError(f"批次合輯僅支援 1 至 10 球，收到: {len(clip_specs)}")

    out_mp4 = Path(output_mp4_path)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    out_sidecar = (
        Path(sidecar_json_path)
        if sidecar_json_path is not None
        else out_mp4.with_suffix(".tracer.json")
    )

    if len(clip_specs) == 1:
        return export_single_tracer_clip(
            spec=clip_specs[0],
            output_mp4_path=out_mp4,
            sidecar_json_path=out_sidecar,
            allow_low_res_test=allow_low_res_test,
        )

    master_recipe = clip_specs[0].recipe
    fps = 30 if int(master_recipe.export_format.fps) == 30 else 60
    aspect_str = master_recipe.export_format.aspect_ratio.value
    audio_mode_str = master_recipe.export_format.audio_mode.value

    # 以第一支影片決定基準輸出尺寸（若為 16:9 或 9:16 則固定為 1920x1080 或 1080x1920）
    master_layout = compute_output_layout(clip_specs[0].geometry, target_aspect=aspect_str)

    with tempfile.TemporaryDirectory(prefix="gsl_tracer_batch_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        part_paths: list[Path] = []
        part_artifacts: list[StudioExportArtifact] = []

        for idx, spec in enumerate(clip_specs):
            raw_part = tmp_dir / f"part_raw_{idx:02d}.mp4"
            raw_sidecar = tmp_dir / f"part_raw_{idx:02d}.tracer.json"
            art = export_single_tracer_clip(
                spec=spec,
                output_mp4_path=raw_part,
                sidecar_json_path=raw_sidecar,
                allow_low_res_test=allow_low_res_test,
            )
            part_artifacts.append(art)

            # 確保每一段具備完全一致的 WxH、CFR 與音軌結構以便無縫 concat
            norm_part = tmp_dir / f"part_norm_{idx:02d}.mp4"
            if audio_mode_str == AudioMode.PRESERVE.value and not art.has_audio_in_output:
                # 補齊靜音 AAC 音軌，避免混合有無音訊片段時 concat 失敗
                norm_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_part),
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-vf",
                    f"scale={master_layout.output_width}:{master_layout.output_height}:force_original_aspect_ratio=decrease,pad={master_layout.output_width}:{master_layout.output_height}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    f"{fps}/1",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(norm_part),
                ]
                subprocess.run(norm_cmd, capture_output=True, text=True, timeout=90, check=True)
                part_paths.append(norm_part)
            elif (
                art.output_width != master_layout.output_width
                or art.output_height != master_layout.output_height
            ):
                norm_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(raw_part),
                    "-vf",
                    f"scale={master_layout.output_width}:{master_layout.output_height}:force_original_aspect_ratio=decrease,pad={master_layout.output_width}:{master_layout.output_height}:(ow-iw)/2:(oh-ih)/2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    f"{fps}/1",
                ]
                if audio_mode_str == AudioMode.PRESERVE.value:
                    norm_cmd.extend(["-c:a", "aac"])
                else:
                    norm_cmd.append("-an")
                norm_cmd.append(str(norm_part))
                subprocess.run(norm_cmd, capture_output=True, text=True, timeout=90, check=True)
                part_paths.append(norm_part)
            else:
                part_paths.append(raw_part)

        concat_list = tmp_dir / "concat_list.txt"
        concat_lines = [f"file '{p.as_posix()}'" for p in part_paths]
        concat_list.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        concat_cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
        subprocess.run(concat_cmd, capture_output=True, text=True, timeout=120, check=True)

    probe_meta = probe_video_file(out_mp4)
    has_audio_out = _check_source_has_audio(out_mp4)
    mp4_sha256 = _compute_file_sha256(out_mp4)
    mp4_size = out_mp4.stat().st_size

    max_coord_err = max(a.parity_report.max_coordinate_error_px for a in part_artifacts)
    mean_coord_err = sum(a.parity_report.mean_coordinate_error_px for a in part_artifacts) / len(part_artifacts)
    max_pts_delta = max(a.parity_report.max_frame_pts_delta_us for a in part_artifacts)
    max_frame_delta = max(a.parity_report.max_frame_delta_frames for a in part_artifacts)
    total_checked_pts = sum(a.parity_report.checked_point_count for a in part_artifacts)
    total_frames = sum(a.frame_count for a in part_artifacts)

    agg_parity = ParityCheckReport(
        aspect_ratio=aspect_str,
        fps=fps,
        checked_point_count=total_checked_pts,
        max_coordinate_error_px=round(max_coord_err, 4),
        mean_coordinate_error_px=round(mean_coord_err, 4),
        max_frame_pts_delta_us=max_pts_delta,
        max_frame_delta_frames=round(max_frame_delta, 4),
        coordinate_parity_passed=all(a.parity_report.coordinate_parity_passed for a in part_artifacts),
        pts_parity_passed=all(a.parity_report.pts_parity_passed for a in part_artifacts),
    )

    sidecar_payload: dict[str, Any] = {
        "schema_version": "r4_tracer_batch_sidecar_v1",
        "clip_count": len(clip_specs),
        "clips": [a.sidecar_payload for a in part_artifacts],
        "output_video": {
            "sha256": mp4_sha256,
            "size_bytes": mp4_size,
            "width": probe_meta.width,
            "height": probe_meta.height,
            "fps": fps,
            "aspect_ratio": aspect_str,
            "audio_mode": audio_mode_str,
            "has_audio_stream": has_audio_out,
            "duration_ms": probe_meta.duration_ms,
            "frame_count": total_frames,
            "codec_name": probe_meta.codec,
            "pix_fmt": "yuv420p",
        },
        "parity_report": asdict(agg_parity),
    }

    sidecar_bytes = json.dumps(sidecar_payload, ensure_ascii=False, indent=2).encode("utf-8")
    out_sidecar.write_bytes(sidecar_bytes)
    sidecar_sha256 = hashlib.sha256(sidecar_bytes).hexdigest()

    return StudioExportArtifact(
        output_mp4_path=out_mp4,
        sidecar_json_path=out_sidecar,
        mp4_sha256=mp4_sha256,
        sidecar_sha256=sidecar_sha256,
        mp4_size_bytes=mp4_size,
        output_width=probe_meta.width,
        output_height=probe_meta.height,
        fps=fps,
        aspect_ratio=aspect_str,
        audio_mode=audio_mode_str,
        has_audio_in_output=has_audio_out,
        duration_ms=probe_meta.duration_ms,
        frame_count=total_frames,
        parity_report=agg_parity,
        sidecar_payload=sidecar_payload,
    )
