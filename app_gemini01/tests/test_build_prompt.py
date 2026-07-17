#!/usr/bin/env python3
"""Step 4: build_prompt の検証。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.build_prompt import (  # noqa: E402
    PAYLOAD_KEYS,
    SYSTEM_INSTRUCTION,
    build_user_payload,
    build_user_payload_dict,
    validate_payload,
)

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"

REQUIRED_SYSTEM_KEYWORDS = (
    "推測",
    "uncertain_spans",
    "must_cover",
    "numeric_facts",
    "重複",
    "segment_summaries",
    "chapter_summary",
    "conclusion",
    "0始まり",
)


def test_payload_fields() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = build_user_payload_dict(bundle)

    assert "must_cover" in payload and len(payload["must_cover"]) > 0
    assert "uncertain_spans" in payload
    assert "outline_hints" in payload and len(payload["outline_hints"]) > 0
    assert len(payload["segments"]) == payload["segment_count"] == 8

    for key in PAYLOAD_KEYS:
        assert key in payload, key

    errors = validate_payload(payload)
    assert not errors, errors
    print("payload fields ok")


def test_segment_text_not_truncated() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload = build_user_payload_dict(bundle)
    fixture_total = sum(len(s.get("text", "")) for s in bundle["segments"])
    payload_total = sum(len(s.get("text", "")) for s in payload["segments"])
    assert fixture_total == payload_total, f"{fixture_total} vs {payload_total}"
    assert "_warnings" not in payload
    print(f"segment text preserved: {payload_total} chars")


def test_system_instruction() -> None:
    lower = SYSTEM_INSTRUCTION.lower()
    for kw in REQUIRED_SYSTEM_KEYWORDS:
        assert kw in SYSTEM_INSTRUCTION or kw in lower, f"missing keyword: {kw}"
    print("system instruction ok")


def test_build_user_payload_json() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw = build_user_payload(bundle)
    parsed = json.loads(raw)
    assert parsed["segment_count"] == 8
    print("build_user_payload json ok")


if __name__ == "__main__":
    test_payload_fields()
    test_segment_text_not_truncated()
    test_system_instruction()
    test_build_user_payload_json()
    print("Step 4 合格")
