#!/usr/bin/env python3
"""enrich_bundle の数値抽出強化テスト（API 不要）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from enrich_bundle import enrich_bundle  # noqa: E402

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"


def test_inventory_facts_extracted() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    values = [f.get("value", "") for f in enriched.get("numeric_facts", [])]
    blob = " ".join(values)
    assert "817体" in blob or any("817" in v for v in values), values[:10]
    print("inventory facts ok:", [v for v in values if "817" in v or "1379" in v][:5])


def test_date_and_range_facts() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    must_values = [str(m.get("value", "")) for m in enriched.get("must_cover", [])]
    assert any("2024年4月2日" in v for v in must_values), must_values[:5]
    range_facts = [f for f in enriched["numeric_facts"] if f.get("kind") == "range"]
    assert any(f.get("value") == "300km" for f in range_facts), range_facts
    print("date/range facts ok")


if __name__ == "__main__":
    test_inventory_facts_extracted()
    test_date_and_range_facts()
    print("enrich inventory 合格")
