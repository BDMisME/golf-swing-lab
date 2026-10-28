#!/usr/bin/env python3
"""
scripts/verify_multipart_upload_e2e.py — 真實大檔案分段上傳、合併與串流驗證腳本
"""
import hashlib
import sys
from pathlib import Path
import httpx

from apps.api.config import get_settings


def main() -> None:
    s = get_settings()
    video_path = Path("測試影片/11秒.mov")
    if not video_path.exists():
        print("❌ 測試影片不存在: 測試影片/11秒.mov")
        sys.exit(1)

    video_data = video_path.read_bytes()
    total_size = len(video_data)
    full_sha256 = hashlib.sha256(video_data).hexdigest()
    part_size = 5 * 1024 * 1024  # 5MB per part

    client = httpx.Client(base_url="http://127.0.0.1:28000", timeout=60.0)

    # 1. 登入
    login_res = client.post(
        "/api/auth/login",
        json={"email": s.admin_email, "password": s.admin_password},
    )
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ 1. 登入成功，取得 Token")

    # 2. 建立場次
    sess_res = client.post(
        "/api/sessions",
        json={"title": "自動化大檔案分段上傳驗證場次", "target_fps": 30},
        headers=headers,
    )
    assert sess_res.status_code == 201, f"Session creation failed: {sess_res.text}"
    session_id = sess_res.json()["id"]
    print(f"✅ 2. 建立場次成功: session_id={session_id}")

    # 3. 發起 Multipart 上傳
    init_res = client.post(
        "/api/uploads/initiate",
        json={
            "session_id": session_id,
            "filename": "11s_iphone_e2e.mov",
            "mime_type": "video/quicktime",
            "size_bytes": total_size,
            "part_size_bytes": part_size,
            "sha256": full_sha256,
        },
        headers=headers,
    )
    assert init_res.status_code == 200, f"Upload initiate failed: {init_res.text}"
    init_data = init_res.json()
    upload_id = init_data["upload_id"]
    total_parts = init_data["total_parts"]
    print(f"✅ 3. 發起 Multipart 上傳成功: upload_id={upload_id}, total_parts={total_parts}")

    # 4. 逐分段上傳
    parts_info = []
    for p in range(1, total_parts + 1):
        chunk = video_data[(p - 1) * part_size : p * part_size]
        chunk_sha = hashlib.sha256(chunk).hexdigest()
        part_res = client.put(
            f"/api/uploads/{upload_id}/parts/{p}/content",
            content=chunk,
            headers={"Content-Type": "application/octet-stream", **headers},
        )
        assert part_res.status_code == 200, f"Part {p} failed: {part_res.text}"
        etag = part_res.json()["etag"]
        parts_info.append({"part_number": p, "etag": etag, "sha256": chunk_sha})
        print(f"   分段 {p}/{total_parts} 上傳完成 (etag={etag})")

    # 5. 完成合併
    comp_res = client.post(
        f"/api/uploads/{upload_id}/complete",
        json={
            "parts": parts_info,
            "sha256": full_sha256,
        },
        headers=headers,
    )
    assert comp_res.status_code == 200, f"Complete failed: {comp_res.text}"
    comp_data = comp_res.json()
    video_id = comp_data.get("video_id")
    print(f"✅ 4. 分段合併完成: video_id={video_id}")

    # 6. 驗證影片串流與 HTTP 206 Range 讀取
    stream_url = f"/api/videos/{video_id}/stream"
    range_res = client.get(stream_url, headers={**headers, "Range": "bytes=0-1048575"})
    assert range_res.status_code == 206, f"Range stream failed: {range_res.status_code}"
    assert len(range_res.content) == 1048576
    assert range_res.content == video_data[0:1048576]
    print(f"✅ 5. 影片串流與 HTTP 206 Range 讀取 100% 吻合！")

    print("\n🎉 大檔案分段上傳與串流驗證全數通過 (PASS)！")


if __name__ == "__main__":
    main()
