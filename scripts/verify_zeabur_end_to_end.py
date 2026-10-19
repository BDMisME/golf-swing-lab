import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

from tests.fixtures.video_factory import create_synthetic_dtl_video

API_BASE = os.environ.get("TARGET_API_URL", "https://golf-swing-lab-api.zeabur.app").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "golfer@swinglab.local")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "GolfSwingLab!2026")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    log(f"開始 Zeabur 遠端生產環境端對端驗收: {API_BASE}")

    with httpx.Client(timeout=30.0) as client:
        # 1. 檢查 readyz
        r_ready = client.get(f"{API_BASE}/readyz")
        log(f"GET /readyz -> {r_ready.status_code} {r_ready.text}")
        if r_ready.status_code != 200:
            log("伺服器未就緒，終止驗收")
            return 1

        # 2. 登入
        r_login = client.post(f"{API_BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r_login.status_code != 200:
            log(f"登入失敗: {r_login.status_code} {r_login.text}")
            return 1
        token = r_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        log("登入成功，已取得 JWT Token")

        # 3. 檢查設定
        r_settings = client.get(f"{API_BASE}/api/settings", headers=headers)
        log(f"目前設定: {r_settings.json()}")

        # 4. 建立場次
        r_sess = client.post(
            f"{API_BASE}/api/sessions",
            headers=headers,
            json={
                "title": f"Gemini 3.8 Flash 線上驗收場次 ({time.strftime('%m/%d %H:%M')})",
                "date": time.strftime("%Y-%m-%d"),
                "club": "7I",
                "handedness": "right",
                "camera_angle": "DTL",
                "notes": "全自動切球 + Gemini 3.8 Flash 教練報告驗證",
            },
        )
        if r_sess.status_code not in (200, 201):
            log(f"建立場次失敗: {r_sess.status_code} {r_sess.text}")
            return 1
        sess_data = r_sess.json()
        session_id = sess_data["id"]
        log(f"建立場次成功: session_id={session_id}")

        # 5. 建立合成 6 秒 DTL 揮桿影片
        tmp_video = Path("/tmp/gsl_zeabur_verify_6s.mp4")
        if not tmp_video.exists():
            log("正在生成 6 秒合成 DTL 影片...")
            create_synthetic_dtl_video(
                tmp_video,
                duration_ms=6000,
                fps=30,
                swings_spec=[
                    {"start_ms": 1200, "end_ms": 4400, "label": "valid_swing", "spine_delta_deg": 2.1}
                ],
            )
        video_bytes = tmp_video.read_bytes()
        file_size = len(video_bytes)
        sha256_hex = hashlib.sha256(video_bytes).hexdigest()
        log(f"影片準備完成: 大小={file_size} bytes, sha256={sha256_hex[:12]}...")

        # 6. 初始化分段上傳 (POST /api/uploads/initiate)
        r_init = client.post(
            f"{API_BASE}/api/uploads/initiate",
            headers=headers,
            json={
                "session_id": session_id,
                "filename": "zeabur_gemini_verify.mp4",
                "size_bytes": file_size,
                "mime_type": "video/mp4",
                "part_size_bytes": 5242880,
                "sha256": sha256_hex,
            },
        )
        if r_init.status_code not in (200, 201):
            log(f"初始化上傳失敗: {r_init.status_code} {r_init.text}")
            return 1
        init_data = r_init.json()
        upload_id = init_data["upload_id"]
        video_id = init_data["video_id"]
        log(f"初始化上傳成功: upload_id={upload_id}, video_id={video_id}")

        # 7. 上傳區段內容 (PUT /api/uploads/{upload_id}/parts/1/content)
        log(f"正在上傳第 1 區段 ({file_size} bytes)...")
        r_part = client.put(
            f"{API_BASE}/api/uploads/{upload_id}/parts/1/content",
            headers=headers,
            content=video_bytes,
            timeout=60.0,
        )
        if r_part.status_code not in (200, 204):
            log(f"上傳區段失敗: {r_part.status_code} {r_part.text}")
            return 1
        part_res = r_part.json()
        etag = part_res.get("etag", sha256_hex[:16])
        log(f"區段上傳成功: etag={etag}")

        # 8. 完成上傳 (POST /api/uploads/{upload_id}/complete)
        r_comp = client.post(
            f"{API_BASE}/api/uploads/{upload_id}/complete",
            headers=headers,
            json={
                "parts": [{"part_number": 1, "etag": etag, "size_bytes": file_size}],
                "sha256": sha256_hex,
            },
        )
        if r_comp.status_code != 200:
            log(f"完成上傳失敗: {r_comp.status_code} {r_comp.text}")
            return 1
        log("影片合併與 SHA256 驗證成功")

        # 9. 觸發分析 (POST /api/videos/{video_id}/analyze)
        r_ana = client.post(f"{API_BASE}/api/videos/{video_id}/analyze", headers=headers)
        if r_ana.status_code != 200:
            log(f"觸發分析失敗: {r_ana.status_code} {r_ana.text}")
            return 1
        job_id = r_ana.json()["job_id"]
        log(f"分析任務已觸發: job_id={job_id}")

        # 10. 輪詢分析進度
        for attempt in range(60):
            time.sleep(2)
            r_job = client.get(f"{API_BASE}/api/jobs/{job_id}", headers=headers)
            if r_job.status_code != 200:
                log(f"查詢任務進度異常: {r_job.status_code}")
                continue
            job_state = r_job.json()
            status = job_state.get("status")
            stage = job_state.get("stage")
            progress = job_state.get("progress")
            log(f"任務狀態: status={status}, stage={stage}, progress={progress}%")
            if status == "completed":
                log("分析完成！")
                break
            elif status in ("failed", "cancelled"):
                log(f"任務終止: {status}, error={job_state.get('error_message')}")
                return 1
        else:
            log("任務等待逾時 (120s)")
            return 1

        # 11. 取得場次完整報告與教練回饋
        r_report = client.get(f"{API_BASE}/api/sessions/{session_id}/report", headers=headers)
        if r_report.status_code != 200:
            log(f"取得場次報告失敗: {r_report.status_code} {r_report.text}")
            return 1
        rep_data = r_report.json()
        swings = rep_data.get("swings", [])
        coach_rep = rep_data.get("coach_report", {})
        log(f"偵測到揮桿球數: {len(swings)}")
        log(f"教練報告 Provider: {coach_rep.get('provider')}, Model: {coach_rep.get('model')}")
        log(f"教練摘要: {coach_rep.get('summary')}")
        if coach_rep.get("observations"):
            log(f"關鍵觀察: {coach_rep['observations'][0].get('title')}")
        if coach_rep.get("priority_fixes"):
            log(f"改善課表: {coach_rep['priority_fixes'][0].get('focus_area')}")

        log("Zeabur 遠端生產環境全流程驗收 SUCCESS!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
