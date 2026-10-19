import json
from pathlib import Path

from typing import Any

from packages.analysis.detection.scanner import (
    CoarseToFineDetector,
    compute_time_iou,
    merge_overlapping_windows,
)
from packages.analysis.evaluation.golden_eval import evaluate_against_golden
from packages.analysis.scoring.engine import compute_swing_score, rank_session_swings
from tests.fixtures.video_factory import create_synthetic_dtl_video


def test_iou_and_window_deduplication() -> None:
    assert round(compute_time_iou(1000, 4000, 2500, 5500), 3) == round(1500 / 4500, 3)
    assert compute_time_iou(1000, 2000, 3000, 4000) == 0.0

    merged = merge_overlapping_windows([(1000, 3800), (3500, 5200), (8000, 11500)])
    assert len(merged) == 2
    assert merged[0] == (1000, 5200)
    assert merged[1] == (8000, 11500)


def test_coarse_to_fine_detector_against_synthetic_golden(tmp_path: Path) -> None:
    gt_path = Path("tests/golden/synthetic_session_gt.json")
    gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
    gt_swings = gt_data["ground_truth_swings"]

    video_path = create_synthetic_dtl_video(
        tmp_path / "synthetic_session_30fps.mp4",
        duration_ms=16000,
        fps=30,
        swings_spec=gt_swings,
    )

    detector = CoarseToFineDetector(model_version="pose-v1")
    detected, quality = detector.analyze_video(video_path, duration_ms=16000)

    assert len(detected) == 3
    assert quality["low_light"] is False

    preds = [
        {"sequence_no": d.sequence_no, "start_ms": d.start_ms, "end_ms": d.end_ms}
        for d in detected
    ]
    eval_res = evaluate_against_golden(preds, gt_swings)
    assert eval_res.recall >= 0.90
    assert eval_res.precision >= 0.85
    assert eval_res.combined_boundary_median_ms <= 500.0


def test_60fps_low_light_and_multi_person_robustness(tmp_path: Path) -> None:
    detector = CoarseToFineDetector(model_version="pose-v1")

    # 1. 60fps 影片偵測
    v60 = create_synthetic_dtl_video(
        tmp_path / "swing_60fps.mp4",
        duration_ms=6000,
        fps=60,
        swings_spec=[{"start_ms": 1200, "end_ms": 4400, "label": "valid_swing"}],
    )
    segs_60, _ = detector.analyze_video(v60, duration_ms=6000)
    assert len(segs_60) == 1
    assert len(segs_60[0].events) == 8

    # 2. 低光環境影片 (brightness_scale=0.12)：不得產生虛假高信心分數
    v_dark = create_synthetic_dtl_video(
        tmp_path / "swing_dark.mp4",
        duration_ms=5000,
        fps=30,
        brightness_scale=0.12,
        swings_spec=[{"start_ms": 1000, "end_ms": 4000, "label": "valid_swing"}],
    )
    segs_dark, q_dark = detector.analyze_video(v_dark, duration_ms=5000)
    assert q_dark["low_light"] is True
    assert len(segs_dark) == 0

    # 3. 多人入鏡干擾影片：應標記 multi_person 旗標並進入 needs_review
    v_multi = create_synthetic_dtl_video(
        tmp_path / "swing_multiperson.mp4",
        duration_ms=6000,
        fps=30,
        intruder_window_ms=(1500, 4000),
        swings_spec=[{"start_ms": 1200, "end_ms": 4400, "label": "valid_swing"}],
    )
    segs_multi, q_multi = detector.analyze_video(v_multi, duration_ms=6000)
    assert q_multi["multi_person_detected"] is True
    assert len(segs_multi) == 1
    assert "multi_person" in segs_multi[0].review_flags
    assert segs_multi[0].review_status == "needs_review"


def test_score_v1_determinism_coverage_gate_and_rankings() -> None:
    full_metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 2.0, "confidence": 0.92},
        {"metric_key": "head_displacement_ratio", "value": 0.05, "confidence": 0.90},
        {"metric_key": "hand_path_deviation_ratio", "value": 0.04, "confidence": 0.88},
        {"metric_key": "backswing_downswing_ratio", "value": 3.05, "confidence": 0.91},
        {"metric_key": "finish_hold_ms", "value": 1300.0, "confidence": 0.90},
        {"metric_key": "finish_sway_ratio", "value": 0.02, "confidence": 0.90},
    ]
    s1 = compute_swing_score(full_metrics)
    s2 = compute_swing_score(full_metrics)
    assert s1.overall_nullable == s2.overall_nullable == 100.0
    assert s1.partial_score is False
    assert s1.coverage == 1.0
    assert s1.ig_visual_score is not None

    # 有效覆蓋率 < 70%（僅有 25% + 15% = 40% 分項有效）必須回傳 overall_nullable = None
    sparse_metrics: list[dict[str, Any]] = [
        {"metric_key": "spine_tilt_delta_deg", "value": 3.0, "confidence": 0.85},
        {"metric_key": "head_displacement_ratio", "value": 0.07, "confidence": 0.85},
        {"metric_key": "hand_path_deviation_ratio", "value": None, "confidence": 0.0},
        {"metric_key": "backswing_downswing_ratio", "value": None, "confidence": 0.0},
        {"metric_key": "finish_hold_ms", "value": None, "confidence": 0.0},
        {"metric_key": "finish_sway_ratio", "value": None, "confidence": 0.0},
    ]
    s_sparse = compute_swing_score(sparse_metrics)
    assert s_sparse.coverage == 0.40
    assert s_sparse.overall_nullable is None
    assert s_sparse.partial_score is True
    assert "無法可靠評分" in s_sparse.explanation

    # 測試排名與手動排除/置頂
    swings = [
        {
            "id": "seg-1",
            "sequence_no": 1,
            "start_ms": 1000,
            "end_ms": 4000,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "overall_score": 91.5,
            "ig_visual_score": 88.0,
            "confidence": 0.9,
            "subscores": {
                "tempo_consistency": {"score": 85.0},
                "finish_balance": {"score": 92.0},
            },
        },
        {
            "id": "seg-2",
            "sequence_no": 2,
            "start_ms": 5000,
            "end_ms": 8000,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "overall_score": 86.0,
            "ig_visual_score": 94.0,
            "confidence": 0.88,
            "subscores": {
                "tempo_consistency": {"score": 96.0},
                "finish_balance": {"score": 84.0},
            },
        },
    ]
    ranks = rank_session_swings(swings)
    assert ranks["posture"][0]["segment_id"] == "seg-1"
    assert ranks["tempo"][0]["segment_id"] == "seg-2"
    assert ranks["ig"][0]["segment_id"] == "seg-2"

    # 手動排除 seg-1 後，seg-2 成為 posture 第一名
    ranks_after_exclude = rank_session_swings(
        swings, favorites=[{"segment_id": "seg-1", "category": "excluded"}]
    )
    assert len(ranks_after_exclude["posture"]) == 1
    assert ranks_after_exclude["posture"][0]["segment_id"] == "seg-2"
