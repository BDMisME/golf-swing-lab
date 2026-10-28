#!/usr/bin/env python3
"""
scripts/frame_evidence.py — 原始影格證據擷取工具（人工視覺驗證用）

依「真實解碼影格 PTS」擷取原片影格，拼成帶有時間碼 / 影格序號標註的 Contact Sheet。
不經過任何姿態或事件演算法，純粹提供可查核的畫面證據。

子指令：
  overview  --video V --step-ms 500 --out-dir D           全片稀疏總覽（找出每次揮桿的大致位置）
  window    --video V --start-ms A --end-ms B [--every N] --out F.jpg [--crop x0,y0,x1,y1]
            擷取 [A,B] 區間內每 N 個實際影格（N=1 為全部 60fps 影格）
  pts-check --video V                                      比對 OpenCV PTS 與 ffprobe PTS
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np


def _read_frames(video: str, start_ms: int, end_ms: int, every: int = 1, step_ms: int | None = None):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(start_ms) - 1500.0))
    out = []
    k = 0
    next_t = start_ms
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC)
        idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
        if t < start_ms:
            continue
        if t > end_ms:
            break
        if step_ms is not None:
            if t + 0.5 >= next_t:
                out.append((t, idx, fr))
                next_t = t + step_ms
        else:
            if k % every == 0:
                out.append((t, idx, fr))
            k += 1
    cap.release()
    return out


def _sheet(frames, cols: int, thumb_w: int, crop=None, title: str = "") -> np.ndarray:
    tiles = []
    for t, idx, fr in frames:
        img = fr
        if crop:
            h, w = img.shape[:2]
            x0, y0, x1, y1 = crop
            img = img[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]
        h, w = img.shape[:2]
        th = int(h * thumb_w / w)
        img = cv2.resize(img, (thumb_w, th), interpolation=cv2.INTER_AREA)
        label = f"{t:.0f}ms f{idx}"
        cv2.rectangle(img, (0, 0), (thumb_w, 22), (0, 0, 0), -1)
        cv2.putText(img, label, (3, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(img)
    if not tiles:
        return np.zeros((50, 400, 3), np.uint8)
    th = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, th - t.shape[0], 0, 2, cv2.BORDER_CONSTANT) for t in tiles]
    rows = []
    for i in range(0, len(tiles), cols):
        row = tiles[i : i + cols]
        while len(row) < cols:
            row.append(np.zeros_like(tiles[0]))
        rows.append(np.hstack(row))
    sheet = np.vstack(rows)
    if title:
        bar = np.zeros((28, sheet.shape[1], 3), np.uint8)
        cv2.putText(bar, title, (5, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        sheet = np.vstack([bar, sheet])
    return sheet


def cmd_overview(a):
    cap = cv2.VideoCapture(a.video)
    dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30) * 1000
    cap.release()
    frames = _read_frames(a.video, 0, int(dur), step_ms=a.step_ms)
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    per = a.cols * a.rows
    for i in range(0, len(frames), per):
        chunk = frames[i : i + per]
        sheet = _sheet(chunk, a.cols, a.thumb_w, title=f"{chunk[0][0]:.0f}-{chunk[-1][0]:.0f}ms")
        p = out_dir / f"overview_{int(chunk[0][0]):06d}.jpg"
        cv2.imwrite(str(p), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(p)


def cmd_window(a):
    crop = tuple(float(x) for x in a.crop.split(",")) if a.crop else None
    frames = _read_frames(a.video, a.start_ms, a.end_ms, every=a.every)
    sheet = _sheet(frames, a.cols, a.thumb_w, crop=crop, title=a.title or f"{a.start_ms}-{a.end_ms}ms every={a.every}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(a.out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(a.out, len(frames), "frames")


def cmd_pts_check(a):
    cap = cv2.VideoCapture(a.video)
    cv_ts = []
    for _ in range(a.n):
        ok, _f = cap.read()
        if not ok:
            break
        cv_ts.append(round(cap.get(cv2.CAP_PROP_POS_MSEC), 3))
    cap.release()
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
         "-read_intervals", f"%+#{a.n}", "-of", "json", a.video],
        capture_output=True, text=True,
    )
    ff = [round(float(f["pts_time"]) * 1000, 3) for f in json.loads(res.stdout)["frames"]][: a.n]
    for i, (c, f) in enumerate(zip(cv_ts, ff)):
        print(f"{i:>3} cv={c:>9} ffprobe={f:>9} diff={c - f:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("overview")
    o.add_argument("--video", required=True)
    o.add_argument("--step-ms", type=int, default=500)
    o.add_argument("--out-dir", required=True)
    o.add_argument("--cols", type=int, default=10)
    o.add_argument("--rows", type=int, default=4)
    o.add_argument("--thumb-w", type=int, default=150)
    o.set_defaults(fn=cmd_overview)
    w = sub.add_parser("window")
    w.add_argument("--video", required=True)
    w.add_argument("--start-ms", type=int, required=True)
    w.add_argument("--end-ms", type=int, required=True)
    w.add_argument("--every", type=int, default=1)
    w.add_argument("--cols", type=int, default=8)
    w.add_argument("--thumb-w", type=int, default=220)
    w.add_argument("--crop", default=None)
    w.add_argument("--title", default=None)
    w.add_argument("--out", required=True)
    w.set_defaults(fn=cmd_window)
    p = sub.add_parser("pts-check")
    p.add_argument("--video", required=True)
    p.add_argument("--n", type=int, default=12)
    p.set_defaults(fn=cmd_pts_check)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
