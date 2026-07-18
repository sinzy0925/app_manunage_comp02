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
from unit_consistency import apply_unit_consistency, build_unit_bindings

META_NOTE_RE = re.compile(r"（セグメント\d+と連続）")
SEGMENT_HEADER_RE = re.compile(r"---\s*セグメント(\d+)")
# 自動字幕由来の英語断片（例: 「唯一 of」「12 of」「the 」）
DIGIT_OF_RE = re.compile(r"\d+\s+of\s+", re.IGNORECASE)
ENGLISH_FRAGMENT_RE = re.compile(
    r"(?<=[\u3040-\u30ff\u4e00-\u9fff])(?:\s+(?:of|the|and|or|in|on|at|to|for|with|by)\s*)(?=[\u3040-\u30ff\u4e00-\u9fff、。]|$)",
    re.IGNORECASE,
)
STANDALONE_EN_WORD_RE = re.compile(
    r"(?<=[\u3040-\u30ff\u4e00-\u9fff、])\s+(?:of|the|and|or)\s*(?=[\u3040-\u30ff\u4e00-\u9fff]|$)",
    re.IGNORECASE,
)


def unwrap_draft_payload(data: dict) -> dict:
    """Pass2 が verify ペイロード形式 {draft, reference} を返した場合に展開。"""
    result = dict(data)
    inner = result.get("draft")
    if isinstance(inner, dict):
        for key in ("conclusion", "chapter_summary", "segment_summaries"):
            top = result.get(key)
            inner_val = inner.get(key)
            if inner_val in (None, "", []):
                continue
            if top in (None, "", []):
                result[key] = inner_val
        result.pop("draft", None)
    result.pop("reference", None)
    return result


def draft_field_text(value: object) -> str:
    """レンダリング用にドラフトフィールドを文字列化。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if not value:
            return ""
        if isinstance(value[0], dict) and "bullets" in value[0]:
            lines: list[str] = []
            for item in value:
                for bullet in item.get("bullets", []):
                    text = str(bullet).strip()
                    if text:
                        lines.append(f"- {text.lstrip('-').strip()}")
            return "\n".join(lines)
        return "\n".join(str(x).strip() for x in value if str(x).strip())
    return str(value or "").strip()


def is_segment_items_list(segments: object) -> bool:
    if not isinstance(segments, list) or not segments:
        return False
    first = segments[0]
    return isinstance(first, dict) and "bullets" in first


def format_segment_summaries(bundle: dict, items: list[dict]) -> str:
    """segments[].index（0始まり）からヘッダを機械生成する。"""
    seg_meta = {int(seg.get("index", i)): seg for i, seg in enumerate(bundle.get("segments", []))}
    sorted_items = sorted(items, key=lambda item: int(item.get("index", 0)))
    parts: list[str] = []
    for item in sorted_items:
        idx = int(item.get("index", 0))
        meta = seg_meta.get(idx, {})
        label = str(meta.get("label", ""))
        header = f"--- セグメント{idx:02d}（{label}）---"
        bullets_raw = item.get("bullets", [])
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        bullet_lines: list[str] = []
        for bullet in bullets_raw:
            text = str(bullet).strip().lstrip("-").strip()
            if text:
                bullet_lines.append(f"- {text}")
        parts.append(f"{header}\n" + "\n".join(bullet_lines))
    return "\n\n".join(parts)


def count_segment_headers(segment_summaries: str) -> int:
    return len(SEGMENT_HEADER_RE.findall(segment_summaries))


def count_segment_items(segment_summaries: object) -> int:
    if is_segment_items_list(segment_summaries):
        return len(segment_summaries)
    if isinstance(segment_summaries, str):
        return count_segment_headers(segment_summaries)
    return 0


def _strip_english_fragments(text: str) -> str:
    """日本語文中に紛れた単独英語断片を除去。"""
    text = DIGIT_OF_RE.sub("", text)
    text = ENGLISH_FRAGMENT_RE.sub("", text)
    text = STANDALONE_EN_WORD_RE.sub("", text)
    # 行末の孤立英単語
    text = re.sub(r"\s+(?:of|the|and|or)\s*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    return text


def _fix_text(text: str) -> str:
    text = apply_corrections(text)
    text = META_NOTE_RE.sub("", text)
    text = _strip_english_fragments(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def postprocess_draft(
    draft: dict,
    *,
    bundle: dict | None = None,
    expected_segments: int | None = None,
    stringify_segments: bool = True,
) -> dict:
    result = unwrap_draft_payload(dict(draft))
    for key in ("conclusion", "chapter_summary"):
        if key in result and isinstance(result[key], str):
            result[key] = _fix_text(result[key])

    segments = result.get("segment_summaries")
    if bundle and is_segment_items_list(segments) and stringify_segments:
        result["segment_summaries"] = _fix_text(format_segment_summaries(bundle, segments))
    elif isinstance(segments, str):
        result["segment_summaries"] = _fix_text(segments)

    if "glossary" in result and isinstance(result["glossary"], dict):
        fixed_glossary: dict[str, str] = {}
        for name, desc in result["glossary"].items():
            fixed_glossary[apply_corrections(str(name))] = _fix_text(str(desc))
        result["glossary"] = fixed_glossary

    if expected_segments is not None:
        found = count_segment_items(result.get("segment_summaries"))
        if found != expected_segments:
            result.setdefault("_warnings", []).append(
                f"セグメント数不一致: expected={expected_segments}, found={found}"
            )

    if bundle:
        result = apply_unit_consistency(result, bundle)

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
    bundle: dict | None = None
    if expected is None:
        bundle_path = base / f"{args.video_id}_ai_bundle.json"
        if bundle_path.exists():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            expected = int(bundle.get("segment_count", 0)) or None

    if bundle is None:
        bundle_path = base / f"{args.video_id}_ai_bundle.json"
        if bundle_path.exists():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    processed = postprocess_draft(draft, bundle=bundle, expected_segments=expected)
    draft_path.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")

    warnings = processed.get("_warnings", [])
    print(json.dumps({"draft_path": str(draft_path), "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
