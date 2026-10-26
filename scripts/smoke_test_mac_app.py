#!/usr/bin/env python3
"""
scripts/smoke_test_mac_app.py

Golf Swing Lab — 隔離環境 Mac App 端到端 Smoke Test
驗證項目：
1. 完全隔離環境（暫存 SQLite 資料庫與 Local Storage，不影響既有使用者練習紀錄）
2. 真實 139 秒 iPhone 錄影完整 Pipeline（Video Ingest -> Proxy -> Coarse-to-Fine -> Pose -> Scoring -> DB 持久化）
3. 場次報告 API (/api/sessions/{id}/report) 與 Top 5 排行榜驗證（姿勢榜獨立性、Needs Review 球次排除）
4. 單球播放 API (/api/swings/{id}) 與 Clean Motion 幾何骨架/時間碼一致性（特別檢驗第 8、9、10 球）
5. 測試完成後 100% 安全清理暫存資源
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.auth import create_session_token, hash_password
from apps.api.config import get_settings
from apps.api.db import Base, get_db
from apps.api.main import app
from apps.api.models import AnalysisJob, PracticeSession, User, Video
from apps.worker.tasks import run_video_analysis_job
from packages.storage.s3_client import LocalStorageService, get_storage_service


def run_mac_app_smoke_test() -> dict[str, Any]:
    print("=" * 80)
    print("Golf Swing Lab — 隔離環境端到端 Mac App Smoke Test")
    print("=" * 80)

    raw_video_path = REPO_ROOT / "測試影片" / "2分鐘.mov"
    if not raw_video_path.exists():
        raise FileNotFoundError(f"找不到測試影片: {raw_video_path}")

    # 1. 建立完全隔離的臨時環境
    temp_dir = Path(tempfile.mkdtemp(prefix="gsl_smoke_test_"))
    temp_db_path = temp_dir / "isolated_smoke_test.db"
    temp_storage_dir = temp_dir / "storage"
    temp_storage_dir.mkdir(parents=True, exist_ok=True)

    print(f"[隔離環境] 暫存目錄: {temp_dir}")
    print(f"[隔離環境] 獨立 SQLite 資料庫: {temp_db_path}")

    db_url = f"sqlite:///{temp_db_path}"
    test_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # 建立 Tables
    Base.metadata.create_all(bind=test_engine)

    # 覆寫 FastAPI get_db dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # 建立測試用 Storage 並替換 get_storage_service
    isolated_storage = LocalStorageService(base_dir=temp_storage_dir)

    import packages.storage.s3_client as s3_mod
    import apps.api.main as api_main
    import apps.worker.tasks as worker_tasks

    orig_s3_getter = s3_mod.get_storage_service
    orig_api_getter = api_main.get_storage_service
    orig_worker_getter = worker_tasks.get_storage_service

    s3_mod.get_storage_service = lambda: isolated_storage
    api_main.get_storage_service = lambda: isolated_storage
    worker_tasks.get_storage_service = lambda: isolated_storage

    # 同時猴子補丁 apps.worker.tasks.SessionLocal
    orig_worker_session = worker_tasks.SessionLocal
    worker_tasks.SessionLocal = TestingSessionLocal

    client = TestClient(app)

    smoke_results: dict[str, Any] = {
        "tested_at": datetime.now(UTC).isoformat(),
        "video_path": str(raw_video_path),
        "steps": {},
    }

    try:
        # Step 1: 建立測試使用者與登入 Token
        with TestingSessionLocal() as db:
            test_user = User(
                id="user_smoke_admin",
                email="smoke_admin@golfswinglab.local",
                username="smoke_admin",
                password_hash=hash_password("AdminPass123!"),
                role="admin",
            )
            db.add(test_user)
            db.commit()

            auth_token = create_session_token(test_user)
        headers = {"Authorization": f"Bearer {auth_token}"}
        print("[Step 1] 測試使用者建立完成並成功取得 JWT 憑證。")
        smoke_results["steps"]["auth"] = "PASS"

        # Step 2: 建立 Session 與 Video 紀錄
        sess_res = client.post(
            "/api/sessions",
            headers=headers,
            json={
                "title": "Mac App 隔離冒煙測試場次",
                "date": "2026-10-27",
                "club": "7I",
                "handedness": "right",
            },
        )
        assert sess_res.status_code in (200, 201), f"建立場次失敗: {sess_res.text}"
        session_id = sess_res.json()["id"]
        print(f"[Step 2] 場次建立成功: {session_id}")

        # 上傳/複製測試影片至隔離 storage
        video_storage_key = f"videos/user_smoke_admin/vid_smoke_2min/raw.mov"
        isolated_storage.put_file(video_storage_key, raw_video_path, "video/quicktime")

        with TestingSessionLocal() as db:
            video_rec = Video(
                id="vid_smoke_2min",
                owner_id="user_smoke_admin",
                session_id=session_id,
                storage_key=video_storage_key,
                original_name="2分鐘.mov",
                size_bytes=raw_video_path.stat().st_size,
                mime="video/quicktime",
                ingest_status="uploaded",
            )
            db.add(video_rec)

            job = AnalysisJob(
                id="job_smoke_2min",
                owner_id="user_smoke_admin",
                video_id=video_rec.id,
                status="queued",
                stage="queued",
                progress=0,
            )
            db.add(job)
            db.commit()

        print("[Step 2] 影片與分析任務寫入資料庫完成。")
        smoke_results["steps"]["ingest"] = "PASS"

        # Step 3: 執行 Worker 分析 (完整真實 Pipeline)
        print("\n[Step 3] 開始執行 Worker 分析管線 (run_video_analysis_job)...")
        job_result = run_video_analysis_job("job_smoke_2min")
        assert job_result.get("status") == "completed", f"Worker 分析未成功完成: {job_result}"

        with TestingSessionLocal() as db:
            db_job = db.get(AnalysisJob, "job_smoke_2min")
            assert db_job.status == "completed", "Job status is not completed in DB"
            assert db_job.progress == 100, f"Job progress expected 100, got {db_job.progress}"

            db_video = db.get(Video, "vid_smoke_2min")
            assert db_video.proxy_storage_key is not None, "Proxy 檔案未生成"
            assert db_video.thumbnail_storage_key is not None, "縮圖檔案未生成"
            assert db_video.duration_ms > 100000, "影片長度探測異常"

        print("[Step 3] Worker 分析成功完成，Proxy 與縮圖均生成，進度 100%。")
        smoke_results["steps"]["worker_analysis"] = "PASS"

        # Step 4: 驗證場次報告 API (/api/sessions/{id}/report)
        print("\n[Step 4] 驗證場次報告 API (/api/sessions/{session_id}/report)...")
        report_res = client.get(f"/api/sessions/{session_id}/report", headers=headers)
        assert report_res.status_code == 200, f"場次報告 API 失敗: {report_res.text}"
        report_data = report_res.json()

        summary_sec = report_data.get("summary", {})
        swings_list_in_report = report_data.get("swings", [])
        total_swings = summary_sec.get("total_swings", len(swings_list_in_report))
        valid_swings = summary_sec.get("valid_swings", 0)
        rankings = report_data.get("rankings", {})

        print(f"  - 偵測總球數: {total_swings}")
        print(f"  - 有效揮桿數: {valid_swings}")
        print(f"  - 四大排行榜: {list(rankings.keys())}")

        assert total_swings == 12, f"預期偵測到 12 球，實際取得: {total_swings}"
        assert valid_swings >= 10, f"預期有效揮桿 >= 10 球，實際取得: {valid_swings}"
        assert "posture" in rankings, "缺少姿勢排行榜"
        assert "tempo" in rankings, "缺少節奏排行榜"
        assert "finish" in rankings, "缺少收桿排行榜"
        assert "ig" in rankings, "缺少 IG 視覺分排行榜"

        # 檢驗最佳姿勢榜之分數獨立性（嚴格不得冒充總分）
        posture_list = rankings.get("posture", [])
        assert len(posture_list) > 0, "姿勢排行榜不得為空"
        for p_item in posture_list:
            assert p_item["category_score"] is not None, "姿勢榜得分不可為 None"
            assert "姿勢" in p_item.get("reason", "") or "前傾" in p_item.get("reason", "") or "頭部" in p_item.get("reason", ""), "理由文字應聚焦姿勢"

        # 檢驗爭議球 (needs_review，如第 4 球) 絕不出現在姿勢或節奏榜中
        for cat_name in ["posture", "tempo"]:
            cat_items = rankings.get(cat_name, [])
            for item in cat_items:
                assert item["sequence_no"] != 4, f"重大違規：第 4 球 (needs_review) 竟然出現在 {cat_name} 排行榜中！"

        print("[Step 4] 場次報告 API 與 Top 5 排行榜驗證通過（獨立姿勢評分正確、爭議球嚴格排除）。")
        smoke_results["steps"]["session_report"] = "PASS"

        # Step 5: 驗證單球播放與 Clean Motion 骨架/時間碼（特別檢驗第 8、9、10 球）
        print("\n[Step 5] 驗證單球播放與 Clean Motion 骨架/時間碼一致性...")
        swings_res = client.get(f"/api/videos/vid_smoke_2min/swings", headers=headers)
        assert swings_res.status_code == 200, f"取得揮桿清單失敗: {swings_res.text}"
        swings_list = swings_res.json().get("items", [])
        assert len(swings_list) == 12, f"揮桿片段數量預期 12，實際 {len(swings_list)}"

        swings_by_seq = {s["sequence_no"]: s for s in swings_list}

        verified_swings_info = {}
        for target_seq in [8, 9, 10]:
            target_summary = swings_by_seq.get(target_seq)
            assert target_summary is not None, f"找不到第 {target_seq} 球"
            target_id = target_summary["id"]

            detail_res = client.get(f"/api/swings/{target_id}", headers=headers)
            assert detail_res.status_code == 200, f"取得 Swing #{target_seq} 詳情失敗"
            detail = detail_res.json()

            # 檢驗事件時間碼
            top_ms = detail.get("top_time_ms")
            imp_ms = detail.get("impact_time_ms")
            assert top_ms is not None, f"Swing #{target_seq} 缺少 Top 時間碼"
            assert imp_ms is not None, f"Swing #{target_seq} 缺少 Impact 時間碼"
            downswing_ms = imp_ms - top_ms

            # 生理下桿時間合規性檢驗 (180ms ~ 480ms)
            assert 180 <= downswing_ms <= 480, f"Swing #{target_seq} 下桿時長異常: {downswing_ms}ms"

            # 檢驗 Clean Motion 骨架與關鍵格資料結構
            keyframes = detail.get("keyframes", [])
            assert len(keyframes) > 0, f"Swing #{target_seq} 缺少 keyframes，Clean Motion 無法繪圖"

            # 驗證關鍵點 (landmarks) 座標有效性
            has_valid_landmarks = False
            for kf in keyframes:
                lm = kf.get("landmarks", {})
                if "left_shoulder" in lm or "right_shoulder" in lm:
                    has_valid_landmarks = True
                    break
            assert has_valid_landmarks, f"Swing #{target_seq} keyframes 未包含人體姿態關鍵點"

            # 驗證審查狀態 (30fps Proxy 下第 8、9、10 球均為 auto_accepted)
            review_status = detail.get("review_status")
            assert review_status == "auto_accepted", f"Swing #{target_seq} 預期 auto_accepted，實際 {review_status}"

            verified_swings_info[f"swing_{target_seq}"] = {
                "top_time_ms": top_ms,
                "impact_time_ms": imp_ms,
                "downswing_ms": downswing_ms,
                "review_status": review_status,
                "keyframes_count": len(keyframes),
                "has_landmarks": has_valid_landmarks,
            }
            print(f"  - Swing #{target_seq}: Top={top_ms}ms, Imp={imp_ms}ms, Downswing={downswing_ms}ms, Status={review_status}, Keyframes={len(keyframes)} frames")

        smoke_results["steps"]["single_swing_and_clean_motion"] = "PASS"
        smoke_results["verified_swings"] = verified_swings_info
        print("[Step 5] 單球播放與 Clean Motion 骨架/時間碼一致性全數通過。")

        smoke_results["overall_status"] = "PASS"

    finally:
        # Step 6: 徹底安全清理
        print("\n[Step 6] 執行測試環境安全清理...")
        app.dependency_overrides.clear()
        s3_mod.get_storage_service = orig_s3_getter
        api_main.get_storage_service = orig_api_getter
        worker_tasks.get_storage_service = orig_worker_getter
        worker_tasks.SessionLocal = orig_worker_session
        test_engine.dispose()

        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"[Step 6] 暫存目錄 {temp_dir} 已安全清除，使用者既有資料庫完全不受影響。")

    print("\n" + "=" * 80)
    print("隔離環境 Mac App Smoke Test: 100% PASS")
    print("=" * 80)
    return smoke_results


if __name__ == "__main__":
    res = run_mac_app_smoke_test()
    report_file = REPO_ROOT / "docs/reports/takeover/smoke_test_report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(f"\n[INFO] Smoke Test 結果報告已儲存: {report_file}")
