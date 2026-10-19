from dataclasses import dataclass
from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "spine_tilt_stability": 25.0,
    "head_stability": 15.0,
    "path_repeatability": 20.0,
    "tempo_consistency": 20.0,
    "finish_balance": 20.0,
}


def _clip(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, val))


@dataclass
class ScoreComputeResult:
    score_version: str
    overall_nullable: float | None
    ig_visual_score: float | None
    partial_score: bool
    coverage: float
    confidence: float
    subscores: dict[str, Any]
    explanation: str


def compute_swing_score(
    metrics: list[dict[str, Any]],
    quality_metadata: dict[str, Any] | None = None,
    weights: dict[str, float] | None = None,
    score_version: str = "score-v1",
    min_confidence: float = 0.50,
    min_coverage_gate: float = 0.70,
) -> ScoreComputeResult:
    """
    計算可解釋、確定性 (deterministic) 之內部 2D DTL 動作指標分數 (score-v1)。
    嚴格遵守：
    1. 不虛構球速、飛行距離、甜蜜點或 3D 旋轉角。
    2. 任一分項若缺值或 confidence < min_confidence，該分項為 None。
    3. 有效分項權重覆蓋率 < 70% 時，overall_nullable 必為 None（「無法可靠評分」）。
    4. 每個分項皆附帶公式、輸入值、權重、信心度與「怎麼算的？」繁體中文說明。
    """
    active_weights = dict(DEFAULT_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in active_weights and v >= 0:
                active_weights[k] = float(v)

    total_weight = sum(active_weights.values()) or 100.0
    m_map: dict[str, dict[str, Any]] = {m["metric_key"]: m for m in metrics}
    q_meta = quality_metadata or {}

    subscores: dict[str, Any] = {}

    # 1. 軀幹前傾穩定 (spine_tilt_stability, 25%)
    m_spine = m_map.get("spine_tilt_delta_deg")
    if (
        m_spine
        and m_spine.get("value") is not None
        and float(m_spine.get("confidence", 0.0)) >= min_confidence
    ):
        delta_deg = float(m_spine["value"])
        c_spine = float(m_spine["confidence"])
        if delta_deg <= 2.5:
            s_spine = 100.0
        else:
            s_spine = _clip(100.0 - ((delta_deg - 2.5) / 12.5) * 80.0, 20.0, 100.0)
        subscores["spine_tilt_stability"] = {
            "label": "軀幹前傾穩定",
            "score": round(s_spine, 1),
            "weight": active_weights["spine_tilt_stability"],
            "raw_value": round(delta_deg, 2),
            "unit": "deg_2d",
            "confidence": round(c_spine, 3),
            "formula": "clip(100 - max(0, delta_deg - 2.5) / 12.5 * 80, 20, 100)",
            "how_calculated": (
                f"比較準備姿勢 (Address) 與疑似擊球瞬間之 2D 軀幹前傾角度差 Δ={delta_deg:.2f}°；"
                "Δ ≤ 2.5° 得 100 分，超過則隨起身/下沉幅度線性扣分。"
            ),
        }
    else:
        subscores["spine_tilt_stability"] = {
            "label": "軀幹前傾穩定",
            "score": None,
            "weight": active_weights["spine_tilt_stability"],
            "raw_value": None,
            "unit": "deg_2d",
            "confidence": 0.0,
            "formula": "N/A (關鍵點可見度不足)",
            "how_calculated": "肩部或髖部 2D 關鍵點於準備或擊球階段受遮擋或低光影響，不予計分。",
        }

    # 2. 頭部相對位移 (head_stability, 15%)
    m_head = m_map.get("head_displacement_ratio")
    if (
        m_head
        and m_head.get("value") is not None
        and float(m_head.get("confidence", 0.0)) >= min_confidence
    ):
        disp = float(m_head["value"])
        c_head = float(m_head["confidence"])
        if disp <= 0.06:
            s_head = 100.0
        else:
            s_head = _clip(100.0 - ((disp - 0.06) / 0.22) * 80.0, 20.0, 100.0)
        subscores["head_stability"] = {
            "label": "頭部相對位移",
            "score": round(s_head, 1),
            "weight": active_weights["head_stability"],
            "raw_value": round(disp, 4),
            "unit": "torso_ratio",
            "confidence": round(c_head, 3),
            "formula": "clip(100 - max(0, ratio - 0.06) / 0.22 * 80, 20, 100)",
            "how_calculated": (
                f"計算準備至擊球期間頭部相對於軀幹長度之最大 2D 位移比 r={disp:.3f}；"
                "r ≤ 0.06 得 100 分，位移越大扣分越多。"
            ),
        }
    else:
        subscores["head_stability"] = {
            "label": "頭部相對位移",
            "score": None,
            "weight": active_weights["head_stability"],
            "raw_value": None,
            "unit": "torso_ratio",
            "confidence": 0.0,
            "formula": "N/A (關鍵點可見度不足)",
            "how_calculated": "頭部或軀幹基準長度可見度不足，不予計分。",
        }

    # 3. 身體與手部軌跡重複性 (path_repeatability, 20%)
    m_path = m_map.get("hand_path_deviation_ratio")
    if (
        m_path
        and m_path.get("value") is not None
        and float(m_path.get("confidence", 0.0)) >= min_confidence
    ):
        dev = float(m_path["value"])
        c_path = float(m_path["confidence"])
        if dev <= 0.05:
            s_path = 100.0
        else:
            s_path = _clip(100.0 - ((dev - 0.05) / 0.20) * 75.0, 25.0, 100.0)
        subscores["path_repeatability"] = {
            "label": "身體與手部軌跡重複性",
            "score": round(s_path, 1),
            "weight": active_weights["path_repeatability"],
            "raw_value": round(dev, 4),
            "unit": "ratio",
            "confidence": round(c_path, 3),
            "formula": "clip(100 - max(0, dev - 0.05) / 0.20 * 75, 25, 100)",
            "how_calculated": (
                f"評估上下桿手腕 2D 路徑平面差距與同場中位數軌跡偏差 d={dev:.3f}；"
                "d ≤ 0.05 得 100 分（僅衡量手部 2D 投影，不代表真實桿頭路徑）。"
            ),
        }
    else:
        subscores["path_repeatability"] = {
            "label": "身體與手部軌跡重複性",
            "score": None,
            "weight": active_weights["path_repeatability"],
            "raw_value": None,
            "unit": "ratio",
            "confidence": 0.0,
            "formula": "N/A (關鍵點可見度不足)",
            "how_calculated": "上下桿手腕關鍵點可見度不足，不予計分。",
        }

    # 4. 上下桿節奏一致性 (tempo_consistency, 20%)
    m_tempo = m_map.get("backswing_downswing_ratio")
    if (
        m_tempo
        and m_tempo.get("value") is not None
        and float(m_tempo.get("confidence", 0.0)) >= min_confidence
    ):
        ratio = float(m_tempo["value"])
        c_tempo = float(m_tempo["confidence"])
        err = abs(ratio - 3.0)
        if err <= 0.25:
            s_tempo = 100.0
        else:
            s_tempo = _clip(100.0 - ((err - 0.25) / 1.55) * 80.0, 20.0, 100.0)
        subscores["tempo_consistency"] = {
            "label": "上下桿節奏一致性",
            "score": round(s_tempo, 1),
            "weight": active_weights["tempo_consistency"],
            "raw_value": round(ratio, 2),
            "unit": "ratio",
            "confidence": round(c_tempo, 3),
            "formula": "clip(100 - max(0, |ratio - 3.0| - 0.25) / 1.55 * 80, 20, 100)",
            "how_calculated": (
                f"依上桿時間與下桿時間比值 ratio={ratio:.2f}:1 與基準 3.0:1 之差距計算；"
                "差距 ≤ 0.25 得 100 分（基於 2D 階段時間碼估計）。"
            ),
        }
    else:
        subscores["tempo_consistency"] = {
            "label": "上下桿節奏一致性",
            "score": None,
            "weight": active_weights["tempo_consistency"],
            "raw_value": None,
            "unit": "ratio",
            "confidence": 0.0,
            "formula": "N/A (階段事件不完整)",
            "how_calculated": "無法可靠定位 Takeaway、Top 或疑似擊球時間點，不予計分。",
        }

    # 5. 收桿姿勢穩定 (finish_balance, 20%)
    m_hold = m_map.get("finish_hold_ms")
    m_sway = m_map.get("finish_sway_ratio")
    if (
        m_hold
        and m_sway
        and m_hold.get("value") is not None
        and m_sway.get("value") is not None
        and min(float(m_hold.get("confidence", 0.0)), float(m_sway.get("confidence", 0.0))) >= min_confidence
    ):
        hold_ms = float(m_hold["value"])
        sway = float(m_sway["value"])
        c_fin = min(float(m_hold["confidence"]), float(m_sway["confidence"]))
        hold_score = _clip((hold_ms / 1100.0) * 100.0, 35.0, 100.0)
        sway_penalty = 0.0 if sway <= 0.04 else min(45.0, ((sway - 0.04) / 0.16) * 45.0)
        s_fin = _clip(hold_score - sway_penalty, 20.0, 100.0)
        subscores["finish_balance"] = {
            "label": "收桿姿勢穩定",
            "score": round(s_fin, 1),
            "weight": active_weights["finish_balance"],
            "raw_value": round(sway, 4),
            "hold_ms": round(hold_ms, 0),
            "unit": "sway_ratio",
            "confidence": round(c_fin, 3),
            "formula": "clip(min(100, hold_ms/1100*100) - max(0, sway-0.04)/0.16*45, 20, 100)",
            "how_calculated": (
                f"收桿停留時間 {hold_ms:.0f}ms、下半身 2D 晃動比 {sway:.3f}；"
                "停留超過 1100ms 且晃動 ≤ 0.04 得滿分。"
            ),
        }
    else:
        subscores["finish_balance"] = {
            "label": "收桿姿勢穩定",
            "score": None,
            "weight": active_weights["finish_balance"],
            "raw_value": None,
            "unit": "sway_ratio",
            "confidence": 0.0,
            "formula": "N/A (收桿關鍵點可見度不足)",
            "how_calculated": "收桿階段身體出鏡或關鍵點信心不足，不予計分。",
        }

    # 計算有效覆蓋率與總分
    valid_items = [item for item in subscores.values() if item["score"] is not None]
    valid_weight_sum = sum(float(item["weight"]) for item in valid_items)
    coverage = round(valid_weight_sum / total_weight, 4)

    if not valid_items:
        overall_conf = 0.0
    else:
        overall_conf = round(
            sum(float(item["confidence"]) * float(item["weight"]) for item in valid_items)
            / max(1e-6, valid_weight_sum),
            3,
        )

    partial_score = coverage < 0.999
    if coverage < min_coverage_gate:
        overall_nullable = None
        explanation = (
            f"無法可靠評分：目前有效動作分項權重覆蓋率為 {coverage * 100:.0f}%（低於 70% 安全門檻）。"
            "請確認拍攝光線充足、全身完整入鏡且無遮擋。"
        )
    else:
        weighted_sum = sum(float(item["score"]) * float(item["weight"]) for item in valid_items)
        overall_nullable = round(weighted_sum / valid_weight_sum, 1)
        if partial_score:
            explanation = (
                f"內部動作檢核總分 {overall_nullable} 分（部分評分，有效覆蓋率 {coverage * 100:.0f}%，"
                f"演算法版本 {score_version}）。此分數僅反映 2D 後方視角動作穩定度，不代表實際擊球距離或球路。"
            )
        else:
            explanation = (
                f"內部動作檢核總分 {overall_nullable} 分（完整覆蓋率 100%，演算法版本 {score_version}）。"
                "此分數僅反映 2D 後方視角動作穩定度，不代表實際擊球距離或球路。"
            )

    # 計算獨立之 IG 視覺呈現分數 (ig_visual_score)
    # 畫面完整 30% + 平穩收桿 25% + 節奏觀感 20% + 清晰度 15% + 起迄剪輯完整性 10%
    ig_visual_score: float | None = None
    if coverage >= min_coverage_gate:
        framing_score = min(100.0, coverage * 100.0)
        fin_score = float(subscores["finish_balance"]["score"] or 70.0)
        tempo_score = float(subscores["tempo_consistency"]["score"] or 75.0)
        sharpness = float(q_meta.get("mean_sharpness", 80.0))
        cam_motion = float(q_meta.get("max_camera_motion", 0.0))
        clarity_score = _clip(min(100.0, 60.0 + sharpness * 0.4) - cam_motion * 250.0, 30.0, 100.0)
        margin_score = 95.0 if len(valid_items) >= 4 else 75.0
        ig_raw = (
            framing_score * 0.30
            + fin_score * 0.25
            + tempo_score * 0.20
            + clarity_score * 0.15
            + margin_score * 0.10
        )
        ig_visual_score = round(ig_raw, 1)
        subscores["ig_visual_breakdown"] = {
            "framing_30": round(framing_score, 1),
            "finish_25": round(fin_score, 1),
            "tempo_20": round(tempo_score, 1),
            "clarity_15": round(clarity_score, 1),
            "clip_margin_10": round(margin_score, 1),
            "note": "IG 精選分數僅評估畫面完整度、收桿平穩與視覺流暢度，不代表實際擊球距離或球速。",
        }

    return ScoreComputeResult(
        score_version=score_version,
        overall_nullable=overall_nullable,
        ig_visual_score=ig_visual_score,
        partial_score=partial_score,
        coverage=coverage,
        confidence=overall_conf,
        subscores=subscores,
        explanation=explanation,
    )


def rank_session_swings(
    swing_items: list[dict[str, Any]],
    favorites: list[dict[str, Any]] | None = None,
    top_k: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """
    對同場有效揮桿進行四大類別獨立排序：
    - posture (姿勢最佳：依 overall_nullable，次要依 spine_tilt_stability)
    - tempo (節奏最佳：依 tempo_consistency 分數)
    - finish (收桿最佳：依 finish_balance 分數)
    - ig (IG 視覺呈現最佳：依 ig_visual_score)
    支援使用者手動排除 (category='excluded') 與手動置頂/指定排名 (rank_override)。
    """
    favs = favorites or []
    excluded_ids = {f["segment_id"] for f in favs if f.get("category") == "excluded"}

    eligible = [
        s
        for s in swing_items
        if s.get("id") not in excluded_ids
        and s.get("label") == "valid_swing"
        and s.get("review_status") != "rejected"
        and s.get("overall_score") is not None
    ]

    def _build_category_rank(
        cat_name: str, score_getter: Any
    ) -> list[dict[str, Any]]:
        manual_overrides = {
            f["segment_id"]: (f.get("rank_override") or 1)
            for f in favs
            if f.get("category") == cat_name
        }

        def sort_key(item: dict[str, Any]) -> tuple[int, int, float, float, int]:
            seg_id = str(item["id"])
            is_manual = 0 if seg_id in manual_overrides else 1
            manual_rank = int(manual_overrides.get(seg_id, 999))
            primary_score = float(score_getter(item) or 0.0)
            conf = float(item.get("confidence") or 0.0)
            # tie-breaker: sequence_no 越小越優先
            seq = int(item.get("sequence_no") or 9999)
            return (is_manual, manual_rank, -primary_score, -conf, seq)

        ranked = sorted(eligible, key=sort_key)
        output: list[dict[str, Any]] = []
        for idx, it in enumerate(ranked[:top_k], start=1):
            output.append(
                {
                    "rank": idx,
                    "segment_id": it["id"],
                    "sequence_no": it.get("sequence_no"),
                    "start_ms": it.get("start_ms"),
                    "end_ms": it.get("end_ms"),
                    "category_score": score_getter(it),
                    "overall_score": it.get("overall_score"),
                    "confidence": it.get("confidence"),
                    "manual_pinned": it["id"] in manual_overrides,
                }
            )
        return output

    return {
        "posture": _build_category_rank("posture", lambda x: x.get("overall_score")),
        "tempo": _build_category_rank(
            "tempo",
            lambda x: ((x.get("subscores") or {}).get("tempo_consistency") or {}).get("score")
            or x.get("overall_score"),
        ),
        "finish": _build_category_rank(
            "finish",
            lambda x: ((x.get("subscores") or {}).get("finish_balance") or {}).get("score")
            or x.get("overall_score"),
        ),
        "ig": _build_category_rank("ig", lambda x: x.get("ig_visual_score") or x.get("overall_score")),
    }
