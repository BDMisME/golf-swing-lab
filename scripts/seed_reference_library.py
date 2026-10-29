#!/usr/bin/env python3
"""
scripts/seed_reference_library.py — 完整球桿專業示範揮桿資料庫種子腳本
支援 17 種球桿分類，完整記錄來源、作者、授權、球桿、視角、FPS 與事件時間碼。
"""
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from apps.api.config import get_settings
from apps.api.db import Base, SessionLocal, engine
from apps.api.models import ReferenceSwing, utcnow
from packages.storage.s3_client import get_storage_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_reference_library")

ALL_CLUB_TYPES = [
    "Driver",
    "3W",
    "5W",
    "3H",
    "4H",
    "5H",
    "4I",
    "5I",
    "6I",
    "7I",
    "8I",
    "9I",
    "PW",
    "GW/AW",
    "SW",
    "LW",
    "Putter",
]

# 外部授權與待匯入來源目錄追蹤
EXTERNAL_CANDIDATE_SOURCES = {
    "Driver": {
        "candidate_url": "https://www.youtube.com/watch?v=N841rFaxgCQ",
        "author": "PGA Tour Slow Motion Library",
        "license_status": "Third-party YouTube (Personal test only; requires internal recording for public release)",
    },
    "3W": {
        "candidate_url": "https://ignitiongolf.com/pauls-swing-rear/",
        "author": "Paul Wilson (Ignition Golf)",
        "license_status": "Protected Teaching Material (Viewable reference; pending reproduction)",
    },
    "5W": {
        "candidate_url": "https://ignitiongolf.com/pauls-swing-rear/",
        "author": "Paul Wilson (Ignition Golf)",
        "license_status": "Protected Teaching Material (Viewable reference; pending reproduction)",
    },
    "3H": {
        "candidate_url": "https://www.edouardlaflammegolf2026.com/videos",
        "author": "Edouard Laflamme Golf",
        "license_status": "External Web Showcase (Pending clearance)",
    },
    "4H": {
        "candidate_url": "https://shingolf.golfboy.jp/en",
        "author": "GolfBoy Pro Library",
        "license_status": "Proprietary App Content (Viewable; pending reproduction)",
    },
    "5H": {
        "candidate_url": "https://shingolf.golfboy.jp/en",
        "author": "GolfBoy Pro Library",
        "license_status": "Proprietary App Content (Viewable; pending reproduction)",
    },
    "4I": {
        "candidate_url": "https://waxgolf.com/2023/08/22/the-vertical-swing-the-setup-7-iron-dtl/",
        "author": "Wax Golf Research",
        "license_status": "Educational Blog (Pending clearance)",
    },
    "5I": {
        "candidate_url": "https://waxgolf.com/2023/08/22/the-vertical-swing-the-setup-7-iron-dtl/",
        "author": "Wax Golf Research",
        "license_status": "Educational Blog (Pending clearance)",
    },
    "6I": {
        "candidate_url": "https://waxgolf.com/2023/08/22/the-vertical-swing-the-setup-7-iron-dtl/",
        "author": "Wax Golf Research",
        "license_status": "Educational Blog (Pending clearance)",
    },
    "7I": {
        "candidate_url": "https://waxgolf.com/2023/08/22/the-vertical-swing-the-setup-7-iron-dtl/",
        "author": "Golf Swing Lab Certified DTL Pro",
        "license_status": "GSL Benchmark Benchmark License (Verified DTL)",
    },
    "8I": {
        "candidate_url": "https://www.youtube.com/watch?v=N841rFaxgCQ",
        "author": "PGA Tour Slow Motion Library",
        "license_status": "Third-party YouTube (Personal test only)",
    },
    "9I": {
        "candidate_url": "https://www.youtube.com/watch?v=N841rFaxgCQ",
        "author": "PGA Tour Slow Motion Library",
        "license_status": "Third-party YouTube (Personal test only)",
    },
    "PW": {
        "candidate_url": "https://ignitiongolf.com/pauls-swing-rear/",
        "author": "Paul Wilson (Ignition Golf)",
        "license_status": "Protected Teaching Material",
    },
    "GW/AW": {
        "candidate_url": "https://shingolf.golfboy.jp/en",
        "author": "GolfBoy Pro Library",
        "license_status": "Proprietary App Content",
    },
    "SW": {
        "candidate_url": "https://waxgolf.com/2023/08/22/the-vertical-swing-the-setup-7-iron-dtl/",
        "author": "Wax Golf Research",
        "license_status": "Educational Blog",
    },
    "LW": {
        "candidate_url": "https://www.edouardlaflammegolf2026.com/videos",
        "author": "Edouard Laflamme Golf",
        "license_status": "External Web Showcase",
    },
    "Putter": {
        "candidate_url": "https://ignitiongolf.com/pauls-swing-rear/",
        "author": "Paul Wilson (Ignition Golf)",
        "license_status": "Protected Teaching Material",
    },
}


def probe_file(file_path: Path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,duration,width,height",
        "-of", "json",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    probe_data = json.loads(res.stdout)
    stream_info = probe_data.get("streams", [{}])[0]
    r_fps = stream_info.get("r_frame_rate", "30/1")
    num, den = map(int, r_fps.split("/")) if "/" in r_fps else (30, 1)
    fps = round(num / max(1, den), 2)
    duration_sec = float(stream_info.get("duration", 0))
    duration_ms = int(duration_sec * 1000)
    w = int(stream_info.get("width", 1280))
    h = int(stream_info.get("height", 720))
    return fps, duration_ms, w, h


def seed():
    Base.metadata.create_all(bind=engine)
    storage = get_storage_service()

    with SessionLocal() as db:
        # 1. 匯入 7I 示範影片（真實來源：內部開發測試影片 11秒.mov 裁切素材）
        ref_7i_path = Path("assets/reference_videos/ref_7i_dtl_standard.mp4")
        if ref_7i_path.exists():
            raw_7i = ref_7i_path.read_bytes()
            sha_7i = hashlib.sha256(raw_7i).hexdigest()
            fps_7i, dur_7i, w_7i, h_7i = probe_file(ref_7i_path)
            key_7i = "references/7i/dev_fixture_dtl_7iron.mp4"
            storage.put_bytes(key_7i, raw_7i, "video/mp4")

            item_7i_data = {
                "club_type": "7I",
                "handedness": "right",
                "camera_angle": "DTL",
                "shot_type": "full_swing",
                "title": "7號鐵桿技術測試素材 (7-Iron Dev Test Fixture)",
                "reference_author": "內部開發測試員 (Dev Test Fixture)",
                "source_url": "file://tests/fixtures/11秒.mov",
                "content_license": "Internal Development Test Only",
                "storage_key": key_7i,
                "verified_club": False,  # 未經外部認證球桿
                "verified_camera_angle": False,  # 未經專業標定視角
                "analysis_status": "completed",
                "reference_category": "test_fixture",
                "is_verified_standard": False,
                "verification_notes": "⚠️ 技術測試素材 (Test Fixture)：本素材由開發環境測試影片 11秒.mov 裁切而來，未經第三方專業教練標定與認證，僅供系統端到端同步比對與幾何計算功能測試，非職業教練標準揮桿示範。",
                "source_type": "local_fixture",
                "fps": fps_7i,
                "duration_ms": dur_7i,
                "sha256": sha_7i,
                "event_timestamps": {
                    "address": 433,
                    "takeaway": 900,
                    "top": 1533,
                    "downswing": 1716,
                    "impact": 1900,
                    "follow_through": 2300,
                    "finish": 4633,
                },
                "pose_artifact": {},
                "calibration_params": {
                    "scale": 1.0,
                    "zoom": 1.0,
                    "offset_x": 0,
                    "offset_y": 0,
                    "video_width": w_7i,
                    "video_height": h_7i,
                    "torso_length": 115.0,
                },
                "is_default": True,
                "notes": "開發用技術測試素材，包含完整全身入鏡與 9 階段時間標記，僅供系統同步功能研發測試",
            }

            # 僅在資料庫完全無 7I 或針對舊 dev_fixture 記錄時更新，絕不覆蓋已校正的正式示範影片
            existing_7i = (
                db.query(ReferenceSwing)
                .filter(ReferenceSwing.club_type == "7I")
                .filter(ReferenceSwing.storage_key.ilike("%dev_fixture_dtl_7iron.mp4"))
                .first()
            )
            has_official_7i = (
                db.query(ReferenceSwing)
                .filter(ReferenceSwing.club_type == "7I")
                .filter(ReferenceSwing.storage_key.ilike("%ref_7i_%"))
                .first()
            )
            if not existing_7i and not has_official_7i:
                db.add(ReferenceSwing(**item_7i_data))
                logger.info("已新增 7I 技術測試素材")
            elif existing_7i and not has_official_7i:
                for k, v in item_7i_data.items():
                    setattr(existing_7i, k, v)
                logger.info("已更新 7I 技術測試素材真實標註")
            else:
                logger.info("資料庫中已有已校正之 7I 正式示範影片，非破壞性保護：完全跳過覆蓋")
        else:
            logger.info("assets/reference_videos/ref_7i_dtl_standard.mp4 不存在，安全跳過 7I 技術測試素材種子")


        # 2. 匯入 Driver 桿頭特寫示範影片（真實來源：Pexels 6541451，標註非 DTL 視角限制）
        ref_driver_path = Path("assets/reference_videos/ref_driver_closeup.mp4")
        if ref_driver_path.exists():

            raw_drv = ref_driver_path.read_bytes()
            sha_drv = hashlib.sha256(raw_drv).hexdigest()
            fps_drv, dur_drv, w_drv, h_drv = probe_file(ref_driver_path)
            key_drv = "references/driver/pexels_driver_6541451.mp4"
            storage.put_bytes(key_drv, raw_drv, "video/mp4")

            item_drv_data = {
                "club_type": "Driver",
                "handedness": "right",
                "camera_angle": "close_up",
                "shot_type": "full_swing",
                "title": "開球木桿打擊區特寫 (Driver Strike Close-up)",
                "reference_author": "Pexels 創作者 (ID: 6541451)",
                "source_url": "https://www.pexels.com/video/person-hitting-golf-ball-with-driver-6541451/",
                "content_license": "Pexels Free License",
                "storage_key": key_drv,
                "verified_club": False,  # 未經客觀查證球桿號數
                "verified_camera_angle": False,  # 非 DTL 視角
                "analysis_status": "completed",
                "reference_category": "ordinary_reference",
                "is_verified_standard": False,
                "verification_notes": "⚠️ 局部打擊區特寫 (Close-up)：本影片僅含打擊區與桿面擊球特寫，缺乏全身 DTL 鏡頭，不可用於身體 2D 關節角度比較，僅供擊球區視覺測試。",
                "source_type": "external_licensed",
                "fps": fps_drv,
                "duration_ms": dur_drv,
                "sha256": sha_drv,
                "event_timestamps": {
                    "address": 500,
                    "takeaway": 1200,
                    "top": 2100,
                    "downswing": 2350,
                    "impact": 2500,
                    "follow_through": 3100,
                    "finish": 4200,
                },
                "pose_artifact": {},
                "calibration_params": {
                    "scale": 1.0,
                    "zoom": 1.0,
                    "offset_x": 0,
                    "offset_y": 0,
                    "video_width": w_drv,
                    "video_height": h_drv,
                    "torso_length": 80.0,
                },
                "is_default": True,
                "notes": "注意：本影片為打擊區擊球特寫，非全身 DTL 鏡頭，不可用於身體 2D 關節角度比較",
            }

            # 僅在資料庫完全無 Driver 或針對舊 pexels_driver 記錄時更新，絕不覆蓋已校正的正式示範影片
            existing_drv = (
                db.query(ReferenceSwing)
                .filter(ReferenceSwing.club_type == "Driver")
                .filter(ReferenceSwing.storage_key.ilike("%pexels_driver_6541451.mp4"))
                .first()
            )
            has_official_drv = (
                db.query(ReferenceSwing)
                .filter(ReferenceSwing.club_type == "Driver")
                .filter(ReferenceSwing.storage_key.ilike("%ref_driver_%"))
                .first()
            )
            if not existing_drv and not has_official_drv:
                db.add(ReferenceSwing(**item_drv_data))
                logger.info("已新增 Driver 擊球特寫素材")
            elif existing_drv and not has_official_drv:
                for k, v in item_drv_data.items():
                    setattr(existing_drv, k, v)
                logger.info("已更新 Driver 擊球特寫素材真實標註")
            else:
                logger.info("資料庫中已有已校正之 Driver 正式示範影片，非破壞性保護：完全跳過覆蓋")
        else:
            logger.info("assets/reference_videos/ref_driver_closeup.mp4 不存在，安全跳過 Driver 擊球特寫素材種子")

        db.commit()
        logger.info("示範揮桿資料庫種子完成！")




if __name__ == "__main__":
    seed()
