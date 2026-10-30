"""
tests/test_offline_llm_guard.py
================================
驗證 R3: 關閉所有外部 LLM 呼叫 (Offline Swing Coach Guard)
1. 預設 GSL_ENABLE_EXTERNAL_LLM=false，且後端統一開關生效。
2. 即使傳入 API Key 或配置 Gemini / OpenAI Provider，也絕對不向外部模型發出網路請求。
3. Session Report, Deep Insight, Coach 等入口皆強制回退為 RuleBasedCoachProvider。
4. 既有 LLM Provider 程式碼保留，供未來需要時重新啟用。
5. 日誌不洩漏 API Key。
6. 本機視覺分析能力 (YOLO, MediaPipe, 狀態機, 評分) 100% 完整運作。
"""

import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.config import Settings, get_settings
from apps.api.main import app
from packages.analysis.coach import (
    ActionDifference,
    CoachReport,
    GeminiCoachProvider,
    OpenAICompatibleCoachProvider,
    RuleBasedCoachProvider,
    generate_deep_vision_insight,
)


def test_default_config_offline_guard():
    """驗證預設組態下 enable_external_llm 嚴格為 False。"""
    settings = Settings()
    # 預設不得開啟外部 LLM
    assert settings.enable_external_llm is False


def test_environment_variable_override_guard(monkeypatch):
    """驗證環境變數 GSL_ENABLE_EXTERNAL_LLM 可以控制開關。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    s_false = Settings()
    assert s_false.enable_external_llm is False

    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "true")
    s_true = Settings()
    assert s_true.enable_external_llm is True


@pytest.mark.asyncio
async def test_openai_compatible_provider_zero_network_when_disabled(monkeypatch):
    """驗證當 enable_external_llm=False 時，OpenAICompatibleCoachProvider 絕不向外發送 HTTP 請求。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()

    # 模擬即使有 API Key 與模型設定
    provider = OpenAICompatibleCoachProvider(
        api_key="sk-test-secret-key-123456",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        report = await provider.generate_feedback(
            session_summary={"total_swings": 5, "valid_swings": 5},
            swing_evidence=[{
                "segment_id": "seg-1",
                "overall_score": 75.0,
                "label": "valid_swing",
                "subscores": {
                    "spine_tilt_stability": {"score": 65.0, "raw_value": 6.2, "confidence": 0.88}
                },
            }],
        )

        # 斷言：外部 HTTP 請求次數嚴格為 0
        assert mock_post.call_count == 0

        # 斷言：回傳的報告由 RuleBasedCoachProvider 安全產生
        assert report.llm_enabled is False
        assert report.provider in ("none", "rule-based")
        assert len(report.observations) > 0


@pytest.mark.asyncio
async def test_gemini_provider_zero_network_when_disabled(monkeypatch):
    """驗證當 enable_external_llm=False 時，GeminiCoachProvider 絕不向外發送 HTTP 請求。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()

    provider = GeminiCoachProvider(
        api_key="AIzaSyTestGeminiFakeKey9999",
        model="gemini-3.8-flash",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        report = await provider.generate_feedback(
            session_summary={"total_swings": 3, "valid_swings": 3},
            swing_evidence=[{"segment_id": "seg-2", "overall_score": 80.0, "label": "valid_swing"}],
        )

        # 斷言：外部 HTTP 請求次數嚴格為 0
        assert mock_post.call_count == 0

        # 斷言：報告由 RuleBased 安全產生
        assert report.llm_enabled is False
        assert report.provider in ("none", "rule-based")


def test_deep_insight_offline_rule_based_mode(monkeypatch):
    """驗證 generate_deep_vision_insight 在離線守衛下強制使用 rule_based_advice。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()

    diff = ActionDifference(
        id="spine_tilt_diff",
        title="上桿頂點：軀幹前傾角度偏立",
        phase="top",
        time_ms=1367,
        magnitude="前傾角變化 5.8°",
        evidence_text="軀幹軸線較準備姿勢抬起 5.8°",
        suggested_cue="維持臀部深度",
        retest_target="前傾角變化 <= 4.0°",
        confidence=0.88,
    )

    # 即使嘗試傳入外部 Provider 與圖片
    fake_provider = OpenAICompatibleCoachProvider(api_key="sk-test", model="gpt-4o")
    insight = generate_deep_vision_insight(
        diff=diff,
        swing_detail={"id": "swing-1"},
        llm_provider=fake_provider,
        keyframe_images=[{"label": "top", "base64": "fake"}],
    )

    # 斷言：強制為 rule_based_advice，llm_used 為 False，images_used 為 False
    assert insight.analysis_mode == "rule_based_advice"
    assert insight.llm_used is False
    assert insight.images_used is False
    assert "gsl-evidence-engine" in insight.provider or insight.provider == "gsl-evidence-engine-v1"


def test_settings_api_exposes_offline_mode():
    """驗證 /api/settings 端點回傳 enable_external_llm=false 與 coach_mode='offline'。"""
    get_settings.cache_clear()
    with TestClient(app) as client:
        # 先以預設管理員登入
        login_res = client.post(
            "/api/auth/login",
            json={"email": "golfer@swinglab.local", "password": "GolfSwingLab!2026"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        res = client.get("/api/settings", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["enable_external_llm"] is False
        assert data["coach_mode"] == "offline"


@pytest.mark.asyncio
async def test_provider_with_transport_still_blocked_when_offline(monkeypatch):
    """
    P1-A 核心驗證：
    即使呼叫端注入了 transport（如 MockTransport）或合法 API Key，
    只要 enable_external_llm=False，就絕對不得發送請求，必須 100% 阻斷並回退至 RuleBasedCoachProvider。
    """
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()

    request_called = False

    def handler(_req):
        nonlocal request_called
        request_called = True
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    import httpx
    provider = OpenAICompatibleCoachProvider(
        api_key="sk-real-looking-key-123456",
        transport=httpx.MockTransport(handler),
    )

    report = await provider.generate_feedback(
        session_summary={"total_swings": 1},
        swing_evidence=[{"segment_id": "seg-1", "overall_score": 80.0, "label": "valid_swing"}],
    )

    # 必須未曾觸發 transport
    assert request_called is False
    assert report.provider in ("none", "rule-based")
    assert report.llm_enabled is False


@pytest.mark.asyncio
async def test_gemini_with_transport_still_blocked_when_offline(monkeypatch):
    """驗證 GeminiCoachProvider 在有 transport 且離線時依然 100% 阻斷。"""
    monkeypatch.setenv("GSL_ENABLE_EXTERNAL_LLM", "false")
    get_settings.cache_clear()

    request_called = False

    def handler(_req):
        nonlocal request_called
        request_called = True
        return httpx.Response(200, json={"candidates": []})

    import httpx
    gemini = GeminiCoachProvider(
        api_key="AIzaSyTestKey9999",
        transport=httpx.MockTransport(handler),
    )

    report = await gemini.generate_feedback(
        session_summary={"total_swings": 1},
        swing_evidence=[{"segment_id": "seg-1", "overall_score": 80.0, "label": "valid_swing"}],
    )

    assert request_called is False
    assert report.provider in ("none", "rule-based")
    assert report.llm_enabled is False


def test_fail_closed_when_settings_load_error(monkeypatch):
    """
    P1-A 核心驗證：
    當組態系統載入失敗（如拋出例外）時，必須安全 Fail-Closed，
    is_external_llm_allowed 必須回傳 False，拒絕外部呼叫。
    """
    from packages.analysis.coach import is_external_llm_allowed

    def broken_get_settings():
        raise RuntimeError("無法讀取系統配置檔 (Simulated Config Failure)")

    monkeypatch.setattr("apps.api.config.get_settings", broken_get_settings)
    assert is_external_llm_allowed() is False

