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
    score_version: str = "score-v2",
    min_confidence: float = 0.50,
    min_coverage_gate: float = 0.70,
) -> ScoreComputeResult:
    """
    計算可解釋、確定性 (deterministic) 之內部 2D DTL 動作指標分數 (score-v2)。
    升級項目 (score-v2)：
    1. 將單球上下桿路徑間隙 (single_swing_plane_gap_ratio) 與多球重複性 (repeatability) 分開。
    2. IG 視覺呈現分數改採真實關鍵點出界檢核 (framing_score) 與真實片段前後邊界緩衝 (clip_margin_score)。
    3. 嚴格遵守最高誠信原則，不虛構球速、飛行距離或 3D 角度。
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

    # 3. 手部路徑與重複性 (path_repeatability, 20%)
    # 明確分開：單球上下桿路徑間隙 (single_swing_plane_gap_ratio) 與多球重複性 (session_path_repeatability)
    m_plane = m_map.get("single_swing_plane_gap_ratio") or m_map.get("hand_path_deviation_ratio")
    m_repeat = m_map.get("session_path_repeatability")

    has_plane = (
        m_plane
        and m_plane.get("value") is not None
        and float(m_plane.get("confidence", 0.0)) >= min_confidence
    )
    has_repeat = (
        m_repeat
        and m_repeat.get("value") is not None
        and float(m_repeat.get("confidence", 0.0)) >= min_confidence
    )

    if has_plane and has_repeat:
        dev_plane = float(m_plane["value"])  # type: ignore
        conf_plane = float(m_plane["confidence"])  # type: ignore
        dev_repeat = float(m_repeat["value"])  # type: ignore
        conf_repeat = float(m_repeat["confidence"])  # type: ignore
        s_plane = 100.0 if dev_plane <= 0.05 else _clip(100.0 - ((dev_plane - 0.05) / 0.20) * 75.0, 25.0, 100.0)
        s_repeat = 100.0 if dev_repeat <= 0.04 else _clip(100.0 - ((dev_repeat - 0.04) / 0.16) * 70.0, 30.0, 100.0)
        final_s_path = round(s_plane * 0.60 + s_repeat * 0.40, 1)
        final_conf = round(conf_plane * 0.60 + conf_repeat * 0.40, 3)
        how_calc = (
            f"融合單球上下桿手部平面差距 d={dev_plane:.3f}（佔 60%）與同場多球重複性偏差 r={dev_repeat:.3f}（佔 40%）；"
            "僅衡量手部 2D 投影軌跡，不代表真實桿頭路徑。"
        )
        raw_repr = round(dev_plane, 4)
    elif has_plane:
        dev_plane = float(m_plane["value"])  # type: ignore
        conf_plane = float(m_plane["confidence"])  # type: ignore
        s_plane = 100.0 if dev_plane <= 0.05 else _clip(100.0 - ((dev_plane - 0.05) / 0.20) * 75.0, 25.0, 100.0)
        final_s_path = round(s_plane, 1)
        final_conf = round(conf_plane, 3)
        how_calc = (
            f"評估單球上下桿手腕 2D 平面間隙 gap={dev_plane:.3f}；"
            "gap ≤ 0.05 得 100 分（單球路徑穩定度，未結合多球重複性）。"
        )
        raw_repr = round(dev_plane, 4)
        dev_repeat = None
    elif has_repeat:
        dev_repeat = float(m_repeat["value"])  # type: ignore
        conf_repeat = float(m_repeat["confidence"])  # type: ignore
        s_repeat = 100.0 if dev_repeat <= 0.04 else _clip(100.0 - ((dev_repeat - 0.04) / 0.16) * 70.0, 30.0, 100.0)
        final_s_path = round(s_repeat, 1)
        final_conf = round(conf_repeat, 3)
        how_calc = f"評估同場多球手部中位數路徑重複性偏差 r={dev_repeat:.3f}（缺乏單球平面數據）。"
        raw_repr = round(dev_repeat, 4)
        dev_plane = None
    else:
        final_s_path = None
        final_conf = 0.0
        how_calc = "上下桿手腕關鍵點可見度不足，不予計分。"
        raw_repr = None
        dev_plane = None
        dev_repeat = None

    if final_s_path is not None:
        subscores["path_repeatability"] = {
            "label": "手部路徑間隙與重複性",
            "score": final_s_path,
            "weight": active_weights["path_repeatability"],
            "raw_value": raw_repr,
            "unit": "ratio",
            "confidence": final_conf,
            "formula": "clip(100 - max(0, dev - 0.05) / 0.20 * 75, 25, 100)",
            "how_calculated": how_calc,
            "details": {
                "single_swing_plane_gap": dev_plane,
                "session_repeatability": dev_repeat,
            },
        }
    else:
        subscores["path_repeatability"] = {
            "label": "手部路徑間隙與重複性",
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
    # 畫面完整 (真實入鏡檢核) 30% + 平穩收桿 25% + 節奏觀感 20% + 清晰度 15% + 起迄剪輯完整性 (真實時間碼邊界) 10%
    ig_visual_score: float | None = None

    # 1. 畫面完整度 (framing, 30%): 真實檢查是否頭腳出鏡或邊界遮擋
    oof_flags = q_meta.get("out_of_frame_flags") or []
    oof_penalty = len(oof_flags) * 20.0
    vis_ratio = q_meta.get("body_visibility_ratio")
    if vis_ratio is not None:
        base_framing = float(vis_ratio) * 100.0
        framing_score: float | None = _clip(base_framing - oof_penalty, 20.0, 100.0)
    elif coverage > 0.0:
        base_framing = float(coverage) * 100.0
        framing_score = _clip(base_framing - oof_penalty, 20.0, 100.0)
    else:
        framing_score = None

    # 2. 收桿平衡 (finish, 25%) 與 3. 節奏觀感 (tempo, 20%)
    fin_score = subscores["finish_balance"]["score"]
    tempo_score = subscores["tempo_consistency"]["score"]

    # 4. 畫質清晰度與相機晃動 (clarity, 15%)
    if q_meta.get("mean_sharpness") is not None:
        sharpness = float(q_meta["mean_sharpness"])
        cam_motion = float(q_meta.get("max_camera_motion", 0.0))
        clarity_score: float | None = _clip(min(100.0, 60.0 + sharpness * 0.4) - cam_motion * 250.0, 30.0, 100.0)
    else:
        clarity_score = None

    # 5. 起迄剪輯完整性 (clip_margin, 10%): 真實檢查準備動作前與收桿後的緩衝時間 (ms)
    pre_m_raw = q_meta.get("clip_pre_margin_ms") or (m_map.get("pre_margin_ms", {}).get("value"))
    post_m_raw = q_meta.get("clip_post_margin_ms") or (m_map.get("post_margin_ms", {}).get("value"))
    pre_m: float | None = None
    post_m: float | None = None
    margin_score: float | None = None
    if pre_m_raw is not None and post_m_raw is not None:
        p_pre = float(pre_m_raw)
        p_post = float(post_m_raw)
        pre_m = p_pre
        post_m = p_post
        min_margin = min(p_pre, p_post)
        if min_margin >= 300.0:
            margin_score = 100.0
        elif min_margin <= 50.0:
            margin_score = 30.0
        else:
            margin_score = _clip(30.0 + ((min_margin - 50.0) / 250.0) * 70.0, 30.0, 100.0)

    ig_components: list[tuple[str, float | None, float]] = [
        ("framing_30", framing_score, 0.30),
        ("finish_25", fin_score, 0.25),
        ("tempo_20", tempo_score, 0.20),
        ("clarity_15", clarity_score, 0.15),
        ("clip_margin_10", margin_score, 0.10),
    ]

    valid_ig_weight = sum(w for _, s, w in ig_components if s is not None)
    if valid_ig_weight >= 0.70:
        ig_weighted_sum = sum(float(s) * w for _, s, w in ig_components if s is not None)
        ig_visual_score = round(ig_weighted_sum / valid_ig_weight, 1)

    subscores["ig_visual_breakdown"] = {
        "framing_30": round(framing_score, 1) if framing_score is not None else None,
        "finish_25": round(fin_score, 1) if fin_score is not None else None,
        "tempo_20": round(tempo_score, 1) if tempo_score is not None else None,
        "clarity_15": round(clarity_score, 1) if clarity_score is not None else None,
        "clip_margin_10": round(margin_score, 1) if margin_score is not None else None,
        "valid_weight_coverage": round(valid_ig_weight, 2),
        "details": {
            "out_of_frame_flags": oof_flags,
            "pre_margin_ms": round(pre_m, 1) if pre_m is not None else None,
            "post_margin_ms": round(post_m, 1) if post_m is not None else None,
        },
        "note": "IG 精選分數僅評估畫面完整度、收桿平穩、真實剪輯緩衝與視覺流暢度，不代表實際擊球距離或球速。",
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
    嚴格過濾：各分類排行榜僅納入具有真實分項數據之球，禁止使用替代分數冒充。
    """
    favs = favorites or []
    excluded_ids = {f["segment_id"] for f in favs if f.get("category") == "excluded"}

    base_eligible = [
        s
        for s in swing_items
        if s.get("id") not in excluded_ids
        and s.get("label") == "valid_swing"
        and s.get("review_status") != "rejected"
    ]

    def _posture_reason(s: dict[str, Any], score: float | None) -> str:
        spine = ((s.get("subscores") or {}).get("spine_tilt_stability") or {})
        delta = spine.get("raw_value")
        if delta is not None:
            return f"軀幹前傾穩定 Δ={delta:.1f}°，動作總分 {score or 'N/A'} 分"
        return f"綜合動作檢核評定 {score or 'N/A'} 分"

    def _tempo_reason(s: dict[str, Any], score: float | None) -> str:
        tempo = ((s.get("subscores") or {}).get("tempo_consistency") or {})
        ratio = tempo.get("raw_value")
        if ratio is not None:
            return f"上下桿時間比 {ratio:.2f}:1（標準 3.0:1），節奏得分 {score or 'N/A'} 分"
        return f"揮桿節奏得分 {score or 'N/A'} 分"

    def _finish_reason(s: dict[str, Any], score: float | None) -> str:
        fin = ((s.get("subscores") or {}).get("finish_balance") or {})
        hold = fin.get("hold_ms")
        sway = fin.get("raw_value")
        if hold is not None and sway is not None:
            return f"收桿停頓 {hold:.0f}ms、晃動比 {sway:.3f}，收桿得分 {score or 'N/A'} 分"
        return f"收桿姿勢得分 {score or 'N/A'} 分"

    def _ig_reason(s: dict[str, Any], score: float | None) -> str:
        bd = ((s.get("subscores") or {}).get("ig_visual_breakdown") or {})
        frm = bd.get("framing_30")
        if frm is not None:
            return f"畫面完整度 {frm} 分、收桿平穩，IG 吸睛分 {score or 'N/A'} 分"
        return f"IG 社群短影音推薦分 {score or 'N/A'} 分"

    def _build_category_rank(
        cat_name: str,
        score_getter: Any,
        reason_builder: Any,
    ) -> list[dict[str, Any]]:
        manual_overrides = {
            f["segment_id"]: (f.get("rank_override") or 1)
            for f in favs
            if f.get("category") == cat_name
        }

        # 嚴格過濾：該球在此分類必須具有真實有效分數 (not None)，或有手動置頂
        cat_candidates = [
            s
            for s in base_eligible
            if score_getter(s) is not None or str(s.get("id")) in manual_overrides
        ]

        def sort_key(item: dict[str, Any]) -> tuple[int, int, float, float, int]:
            seg_id = str(item["id"])
            is_manual = 0 if seg_id in manual_overrides else 1
            manual_rank = int(manual_overrides.get(seg_id, 999))
            primary_score = float(score_getter(item) or 0.0)
            conf = float(item.get("confidence") or 0.0)
            # tie-breaker: sequence_no 越小越優先
            seq = int(item.get("sequence_no") or 9999)
            return (is_manual, manual_rank, -primary_score, -conf, seq)

        ranked = sorted(cat_candidates, key=sort_key)
        output: list[dict[str, Any]] = []
        for idx, it in enumerate(ranked[:top_k], start=1):
            score_val = score_getter(it)
            output.append(
                {
                    "rank": idx,
                    "segment_id": it["id"],
                    "sequence_no": it.get("sequence_no"),
                    "start_ms": it.get("start_ms"),
                    "end_ms": it.get("end_ms"),
                    "category_score": score_val,
                    "overall_score": it.get("overall_score"),
                    "confidence": it.get("confidence"),
                    "reason": reason_builder(it, score_val),
                    "manual_pinned": str(it["id"]) in manual_overrides,
                }
            )
        return output

    return {
        "posture": _build_category_rank(
            "posture",
            lambda x: x.get("overall_score"),
            _posture_reason,
        ),
        "tempo": _build_category_rank(
            "tempo",
            lambda x: ((x.get("subscores") or {}).get("tempo_consistency") or {}).get("score"),
            _tempo_reason,
        ),
        "finish": _build_category_rank(
            "finish",
            lambda x: ((x.get("subscores") or {}).get("finish_balance") or {}).get("score"),
            _finish_reason,
        ),
        "ig": _build_category_rank(
            "ig",
            lambda x: x.get("ig_visual_score"),
            _ig_reason,
        ),
    }
