#!/usr/bin/env python3
"""draft_audit の機械監査テスト（API 不要）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from draft_audit import (  # noqa: E402
    audit_draft,
    find_date_merge_issues,
    find_english_fragments,
    score_draft,
)
from enrich_bundle import enrich_bundle  # noqa: E402

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"


def test_english_fragment_detection() -> None:
    draft = {
        "conclusion": "",
        "chapter_summary": "",
        "segment_summaries": [
            {"index": 5, "bullets": ["12 of 部隊が統合された"]},
        ],
    }
    issues = find_english_fragments(draft)
    assert issues, issues
    print("english fragment ok:", issues[0]["type"])


def test_date_merge_detection() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    assert enriched.get("date_hints"), enriched.get("date_hints")
    draft = {
        "conclusion": "",
        "chapter_summary": "",
        "segment_summaries": [
            {
                "index": 1,
                "bullets": [
                    "2024年4月2日の朝6時頃、ヤラブガ工場が攻撃された（1月2日の朝とも関連）"
                ],
            }
        ],
    }
    issues = find_date_merge_issues(enriched, draft)
    assert issues, issues
    print("date merge ok:", issues[0]["note"][:40])


def test_score_prefers_cleaner_draft() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    good = {
        "conclusion": "- 要点",
        "chapter_summary": "■ 章\n- 説明",
        "segment_summaries": [
            {"index": 1, "bullets": ["2024年4月2日、ヤラブガの地点が紹介された", "1月2日の朝6時頃に攻撃"]},
        ],
    }
    bad = {
        "conclusion": "- 要点",
        "chapter_summary": "■ 章\n- 西側巡航ミサイルを凌駕する性能",
        "segment_summaries": [
            {"index": 1, "bullets": ["2024年4月2日の朝6時頃に1月2日の攻撃があった", "12 of 部隊"]},
        ],
    }
    assert score_draft(enriched, good) > score_draft(enriched, bad)
    audit = audit_draft(enriched, bad)
    assert audit["english_fragments"] or audit["date_merge_issues"]
    print("score draft ok")


if __name__ == "__main__":
    test_english_fragment_detection()
    test_date_merge_detection()
    test_score_prefers_cleaner_draft()
    print("draft_audit 合格")
