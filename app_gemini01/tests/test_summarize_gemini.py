#!/usr/bin/env python3
"""Step 5: summarize_gemini の検証。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from postprocess_draft import count_segment_headers  # noqa: E402
from summarize_gemini import load_bundle, summarize_bundle_gemini  # noqa: E402

VIDEO_ID = "koBLOf-53_g"
BUNDLE_PATH = _ROOT / "jimaku" / f"{VIDEO_ID}_ai_bundle.json"
DRAFT_PATH = _ROOT / "jimaku" / f"{VIDEO_ID}_summary_draft.json"


def test_summarize_and_save() -> None:
    if not BUNDLE_PATH.exists():
        BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fixture = _ROOT / "tests" / "fixtures" / f"{VIDEO_ID}_ai_bundle.json"
        BUNDLE_PATH.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    bundle = load_bundle(BUNDLE_PATH)
    model = os.environ.get("GEMINI_TEST_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))
    thinking = os.environ.get("GEMINI_TEST_THINKING", os.environ.get("GEMINI_THINKING_LEVEL", "low"))

    print(f"summarizing with model={model} thinking={thinking} ...")
    draft = summarize_bundle_gemini(bundle, model=model, thinking_level=thinking)

    for key in ("conclusion", "chapter_summary", "segment_summaries"):
        assert key in draft, key
        assert len(draft[key]) > 100, f"{key} too short: {len(draft[key])}"

    expected = int(bundle.get("segment_count", 0))
    found = count_segment_headers(str(draft.get("segment_summaries", "")))
    assert found == expected, f"segments expected={expected} found={found}"
    assert not draft.get("_warnings"), draft.get("_warnings")

    DRAFT_PATH.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"draft saved: {DRAFT_PATH}")
    print(f"segment headers: {found}")


if __name__ == "__main__":
    test_summarize_and_save()
    print("Step 5 合格")
