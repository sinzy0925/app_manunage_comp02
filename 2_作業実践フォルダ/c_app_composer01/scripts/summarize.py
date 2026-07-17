#!/usr/bin/env python3
"""OpenAI API で字幕バンドルを要約する（map-reduce 1パス）。

1回のパイプライン実行内で:
  1) セグメントごとに facts + summary を抽出
  2) 統合して conclusion / chapter_summary / segment_summaries を生成
  3) 機械的 postprocess
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import JIMaku_DIR, configure_stdout_utf8
from postprocess_draft import postprocess_draft

SEGMENT_SYSTEM_PROMPT = """あなたはYouTube動画字幕の1セグメント分を分析するアシスタントです。
JSONのみを返してください。マークダウンコードブロックは使わないでください。

出力スキーマ:
{
  "segment_index": 0,
  "facts": [
    {"type": "entity|date|number|event", "text": "事実の短文", "confidence": "high|low"}
  ],
  "summary": "このセグメントの要約（日本語、箇条書き相当の密度で5〜8文。事実・数値を落とさない）"
}

制約:
- 字幕テキストに書かれた事実のみ。推測禁止
- uncertain_spans がある場合は confidence=low とし、欠落数値を補完しない
- 数値・固有名詞は原文に忠実に
- 宣伝・[音楽]は無視
"""

MERGE_SYSTEM_PROMPT = """あなたはYouTube動画の字幕要約を統合するアシスタントです。
JSONのみを返してください。マークダウンコードブロックは使わないでください。

出力スキーマ:
{
  "glossary": {"固有名詞": "短い説明（字幕に基づく）"},
  "conclusion": "全体の結論（日本語、1〜2段落）",
  "chapter_summary": "章立て詳細要約（■ 見出し付き、日本語）",
  "segment_summaries": "各セグメント要約（--- セグメントNN（時刻範囲）--- 形式、日本語）"
}

制約:
- まず glossary で組織・製品・人物を整理してから要約を書く（同一JSON内）
- 別組織の設立年・属性を混同しない
- outline_hints があれば chapter_summary の章構成に反映
- uncertain な事実は書かないか「字幕上不明」とする
- segment_summaries のセグメント数・ラベルは入力と一致
- chapter_summary はテーマの因果・対比、segment_summaries は時系列の事実。同一エピソード・同一数値を両方にフル再現しない
- must_cover は章かセグメントのどちらか一方に置く（両方に書いてはならない）
- 宣伝・チャンネル登録は最終セグメントのみ簡潔化
- 厚み: conclusion は箇条3〜5点、各■は箇条4〜7本、各セグメントは箇条5〜8本
- must_cover / 高信号 numeric_facts は章かセグメントにほぼすべて織り込む
"""


def _openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai パッケージが必要です: pip install openai") from exc

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("環境変数 OPENAI_API_KEY が設定されていません")
    return OpenAI(api_key=api_key)


def _chat_json(client, *, model: str, system: str, user: str, temperature: float = 0.15) -> dict:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def _segment_context(bundle: dict, seg: dict) -> dict:
    index = int(seg["index"])
    entities = next(
        (e for e in bundle.get("entities_by_segment", []) if int(e.get("segment", -1)) == index),
        {},
    )
    uncertain = [
        u
        for u in bundle.get("uncertain_spans", [])
        if int(u.get("segment", -1)) == index
    ]
    numbers = [
        n
        for n in bundle.get("numeric_facts", [])
        if int(n.get("segment", -1)) == index
    ]
    return {
        "segment_index": index,
        "label": seg.get("label", ""),
        "entities": entities.get("names", []),
        "numeric_facts": numbers[:12],
        "uncertain_spans": uncertain,
    }


def build_segment_prompt(bundle: dict, seg: dict) -> str:
    ctx = _segment_context(bundle, seg)
    text = str(seg.get("text", ""))
    if len(text) > 14000:
        text = text[:14000] + "…（以下省略）"
    return "\n".join(
        [
            f"動画タイトル: {bundle.get('metadata', {}).get('title', '')}",
            f"セグメント: {ctx['segment_index']:02d} ({ctx['label']})",
            f"固有名詞候補: {', '.join(ctx['entities']) or 'なし'}",
            f"数値候補: {json.dumps(ctx['numeric_facts'], ensure_ascii=False)}",
            f"不明箇所: {json.dumps(ctx['uncertain_spans'], ensure_ascii=False)}",
            "",
            "字幕テキスト:",
            text,
        ]
    )


def build_merge_prompt(bundle: dict, segment_results: list[dict]) -> str:
    meta = bundle.get("metadata", {})
    segments = bundle.get("segments", [])
    labels = {
        int(seg["index"]): str(seg.get("label", ""))
        for seg in segments
    }
    payload = {
        "video_title": meta.get("title", ""),
        "uploader": meta.get("uploader", ""),
        "url": bundle.get("url", ""),
        "outline_hints": bundle.get("outline_hints", []),
        "uncertain_spans": bundle.get("uncertain_spans", []),
        "segment_count": bundle.get("segment_count", len(segments)),
        "segment_labels": labels,
        "segment_results": segment_results,
        "instructions": bundle.get("instructions", ""),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def summarize_segment(client, bundle: dict, seg: dict, model: str) -> dict:
    result = _chat_json(
        client,
        model=model,
        system=SEGMENT_SYSTEM_PROMPT,
        user=build_segment_prompt(bundle, seg),
    )
    index = int(seg["index"])
    result.setdefault("segment_index", index)
    result.setdefault("label", seg.get("label", ""))
    result.setdefault("facts", [])
    result.setdefault("summary", "")
    return result


def merge_segment_summaries(client, bundle: dict, segment_results: list[dict], model: str) -> dict:
    result = _chat_json(
        client,
        model=model,
        system=MERGE_SYSTEM_PROMPT,
        user=build_merge_prompt(bundle, segment_results),
        temperature=0.2,
    )
    for key in ("conclusion", "chapter_summary", "segment_summaries"):
        if key not in result:
            raise ValueError(f"統合応答に '{key}' が含まれていません")
    result.setdefault("glossary", {})
    return result


def summarize_bundle_map_reduce(bundle: dict, model: str) -> dict:
    client = _openai_client()
    segment_results: list[dict] = []
    for seg in bundle.get("segments", []):
        segment_results.append(summarize_segment(client, bundle, seg, model))

    merged = merge_segment_summaries(client, bundle, segment_results, model)
    merged["_segment_facts"] = segment_results
    return merged


def summarize_bundle(bundle: dict, model: str) -> dict:
    """後方互換エントリポイント。常に map-reduce を使用。"""
    draft = summarize_bundle_map_reduce(bundle, model)
    expected = int(bundle.get("segment_count", 0)) or None
    return postprocess_draft(draft, expected_segments=expected)


def load_bundle(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"バンドルが見つかりません: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="AI で字幕を要約（map-reduce）")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--bundle", help="AI バンドル JSON（省略時は自動生成）")
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--output", help="要約 JSON 出力先")
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    bundle_path = Path(args.bundle) if args.bundle else base / f"{args.video_id}_ai_bundle.json"

    if not bundle_path.exists():
        from load_manifest import build_ai_bundle

        mpath = base / f"{args.video_id}_manifest.json"
        bundle = build_ai_bundle(mpath, base)
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        bundle = load_bundle(bundle_path)

    try:
        summary = summarize_bundle(bundle, args.model)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_path = Path(args.output) if args.output else base / f"{args.video_id}_summary_draft.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"draft_path": str(out_path), "warnings": summary.get("_warnings", [])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
