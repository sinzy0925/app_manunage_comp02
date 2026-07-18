"""Gemini 要約用プロンプト構築（SKILL 相当）。"""

from __future__ import annotations

import json
from typing import Any

# おおよそ 1M トークン ≒ 300万文字の安全域。超過時のみ末尾セグメントを警告付きで省略。
MAX_INPUT_CHARS = 2_500_000

SYSTEM_INSTRUCTION = """あなたは YouTube 動画字幕の高精度要約アシスタントです。
入力 JSON はクリーニング済み字幕と enrichment（outline_hints, entities_by_segment, numeric_facts, must_cover, date_hints, uncertain_spans, instructions）です。

【出力】
JSON のみ返す。マークダウンコードブロックは使わない。
必須キー: conclusion, chapter_summary, segment_summaries

【要約構成】
1. conclusion — 箇条書き 3〜5 点（全体主張＋主要メカニズム名）
2. chapter_summary — ■ 見出し付き章立て。outline_hints があれば従う。各 ■ の下に箇条書き 4〜7 本。因果・対比中心。数値は最小限
3. segment_summaries — 配列 [{index, bullets[]}]。index は segments[].index（0始まり）。各 bullets は 5〜8 本の箇条書き（先頭に - は不要）。時系列ファクト中心

【役割分担（重複禁止）】
- chapter_summary: テーマの因果・対比・意味付け
- segment_summaries: 日付・距離・金額・作戦の時系列事実（must_cover の置き場はこちら優先）
- 同一エピソード・同一数値を章とセグメントの両方にフル再現しない
- must_cover は章かセグメントのどちらか一方に置く（両方に書いてはならない）

【厳守】
- 字幕テキストと enrichment のみに基づく。推測禁止
- uncertain_spans の箇所は年号・数値を補完しない（省略または「不明」）
- date_hints があるセグメントでは、完全日付（YYYY年M月D日）と月日のみの日付は別イベント。同一箇条書きに結合しない
- chapter_summary に字幕・numeric_facts にない比較（〜を超える、凌駕、倍以上など）は書かない
- 別組織・製品・人物の属性を混同しない（entities_by_segment を参照。例: エアロドローム ≠ ファイアポイント）
- must_cover と高信号 numeric_facts は章かセグメントにほぼすべて織り込む（目安 8 割以上）
- 数値・固有名詞は原文表記を優先。英日混在表記を作らない
- numeric_facts の value と単位（km/kg/体/両/人/発/台）はそのまま使う。同じ数値に別単位を付けない
- 自動字幕の重複・[音楽]・ノイズは無視
- 宣伝・チャンネル登録・おまけトークは最終セグメントのみ簡潔化。本編は抜けなし
- メタ記述（「字幕によると」「セグメント05と連続」等）を入れない
- segment_summaries の配列長は segment_count と一致。index は 0 から連番（01始まり禁止）

【手順】
1. outline_hints・must_cover・date_hints・entities_by_segment・numeric_facts を把握
2. segments[] を順に読み、各セグメントの時系列ファクトを整理
3. uncertain_spans を確認し推測しない
4. conclusion → chapter_summary → segment_summaries の順で作成
5. 保存前: 配列長=segment_count、must_cover カバー、章/セグメント重複なし、数値単位照合を確認

instructions フィールドがあれば、厚みノルマの正本として最優先で従う。"""

VERIFY_SYSTEM_INSTRUCTION = """あなたは YouTube 字幕要約の事実監査アシスタントです。
第1パスで生成された要約ドラフトを、reference（numeric_facts / must_cover / date_hints / uncertain_spans / detected_issues）と照合し、誤りのみ修正した JSON を返します。

【修正対象（detected_issues を最優先）】
- detected_issues.unit_conflicts: 単位を numeric_facts に合わせて修正
- detected_issues.english_fragments: 英語断片（of, the, 12 of 等）を除去または日本語に直す
- detected_issues.uncertain_violations: 字幕欠落年号の補完を削除し「設立年は不明」等に置換
- detected_issues.date_merge_issues: 別イベントの日付結合を分割（2024年4月2日＝地点導入、1月2日＝攻撃など）
- detected_issues.unsupported_comparisons: 字幕に根拠のない比較文を削除
- 数値・単位の誤変換（numeric_facts / unit_bindings の number+unit を優先）
- uncertain_spans への年号・数値の補完
- must_cover の未記載（章かセグメントの bullets に追加）
- missing_must_cover に列挙された項目は最優先で該当 segment の bullets に追加
- 組織・製品・人物の混同

【変更禁止】
- 既に正しい記述・章立て構成・厚み
- 宣伝の簡潔化方針

【出力形式】
conclusion（文字列）, chapter_summary（文字列）, segment_summaries（[{index, bullets[]}] 配列）
index は segments[].index（0始まり）。JSON のみ。マークダウンコードブロック禁止。"""

PAYLOAD_KEYS = (
    "video_id",
    "url",
    "metadata",
    "outline_hints",
    "date_hints",
    "entities_by_segment",
    "numeric_facts",
    "must_cover",
    "uncertain_spans",
    "segment_count",
    "segment_minutes",
    "segments",
    "instructions",
)


def _segment_char_total(segments: list[dict]) -> int:
    return sum(len(str(seg.get("text", ""))) for seg in segments)


def build_user_payload_dict(bundle: dict) -> dict[str, Any]:
    """bundle から Gemini input 用 dict を構築。"""
    segments = list(bundle.get("segments", []))
    payload: dict[str, Any] = {
        "video_id": bundle.get("video_id", ""),
        "url": bundle.get("url", ""),
        "metadata": bundle.get("metadata", {}),
        "outline_hints": bundle.get("outline_hints", []),
        "date_hints": bundle.get("date_hints", []),
        "entities_by_segment": bundle.get("entities_by_segment", []),
        "numeric_facts": bundle.get("numeric_facts", []),
        "must_cover": bundle.get("must_cover", []),
        "uncertain_spans": bundle.get("uncertain_spans", []),
        "segment_count": bundle.get("segment_count", len(segments)),
        "segment_minutes": bundle.get("segment_minutes", 10),
        "segments": segments,
        "instructions": bundle.get("instructions", ""),
    }

    serialized = json.dumps(payload, ensure_ascii=False)
    if len(serialized) > MAX_INPUT_CHARS:
        payload["_warnings"] = [
            f"入力が長すぎます（{len(serialized)} 文字）。末尾セグメントを省略しました。"
        ]
        while segments and len(json.dumps(payload, ensure_ascii=False)) > MAX_INPUT_CHARS:
            segments.pop()
        payload["segments"] = segments

    return payload


def build_verify_payload(bundle: dict, draft: dict) -> dict[str, Any]:
    """Pass2 検証用ペイロード。"""
    from draft_audit import audit_draft
    from must_cover_check import find_missing_must_cover
    from unit_consistency import build_unit_bindings

    segments = draft.get("segment_summaries", [])
    missing = find_missing_must_cover(bundle, draft)
    detected = audit_draft(bundle, draft)
    return {
        "draft": {
            "conclusion": draft.get("conclusion", ""),
            "chapter_summary": draft.get("chapter_summary", ""),
            "segment_summaries": segments,
        },
        "reference": {
            "numeric_facts": bundle.get("numeric_facts", [])[:50],
            "unit_bindings": build_unit_bindings(bundle.get("numeric_facts", []))[:40],
            "must_cover": bundle.get("must_cover", []),
            "date_hints": bundle.get("date_hints", []),
            "missing_must_cover": missing,
            "uncertain_spans": bundle.get("uncertain_spans", []),
            "detected_issues": {
                "unit_conflicts": detected.get("unit_conflicts", [])[:20],
                "english_fragments": detected.get("english_fragments", [])[:20],
                "uncertain_violations": detected.get("uncertain_violations", [])[:20],
                "date_merge_issues": detected.get("date_merge_issues", [])[:20],
                "unsupported_comparisons": detected.get("unsupported_comparisons", [])[:20],
            },
            "segment_indexes": [
                {"index": int(seg.get("index", i)), "label": seg.get("label", "")}
                for i, seg in enumerate(bundle.get("segments", []))
            ],
        },
    }


def build_user_payload(bundle: dict) -> str:
    """Gemini interactions の input 用文字列（JSON）。"""
    return json.dumps(build_user_payload_dict(bundle), ensure_ascii=False, indent=2)


def validate_payload(payload: dict) -> list[str]:
    """payload の必須フィールド欠落を返す。"""
    errors: list[str] = []
    for key in PAYLOAD_KEYS:
        if key not in payload:
            errors.append(f"missing: {key}")
    expected = int(payload.get("segment_count", 0))
    actual = len(payload.get("segments", []))
    if expected and actual != expected:
        errors.append(f"segment mismatch: expected={expected}, actual={actual}")
    for seg in payload.get("segments", []):
        if not str(seg.get("text", "")).strip():
            errors.append(f"empty segment text: index={seg.get('index')}")
    return errors
