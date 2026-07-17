"""must_cover の機械的カバレッジチェック（辞書置換なし）。"""

from __future__ import annotations

import re
from typing import Any

FULL_DATE_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")


def draft_to_text(draft: dict) -> str:
    """要約ドラフト全文を検索用に連結。"""
    parts: list[str] = []
    for key in ("conclusion", "chapter_summary"):
        value = draft.get(key)
        if isinstance(value, str):
            parts.append(value)

    segments = draft.get("segment_summaries")
    if isinstance(segments, str):
        parts.append(segments)
    elif is_segment_items_list(segments):
        for item in segments:
            parts.append(" ".join(str(b) for b in item.get("bullets", [])))

    return "\n".join(parts)


def is_segment_items_list(segments: object) -> bool:
    if not isinstance(segments, list) or not segments:
        return False
    first = segments[0]
    return isinstance(first, dict) and "bullets" in first


def _normalize_digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _date_covered(value: str, text: str) -> bool:
    if value in text:
        return True
    # 2024年4月2日 vs 2024年04月02日 などのゆれ
    if FULL_DATE_RE.fullmatch(value.strip()):
        digits = _normalize_digits(value)
        if digits and digits in _normalize_digits(text):
            return True
    return False


def is_fact_covered(item: dict[str, Any], text: str) -> bool:
    value = str(item.get("value", "")).strip()
    if not value:
        return True
    if FULL_DATE_RE.search(value):
        return _date_covered(value, text)

    context = str(item.get("context", "") or item.get("quote", ""))
    # 数値+単位は value を優先
    if value in text:
        return True
    # 817体など: 数値部分だけでも可
    number_match = re.match(r"(\d{3,4})", value)
    if number_match and number_match.group(1) in text:
        unit = re.sub(r"[\d,.]", "", value)
        if not unit or unit in text:
            return True
    # 短い value は context のキーフレーズで判定
    if len(value) <= 3 and context:
        tokens = [t for t in re.split(r"[、。.\s]+", context) if len(t) >= 4]
        if tokens and any(token in text for token in tokens[:2]):
            return True
    return False


def find_missing_must_cover(bundle: dict, draft: dict) -> list[dict[str, Any]]:
    """must_cover のうち要約本文に未出現の項目。"""
    text = draft_to_text(draft)
    missing: list[dict[str, Any]] = []
    for item in bundle.get("must_cover", []):
        if not is_fact_covered(item, text):
            missing.append(
                {
                    "id": item.get("id"),
                    "segment": item.get("segment"),
                    "value": item.get("value"),
                    "context": item.get("context") or item.get("quote", ""),
                }
            )
    return missing


def coverage_summary(bundle: dict, draft: dict) -> dict[str, Any]:
    must = bundle.get("must_cover", [])
    missing = find_missing_must_cover(bundle, draft)
    total = len(must)
    covered = total - len(missing)
    ratio = covered / total if total else 1.0
    return {
        "total": total,
        "covered": covered,
        "missing_count": len(missing),
        "ratio": round(ratio, 3),
        "missing": missing,
    }
