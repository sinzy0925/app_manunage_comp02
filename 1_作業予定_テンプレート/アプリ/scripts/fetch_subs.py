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

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import JIMaku_DIR, configure_stdout_utf8, ensure_dirs


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


def list_available_subs(url: str) -> list[str]:
    result = run_yt_dlp(["--list-subs", url])
    if result.returncode != 0:
        return []
    langs: list[str] = []
    for line in result.stdout.splitlines():
        m = re.match(r"^([a-z]{2}(?:-[A-Za-z]+)?)\s+", line.strip())
        if m:
            langs.append(m.group(1))
    return langs


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
        available = list_available_subs(url)
        hint = f" 利用可能な字幕: {', '.join(available)}" if available else ""
        raise RuntimeError((result.stderr.strip() or "yt-dlp failed") + hint)

    video_id = extract_video_id(url)
    candidates = sorted(output_dir.glob(f"{video_id}*.{lang}.vtt"))
    if not candidates:
        candidates = sorted(output_dir.glob(f"{video_id}*.vtt"))
    if not candidates:
        available = list_available_subs(url)
        hint = f" 利用可能な字幕: {', '.join(available)}" if available else ""
        raise FileNotFoundError(f"字幕ファイルが見つかりません: {output_dir}{hint}")
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
    result = run_yt_dlp(["-j", "--skip-download", url])
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {}
    return {
        "video_id": str(data.get("id", "")),
        "title": str(data.get("title", "")),
        "duration_sec": str(data.get("duration", "")),
        "uploader": str(data.get("uploader") or data.get("channel") or ""),
    }


def fetch_subtitles(
    url: str,
    output_dir: Path | None = None,
    lang: str = "ja",
    segment_minutes: int = 10,
) -> dict:
    base = output_dir or JIMaku_DIR
    ensure_dirs()
    metadata = get_metadata(url)
    video_id = metadata.get("video_id") or extract_video_id(url)

    try:
        vtt_path = download_subtitle(url, base, lang)
    except (RuntimeError, FileNotFoundError):
        available = list_available_subs(url)
        if lang not in available and available:
            fallback = available[0]
            vtt_path = download_subtitle(url, base, fallback)
            lang = fallback
        else:
            raise

    entries = parse_vtt(vtt_path)
    if not entries:
        raise ValueError("字幕エントリが空です")

    full_text = "".join(str(e["text"]) for e in entries)
    full_path = base / f"{video_id}_{lang}_full.txt"
    full_path.write_text(full_text, encoding="utf-8")

    segments = split_segments(entries, segment_minutes)
    segment_paths: list[str] = []
    segment_meta: list[dict] = []
    for seg in segments:
        seg_path = base / f"segment_{seg['index']:02d}.txt"
        seg_path.write_text(str(seg["text"]), encoding="utf-8")
        segment_paths.append(str(seg_path))
        segment_meta.append(
            {
                "index": seg["index"],
                "start_sec": seg["start_sec"],
                "end_sec": seg["end_sec"],
                "path": str(seg_path),
            }
        )

    manifest = {
        "url": url,
        "video_id": video_id,
        "lang": lang,
        "segment_minutes": segment_minutes,
        "vtt_path": str(vtt_path),
        "full_text_path": str(full_path),
        "segment_paths": segment_paths,
        "segments": segment_meta,
        "segment_count": len(segments),
        "entry_count": len(entries),
        "metadata": metadata,
        "processing": {},
    }
    manifest_path = base / f"{video_id}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube字幕を jimaku/ に保存")
    parser.add_argument("url", help="YouTube URL")
    parser.add_argument("--output-dir", default=str(JIMaku_DIR), help="保存先")
    parser.add_argument("--lang", default="ja", help="字幕言語")
    parser.add_argument("--segment-minutes", type=int, default=10, help="分割単位（分）")
    args = parser.parse_args()

    configure_stdout_utf8()
    try:
        manifest = fetch_subtitles(
            args.url,
            Path(args.output_dir),
            args.lang,
            args.segment_minutes,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
