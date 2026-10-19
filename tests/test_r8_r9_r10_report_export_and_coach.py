import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from apps.worker.tasks import run_export_job, run_video_analysis_job
from packages.analysis.coach import OpenAICompatibleCoachProvider, RuleBasedCoachProvider
from packages.analysis.probe import probe_video_file
from tests.fixtures.video_factory import create_synthetic_dtl_video

client = TestClient(app)


def _auth_headers() -> dict[str, str]:
    s = get_settings()
    r = client.post("/api/auth/login", json={"email": s.admin_email, "password": s.admin_password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_full_pipeline_report_manual_calibration_and_mp4_exports(tmp_path: Path) -> None:
    headers = _auth_headers()
    sess = client.post(
        "/api/sessions",
        headers=headers,
        json={
            "title": "完整 E2E 報告與匯出測試場次",
            "date": "2026-10-19",
            "club": "7I",
            "handedness": "right",
            "camera_angle": "DTL",
            "notes": "含正式揮桿與空揮測試",
        },
    ).json()

    v_path = create_synthetic_dtl_video(
        tmp_path / "full_e2e_session.mp4",
        duration_ms=16000,
        fps=30,
        swings_spec=[
            {"start_ms": 1500, "end_ms": 4700, "label": "valid_swing", "spine_delta_deg": 1.5},
            {"start_ms": 6500, "end_ms": 9700, "label": "valid_swing", "spine_delta_deg": 2.8},
            {"start_ms": 11500, "end_ms": 14700, "label": "practice_swing", "spine_delta_deg": 4.0},
        ],
    )
    v_bytes = v_path.read_bytes()

    init_r = client.post(
        "/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": sess["id"],
            "filename": "full_e2e_session.mp4",
            "mime_type": "video/mp4",
            "size_bytes": len(v_bytes),
        },
    ).json()
    part_r = client.put(
        f"/api/uploads/{init_r['upload_id']}/parts/1/content",
        headers=headers,
        content=v_bytes,
    ).json()
    client.post(
        f"/api/uploads/{init_r['upload_id']}/complete",
        headers=headers,
        json={"parts": [{"part_number": 1, "etag": part_r["etag"]}]},
    )

    video_id = init_r["video_id"]
    enq = client.post(f"/api/videos/{video_id}/analyze", headers=headers).json()
    job_id = enq["job_id"]

    # 執行 Worker 分析任務（若背景 daemon 已在執行則等待其完成）
    worker_res = run_video_analysis_job(job_id)
    if worker_res.get("status") == "running":
        for _ in range(60):
            time.sleep(0.3)
            check = client.get(f"/api/jobs/{job_id}", headers=headers).json()
            if check.get("status") == "completed":
                worker_res = {"status": "completed", "segments_detected": 3}
                break

    assert worker_res["status"] == "completed"
    assert worker_res["segments_detected"] == 3

    swings_r = client.get(f"/api/videos/{video_id}/swings", headers=headers)
    assert swings_r.status_code == 200
    swings = swings_r.json()["items"]
    assert len(swings) == 3

    # 測試人工校正第一球時間碼與註記，並確認 feedback_history 留存
    first_id = swings[0]["id"]
    patch_r = client.patch(
        f"/api/swings/{first_id}",
        headers=headers,
        json={
            "start_ms": 1450,
            "end_ms": 4750,
            "ball_strike_status": "confirmed_strike",
            "notes": "紮實擊球，收桿穩定",
            "feedback_category": "boundary_refinement",
            "feedback_note": "微調起迄緩衝 50ms",
        },
    )
    assert patch_r.status_code == 200
    patched = patch_r.json()
    assert patched["manual_override"] is True
    assert patched["notes"] == "紮實擊球，收桿穩定"
    assert len(patched["feedback_history"]) >= 1

    # 重新觸發分析 (force=True)，確認 manual_override=True 之人工註記不會被覆蓋清除！
    enq_force = client.post(f"/api/videos/{video_id}/analyze?force=true", headers=headers).json()
    run_video_analysis_job(enq_force["job_id"])
    check_patched = client.get(f"/api/swings/{first_id}", headers=headers).json()
    assert check_patched["manual_override"] is True
    assert check_patched["notes"] == "紮實擊球，收桿穩定"

    # 驗證場次完整報告與規則式教練輸出
    rep_r = client.get(f"/api/sessions/{sess['id']}/report", headers=headers)
    assert rep_r.status_code == 200
    report = rep_r.json()
    assert report["summary"]["total_swings"] >= 3
    assert report["coach_report"]["provider"] == "none"
    assert report["coach_report"]["llm_enabled"] is False
    assert len(report["coach_report"]["priority_fixes"]) >= 1

    # 測試匯出：1) 單球原始比例 MP4，2) 雙球 9:16 直式精選合輯 MP4
    swings_after = client.get(f"/api/videos/{video_id}/swings", headers=headers).json()["items"]
    second_id = [s["id"] for s in swings_after if s["id"] != first_id][0]
    exp_single = client.post(
        "/api/exports",
        headers=headers,
        json={"segment_ids": [first_id], "layout": "original", "format": "mp4"},
    ).json()
    res_exp1 = run_export_job(exp_single["id"])
    assert res_exp1["status"] == "completed"

    dl_1 = client.get(f"/api/exports/{exp_single['id']}/download", headers=headers)
    assert dl_1.status_code == 200
    out_mp4_1 = tmp_path / "exported_single.mp4"
    out_mp4_1.write_bytes(dl_1.content)
    meta_1 = probe_video_file(out_mp4_1)
    assert abs(meta_1.duration_ms - (4750 - 1450)) <= 250

    exp_916 = client.post(
        "/api/exports",
        headers=headers,
        json={"segment_ids": [first_id, second_id], "layout": "9:16", "format": "mp4"},
    ).json()
    res_exp2 = run_export_job(exp_916["id"])
    assert res_exp2["status"] == "completed"

    dl_2 = client.get(f"/api/exports/{exp_916['id']}/download", headers=headers)
    assert dl_2.status_code == 200
    out_mp4_2 = tmp_path / "exported_9x16.mp4"
    out_mp4_2.write_bytes(dl_2.content)
    meta_2 = probe_video_file(out_mp4_2)
    assert meta_2.width == 720
    assert meta_2.height == 1280
    assert meta_2.duration_ms >= 5500


@pytest.mark.asyncio
async def test_llm_coach_adapter_mock_and_anti_hallucination_guard() -> None:
    session_summary = {"session_id": "s-1", "average_overall_score": 88.5}
    swing_evidence = [
        {
            "id": "seg-101",
            "sequence_no": 1,
            "start_ms": 1200,
            "impact_time_ms": 3100,
            "label": "valid_swing",
            "subscores": {
                "spine_tilt_stability": {
                    "score": 82.0,
                    "raw_value": 4.2,
                    "confidence": 0.9,
                    "how_calculated": "軀幹前傾角變化 4.2 度",
                }
            },
        }
    ]

    # 1. 預設 RuleBasedCoachProvider 不需網路即可產出結構化報告
    rule_coach = RuleBasedCoachProvider()
    r_base = await rule_coach.generate_feedback(session_summary, swing_evidence)
    assert r_base.provider == "none"
    assert r_base.llm_enabled is False
    assert r_base.observations[0].segment_id == "seg-101"

    # 2. Mock OpenAICompatibleCoachProvider 正常結構化回應
    def valid_handler(_request: httpx.Request) -> httpx.Response:
        mock_report = {
            "provider": "openai-compatible",
            "model": "gpt-4o-mini",
            "llm_enabled": True,
            "notice": "AI 教練依據 2D 指標生成",
            "summary": "軀幹前傾維持良好，建議持續強化下桿穩定度。",
            "observations": [
                {
                    "title": "下桿前傾角微幅變化",
                    "detail": "於 3100ms 處觀測到 4.2 度變化",
                    "segment_id": "seg-101",
                    "time_ms": 3100,
                    "metric_key": "spine_tilt_delta_deg",
                    "metric_value": 4.2,
                    "confidence": 0.9,
                }
            ],
            "priority_fixes": [
                {
                    "focus_area": "維持前傾角",
                    "action_cue": "保持臀部貼牆感",
                    "drill_steps": "慢速 7 號鐵半揮桿 10 球",
                    "target_metric": "spine_tilt_delta_deg <= 3.0",
                }
            ],
            "uncertainties": ["2D DTL 不提供實際觸球甜蜜點"],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(mock_report, ensure_ascii=False)}}]},
        )

    provider_ok = OpenAICompatibleCoachProvider(
        api_key="test-key",
        transport=httpx.MockTransport(valid_handler),
    )
    r_ok = await provider_ok.generate_feedback(session_summary, swing_evidence)
    assert r_ok.provider == "openai-compatible"
    assert r_ok.llm_enabled is True
    assert r_ok.observations[0].time_ms == 3100

    # 3. 當 LLM 違規編造「飛行距離 / 球速」時，防呆機制必須攔截並退回 RuleBasedCoachProvider
    def hallucinating_handler(_request: httpx.Request) -> httpx.Response:
        bad_report = {
            "provider": "openai-compatible",
            "model": "gpt-4o-mini",
            "llm_enabled": True,
            "notice": "",
            "summary": "這球飛行距離達 165 碼，球速 120 mph！",
            "observations": [],
            "priority_fixes": [],
            "uncertainties": [],
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(bad_report, ensure_ascii=False)}}]},
        )

    provider_guard = OpenAICompatibleCoachProvider(
        api_key="test-key",
        transport=httpx.MockTransport(hallucinating_handler),
    )
    r_guarded = await provider_guard.generate_feedback(session_summary, swing_evidence)
    assert r_guarded.provider == "none"
    assert r_guarded.llm_enabled is False

    # 4. 確認 /api/settings 不回傳明文 API Key
    headers = _auth_headers()
    upd = client.put(
        "/api/settings",
        headers=headers,
        json={
            "default_club": "7I",
            "handedness": "right",
            "camera_angle": "DTL",
            "llm_provider": "none",
            "llm_api_key": "sk-secret-never-expose-12345",
        },
    )
    assert upd.status_code == 200
    get_s = client.get("/api/settings", headers=headers)
    assert get_s.status_code == 200
    assert "sk-secret-never-expose-12345" not in get_s.text
    assert get_s.json()["has_llm_api_key"] is True
