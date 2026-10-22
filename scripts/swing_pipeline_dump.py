#!/usr/bin/env python3
"""
scripts/swing_pipeline_dump.py

以「正式 Worker 相同的分析路徑」對單支影片執行一次完整推論，輸出每球完整資料流快照：
候選假設 → 選擇 → 精修 → 最終事件 → 指標 → 分數 → 排行榜。

用途：版本間前後比較（baseline vs fixed），不含任何 Ground Truth 比對，也不輸出 PASS/FAIL。

用法：
  uv run python scripts/swing_pipeline_dump.py --video 測試影片/2分鐘.mov --out docs/reports/x.json
  uv run python scripts/swing_pipeline_dump.py --video 測試影片/2分鐘.mov --proxy --out ...
    （--proxy：先以正式 generate_proxy_and_thumbnail 產生 720p/30fps Proxy，再分析 Proxy，
      與 apps/worker/tasks.py 的實際行為相同）
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from packages.analysis.detection.scanner import CoarseToFineDetector  # noqa: E402
from packages.analysis.probe import generate_proxy_and_thumbnail, probe_video_file  # noqa: E402
from packages.analysis.scoring.engine import compute_swing_score, rank_session_swings  # noqa: E402

KEEP_METRICS = (
    "spine_tilt_delta_deg",
    "head_displacement_ratio",
    "single_swing_plane_gap_ratio",
    "backswing_ms",
    "downswing_ms",
    "backswing_downswing_ratio",
    "finish_hold_ms",
    "finish_sway_ratio",
    "session_path_repeatability",
)


def _git_sha() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True).strip()
        return sha + ("-DIRTY" if dirty else "")
    except Exception:
        return "UNKNOWN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--proxy", action="store_true")
    ap.add_argument("--model-version", default="pose-v1")
    args = ap.parse_args()

    src = (REPO_ROOT / args.video).resolve() if not Path(args.video).is_absolute() else Path(args.video)
    meta = probe_video_file(src, collect_pts=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory(prefix="gsl_dump_") as td:
        target = src
        proxy_s = 0.0
        if args.proxy:
            p0 = time.time()
            proxy = Path(td) / "proxy.mp4"
            generate_proxy_and_thumbnail(src, proxy, Path(td) / "thumb.jpg")
            target = proxy
            proxy_s = time.time() - p0

        det = CoarseToFineDetector(model_version=args.model_version)
        a0 = time.time()
        segs, quality = det.analyze_video(video_path=target, duration_ms=meta.duration_ms)
        analyze_s = time.time() - a0

    swings: list[dict[str, Any]] = []
    for s in segs:
        score = compute_swing_score(metrics=s.metrics, quality_metadata=s.quality_metadata)
        ev = {e.event_name: e for e in s.events}
        qm = s.quality_metadata or {}
        hyps = qm.get("hypotheses") or []
        m_map = {m["metric_key"]: m for m in s.metrics}
        swings.append(
            {
                "id": f"seq-{s.sequence_no}",
                "sequence_no": s.sequence_no,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "label": s.label,
                "ball_strike_status": s.ball_strike_status,
                "review_status": s.review_status,
                "review_flags": s.review_flags,
                "confidence": s.confidence,
                "events": {
                    k: {
                        "time_ms": v.time_ms,
                        "confidence": round(v.confidence, 3),
                        "sources": list(v.detection_sources),
                        "uncertainty_ms": v.uncertainty_ms,
                        "sampling_resolution_ms": v.sampling_resolution_ms,
                    }
                    for k, v in ev.items()
                },
                "selection_rationale": qm.get("selection_rationale"),
                "is_ambiguous": qm.get("is_ambiguous"),
                "unreliable_for_ranking": qm.get("unreliable_for_ranking"),
                "hypotheses_top3": hyps[:3],
                "hypothesis_count": len(hyps),
                "local_refinements": qm.get("local_refinements"),
                "ball_strike_feedback": qm.get("ball_strike_feedback"),
                "event_chain": qm.get("event_chain"),
                "strike_evidence": qm.get("strike_evidence"),
                "metrics": {
                    k: {
                        "value": m_map[k].get("value"),
                        "confidence": m_map[k].get("confidence"),
                        "details": m_map[k].get("details"),
                    }
                    for k in KEEP_METRICS
                    if k in m_map
                },
                "overall_score": score.overall_nullable,
                "ig_visual_score": score.ig_visual_score,
                "coverage": score.coverage,
                "subscores": {
                    k: {"score": v.get("score"), "raw": v.get("raw_value")}
                    for k, v in score.subscores.items()
                    if isinstance(v, dict) and "score" in v
                },
                "_subscores_full": score.subscores,
                "quality_metadata": {
                    "unreliable_for_ranking": qm.get("unreliable_for_ranking"),
                    "is_ambiguous": qm.get("is_ambiguous"),
                },
            }
        )

    rank_input = [
        {**sw, "subscores": sw["_subscores_full"]} for sw in swings
    ]
    rankings = rank_session_swings(rank_input, favorites=[], top_k=5)
    for sw in swings:
        sw.pop("_subscores_full", None)

    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)
    out = {
        "git_sha": _git_sha(),
        "video": str(src.relative_to(REPO_ROOT)) if src.is_relative_to(REPO_ROOT) else str(src),
        "analyzed_target": "proxy_720p_30fps" if args.proxy else "original",
        "video_meta": {
            "duration_ms": meta.duration_ms,
            "fps": (meta.fps_num / meta.fps_den) if meta.fps_den else None,
            "width": meta.width,
            "height": meta.height,
        },
        "timing_s": {
            "proxy": round(proxy_s, 1),
            "analyze": round(analyze_s, 1),
            "total": round(time.time() - t0, 1),
        },
        "peak_rss_mb": round(peak_rss_mb, 1),
        "quality_summary": quality,
        "swing_count": len(swings),
        "swings": swings,
        "rankings": {
            k: [
                {"rank": r["rank"], "seq": r["sequence_no"], "score": r["category_score"], "pinned": r["manual_pinned"]}
                for r in v
            ]
            for k, v in rankings.items()
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(f"[{out['git_sha'][:8]}] {out['analyzed_target']} swings={len(swings)} analyze={analyze_s:.1f}s rss={peak_rss_mb:.0f}MB")
    for sw in swings:
        e = sw["events"]
        top = e.get("top", {}).get("time_ms")
        imp = e.get("impact_estimated", {}).get("time_ms")
        ds = (imp - top) if (top is not None and imp is not None) else None
        print(
            f"#{sw['sequence_no']:>2} {sw['start_ms']:>7}-{sw['end_ms']:<7} {sw['label']:<15} "
            f"{sw['ball_strike_status']:<17} {sw['review_status']:<13} top={top} imp={imp} ds={ds} "
            f"score={sw['overall_score']} flags={sw['review_flags']}"
        )
    print("rankings:", json.dumps(out["rankings"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
