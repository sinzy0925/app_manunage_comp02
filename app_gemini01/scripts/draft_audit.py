"""要約ドラフトの機械的監査（Pass2 前の issue 検出）。"""

from __future__ import annotations

import re
from typing import Any

from must_cover_check import coverage_summary, draft_to_text, is_segment_items_list
from unit_consistency import build_unit_bindings, find_unit_conflicts

# postprocess_draft と同等の英語断片検出
ENGLISH_FRAGMENT_RE = re.compile(
    r"(?<=[\u3040-\u30ff\u4e00-\u9fff])(?:\s+(?:of|the|and|or|in|on|at|to|for|with|by)\s*)(?=[\u3040-\u30ff\u4e00-\u9fff、。]|$)",
    re.IGNORECASE,
)
DIGIT_OF_RE = re.compile(r"\d+\s+of\s+", re.IGNORECASE)
STANDALONE_EN_WORD_RE = re.compile(
    r"(?<=[\u3040-\u30ff\u4e00-\u9fff、])\s+(?:of|the|and|or)\s*(?=[\u3040-\u30ff\u4e00-\u9fff]|$)",
    re.IGNORECASE,
)

DATE_MERGE_RE = re.compile(
    r"2024年4月2日.{0,80}1月2日|1月2日.{0,80}2024年4月2日"
)
UNCERTAIN_YEAR_FILL_RE = re.compile(
    r"\d{4}年.{0,12}(?:設立|創業|誕生|に設立|に創業)"
)
COMPARISON_CLAIM_RE = re.compile(
    r"(?:を超える|凌駕|倍以上|上回る|下回る|劣る|超えて)"
)


def _iter_bullets(draft: dict) -> list[tuple[str, int | None, str]]:
    """(field, segment_index, bullet_text) の列。"""
    items: list[tuple[str, int | None, str]] = []
    for field in ("conclusion", "chapter_summary"):
        value = draft.get(field)
        if isinstance(value, str) and value.strip():
            for line in value.splitlines():
                text = line.strip().lstrip("-").strip()
                if text:
                    items.append((field, None, text))

    segments = draft.get("segment_summaries")
    if isinstance(segments, str):
        current_idx: int | None = None
        for line in segments.splitlines():
            header = re.match(r"---\s*セグメント(\d+)", line)
            if header:
                current_idx = int(header.group(1))
                continue
            text = line.strip().lstrip("-").strip()
            if text:
                items.append(("segment_summaries", current_idx, text))
    elif is_segment_items_list(segments):
        for item in segments:
            idx = int(item.get("index", 0))
            for bullet in item.get("bullets", []):
                text = str(bullet).strip().lstrip("-").strip()
                if text:
                    items.append(("segment_summaries", idx, text))
    return items


def find_english_fragments(draft: dict) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for field, seg_idx, text in _iter_bullets(draft):
        for pattern, label in (
            (DIGIT_OF_RE, "digit_of"),
            (ENGLISH_FRAGMENT_RE, "english_fragment"),
            (STANDALONE_EN_WORD_RE, "standalone_en"),
        ):
            if pattern.search(text):
                issues.append(
                    {
                        "type": label,
                        "field": field,
                        "segment": str(seg_idx) if seg_idx is not None else "",
                        "excerpt": text[:120],
                    }
                )
                break
    return issues


def find_unit_conflicts_in_draft(bundle: dict, draft: dict) -> list[dict[str, str]]:
    bindings = build_unit_bindings(bundle.get("numeric_facts", []))
    if not bindings:
        return []
    text = draft_to_text(draft)
    return find_unit_conflicts(text, bindings)


def find_uncertain_violations(bundle: dict, draft: dict) -> list[dict[str, str]]:
    """uncertain_spans に該当する箇所へ年号を補完した記述を検出。"""
    issues: list[dict[str, str]] = []
    uncertain_notes = {str(s.get("note", "")) for s in bundle.get("uncertain_spans", [])}
    has_uncertain_year = any("年号" in n or "設立年" in n or "年数" in n for n in uncertain_notes)
    if not has_uncertain_year:
        return issues

    for field, seg_idx, text in _iter_bullets(draft):
        if UNCERTAIN_YEAR_FILL_RE.search(text):
            issues.append(
                {
                    "type": "uncertain_year_fill",
                    "field": field,
                    "segment": str(seg_idx) if seg_idx is not None else "",
                    "excerpt": text[:120],
                    "note": "字幕で欠落した年号を補完している可能性",
                }
            )
    return issues


def find_date_merge_issues(bundle: dict, draft: dict) -> list[dict[str, str]]:
    """別イベントの日付を1文に結合した記述を検出。"""
    issues: list[dict[str, str]] = []
    hints = bundle.get("date_hints", [])
    if not hints:
        return issues

    for field, seg_idx, text in _iter_bullets(draft):
        if DATE_MERGE_RE.search(text):
            issues.append(
                {
                    "type": "date_merge",
                    "field": field,
                    "segment": str(seg_idx) if seg_idx is not None else "",
                    "excerpt": text[:160],
                    "note": "2024年4月2日（地点導入）と1月2日（攻撃）は別。同一文に結合しない",
                }
            )
        elif seg_idx is not None:
            for hint in hints:
                if int(hint.get("segment", -1)) != seg_idx:
                    continue
                full_dates = hint.get("full_dates", [])
                partial_dates = hint.get("partial_dates", [])
                has_full = any(d in text for d in full_dates)
                has_partial = any(d in text for d in partial_dates)
                if has_full and has_partial and re.search(r"攻撃|朝|6時", text):
                    issues.append(
                        {
                            "type": "date_merge",
                            "field": field,
                            "segment": str(seg_idx),
                            "excerpt": text[:160],
                            "note": hint.get("rule", "別日付の混同"),
                        }
                    )
                    break
    return issues


def _subtitle_blob(bundle: dict) -> str:
    return "\n".join(str(seg.get("text", "")) for seg in bundle.get("segments", []))


def find_unsupported_comparisons(bundle: dict, draft: dict) -> list[dict[str, str]]:
    """字幕にない比較・優位主張を章立てから検出。"""
    issues: list[dict[str, str]] = []
    subtitle = _subtitle_blob(bundle)
    chapter = str(draft.get("chapter_summary", ""))
    if not chapter:
        return issues

    for line in chapter.splitlines():
        text = line.strip().lstrip("-").strip()
        if not text or not COMPARISON_CLAIM_RE.search(text):
            continue
        # 比較フレーズの主要語が字幕に無ければ unsupported
        tokens = [t for t in re.split(r"[、。.\s]+", text) if len(t) >= 4]
        if tokens and not any(t in subtitle for t in tokens[:3]):
            issues.append(
                {
                    "type": "unsupported_comparison",
                    "field": "chapter_summary",
                    "segment": "",
                    "excerpt": text[:120],
                    "note": "字幕・numeric_facts に根拠のない比較表現",
                }
            )
    return issues


def audit_draft(bundle: dict, draft: dict) -> dict[str, Any]:
    """Pass2 に渡す機械検出 issue 一覧。"""
    return {
        "unit_conflicts": find_unit_conflicts_in_draft(bundle, draft),
        "english_fragments": find_english_fragments(draft),
        "uncertain_violations": find_uncertain_violations(bundle, draft),
        "date_merge_issues": find_date_merge_issues(bundle, draft),
        "unsupported_comparisons": find_unsupported_comparisons(bundle, draft),
        "coverage": coverage_summary(bundle, draft),
    }


def score_draft(bundle: dict, draft: dict) -> float:
    """Pass1 複数試行の機械採点（高いほど良い）。"""
    audit = audit_draft(bundle, draft)
    cov = audit["coverage"]
    score = float(cov.get("ratio", 0)) * 100.0
    score -= len(audit["unit_conflicts"]) * 15
    score -= len(audit["english_fragments"]) * 10
    score -= len(audit["uncertain_violations"]) * 12
    score -= len(audit["date_merge_issues"]) * 20
    score -= len(audit["unsupported_comparisons"]) * 8
    score -= int(cov.get("missing_count", 0)) * 5
    return score
