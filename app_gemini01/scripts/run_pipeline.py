#!/usr/bin/env python3
"""YouTube字幕取得・Gemini要約パイプライン統合 CLI。

フル実行:
  python scripts/run_pipeline.py "URL" --provider gemini

段階実行:
  python scripts/run_pipeline.py "URL" --steps fetch,clean,bundle
  python scripts/run_pipeline.py --video-id ID --steps summarize,render --provider gemini
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common as pipeline_common
from common import (
    JIMaku_DIR,
    RESULT_DIR,
    configure_stdout_utf8,
    elapsed_sec,
    ensure_dirs,
    format_duration,
    log_progress,
    make_pipeline_log_path,
    manifest_path,
    now_str,
    set_pipeline_log,
    update_manifest_processing,
)
from clean_subs import clean_subtitles
from fetch_subs import fetch_subtitles
from load_manifest import build_ai_bundle
from postprocess_draft import postprocess_draft
from render_summary import render_summary
from summarize_gemini import load_bundle, summarize_bundle_gemini

APP_STEPS = ("fetch", "clean", "bundle", "summarize", "render")
DEFAULT_PROVIDER = "gemini"


def _video_id_from_json(path: Path) -> str | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("video_id")


def parse_steps(value: str, *, provider: str) -> list[str]:
    if value == "all":
        steps = ["fetch", "clean", "bundle"]
        if provider == "gemini":
            steps.append("summarize")
        steps.append("render")
        return steps
    steps = [s.strip() for s in value.split(",") if s.strip()]
    unknown = set(steps) - set(APP_STEPS)
    if unknown:
        raise ValueError(f"不明なステップ: {', '.join(sorted(unknown))}")
    if "summarize" in steps and provider != "gemini":
        raise ValueError("summarize ステップには --provider gemini が必要です")
    return steps


def run_pipeline(
    url: str,
    *,
    lang: str = "ja",
    segment_minutes: int = 10,
    steps: list[str] | None = None,
    jimaku_dir: Path | None = None,
    result_dir: Path | None = None,
    model: str | None = None,
    thinking_level: str | None = None,
    summary_json: Path | None = None,
    provider: str = DEFAULT_PROVIDER,
    video_id: str | None = None,
    pass1_trials: int = 1,
) -> dict:
    ensure_dirs()
    base = jimaku_dir or JIMaku_DIR
    out_dir = result_dir or RESULT_DIR
    selected = steps or parse_steps("all", provider=provider)
    start_time = now_str()

    manifest: dict | None = None
    resolved_id = video_id

    if "fetch" in selected:
        log_progress(f"STEP fetch 開始: {url}")
        manifest = fetch_subtitles(url, base, lang, segment_minutes)
        resolved_id = manifest["video_id"]
        log_progress(f"STEP fetch 完了: video_id={resolved_id}")
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
        log_progress("STEP clean 開始")
        clean_subtitles(mpath, base)
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        log_progress("STEP clean 完了")

    bundle: dict | None = None
    if "bundle" in selected:
        log_progress("STEP bundle 開始")
        bundle = build_ai_bundle(mpath, base)
        bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        log_progress(f"STEP bundle 完了: {bundle_path}")

    if "summarize" in selected:
        model_name = model or os.environ.get("GEMINI_MODEL")
        thinking = thinking_level or os.environ.get("GEMINI_THINKING_LEVEL")
        log_progress(f"STEP summarize 開始: model={model_name} thinking={thinking}")
        if summary_json:
            draft_path.write_text(summary_json.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            if bundle is None:
                bundle = load_bundle(bundle_path) if bundle_path.exists() else build_ai_bundle(mpath, base)
                if not bundle_path.exists():
                    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
            summary = summarize_bundle_gemini(
                bundle,
                model=model_name,
                thinking_level=thinking,
                pass1_trials=pass1_trials,
            )
            draft_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        log_progress(f"STEP summarize 完了: {draft_path}")

    result_path: Path | None = None

    if "render" in selected:
        log_progress("STEP render 開始")
        if not draft_path.exists():
            raise RuntimeError(
                f"要約ドラフトがありません: {draft_path}\n"
                "--steps summarize を含めるか、先に要約を作成してください。"
            )
        if bundle is None and bundle_path.exists():
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        expected = int(bundle.get("segment_count", 0)) if bundle else None
        draft = postprocess_draft(
            draft,
            bundle=bundle,
            expected_segments=expected or None,
            stringify_segments=True,
        )
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        start = manifest.get("processing", {}).get("start_time", start_time)
        end_time = now_str()
        update_manifest_processing(mpath, end_time=end_time)
        result_path = render_summary(mpath, draft, start, end_time, output_dir=out_dir)
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        log_progress(f"STEP render 完了: {result_path}")

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
        "provider": provider,
        "log_path": str(pipeline_common._pipeline_log_path)
        if pipeline_common._pipeline_log_path
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="YouTube字幕取得・Gemini要約パイプライン")
    parser.add_argument("url", nargs="?", help="YouTube URL")
    parser.add_argument("--video-id", help="fetch 省略時の動画 ID")
    parser.add_argument(
        "--steps",
        default="all",
        help="fetch,clean,bundle,summarize,render（既定 all）",
    )
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, choices=["gemini"])
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--segment-minutes", type=int, default=10)
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--result-dir", default=str(RESULT_DIR))
    parser.add_argument("--model", help="Gemini モデル名（省略時 GEMINI_MODEL）")
    parser.add_argument("--thinking-level", help="thinking_level（省略時 GEMINI_THINKING_LEVEL）")
    parser.add_argument(
        "--pass1-trials",
        type=int,
        default=1,
        help="Pass1 試行回数（2以上で機械スコア最高を採用）",
    )
    parser.add_argument("--summary-json", type=Path, help="既存の要約 JSON をドラフトとして使う")
    args = parser.parse_args()

    configure_stdout_utf8()

    if not args.url and not args.summary_json and not args.video_id:
        parser.error("url、--video-id、または --summary-json が必要です")

    url = args.url or "https://www.youtube.com/watch?v=PLACEHOLDER"

    video_id_guess = args.video_id
    if not video_id_guess and args.url and "PLACEHOLDER" not in args.url:
        from fetch_subs import extract_video_id

        try:
            video_id_guess = extract_video_id(args.url)
        except ValueError:
            video_id_guess = None
    if not video_id_guess and args.summary_json:
        video_id_guess = _video_id_from_json(args.summary_json)

    log_path = make_pipeline_log_path(video_id_guess or "run")
    set_pipeline_log(log_path)

    try:
        steps = parse_steps(args.steps, provider=args.provider)
        model_name = args.model or os.environ.get("GEMINI_MODEL", "")
        thinking = args.thinking_level or os.environ.get("GEMINI_THINKING_LEVEL", "")
        log_progress(
            f"パイプライン開始 steps={','.join(steps)} model={model_name} thinking={thinking}"
        )
        log_progress(f"ログファイル: {log_path}")
        result = run_pipeline(
            url,
            lang=args.lang,
            segment_minutes=args.segment_minutes,
            steps=steps,
            jimaku_dir=Path(args.jimaku_dir),
            result_dir=Path(args.result_dir),
            model=args.model,
            thinking_level=args.thinking_level,
            summary_json=args.summary_json,
            provider=args.provider,
            video_id=args.video_id,
            pass1_trials=args.pass1_trials,
        )
    except Exception as exc:
        log_progress(f"エラー: {exc}")
        print(str(exc), file=sys.stderr)
        return 1

    log_progress("パイプライン完了")
    print("=" * 60)
    print("処理完了")
    print("=" * 60)
    print(f"動画ID      : {result['video_id']}")
    print(f"プロバイダ  : {result['provider']}")
    print(f"処理開始    : {result['start_time']}")
    print(f"処理終了    : {result['end_time']}")
    print(f"処理時間    : {result['elapsed_human']} ({result['elapsed_sec']}秒)")
    if result.get("result_path"):
        print(f"保存先      : {result['result_path']}")
    if result.get("bundle_path"):
        print(f"AIバンドル  : {result['bundle_path']}")
    if result.get("draft_path"):
        print(f"要約ドラフト: {result['draft_path']}")
    if result.get("log_path"):
        print(f"ログ        : {result['log_path']}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
