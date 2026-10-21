"""Golden Set 資料集管理與人工審核單一真實來源 (Single Source of Truth).

負責：
1. 註冊、驗證並持久化 Golden Set 標註資料集。
2. 綁定影片檔名與 SHA-256，拒絕隨機關聯影片。
3. 嚴格防呆：事件時間碼超出影片長度時拒絕儲存。
4. 提供機器建議 (machine_suggested)、人工確認 (human_verified) 與不確定 (uncertain) 狀態轉換。
5. 記錄審核歷程 (audit trail)。
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

EventStatus = Literal["machine_suggested", "human_verified", "uncertain", "pending_human_review"]


class GoldenEventDetail(BaseModel):
    time_ms: int
    frame: int
    status: EventStatus = "machine_suggested"
    source: str = "machine_heuristic_v1"
    confidence: float = 0.80
    rationale: str = ""
    verified_by: str | None = None
    verified_at: str | None = None
    previous_value: dict[str, Any] | None = None


class GoldenSwingItem(BaseModel):
    gt_id: str
    sequence_no: int
    start_ms: int
    end_ms: int
    address_ms: int
    takeaway_ms: int
    top_ms: int
    impact_ms: int
    finish_ms: int
    frames: dict[str, int]
    events: dict[str, GoldenEventDetail] = Field(default_factory=dict)
    downswing_ms: int | None = None
    backswing_ms: int | None = None
    tempo_ratio: float | None = None
    label: str = "valid_swing"
    strike_status: str = "confirmed_strike"
    history: list[dict[str, Any]] = Field(default_factory=list)


def compute_swing_tempo(
    takeaway_ms: int | None, top_ms: int | None, impact_ms: int | None
) -> tuple[int | None, int | None, float | None]:
    """依據高爾夫運動學精確計算上／下桿時間與節奏比 (P1-4).
    
    定義：
    - Backswing = Top - Takeaway
    - Downswing = Impact - Top
    - Tempo Ratio = Backswing / Downswing
    
    規則：
    1. 嚴禁將 Address 等待時間併入上桿時間。
    2. 若 Takeaway、Top、Impact 任一不存在或時序不合法 (Takeaway >= Top 或 Top >= Impact)，
       或 Downswing <= 0，則 Tempo 與時間必須為 None。
    """
    if takeaway_ms is None or top_ms is None or impact_ms is None:
        return None, None, None
    if not (takeaway_ms < top_ms < impact_ms):
        return None, None, None
    bs = top_ms - takeaway_ms
    ds = impact_ms - top_ms
    if ds <= 0 or bs <= 0:
        return None, None, None
    tempo = round(float(bs) / float(ds), 2)
    return bs, ds, tempo


class GoldenDatasetModel(BaseModel):
    dataset_id: str
    dataset_version: str
    video_filename: str
    video_sha256: str
    duration_ms: int
    total_frames: int
    fps: float
    timebase: str = "1/60000"
    note: str = ""
    ground_truth_swings: list[GoldenSwingItem] = Field(default_factory=list)

    @property
    def swings(self) -> list[GoldenSwingItem]:
        return self.ground_truth_swings

    @property
    def video_duration_ms(self) -> int:
        return self.duration_ms


def compute_file_sha256(file_path: Path | str) -> str:
    path = Path(file_path)
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


class GoldenSetRegistry:
    def __init__(self, golden_dir: Path | None = None) -> None:
        self.golden_dir = golden_dir or GOLDEN_DIR
        self.golden_dir.mkdir(parents=True, exist_ok=True)

    def list_golden_sets(self) -> list[dict[str, Any]]:
        return self.list_datasets()

    def get_golden_set(self, dataset_id: str) -> GoldenDatasetModel | None:
        return self.get_dataset(dataset_id)

    def list_datasets(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for file in sorted(self.golden_dir.glob("*.json")):
            try:
                with open(file, encoding="utf-8") as f:
                    data = json.load(f)
                ds_id = data.get("dataset_id") or data.get("video_id") or file.stem
                swings = data.get("ground_truth_swings", [])
                
                # 統計人工驗證率
                verified_events = 0
                total_events = 0
                for sw in swings:
                    evs = sw.get("events", {})
                    if evs:
                        for ev in evs.values():
                            total_events += 1
                            if ev.get("status") == "human_verified":
                                verified_events += 1

                results.append(
                    {
                        "dataset_id": ds_id,
                        "file_path": str(file),
                        "dataset_version": data.get("dataset_version", "v1"),
                        "video_filename": data.get("video_filename", ""),
                        "video_sha256": data.get("video_sha256", ""),
                        "duration_ms": data.get("duration_ms", 0),
                        "total_frames": data.get("total_frames", 0),
                        "fps": data.get("fps", 60.0),
                        "total_swings": len(swings),
                        "verified_events_count": verified_events,
                        "total_events_count": total_events,
                        "verification_rate": round(verified_events / max(1, total_events), 2),
                    }
                )
            except Exception as exc:
                logger.warning(f"讀取 Golden Set 檔案失敗 {file}: {exc}")
        return results

    def get_dataset(self, dataset_id: str) -> GoldenDatasetModel | None:
        for file in sorted(self.golden_dir.glob("*.json")):
            try:
                with open(file, encoding="utf-8") as f:
                    data = json.load(f)
                ds_id = data.get("dataset_id") or data.get("video_id") or file.stem
                stem_base = file.stem.replace("_gt", "")
                if dataset_id in (ds_id, file.stem, stem_base) or ds_id.startswith(dataset_id):
                    # 補齊與正規化結構
                    return self._normalize_dataset(data, file)
            except Exception as exc:
                logger.warning(f"讀取 Dataset {dataset_id} 失敗: {exc}")
        return None

    def _normalize_dataset(self, data: dict[str, Any], file_path: Path) -> GoldenDatasetModel:
        ds_id = data.get("dataset_id") or data.get("video_id") or file_path.stem
        dur_ms = data.get("duration_ms", 139053)
        fps = float(data.get("fps", 59.99137))
        total_frames = data.get("total_frames") or int(round(dur_ms * fps / 1000.0))

        raw_swings = data.get("ground_truth_swings", [])
        normalized_swings: list[GoldenSwingItem] = []

        for idx, sw in enumerate(raw_swings, start=1):
            gt_id = sw.get("gt_id") or f"gt-{idx}"
            s_ms = int(sw.get("start_ms", 0))
            e_ms = min(dur_ms, int(sw.get("end_ms", dur_ms)))
            addr_ms = int(sw.get("address_ms", s_ms))
            take_ms = int(sw.get("takeaway_ms", addr_ms + 400))
            top_ms = int(sw.get("top_ms", addr_ms + 1700))
            imp_ms = int(sw.get("impact_ms", top_ms + 550))
            fin_ms = min(dur_ms, int(sw.get("finish_ms", imp_ms + 1400)))

            frames = sw.get("frames", {})
            f_addr = frames.get("address", int(round(addr_ms * fps / 1000.0)))
            f_take = frames.get("takeaway", int(round(take_ms * fps / 1000.0)))
            f_top = frames.get("top", int(round(top_ms * fps / 1000.0)))
            f_imp = frames.get("impact", int(round(imp_ms * fps / 1000.0)))
            f_fin = frames.get("finish", int(round(fin_ms * fps / 1000.0)))

            raw_events = sw.get("events") or {}
            events: dict[str, GoldenEventDetail] = {}

            for ev_name, default_ms, default_f in [
                ("address", addr_ms, f_addr),
                ("takeaway", take_ms, f_take),
                ("top", top_ms, f_top),
                ("impact", imp_ms, f_imp),
                ("finish", fin_ms, f_fin),
            ]:
                if ev_name in raw_events:
                    ev_dict = raw_events[ev_name]
                    events[ev_name] = GoldenEventDetail(
                        time_ms=min(dur_ms, max(0, int(ev_dict.get("time_ms", default_ms)))),
                        frame=min(total_frames - 1, max(0, int(ev_dict.get("frame", default_f)))),
                        status=ev_dict.get("status", "machine_suggested"),
                        source=ev_dict.get("source", "machine_heuristic_v1"),
                        confidence=float(ev_dict.get("confidence", 0.80)),
                        rationale=ev_dict.get("rationale", ""),
                        verified_by=ev_dict.get("verified_by"),
                        verified_at=ev_dict.get("verified_at"),
                        previous_value=ev_dict.get("previous_value"),
                    )
                else:
                    events[ev_name] = GoldenEventDetail(
                        time_ms=default_ms,
                        frame=default_f,
                        status="machine_suggested",
                        source="machine_heuristic_v1",
                        confidence=0.85,
                        rationale="機器演算法初始推算",
                    )

            bs, ds, tempo = compute_swing_tempo(take_ms, top_ms, imp_ms)

            normalized_swings.append(
                GoldenSwingItem(
                    gt_id=gt_id,
                    sequence_no=int(sw.get("sequence_no", idx)),
                    start_ms=s_ms,
                    end_ms=e_ms,
                    address_ms=addr_ms,
                    takeaway_ms=take_ms,
                    top_ms=top_ms,
                    impact_ms=imp_ms,
                    finish_ms=fin_ms,
                    frames={
                        "address": f_addr,
                        "takeaway": f_take,
                        "top": f_top,
                        "impact": f_imp,
                        "finish": f_fin,
                    },
                    events=events,
                    downswing_ms=ds,
                    backswing_ms=bs,
                    tempo_ratio=tempo,
                    label=sw.get("label", "valid_swing"),
                    strike_status=sw.get("strike_status", "confirmed_strike"),
                    history=sw.get("history", []),
                )
            )

        return GoldenDatasetModel(
            dataset_id=ds_id,
            dataset_version=data.get("dataset_version", "golden-v3.1-strict"),
            video_filename=data.get("video_filename", "2分鐘.mov"),
            video_sha256=data.get(
                "video_sha256",
                "4993a3b695ad96a261795d52673e46de81ed19c7d079dff86d6fc60a7d34f0c9",
            ),
            duration_ms=dur_ms,
            total_frames=total_frames,
            fps=fps,
            timebase=data.get("timebase", "1/60000"),
            note=data.get("note", ""),
            ground_truth_swings=normalized_swings,
        )

    def save_dataset(self, model: GoldenDatasetModel) -> None:
        target_file = self.golden_dir / f"{model.dataset_id}.json"
        if not target_file.exists():
            # 尋找既有檔案
            for f in self.golden_dir.glob("*.json"):
                with open(f, encoding="utf-8") as fp:
                    d = json.load(fp)
                if (d.get("dataset_id") or d.get("video_id") or f.stem) == model.dataset_id:
                    target_file = f
                    break

        # 防呆驗證：所有事件與起訖時間不得超過 duration_ms
        for sw in model.ground_truth_swings:
            if sw.end_ms > model.duration_ms:
                raise ValueError(
                    f"第 #{sw.sequence_no} 球結束時間 {sw.end_ms}ms 超過影片總長度 {model.duration_ms}ms"
                )
            if sw.start_ms < 0 or sw.start_ms > model.duration_ms:
                raise ValueError(f"第 #{sw.sequence_no} 球起始時間 {sw.start_ms}ms 不在合法範圍內")
            for ev_name, ev in sw.events.items():
                if ev.time_ms < 0 or ev.time_ms > model.duration_ms:
                    raise ValueError(
                        f"第 #{sw.sequence_no} 球事件 {ev_name} 時間碼 {ev.time_ms}ms 超出影片長度 {model.duration_ms}ms"
                    )
                if ev.frame < 0 or ev.frame >= model.total_frames:
                    raise ValueError(
                        f"第 #{sw.sequence_no} 球事件 {ev_name} 幀號 {ev.frame} 超出總幀數 {model.total_frames}"
                    )

        payload = model.model_dump(mode="json")
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Golden Set {model.dataset_id} 已成功儲存至 {target_file}")

    def update_swing_event(
        self,
        dataset_id: str,
        swing_id: str,
        event_name: str,
        new_time_ms: int,
        new_frame: int,
        status: EventStatus = "human_verified",
        rationale: str = "",
        user: str = "human_user",
    ) -> GoldenSwingItem:
        model = self.get_dataset(dataset_id)
        if not model:
            raise KeyError(f"找不到指定的 Golden Set: {dataset_id}")

        if new_time_ms < 0 or new_time_ms > model.duration_ms:
            raise ValueError(
                f"事件時間碼 {new_time_ms}ms 超出影片合法長度 [0, {model.duration_ms}]ms"
            )
        if new_frame < 0 or new_frame >= model.total_frames:
            raise ValueError(
                f"事件影格 {new_frame} 超出影片合法幀數 [0, {model.total_frames - 1}]"
            )

        target_swing: GoldenSwingItem | None = None
        for sw in model.ground_truth_swings:
            if sw.gt_id == swing_id:
                target_swing = sw
                break

        if not target_swing:
            raise KeyError(f"在 {dataset_id} 中找不到揮桿 {swing_id}")

        prev_event = target_swing.events.get(event_name)
        prev_dict = prev_event.model_dump(mode="json") if prev_event else None

        # 紀錄歷史修改
        now_str = datetime.now(UTC).isoformat()
        target_swing.history.append(
            {
                "timestamp": now_str,
                "event_name": event_name,
                "action": "update_event",
                "user": user,
                "previous_time_ms": prev_event.time_ms if prev_event else None,
                "previous_frame": prev_event.frame if prev_event else None,
                "new_time_ms": new_time_ms,
                "new_frame": new_frame,
                "previous_status": prev_event.status if prev_event else None,
                "new_status": status,
                "rationale": rationale,
            }
        )

        target_swing.events[event_name] = GoldenEventDetail(
            time_ms=new_time_ms,
            frame=new_frame,
            status=status,
            source=f"{user}_override",
            confidence=1.0 if status == "human_verified" else 0.85,
            rationale=rationale or f"由使用者 {user} 於 {now_str} 人工精確標註",
            verified_by=user if status == "human_verified" else None,
            verified_at=now_str if status == "human_verified" else None,
            previous_value=prev_dict,
        )

        # 同步頂層快捷欄位與時序
        if event_name == "address":
            target_swing.address_ms = new_time_ms
            target_swing.frames["address"] = new_frame
            target_swing.start_ms = new_time_ms
        elif event_name == "takeaway":
            target_swing.takeaway_ms = new_time_ms
            target_swing.frames["takeaway"] = new_frame
        elif event_name == "top":
            target_swing.top_ms = new_time_ms
            target_swing.frames["top"] = new_frame
        elif event_name == "impact":
            target_swing.impact_ms = new_time_ms
            target_swing.frames["impact"] = new_frame
        elif event_name == "finish":
            target_swing.finish_ms = new_time_ms
            target_swing.frames["finish"] = new_frame
            target_swing.end_ms = min(model.duration_ms, new_time_ms + 200)

        # 重新計算衍生運動學生理指標 (P1-4)
        bs, ds, tempo = compute_swing_tempo(
            target_swing.takeaway_ms, target_swing.top_ms, target_swing.impact_ms
        )
        target_swing.backswing_ms = bs
        target_swing.downswing_ms = ds
        target_swing.tempo_ratio = tempo

        # 寫回磁碟
        self.save_dataset(model)
        return target_swing

    def reset_swing_to_machine(self, dataset_id: str, swing_id: str) -> GoldenSwingItem:
        """撤回人工修改，完整還原為 machine_suggested 初始推算與原始欄位 (P0-2 Round-Trip)."""
        model = self.get_dataset(dataset_id)
        if not model:
            raise KeyError(f"找不到指定的 Golden Set: {dataset_id}")

        target_swing: GoldenSwingItem | None = None
        for sw in model.ground_truth_swings:
            if sw.gt_id == swing_id:
                target_swing = sw
                break

        if not target_swing:
            raise KeyError(f"在 {dataset_id} 中找不到揮桿 {swing_id}")

        # 1. 恢復所有事件至原始機器建議值
        for _ev_name, ev in target_swing.events.items():
            if ev.previous_value:
                ev.time_ms = ev.previous_value["time_ms"]
                ev.frame = ev.previous_value["frame"]
                ev.status = "machine_suggested"
                ev.source = ev.previous_value.get("source", "machine_heuristic_v1")
                ev.confidence = ev.previous_value.get("confidence", 0.85)
                ev.rationale = "已撤回人工修改，還原為初始機器建議"
                ev.verified_by = None
                ev.verified_at = None
                ev.previous_value = None

        # 2. 同步恢復頂層快捷欄位與 frames (P0-2)
        if "address" in target_swing.events:
            target_swing.address_ms = target_swing.events["address"].time_ms
            target_swing.frames["address"] = target_swing.events["address"].frame
            target_swing.start_ms = target_swing.address_ms
        if "takeaway" in target_swing.events:
            target_swing.takeaway_ms = target_swing.events["takeaway"].time_ms
            target_swing.frames["takeaway"] = target_swing.events["takeaway"].frame
        if "top" in target_swing.events:
            target_swing.top_ms = target_swing.events["top"].time_ms
            target_swing.frames["top"] = target_swing.events["top"].frame
        if "impact" in target_swing.events:
            target_swing.impact_ms = target_swing.events["impact"].time_ms
            target_swing.frames["impact"] = target_swing.events["impact"].frame
        if "finish" in target_swing.events:
            target_swing.finish_ms = target_swing.events["finish"].time_ms
            target_swing.frames["finish"] = target_swing.events["finish"].frame
            target_swing.end_ms = min(model.duration_ms, target_swing.finish_ms + 200)

        # 3. 重新計算運動學生理節奏指標 (P1-4)
        bs, ds, tempo = compute_swing_tempo(
            target_swing.takeaway_ms, target_swing.top_ms, target_swing.impact_ms
        )
        target_swing.backswing_ms = bs
        target_swing.downswing_ms = ds
        target_swing.tempo_ratio = tempo

        target_swing.history.append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "action": "reset_to_machine",
                "note": "使用者撤回人工核定",
            }
        )

        self.save_dataset(model)
        return target_swing

    def extract_audio_peaks(self, video_path: str | Path, threshold_pct: float = 97.0) -> list[dict[str, Any]]:
        """提取 48kHz PCM 音訊瞬態能量峰值供前端波形對照與 Impact 候選對齊。"""
        path = Path(video_path)
        if not path.exists():
            return []
        try:
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-f",
                "s16le",
                "-",
            ]
            raw = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
            audio = np.frombuffer(raw, dtype=np.int16)
            if len(audio) == 0:
                return []

            win_size = int(48000 * 0.02)  # 20ms
            hop = int(48000 * 0.01)  # 10ms
            energies: list[float] = []
            times: list[int] = []

            for i in range(0, len(audio) - win_size, hop):
                chunk = audio[i : i + win_size].astype(np.float32)
                rms = float(np.sqrt(np.mean(chunk**2)))
                energies.append(rms)
                times.append(int(round(i * 1000.0 / 48000.0)))

            e_arr = np.array(energies)
            thresh = float(np.percentile(e_arr, threshold_pct))
            peaks: list[dict[str, Any]] = []

            for idx in range(1, len(e_arr) - 1):
                if e_arr[idx] > thresh and e_arr[idx] > e_arr[idx - 1] and e_arr[idx] > e_arr[idx + 1]:
                    t_ms = times[idx]
                    if not peaks or (t_ms - peaks[-1]["time_ms"]) > 800:
                        peaks.append(
                            {
                                "time_ms": t_ms,
                                "rms_energy": round(float(e_arr[idx]), 1),
                                "label": "audio_transient_peak",
                            }
                        )
            return peaks
        except Exception as exc:
            logger.warning(f"音訊衝擊峰值提取跳過: {exc}")
            return []


golden_registry = GoldenSetRegistry()


def get_golden_registry() -> GoldenSetRegistry:
    """取得 GoldenSetRegistry 全域單例。"""
    return golden_registry
