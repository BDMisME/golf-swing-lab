#!/usr/bin/env python3
"""
scripts/setup_verification_session.py

建立或取得最新 139 秒 (2分鐘.mov - 12記真實揮桿) 的正式驗收 Session 與 Video：
- 驗證原片 SHA-256 (4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9)
- 透過正式 run_video_analysis_job 完整產出 30fps Proxy、縮圖、12 記真實揮桿與 Keyframes
- 提供結構化 JSON 輸出供 WebKit GUI 實測腳本動態載入
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from apps.api.db import SessionLocal
from apps.api.models import AnalysisJob, PracticeSession, SwingSegment, User, Video
from apps.worker.tasks import run_video_analysis_job
from packages.storage.s3_client import get_storage_service


def setup_or_get_verification_session() -> dict[str, Any]:
    raw_video_path = REPO_ROOT / "測試影片" / "2分鐘.mov"
    if not raw_video_path.exists():
        raise FileNotFoundError(f"找不到測試影片: {raw_video_path}")

    v_sha256 = hashlib.sha256(raw_video_path.read_bytes()).hexdigest()
    expected_sha256 = "4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9"
    if v_sha256 != expected_sha256:
        raise ValueError(f"測試影片 SHA256 不符預期: {v_sha256} != {expected_sha256}")

    with SessionLocal() as db:
        admin = db.query(User).filter(User.role == "admin").first()
        if not admin:
            raise RuntimeError("系統中未找到管理員帳號")

        # 檢查是否已有相同 SHA-256 且揮桿數為 12 的 Session
        target_session = None
        target_video = None
        candidate_videos = db.query(Video).filter(Video.sha256 == v_sha256).all()
        for v in candidate_videos:
            sw_count = db.query(SwingSegment).filter(SwingSegment.video_id == v.id).count()
            if sw_count == 12:
                sess = db.get(PracticeSession, v.session_id)
                if sess and v.proxy_storage_key:
                    target_session = sess
                    target_video = v
                    break

        if target_session and target_video:
            print(f"[OK] 找到既有 12 球正式驗收場次: Session={target_session.id}, Video={target_video.id}")
        else:
            print(f"[INIT] 建立全新 139 秒 2分鐘.mov 驗收場次並執行正式分析管線...")
            sess = PracticeSession(
                owner_id=admin.id,
                title="2分鐘.mov 正式驗收場次 (12記揮桿)",
                date="2026-10-27",
                club="7I",
                handedness="right",
                camera_angle="DTL",
                notes="由 setup_verification_session.py 自動建立供 WebKit GUI 驗收使用",
            )
            db.add(sess)
            db.flush()

            storage = get_storage_service()
            v_key = f"raw/{admin.id}/{sess.id}/video_2min.mov"
            storage.put_file(v_key, raw_video_path, "video/quicktime")

            vid = Video(
                owner_id=admin.id,
                session_id=sess.id,
                storage_key=v_key,
                original_name="2分鐘.mov",
                size_bytes=raw_video_path.stat().st_size,
                mime="video/quicktime",
                sha256=v_sha256,
                ingest_status="uploaded",
            )
            db.add(vid)
            db.flush()

            job = AnalysisJob(
                owner_id=admin.id,
                video_id=vid.id,
                status="queued",
                stage="queued",
            )
            db.add(job)
            db.commit()

            print(f"  -> 開始執行 Worker 分析任務 (Job ID: {job.id})...")
            job_res = run_video_analysis_job(job.id)
            print(f"  -> Worker 分析結果: {job_res}")

            target_session = sess
            target_video = vid

        # 讀取分析產出的 12 球明細
        swings = (
            db.query(SwingSegment)
            .filter(SwingSegment.video_id == target_video.id)
            .order_by(SwingSegment.sequence_no)
            .all()
        )
        print(f"\n[INFO] 場次已就緒，包含 {len(swings)} 記揮桿:")
        swings_data = []
        for s in swings:
            ev_map = {e.event_name: e.time_ms for e in s.events}
            top_ms = ev_map.get("top")
            imp_ms = ev_map.get("impact_estimated") or ev_map.get("impact")
            print(
                f"  #{s.sequence_no:2d} id={s.id} range=[{s.start_ms}..{s.end_ms}] "
                f"top={top_ms} imp={imp_ms} status={s.review_status}"
            )
            swings_data.append({
                "sequence_no": s.sequence_no,
                "id": s.id,
                "start_ms": s.start_ms,
                "end_ms": s.end_ms,
                "top_ms": top_ms,
                "imp_ms": imp_ms,
                "review_status": s.review_status,
                "events": ev_map,
            })

        out = {
            "session_id": target_session.id,
            "session_title": target_session.title,
            "video_id": target_video.id,
            "video_sha256": target_video.sha256,
            "video_duration_ms": target_video.duration_ms,
            "proxy_storage_key": target_video.proxy_storage_key,
            "swings": swings_data,
        }
        return out


if __name__ == "__main__":
    res = setup_or_get_verification_session()
    print("\n" + json.dumps(res, indent=2, ensure_ascii=False))
