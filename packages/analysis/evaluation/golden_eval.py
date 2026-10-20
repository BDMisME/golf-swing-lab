from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from packages.analysis.detection.scanner import compute_time_iou


@dataclass
class GoldenEvalSummary:
    """既有邊界評估摘要（向後相容）"""

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


@dataclass
class DetectionAccuracyReport:
    """R13-D 偵測準確率報告（專注揮桿有無抓到、切球完整性、漏切與重複切球）"""

    total_gt: int
    total_pred: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    mean_iou: float
    min_iou: float
    missed_swings: list[dict[str, Any]] = field(default_factory=list)
    duplicate_swings: list[dict[str, Any]] = field(default_factory=list)
    matches: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_gt": self.total_gt,
            "total_pred": self.total_pred,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "mean_iou": round(self.mean_iou, 4),
            "min_iou": round(self.min_iou, 4),
            "missed_swings": self.missed_swings,
            "duplicate_swings": self.duplicate_swings,
            "matches": self.matches,
        }


@dataclass
class EventMetricSummary:
    """單一事件（如 Top, Impact）誤差統計"""

    event_name: str
    sample_count: int
    mean_absolute_error_ms: float
    median_error_ms: float
    max_error_ms: float
    frame_error_median: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "sample_count": self.sample_count,
            "mean_absolute_error_ms": round(self.mean_absolute_error_ms, 1),
            "median_error_ms": round(self.median_error_ms, 1),
            "max_error_ms": round(self.max_error_ms, 1),
            "frame_error_median": round(self.frame_error_median, 1),
        }


@dataclass
class SwingEventAccuracyReport:
    """R13-D 關鍵影格事件準確率報告（Address, Takeaway, Top, Impact, Finish 與節奏）"""

    metrics: dict[str, EventMetricSummary] = field(default_factory=dict)
    tempo_ratio_mae: float | None = None
    per_swing_diffs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "tempo_ratio_mae": round(self.tempo_ratio_mae, 3) if self.tempo_ratio_mae is not None else None,
            "per_swing_diffs": self.per_swing_diffs,
        }


@dataclass
class DualEvaluationReport:
    """R13-D 雙向綜合驗收報告（Detection + Swing Events 完全獨立分開）"""

    detection: DetectionAccuracyReport
    events: SwingEventAccuracyReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "detection": self.detection.to_dict(),
            "events": self.events.to_dict(),
        }


def _extract_event_time(obj: dict[str, Any], event_name: str) -> float | None:
    """從字典中彈性提取特定事件的時間碼 (ms)"""
    # 1. 檢查 events 字典 (GoldenSetSwingSchema 格式)
    if "events" in obj and isinstance(obj["events"], dict):
        ev = obj["events"].get(event_name)
        if isinstance(ev, dict) and "time_ms" in ev and ev["time_ms"] is not None:
            return float(ev["time_ms"])
        if isinstance(ev, (int, float)):
            return float(ev)

    # 2. 檢查常用別名欄位
    aliases = [
        f"{event_name}_ms",
        f"{event_name}_time_ms",
    ]
    if event_name == "impact":
        aliases.extend(["impact_estimated_ms", "confirmed_strike_ms"])
    elif event_name == "address":
        aliases.extend(["address_candidate_ms", "setup_ms"])

    for alias in aliases:
        if alias in obj and obj[alias] is not None:
            return float(obj[alias])

    return None


def _extract_event_frame(obj: dict[str, Any], event_name: str) -> int | None:
    """從字典中彈性提取特定事件的影格號"""
    if "events" in obj and isinstance(obj["events"], dict):
        ev = obj["events"].get(event_name)
        if isinstance(ev, dict) and "frame_idx" in ev and ev["frame_idx"] is not None:
            return int(ev["frame_idx"])

    aliases = [
        f"{event_name}_frame",
        f"{event_name}_frame_idx",
    ]
    for alias in aliases:
        if alias in obj and obj[alias] is not None:
            return int(obj[alias])
    return None


def evaluate_against_golden(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    iou_threshold: float = 0.25,
) -> GoldenEvalSummary:
    """
    對比預測揮桿區段與人工標註真值 (Ground Truth)：
    計算 Recall、Precision 與起迄邊界時間偏差中位數 (ms)。
    保留既有介面向後相容。
    """
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matches: list[dict[str, Any]] = []
    start_errors: list[float] = []
    end_errors: list[float] = []

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


def evaluate_detection_and_events(
    predictions: list[dict[str, Any]],
    ground_truths: list[dict[str, Any]],
    iou_threshold: float = 0.25,
    fps: float = 60.0,
) -> DualEvaluationReport:
    """
    R13-D 嚴格分離評估：
    1. Detection Accuracy: TP/FP/FN/Recall/Precision/F1/IoU/漏切/重複切球
    2. Swing Event Accuracy: Address/Takeaway/Top/Impact/Finish 與 Tempo 誤差
    """
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matches: list[dict[str, Any]] = []

    # 計算所有候選配對
    candidates: list[tuple[float, int, int]] = []
    # 記錄重複覆蓋：記錄每個 gt 命中哪些預測
    gt_coverage: dict[int, list[tuple[int, float]]] = {g: [] for g in range(len(ground_truths))}

    for p_idx, pred in enumerate(predictions):
        ps, pe = int(pred["start_ms"]), int(pred["end_ms"])
        for g_idx, gt in enumerate(ground_truths):
            gs, ge = int(gt["start_ms"]), int(gt["end_ms"])
            iou = compute_time_iou(ps, pe, gs, ge)
            if iou >= iou_threshold:
                candidates.append((iou, p_idx, g_idx))
                gt_coverage[g_idx].append((p_idx, iou))

    candidates.sort(key=lambda x: x[0], reverse=True)
    paired_ious: list[float] = []

    for iou, p_idx, g_idx in candidates:
        if p_idx in matched_pred or g_idx in matched_gt:
            continue
        matched_pred.add(p_idx)
        matched_gt.add(g_idx)
        paired_ious.append(iou)
        pred = predictions[p_idx]
        gt = ground_truths[g_idx]
        matches.append(
            {
                "gt_id": gt.get("gt_id", f"gt-{g_idx + 1}"),
                "pred_seq": pred.get("sequence_no", p_idx + 1),
                "p_idx": p_idx,
                "g_idx": g_idx,
                "iou": round(iou, 4),
                "gt_start_ms": int(gt["start_ms"]),
                "gt_end_ms": int(gt["end_ms"]),
                "pred_start_ms": int(pred["start_ms"]),
                "pred_end_ms": int(pred["end_ms"]),
            }
        )

    # 1. 偵測指標
    tp = len(matches)
    fp = max(0, len(predictions) - tp)
    fn = max(0, len(ground_truths) - tp)
    precision = tp / float(len(predictions)) if predictions else (1.0 if not ground_truths else 0.0)
    recall = tp / float(len(ground_truths)) if ground_truths else 1.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    mean_iou = float(statistics.mean(paired_ious)) if paired_ious else 0.0
    min_iou = float(min(paired_ious)) if paired_ious else 0.0

    # 漏切項目
    missed_swings = [
        {
            "gt_id": ground_truths[g].get("gt_id", f"gt-{g + 1}"),
            "start_ms": int(ground_truths[g]["start_ms"]),
            "end_ms": int(ground_truths[g]["end_ms"]),
        }
        for g in range(len(ground_truths))
        if g not in matched_gt
    ]

    # 重複切球項目（同一個真值被多個預測同時覆蓋）
    duplicate_swings: list[dict[str, Any]] = []
    for g, cov in gt_coverage.items():
        if len(cov) > 1:
            gt_id = ground_truths[g].get("gt_id", f"gt-{g + 1}")
            duplicate_swings.append(
                {
                    "gt_id": gt_id,
                    "matched_count": len(cov),
                    "candidate_predictions": [
                        {"pred_seq": predictions[p].get("sequence_no", p + 1), "iou": round(u, 3)}
                        for p, u in cov
                    ],
                }
            )

    det_report = DetectionAccuracyReport(
        total_gt=len(ground_truths),
        total_pred=len(predictions),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=precision,
        recall=recall,
        f1_score=f1,
        mean_iou=mean_iou,
        min_iou=min_iou,
        missed_swings=missed_swings,
        duplicate_swings=duplicate_swings,
        matches=matches,
    )

    # 2. 事件準確率指標
    event_names = ["address", "takeaway", "top", "impact", "finish"]
    event_diffs_map: dict[str, list[float]] = {ev: [] for ev in event_names}
    frame_diffs_map: dict[str, list[float]] = {ev: [] for ev in event_names}
    tempo_ratio_errors: list[float] = []
    per_swing_diffs: list[dict[str, Any]] = []

    for match in matches:
        pred = predictions[match["p_idx"]]
        gt = ground_truths[match["g_idx"]]
        swing_diff_record: dict[str, Any] = {
            "gt_id": match["gt_id"],
            "pred_seq": match["pred_seq"],
            "events": {},
        }

        # 比對每個事件
        pred_times: dict[str, float] = {}
        gt_times: dict[str, float] = {}

        for ev in event_names:
            gt_t = _extract_event_time(gt, ev)
            pred_t = _extract_event_time(pred, ev)
            gt_f = _extract_event_frame(gt, ev)
            pred_f = _extract_event_frame(pred, ev)

            if gt_t is not None and pred_t is not None:
                diff_ms = pred_t - gt_t
                abs_diff_ms = abs(diff_ms)
                event_diffs_map[ev].append(abs_diff_ms)
                pred_times[ev] = pred_t
                gt_times[ev] = gt_t

                # 影格差異計算
                if gt_f is not None and pred_f is not None:
                    diff_f = abs(pred_f - gt_f)
                else:
                    diff_f = abs_diff_ms / (1000.0 / fps) if fps > 0 else 0.0
                frame_diffs_map[ev].append(diff_f)

                swing_diff_record["events"][ev] = {
                    "gt_time_ms": gt_t,
                    "pred_time_ms": pred_t,
                    "diff_ms": round(diff_ms, 1),
                    "abs_diff_ms": round(abs_diff_ms, 1),
                    "frame_diff": round(diff_f, 1),
                }
            elif gt_t is not None:
                swing_diff_record["events"][ev] = {
                    "gt_time_ms": gt_t,
                    "pred_time_ms": None,
                    "error": "missing_in_prediction",
                }

        # 節奏 (Tempo Ratio: Backswing / Downswing)
        # Backswing = top - address (若無 address 則 takeaway)
        # Downswing = impact - top
        def calc_tempo(times: dict[str, float]) -> float | None:
            if "top" in times and "impact" in times:
                bs_start = times.get("address") or times.get("takeaway")
                if bs_start is not None and times["top"] > bs_start and times["impact"] > times["top"]:
                    bs_dur = times["top"] - bs_start
                    ds_dur = times["impact"] - times["top"]
                    if ds_dur > 10:
                        return bs_dur / ds_dur
            return None

        gt_tempo = calc_tempo(gt_times)
        pred_tempo = calc_tempo(pred_times)
        if gt_tempo is not None and pred_tempo is not None:
            tempo_err = abs(pred_tempo - gt_tempo)
            tempo_ratio_errors.append(tempo_err)
            swing_diff_record["tempo_ratio"] = {
                "gt": round(gt_tempo, 2),
                "pred": round(pred_tempo, 2),
                "abs_error": round(tempo_err, 2),
            }

        per_swing_diffs.append(swing_diff_record)

    # 聚合事件統計
    metrics_summary: dict[str, EventMetricSummary] = {}
    for ev in event_names:
        diffs = event_diffs_map[ev]
        fdiffs = frame_diffs_map[ev]
        if diffs:
            metrics_summary[ev] = EventMetricSummary(
                event_name=ev,
                sample_count=len(diffs),
                mean_absolute_error_ms=float(statistics.mean(diffs)),
                median_error_ms=float(statistics.median(diffs)),
                max_error_ms=float(max(diffs)),
                frame_error_median=float(statistics.median(fdiffs)) if fdiffs else 0.0,
            )

    tempo_mae = float(statistics.mean(tempo_ratio_errors)) if tempo_ratio_errors else None

    evt_report = SwingEventAccuracyReport(
        metrics=metrics_summary,
        tempo_ratio_mae=tempo_mae,
        per_swing_diffs=per_swing_diffs,
    )

    return DualEvaluationReport(detection=det_report, events=evt_report)
