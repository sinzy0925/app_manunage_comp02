#!/usr/bin/env python3
"""要約ドラフトの機械的整形（AI 再要約なし）。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from asr_corrections import apply_corrections
from common import JIMaku_DIR, configure_stdout_utf8

META_NOTE_RE = re.compile(r"（セグメント\d+と連続）")
SEGMENT_HEADER_RE = re.compile(r"---\s*セグメント(\d+)")


def _fix_text(text: str) -> str:
    text = apply_corrections(text)
    text = META_NOTE_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def count_segment_headers(segment_summaries: str) -> int:
    return len(SEGMENT_HEADER_RE.findall(segment_summaries))


def postprocess_draft(draft: dict, *, expected_segments: int | None = None) -> dict:
    result = dict(draft)
    for key in ("conclusion", "chapter_summary", "segment_summaries"):
        if key in result and isinstance(result[key], str):
            result[key] = _fix_text(result[key])

    if "glossary" in result and isinstance(result["glossary"], dict):
        fixed_glossary: dict[str, str] = {}
        for name, desc in result["glossary"].items():
            fixed_glossary[apply_corrections(str(name))] = _fix_text(str(desc))
        result["glossary"] = fixed_glossary

    if expected_segments is not None:
        found = count_segment_headers(str(result.get("segment_summaries", "")))
        if found != expected_segments:
            result.setdefault("_warnings", []).append(
                f"セグメント数不一致: expected={expected_segments}, found={found}"
            )

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="要約ドラフトを機械的に整形")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--draft", help="要約ドラフト JSON")
    parser.add_argument("--expected-segments", type=int)
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    draft_path = Path(args.draft) if args.draft else base / f"{args.video_id}_summary_draft.json"
    if not draft_path.exists():
        print(f"ドラフトが見つかりません: {draft_path}", file=sys.stderr)
        return 1

    expected = args.expected_segments
    if expected is None:
        bundle_path = base / f"{args.video_id}_ai_bundle.json"
        if bundle_path.exists():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            expected = int(bundle.get("segment_count", 0)) or None

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    processed = postprocess_draft(draft, expected_segments=expected)
    draft_path.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")

    warnings = processed.get("_warnings", [])
    print(json.dumps({"draft_path": str(draft_path), "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
