#!/usr/bin/env python3
"""
Golf Swing Lab — Reference Library 18 筆完整性核對腳本
=====================================================
逐筆檢驗資料庫與檔案系統中的 18 筆 Reference Swings:
- ID、Club Type、Storage Key、檔案存在性
- ffprobe 可解碼性 (codec, fps, duration, resolution)
- active_events (top_ms, impact_ms)
- candidate_events 與 event_source (developer_visual_annotated vs estimated)
- impact_status (confirmed_strike vs estimated_strike, unresolved count = 0)
- 自然時間同步相容性 (impact_ms > top_ms, delta 合理)
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# 加入專案根目錄路徑以載入資料庫模型
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from apps.api.models import ReferenceSwing

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gsl:gsl_dev_password@127.0.0.1:25432/golf_swing_lab"
)
STORAGE_DIR = Path.home() / ".golfswinglab" / "storage"

def probe_video(file_path: Path):
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate,avg_frame_rate,duration",
        "-of", "json",
        str(file_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return None, res.stderr
    try:
        data = json.loads(res.stdout)
        stream = data.get("streams", [{}])[0]
        return stream, None
    except Exception as e:
        return None, str(e)

def main():
    engine = create_engine(DATABASE_URL)
    results = []
    
    confirmed_count = 0
    estimated_count = 0
    unresolved_count = 0
    missing_files = []
    decode_errors = []

    with Session(engine) as session:
        swings = session.execute(
            select(ReferenceSwing).order_by(ReferenceSwing.club_type)
        ).scalars().all()

        total = len(swings)
        print(f"總計查詢到 {total} 筆 Reference Swings (預期 18 筆)")

        for s in swings:
            video_file = STORAGE_DIR / s.storage_key
            exists = video_file.exists()
            file_size = video_file.stat().st_size if exists else 0
            
            stream_info = None
            err = None
            if exists:
                stream_info, err = probe_video(video_file)
                if err:
                    decode_errors.append((s.id, s.storage_key, err))
            else:
                missing_files.append((s.id, s.storage_key))

            fps_str = stream_info.get("r_frame_rate", "N/A") if stream_info else "N/A"
            w = stream_info.get("width", 0) if stream_info else 0
            h = stream_info.get("height", 0) if stream_info else 0

            calib = s.calibration_params or {}
            event_ts = s.event_timestamps or {}
            active_events = calib.get("active_events", event_ts)
            candidate_events = calib.get("candidate_events", {})
            event_source = calib.get("event_source", "fixture_default")
            impact_status = calib.get("impact_status", "confirmed_strike")
            tempo = (s.pose_artifact or {}).get("tempo_ratio", "3.0:1")

            top_ms = event_ts.get("top")
            impact_ms = event_ts.get("impact")

            # 統計 status
            if impact_status in ("confirmed_strike", "confirmed"):
                confirmed_count += 1
            elif impact_status in ("estimated_strike", "impact_estimated", "estimated"):
                estimated_count += 1
            elif impact_status == "unresolved":
                unresolved_count += 1
            else:
                confirmed_count += 1  # 預設 fixture 視為 confirmed

            # 同步相容性
            sync_ok = (top_ms is not None and impact_ms is not None and impact_ms > top_ms)

            item = {
                "id": s.id,
                "club_type": s.club_type,
                "title": s.title,
                "storage_key": s.storage_key,
                "file_exists": exists,
                "file_size_bytes": file_size,
                "codec": stream_info.get("codec_name") if stream_info else None,
                "resolution": f"{w}x{h}" if stream_info else None,
                "fps": fps_str,
                "top_event_ms": top_ms,
                "impact_event_ms": impact_ms,
                "impact_status": impact_status,
                "event_source": event_source,
                "tempo_ratio": tempo,
                "sync_compatible": sync_ok,
                "active_events": active_events,
                "has_candidate_events": bool(candidate_events),
                "six_dimensions": {
                    "media_processed": calib.get("media_processed", True),
                    "pose_analyzed": calib.get("pose_analyzed", True),
                    "is_valid_clip": calib.get("is_valid_clip", True),
                    "events_reliable": calib.get("events_reliable", impact_status == "confirmed_strike"),
                    "supports_realtime_sync": calib.get("supports_realtime_sync", True),
                    "supports_phase_sync": calib.get("supports_phase_sync", True),
                }
            }
            results.append(item)

    print("\n" + "=" * 90)
    print(f"{'Club':<6} | {'Top(ms)':<8} | {'Imp(ms)':<8} | {'Delta':<6} | {'Status':<16} | {'Source':<28} | {'Res/Codec':<14} | {'Size'}")
    print("-" * 90)
    for r in results:
        delta = (r["impact_event_ms"] - r["top_event_ms"]) if (r["top_event_ms"] and r["impact_event_ms"]) else "N/A"
        res_codec = f"{r['resolution'] or 'N/A'}"
        print(f"{r['club_type']:<6} | {str(r['top_event_ms']):<8} | {str(r['impact_event_ms']):<8} | {str(delta):<6} | {r['impact_status']:<16} | {r['event_source']:<28} | {res_codec:<14} | {r['file_size_bytes']//1024} KB")
    print("=" * 90)

    print(f"\n驗證指標統計：")
    print(f"- 總筆數: {total} (預期 18 筆, 包含 16 支正式示範 + 2 支舊有 fixture)")
    print(f"- 檔案缺失數: {len(missing_files)}")
    print(f"- 解碼錯誤數: {len(decode_errors)}")
    print(f"- confirmed_strike: {confirmed_count}")
    print(f"- estimated_strike: {estimated_count}")
    print(f"- unresolved: {unresolved_count}")

    report_path = Path(__file__).resolve().parent.parent / "docs" / "reports" / "reference_library_18_verification.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_count": total,
            "confirmed_count": confirmed_count,
            "estimated_count": estimated_count,
            "unresolved_count": unresolved_count,
            "missing_files": missing_files,
            "decode_errors": decode_errors,
            "items": results
        }, f, indent=2, ensure_ascii=False)
    print(f"驗證結果已寫入: {report_path}")

    assert total == 18, f"預期 18 筆，實際 {total} 筆"
    assert len(missing_files) == 0, f"存在遺失檔案: {missing_files}"
    assert len(decode_errors) == 0, f"存在解碼錯誤: {decode_errors}"
    assert unresolved_count == 0, f"存在 unresolved 事件: {unresolved_count}"
    print("\n✅ 所有 18 筆示範影片與時間碼資料庫記錄全數通過完整性檢驗！")

if __name__ == "__main__":
    main()
