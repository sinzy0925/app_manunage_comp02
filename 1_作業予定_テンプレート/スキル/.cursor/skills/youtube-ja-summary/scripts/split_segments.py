#!/usr/bin/env python3
"""Split cleaned cues into ~10-minute segment files."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

SEGMENT_SECONDS = 600  # 10 minutes


def format_range(start: float, end: float) -> str:
    def fmt(sec: float) -> str:
        total = max(0, int(sec))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    return f"{fmt(start)}〜{fmt(end)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Video duration seconds (from meta). Optional.",
    )
    parser.add_argument("--segment-seconds", type=int, default=SEGMENT_SECONDS)
    args = parser.parse_args()
    outdir: Path = args.outdir
    cues_path = outdir / "cleaned_cues.json"
    if not cues_path.exists():
        raise SystemExit(f"missing {cues_path}")

    cues = json.loads(cues_path.read_text(encoding="utf-8"))
    if not cues:
        raise SystemExit("no cues to split")

    last_t = float(cues[-1]["t"])
    duration = float(args.duration) if args.duration is not None else last_t
    if duration < last_t:
        duration = last_t

    seg_len = max(1, int(args.segment_seconds))
    n = max(1, int(math.ceil(duration / seg_len)))

    seg_dir = outdir / "segments"
    if seg_dir.exists():
        for old in seg_dir.glob("seg_*.txt"):
            old.unlink()
    else:
        seg_dir.mkdir(parents=True, exist_ok=True)

    buckets: list[list[dict]] = [[] for _ in range(n)]
    for cue in cues:
        t = float(cue["t"])
        idx = min(n - 1, int(t // seg_len))
        buckets[idx].append(cue)

    manifest = []
    for i, bucket in enumerate(buckets):
        start = i * seg_len
        end = min(duration, (i + 1) * seg_len)
        # last segment: extend end to duration
        if i == n - 1:
            end = duration
        header = (
            f"# セグメント{i:02d}（{format_range(start, end)}）\n"
            f"# cue_count={len(bucket)}\n"
        )
        body_lines = [f"[{_fmt_ts(float(c['t']))}] {c['text']}" for c in bucket]
        path = seg_dir / f"seg_{i:02d}.txt"
        path.write_text(header + "\n".join(body_lines) + "\n", encoding="utf-8")
        manifest.append(
            {
                "index": i,
                "file": str(path.resolve()),
                "start_seconds": start,
                "end_seconds": end,
                "label": f"セグメント{i:02d}（{format_range(start, end)}）",
                "cue_count": len(bucket),
            }
        )

    (outdir / "segments_manifest.json").write_text(
        json.dumps({"segment_count": n, "segments": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"ok": True, "segment_count": n, "segments_dir": str(seg_dir.resolve())},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _fmt_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


if __name__ == "__main__":
    raise SystemExit(main())
