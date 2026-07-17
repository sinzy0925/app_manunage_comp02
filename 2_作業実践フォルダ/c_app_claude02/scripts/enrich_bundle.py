#!/usr/bin/env python3
"""ai_bundle に要約補助データ（章ヒント・固有名詞・数値・不明箇所）を付与する。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import JIMaku_DIR, configure_stdout_utf8

OUTLINE_PATTERNS = [
    (re.compile(r"存在し(?:ちゃ|ては)いけない武器"), "存在しないはずの武器"),
    (re.compile(r"裏口"), "裏口"),
    (re.compile(r"ピンク色の(?:シールド|盾)"), "ピンク色の盾"),
    (re.compile(r"(?:全てを|すべてを)動かす頭脳"), "頭脳"),
]

KATAKANA_NAME_RE = re.compile(r"[ァ-ヴー]{3,}")
LATIN_NAME_RE = re.compile(r"\b[A-Z][A-Za-z0-9\-]{2,}\b")
NUMBER_FACT_RE = re.compile(
    r"(.{0,28})"
    r"("
    r"\d{4}年|"
    r"\d{1,2}月(?:\d{1,2}日)?|"
    r"\d{1,4}(?:[,.]\d+)?(?:%|km|m|発|人|台|両|機|個|件|回|ドル|万)?"
    r")"
    r"(.{0,28})"
)

UNIT_OR_SCALE_RE = re.compile(
    r"(?:%|km|m|発|人|台|両|機|個|件|回|ドル|万|億|年|月|日|時間)"
)
DATE_LIKE_RE = re.compile(r"(?:\d{4}年|\d{1,2}月)")
BARE_SMALL_INT_RE = re.compile(r"^\d{1,2}$")

ENTITY_STOP = {
    "ドローン",
    "ミサイル",
    "ウクライナ",
    "ロシア",
    "アメリカ",
    "ヨーロッパ",
    "カメラ",
    "マニュアル",
    "コメント",
    "ポイント",
    "システム",
    "バージョン",
    "プロジェクト",
    "マシン",
    "ステップ",
    "ターゲット",
    "バッテリー",
    "トラック",
    "ゾーン",
    "エンジン",
    "パイロット",
    "チャンネル",
    "チーム",
    "データ",
    "ネットワーク",
    "シンプル",
    "プレッシャー",
    "コントロール",
    "パトロール",
    "ミッション",
    "リアルタイム",
    "フィクション",
    "テクノロジー",
    "クリエイティブ",
    "テスト",
    "タイプ",
    "サイン",
    "マーキング",
    "ルーツ",
    "ルート",
    "タンク",
    "ライン",
    "ライセンス",
    "ホワイトハウス",
    "メディア",
    "ジョーク",
    "マップ",
    "グループ",
    "センター",
    "ハンマー",
    "バタン",
    "ブロック",
    "パートナー",
    "タイヤ",
    "コロラド",
    "キエフ",
    "エリア",
    "トック",
    "スクーター",
    "ウルトラライト",
    "ベース",
    "マイナー",
    "プログラム",
    "アナリスト",
    "バラバラ",
    "スイスチーズ",
    "ドクトリン",
    "ルール",
    "ミニドキュメンタリー",
    "ピンク",
    "シールド",
    "シアリオ",
}

UNCERTAIN_PATTERNS = [
    (re.compile(r"は年に"), "年号・数値が字幕で欠落"),
    (re.compile(r"年前には"), "年数が字幕で欠落"),
    (re.compile(r"時刻の"), "固有名詞の誤変換の可能性"),
    (re.compile(r"番意外"), "数値の誤変換の可能性"),
    (re.compile(r"年に誕生"), "設立年が字幕で欠落"),
]

INSTRUCTIONS = """以下の字幕テキストを要約してください。
出力は glossary → conclusion → chapter_summary → segment_summaries の順で考え、JSON では conclusion / chapter_summary / segment_summaries を返してください。
一発で詳細要約する。再要約前提にしない。
本編事実は抜けなし。簡潔化は宣伝・チャンネル登録・おまけトークのみ。章とセグメントの全文重複で厚くしない。

【役割分担（重複禁止）】
- chapter_summary: テーマの因果・対比・意味付け。数値は章の論を支える最小限にとどめる
- segment_summaries: 時系列の事実・日付・距離・金額の主戦場（must_cover の置き場はこちら優先）
- 同一エピソード・同一数値を章とセグメントの両方にフル再現しない。must_cover はどちらか一方に置けばよい（両方に書いてはならない）

【厚みノルマ（必須・下限）】
- conclusion: 箇条書き 3〜5点。動画の主張・主要メカニズム名を漏らさず書く
- chapter_summary: 導入（あれば）＋ outline_hints 各章 ＋ 締め。各 ■ 見出しの下に箇条書き 4〜7本
- segment_summaries: 各セグメントを箇条書き 5〜8本（1段落の要約文だけで終わらせない）
- must_cover（あれば）と高信号の numeric_facts（日付・距離・金額・人数・発数・％など）は、章かセグメントのどちらかにほぼすべて織り込む（目安8割以上）

【厳守】
- 事実は字幕テキストと enrichment（outline_hints / entities_by_segment / numeric_facts / must_cover）に基づくこと
- 字幕にない年号・数値・固有名詞は推測して書かない（uncertain_spans は「不明」または省略）
- 別の組織・製品・人物の属性を混同しない（entities_by_segment を参照）
- 動画内で示された章立て（outline_hints）があれば chapter_summary はそれに従う
- chapter_summary はテーマ別（■ 見出し）、segment_summaries は時刻順の事実要約
- 自動字幕の重複・[音楽]・ノイズは無視
- 宣伝・チャンネル登録は最終セグメントのみ簡潔化
- 数値・固有名詞は原文表記を優先し、英日混在表記を作らない
- segment_summaries のセグメント数は入力と同じ"""


def _unique_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_outline_hints(text: str) -> list[str]:
    hints: list[str] = []
    for pattern, label in OUTLINE_PATTERNS:
        if pattern.search(text):
            hints.append(label)
    return _unique_preserve(hints)


def extract_entities(text: str, limit: int = 20) -> list[str]:
    names = KATAKANA_NAME_RE.findall(text) + LATIN_NAME_RE.findall(text)
    filtered: list[str] = []
    for name in names:
        if name in ENTITY_STOP or len(name) < 3:
            continue
        filtered.append(name)
    return _unique_preserve(filtered)[:limit]


def _fact_signal_score(value: str, context: str) -> int:
    blob = f"{value} {context}"
    # 「4月2日」から剥がれた "2" などは高信号扱いにしない
    if BARE_SMALL_INT_RE.fullmatch(value) and (
        re.search(rf"月{re.escape(value)}日?", context)
        or re.search(rf"{re.escape(value)}日", context)
    ):
        return 0
    score = 0
    if UNIT_OR_SCALE_RE.search(value):
        score += 6
    elif UNIT_OR_SCALE_RE.search(context):
        score += 3
    if DATE_LIKE_RE.search(value):
        score += 5
    elif DATE_LIKE_RE.search(context):
        score += 2
    if re.search(r"\d{3,}", value):
        score += 2
    if BARE_SMALL_INT_RE.fullmatch(value) and not UNIT_OR_SCALE_RE.search(blob):
        score -= 4
    if re.search(r"(設立|創業|誕生|射程|航続|時速|生産|損失|在庫|ドル|km|発|人)", context):
        score += 2
    return score


def extract_numeric_facts(text: str, segment_index: int, limit: int = 20) -> list[dict]:
    facts: list[dict] = []
    seen_ctx: set[str] = set()
    for match in NUMBER_FACT_RE.finditer(text):
        before, value, after = match.groups()
        context = (before + value + after).strip()
        if len(context) < 6:
            continue
        score = _fact_signal_score(value, context)
        if score < 1:
            continue
        key = context[:60].casefold()
        if key in seen_ctx:
            continue
        seen_ctx.add(key)
        facts.append(
            {
                "segment": segment_index,
                "value": value,
                "context": context[:80],
                "score": score,
            }
        )
    facts.sort(key=lambda f: int(f.get("score", 0)), reverse=True)
    return facts[:limit]


def extract_uncertain_spans(text: str, segment_index: int) -> list[dict]:
    spans: list[dict] = []
    for pattern, reason in UNCERTAIN_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            spans.append(
                {
                    "segment": segment_index,
                    "raw": text[start:end],
                    "note": reason,
                }
            )
    return spans


def build_must_cover(numeric_facts: list[dict], limit: int = 20) -> list[dict]:
    """一発要約で落とされやすい高信号数値を優先リスト化。"""
    ranked = sorted(numeric_facts, key=lambda f: int(f.get("score", 0)), reverse=True)
    out: list[dict] = []
    seen: set[str] = set()
    for fact in ranked:
        key = f"{fact.get('value')}|{str(fact.get('context', ''))[:40]}".casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "segment": fact.get("segment"),
                "value": fact.get("value"),
                "context": fact.get("context"),
            }
        )
        if len(out) >= limit:
            break
    return out


def enrich_bundle(bundle: dict) -> dict:
    enriched = dict(bundle)
    all_text = "\n".join(str(seg.get("text", "")) for seg in bundle.get("segments", []))

    outline_hints = extract_outline_hints(all_text)
    entities_by_segment: list[dict] = []
    numeric_facts: list[dict] = []
    uncertain_spans: list[dict] = []

    for seg in bundle.get("segments", []):
        index = int(seg.get("index", 0))
        text = str(seg.get("text", ""))
        entities_by_segment.append(
            {
                "segment": index,
                "label": seg.get("label", ""),
                "names": extract_entities(text),
            }
        )
        numeric_facts.extend(extract_numeric_facts(text, index))
        uncertain_spans.extend(extract_uncertain_spans(text, index))

    numeric_facts.sort(key=lambda f: int(f.get("score", 0)), reverse=True)
    numeric_facts = numeric_facts[:80]
    must_cover = build_must_cover(numeric_facts, limit=20)

    # 下流 JSON では score は任意。表示ノイズを減らすため外してもよいが照合用に残す。
    enriched["outline_hints"] = outline_hints
    enriched["entities_by_segment"] = entities_by_segment
    enriched["numeric_facts"] = numeric_facts
    enriched["must_cover"] = must_cover
    enriched["uncertain_spans"] = uncertain_spans[:30]
    enriched["instructions"] = INSTRUCTIONS
    enriched["enrichment_version"] = 2
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser(description="AI バンドルに要約補助データを付与")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--bundle", help="入力バンドル JSON")
    parser.add_argument("--in-place", action="store_true", help="元ファイルを上書き")
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    bundle_path = Path(args.bundle) if args.bundle else base / f"{args.video_id}_ai_bundle.json"
    if not bundle_path.exists():
        print(f"バンドルが見つかりません: {bundle_path}", file=sys.stderr)
        return 1

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    enriched = enrich_bundle(bundle)
    out_path = bundle_path if args.in_place else bundle_path
    out_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "bundle_path": str(out_path),
                "outline_hints": enriched.get("outline_hints", []),
                "must_cover_count": len(enriched.get("must_cover", [])),
                "uncertain_count": len(enriched.get("uncertain_spans", [])),
                "enrichment_version": enriched.get("enrichment_version"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
