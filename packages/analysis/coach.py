import json
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field


class CoachObservation(BaseModel):
    title: str
    detail: str
    segment_id: str | None = None
    time_ms: int | None = None
    metric_key: str | None = None
    metric_value: float | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class CoachDrill(BaseModel):
    focus_area: str
    action_cue: str
    drill_steps: str
    target_metric: str


class CoachReport(BaseModel):
    provider: str
    model: str
    llm_enabled: bool
    notice: str
    summary: str
    observations: list[CoachObservation]
    priority_fixes: list[CoachDrill]
    uncertainties: list[str]


class GolfCoachProvider(Protocol):
    async def generate_feedback(
        self,
        session_summary: dict[str, Any],
        swing_evidence: list[dict[str, Any]],
    ) -> CoachReport: ...


FORBIDDEN_HALLUCINATION_TERMS = (
    "碼數",
    "飛行距離",
    "球速",
    "桿頭速度",
    "smash factor",
    "launch angle",
    "spin rate",
)


class RuleBasedCoachProvider:
    """
    預設無金鑰規則式教練 (`LLM_PROVIDER=none`)。
    完全不發送任何外網請求；依據客觀 2D 量測指標、時間碼與變異數產出繁體中文回饋與下次練習課表。
    """

    async def generate_feedback(
        self,
        session_summary: dict[str, Any],
        swing_evidence: list[dict[str, Any]],
    ) -> CoachReport:
        valid_swings = [s for s in swing_evidence if s.get("label") == "valid_swing"]
        observations: list[CoachObservation] = []
        drills: list[CoachDrill] = []
        uncertainties: list[str] = [
            "2D 後方（DTL）單視角影像無法量測真實球飛行距離、球速、桿頭速度、桿面角與甜蜜點接觸品質。",
            "疑似擊球時間（impact_estimated_ms）由手腕最低點與運動峰值推算，不等同雷達實測觸球。",
        ]

        if not valid_swings:
            return CoachReport(
                provider="none",
                model="rule-coach-v1",
                llm_enabled=False,
                notice="進階 AI 教練尚未設定（目前使用內建規則式證據分析引擎，無需外部 API Key）。",
                summary="本場次尚無通過覆蓋率門檻之有效揮桿可供建立趨勢，建議檢查拍攝光線與全身入鏡完整性。",
                observations=[],
                priority_fixes=[
                    CoachDrill(
                        focus_area="拍攝架設品質",
                        action_cue="將 iPhone 固定於手部高度、正對目標線後方 2.5–3 公尺處",
                        drill_steps="確認準備姿勢至收桿全身與球桿皆在畫面內，避免逆光或他人走入鏡頭。",
                        target_metric="coverage >= 0.85",
                    )
                ],
                uncertainties=uncertainties,
            )

        # 尋找最弱分項與對應代表球及時間碼
        subscore_keys = [
            ("spine_tilt_stability", "軀幹前傾穩定", "spine_tilt_delta_deg"),
            ("head_stability", "頭部相對位移", "head_displacement_ratio"),
            ("path_repeatability", "手部 2D 路徑重複性", "hand_path_deviation_ratio"),
            ("tempo_consistency", "上下桿節奏一致性", "backswing_downswing_ratio"),
            ("finish_balance", "收桿姿勢穩定", "finish_sway_ratio"),
        ]

        weakest_items: list[tuple[float, str, str, str, dict[str, Any]]] = []
        for skey, slabel, mkey in subscore_keys:
            scored_swings = [
                s
                for s in valid_swings
                if ((s.get("subscores") or {}).get(skey) or {}).get("score") is not None
            ]
            if scored_swings:
                worst_swing = min(
                    scored_swings,
                    key=lambda x: float(((x.get("subscores") or {}).get(skey) or {}).get("score", 100.0)),
                )
                sub_info = (worst_swing.get("subscores") or {})[skey]
                avg_val = sum(
                    float(((x.get("subscores") or {}).get(skey) or {}).get("score", 0.0))
                    for x in scored_swings
                ) / len(scored_swings)
                weakest_items.append((avg_val, skey, slabel, mkey, worst_swing))
                ev_time = worst_swing.get("impact_time_ms") or worst_swing.get("top_time_ms") or worst_swing.get("start_ms")
                observations.append(
                    CoachObservation(
                        title=f"{slabel}（場次平均 {avg_val:.1f} 分）",
                        detail=str(sub_info.get("how_calculated", "")),
                        segment_id=str(worst_swing.get("id")),
                        time_ms=int(ev_time) if ev_time is not None else None,
                        metric_key=mkey,
                        metric_value=sub_info.get("raw_value"),
                        confidence=float(sub_info.get("confidence", 0.8)),
                    )
                )

        weakest_items.sort(key=lambda x: x[0])
        for _, skey, slabel, mkey, w_swing in weakest_items[:2]:
            ref_time = w_swing.get("impact_time_ms") or w_swing.get("start_ms") or 0
            if skey == "spine_tilt_stability":
                drills.append(
                    CoachDrill(
                        focus_area=f"維持軀幹前傾角（參考第 #{w_swing.get('sequence_no')} 球 @ {ref_time}ms）",
                        action_cue="下桿啟動時保持臀部向後維持空間，避免提早起身（Early Extension）",
                        drill_steps="練習場慢速半揮桿 10 球：在球包或椅背輕貼臀部後方，感受下桿至釋放期間臀部不離開接觸面。",
                        target_metric="spine_tilt_delta_deg <= 4.0°",
                    )
                )
            elif skey == "tempo_consistency":
                drills.append(
                    CoachDrill(
                        focus_area=f"穩定上下桿節奏比（參考第 #{w_swing.get('sequence_no')} 球 @ {ref_time}ms）",
                        action_cue="建立約 3:1 的上桿與下桿時間比例，避免上桿過急或頂點急促下砸",
                        drill_steps="使用默數節拍法（上桿默數 1-2-3 到頂點，下桿數 1 通過擊球區），連續執行 5 次空揮與 5 次實擊對照。",
                        target_metric="backswing_downswing_ratio 介於 2.7 ~ 3.3",
                    )
                )
            elif skey == "head_stability":
                drills.append(
                    CoachDrill(
                        focus_area=f"減少準備至擊球期間之頭部高度起伏（參考第 #{w_swing.get('sequence_no')} 球 @ {ref_time}ms）",
                        action_cue="以胸椎旋轉帶動上桿，保持視線與頸部軸心高度穩定",
                        drill_steps="採用 7 號鐵桿 70% 力道揮桿，專注於上桿頂點至擊球瞬間雙眼高度不大幅上下移動。",
                        target_metric="head_displacement_ratio <= 0.10",
                    )
                )
            else:
                drills.append(
                    CoachDrill(
                        focus_area=f"強化{slabel}（參考第 #{w_swing.get('sequence_no')} 球 @ {ref_time}ms）",
                        action_cue="收桿後維持平衡停留 2 秒，檢視重心是否完全轉移至前腳",
                        drill_steps="每球擊出後強制保持收桿姿勢默數 2 秒不移動雙腳，連續完成 10 球。",
                        target_metric=f"{mkey} 穩定度提升",
                    )
                )

        avg_overall = session_summary.get("average_overall_score")
        summary_text = (
            f"本場次共分析 {len(valid_swings)} 記有效揮桿"
            + (f"，場次平均內部動作指標為 {avg_overall:.1f} 分。" if avg_overall is not None else "。")
            + "系統已依各球實際時間碼標記優先改善項目與下一場練習課表。"
        )

        return CoachReport(
            provider="none",
            model="rule-coach-v1",
            llm_enabled=False,
            notice="進階 AI 教練尚未設定（目前顯示內建規則式證據分析，無需外部 API Key）。",
            summary=summary_text,
            observations=observations[:4],
            priority_fixes=drills[:2],
            uncertainties=uncertainties,
        )


class OpenAICompatibleCoachProvider:
    """
    相容 OpenAI Chat Completions 之可插拔 LLM 教練 Provider。
    具備：
    - 嚴格系統提示詞（禁止推斷球速、距離、球路與 3D 未感測角度）。
    - Pydantic 結構化驗證與違規詞彙攔截。
    - Timeout 與錯誤安全降級（若外部 API 失敗或預算為 0 則自動退回 RuleBasedCoachProvider，絕不中斷分析）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        max_budget_usd: float = 1.0,
        timeout_sec: float = 12.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_budget_usd = max_budget_usd
        self.timeout_sec = timeout_sec
        self.transport = transport
        self.fallback = RuleBasedCoachProvider()

    async def generate_feedback(
        self,
        session_summary: dict[str, Any],
        swing_evidence: list[dict[str, Any]],
    ) -> CoachReport:
        base_report = await self.fallback.generate_feedback(session_summary, swing_evidence)
        if not self.api_key or self.max_budget_usd <= 0:
            return base_report

        system_prompt = (
            "你是 Golf Swing Lab 的專業高爾夫 2D 後方視角（DTL）動作分析教練。"
            "請一律使用繁體中文（台灣）回答，並輸出符合 CoachReport schema 的 JSON。"
            "嚴格禁止編造或推論：球飛行距離、球速、桿頭速度、甜蜜點、桿面角、3D 旋轉角度或實際球路。"
            "每個建議都必須引用輸入資料中的 segment_id、time_ms 與 metric_key。"
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "session_summary": session_summary,
                            "swing_evidence": swing_evidence[:10],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_sec, transport=self.transport) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                parsed["provider"] = "openai-compatible"
                parsed["model"] = self.model
                parsed["llm_enabled"] = True
                parsed.setdefault("notice", f"由外部 LLM ({self.model}) 依 2D 量測證據生成。")
                report = CoachReport.model_validate(parsed)

                # 檢查是否違反誠信原則（出現未授權之距離/球速臆測）
                combined_text = (
                    report.summary
                    + " ".join(o.detail for o in report.observations)
                    + " ".join(d.action_cue + d.drill_steps for d in report.priority_fixes)
                ).lower()
                for forbidden in FORBIDDEN_HALLUCINATION_TERMS:
                    if forbidden.lower() in combined_text:
                        raise ValueError(f"LLM 輸出包含禁止臆測之物理名詞: {forbidden}")
                return report
        except Exception:
            # 外部 API 超時、驗證失敗或違規時，安全退回規則式報告
            return base_report
