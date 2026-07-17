#!/usr/bin/env python3
"""字幕テキストのクリーニング（タグ除去・重複圧縮）。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asr_corrections import apply_corrections
from common import JIMaku_DIR, configure_stdout_utf8, load_manifest, manifest_path, save_manifest
from fetch_subs import parse_vtt, split_segments

BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")
WHITESPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])")
IMMEDIATE_REPEAT_RE = re.compile(r"(.{10,120}?)\1+")


def remove_bracket_tags(text: str) -> str:
    return BRACKET_TAG_RE.sub("", text)


def normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub("", text).strip()


def collapse_consecutive_repeats(text: str, min_len: int = 3) -> str:
    """連続する同一フレーズを1つに圧縮（自動字幕の3連続など）。"""
    if len(text) < min_len * 2:
        return text

    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched = False
        max_len = min((n - i) // 2, 120)
        for length in range(max_len, min_len - 1, -1):
            chunk = text[i : i + length]
            reps = 1
            pos = i + length
            while pos + length <= n and text[pos : pos + length] == chunk:
                reps += 1
                pos += length
            if reps > 1:
                parts.append(chunk)
                i += reps * length
                matched = True
                break
        if not matched:
            parts.append(text[i])
            i += 1
    return "".join(parts)


def clean_entry_text(text: str) -> str:
    text = remove_bracket_tags(text)
    text = normalize_whitespace(text)
    text = collapse_consecutive_repeats(text)
    text = apply_corrections(text)
    return text.strip()


def _suffix_prefix_overlap(left: str, right: str, *, min_overlap: int = 8) -> int:
    """連結テキスト境界で、左の末尾と右の先頭が重なる文字数。"""
    max_check = min(len(left), len(right), 100)
    for size in range(max_check, min_overlap - 1, -1):
        if left.endswith(right[:size]):
            return size
    return 0


def _dedupe_clauses(clauses: list[str]) -> list[str]:
    """句単位で連続重複・拡張版プレフィックスを圧縮。"""
    result: list[str] = []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        norm = normalize_whitespace(clause)
        if not norm:
            continue
        if result:
            prev = result[-1]
            prev_norm = normalize_whitespace(prev)
            if norm == prev_norm:
                continue
            if norm.startswith(prev_norm):
                result[-1] = clause
                continue
            if prev_norm.startswith(norm):
                continue
            overlap = _suffix_prefix_overlap(prev_norm, norm)
            if overlap >= min(10, len(prev_norm) // 2, len(norm) // 2):
                result[-1] = prev_norm + norm[overlap:]
                continue
        result.append(clause)
    return result


def compact_merged_text(text: str) -> str:
    """結合後テキスト向けの追加圧縮（自動字幕のローリング重複を除去）。"""
    if not text:
        return text

    text = normalize_whitespace(text)

    for _ in range(3):
        text = IMMEDIATE_REPEAT_RE.sub(r"\1", text)

    clauses = [part for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
    if clauses:
        text = "".join(_dedupe_clauses(clauses))

    for _ in range(2):
        text = IMMEDIATE_REPEAT_RE.sub(r"\1", text)

    # 長文は句単位で collapse し、全体の O(n^2) 走査を避ける
    if len(text) > 5000:
        clauses = [part for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]
        compacted: list[str] = []
        for clause in clauses:
            if len(clause) > 200:
                clause = collapse_consecutive_repeats(clause, min_len=10)
                clause = IMMEDIATE_REPEAT_RE.sub(r"\1", clause)
            compacted.append(clause)
        text = "".join(compacted)
    else:
        text = collapse_consecutive_repeats(text, min_len=10)
        text = IMMEDIATE_REPEAT_RE.sub(r"\1", text)

    return text.strip()


def dedupe_rolling_prefix(entries: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    """自動字幕の増えていくプレフィックス重複を除去。"""
    result: list[dict[str, float | str]] = []
    for entry in entries:
        text = str(entry["text"]).strip()
        if not text:
            continue
        if result:
            prev = str(result[-1]["text"])
            if text == prev:
                continue
            if text.startswith(prev):
                result[-1] = {"start": entry["start"], "text": text}
                continue
            if prev.startswith(text):
                continue
        result.append({"start": entry["start"], "text": text})
    return result


def dedupe_consecutive_identical(entries: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []
    for entry in entries:
        if result and result[-1]["text"] == entry["text"]:
            continue
        result.append(entry)
    return result


def clean_entries(entries: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    preliminary: list[dict[str, float | str]] = []
    for entry in entries:
        text = clean_entry_text(str(entry["text"]))
        if text:
            preliminary.append({"start": entry["start"], "text": text})
    cleaned = dedupe_rolling_prefix(preliminary)
    return dedupe_consecutive_identical(cleaned)


def join_entries(entries: list[dict[str, float | str]]) -> str:
    return "\n".join(str(e["text"]) for e in entries if str(e["text"]).strip())


def cleaning_stats(
    raw_entries: list,
    clean_entries_list: list,
    raw_text: str,
    joined_text: str,
    compact_text: str,
) -> dict:
    raw_chars = len(raw_text)
    joined_chars = len(joined_text)
    compact_chars = len(compact_text)
    entry_reduction = round((1 - joined_chars / raw_chars) * 100, 1) if raw_chars else 0.0
    compact_reduction = round((1 - compact_chars / joined_chars) * 100, 1) if joined_chars else 0.0
    total_reduction = round((1 - compact_chars / raw_chars) * 100, 1) if raw_chars else 0.0
    return {
        "raw_entry_count": len(raw_entries),
        "clean_entry_count": len(clean_entries_list),
        "raw_char_count": raw_chars,
        "joined_char_count": joined_chars,
        "clean_char_count": compact_chars,
        "entry_reduction_pct": entry_reduction,
        "compact_reduction_pct": compact_reduction,
        "reduction_pct": total_reduction,
    }


def clean_subtitles(manifest_file: Path, jimaku_dir: Path | None = None) -> dict:
    """manifest の VTT から再パースし、クリーニング済みテキストを書き戻す。"""
    data = load_manifest(manifest_file)
    base = jimaku_dir or manifest_file.parent
    video_id = data["video_id"]
    lang = data.get("lang", "ja")
    segment_minutes = int(data.get("segment_minutes", 10))

    vtt_path = Path(data["vtt_path"])
    if not vtt_path.exists():
        raise FileNotFoundError(f"VTT が見つかりません: {vtt_path}")

    raw_entries = parse_vtt(vtt_path)
    if not raw_entries:
        raise ValueError("字幕エントリが空です")

    raw_text = "".join(str(e["text"]) for e in raw_entries)
    entries = clean_entries(raw_entries)
    joined_text = join_entries(entries)
    clean_text = apply_corrections(compact_merged_text(joined_text))

    full_path = base / f"{video_id}_{lang}_full.txt"
    full_path.write_text(clean_text, encoding="utf-8")

    segments = split_segments(entries, segment_minutes)
    segment_paths: list[str] = []
    segment_meta: list[dict] = []
    for seg in segments:
        seg_entries = [
            e for e in entries if seg["start_sec"] <= float(e["start"]) < seg["end_sec"]
        ]
        seg_text = apply_corrections(compact_merged_text(join_entries(seg_entries)))

        seg_path = base / f"segment_{seg['index']:02d}.txt"
        seg_path.write_text(seg_text, encoding="utf-8")
        segment_paths.append(str(seg_path))
        segment_meta.append(
            {
                "index": seg["index"],
                "start_sec": seg["start_sec"],
                "end_sec": seg["end_sec"],
                "path": str(seg_path),
            }
        )

    stats = cleaning_stats(raw_entries, entries, raw_text, joined_text, clean_text)
    data["full_text_path"] = str(full_path)
    data["segment_paths"] = segment_paths
    data["segments"] = segment_meta
    data["segment_count"] = len(segments)
    data["entry_count"] = len(entries)
    data["cleaning"] = stats
    save_manifest(manifest_file, data)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="jimaku/ の字幕テキストをクリーニング")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    mpath = manifest_path(args.video_id, base)

    try:
        manifest = clean_subtitles(mpath, base)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "video_id": manifest["video_id"],
                "manifest_path": str(mpath),
                "cleaning": manifest.get("cleaning", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
