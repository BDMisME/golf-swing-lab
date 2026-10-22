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


def test_scoring_no_synthetic_fallbacks_when_data_missing():
    """驗證當關鍵可觀測資料缺失時，嚴禁使用 70.0/75.0 假分數，IG 分數如實為 None。"""
    # 僅有軀幹前傾和頭部位移（共 40% 權重），缺少路徑、節奏與收桿
    partial_metrics = [
        {"metric_key": "spine_tilt_delta_deg", "value": 2.1, "confidence": 0.95},
        {"metric_key": "head_displacement_ratio", "value": 0.04, "confidence": 0.90},
    ]
    res = compute_swing_score(metrics=partial_metrics, min_coverage_gate=0.70)
    assert res.overall_nullable is None, "未達 70% 動作門檻不得給總分"
    assert res.subscores["path_repeatability"]["score"] is None
    assert res.subscores["tempo_consistency"]["score"] is None
    assert res.subscores["finish_balance"]["score"] is None
    # 由於缺少收桿與節奏，IG 視覺有效權重僅 30%（低於 70% 門檻），IG 分數必須為 None
    assert res.ig_visual_score is None, "IG 分數缺少足夠觀測數據時必須為 None，絕不使用 fallback"
    assert res.subscores["ig_visual_breakdown"]["valid_weight_coverage"] < 0.70


def test_rank_session_swings_strict_filtering_and_reasons():
    """驗證排行榜各榜單只納入具備該指標真實數據之片段，絕不拿 overall_score 頂替，且包含詳細 reason 與時間碼。"""
    swings = [
        {
            "id": "swing-a",
            "sequence_no": 1,
            "start_ms": 1000,
            "end_ms": 4000,
            "label": "valid_swing",
            "overall_score": 90.0,
            "confidence": 0.95,
            "subscores": {
                "spine_tilt_stability": {"score": 95.0, "raw_value": 2.1},
                # tempo_consistency 缺失 (None)
                "tempo_consistency": {"score": None, "raw_value": None},
                "finish_balance": {"score": 85.0, "hold_ms": 1200, "raw_value": 0.03},
                "ig_visual_breakdown": {"framing_30": 90.0},
            },
            "ig_visual_score": 88.0,
        },
        {
            "id": "swing-b",
            "sequence_no": 2,
            "start_ms": 5000,
            "end_ms": 8000,
            "label": "valid_swing",
            "overall_score": 75.0,
            "confidence": 0.90,
            "subscores": {
                "spine_tilt_stability": {"score": 70.0, "raw_value": 4.5},
                # 具備真實 tempo 分數
                "tempo_consistency": {"score": 98.0, "raw_value": 2.98},
                "finish_balance": {"score": None, "hold_ms": None, "raw_value": None},
            },
            "ig_visual_score": None,
        },
    ]

    ranked = rank_session_swings(swings)

    # 1. 姿勢榜：兩者都有 overall_score，swing-a (90) > swing-b (75)
    assert len(ranked["posture"]) == 2
    assert ranked["posture"][0]["segment_id"] == "swing-a"
    assert "軀幹前傾穩定" in ranked["posture"][0]["reason"]
    assert ranked["posture"][0]["start_ms"] == 1000

    # 2. 節奏榜：swing-a 的 tempo_consistency 為 None，絕對不能被納入 tempo 榜！
    assert len(ranked["tempo"]) == 1, "swing-a 缺少節奏數據，不得被 overall_score 頂替入榜"
    assert ranked["tempo"][0]["segment_id"] == "swing-b"
    assert ranked["tempo"][0]["category_score"] == 98.0
    assert "2.98:1" in ranked["tempo"][0]["reason"]

    # 3. 收桿榜：swing-b 的 finish_balance 為 None，不能入榜
    assert len(ranked["finish"]) == 1
    assert ranked["finish"][0]["segment_id"] == "swing-a"
    assert ranked["finish"][0]["category_score"] == 85.0
    assert "1200ms" in ranked["finish"][0]["reason"]

    # 4. IG 榜：swing-b 的 ig_visual_score 為 None，不能入榜
    assert len(ranked["ig"]) == 1
    assert ranked["ig"][0]["segment_id"] == "swing-a"
    assert ranked["ig"][0]["category_score"] == 88.0


def test_rank_session_swings_reliable_vs_disputed_exclusion():
    """
    P0-5 驗證排行榜安全過濾：
    1. 建立至少一球可靠、一球爭議的真實測試。
    2. 確保可靠球正常入榜，具有爭議 (unreliable_for_ranking/candidate_ambiguous/needs_review) 之球次嚴格排除於 posture 與 tempo 榜外。
    3. 確保排行榜非空 (若有合規球，禁止全空)。
    4. 手動置頂球 (manual_overrides) 必須明確標記 manual_pinned=True 且優先置頂。
    """
    swings = [
        # 球 1: 可靠球 (正常入榜)
        {
            "id": "swing-reliable-1",
            "sequence_no": 1,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "review_flags": [],
            "unreliable_for_ranking": False,
            "overall_score": 85.0,
            "confidence": 0.92,
            "subscores": {
                "spine_tilt_stability": {"score": 85.0, "raw_value": 2.5},
                "tempo_consistency": {"score": 88.0, "raw_value": 3.01},
                "finish_balance": {"score": 82.0, "hold_ms": 900, "raw_value": 0.04},
                "ig_visual_breakdown": {"framing_30": 85.0},
            },
            "ig_visual_score": 86.0,
        },
        # 球 2: 爭議球 (分數極高，但因具有候選雙峰爭議，必須被排除於 posture 與 tempo 榜外)
        {
            "id": "swing-disputed-2",
            "sequence_no": 2,
            "label": "valid_swing",
            "review_status": "needs_review",
            "review_flags": ["candidate_ambiguous"],
            "unreliable_for_ranking": True,
            "overall_score": 96.0,  # 分數極高
            "confidence": 0.70,
            "subscores": {
                "spine_tilt_stability": {"score": 96.0, "raw_value": 1.1},
                "tempo_consistency": {"score": 99.0, "raw_value": 3.00},
                "finish_balance": {"score": 95.0, "hold_ms": 1500, "raw_value": 0.02},
                "ig_visual_breakdown": {"framing_30": 95.0},
            },
            "ig_visual_score": 90.0,
        },
        # 球 3: 第二顆可靠球
        {
            "id": "swing-reliable-3",
            "sequence_no": 3,
            "label": "valid_swing",
            "review_status": "auto_accepted",
            "review_flags": [],
            "unreliable_for_ranking": False,
            "overall_score": 78.0,
            "confidence": 0.88,
            "subscores": {
                "spine_tilt_stability": {"score": 78.0, "raw_value": 3.2},
                "tempo_consistency": {"score": 80.0, "raw_value": 2.80},
                "finish_balance": {"score": 75.0, "hold_ms": 700, "raw_value": 0.05},
                "ig_visual_breakdown": {"framing_30": 80.0},
            },
            "ig_visual_score": 79.0,
        },
    ]

    # 設定手動置頂：使用者將 swing-reliable-3 在 posture 類別手動置頂為第一名
    favs = [
        {"segment_id": "swing-reliable-3", "category": "posture", "rank_override": 1}
    ]

    ranked = rank_session_swings(swings, favorites=favs, top_k=5)

    # 1. 確保排行榜非空
    assert len(ranked["posture"]) > 0, "posture 排行榜不可為空"
    assert len(ranked["tempo"]) > 0, "tempo 排行榜不可為空"
    assert len(ranked["finish"]) > 0, "finish 排行榜不可為空"
    assert len(ranked["ig"]) > 0, "ig 排行榜不可為空"

    # 2. 檢驗爭議球 (swing-disputed-2) 嚴格排除於 posture 與 tempo 榜外
    posture_ids = [it["segment_id"] for it in ranked["posture"]]
    tempo_ids = [it["segment_id"] for it in ranked["tempo"]]
    assert "swing-disputed-2" not in posture_ids, "爭議球 swing-disputed-2 必須排除於 posture 榜外！"
    assert "swing-disputed-2" not in tempo_ids, "爭議球 swing-disputed-2 必須排除於 tempo 榜外！"

    # 3. 檢驗可靠球正常入榜
    assert "swing-reliable-1" in posture_ids
    assert "swing-reliable-1" in tempo_ids

    # 4. 檢驗手動置頂球 (swing-reliable-3) 在 posture 榜排第一，且標記為 manual_pinned=True
    assert ranked["posture"][0]["segment_id"] == "swing-reliable-3"
    assert ranked["posture"][0]["manual_pinned"] is True, "手動置頂必須標記 manual_pinned=True"

    # 非手動置頂者 manual_pinned 必須為 False
    assert ranked["posture"][1]["segment_id"] == "swing-reliable-1"
    assert ranked["posture"][1]["manual_pinned"] is False


