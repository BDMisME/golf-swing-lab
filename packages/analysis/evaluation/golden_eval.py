import statistics
from dataclasses import dataclass, field
from typing import Any

from packages.analysis.detection.scanner import compute_time_iou


@dataclass
class GoldenEvalSummary:
    total_gt: int
    total_pred: int
    true_positives: int
    false_positives: int
    false_negatives: int
    recall: float
    precision: float
    start_error_median_ms: float
    end_error_median_ms: float
    combined_boundary_median_ms: float
    matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_gt": self.total_gt,
            "total_pred": self.total_pred,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "recall": round(self.recall, 4),
            "precision": round(self.precision, 4),
            "start_error_median_ms": round(self.start_error_median_ms, 1),
            "end_error_median_ms": round(self.end_error_median_ms, 1),
            "combined_boundary_median_ms": round(self.combined_boundary_median_ms, 1),
            "matches": self.matches,
        }


def evaluate_against_golden(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    iou_threshold: float = 0.25,
) -> GoldenEvalSummary:
    """
    對比預測揮桿區段與人工標註真值 (Ground Truth)：
    計算 Recall、Precision 與起迄邊界時間偏差中位數 (ms)。
    """
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matches: list[dict[str, Any]] = []
    start_errors: list[float] = []
    end_errors: list[float] = []

    # 計算所有 (pred, gt) 配對之 IoU 並由高至低貪婪配對
    candidates: list[tuple[float, int, int]] = []
    for p_idx, pred in enumerate(predictions):
        ps, pe = int(pred["start_ms"]), int(pred["end_ms"])
        for g_idx, gt in enumerate(ground_truths):
            gs, ge = int(gt["start_ms"]), int(gt["end_ms"])
            iou = compute_time_iou(ps, pe, gs, ge)
            if iou >= iou_threshold:
                candidates.append((iou, p_idx, g_idx))

    candidates.sort(key=lambda x: x[0], reverse=True)
    for iou, p_idx, g_idx in candidates:
        if p_idx in matched_pred or g_idx in matched_gt:
            continue
        matched_pred.add(p_idx)
        matched_gt.add(g_idx)
        pred = predictions[p_idx]
        gt = ground_truths[g_idx]
        s_err = abs(float(pred["start_ms"]) - float(gt["start_ms"]))
        e_err = abs(float(pred["end_ms"]) - float(gt["end_ms"]))
        start_errors.append(s_err)
        end_errors.append(e_err)
        matches.append(
            {
                "gt_id": gt.get("gt_id", f"gt-{g_idx + 1}"),
                "pred_seq": pred.get("sequence_no", p_idx + 1),
                "iou": round(iou, 3),
                "start_error_ms": round(s_err, 1),
                "end_error_ms": round(e_err, 1),
            }
        )

    tp = len(matches)
    fp = max(0, len(predictions) - tp)
    fn = max(0, len(ground_truths) - tp)
    recall = tp / float(len(ground_truths)) if ground_truths else 1.0
    precision = tp / float(len(predictions)) if predictions else (1.0 if not ground_truths else 0.0)

    s_med = float(statistics.median(start_errors)) if start_errors else 0.0
    e_med = float(statistics.median(end_errors)) if end_errors else 0.0
    all_errs = start_errors + end_errors
    c_med = float(statistics.median(all_errs)) if all_errs else 0.0

    return GoldenEvalSummary(
        total_gt=len(ground_truths),
        total_pred=len(predictions),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        recall=recall,
        precision=precision,
        start_error_median_ms=s_med,
        end_error_median_ms=e_med,
        combined_boundary_median_ms=c_med,
        matches=matches,
    )
