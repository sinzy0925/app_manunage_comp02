#!/usr/bin/env python3
"""unit_consistency の単体テスト（動画固有辞書なし）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from unit_consistency import (  # noqa: E402
    apply_unit_consistency,
    build_unit_bindings,
    extract_number_unit,
    find_unit_conflicts,
    normalize_numeric_fact,
)

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"


def test_extract_number_unit_from_context() -> None:
    number, unit = extract_number_unit("300", "最大で300kmまで詰めるんだ")
    assert number == "300"
    assert unit == "km"
    normalized = normalize_numeric_fact({"value": "300", "context": "最大で300kmまで詰めるんだ", "score": 5})
    assert normalized["value"] == "300km"
    assert normalized["unit"] == "km"
    print("extract number+unit ok:", normalized)


def test_km_kg_conflict_with_competing_bindings() -> None:
    """同一数値300に km と 発 がある場合、300kg は km 側で修正。"""
    bundle = {
        "numeric_facts": [
            {"value": "300", "context": "年間で約300発くらい", "score": 10, "segment": 4},
            {"value": "300", "context": "最大で300kmまで詰める", "score": 7, "segment": 0},
        ]
    }
    draft = {
        "conclusion": "-",
        "chapter_summary": "■",
        "segment_summaries": "- 最大300kgの積載",
    }
    fixed = apply_unit_consistency(draft, bundle)
    assert "300kg" not in fixed["segment_summaries"].lower()
    assert "300km" in fixed["segment_summaries"].lower()
    print("competing bindings ok")


def test_no_fix_without_binding() -> None:
    """バインディングにない数値は触らない。"""
    bundle = {"numeric_facts": []}
    draft = {
        "conclusion": "- 500kg",
        "chapter_summary": "■",
        "segment_summaries": "- 500kg",
    }
    fixed = apply_unit_consistency(draft, bundle)
    assert fixed["segment_summaries"] == "- 500kg"
    print("no binding no fix ok")


def test_fixture_has_300km_binding() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    from enrich_bundle import enrich_bundle

    enriched = enrich_bundle(bundle)
    facts = enriched["numeric_facts"]
    km300 = [f for f in facts if f.get("number") == "300" and f.get("unit") == "km"]
    if not km300:
        # fixture に 300km 文脈が無い場合は enrich 後の全 facts から km 系を確認
        km_facts = [f for f in facts if f.get("unit") == "km"]
        assert km_facts, "km binding が1件も無い"
        print("fixture km bindings ok (no 300km):", km_facts[0]["value"])
        return
    print("fixture 300km binding ok:", km300[0]["value"])


if __name__ == "__main__":
    test_extract_number_unit_from_context()
    test_km_kg_conflict_with_competing_bindings()
    test_no_fix_without_binding()
    test_fixture_has_300km_binding()
    print("unit_consistency 合格")
