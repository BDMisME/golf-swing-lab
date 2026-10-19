import subprocess
import tempfile
from pathlib import Path
from typing import Any

from packages.analysis.probe import VideoProbeError, probe_video_file


def export_swing_compilation(
    clip_specs: list[dict[str, Any]],
    output_path: str | Path,
    layout: str = "original",
) -> dict[str, Any]:
    """
    將 1 至 3 個揮桿片段裁切並合輯為 Safari 相容之 H.264 MP4 影片。
    - 嚴格保留原片真實畫面，不繪製任何虛構球飛行軌跡。
    - layout='original'：維持原始比例（正規化為偶數像素寬高）。
    - layout='9:16'：輸出 720x1280 直式構圖，原畫面置中保留完整比例並填充深色背景。
    """
    if not clip_specs:
        raise ValueError("至少需指定 1 個揮桿片段進行匯出")
    if len(clip_specs) > 5:
        raise ValueError("單次合輯最多支援 5 個揮桿片段")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gsl_export_") as tmp_dir:
        tmp_root = Path(tmp_dir)
        part_files: list[Path] = []

        if layout == "9:16":
            vf_filter = (
                "scale=720:1280:force_original_aspect_ratio=decrease,"
                "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=#0B1320,setsar=1"
            )
        else:
            vf_filter = "scale='trunc(iw/2)*2':'trunc(ih/2)*2',setsar=1"

        for idx, spec in enumerate(clip_specs):
            src_path = Path(spec["video_path"])
            start_ms = max(0, int(spec["start_ms"]))
            end_ms = max(start_ms + 500, int(spec["end_ms"]))
            duration_sec = (end_ms - start_ms) / 1000.0
            start_sec = start_ms / 1000.0

            part_out = tmp_root / f"clip_{idx:02d}.mp4"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start_sec:.3f}",
                "-i",
                str(src_path),
                "-t",
                f"{duration_sec:.3f}",
                "-vf",
                vf_filter,
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-an",
                str(part_out),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0 or not part_out.exists():
                raise VideoProbeError(f"片段 #{idx + 1} 裁切失敗: {proc.stderr[-300:]}")
            part_files.append(part_out)

        if len(part_files) == 1:
            part_files[0].replace(out_p)
        else:
            concat_list = tmp_root / "concat_list.txt"
            lines = [f"file '{p.as_posix()}'" for p in part_files]
            concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
            concat_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(out_p),
            ]
            proc = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=180)
            if proc.returncode != 0 or not out_p.exists():
                raise VideoProbeError(f"多球合輯合併失敗: {proc.stderr[-300:]}")

    meta = probe_video_file(out_p)
    return {
        "duration_ms": meta.duration_ms,
        "width": meta.width,
        "height": meta.height,
        "size_bytes": out_p.stat().st_size,
        "codec": meta.codec,
    }
