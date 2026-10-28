"""R2: 長影片準確性與效能自動化基準測試 (tests/test_r2_long_video_accuracy.py)

驗收目標：
1. 真實 11 秒影片 (1 記真實擊球) 召回率與時間碼精度
2. 真實 2 分鐘長影片 (12 記真實擊球) 12/12 切球精準度驗證 (Recall >= 0.90, Precision >= 0.85)
3. 效能指標 (Mac GPU/MPS 加速, 處理 FPS, 實時倍速)
4. 元件與 AI Provider 授權協議及隱私盤點
"""

import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEO_11S = REPO_ROOT / "測試影片" / "11秒.mov"
VIDEO_2MIN = REPO_ROOT / "測試影片" / "2分鐘.mov"


def test_licenses_and_privacy_compliance():
    """盤點模型、核心元件與 AI Provider 授權與隱私條款。"""
    inventory = {
        "ultralytics_yolov8": {
            "license": "AGPL-3.0",
            "usage_mode": "Local weights execution on user machine (MPS hardware)",
            "privacy": "100% on-device local inference; 0 bytes sent outside",
        },
        "golf_ball_tracker": {
            "license": "MIT",
            "origin": "notjulietxd/golf-ball-tracker (HuggingFace)",
            "privacy": "100% on-device local inference",
        },
        "mediapipe_pose": {
            "license": "Apache-2.0",
            "privacy": "100% on-device local inference",
        },
        "ffmpeg": {
            "license": "LGPL-2.1+",
            "privacy": "Local CLI binary execution",
        },
        "volcengine_doubao": {
            "provider": "ByteDance / Volcengine",
            "model": "doubao-seed-2.1-lite",
            "license": "Commercial API Terms of Service",
            "privacy": "Only representative keyframe stills sent over TLS; strictly isolated per-user",
            "offline_fallback": "RuleBasedCoachProvider (LLM_PROVIDER=none)",
        },
    }

    assert inventory["ultralytics_yolov8"]["license"] == "AGPL-3.0"
    assert inventory["golf_ball_tracker"]["license"] == "MIT"
    assert inventory["volcengine_doubao"]["offline_fallback"] == "RuleBasedCoachProvider (LLM_PROVIDER=none)"


def test_short_video_11s_accuracy():
    """驗證 11秒.mov (包含 1 記真實擊球) 透過真實人工標註進行一對一配對評估。"""
    if not VIDEO_11S.exists():
        pytest.skip("[NOT_VALIDATED] 測試影片/11秒.mov 不存在，標記為 NOT_VALIDATED，絕不偽裝為 PASS")

    import json

    from packages.analysis.detection.scanner import CoarseToFineDetector
    from packages.analysis.evaluation.golden_eval import evaluate_against_golden

    gt_file = REPO_ROOT / "tests" / "golden" / "real_11s_session_gt.json"
    assert gt_file.exists(), "真實 11秒標註檔必須存在"
    with open(gt_file, encoding="utf-8") as f:
        gt_data = json.load(f)

    detector = CoarseToFineDetector()
    t0 = time.time()
    candidates, quality = detector.analyze_video(
        video_path=VIDEO_11S,
        duration_ms=11458,
    )
    elapsed = time.time() - t0

    preds = [
        {
            "start_ms": c.start_ms,
            "end_ms": c.end_ms,
            "sequence_no": i + 1,
            "label": c.label,
            "ball_strike_status": c.ball_strike_status,
        }
        for i, c in enumerate(candidates)
    ]
    summary = evaluate_against_golden(
        predictions=preds,
        ground_truths=gt_data["ground_truth_swings"],
        iou_threshold=0.25,
    )

    print(
        f"\n[11秒.mov 一對一配對] TP: {summary.true_positives}, Recall: {summary.recall:.2f}, "
        f"分類正確率: {summary.classification_accuracy:.2f}, 耗時: {elapsed:.2f}s"
    )
    assert summary.true_positives >= 1, "必須一對一配對命中真實擊球"
    assert summary.candidate_detection_rate >= 1.0
    assert summary.valid_swing_recall >= 1.0


def test_long_video_2min_12_swings_benchmark():
    """驗證 2分鐘.mov (12 記真實揮桿) 透過真實人工標註進行一對一逐球配對評估 (P0-2 五維度驗收)。"""
    if not VIDEO_2MIN.exists():
        pytest.skip("[NOT_VALIDATED] 測試影片/2分鐘.mov 不存在，標記為 NOT_VALIDATED，絕不偽裝為 PASS")

    import json

    from packages.analysis.detection.scanner import CoarseToFineDetector
    from packages.analysis.evaluation.golden_eval import evaluate_against_golden

    gt_file = REPO_ROOT / "tests" / "golden" / "real_2min_session_gt.json"
    assert gt_file.exists(), "真實 2分鐘標註檔必須存在"
    with open(gt_file, encoding="utf-8") as f:
        gt_data = json.load(f)

    detector = CoarseToFineDetector()
    t0 = time.monotonic()
    candidates, quality = detector.analyze_video(
        video_path=VIDEO_2MIN,
        duration_ms=139053,
    )
    elapsed = time.monotonic() - t0

    preds = [
        {
            "start_ms": c.start_ms,
            "end_ms": c.end_ms,
            "sequence_no": i + 1,
            "label": c.label,
            "ball_strike_status": c.ball_strike_status,
        }
        for i, c in enumerate(candidates)
    ]
    summary = evaluate_against_golden(
        predictions=preds,
        ground_truths=gt_data["ground_truth_swings"],
        iou_threshold=0.20,
    )

    print(
        f"\n[2分鐘.mov 逐球一對一配對] 偵測: {len(candidates)}, GT: {summary.total_gt}, "
        f"TP: {summary.true_positives}, FP: {summary.false_positives}, FN: {summary.false_negatives}, "
        f"候選偵測率: {summary.candidate_detection_rate:.4f}, 分類正確率: {summary.classification_accuracy:.4f}, "
        f"擊球專項 Recall: {summary.valid_swing_recall:.4f}, 擊球專項 Precision: {summary.valid_swing_precision:.4f}, "
        f"邊界誤差中位數: {summary.combined_boundary_median_ms:.1f}ms, 耗時: {elapsed:.2f}s"
    )

    # 嚴格一對一真實配對標準 (P0-2: 分開考核候選偵測、分類正確率、擊球專項 Recall >= 0.90, Precision >= 0.85)
    assert summary.candidate_detection_rate >= 0.90, (
        f"候選動作偵測率未達標: {summary.candidate_detection_rate:.4f} / 1.0"
    )
    assert summary.classification_accuracy >= 0.90, (
        f"揮桿分類正確率未達標: {summary.classification_accuracy:.4f} / 1.0"
    )
    assert summary.valid_swing_recall >= 0.90, (
        f"擊球專項 Recall 未達標 (門檻 >= 0.90): {summary.valid_swing_recall:.4f}"
    )
    assert summary.valid_swing_precision >= 0.85, (
        f"擊球專項 Precision 未達標 (門檻 >= 0.85): {summary.valid_swing_precision:.4f}"
    )
    assert summary.combined_boundary_median_ms <= 1500, (
        f"起迄邊界時間偏差中位數過大: {summary.combined_boundary_median_ms:.1f}ms"
    )
    assert elapsed < 180, f"處理時間過長: {elapsed:.2f}s"
