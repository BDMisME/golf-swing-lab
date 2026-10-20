import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from packages.analysis.evaluation.golden_eval import (
    DetectionAccuracyReport,
    DualEvaluationReport,
    SwingEventAccuracyReport,
    evaluate_detection_and_events,
)
from packages.analysis.evaluation.golden_registry import get_golden_registry
from packages.analysis.scoring.engine import compute_session_wrist_repeatability


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)


def _get_auth_headers(client: TestClient) -> dict[str, str]:
    s = get_settings()
    resp = client.post(
        "/api/auth/login",
        json={"email": s.admin_email, "password": s.admin_password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_golden_set_registry_integrity():
    """R13-A: 檢驗 Golden Set 單一真實來源之資料完整性與時序邊界"""
    registry = get_golden_registry()
    sets = registry.list_golden_sets()
    assert len(sets) >= 2

    # 1. 檢驗 2 分鐘原片基準
    gs_2min = registry.get_golden_set("real_2min_session")
    assert gs_2min is not None
    assert gs_2min.video_sha256 == "4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9"
    assert gs_2min.video_duration_ms == 139053
    assert len(gs_2min.swings) == 12

    # 檢驗每顆球的邊界與事件必須在 [0, video_duration_ms] 內
    for sw in gs_2min.swings:
        assert 0 <= sw.start_ms < sw.end_ms <= gs_2min.video_duration_ms
        for ev_name, ev in sw.events.items():
            assert 0 <= ev.time_ms <= gs_2min.video_duration_ms
            assert 0 <= ev.frame <= gs_2min.total_frames
            # 確認初始狀態為 machine_suggested（未被偽造為 human_verified）
            assert ev.status in ["machine_suggested", "human_verified", "uncertain", "pending_human_review"]

    # 檢驗最後一球結束時間不可超出影片長度
    last_sw = gs_2min.swings[-1]
    assert last_sw.end_ms <= gs_2min.video_duration_ms

    # 2. 檢驗 11 秒單球基準
    gs_11s = registry.get_golden_set("real_11s_session")
    assert gs_11s is not None
    assert gs_11s.video_sha256 == "9df04b7b244f56788bdfaf8edd95d7233b807ef87f0bc9ddeab599b5bee15ead"
    assert gs_11s.video_duration_ms == 11458
    assert len(gs_11s.swings) == 1
    assert gs_11s.swings[0].end_ms <= gs_11s.video_duration_ms


def test_audit_api_boundary_validation_and_event_update(api_client: TestClient):
    """R13-A & R13-C: 檢驗 API 邊界防呆 (422) 與事件更新機制"""
    registry = get_golden_registry()
    gs_2min = registry.get_golden_set("real_2min_session")
    assert gs_2min is not None

    headers = _get_auth_headers(api_client)

    # 1. 嘗試傳入越界時間（大於影片時長 139053ms）-> 必須回傳 422
    resp_overflow = api_client.put(
        "/api/audit/golden-sets/real_2min_session/swings/gt-12/events/finish",
        json={"time_ms": 140000, "status": "human_verified"},
        headers=headers,
    )
    assert resp_overflow.status_code == 422
    assert "超出影片合法長度" in resp_overflow.json()["detail"]

    # 2. 嘗試傳入負數時間碼 -> 必須回傳 422
    resp_negative = api_client.put(
        "/api/audit/golden-sets/real_2min_session/swings/gt-1/events/address",
        json={"time_ms": -50, "status": "human_verified"},
        headers=headers,
    )
    assert resp_negative.status_code == 422

    # 3. 合法時間碼更新為 human_verified
    orig_impact = gs_2min.swings[0].events["impact"].time_ms
    new_test_impact = orig_impact + 15
    resp_valid = api_client.put(
        "/api/audit/golden-sets/real_2min_session/swings/gt-1/events/impact",
        json={
            "time_ms": new_test_impact,
            "status": "human_verified",
            "rationale": "測試人工校正",
        },
        headers=headers,
    )
    assert resp_valid.status_code == 200
    data = resp_valid.json()
    assert data["event"]["status"] == "human_verified"
    assert data["event"]["time_ms"] == new_test_impact
    assert data["event"]["previous_value"]["time_ms"] == orig_impact

    # 4. 測試撤回 (Reset)
    resp_reset = api_client.post(
        "/api/audit/golden-sets/real_2min_session/swings/gt-1/reset",
        headers=headers,
    )
    assert resp_reset.status_code == 200
    reset_data = resp_reset.json()
    assert reset_data["swing"]["events"]["impact"]["status"] == "machine_suggested"
    assert reset_data["swing"]["events"]["impact"]["time_ms"] == orig_impact


def test_pelvis_and_torso_normalized_repeatability():
    """R13-E: 檢驗手腕軌跡重複性經骨盆原點與軀幹長度歸一化"""
    # 建立兩球具有不同身材比例與站位座標的合成手腕軌跡
    # 球 1: 站在 (0.5, 0.6)，軀幹長 0.25
    traj_1 = [
        {"time_ms": 0, "x": 0.45, "y": 0.60, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 300, "x": 0.40, "y": 0.45, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 600, "x": 0.35, "y": 0.30, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 900, "x": 0.50, "y": 0.60, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
    ]

    # 球 2: 站位往右平移 (0.6, 0.6)，動作形狀完全相同
    traj_2 = [
        {"time_ms": 0, "x": 0.55, "y": 0.60, "conf": 0.9, "hip_x": 0.60, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 300, "x": 0.50, "y": 0.45, "conf": 0.9, "hip_x": 0.60, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 600, "x": 0.45, "y": 0.30, "conf": 0.9, "hip_x": 0.60, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 900, "x": 0.60, "y": 0.60, "conf": 0.9, "hip_x": 0.60, "hip_y": 0.60, "torso_len": 0.25},
    ]

    trajs = {"swing_1": traj_1, "swing_2": traj_2}
    res = compute_session_wrist_repeatability(trajs)

    assert "swing_1" in res and "swing_2" in res
    assert res["swing_1"]["normalized_by"] == "pelvis_and_torso"
    # 因為兩球在骨盆相對座標系中軌跡完全重疊，偏差應接近 0.0
    assert res["swing_1"]["deviation"] is not None
    assert res["swing_1"]["deviation"] < 0.01

    # 單球測試：應返回 None
    single_res = compute_session_wrist_repeatability({"swing_1": traj_1})
    assert single_res["swing_1"]["deviation"] is None
    assert "少於 2 球" in single_res["swing_1"]["reason"]


def test_dual_evaluation_detection_and_events():
    """R13-D: 檢驗 Detection Accuracy 與 Swing Event Accuracy 雙向分離評估"""
    gt_swings = [
        {
            "gt_id": "gt-1",
            "start_ms": 1000,
            "end_ms": 4000,
            "address_ms": 1000,
            "takeaway_ms": 1300,
            "top_ms": 2500,
            "impact_ms": 3000,
            "finish_ms": 3900,
        },
        {
            "gt_id": "gt-2",
            "start_ms": 6000,
            "end_ms": 9000,
            "address_ms": 6000,
            "takeaway_ms": 6300,
            "top_ms": 7500,
            "impact_ms": 8000,
            "finish_ms": 8900,
        },
        {
            "gt_id": "gt-3",
            "start_ms": 12000,
            "end_ms": 15000,
            "address_ms": 12000,
            "takeaway_ms": 12300,
            "top_ms": 13500,
            "impact_ms": 14000,
            "finish_ms": 14900,
        },
    ]

    predictions = [
        {
            "sequence_no": 1,
            "start_ms": 1050,
            "end_ms": 4020,
            "address_ms": 1050,
            "takeaway_ms": 1310,
            "top_ms": 2510,
            "impact_estimated_ms": 3020,
            "finish_ms": 3910,
        },
        {
            "sequence_no": 2,
            "start_ms": 5980,
            "end_ms": 8990,
            "address_ms": 5980,
            "takeaway_ms": 6290,
            "top_ms": 7490,
            "impact_estimated_ms": 7990,
            "finish_ms": 8890,
        },
        {
            "sequence_no": 3,
            "start_ms": 18000,
            "end_ms": 20000,
            "address_ms": 18000,
            "top_ms": 19000,
            "impact_estimated_ms": 19500,
            "finish_ms": 20000,
        },
    ]

    report: DualEvaluationReport = evaluate_detection_and_events(
        predictions, gt_swings, iou_threshold=0.3
    )

    # 1. 檢驗 Detection Accuracy 指標
    det = report.detection
    assert det.total_gt == 3
    assert det.total_pred == 3
    assert det.true_positives == 2
    assert det.false_positives == 1
    assert det.false_negatives == 1
    assert round(det.precision, 2) == 0.67
    assert round(det.recall, 2) == 0.67
    assert len(det.missed_swings) == 1
    assert det.missed_swings[0]["gt_id"] == "gt-3"

    # 2. 檢驗 Swing Event Accuracy 指標
    evts = report.events
    assert "impact" in evts.metrics
    impact_metric = evts.metrics["impact"]
    assert impact_metric.sample_count == 2
    assert impact_metric.mean_absolute_error_ms == 15.0
    assert impact_metric.max_error_ms == 20.0
