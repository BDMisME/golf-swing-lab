#!/usr/bin/env python3
"""
scripts/evaluate_takeover.py

比對 8b56c22 基線與本次接管修復後（fixed）在獨立人工真值上的客觀精度指標。
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def load_json(p: Path) -> dict:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def evaluate_run(run_data: dict, gt_data: dict) -> dict:
    gt_swings = {s["sequence_no"]: s for s in gt_data["swings"]}
    pred_swings = {s["sequence_no"]: s for s in run_data["swings"]}

    total_gt = len(gt_swings)
    correct_label = 0
    top_diffs = []
    impact_diffs = []
    valid_ds_count = 0
    auto_accepted_count = 0
    timing_anomalies = 0

    per_swing_results = []

    for seq, gt in sorted(gt_swings.items()):
        pred = pred_swings.get(seq)
        if not pred:
            continue

        label_match = (pred["label"] == gt["label"])
        if label_match:
            correct_label += 1

        top_ev = pred["events"].get("top", {})
        imp_ev = pred["events"].get("impact_estimated", {})

        pred_top = top_ev.get("time_ms")
        pred_imp = imp_ev.get("time_ms")

        top_diff = abs(pred_top - gt["top_ms"]) if pred_top is not None else None
        imp_diff = abs(pred_imp - gt["impact_ms"]) if pred_imp is not None else None

        if top_diff is not None:
            top_diffs.append(top_diff)
        if imp_diff is not None:
            impact_diffs.append(imp_diff)

        pred_ds = (pred_imp - pred_top) if (pred_top and pred_imp) else None
        is_ds_valid = (pred_ds is not None and 180 <= pred_ds <= 650)
        if is_ds_valid:
            valid_ds_count += 1

        if pred["review_status"] == "auto_accepted":
            auto_accepted_count += 1

        if "timing_anomaly" in pred["review_flags"]:
            timing_anomalies += 1

        per_swing_results.append({
            "seq": seq,
            "label_pred": pred["label"],
            "label_gt": gt["label"],
            "top_gt": gt["top_ms"],
            "top_pred": pred_top,
            "top_diff_ms": top_diff,
            "top_diff_frames": round(top_diff / 16.67, 1) if top_diff is not None else None,
            "imp_gt": gt["impact_ms"],
            "imp_pred": pred_imp,
            "imp_diff_ms": imp_diff,
            "imp_diff_frames": round(imp_diff / 16.67, 1) if imp_diff is not None else None,
            "ds_gt": gt["downswing_ms"],
            "ds_pred": pred_ds,
            "status": pred["review_status"],
            "flags": pred["review_flags"],
            "overall_score": pred.get("overall_score"),
        })

    return {
        "total_swings": total_gt,
        "classification_accuracy": round((correct_label / total_gt) * 100, 1),
        "top_mae_ms": round(sum(top_diffs) / len(top_diffs), 1) if top_diffs else None,
        "impact_mae_ms": round(sum(impact_diffs) / len(impact_diffs), 1) if impact_diffs else None,
        "top_mae_frames": round((sum(top_diffs) / len(top_diffs)) / 16.67, 1) if top_diffs else None,
        "impact_mae_frames": round((sum(impact_diffs) / len(impact_diffs)) / 16.67, 1) if impact_diffs else None,
        "downswing_compliance_rate": round((valid_ds_count / total_gt) * 100, 1),
        "auto_acceptance_rate": round((auto_accepted_count / total_gt) * 100, 1),
        "timing_anomaly_count": timing_anomalies,
        "per_swing": per_swing_results,
    }

def main():
    gt_path = REPO_ROOT / "docs/reports/takeover/independent_human_gt_2min.json"
    base_path = REPO_ROOT / "docs/reports/takeover/baseline_8b56c22_original.json"
    fixed_path = REPO_ROOT / "docs/reports/takeover/fixed_original.json"

    gt = load_json(gt_path)
    base = load_json(base_path)
    fixed = load_json(fixed_path)

    res_base = evaluate_run(base, gt)
    res_fixed = evaluate_run(fixed, gt)

    print("================================================================================")
    print(" GOLF SWING LAB — PRINCIPAL TAKEOVER OBJECTIVE ACCURACY REPORT")
    print("================================================================================")
    print(f"基準版本 (Commit 8b56c22):")
    print(f"  - 揮桿分類正確率: {res_base['classification_accuracy']}% ({res_base['classification_accuracy']/100*12:.0f}/12)")
    print(f"  - Top 平均絕對誤差 (MAE): {res_base['top_mae_ms']} ms ({res_base['top_mae_frames']} frames)")
    print(f"  - Impact 平均絕對誤差 (MAE): {res_base['impact_mae_ms']} ms ({res_base['impact_mae_frames']} frames)")
    print(f"  - 生理下桿符合率: {res_base['downswing_compliance_rate']}%")
    print(f"  - 自動通過率 (免人工審核): {res_base['auto_acceptance_rate']}%")
    print(f"  - 時序異常球數: {res_base['timing_anomaly_count']} 球")
    print("--------------------------------------------------------------------------------")
    print(f"本次接管修復版本 (Fixed):")
    print(f"  - 揮桿分類正確率: {res_fixed['classification_accuracy']}% ({res_fixed['classification_accuracy']/100*12:.0f}/12)")
    print(f"  - Top 平均絕對誤差 (MAE): {res_fixed['top_mae_ms']} ms ({res_fixed['top_mae_frames']} frames)")
    print(f"  - Impact 平均絕對誤差 (MAE): {res_fixed['impact_mae_ms']} ms ({res_fixed['impact_mae_frames']} frames)")
    print(f"  - 生理下桿符合率: {res_fixed['downswing_compliance_rate']}%")
    print(f"  - 自動通過率 (免人工審核): {res_fixed['auto_acceptance_rate']}%")
    print(f"  - 時序異常球數: {res_fixed['timing_anomaly_count']} 球")
    print("================================================================================")
    print("逐球精度比對表 (Fixed vs Ground Truth):")
    print("Seq | GT Top -> Imp (ds)  | Pred Top -> Imp (ds) | TopErr | ImpErr | Status | Flags")
    print("----+----------------------+----------------------+--------+--------+--------+-------")
    for r in res_fixed["per_swing"]:
        gt_s = f"{r['top_gt']}->{r['imp_gt']} ({r['ds_gt']}ms)"
        pred_s = f"{r['top_pred']}->{r['imp_pred']} ({r['ds_pred']}ms)"
        print(f"#{r['seq']:2d} | {gt_s:20s} | {pred_s:20s} | {r['top_diff_ms']:4d}ms | {r['imp_diff_ms']:4d}ms | {r['status']:6s} | {r['flags']}")

    # 輸出成 JSON 報告
    out_path = REPO_ROOT / "docs/reports/takeover/takeover_accuracy_evaluation.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "baseline": res_base,
            "fixed": res_fixed,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n完整評估 JSON 已儲存至: {out_path}")

if __name__ == "__main__":
    main()
