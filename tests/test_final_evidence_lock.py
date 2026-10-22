"""
tests/test_final_evidence_lock.py

P0-A & P0-B: 驗證正式唯一推論 JSON 與 Markdown 報告之 100% 數據一致性與 12 球 Invariant。
嚴格檢驗：
1. 單一執行來源：報告必須由 final_evidence_lock.json 自動生成，數據零矛盾
2. Event Time vs Metric Time Invariant：所有 12 球之 downswing_ms 嚴格等於 (impact - top)，絕無不同 Tempo
3. 異常球時序保護：時序超標球之指標必須為 None，標記 needs_review，禁止虛構評分
4. Golden Set 零污染：real_2min_session_gt.json SHA-256 恆定
5. 五大獨立驗收判定 (Five-Dimension Final Verdicts) 完整性
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_REPORT_PATH = REPO_ROOT / "docs" / "reports" / "final_evidence_lock.json"
MD_REPORT_PATH = REPO_ROOT / "docs" / "FINAL_EVIDENCE_LOCK_REPORT.md"
GT_PATH = REPO_ROOT / "tests" / "golden" / "real_2min_session_gt.json"
EXPECTED_GT_SHA256 = "efefa02b2bd3d6c4cb461e9882cf63995694df37846ee57d0badef78b0d07954"


def _compute_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_golden_set_integrity_unpolluted():
    """驗證正式 Golden Set 檔案未被測試或推論污染。"""
    assert GT_PATH.exists(), "正式 Golden Set 檔案必須存在"
    actual_sha = _compute_sha256(GT_PATH)
    assert actual_sha == EXPECTED_GT_SHA256, (
        f"Golden Set 遭到修改！預期 {EXPECTED_GT_SHA256}，實際 {actual_sha}"
    )


def test_evidence_lock_files_exist_and_valid():
    """驗證唯一推論 JSON 與 Markdown 報告皆已生成且結構合法。"""
    if not JSON_REPORT_PATH.exists():
        pytest.skip("docs/reports/final_evidence_lock.json 尚未生成，請先執行 scripts/run_final_evidence_evaluation.py")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "summary" in data
    assert "verdicts" in data
    assert "swings" in data
    assert len(data["swings"]) == 12, "2分鐘原片必須精準檢測出 12 記揮桿"

    assert MD_REPORT_PATH.exists(), "Markdown 報告必須存在"


def test_12_swings_event_metric_invariants():
    """
    P0-B: 驗證全部 12 球之 Event Time 與 Metric Time Invariant：
    1. 正常球：downswing_ms == (impact_ms - top_ms)
    2. 正常球：backswing_ms == (top_ms - start_ms)
    3. 正常球：backswing_downswing_ratio == round(backswing_ms / downswing_ms, 2)
    4. 異常球：downswing_ms, backswing_ms, tempo_ratio 全數為 None，review_status == 'needs_review'
    """
    if not JSON_REPORT_PATH.exists():
        pytest.skip("docs/reports/final_evidence_lock.json 尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    swings = data["swings"]
    for s in swings:
        seq = s["sequence_no"]
        ev = s["events"]
        m = s["metrics"]
        cls = s["classification"]

        top_ms = ev["top"]["time_ms"]
        imp_ms = ev["impact"]["time_ms"]
        start_ms = ev["takeaway"]["time_ms"] or ev["address"]["time_ms"]

        assert top_ms is not None and imp_ms is not None and start_ms is not None

        if cls["review_status"] == "auto_accepted":
            # 正常球：數值必須嚴格等於事件時間差
            expected_ds = float(imp_ms - top_ms)
            expected_bs = float(top_ms - start_ms)
            expected_tempo = round(expected_bs / expected_ds, 2)

            actual_ds = m["downswing_ms"]
            actual_bs = m["backswing_ms"]
            actual_tempo = m["backswing_downswing_ratio"]

            assert actual_ds == expected_ds, (
                f"球次 #{seq} [P0-B 違規] Metric 下桿時間 ({actual_ds}ms) "
                f"與 Event 時間差 ({expected_ds}ms) 不一致！"
            )
            assert actual_bs == expected_bs, (
                f"球次 #{seq} [P0-B 違規] Metric 上桿時間 ({actual_bs}ms) "
                f"與 Event 時間差 ({expected_bs}ms) 不一致！"
            )
            assert actual_tempo == expected_tempo, (
                f"球次 #{seq} [P0-B 違規] Metric Tempo ({actual_tempo}) "
                f"與計算值 ({expected_tempo}) 不一致！"
            )
            assert 180 <= actual_ds <= 650, f"球次 #{seq} 正常球下桿時間超出生理區間: {actual_ds}ms"

        else:
            # 異常球：必須誠實設為 None，不虛構分數
            assert m["downswing_ms"] is None, f"球次 #{seq} 異常球 downswing_ms 必須為 None"
            assert m["backswing_ms"] is None, f"球次 #{seq} 異常球 backswing_ms 必須為 None"
            assert m["backswing_downswing_ratio"] is None, f"球次 #{seq} 異常球 tempo 必須為 None"


def test_markdown_and_json_report_consistency():
    """
    P0-A: 驗證 Markdown 報告中的數據與 JSON 保持 100% 絕對一致。
    杜絕手動拼貼或多份執行結果混合的缺陷。
    """
    if not JSON_REPORT_PATH.exists() or not MD_REPORT_PATH.exists():
        pytest.skip("報告檔案尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    with open(MD_REPORT_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 1. 驗證 Git Commit SHA (支援 -DIRTY 標記)
    git_sha_display = json_data["metadata"].get("git_commit_sha_display", json_data["metadata"]["git_commit_sha"])
    assert f"`{git_sha_display}`" in md_text, "Markdown 報告中的 Git Commit SHA 與 JSON 不符！"

    # 2. 驗證推論耗時
    elapsed = json_data["metadata"]["execution_telemetry"]["elapsed_seconds"]
    assert f"`{elapsed}s`" in md_text, "Markdown 報告中的耗時與 JSON 不符！"

    # 3. 驗證各球關鍵時間碼出現在表格中
    for s in json_data["swings"]:
        seq = s["sequence_no"]
        top_ms = s["events"]["top"]["time_ms"]
        imp_ms = s["events"]["impact"]["time_ms"]
        # 在 markdown 表格中搜尋該球的行
        pattern = rf"\|\s*\*\*#{seq}\*\*\s*\|.*{top_ms:,}.*{imp_ms:,}.*\|"
        match = re.search(pattern, md_text)
        assert match is not None, f"球次 #{seq} 的時間碼 ({top_ms}, {imp_ms}) 未在 Markdown 表格中精確匹配！"


def test_golden_set_actual_status_dynamic_integrity():
    """
    P0-A: 驗證 Golden Set 驗證狀態為實際動態統計，絕非偽造硬編碼。
    當前 60 個事件均為 machine_suggested，human_verified 必須為 0。
    """
    if not JSON_REPORT_PATH.exists():
        pytest.skip("報告檔案尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    gs = json_data["metadata"]["golden_set"]
    assert gs["human_verified_events_count"] == 0, "當前 Golden Set 尚無人工驗證事件"
    assert gs["machine_suggested_events_count"] == 60, "當前 Golden Set 全部 60 個事件應為 machine_suggested"
    assert gs["human_verified_ratio"] == 0.0, "人工驗證率必須如實反映為 0.0"

    # 驗證五大 Verdicts 中 EVENT_ACCURACY_VALIDATED 為 NOT_VALIDATED
    verdicts = json_data["verdicts"]
    assert verdicts["EVENT_ACCURACY_VALIDATED"] == "NOT_VALIDATED", (
        "因無人工確認之正式真值，EVENT_ACCURACY_VALIDATED 必須動態判定為 NOT_VALIDATED"
    )
    assert verdicts["DETECTION_VALIDATED"] == "PASS (PROVISIONAL)"


def test_dynamic_verdicts_accuracy_and_provisional():
    """
    P0-4: 驗證五大 Verdicts 之動態裁決規則：
    1. ENGINEERING_PASS: 由自動化測試與建置 exit code 動態判定為 PASS
    2. DATA_INTEGRITY_PASS: PASS
    3. DETECTION_VALIDATED: PASS (PROVISIONAL)
    4. EVENT_ACCURACY_VALIDATED: 因無人工確認之正式真值，動態判定為 NOT_VALIDATED
    5. REAL_WORLD_AUTOMATION_READY: 在具備外部獨立人工標註前，客觀標記為 PROVISIONAL
    """
    if not JSON_REPORT_PATH.exists():
        pytest.skip("報告檔案尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    verdicts = json_data["verdicts"]
    assert verdicts["ENGINEERING_PASS"] == "PASS"
    assert verdicts["DATA_INTEGRITY_PASS"] == "PASS"
    assert verdicts["DETECTION_VALIDATED"] == "PASS (PROVISIONAL)"
    assert verdicts["EVENT_ACCURACY_VALIDATED"] == "NOT_VALIDATED", (
        "因無人工確認之正式真值，EVENT_ACCURACY_VALIDATED 必須動態判定為 NOT_VALIDATED"
    )
    assert verdicts["REAL_WORLD_AUTOMATION_READY"] == "PROVISIONAL", (
        "長片雖跑通 12 球偵測，但尚缺高精獨立人工金標驗證，依 P0-4 規範必須標記為 PROVISIONAL"
    )


def test_unlabeled_candidate_negatives_marked_not_validated():
    """
    P0-4: 驗證真實長片中 11 個未擊球區段標記為 unlabeled_candidate_negatives，
    因缺乏第三方獨立人工標註，其正式狀態必須動態回傳 NOT_VALIDATED，禁止謊稱 PASS。
    """
    if not JSON_REPORT_PATH.exists():
        pytest.skip("報告檔案尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    summary = json_data["summary"]
    assert summary["unlabeled_candidate_negatives_tested"] >= 11, "必須完整檢驗非揮桿間隔區段"
    assert summary["unlabeled_candidate_negatives_status"] == "NOT_VALIDATED"
    assert summary["unlabeled_candidate_negatives_false_positives"] == 0
    assert summary["unlabeled_candidate_negatives_total_duration_sec"] > 70.0

    negs = json_data.get("negative_samples_real_world", [])
    assert len(negs) >= 11
    for n in negs:
        assert n["category"] == "unlabeled_candidate_negatives"
        assert n["status"] == "NOT_VALIDATED"
        assert n["false_positives"] == 0


def test_multi_hypothesis_and_best_swings_ranking_protection():
    """
    P0-3 & P0-5: 驗證多候選雙峰假設推導資料結構，以及爭議球在 Top 5 排行榜中之安全排除。
    """
    if not JSON_REPORT_PATH.exists():
        pytest.skip("報告檔案尚未生成")

    with open(JSON_REPORT_PATH, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    swings = json_data["swings"]
    disputed_ids = set()

    for s in swings:
        seq = s["sequence_no"]
        m_hyp = s.get("multi_hypothesis_analysis", {})
        assert "hypotheses_count" in m_hyp
        assert "selection_rationale" in m_hyp
        hyps = m_hyp.get("hypotheses", [])
        assert len(hyps) >= 1, f"球次 #{seq} 必須具備至少 1 組候選假設"
        for h in hyps:
            assert "top_ms" in h
            assert "impact_ms" in h
            assert "total_score" in h
            assert "supporting_evidence" in h
            assert "opposing_evidence" in h

        # 檢驗爭議標記
        if m_hyp.get("is_ambiguous") or s["classification"]["review_status"] == "needs_review":
            disputed_ids.add(f"swing_{seq}")

    # 驗證 P0-5: 爭議球絕不出現在 posture 與 tempo 排行榜
    rv = json_data.get("ranking_validation", {})
    assert rv.get("disputed_swings_excluded_from_posture_and_tempo") is True
    posture_top5 = set(rv.get("posture_top5", []))
    tempo_top5 = set(rv.get("tempo_top5", []))

    for disp in disputed_ids:
        assert disp not in posture_top5, f"爭議球 {disp} 違規進入了 posture 排行榜！"
        assert disp not in tempo_top5, f"爭議球 {disp} 違規進入了 tempo 排行榜！"

