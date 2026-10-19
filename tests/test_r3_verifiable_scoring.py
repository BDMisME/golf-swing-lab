"""R3: 可驗證評分與精選球自動化測試 (tests/test_r3_verifiable_scoring.py)

驗收範疇：
1. Score v1 可解釋內部動作評分公式與 70% 覆蓋率硬門檻 (<70% 必須 overall=None)
2. 「怎麼算的？」透明度揭露 (公式、權重、信心度、原始值與繁體中文說明)
3. Top 精選球 4 榜多維排序 (綜合最高分、最佳節奏 3.0:1、最佳前傾穩定、痛點待改善球)
4. 人工標籤校正與即時分數重算
"""

from packages.analysis.scoring.engine import (
    compute_swing_score,
    rank_session_swings,
)


def test_coverage_gate_less_than_70_percent():
    """驗證分項覆蓋率 < 70% 時，overall_nullable 必須為 None。"""
    # 僅提供單一指標 (軀幹前傾 25% 權重，未達 70% 門檻)
    incomplete_metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 3.2, "confidence": 0.85}
    ]
    res = compute_swing_score(metrics=incomplete_metrics, min_coverage_gate=0.70)
    assert res.overall_nullable is None, "覆蓋率 < 70% 時綜合分數必須為 None"
    assert res.coverage == 0.25, "覆蓋率應為 25%"
    assert "無法可靠評分" in res.explanation
    assert res.subscores["spine_tilt_stability"]["score"] is not None


def test_coverage_gate_full_and_transparency():
    """驗證完整指標時總分確定性計算，且各分項均附帶怎麼算的說明。"""
    full_metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 2.5, "confidence": 0.90},
        {"metric_key": "head_displacement_ratio", "value": 0.05, "confidence": 0.90},
        {"metric_key": "hand_path_deviation_ratio", "value": 0.04, "confidence": 0.85},
        {"metric_key": "backswing_downswing_ratio", "value": 2.95, "confidence": 0.95},
        {"metric_key": "finish_hold_ms", "value": 1200.0, "confidence": 0.90},
        {"metric_key": "finish_sway_ratio", "value": 0.03, "confidence": 0.90},
    ]
    res = compute_swing_score(metrics=full_metrics, min_coverage_gate=0.70)
    assert res.overall_nullable is not None
    assert res.coverage == 1.0, "完整覆蓋率應為 100%"
    assert 80 <= res.overall_nullable <= 100, f"得分應在優質區間: {res.overall_nullable}"

    # 驗證透明度揭露
    for k in ["spine_tilt_stability", "head_stability", "tempo_consistency", "finish_balance"]:
        sub = res.subscores[k]
        assert sub["formula"] != "", f"{k} 必須包含計算公式"
        assert sub["how_calculated"] != "", f"{k} 必須包含「怎麼算的？」繁中說明"
        assert "confidence" in sub, f"{k} 必須包含信心度"


def test_rank_session_swings_four_boards():
    """驗證 4 榜多維排序正確區分最優動作、最佳節奏與收桿標竿球。"""
    swings = [
        {
            "id": "swing-1",
            "sequence_no": 1,
            "label": "valid_swing",
            "overall_score": 92.0,
            "coverage_ratio": 1.0,
            "subscores": {
                "spine_tilt_stability": {"score": 95.0},
                "tempo_consistency": {"score": 88.0, "raw_value": 2.8},
                "finish_balance": {"score": 90.0},
            },
        },
        {
            "id": "swing-2",
            "sequence_no": 2,
            "label": "valid_swing",
            "overall_score": 84.0,
            "coverage_ratio": 1.0,
            "subscores": {
                "spine_tilt_stability": {"score": 75.0},
                "tempo_consistency": {"score": 100.0, "raw_value": 3.01},  # 節奏近乎完美 3.0:1
                "finish_balance": {"score": 80.0},
            },
        },
        {
            "id": "swing-3",
            "sequence_no": 3,
            "label": "valid_swing",
            "overall_score": 62.0,
            "coverage_ratio": 1.0,
            "subscores": {
                "spine_tilt_stability": {"score": 50.0},
                "tempo_consistency": {"score": 60.0, "raw_value": 1.8},
                "finish_balance": {"score": 55.0},
            },
        },
    ]

    ranked = rank_session_swings(swings)
    assert ranked["posture"][0]["segment_id"] == "swing-1", "姿勢最佳應為第 1 球"
    assert ranked["tempo"][0]["segment_id"] == "swing-2", "最佳節奏應為第 2 球"
    assert ranked["finish"][0]["segment_id"] == "swing-1", "收桿最佳應為第 1 球"
