#!/usr/bin/env python3
"""postprocess_draft のセグメント整形テスト（API 不要）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from postprocess_draft import (  # noqa: E402
    _strip_english_fragments,
    count_segment_headers,
    format_segment_summaries,
    is_segment_items_list,
    postprocess_draft,
)

FIXTURE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"


def test_segment_items_detection() -> None:
    items = [{"index": 0, "bullets": ["a", "b"]}]
    assert is_segment_items_list(items)
    assert not is_segment_items_list(["--- セグメント00 ---"])
    print("segment items detection ok")


def test_format_segment_headers_zero_based() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = [
        {"index": 0, "bullets": ["ファクトA", "ファクトB"]},
        {"index": 1, "bullets": ["ファクトC"]},
    ]
    text = format_segment_summaries(bundle, items)
    assert "--- セグメント00（0:00〜10:00）---" in text
    assert "--- セグメント01（10:00〜20:00）---" in text
    assert count_segment_headers(text) == 2
    print("zero-based headers ok")


def test_strip_english_fragments() -> None:
    assert "唯一" in _strip_english_fragments("唯一 of 攻撃")
    assert "of" not in _strip_english_fragments("唯一 of 攻撃")
    assert _strip_english_fragments("正常な日本語のみ") == "正常な日本語のみ"
    print("english fragment strip ok")


def test_postprocess_stringify() -> None:
    bundle = json.loads(FIXTURE.read_text(encoding="utf-8"))
    draft = {
        "conclusion": "- 結論",
        "chapter_summary": "■ 章",
        "segment_summaries": [
            {"index": i, "bullets": [f"item {i}"]}
            for i in range(bundle["segment_count"])
        ],
    }
    processed = postprocess_draft(
        draft,
        bundle=bundle,
        expected_segments=bundle["segment_count"],
        stringify_segments=True,
    )
    text = processed["segment_summaries"]
    assert isinstance(text, str)
    assert count_segment_headers(text) == bundle["segment_count"]
    assert text.startswith("--- セグメント00")
    assert not processed.get("_warnings")
    print(f"postprocess stringify ok: {count_segment_headers(text)} headers")


if __name__ == "__main__":
    test_segment_items_detection()
    test_format_segment_headers_zero_based()
    test_strip_english_fragments()
    test_postprocess_stringify()
    print("postprocess segments 合格")
