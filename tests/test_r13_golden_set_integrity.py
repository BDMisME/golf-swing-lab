import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.routers.audit import get_audit_registry
from packages.analysis.evaluation.golden_eval import (
    DualEvaluationReport,
    evaluate_detection_and_events,
)
from packages.analysis.evaluation.golden_registry import (
    GOLDEN_DIR,
    GoldenSetRegistry,
    compute_swing_tempo,
    get_golden_registry,
)
from packages.analysis.scoring.engine import compute_session_wrist_repeatability

CLEAN_GOLDEN_PATH = GOLDEN_DIR / "real_2min_session_gt.json"


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


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_golden_set_registry_integrity_and_sha256_preservation():
    """R13-A & P0-2: 檢驗 Golden Set 單一真實來源完整性，且測試前後 SHA-256 絕不改變"""
    sha_before = _file_sha256(CLEAN_GOLDEN_PATH)
    registry = get_golden_registry()
    sets = registry.list_golden_sets()
    assert len(sets) >= 2

    # 1. 檢驗 2 分鐘原片基準
    gs_2min = registry.get_golden_set("real_2min_session")
    assert gs_2min is not None
    assert gs_2min.video_sha256 == "4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9"
    assert gs_2min.video_duration_ms == 139053
    assert len(gs_2min.swings) == 12

    for sw in gs_2min.swings:
        assert 0 <= sw.start_ms < sw.end_ms <= gs_2min.video_duration_ms
        for ev_name, ev in sw.events.items():
            assert 0 <= ev.time_ms <= gs_2min.video_duration_ms
            assert 0 <= ev.frame <= gs_2min.total_frames
            assert ev.status in [
                "machine_suggested",
                "human_verified",
                "uncertain",
                "pending_human_review",
            ]

    last_sw = gs_2min.swings[-1]
    assert last_sw.end_ms <= gs_2min.video_duration_ms

    # 檢驗正式 Golden Set 檔案 SHA-256 保持不變
    sha_after = _file_sha256(CLEAN_GOLDEN_PATH)
    assert sha_before == sha_after, "正式 Golden Set 檔案在唯讀檢驗過程中不可被修改！"


def test_audit_api_isolated_with_tmp_path(api_client: TestClient, tmp_path: Path):
    """P0-2 & P1-5: 檢驗 API 邊界防呆 (422) 與事件更新機制，透過 tmp_path 隔離保證不污染正式檔案"""
    sha_clean_before = _file_sha256(CLEAN_GOLDEN_PATH)

    # 建立獨立的測試 Golden 目錄
    for f in GOLDEN_DIR.glob("*.json"):
        shutil.copy2(f, tmp_path / f.name)

    isolated_reg = GoldenSetRegistry(golden_dir=tmp_path)
    app.dependency_overrides[get_audit_registry] = lambda: isolated_reg

    try:
        # 1. 未認證請求檢驗 (P1-5)
        resp_unauth = api_client.get("/api/audit/golden-sets")
        assert resp_unauth.status_code == 401

        headers = _get_auth_headers(api_client)

        # 2. 越界時間碼檢驗 (422)
        resp_overflow = api_client.put(
            "/api/audit/golden-sets/real_2min_session/swings/gt-12/events/finish",
            json={"time_ms": 140000, "status": "human_verified"},
            headers=headers,
        )
        assert resp_overflow.status_code == 422
        assert "超出影片合法長度" in resp_overflow.json()["detail"]

        # 3. 負數時間碼檢驗 (422)
        resp_negative = api_client.put(
            "/api/audit/golden-sets/real_2min_session/swings/gt-1/events/address",
            json={"time_ms": -50, "status": "human_verified"},
            headers=headers,
        )
        assert resp_negative.status_code == 422

        # 4. 合法時間碼更新為 human_verified (200)
        gs_isolated = isolated_reg.get_golden_set("real_2min_session")
        assert gs_isolated is not None
        orig_impact = gs_isolated.swings[0].events["impact"].time_ms
        new_test_impact = orig_impact + 20

        resp_valid = api_client.put(
            "/api/audit/golden-sets/real_2min_session/swings/gt-1/events/impact",
            json={
                "time_ms": new_test_impact,
                "frame": 817,
                "status": "human_verified",
                "rationale": "測試人工校正",
            },
            headers=headers,
        )
        assert resp_valid.status_code == 200
        data = resp_valid.json()
        assert data["event"]["status"] == "human_verified"
        assert data["event"]["time_ms"] == new_test_impact
        assert data["event"]["frame"] == 817
        assert data["event"]["verified_at"] is not None
        assert data["event"]["previous_value"]["time_ms"] == orig_impact

        # 5. 測試撤回 (Reset)
        resp_reset = api_client.post(
            "/api/audit/golden-sets/real_2min_session/swings/gt-1/reset",
            headers=headers,
        )
        assert resp_reset.status_code == 200
        reset_data = resp_reset.json()
        assert reset_data["swing"]["events"]["impact"]["status"] == "machine_suggested"
        assert reset_data["swing"]["events"]["impact"]["time_ms"] == orig_impact
        assert reset_data["swing"]["impact_ms"] == orig_impact

    finally:
        app.dependency_overrides.clear()

    # 驗證正式檔案毫髮無損
    sha_clean_after = _file_sha256(CLEAN_GOLDEN_PATH)
    assert sha_clean_before == sha_clean_after, "測試執行後正式 Golden Set 遭到污染！"


def test_round_trip_reset_integrity(tmp_path: Path):
    """P0-2: 檢驗 Round-Trip: Original -> Update -> Reset -> Equal Original"""
    # 複製測試資料
    for f in GOLDEN_DIR.glob("*.json"):
        shutil.copy2(f, tmp_path / f.name)

    reg = GoldenSetRegistry(golden_dir=tmp_path)
    ds = reg.get_dataset("real_2min_session")
    assert ds is not None

    sw = ds.swings[0]
    # 深度複製修改前的所有關鍵屬性
    orig_sw_dict = sw.model_dump(mode="json")
    orig_events = {k: v.model_dump(mode="json") for k, v in sw.events.items()}
    orig_top_ms = sw.top_ms
    orig_impact_ms = sw.impact_ms
    orig_tempo = sw.tempo_ratio
    orig_start_ms = sw.start_ms
    orig_end_ms = sw.end_ms
    orig_frames = dict(sw.frames)

    # 1. 執行更新多個事件
    reg.update_swing_event(
        dataset_id="real_2min_session",
        swing_id=sw.gt_id,
        event_name="impact",
        new_time_ms=orig_impact_ms + 40,
        new_frame=orig_frames["impact"] + 2,
        status="human_verified",
        rationale="人工校核 Impact",
    )
    reg.update_swing_event(
        dataset_id="real_2min_session",
        swing_id=sw.gt_id,
        event_name="top",
        new_time_ms=orig_top_ms - 20,
        new_frame=orig_frames["top"] - 1,
        status="human_verified",
        rationale="人工校核 Top",
    )

    # 驗證修改後頂層欄位發生變動
    updated_ds = reg.get_dataset("real_2min_session")
    assert updated_ds is not None
    updated_sw = updated_ds.swings[0]
    assert updated_sw.impact_ms == orig_impact_ms + 40
    assert updated_sw.top_ms == orig_top_ms - 20
    assert updated_sw.tempo_ratio != orig_tempo

    # 2. 執行撤回 (Reset)
    reset_sw = reg.reset_swing_to_machine("real_2min_session", sw.gt_id)

    # 3. 驗證所有數值完全恢復回 Original
    assert reset_sw.top_ms == orig_top_ms
    assert reset_sw.impact_ms == orig_impact_ms
    assert reset_sw.takeaway_ms == sw.takeaway_ms
    assert reset_sw.address_ms == sw.address_ms
    assert reset_sw.finish_ms == sw.finish_ms
    assert reset_sw.start_ms == orig_start_ms
    assert reset_sw.end_ms == orig_end_ms
    assert reset_sw.tempo_ratio == orig_tempo
    assert reset_sw.frames == orig_frames

    for ev_k, orig_ev_dict in orig_events.items():
        curr_ev = reset_sw.events[ev_k]
        assert curr_ev.time_ms == orig_ev_dict["time_ms"]
        assert curr_ev.frame == orig_ev_dict["frame"]
        assert curr_ev.status == "machine_suggested"
        assert curr_ev.verified_at is None
        assert curr_ev.previous_value is None


def test_tempo_definition_and_strict_validation():
    """P1-4: 檢驗嚴格高爾夫運動學節奏定義 (Backswing = Top - Takeaway, Downswing = Impact - Top)"""
    # 合法時序: Takeaway=1000, Top=2000, Impact=2500 -> bs=1000, ds=500, tempo=2.0
    bs, ds, tempo = compute_swing_tempo(1000, 2000, 2500)
    assert bs == 1000
    assert ds == 500
    assert tempo == 2.0

    # Address 瞄球停頓 3 秒: Takeaway=4000, Top=5000, Impact=5400 -> bs=1000, ds=400, tempo=2.5
    # (Address 的 1000ms 絕不可併入上桿時間)
    bs, ds, tempo = compute_swing_tempo(4000, 5000, 5400)
    assert bs == 1000
    assert ds == 400
    assert tempo == 2.5

    # 時序不合法 1: Top <= Takeaway
    bs, ds, tempo = compute_swing_tempo(2500, 2000, 3000)
    assert bs is None and ds is None and tempo is None

    # 時序不合法 2: Impact <= Top
    bs, ds, tempo = compute_swing_tempo(1000, 2500, 2000)
    assert bs is None and ds is None and tempo is None

    # 缺漏任一事件
    assert compute_swing_tempo(None, 2000, 2500) == (None, None, None)
    assert compute_swing_tempo(1000, None, 2500) == (None, None, None)
    assert compute_swing_tempo(1000, 2000, None) == (None, None, None)


def test_event_accuracy_strict_human_verified_rule():
    """P0-3: 檢驗正式事件誤差僅能使用 human_verified 的 Ground Truth，未確認時標記 NOT_VALIDATED"""
    # 基準 1: 全部為 machine_suggested
    gt_swings_machine = [
        {
            "gt_id": "gt-1",
            "start_ms": 1000,
            "end_ms": 4000,
            "takeaway_ms": 1300,
            "top_ms": 2500,
            "impact_ms": 3000,
            "events": {
                "impact": {"time_ms": 3000, "frame": 180, "status": "machine_suggested"},
            },
        }
    ]
    preds = [
        {
            "sequence_no": 1,
            "start_ms": 1020,
            "end_ms": 4010,
            "takeaway_ms": 1310,
            "top_ms": 2510,
            "impact_ms": 3020,
        }
    ]

    report_unverified = evaluate_detection_and_events(preds, gt_swings_machine)
    imp_unv = report_unverified.events.metrics["impact"]
    # 絕不可將 machine_suggested 冒充為正式真實誤差
    assert imp_unv.sample_count == 0
    assert imp_unv.mean_absolute_error_ms is None
    assert imp_unv.status == "NOT_VALIDATED"
    assert imp_unv.coverage_rate == 0.0
    assert report_unverified.events.overall_status == "NOT_VALIDATED"

    # 基準 2: 人工確認後 (human_verified)
    gt_swings_human = [
        {
            "gt_id": "gt-1",
            "start_ms": 1000,
            "end_ms": 4000,
            "takeaway_ms": 1300,
            "top_ms": 2500,
            "impact_ms": 3000,
            "events": {
                "impact": {"time_ms": 3000, "frame": 180, "status": "human_verified"},
            },
        }
    ]
    report_verified = evaluate_detection_and_events(preds, gt_swings_human)
    imp_v = report_verified.events.metrics["impact"]
    assert imp_v.sample_count == 1
    assert imp_v.mean_absolute_error_ms == 20.0
    assert imp_v.status == "PASS"
    assert imp_v.coverage_rate == 1.0


def test_pelvis_and_torso_normalized_repeatability():
    """R13-E: 檢驗手腕軌跡重複性經骨盆原點與軀幹長度歸一化"""
    traj_1 = [
        {"time_ms": 0, "x": 0.45, "y": 0.60, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 300, "x": 0.40, "y": 0.45, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 600, "x": 0.35, "y": 0.30, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
        {"time_ms": 900, "x": 0.50, "y": 0.60, "conf": 0.9, "hip_x": 0.50, "hip_y": 0.60, "torso_len": 0.25},
    ]
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
    assert res["swing_1"]["deviation"] is not None
    assert res["swing_1"]["deviation"] < 0.01

    single_res = compute_session_wrist_repeatability({"swing_1": traj_1})
    assert single_res["swing_1"]["deviation"] is None
    assert "少於 2 球" in single_res["swing_1"]["reason"]
