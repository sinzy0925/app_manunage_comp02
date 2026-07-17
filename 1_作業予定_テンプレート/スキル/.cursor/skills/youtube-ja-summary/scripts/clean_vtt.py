#!/usr/bin/env python3
"""Clean YouTube VTT: strip tags/noise/dupes only.

No genre-specific ASR dictionary. Proper-noun fixes are left to the agent
using this video's context at summarize time (any-video, one-shot).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")
TS_LINE_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}"
)
CUE_TIME_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
NOTE_RE = re.compile(r"^\s*(NOTE|STYLE|REGION)\b")


def parse_ts(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


DEFAULT_NOISE_TAGS = [
    "[音楽]",
    "[拍手]",
    "[笑い]",
    "[喝采]",
    "♪",
    "[Music]",
    "[Applause]",
    "[Laughter]",
]


def load_noise_tags(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return list(DEFAULT_NOISE_TAGS)
    data = json.loads(path.read_text(encoding="utf-8"))
    noise = list(data.get("noise_tags", []))
    # Intentionally ignore data["replacements"] — no prebuilt ASR dict.
    return noise or list(DEFAULT_NOISE_TAGS)


def strip_noise(text: str, noise_tags: list[str]) -> str:
    for tag in noise_tags:
        text = text.replace(tag, "")
    text = re.sub(r"\[[^\]]{1,20}\]", "", text)
    return text


def cue_plain_lines(block_lines: list[str]) -> list[str]:
    texts: list[str] = []
    for line in block_lines:
        if TS_LINE_RE.match(line) or line.strip().isdigit():
            continue
        if NOTE_RE.match(line):
            continue
        t = TAG_RE.sub("", line).strip()
        if t:
            texts.append(re.sub(r"\s+", " ", t))
    return texts


def parse_cues(vtt_text: str) -> list[tuple[float, float, str]]:
    """Parse VTT cues. For YouTube auto dual-line cues, keep the last line only."""
    lines = vtt_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[tuple[float, float, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = CUE_TIME_RE.search(line)
        if not m:
            i += 1
            continue
        start = parse_ts(m.group("start"))
        end = parse_ts(m.group("end"))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            body.append(lines[i])
            i += 1
        plain = cue_plain_lines(body)
        if not plain:
            continue
        # YouTube auto: line0=previous on-screen, line1+=current rolling → use last
        text = plain[-1].strip()
        if text:
            cues.append((start, end, text))
    return cues


def collapse_youtube_rolling(
    cues: list[tuple[float, float, str]],
) -> list[tuple[float, str]]:
    """Collapse rolling captions into stable lines."""
    if not cues:
        return []

    # Prefer ultra-short "commit" cues when present; else grow prefixes in place
    by_time: list[tuple[float, str]] = []
    for start, end, text in cues:
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        dur = end - start
        if by_time:
            prev_t, prev = by_time[-1]
            if text == prev:
                continue
            if text.startswith(prev) and len(text) > len(prev):
                by_time[-1] = (prev_t, text)
                continue
            if prev.startswith(text):
                # keep longer prev unless this is a short commit cue with same stem
                if dur < 0.05 and len(text) >= len(prev) * 0.6:
                    by_time[-1] = (start, text)
                continue
            # Overlap: previous ends mid-phrase, new starts with its suffix
            overlap = _suffix_prefix_overlap(prev, text)
            if overlap >= 8:
                merged = prev + text[overlap:]
                by_time[-1] = (prev_t, merged)
                continue
        by_time.append((start, text))

    final: list[tuple[float, str]] = []
    for start, text in by_time:
        if final and final[-1][1] == text:
            continue
        final.append((start, text))
    return final


def _suffix_prefix_overlap(prev: str, cur: str) -> int:
    max_k = min(len(prev), len(cur))
    for k in range(max_k, 7, -1):
        if prev.endswith(cur[:k]):
            return k
    return 0


def extract_internal_memo(lines: list[tuple[float, str]]) -> dict:
    full = " ".join(t for _, t in lines)
    outline_hints: list[str] = []
    for pat in [
        r"[0-9０-９]+つの(?:柱|ステップ|ポイント|テーマ)",
        r"(?:第?[0-9０-９]|[一二三四])\s*(?:つ目|章|部)",
        r"(?:ステップ|ステップ\s*[0-9]|柱)\s*[0-9０-９一二三四]?",
    ]:
        for m in re.finditer(pat, full):
            outline_hints.append(m.group(0))

    numeric_facts = sorted(
        set(re.findall(r"[0-9０-９]+(?:\.[0-9０-９]+)?(?:\s*(?:%|％|km|キロ|年|月|日|発|人|ドル|万|億))?", full))
    )[:80]

    # Light entity candidates: Katakana runs 3+
    entities = sorted(set(re.findall(r"[ァ-ヶー]{3,}", full)))[:60]

    uncertain: list[str] = []
    for m in re.finditer(r"[A-Za-z]{2,}[ぁ-んァ-ヶ一-龥]+|[ぁ-んァ-ヶ一-龥]+[A-Za-z]{2,}", full):
        uncertain.append(m.group(0))

    return {
        "outline_hints": sorted(set(outline_hints))[:40],
        "entities": entities,
        "numeric_facts": numeric_facts,
        "uncertain": sorted(set(uncertain))[:40],
    }


def clean_vtt(
    vtt_path: Path,
    noise_config_path: Path | None,
) -> tuple[list[tuple[float, str]], dict, str]:
    noise = load_noise_tags(noise_config_path)
    raw = vtt_path.read_text(encoding="utf-8", errors="replace")
    cues = parse_cues(raw)
    collapsed = collapse_youtube_rolling(cues)

    lines: list[tuple[float, str]] = []
    prev_norm = ""
    for start, text in collapsed:
        text = strip_noise(text, noise)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        norm = text.replace(" ", "")
        if norm == prev_norm:
            continue
        # consecutive identical phrases (allow short fillers)
        if prev_norm and (norm == prev_norm or (len(norm) > 12 and norm in prev_norm)):
            continue
        lines.append((start, text))
        prev_norm = norm

    memo = extract_internal_memo(lines)
    cleaned_body = "\n".join(f"[{format_ts(t)}] {text}" for t, text in lines)
    return lines, memo, cleaned_body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtt", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument(
        "--noise-config",
        type=Path,
        default=None,
        help="Optional JSON with noise_tags only (no word replacements)",
    )
    args = parser.parse_args()
    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    noise_config = args.noise_config
    if noise_config is None:
        candidate = (
            Path(__file__).resolve().parent.parent / "reference" / "asr-glossary.json"
        )
        noise_config = candidate if candidate.exists() else None

    lines, memo, cleaned_body = clean_vtt(args.vtt, noise_config)
    (outdir / "cleaned.txt").write_text(cleaned_body + "\n", encoding="utf-8")
    (outdir / "internal_memo.json").write_text(
        json.dumps(memo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # sidecar for splitter
    sidecar = [{"t": t, "text": text} for t, text in lines]
    (outdir / "cleaned_cues.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "ok": True,
                "lines": len(lines),
                "cleaned": str((outdir / "cleaned.txt").resolve()),
                "memo": str((outdir / "internal_memo.json").resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
