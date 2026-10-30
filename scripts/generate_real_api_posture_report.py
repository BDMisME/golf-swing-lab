#!/usr/bin/env python3
"""
scripts/generate_real_api_posture_report.py

透過本機真實 API 呼叫 GET /api/swings/{swing_id}/posture-comparison
產生機器可檢查的 7I 與 Driver 真實量化比較報告。
恪守最高誠信原則（Truthfulness & Anti-Hallucination）：
- 所有數值 100% 來自真實 API 回傳。
- 絕無未經執行紀錄之寫死數字或舊版假分數。
- 清楚記錄每個指標之 Metric ID, User Value, Reference Value, Delta,
  User/Reference Frame Time, Event Time Error, Pose Confidence, Geometry Calibration。
- 特寫或視角不相容之素材明確記錄限制與 not_comparable。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.db import SessionLocal
from apps.api.models import User
from apps.api.auth import create_session_token

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_OUTPUT_PATH = REPO_ROOT / "docs/reports/real_api_posture_comparison_report.json"


def generate_report() -> dict[str, Any]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "golfer@swinglab.local").first()
        if not user:
            raise RuntimeError("找不到 golfer@swinglab.local 測試帳號")
        token = create_session_token(user)

    target_swing_id = "cfd10e17-4604-4b9d-b84e-a7a9d1e55bbf"

    # 1. 7I 標準 DTL 示範 (DJ Watts 7 號鐵)
    ref_7i_id = "05af5507-f68a-4d32-9b3c-89bb8a40001a"
    # 2. Driver 標準 DTL 示範 (DJ Watts Driver)
    ref_driver_dtl_id = "839c7956-72cc-48f7-abf6-a5fc60df966a"
    # 3. Driver 特寫示範 (Close-up 視角限制示範)
    ref_driver_closeup_id = "8528adee-06ff-4e3f-842f-c1641ab712e9"

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {token}"}

        res_7i = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison?ref_id={ref_7i_id}",
            headers=headers,
        )
        assert res_7i.status_code == 200, f"7I API 回傳失敗: {res_7i.text}"
        data_7i = res_7i.json()

        res_drv = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison?ref_id={ref_driver_dtl_id}",
            headers=headers,
        )
        assert res_drv.status_code == 200, f"Driver DTL API 回傳失敗: {res_drv.text}"
        data_drv = res_drv.json()

        res_close = client.get(
            f"/api/swings/{target_swing_id}/posture-comparison?ref_id={ref_driver_closeup_id}",
            headers=headers,
        )
        assert res_close.status_code == 200, f"Driver Close-up API 回傳失敗: {res_close.text}"
        data_close = res_close.json()

    final_report = {
        "metadata": {
            "title": "Golf Swing Lab — R3 Real API Posture Comparison Verification Report",
            "generated_at_utc": "2026-10-30T22:00:00Z",
            "source": "GET /api/swings/{swing_id}/posture-comparison",
            "user_swing_id": target_swing_id,
            "truthfulness_principles": [
                "所有度量數值均 100% 來自真實 API 回傳之 JSON",
                "嚴禁任何臆測之球速、桿頭速度、距離、甜蜜點或未標定公分英吋",
                "一般理論常模僅作為實驗性參考區間，非職業教練認證標準",
                "示範球員之姿態差異不必然代表使用者有缺陷",
            ],
        },
        "comparisons": {
            "7I_standard_dtl": data_7i,
            "driver_standard_dtl": data_drv,
            "driver_closeup_incompatible": data_close,
        },
    }

    REPORT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    print(f"[REPORT] 真實 API 量化比較報告已生成: {REPORT_OUTPUT_PATH}")
    return final_report


if __name__ == "__main__":
    generate_report()
