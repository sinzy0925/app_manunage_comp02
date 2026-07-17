#!/usr/bin/env python3
"""YouTube字幕取得・要約パイプライン統合 CLI。

標準（IDE 要約）:
  python scripts/run_pipeline.py "URL" --steps fetch,clean,bundle
  → IDE で @youtube-jimaku-summary 要約
  → python scripts/run_pipeline.py --video-id ID --steps render

任意（API 要約）:
  python scripts/run_pipeline.py "URL" --use-api
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    JIMaku_DIR,
    RESULT_DIR,
    configure_stdout_utf8,
    elapsed_sec,
    ensure_dirs,
    format_duration,
    manifest_path,
    now_str,
    update_manifest_processing,
)
from clean_subs import clean_subtitles
from fetch_subs import fetch_subtitles
from load_manifest import build_ai_bundle
from postprocess_draft import postprocess_draft
from render_summary import render_summary

APP_STEPS = ("fetch", "clean", "bundle", "render")
API_STEP = "summarize"


def _video_id_from_json(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("video_id")


def parse_steps(value: str, *, use_api: bool) -> list[str]:
    if value == "all":
        steps = ["fetch", "clean", "bundle"]
        if use_api:
            steps.append(API_STEP)
        steps.append("render")
        return steps
    steps = [s.strip() for s in value.split(",") if s.strip()]
    allowed = set(APP_STEPS) | {API_STEP}
    unknown = set(steps) - allowed
    if unknown:
        raise ValueError(f"不明なステップ: {', '.join(sorted(unknown))}")
    return steps


def _print_ide_handoff(video_id: str, bundle_path: Path, draft_path: Path) -> None:
    if draft_path.exists():
        print()
        print("=" * 60)
        print("要約ドラフトが既にあります — IDE 要約はスキップ可能")
        print("=" * 60)
        print(f"ドラフト: {draft_path}")
        print("レポート生成:")
        print(f'   python scripts/run_pipeline.py --video-id {video_id} --steps render')
        print("=" * 60)
        return

    print()
    print("=" * 60)
    print("次は IDE（エージェント）で要約してください")
    print("=" * 60)
    print(f"1. {bundle_path} のみを読む（manifest / segment_*.txt は読まない）")
    print("2. outline_hints / entities_by_segment / uncertain_spans を参照して要約")
    print("3. jimaku/{video_id}_summary_draft.json に保存")
    print()
    print("Cursor チャット例:")
    print("   @youtube-jimaku-summary")
    print("   jimaku/ の要約前テキストを元に要約して")
    print()
    print("4. レポート生成:")
    print(f'   python scripts/run_pipeline.py --video-id {video_id} --steps render')
    print("=" * 60)


def run_pipeline(
    url: str,
    *,
    lang: str = "ja",
    segment_minutes: int = 10,
    steps: list[str] | None = None,
    jimaku_dir: Path | None = None,
    result_dir: Path | None = None,
    model: str | None = None,
    summary_json: Path | None = None,
    use_api: bool = False,
    video_id: str | None = None,
) -> dict:
    ensure_dirs()
    base = jimaku_dir or JIMaku_DIR
    out_dir = result_dir or RESULT_DIR
    selected = steps or parse_steps("all", use_api=use_api)
    start_time = now_str()

    manifest: dict | None = None
    resolved_id = video_id

    if "fetch" in selected:
        manifest = fetch_subtitles(url, base, lang, segment_minutes)
        resolved_id = manifest["video_id"]
        mpath = manifest_path(resolved_id, base)
        update_manifest_processing(mpath, start_time=start_time)
    else:
        resolved_id = resolved_id or (summary_json and _video_id_from_json(summary_json))
        if not resolved_id and url and "PLACEHOLDER" not in url:
            from fetch_subs import extract_video_id

            resolved_id = extract_video_id(url)
        if not resolved_id:
            raise ValueError("fetch をスキップする場合は --video-id または --summary-json が必要です")
        mpath = manifest_path(resolved_id, base)
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        if not manifest.get("processing", {}).get("start_time"):
            update_manifest_processing(mpath, start_time=start_time)

    mpath = manifest_path(resolved_id, base)
    bundle_path = base / f"{resolved_id}_ai_bundle.json"
    draft_path = base / f"{resolved_id}_summary_draft.json"

    if "clean" in selected:
        clean_subtitles(mpath, base)
        manifest = json.loads(mpath.read_text(encoding="utf-8"))

    bundle: dict | None = None
    if "bundle" in selected:
        bundle = build_ai_bundle(mpath, base)
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    if API_STEP in selected:
        if summary_json:
            draft_path.write_text(summary_json.read_text(encoding="utf-8"), encoding="utf-8")
        elif use_api:
            from summarize import load_bundle, summarize_bundle
            import os

            if bundle is None:
                bundle = load_bundle(bundle_path) if bundle_path.exists() else build_ai_bundle(mpath, base)
            model_name = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            summary = summarize_bundle(bundle, model_name)
            draft_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        elif not draft_path.exists():
            raise RuntimeError(
                f"要約ドラフトがありません: {draft_path}\n"
                "IDE で要約するか、--use-api を付けてください。"
            )

    result_path: Path | None = None
    awaiting_ide = False

    if "render" in selected:
        if not draft_path.exists():
            if use_api or API_STEP in selected:
                raise RuntimeError(
                    f"要約ドラフトがありません: {draft_path}\n"
                    "IDE で要約を作成するか、--use-api を使用してください。"
                )
            if not bundle_path.exists():
                bundle = build_ai_bundle(mpath, base)
                bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            _print_ide_handoff(resolved_id, bundle_path, draft_path)
            awaiting_ide = True
        else:
            if bundle is None and bundle_path.exists():
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            expected = int(bundle.get("segment_count", 0)) if bundle else None
            draft = postprocess_draft(draft, expected_segments=expected or None)
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

            manifest = json.loads(mpath.read_text(encoding="utf-8"))
            start = manifest.get("processing", {}).get("start_time", start_time)
            end_time = now_str()
            update_manifest_processing(mpath, end_time=end_time)
            result_path = render_summary(mpath, draft, start, end_time, output_dir=out_dir)
            manifest = json.loads(mpath.read_text(encoding="utf-8"))

    end_time = manifest.get("processing", {}).get("end_time", now_str()) if manifest else now_str()
    start = manifest.get("processing", {}).get("start_time", start_time) if manifest else start_time
    sec = elapsed_sec(start, end_time)

    return {
        "video_id": resolved_id,
        "start_time": start,
        "end_time": end_time,
        "elapsed_sec": sec,
        "elapsed_human": format_duration(sec),
        "manifest_path": str(mpath),
        "bundle_path": str(bundle_path) if bundle_path.exists() else None,
        "draft_path": str(draft_path) if draft_path.exists() else None,
        "result_path": str(result_path) if result_path else None,
        "awaiting_ide_summary": awaiting_ide,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube字幕取得・要約パイプライン")
    parser.add_argument("url", nargs="?", help="YouTube URL")
    parser.add_argument("--video-id", help="fetch 省略時の動画 ID")
    parser.add_argument(
        "--steps",
        default="all",
        help="fetch,clean,bundle,render（既定 all。要約は IDE、API は --use-api）",
    )
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--segment-minutes", type=int, default=10)
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--result-dir", default=str(RESULT_DIR))
    parser.add_argument("--model", help="--use-api 時の OpenAI モデル名")
    parser.add_argument("--summary-json", type=Path, help="既存の要約 JSON をドラフトとして使う")
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="OpenAI API で要約（省略時は IDE エージェントが要約）",
    )
    args = parser.parse_args()

    configure_stdout_utf8()

    if not args.url and not args.summary_json and not args.video_id:
        parser.error("url、--video-id、または --summary-json が必要です")

    url = args.url or "https://www.youtube.com/watch?v=PLACEHOLDER"

    try:
        steps = parse_steps(args.steps, use_api=args.use_api)
        result = run_pipeline(
            url,
            lang=args.lang,
            segment_minutes=args.segment_minutes,
            steps=steps,
            jimaku_dir=Path(args.jimaku_dir),
            result_dir=Path(args.result_dir),
            model=args.model,
            summary_json=args.summary_json,
            use_api=args.use_api,
            video_id=args.video_id,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("=" * 60)
    if result.get("awaiting_ide_summary"):
        print("アプリ処理完了（IDE要約待ち）")
    else:
        print("処理完了")
    print("=" * 60)
    print(f"動画ID      : {result['video_id']}")
    print(f"処理開始    : {result['start_time']}")
    print(f"処理終了    : {result['end_time']}")
    print(f"処理時間    : {result['elapsed_human']} ({result['elapsed_sec']}秒)")
    if result.get("result_path"):
        print(f"保存先      : {result['result_path']}")
    if result.get("bundle_path"):
        print(f"AIバンドル  : {result['bundle_path']}")
    if result.get("draft_path"):
        print(f"要約ドラフト: {result['draft_path']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
