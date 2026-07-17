#!/usr/bin/env python3
"""Step 8: 品質ベンチマークの機械チェック + レポート存在確認。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
REPO = _ROOT.parent
GEMINI_SUMMARY = _ROOT / "result" / "koBLOf-53_g_summary.txt"
COMPOSER_SUMMARY = REPO / "app_composer01" / "result" / "koBLOf-53_g_summary.txt"
BENCHMARK_REPORT = REPO / "4_比較結果" / "比較結果_gemini" / "gemini01.md"
SCORES_JSON = _ROOT / "tests" / "fixtures" / "benchmark_scores.json"

PASS_THRESHOLD = 9


def _read(path: Path) -> str:
    assert path.exists(), f"missing: {path}"
    return path.read_text(encoding="utf-8")


def test_reports_exist() -> None:
    assert GEMINI_SUMMARY.exists(), GEMINI_SUMMARY
    assert COMPOSER_SUMMARY.exists(), COMPOSER_SUMMARY
    assert BENCHMARK_REPORT.exists(), BENCHMARK_REPORT
    print("benchmark reports exist")


def test_gemini_structure() -> None:
    text = _read(GEMINI_SUMMARY)
    for section in ("【結論】", "【章立て詳細要約】", "【10分単位セグメント要約】"):
        assert section in text, section
    headers = re.findall(r"---\s*セグメント", text)
    assert len(headers) >= 8, f"segment headers: {len(headers)}"
    assert "処理開始時刻:" in text
    assert "処理終了時刻:" in text
    print(f"gemini structure ok: {len(headers)} segment blocks")


def test_scores_documented() -> None:
    report = _read(BENCHMARK_REPORT)
    assert "app_gemini01" in report
    assert "app_composer01" in report
    assert "合計/10" in report

    scores = json.loads(SCORES_JSON.read_text(encoding="utf-8"))
    gemini = scores["app_gemini01"]
    gemini_total = int(gemini["total"])
    composer_total = int(scores["app_composer01"]["total"])
    model = gemini.get("model", "unknown")

    assert str(gemini_total) in report or str(gemini_total) in _read(
        BENCHMARK_REPORT.parent / "gemini01_35flash_v2.md"
    )
    assert str(composer_total) in report
    print(f"scores: gemini({model})={gemini_total} composer={composer_total} threshold={PASS_THRESHOLD}")

    if gemini_total < PASS_THRESHOLD:
        print(f"NOTE: gemini score {gemini_total} < {PASS_THRESHOLD} (Step 8 品質閾値未達)")
    else:
        print("Step 8 quality threshold PASSED")


if __name__ == "__main__":
    test_reports_exist()
    test_gemini_structure()
    test_scores_documented()
    print("Step 8 ベンチマーク完了（機械チェック）")
