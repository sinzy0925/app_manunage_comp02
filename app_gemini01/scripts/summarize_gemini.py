#!/usr/bin/env python3
"""Gemini API で ai_bundle を一括要約し summary_draft.json を生成する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_prompt import (
    SYSTEM_INSTRUCTION,
    VERIFY_SYSTEM_INSTRUCTION,
    build_user_payload_dict,
    build_verify_payload,
)
from common import JIMaku_DIR, configure_stdout_utf8
from gemini_client import create_text_interaction
from postprocess_draft import (
    count_segment_items,
    is_segment_items_list,
    postprocess_draft,
)
from must_cover_check import coverage_summary

SEGMENT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["index", "bullets"],
    "properties": {
        "index": {"type": "integer"},
        "bullets": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "additionalProperties": False,
}

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["conclusion", "chapter_summary", "segment_summaries"],
    "properties": {
        "conclusion": {"type": "string"},
        "chapter_summary": {"type": "string"},
        "segment_summaries": {
            "type": "array",
            "items": SEGMENT_ITEM_SCHEMA,
        },
    },
    "additionalProperties": False,
}

RETRY_SYSTEM_INSTRUCTION = (
    SYSTEM_INSTRUCTION
    + "\n\n【修正依頼】前回の出力に問題があります。segment_summaries は "
    "[{index, bullets[]}] 配列で segment_count と同数にし、index は segments[].index "
    "（0始まり・連番）に厳密に合わせて修正した JSON のみを返してください。"
)


def _normalize_draft_shape(draft: dict, bundle: dict | None = None) -> dict:
    """structured output の型ゆれを正規化。segment_summaries は配列のまま保持。"""
    result = dict(draft)

    conclusion = result.get("conclusion", "")
    if isinstance(conclusion, list):
        lines = [str(x).strip() for x in conclusion if str(x).strip()]
        result["conclusion"] = "\n".join(
            line if line.startswith("-") else f"- {line}" for line in lines
        )
    else:
        result["conclusion"] = str(conclusion)

    chapter = result.get("chapter_summary", "")
    if isinstance(chapter, list):
        lines = [str(x).strip() for x in chapter if str(x).strip()]
        result["chapter_summary"] = "\n".join(lines)
    else:
        result["chapter_summary"] = str(chapter)

    segments = result.get("segment_summaries", "")
    if is_segment_items_list(segments):
        normalized_items: list[dict] = []
        for item in segments:
            idx = int(item.get("index", len(normalized_items)))
            bullets_raw = item.get("bullets", [])
            if isinstance(bullets_raw, str):
                bullets_raw = [bullets_raw]
            bullets = [str(b).strip().lstrip("-").strip() for b in bullets_raw if str(b).strip()]
            normalized_items.append({"index": idx, "bullets": bullets})
        result["segment_summaries"] = normalized_items
    elif isinstance(segments, dict):
        parts: list[dict] = []
        seg_meta: dict[int, dict] = {}
        if bundle:
            for seg in bundle.get("segments", []):
                seg_meta[int(seg["index"])] = seg

        def _sort_key(k: object) -> int:
            digits = "".join(ch for ch in str(k) if ch.isdigit())
            return int(digits) if digits else 0

        for key in sorted(segments.keys(), key=_sort_key):
            idx = _sort_key(key)
            value = segments[key]
            if isinstance(value, list):
                bullets = [str(x).strip().lstrip("-").strip() for x in value if str(x).strip()]
            else:
                bullets = [str(value).strip()]
            parts.append({"index": idx, "bullets": bullets})
        result["segment_summaries"] = parts
    elif isinstance(segments, str) and segments.strip():
        result["segment_summaries"] = segments
    else:
        result["segment_summaries"] = segments if isinstance(segments, list) else []

    return result


def _parse_summary_json(raw: str, bundle: dict | None = None) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini 応答の JSON パースに失敗しました: {exc}\n先頭200文字: {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"Gemini 応答がオブジェクトではありません: {type(parsed).__name__}")
    return _normalize_draft_shape(parsed, bundle=bundle)


def _call_gemini(
    *,
    input_payload: dict,
    bundle: dict | None,
    model: str | None,
    thinking_level: str | None,
    system_instruction: str,
) -> dict:
    input_text = json.dumps(input_payload, ensure_ascii=False, indent=2)
    raw = create_text_interaction(
        system_instruction=system_instruction,
        input_text=input_text,
        model=model,
        thinking_level=thinking_level,
        response_schema=SUMMARY_SCHEMA,
    )
    if not raw.strip():
        raise ValueError("Gemini 応答が空です")
    return _parse_summary_json(raw, bundle=bundle)


def _call_summarize(
    *,
    bundle: dict,
    model: str | None,
    thinking_level: str | None,
    system_instruction: str,
    extra_user_note: str | None = None,
) -> dict:
    payload = build_user_payload_dict(bundle)
    if extra_user_note:
        payload["_retry_note"] = extra_user_note
    draft = _call_gemini(
        input_payload=payload,
        bundle=bundle,
        model=model,
        thinking_level=thinking_level,
        system_instruction=system_instruction,
    )
    return _normalize_draft_shape(draft, bundle=bundle)


def _verify_draft(
    *,
    bundle: dict,
    draft: dict,
    model: str | None,
    thinking_level: str | None,
) -> dict:
    cov = coverage_summary(bundle, draft)
    payload = build_verify_payload(bundle, draft)
    if cov["missing"]:
        payload["reference"]["_coverage_note"] = (
            f"must_cover {cov['covered']}/{cov['total']} 件カバー。"
            f"missing_must_cover の {len(cov['missing'])} 件を優先追加してください。"
        )
    verified = _call_gemini(
        input_payload=payload,
        bundle=bundle,
        model=model,
        thinking_level=thinking_level,
        system_instruction=VERIFY_SYSTEM_INSTRUCTION,
    )
    verified = _normalize_draft_shape(verified, bundle=bundle)
    verified["_must_cover_coverage"] = coverage_summary(bundle, verified)
    return verified


def summarize_bundle_gemini(
    bundle: dict,
    *,
    model: str | None = None,
    thinking_level: str | None = None,
    verify: bool = True,
) -> dict:
    expected = int(bundle.get("segment_count", 0)) or None
    draft = _call_summarize(
        bundle=bundle,
        model=model,
        thinking_level=thinking_level,
        system_instruction=SYSTEM_INSTRUCTION,
    )
    draft = postprocess_draft(
        draft,
        bundle=bundle,
        expected_segments=expected,
        stringify_segments=False,
    )

    warnings = draft.get("_warnings", [])
    needs_retry = expected is not None and any("セグメント数不一致" in w for w in warnings)
    if needs_retry:
        retry_note = (
            f"segment_count={expected} だが segment_summaries の要素数は "
            f"{count_segment_items(draft.get('segment_summaries'))} 個でした。"
        )
        draft = _call_summarize(
            bundle=bundle,
            model=model,
            thinking_level=thinking_level,
            system_instruction=RETRY_SYSTEM_INSTRUCTION,
            extra_user_note=retry_note,
        )
        draft = postprocess_draft(
            draft,
            bundle=bundle,
            expected_segments=expected,
            stringify_segments=False,
        )
        still_bad = any("セグメント数不一致" in w for w in draft.get("_warnings", []))
        if still_bad:
            draft.setdefault("_warnings", []).append(
                "リトライ後もセグメント数不一致。出力はそのまま保存します。"
            )

    if verify:
        draft = _verify_draft(
            bundle=bundle,
            draft=draft,
            model=model,
            thinking_level=thinking_level,
        )

    draft = postprocess_draft(
        draft,
        bundle=bundle,
        expected_segments=expected,
        stringify_segments=True,
    )
    return draft


def load_bundle(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"バンドルが見つかりません: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini で字幕バンドルを要約")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--bundle", help="AI バンドル JSON")
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL"))
    parser.add_argument("--thinking-level", default=os.environ.get("GEMINI_THINKING_LEVEL"))
    parser.add_argument("--no-verify", action="store_true", help="Pass2 事実検証をスキップ")
    parser.add_argument("--output", help="要約ドラフト JSON 出力先")
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    bundle_path = Path(args.bundle) if args.bundle else base / f"{args.video_id}_ai_bundle.json"

    if not bundle_path.exists():
        from load_manifest import build_ai_bundle

        mpath = base / f"{args.video_id}_manifest.json"
        bundle = build_ai_bundle(mpath, base)
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        bundle = load_bundle(bundle_path)

    try:
        summary = summarize_bundle_gemini(
            bundle,
            model=args.model,
            thinking_level=args.thinking_level,
            verify=not args.no_verify,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_path = Path(args.output) if args.output else base / f"{args.video_id}_summary_draft.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"draft_path": str(out_path), "warnings": summary.get("_warnings", [])},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
