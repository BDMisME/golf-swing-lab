import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class VideoProbeError(Exception):
    """影片封裝損毀、無影像軌或長度不合法時拋出之例外。"""


@dataclass
class VideoMetadata:
    duration_ms: int
    width: int
    height: int
    rotation: int
    fps_num: int
    fps_den: int
    is_vfr: bool
    codec: str
    has_audio: bool
    pts_timestamps_ms: list[int] = field(default_factory=list)
    raw_info: dict[str, Any] = field(default_factory=dict)

    @property
    def fps(self) -> float:
        return self.fps_num / max(1, self.fps_den)


def _parse_fraction(frac_str: str) -> tuple[int, int]:
    if not frac_str or "/" not in frac_str:
        try:
            val = int(float(frac_str))
            return (max(1, val), 1)
        except Exception:
            return (30, 1)
    parts = frac_str.split("/", 1)
    try:
        num = int(parts[0])
        den = int(parts[1])
        if num <= 0 or den <= 0:
            return (30, 1)
        return (num, den)
    except Exception:
        return (30, 1)


def probe_video_file(file_path: str | Path, collect_pts: bool = False) -> VideoMetadata:
    """使用 ffprobe 解析影片真實 metadata、旋轉矩陣、VFR 與真實時間戳 PTS。"""
    path = Path(file_path)
    if not path.exists() or path.stat().st_size == 0:
        raise VideoProbeError("影片檔案不存在或大小為 0 bytes")

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise VideoProbeError(f"ffprobe 無法解析影片格式: {proc.stderr.strip()}")

    try:
        info = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise VideoProbeError(f"ffprobe JSON 解析失敗: {exc}") from exc

    streams = info.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video_stream:
        raise VideoProbeError("檔案中找不到任何有效視訊軌 (video stream)")

    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = info.get("format") or {}

    duration_sec = float(video_stream.get("duration") or fmt.get("duration") or 0.0)
    duration_ms = int(round(duration_sec * 1000))
    if duration_ms <= 0:
        raise VideoProbeError("影片時長為 0，無法進行揮桿分析")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    codec = str(video_stream.get("codec_name") or "unknown")

    # 解析旋轉角度（tags.rotate 或 side_data_list Display Matrix）
    rotation = 0
    tags = video_stream.get("tags") or {}
    if "rotate" in tags:
        try:
            rotation = int(tags["rotate"]) % 360
        except ValueError:
            rotation = 0
    for side in video_stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                rotation = int(round(float(side["rotation"]))) % 360
            except ValueError:
                pass

    r_num, r_den = _parse_fraction(str(video_stream.get("r_frame_rate") or "30/1"))
    avg_num, avg_den = _parse_fraction(str(video_stream.get("avg_frame_rate") or f"{r_num}/{r_den}"))
    r_fps = r_num / max(1, r_den)
    avg_fps = avg_num / max(1, avg_den)
    is_vfr = abs(r_fps - avg_fps) > 0.75

    pts_list: list[int] = []
    if collect_pts:
        pts_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "frame=best_effort_timestamp_time,pkt_pts_time",
            "-of",
            "json",
            str(path),
        ]
        pts_proc = subprocess.run(pts_cmd, capture_output=True, text=True, timeout=60)
        if pts_proc.returncode == 0:
            try:
                pts_data = json.loads(pts_proc.stdout)
                for fr in pts_data.get("frames") or []:
                    ts = fr.get("best_effort_timestamp_time") or fr.get("pkt_pts_time")
                    if ts is not None:
                        pts_list.append(int(round(float(ts) * 1000)))
            except Exception:
                pass
        if len(pts_list) >= 4:
            diffs = [pts_list[i + 1] - pts_list[i] for i in range(len(pts_list) - 1)]
            if max(diffs) - min(diffs) > 8:
                is_vfr = True

    return VideoMetadata(
        duration_ms=duration_ms,
        width=width,
        height=height,
        rotation=rotation,
        fps_num=avg_num if avg_fps > 1 else r_num,
        fps_den=avg_den if avg_fps > 1 else r_den,
        is_vfr=is_vfr,
        codec=codec,
        has_audio=audio_stream is not None,
        pts_timestamps_ms=pts_list,
        raw_info=info,
    )


def generate_proxy_and_thumbnail(
    input_path: str | Path,
    proxy_path: str | Path,
    thumbnail_path: str | Path,
) -> None:
    """生成可供 iPhone Safari 流暢播放與精準 Seek 的 H.264 MP4 Proxy 與首張預覽縮圖。"""
    in_p = Path(input_path)
    proxy_p = Path(proxy_path)
    thumb_p = Path(thumbnail_path)
    proxy_p.parent.mkdir(parents=True, exist_ok=True)
    thumb_p.parent.mkdir(parents=True, exist_ok=True)

    # 產生 H.264 + yuv420p + faststart，自動套用旋轉並限制最大邊長 720p 以兼顧畫質與速度
    proxy_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(in_p),
        "-vf",
        "scale='min(1280,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "24",
        "-pix_fmt",
        "yuv420p",
        "-g",
        "15",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(proxy_p),
    ]
    proc = subprocess.run(proxy_cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise VideoProbeError(f"Proxy 轉碼失敗: {proc.stderr[-400:]}")

    thumb_cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        "00:00:00.500",
        "-i",
        str(proxy_p),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(thumb_p),
    ]
    subprocess.run(thumb_cmd, capture_output=True, text=True, timeout=30)
    if not thumb_p.exists():
        # 若影片短於 0.5 秒則取第 0 秒
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(proxy_p),
                "-frames:v",
                "1",
                str(thumb_p),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
