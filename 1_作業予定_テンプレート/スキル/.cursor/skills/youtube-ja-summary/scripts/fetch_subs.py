#!/usr/bin/env python3
"""Fetch Japanese subs + metadata via yt-dlp. No video download."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def ensure_yt_dlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        print(
            "ERROR: yt-dlp が見つかりません。\n"
            "インストール例:\n"
            "  winget install yt-dlp\n"
            "  または: pip install -U yt-dlp\n"
            "導入後に再実行してください。要約は中止してください。",
            file=sys.stderr,
        )
        sys.exit(2)
    return exe


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "不明"
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "不明"
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def detect_sub_source(info: dict) -> str:
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    has_manual = "ja" in subs or any(k.startswith("ja") for k in subs)
    has_auto = "ja" in auto or any(k.startswith("ja") for k in auto)
    if has_manual:
        return "日本語手動"
    if has_auto:
        return "日本語自動生成"
    return "不明"


def list_available_langs(yt: str, url: str) -> str:
    proc = _run([yt, "--no-update", "--list-subs", url])
    out = (proc.stdout or "") + (proc.stderr or "")
    return out.strip() or "(list-subs 結果なし)"


def find_vtt(work_dir: Path, video_id: str) -> Path | None:
    candidates = [
        work_dir / f"{video_id}.ja.vtt",
        work_dir / f"{video_id}.ja-orig.vtt",
    ]
    for p in candidates:
        if p.exists():
            return p
    found = sorted(work_dir.glob(f"{video_id}*.ja*.vtt"))
    return found[0] if found else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch JA subs with yt-dlp")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument(
        "-o",
        "--outdir",
        type=Path,
        required=True,
        help="Working directory for this video",
    )
    args = parser.parse_args()
    url = args.url.strip()
    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    yt = ensure_yt_dlp()
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    info_path = outdir / "info.json"
    dump = _run(
        [
            yt,
            "--no-update",
            "--skip-download",
            "--dump-single-json",
            url,
        ]
    )
    if dump.returncode != 0:
        langs = list_available_langs(yt, url)
        result = {
            "ok": False,
            "url": url,
            "error": dump.stderr.strip() or dump.stdout.strip() or "dump-single-json failed",
            "available_subs": langs,
            "started_at": started,
        }
        (outdir / "meta.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        info = json.loads(dump.stdout)
    except json.JSONDecodeError as e:
        result = {
            "ok": False,
            "url": url,
            "error": f"JSON parse error: {e}",
            "available_subs": list_available_langs(yt, url),
            "started_at": started,
        }
        (outdir / "meta.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    info_path.write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    video_id = info.get("id") or "unknown"
    title = info.get("title")
    channel = info.get("channel") or info.get("uploader")
    duration = info.get("duration")
    sub_source = detect_sub_source(info)

    # Subtitles only
    sub_cmd = [
        yt,
        "--no-update",
        "--write-auto-subs",
        "--write-subs",
        "--sub-langs",
        "ja",
        "--sub-format",
        "vtt",
        "--skip-download",
        "-o",
        str(outdir / "%(id)s"),
        url,
    ]
    sub_proc = _run(sub_cmd)
    log = outdir / "pipeline_log.txt"
    log.write_text(
        f"$ {' '.join(sub_cmd)}\n\nSTDOUT:\n{sub_proc.stdout}\n\nSTDERR:\n{sub_proc.stderr}\n",
        encoding="utf-8",
    )

    vtt = find_vtt(outdir, video_id)
    if vtt is None or not vtt.exists():
        # Fallback: any ja vtt in outdir
        any_vtt = sorted(outdir.glob("*.ja*.vtt"))
        vtt = any_vtt[0] if any_vtt else None

    if vtt is None:
        result = {
            "ok": False,
            "url": url,
            "video_id": video_id,
            "title": title,
            "channel": channel,
            "duration_seconds": duration,
            "duration_display": format_duration(duration),
            "sub_source": sub_source,
            "error": "日本語字幕 (.vtt) を取得できませんでした",
            "available_subs": list_available_langs(yt, url),
            "yt_dlp_stderr": sub_proc.stderr.strip(),
            "started_at": started,
        }
        (outdir / "meta.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    # Refine sub_source from actual file + info
    if sub_source == "不明":
        # If we got a file and info had auto, prefer that wording
        auto = info.get("automatic_captions") or {}
        subs = info.get("subtitles") or {}
        if "ja" in subs:
            sub_source = "日本語手動"
        elif "ja" in auto:
            sub_source = "日本語自動生成"
        else:
            sub_source = "日本語自動生成"  # yt-dlp wrote something ja

    result = {
        "ok": True,
        "url": url,
        "video_id": video_id,
        "title": title,
        "channel": channel,
        "duration_seconds": duration,
        "duration_display": format_duration(duration),
        "sub_source": sub_source,
        "vtt_path": str(vtt.resolve()),
        "started_at": started,
    }
    (outdir / "meta.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
