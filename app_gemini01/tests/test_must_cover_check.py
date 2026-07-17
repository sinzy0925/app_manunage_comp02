#!/usr/bin/env python3
"""must_cover_check の単体テスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from enrich_bundle import enrich_bundle  # noqa: E402
from must_cover_check import find_missing_must_cover, is_fact_covered  # noqa: E402

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"


def test_date_coverage() -> None:
    item = {"value": "2024年4月2日", "context": "2024年4月2日、タールスタン"}
    assert is_fact_covered(item, "2024年4月2日の攻撃")
    assert not is_fact_covered(item, "1月2日の朝、攻撃")
    print("date coverage ok")


def test_fixture_has_full_date_in_must_cover() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    values = [str(m.get("value", "")) for m in enriched.get("must_cover", [])]
    assert any("2024年4月2日" in v for v in values), values[:8]
    print("must_cover date ok:", [v for v in values if "2024" in v][:3])


def test_missing_detection() -> None:
    bundle = {"must_cover": [{"value": "2024年4月2日", "context": "ヤラブガ", "segment": 1}]}
    draft = {
        "conclusion": "- test",
        "chapter_summary": "■ test",
        "segment_summaries": [{"index": 1, "bullets": ["1月2日に攻撃"]}],
    }
    missing = find_missing_must_cover(bundle, draft)
    assert missing, missing
    print("missing detection ok")


if __name__ == "__main__":
    test_date_coverage()
    test_fixture_has_full_date_in_must_cover()
    test_missing_detection()
    print("must_cover_check 合格")
