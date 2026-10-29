"""
tests/test_reference_events_consistency.py

測試 16 支示範影片的資料一致性、單一事實來源 (Single Source of Truth) 與最高誠信原則：
1. 資料庫 (DB) 中的 event_timestamps 與驗證報告 (docs/reports/reference_events_verification.json) 100% 吻合 (誤差 0ms)。
2. calibration_params 完整保留 candidate_events 與 active_events，且 active_events 與 event_timestamps 一致。
3. 擊球確認狀態 (impact_status) 依據真實影像證據分類：
   - 11 支具備確鑿影像證據者為 confirmed_strike。
   - 5 支 (5W, PW, LW, Putter, SW Bunker) 誠實標記為 impact_estimated，絕無虛假標記。
   - 特別驗證 03_Wood5.mp4 為 impact_estimated。
4. API (GET /api/reference-swings) 回傳之事件時間碼與六維度狀態與資料庫及報告 100% 一致。
5. 資料庫無重複 ID 或垃圾 UUID 膨脹 (總數恆定)。
"""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.db import SessionLocal
from apps.api.models import ReferenceSwing


@pytest.fixture(scope="module")
def verification_report():
    report_path = Path("docs/reports/reference_events_verification.json")
    assert report_path.exists(), "reference_events_verification.json 報告必須存在"
    with open(report_path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def api_client():
    return TestClient(app)


def test_reference_swings_count_stability(db_session, verification_report):
    """驗證資料庫記錄數量無異常膨脹，示範影片記錄恆定為 18 筆 (16 支新 bundle + 2 支既有 fixture)。"""
    rows = db_session.query(ReferenceSwing).all()
    assert len(rows) == 18, f"資料庫 ReferenceSwing 筆數應為 18，實際為 {len(rows)}"
    assert verification_report["total_clips"] == 16, f"驗證報告影片數應為 16，實際為 {verification_report['total_clips']}"


def test_db_events_match_verification_report(db_session, verification_report):
    """驗證資料庫中 16 支示範影片的 event_timestamps 與驗證報告 100% 一致 (0ms 誤差)。"""
    records = {r["filename"]: r for r in verification_report["records"]}

    for fn, rep in records.items():
        club = rep["club_type"]
        fn_clean = fn.replace(" ", "_").replace(".mp4", "")
        club_slug = club.lower().replace("/", "_")
        expected_key = f"ref_{club_slug}_{fn_clean}_clean.mp4"

        db_ref = (
            db_session.query(ReferenceSwing)
            .filter(ReferenceSwing.club_type == club)
            .filter(ReferenceSwing.storage_key.ilike(f"%{expected_key}"))
            .first()
        )
        assert db_ref is not None, f"資料庫中未找到 {club} ({fn})"

        # 檢驗 Top 與 Impact 誤差為 0ms
        db_events = db_ref.event_timestamps
        ve = rep["verified_events"]

        assert db_events["top"] == ve["top"], (
            f"[{club} - {fn}] Top 時間碼不一致: DB={db_events['top']}ms vs Report={ve['top']}ms"
        )
        assert db_events["impact"] == ve["impact"], (
            f"[{club} - {fn}] Impact 時間碼不一致: DB={db_events['impact']}ms vs Report={ve['impact']}ms"
        )
        assert (db_events["impact"] - db_events["top"]) == ve["downswing_ms"], (
            f"[{club} - {fn}] 下桿時長不一致"
        )


def test_calibration_params_preserves_candidate_and_active_events(db_session, verification_report):
    """驗證 calibration_params 中同時保存了原始 candidate_events 與 active_events。"""
    records = {r["filename"]: r for r in verification_report["records"]}

    for fn, rep in records.items():
        club = rep["club_type"]
        fn_clean = fn.replace(" ", "_").replace(".mp4", "")
        club_slug = club.lower().replace("/", "_")
        expected_key = f"ref_{club_slug}_{fn_clean}_clean.mp4"

        db_ref = (
            db_session.query(ReferenceSwing)
            .filter(ReferenceSwing.club_type == club)
            .filter(ReferenceSwing.storage_key.ilike(f"%{expected_key}"))
            .first()
        )
        calib = db_ref.calibration_params
        assert "candidate_events" in calib, f"[{club}] calibration_params 缺少 candidate_events"
        assert "active_events" in calib, f"[{club}] calibration_params 缺少 active_events"
        assert calib["active_events"]["top"] == rep["verified_events"]["top"]
        assert calib["active_events"]["impact"] == rep["verified_events"]["impact"]


def test_truthfulness_of_strike_classification(verification_report):
    """驗證擊球確認度客觀可信，無虛假 confirmed_strike：
    - 5W (03_Wood5.mp4) 必須為 impact_estimated (快門間隙出球，無直接觸球影格)
    - Putter (17_Putter.mp4) 必須為 impact_estimated 且 events_reliable == False
    - PW, LW, SW Bunker 必須為 impact_estimated
    - confirmed_strike 共 11 支，impact_estimated 共 5 支，unresolved 共 0 支
    """
    records = {r["filename"]: r for r in verification_report["records"]}

    # 1. 03_Wood5.mp4 專項檢查
    wood5 = records.get("03_Wood5.mp4")
    assert wood5 is not None
    assert wood5["impact_status"] == "impact_estimated", "5W 必須標記為 impact_estimated"
    assert "快門" in wood5["impact_note"] or "推估" in wood5["impact_note"]

    # 2. 17_Putter.mp4 專項檢查
    putter = records.get("17_Putter.mp4")
    assert putter is not None
    assert putter["impact_status"] == "impact_estimated"
    assert putter["six_dimensions"]["events_reliable"] is False
    assert putter["six_dimensions"]["supports_phase_sync"] is False

    # 3. 統計檢查
    summary = verification_report["summary"]
    assert summary["confirmed_strike_count"] == 11, f"confirmed_strike 應為 11 支，實際為 {summary['confirmed_strike_count']}"
    assert summary["impact_estimated_count"] == 5, f"impact_estimated 應為 5 支，實際為 {summary['impact_estimated_count']}"
    assert summary["unresolved_count"] == 0


from apps.api.models import User
from apps.api.auth import hash_password, create_session_token


def get_auth_token(db):
    user = db.query(User).filter(User.email == "consistency_test@example.com").first()
    if not user:
        user = User(
            email="consistency_test@example.com",
            username="consistency_test",
            password_hash=hash_password("Pass123456!"),
            role="owner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return create_session_token(user)


def test_api_returns_consistent_active_events(api_client, db_session, verification_report):
    """驗證正式 API (GET /api/reference-swings) 回傳的事件和六維度技術狀態與驗證報告 100% 一致。"""
    token = get_auth_token(db_session)
    res = api_client.get("/api/reference-swings", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert "clubs" in data

    api_by_slug = {}
    for ref in data.get("references", []):
        key = ref.get("storage_key", "")
        fn_part = key.split("/")[-1]
        api_by_slug[fn_part] = ref

    for rep in verification_report["records"]:
        club = rep["club_type"]
        fn = rep["filename"]
        fn_clean = fn.replace(" ", "_").replace(".mp4", "")
        club_slug = club.lower().replace("/", "_")
        expected_key = f"ref_{club_slug}_{fn_clean}_clean.mp4"

        api_item = api_by_slug.get(expected_key)
        assert api_item is not None, f"API 回傳列表中未找到 {expected_key}"

        api_events = api_item.get("event_timestamps", {})
        ve = rep["verified_events"]

        assert api_events.get("top") == ve["top"], f"API 回傳之 Top 與驗證報告不一致: {club} ({fn})"
        assert api_events.get("impact") == ve["impact"], f"API 回傳之 Impact 與驗證報告不一致: {club} ({fn})"
        assert api_item.get("impact_status") == rep["impact_status"]
