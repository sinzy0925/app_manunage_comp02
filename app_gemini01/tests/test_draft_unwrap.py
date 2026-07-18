#!/usr/bin/env python3
"""unwrap_draft_payload / draft_field_text のテスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from postprocess_draft import draft_field_text, postprocess_draft, unwrap_draft_payload  # noqa: E402
from render_summary import render_summary  # noqa: E402

FIXTURE_DRAFT = _ROOT / "jimaku" / "koBLOf-53_g_summary_draft.json"
MANIFEST = _ROOT / "jimaku" / "koBLOf-53_g_manifest.json"
BUNDLE = _ROOT / "jimaku" / "koBLOf-53_g_ai_bundle.json"


def test_unwrap_nested_draft() -> None:
    nested = {
        "draft": {
            "conclusion": "- 結論",
            "chapter_summary": "■ 章",
            "segment_summaries": [{"index": 0, "bullets": ["ファクト"]}],
        },
        "conclusion": "",
        "segment_summaries": [],
    }
    out = unwrap_draft_payload(nested)
    assert out["conclusion"] == "- 結論"
    assert out["segment_summaries"][0]["index"] == 0
    assert "draft" not in out
    print("unwrap nested draft ok")


def test_draft_field_text_list() -> None:
    text = draft_field_text([{"index": 0, "bullets": ["a", "b"]}])
    assert "- a" in text and "- b" in text
    print("draft_field_text list ok")


def test_render_corrupted_draft_file() -> None:
    if not FIXTURE_DRAFT.exists() or not MANIFEST.exists():
        print("skip render corrupted (no fixture)")
        return
    raw = json.loads(FIXTURE_DRAFT.read_text(encoding="utf-8"))
    if "draft" not in raw:
        print("skip render corrupted (draft already flat)")
        return
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8")) if BUNDLE.exists() else None
    fixed = postprocess_draft(raw, bundle=bundle, stringify_segments=True)
    assert isinstance(fixed["segment_summaries"], str)
    assert fixed["segment_summaries"].strip()
    out = render_summary(MANIFEST, fixed, "2026-01-01 00:00:00.000", "2026-01-01 00:01:00.000")
    assert out.exists()
    print(f"render corrupted draft ok: {out}")


if __name__ == "__main__":
    test_unwrap_nested_draft()
    test_draft_field_text_list()
    test_render_corrupted_draft_file()
    print("draft unwrap 合格")
