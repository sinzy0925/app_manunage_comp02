#!/usr/bin/env python3
"""YouTube字幕を取得し jimaku/ に保存する。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.lstrip("/").split("/")[0]
    if "youtube.com" in (parsed.hostname or ""):
        qs = parse_qs(parsed.query)
        if "v" in qs:
            return qs["v"][0]
        m = re.match(r"^/(?:shorts|embed|live)/([^/?]+)", parsed.path or "")
        if m:
            return m.group(1)
    raise ValueError(f"YouTube URL から video ID を取得できません: {url}")


def run_yt_dlp(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["yt-dlp", "--no-update", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def download_subtitle(url: str, output_dir: Path, lang: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(id)s")
    result = run_yt_dlp(
        [
            "--write-auto-subs",
            "--write-subs",
            "--sub-lang",
            lang,
            "--sub-format",
            "vtt",
            "--skip-download",
            "-o",
            template,
            url,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "yt-dlp failed")

    video_id = extract_video_id(url)
    candidates = sorted(output_dir.glob(f"{video_id}*.{lang}.vtt"))
    if not candidates:
        candidates = sorted(output_dir.glob(f"{video_id}*.vtt"))
    if not candidates:
        raise FileNotFoundError(f"字幕ファイルが見つかりません: {output_dir}")
    return candidates[0]


def parse_vtt(path: Path) -> list[dict[str, float | str]]:
    content = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content)
    entries: list[dict[str, float | str]] = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        time_line = None
        text_lines: list[str] = []
        for line in lines:
            if "-->" in line:
                time_line = line
            elif (
                not re.match(r"^\d+$", line)
                and not line.startswith("WEBVTT")
                and not line.startswith("Kind:")
                and not line.startswith("Language:")
                and not line.startswith("align:")
                and not line.startswith("position:")
            ):
                text_lines.append(re.sub(r"<[^>]+>", "", line.strip()))

        if not time_line or not text_lines:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)\.(\d+)", time_line)
        if not m:
            continue
        h, mi, s, ms = map(int, m.groups())
        start = h * 3600 + mi * 60 + s + ms / 1000
        text = "".join(text_lines)
        entries.append({"start": start, "text": text})

    deduped: list[dict[str, float | str]] = []
    for entry in entries:
        if deduped and deduped[-1]["text"] == entry["text"]:
            continue
        deduped.append(entry)
    return deduped


def split_segments(entries: list[dict[str, float | str]], minutes: int) -> list[dict]:
    seg_duration = minutes * 60
    segments: list[dict] = []
    current: list[dict[str, float | str]] = []
    seg_start = 0
    seg_idx = 0

    for entry in entries:
        while float(entry["start"]) >= seg_start + seg_duration:
            if current:
                segments.append(
                    {
                        "index": seg_idx,
                        "start_sec": seg_start,
                        "end_sec": seg_start + seg_duration,
                        "text": "".join(str(x["text"]) for x in current),
                    }
                )
                seg_idx += 1
                current = []
            seg_start += seg_duration
        current.append(entry)

    if current:
        end_sec = float(entries[-1]["start"]) + 5 if entries else seg_start + seg_duration
        segments.append(
            {
                "index": seg_idx,
                "start_sec": seg_start,
                "end_sec": end_sec,
                "text": "".join(str(x["text"]) for x in current),
            }
        )
    return segments


def get_metadata(url: str) -> dict[str, str]:
    result = run_yt_dlp(
        [
            "--print",
            "%(id)s|%(title)s|%(duration)s|%(uploader)s",
            "--skip-download",
            url,
        ]
    )
    if result.returncode != 0:
        return {}
    line = result.stdout.strip().splitlines()[-1]
    parts = line.split("|", 3)
    if len(parts) != 4:
        return {}
    return {
        "video_id": parts[0],
        "title": parts[1],
        "duration_sec": parts[2],
        "uploader": parts[3],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube字幕を jimaku/ に保存")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument(
        "--output-dir",
        default="jimaku",
        help="字幕保存先ディレクトリ (default: jimaku)",
    )
    parser.add_argument(
        "--lang",
        default="ja",
        help="字幕言語コード (default: ja)",
    )
    parser.add_argument(
        "--segment-minutes",
        type=int,
        default=10,
        help="分割要約の単位（分） (default: 10)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    metadata = get_metadata(args.url)
    video_id = metadata.get("video_id") or extract_video_id(args.url)

    vtt_path = download_subtitle(args.url, output_dir, args.lang)
    entries = parse_vtt(vtt_path)
    if not entries:
        print("字幕エントリが空です", file=sys.stderr)
        return 1

    full_text = "".join(str(e["text"]) for e in entries)
    full_path = output_dir / f"{video_id}_{args.lang}_full.txt"
    full_path.write_text(full_text, encoding="utf-8")

    segments = split_segments(entries, args.segment_minutes)
    segment_paths: list[str] = []
    for seg in segments:
        seg_path = output_dir / f"segment_{seg['index']:02d}.txt"
        seg_path.write_text(str(seg["text"]), encoding="utf-8")
        segment_paths.append(str(seg_path))

    manifest = {
        "url": args.url,
        "video_id": video_id,
        "lang": args.lang,
        "vtt_path": str(vtt_path),
        "full_text_path": str(full_path),
        "segment_paths": segment_paths,
        "segment_count": len(segments),
        "entry_count": len(entries),
        "metadata": metadata,
    }
    manifest_path = output_dir / f"{video_id}_manifest.json"
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
    manifest_path.write_text(manifest_json, encoding="utf-8")

    # Windows コンソールの cp932 でも落ちないよう stdout を UTF-8 に寄せる
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print(manifest_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
