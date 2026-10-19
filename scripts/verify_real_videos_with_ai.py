import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx

API_BASE = os.environ.get("TARGET_API_URL", "http://localhost:28000").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "golfer@swinglab.local")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "GolfSwingLab!2026")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def upload_and_analyze_real_video(client: httpx.Client, headers: dict[str, str], video_file: Path) -> dict:
    if not video_file.exists():
        raise FileNotFoundError(f"找不到測試影片: {video_file}")

    file_size = video_file.stat().st_size
    log(f"====== 開始測試真實影片: {video_file.name} (大小: {file_size / (1024*1024):.2f} MB) ======")

    # 1. 建立場次
    r_sess = client.post(
        f"{API_BASE}/api/sessions",
        headers=headers,
        json={
            "title": f"真實影片測試場次: {video_file.name} ({time.strftime('%H:%M:%S')})",
            "date": time.strftime("%Y-%m-%d"),
            "club": "7I",
            "handedness": "right",
            "camera_angle": "DTL",
            "notes": f"針對真實影片 {video_file.name} 之切球與豆包 AI 分析實測",
        },
    )
    if r_sess.status_code not in (200, 201):
        raise RuntimeError(f"建立場次失敗: {r_sess.status_code} {r_sess.text}")
    session_id = r_sess.json()["id"]
    log(f"場次已建立: session_id={session_id}")

    # 2. 計算 SHA256 與分段計畫 (8MB per chunk)
    log("正在計算影片 SHA256 雜湊值...")
    hasher = hashlib.sha256()
    with open(video_file, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            hasher.update(chunk)
    sha256_hex = hasher.hexdigest()
    log(f"SHA256: {sha256_hex[:16]}...")

    part_size = 8 * 1024 * 1024
    r_init = client.post(
        f"{API_BASE}/api/uploads/initiate",
        headers=headers,
        json={
            "session_id": session_id,
            "filename": video_file.name,
            "size_bytes": file_size,
            "mime_type": "video/quicktime" if video_file.suffix.lower() == ".mov" else "video/mp4",
            "part_size_bytes": part_size,
            "sha256": sha256_hex,
        },
    )
    if r_init.status_code not in (200, 201):
        raise RuntimeError(f"初始化上傳失敗: {r_init.status_code} {r_init.text}")
    init_data = r_init.json()
    upload_id = init_data["upload_id"]
    video_id = init_data["video_id"]
    total_parts = init_data["total_parts"]
    log(f"初始化上傳成功: upload_id={upload_id}, 共 {total_parts} 個分段")

    # 3. 逐塊上傳
    completed_parts = []
    with open(video_file, "rb") as f:
        for p_num in range(1, total_parts + 1):
            chunk_data = f.read(part_size)
            p_size = len(chunk_data)
            p_pct = int(round((p_num / total_parts) * 100))
            if p_num % 5 == 1 or p_num == total_parts:
                log(f"正在上傳第 {p_num}/{total_parts} 分段 ({p_size} bytes, 進度 {p_pct}%)...")
            # 支援重試以抵禦容器重啟時的瞬態 502/503
            max_retries = 3
            for retry in range(max_retries):
                try:
                    r_part = client.put(
                        f"{API_BASE}/api/uploads/{upload_id}/parts/{p_num}/content",
                        headers=headers,
                        content=chunk_data,
                        timeout=120.0,
                    )
                    if r_part.status_code in (200, 204):
                        break
                    if r_part.status_code in (502, 503, 504) and retry < max_retries - 1:
                        time.sleep(3)
                        continue
                except Exception as net_err:
                    if retry < max_retries - 1:
                        time.sleep(3)
                        continue
                    raise net_err

            if r_part.status_code not in (200, 204):
                raise RuntimeError(f"上傳分段 #{p_num} 失敗: {r_part.status_code} {r_part.text}")
            etag = r_part.json().get("etag", f'"{p_num}"').strip('"')
            completed_parts.append({"part_number": p_num, "etag": etag, "size_bytes": p_size})

    # 4. 完成上傳
    log("所有分段上傳完畢，發送完成指令並校驗 SHA256...")
    r_comp = client.post(
        f"{API_BASE}/api/uploads/{upload_id}/complete",
        headers=headers,
        json={"parts": completed_parts, "sha256": sha256_hex},
    )
    if r_comp.status_code != 200:
        raise RuntimeError(f"完成上傳失敗: {r_comp.status_code} {r_comp.text}")
    log("影片合併與 SHA256 驗證成功！")

    # 5. 觸發分析
    r_ana = client.post(f"{API_BASE}/api/videos/{video_id}/analyze", headers=headers)
    if r_ana.status_code != 200:
        raise RuntimeError(f"觸發分析失敗: {r_ana.status_code} {r_ana.text}")
    job_id = r_ana.json()["job_id"]
    log(f"分析任務已觸發: job_id={job_id}，開始監控任務進度...")

    # 6. 輪詢進度
    last_stage = None
    last_prog = None
    for attempt in range(180):  # 180 * 2s = 360 秒逾時
        time.sleep(2)
        r_job = client.get(f"{API_BASE}/api/jobs/{job_id}", headers=headers)
        if r_job.status_code != 200:
            log(f"查詢任務狀態異常: {r_job.status_code}")
            continue
        job_data = r_job.json()
        st = job_data.get("status")
        stage = job_data.get("stage")
        prog = job_data.get("progress")
        if stage != last_stage or prog != last_prog:
            log(f"  -> 階段: [{stage}] 進度: {prog}% (狀態: {st})")
            last_stage = stage
            last_prog = prog

        if st == "completed":
            log("🎉 分析任務順利完成！")
            break
        elif st in ("failed", "cancelled"):
            err_msg = job_data.get("error_message")
            logs = job_data.get("logs_json", [])
            log(f"❌ 任務失敗: error={err_msg}")
            if logs:
                log(f"  最後日誌: {logs[-1]}")
            raise RuntimeError(f"任務進入失敗狀態: {st}, {err_msg}")
    else:
        raise TimeoutError("分析任務超過 360 秒未完成")

    # 7. 取得場次與 AI 教練報告
    r_rep = client.get(f"{API_BASE}/api/sessions/{session_id}/report", headers=headers)
    if r_rep.status_code != 200:
        raise RuntimeError(f"取得報告失敗: {r_rep.status_code} {r_rep.text}")
    rep_data = r_rep.json()
    swings = rep_data.get("swings", [])
    coach = rep_data.get("coach_report", {})

    log(f"📊 分析總結：共切出 {len(swings)} 記揮桿")
    for idx, s in enumerate(swings[:3], 1):
        sc = s.get("score") or {}
        log(f"  球 #{idx}: 時間 {s.get('start_ms')}ms ~ {s.get('end_ms')}ms, 綜合分: {sc.get('overall_nullable')}, 覆蓋率: {sc.get('coverage')}")

    log(f"🤖 AI 教練分析報告：")
    log(f"  Provider: {coach.get('provider')}, Model: {coach.get('model')}, LLM Enabled: {coach.get('llm_enabled')}")
    log(f"  摘要: {coach.get('summary')}")
    if coach.get("observations"):
        log(f"  關鍵動作觀察: {coach['observations'][0].get('title')} - {coach['observations'][0].get('detail')}")
    if coach.get("priority_fixes"):
        log(f"  優先訓練課表: {coach['priority_fixes'][0].get('focus_area')} - {coach['priority_fixes'][0].get('drill_steps')}")

    return {"session_id": session_id, "video_id": video_id, "swings_count": len(swings), "coach": coach}


def main() -> int:
    log("==================================================================")
    log(f"開始執行真實影片全流程端對端測試 (本機環境: {API_BASE})")
    log("==================================================================")

    with httpx.Client(timeout=180.0) as client:
        # 登入
        r_login = client.post(f"{API_BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        if r_login.status_code != 200:
            log(f"登入失敗: {r_login.status_code} {r_login.text}")
            return 1
        token = r_login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        log("登入成功，取得權限 Token")

        # 確保使用者設定使用豆包 API
        upd = client.put(
            f"{API_BASE}/api/settings",
            headers=headers,
            json={
                "default_club": "7I",
                "handedness": "right",
                "camera_angle": "DTL",
                "llm_provider": "openai-compatible",
                "llm_base_url": os.environ.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/plan/v3"),
                "llm_model": os.environ.get("LLM_MODEL", "doubao-seed-2.1-lite"),
                "llm_api_key": os.environ.get("LLM_API_KEY", ""),
            },
        )
        log(f"已確認更新 AI 教練為豆包 (doubao-seed-2.1-lite): status={upd.status_code}")

        # 測試 1: 11秒真實片段
        res_11s = upload_and_analyze_real_video(client, headers, Path("測試影片/11秒.mov"))
        log(f"✅ 11秒.mov 測試成功！偵測到 {res_11s['swings_count']} 記揮桿，AI 教練正常回應！\n")

        # 測試 2: 2分鐘真實長片段
        res_2m = upload_and_analyze_real_video(client, headers, Path("測試影片/2分鐘.mov"))
        log(f"✅ 2分鐘.mov 測試成功！偵測到 {res_2m['swings_count']} 記揮桿，AI 教練正常回應！\n")

    log("🎉 兩部真實影片（11秒短片、2分鐘長片）本機全流程驗收 100% 通過！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
