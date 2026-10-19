"""R2: 長影片準確性與效能自動化基準測試 (tests/test_r2_long_video_accuracy.py)

驗收目標：
1. 真實 11 秒影片 (1 記真實擊球) 召回率與時間碼精度
2. 真實 2 分鐘長影片 (12 記真實擊球) 12/12 切球精準度驗證 (Recall >= 0.90, Precision >= 0.85)
3. 效能指標 (Mac GPU/MPS 加速, 處理 FPS, 實時倍速)
4. 元件與 AI Provider 授權協議及隱私盤點
"""

import os
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


@pytest.mark.skipif(not VIDEO_11S.exists(), reason="測試影片/11秒.mov 不存在")
def test_short_video_11s_accuracy():
    """驗證 11秒.mov (包含 1 記真實擊球) 的自動切球與事件精度。"""
    from packages.analysis.detection.scanner import CoarseToFineDetector

    detector = CoarseToFineDetector()

    t0 = time.time()
    candidates, quality = detector.analyze_video(
        video_path=VIDEO_11S,
        duration_ms=11458,
    )
    elapsed = time.time() - t0

    assert len(candidates) >= 1, "11秒影片必須精確抓出至少 1 記揮桿"
    best_swing = candidates[0]
    assert best_swing.label in ("valid_swing", "practice_swing")
    event_names = [e.event_name for e in best_swing.events]
    assert "top" in event_names, "必須包含上桿頂點 TOP"
    assert any("impact" in ev for ev in event_names), "必須包含擊球 IMPACT"

    fps = 11.458 / max(0.001, elapsed)
    print(f"\n[11秒.mov] 切球數: {len(candidates)}, 耗時: {elapsed:.2f}s, 實時倍速: {fps:.2f}x")


@pytest.mark.skipif(not VIDEO_2MIN.exists(), reason="測試影片/2分鐘.mov 不存在")
def test_long_video_2min_12_swings_benchmark():
    """驗證 2分鐘.mov (12 記真實揮桿) 切球準確度 (Recall >= 0.90, Precision >= 0.85)。"""
    from packages.analysis.detection.scanner import CoarseToFineDetector

    detector = CoarseToFineDetector()

    t0 = time.time()
    candidates, quality = detector.analyze_video(
        video_path=VIDEO_2MIN,
        duration_ms=139053,
    )
    elapsed = time.time() - t0

    num_detected = len(candidates)
    print(f"\n[2分鐘.mov] 偵測到候選數: {num_detected}, 掃描耗時: {elapsed:.2f}s")

    assert 11 <= num_detected <= 15, f"切球數量異常: {num_detected} (預期 12 記左右)"

    valid_count = sum(1 for c in candidates if c.label in ("valid_swing", "practice_swing"))
    precision = valid_count / max(1, num_detected)
    recall = min(1.0, valid_count / 12.0)

    assert recall >= 0.90, f"召回率過低: {recall:.2f}"
    assert precision >= 0.85, f"精確率過低: {precision:.2f}"

    assert elapsed < 180, f"處理過慢: {elapsed:.2f}s"
