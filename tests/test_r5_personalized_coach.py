"""R5: 個人化 AI 教練與規則式降級自動化測試 (tests/test_r5_personalized_coach.py)

驗收範疇：
1. 預設無金鑰規則式教練 (RuleBasedCoachProvider)：無外網完全獨立運行，依 2D 客觀指標產出繁中體感建議 (Feel vs Real)。
2. 多模態教練 (OpenAICompatibleCoachProvider / 豆包 Vision)：結構化 Prompt、4 關鍵影格傳輸與結構化輸出解析。
3. 最高誠信防偽安全網 (Anti-Hallucination Interception)：攔截未經測量之球速、桿速、距離等虛構數值。
4. 容錯降級機制 (Graceful Fallback)：網路逾時或 API 異常時平滑退回規則式報告，保證零崩潰。
"""

import json

import httpx
import pytest

from packages.analysis.coach import (
    FORBIDDEN_HALLUCINATION_TERMS,
    CoachReport,
    OpenAICompatibleCoachProvider,
    RuleBasedCoachProvider,
)


@pytest.mark.asyncio
async def test_rule_based_coach_offline_and_honest():
    """驗證規則式教練在完全無外網時 100% 穩定產出繁中報告且不捏造物理量。"""
    provider = RuleBasedCoachProvider()

    session_summary = {
        "session_id": "sess-test-01",
        "valid_swings": 5,
        "average_overall_score": 78.5,
    }

    swing_evidence = [
        {
            "id": f"sw-{i}",
            "sequence_no": i + 1,
            "label": "valid_swing",
            "overall_score": 75.0 + i,
            "impact_time_ms": 1000 + i * 2000,
            "subscores": {
                "spine_tilt_stability": {
                    "score": 70.0,
                    "raw_value": 7.5,
                    "confidence": 0.90,
                    "how_calculated": "脊柱前傾角於 Impact 變化 7.5°",
                },
                "head_stability": {
                    "score": 85.0,
                    "raw_value": 0.08,
                    "confidence": 0.88,
                    "how_calculated": "頭部位移為軀幹之 0.08 倍",
                },
                "tempo_consistency": {
                    "score": 65.0,
                    "raw_value": 4.1,
                    "confidence": 0.92,
                    "how_calculated": "上下桿節奏比 4.1:1（上桿偏慢或下桿過急）",
                },
            },
        }
        for i in range(5)
    ]

    report = await provider.generate_feedback(session_summary, swing_evidence)

    assert isinstance(report, CoachReport)
    assert report.provider == "none"
    assert report.llm_enabled is False
    assert len(report.observations) > 0
    assert len(report.priority_fixes) > 0

    # 驗證包含繁中體感建議
    report_text = (
        report.summary
        + " ".join(o.detail for o in report.observations)
        + " ".join(f.action_cue + f.drill_steps for f in report.priority_fixes)
    )
    assert any(term in report_text for term in ["軀幹", "前傾", "節奏", "默數", "臀部"]), "必須包含繁中高爾夫體感口訣"

    # 驗證最高誠信原則：絕不出現無法觀測之物理名詞
    for forbidden in FORBIDDEN_HALLUCINATION_TERMS:
        assert forbidden not in report_text, f"報告中不得包含無法觀測之詞彙: {forbidden}"


@pytest.mark.asyncio
async def test_openai_compatible_coach_with_mock_vision_and_contract(monkeypatch):
    """驗證多模態教練之結構化通訊協定與 Pydantic 解析（模擬後台開啟 LLM 時）。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "true")
    from apps.api.config import get_settings
    get_settings.cache_clear()
    mock_llm_response = {
        "summary": "選手站姿穩定度良好，但在下桿轉折點有提早伸展（Early Extension）趨勢，導致手部揮桿路徑偏外。",
        "observations": [
            {
                "title": "下桿骨盆早起伸展",
                "detail": "依據照片中 Impact 定格，臀部明顯離開原本的後方鉛線約 12% 軀幹長度，造成雙手釋放空間受壓迫。",
                "confidence": 0.92,
            }
        ],
        "priority_fixes": [
            {
                "focus_area": "維持臀部接觸面空間",
                "action_cue": "感覺下桿左側臀部向後緊貼玻璃牆",
                "drill_steps": "練習慢速半揮桿，背後輕貼球包，下桿時確保左臀維持接觸不前衝。",
                "target_metric": "spine_tilt_delta_deg <= 4.0°",
            }
        ],
        "uncertainties": [
            "2D 單鏡頭無法測量桿面開閉角及精確桿頭球速。",
        ],
    }

    # 自訂 Mock Transport 模擬 HTTP 回應
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        # 驗證多模態傳輸是否攜帶圖片
        messages = body.get("messages", [])
        user_msg = messages[-1]["content"]
        assert isinstance(user_msg, list), "多模態請求內容應為陣列"
        has_image = any(item.get("type") == "image_url" for item in user_msg)
        assert has_image is True, "必須包含定格截圖"

        resp_content = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(mock_llm_response, ensure_ascii=False)
                    }
                }
            ]
        }
        return httpx.Response(200, json=resp_content)

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatibleCoachProvider(
        api_key="test-api-key",
        model="doubao-seed-2.1-lite",
        transport=transport,
    )

    mock_keyframes = [
        {"frame_name": "address", "base64": "fake_base64_data_address"},
        {"frame_name": "impact", "base64": "fake_base64_data_impact"},
    ]

    report = await provider.generate_feedback(
        session_summary={"total_swings": 1},
        swing_evidence=[{"id": "sw-1", "overall_score": 75.0, "label": "valid_swing"}],
        keyframe_images=mock_keyframes,
    )

    assert report.provider == "openai-compatible"
    assert report.llm_enabled is True
    assert "Early Extension" in report.summary
    assert report.priority_fixes[0].focus_area == "維持臀部接觸面空間"


@pytest.mark.asyncio
async def test_coach_hallucination_interception(monkeypatch):
    """驗證防偽安全網：當外部模型胡亂臆測球速或碼數時，即時攔截並降級回規則式。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "true")
    from apps.api.config import get_settings
    get_settings.cache_clear()
    # 模擬不守規矩的 LLM 回傳捏造的球速與距離
    hallucinated_response = {
        "summary": "選手擊球猛烈，球速達到 150 mph，飛行距離約 275 碼！",
        "observations": [
            {"title": "球速推估", "detail": "桿頭速度約 105 mph", "confidence": 0.8}
        ],
        "priority_fixes": [
            {"focus_area": "擊球距離", "action_cue": "增加距離", "drill_steps": "大力揮", "target_metric": "300 碼"}
        ],
        "uncertainties": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        resp_content = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(hallucinated_response, ensure_ascii=False)
                    }
                }
            ]
        }
        return httpx.Response(200, json=resp_content)

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatibleCoachProvider(
        api_key="test-api-key",
        transport=transport,
    )

    report = await provider.generate_feedback(
        session_summary={"total_swings": 1},
        swing_evidence=[{"id": "sw-1", "overall_score": 75.0, "label": "valid_swing"}],
    )

    # 由於攔截到「球速」、「飛行距離」，必須平滑降級至規則式報告
    assert report.provider == "none", "違反誠信原則之 LLM 輸出必須被攔截並退回規則式報告"
    assert report.llm_enabled is False
    assert "球速" not in report.summary


@pytest.mark.asyncio
async def test_coach_timeout_and_error_fallback():
    """驗證外部 API 逾時或連線失敗時，系統絲滑降級，絕不中斷作業。"""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("連線逾時無法連線至外部 API")

    transport = httpx.MockTransport(handler)
    provider = OpenAICompatibleCoachProvider(
        api_key="test-api-key",
        transport=transport,
    )

    report = await provider.generate_feedback(
        session_summary={"total_swings": 1},
        swing_evidence=[{"id": "sw-1", "overall_score": 75.0, "label": "valid_swing"}],
    )

    assert report.provider == "none"
    assert report.llm_enabled is False
    assert report.summary is not None
