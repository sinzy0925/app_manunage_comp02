#!/usr/bin/env python3
"""Orchestrate fetch -> clean -> split. Print timing and output paths."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def run_py(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def safe_print(text: str) -> None:
    """Avoid Windows cp932 crash on mixed Unicode from yt-dlp."""
    if not text:
        return
    try:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        sys.stdout.buffer.write((text + "\n").encode(enc, errors="replace"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="YouTube JA subtitle prep pipeline for high-accuracy summary"
    )
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("youtube_summary_work"),
        help="Root directory for per-video work folders (default: ./youtube_summary_work)",
    )
    parser.add_argument(
        "--output-md-dir",
        type=Path,
        default=Path("."),
        help="Directory where the agent should write YouTube動画要約_<id>.md",
    )
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    started = now_str()
    print(f"pipeline_started_at: {started}")

    # Provisional dir until we know video_id; use a temp then rename — simpler:
    # fetch into work_root/_pending then move. Even simpler: fetch with yt-dlp first
    # via fetch_subs into work_root/tmp_*, read id from meta.
    pending = args.work_root / "_pending"
    if pending.exists():
        # clean shallow
        for p in pending.iterdir():
            if p.is_file():
                p.unlink()
    pending.mkdir(parents=True, exist_ok=True)

    fetch = run_py(scripts_dir / "fetch_subs.py", [args.url, "-o", str(pending)])
    safe_print(fetch.stdout)
    if fetch.returncode != 0:
        safe_print(fetch.stderr)
        ended = now_str()
        print(f"pipeline_ended_at: {ended}")
        print("STATUS: FAILED (subtitle fetch)")
        print("Do not summarize. Report error + available languages to the user.")
        return fetch.returncode

    meta = json.loads((pending / "meta.json").read_text(encoding="utf-8"))
    if not meta.get("ok"):
        ended = now_str()
        print(f"pipeline_ended_at: {ended}")
        print("STATUS: FAILED")
        return 1

    video_id = meta["video_id"]
    outdir = args.work_root / video_id
    outdir.mkdir(parents=True, exist_ok=True)

    # Move/copy artifacts from pending -> outdir
    for name in [
        "meta.json",
        "info.json",
        "pipeline_log.txt",
    ]:
        src = pending / name
        if src.exists():
            (outdir / name).write_bytes(src.read_bytes())

    vtt_src = Path(meta["vtt_path"])
    if not vtt_src.exists():
        # try pending
        cand = list(pending.glob("*.vtt"))
        if not cand:
            print("STATUS: FAILED (vtt missing after move)")
            return 1
        vtt_src = cand[0]
    vtt_dst = outdir / vtt_src.name
    vtt_dst.write_bytes(vtt_src.read_bytes())
    meta["vtt_path"] = str(vtt_dst.resolve())
    meta["workdir"] = str(outdir.resolve())
    meta["pipeline_started_at"] = started
    meta["suggested_output_md"] = str(
        (args.output_md_dir / f"YouTube動画要約_{video_id}.md").resolve()
    )
    (outdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    clean = run_py(
        scripts_dir / "clean_vtt.py",
        ["--vtt", str(vtt_dst), "--outdir", str(outdir)],
    )
    safe_print(clean.stdout)
    if clean.returncode != 0:
        safe_print(clean.stderr)
        print("STATUS: FAILED (clean)")
        return clean.returncode

    duration = meta.get("duration_seconds")
    split_args = ["--outdir", str(outdir)]
    if duration is not None:
        split_args.extend(["--duration", str(duration)])
    split = run_py(scripts_dir / "split_segments.py", split_args)
    safe_print(split.stdout)
    if split.returncode != 0:
        safe_print(split.stderr)
        print("STATUS: FAILED (split)")
        return split.returncode

    seg_manifest = json.loads(
        (outdir / "segments_manifest.json").read_text(encoding="utf-8")
    )
    meta["segment_count"] = seg_manifest["segment_count"]
    ended = now_str()
    meta["pipeline_ended_at"] = ended
    (outdir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # cleanup pending vtts to avoid clutter (keep folder)
    for p in pending.glob("*"):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass

    print("---")
    print(f"STATUS: OK")
    print(f"workdir: {outdir.resolve()}")
    print(f"meta: {(outdir / 'meta.json').resolve()}")
    print(f"cleaned: {(outdir / 'cleaned.txt').resolve()}")
    print(f"segments: {(outdir / 'segments').resolve()}")
    print(f"segment_count: {meta['segment_count']}")
    print(f"sub_source: {meta.get('sub_source')}")
    print(f"suggested_output_md: {meta['suggested_output_md']}")
    print(f"pipeline_started_at: {started}")
    print(f"pipeline_ended_at: {ended}")
    print(
        "NEXT: Read meta.json + segments/seg_*.txt + internal_memo.json; "
        "write summary MD using SKILL.md Phase B; report wall-clock start/end to user."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
