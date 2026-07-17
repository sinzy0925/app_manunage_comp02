"""numeric_facts に基づく汎用単位整合チェック（動画固有辞書なし）。"""

from __future__ import annotations

import re
from typing import Any

# 同じ数値に付きうる混同単位（動画非依存）
UNIT_CONFLICTS: dict[str, set[str]] = {
    "km": {"kg"},
    "kg": {"km"},
    "体": {"両", "台"},
    "両": {"体"},
    "人": {"発"},
    "発": {"人"},
}

NUM_UNIT_IN_TEXT_RE = re.compile(
    r"(?<!\d)(\d{1,4}(?:[,.]\d+)?)\s*(km|kg|m|体|両|人|発|台|%)",
    re.IGNORECASE,
)

NUM_WITH_UNIT_RE = re.compile(
    r"(\d{1,4}(?:[,.]\d+)?)\s*(km|kg|m|体|両|人|発|台|%)",
    re.IGNORECASE,
)
FULL_DATE_RE = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")


def extract_number_unit(value: str, context: str) -> tuple[str | None, str | None]:
    """fact の value / context から数値と単位を抽出。"""
    value = str(value).strip()
    context = str(context)

    match = NUM_WITH_UNIT_RE.search(value)
    if match:
        return match.group(1), match.group(2).lower()

    if re.fullmatch(r"\d{1,4}(?:[,.]\d+)?", value):
        near = re.compile(rf"{re.escape(value)}\s*(km|kg|m|体|両|人|発|台|%)", re.IGNORECASE)
        near_match = near.search(context)
        if near_match:
            return value, near_match.group(1).lower()

    ctx_match = NUM_WITH_UNIT_RE.search(context)
    if ctx_match:
        return ctx_match.group(1), ctx_match.group(2).lower()

    return None, None


def normalize_numeric_fact(fact: dict[str, Any]) -> dict[str, Any]:
    """value に単位を付与し number / unit フィールドを付与。"""
    result = dict(fact)
    value = str(result.get("value", "")).strip()
    if result.get("kind") in ("date", "range") or FULL_DATE_RE.fullmatch(value):
        if result.get("kind") == "range":
            range_match = re.match(r"(\d{1,4})(km)", value, re.IGNORECASE)
            if range_match:
                result["number"] = range_match.group(1)
                result["unit"] = range_match.group(2).lower()
        return result
    context = str(result.get("context", ""))
    number, unit = extract_number_unit(value, context)
    if number and unit:
        result["number"] = number
        result["unit"] = unit
        if unit.lower() not in value.lower():
            result["value"] = f"{number}{unit}"
    return result


def build_unit_bindings(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """numeric_facts から (number, unit) ペアの照合リストを構築。"""
    bindings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in facts:
        fact = normalize_numeric_fact(raw)
        number = fact.get("number")
        unit = fact.get("unit")
        if not number or not unit:
            continue
        key = (str(number), str(unit).lower())
        if key in seen:
            continue
        seen.add(key)
        bindings.append(
            {
                "number": str(number),
                "unit": str(unit).lower(),
                "value": fact.get("value", f"{number}{unit}"),
                "context": fact.get("context", ""),
                "segment": fact.get("segment"),
                "score": int(fact.get("score", 0)),
            }
        )
    return bindings


def _binding_candidates(number: str, found_unit: str, bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        b
        for b in bindings
        if b["number"] == number and _conflicts(str(b["unit"]), found_unit)
    ]


def _conflicts(source_unit: str, found_unit: str) -> bool:
    source = source_unit.lower()
    found = found_unit.lower()
    if source == found:
        return False
    return found in UNIT_CONFLICTS.get(source, set())


def find_unit_conflicts(text: str, bindings: list[dict[str, Any]]) -> list[dict[str, str]]:
    """要約文とバインディングの単位衝突を検出。"""
    conflicts: list[dict[str, str]] = []
    for match in NUM_UNIT_IN_TEXT_RE.finditer(text):
        number = match.group(1)
        found_unit = match.group(2).lower()
        candidates = _binding_candidates(number, found_unit, bindings)
        if not candidates:
            continue
        binding = max(candidates, key=lambda b: int(b.get("score", 0)))
        conflicts.append(
            {
                "number": number,
                "found_unit": found_unit,
                "correct_unit": str(binding["unit"]),
                "correct_value": str(binding.get("value", f"{number}{binding['unit']}")),
                "context": str(binding.get("context", ""))[:80],
            }
        )
    return conflicts


def _phrase_for_binding(binding: dict[str, Any]) -> str:
    number = binding["number"]
    unit = binding["unit"]
    context = str(binding.get("context", ""))
    if unit == "km" and re.search(r"詰める|射程|飛行|航続", context):
        return f"射程{number}{unit}"
    return str(binding.get("value", f"{number}{unit}"))


def fix_unit_conflicts_in_text(text: str, bindings: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    """衝突単位をバインディングに基づき置換。"""
    fixed = text
    applied: list[dict[str, str]] = []

    for match in list(NUM_UNIT_IN_TEXT_RE.finditer(text)):
        number = match.group(1)
        found_unit = match.group(2).lower()
        candidates = _binding_candidates(number, found_unit, bindings)
        if not candidates:
            continue
        binding = max(candidates, key=lambda b: int(b.get("score", 0)))

        replacement = _phrase_for_binding(binding)
        pattern = re.compile(
            rf"(?<!\d){re.escape(number)}\s*{re.escape(found_unit)}",
            re.IGNORECASE,
        )
        if pattern.search(fixed):
            fixed = pattern.sub(replacement, fixed, count=1)
            applied.append(
                {
                    "number": number,
                    "from": f"{number}{found_unit}",
                    "to": replacement,
                }
            )
    return fixed, applied


def apply_unit_consistency(draft: dict, bundle: dict) -> dict:
    """draft 全文に単位整合を適用。"""
    bindings = build_unit_bindings(bundle.get("numeric_facts", []))
    if not bindings:
        return draft

    result = dict(draft)
    all_fixes: list[dict[str, str]] = []
    for key in ("conclusion", "chapter_summary", "segment_summaries"):
        value = result.get(key)
        if not isinstance(value, str) or not value:
            continue
        fixed, fixes = fix_unit_conflicts_in_text(value, bindings)
        if fixes:
            result[key] = fixed
            all_fixes.extend(fixes)

    if all_fixes:
        result.setdefault("_unit_fixes", all_fixes)
    return result
