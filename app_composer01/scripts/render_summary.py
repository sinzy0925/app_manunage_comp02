#!/usr/bin/env python3
"""要約ドラフトと manifest をテンプレートに合成し result/ に保存する。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    RESULT_DIR,
    TEMPLATE_PATH,
    configure_stdout_utf8,
    ensure_dirs,
    format_video_duration,
    load_manifest,
    manifest_path,
    now_str,
)


def render_summary(
    manifest_file: Path,
    summary_draft: dict,
    start_time: str,
    end_time: str,
    template_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    manifest = load_manifest(manifest_file)
    video_id = manifest["video_id"]
    metadata = manifest.get("metadata", {})

    duration = metadata.get("duration_sec", "")
    duration_label = format_video_duration(duration) if duration else "不明"

    template = (template_path or TEMPLATE_PATH).read_text(encoding="utf-8")
    content = (
        template.replace("{url}", manifest.get("url", ""))
        .replace("{video_id}", video_id)
        .replace("{duration}", duration_label)
        .replace("{uploader}", metadata.get("uploader", ""))
        .replace("{vtt_path}", manifest.get("vtt_path", ""))
        .replace("{conclusion}", summary_draft.get("conclusion", "").strip())
        .replace("{chapter_summary}", summary_draft.get("chapter_summary", "").strip())
        .replace("{segment_summaries}", summary_draft.get("segment_summaries", "").strip())
        .replace("{start_time}", start_time)
        .replace("{end_time}", end_time)
        .replace("{date}", date.today().isoformat())
    )

    ensure_dirs()
    out_base = output_dir or RESULT_DIR
    out_base.mkdir(parents=True, exist_ok=True)
    out_path = out_base / f"{video_id}_summary.txt"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="要約レポートを result/ に保存")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default="jimaku")
    parser.add_argument("--summary-json", help="要約ドラフト JSON")
    parser.add_argument("--start-time", help="処理開始時刻")
    parser.add_argument("--end-time", help="処理終了時刻（省略時は now）")
    parser.add_argument("--output-dir", default=str(RESULT_DIR))
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    mpath = manifest_path(args.video_id, base)
    draft_path = Path(args.summary_json) if args.summary_json else base / f"{args.video_id}_summary_draft.json"

    if not draft_path.exists():
        print(f"要約ドラフトが見つかりません: {draft_path}", file=sys.stderr)
        return 1

    summary_draft = json.loads(draft_path.read_text(encoding="utf-8"))
    manifest = load_manifest(mpath)
    processing = manifest.get("processing", {})
    start_time = args.start_time or processing.get("start_time", "")
    end_time = args.end_time or processing.get("end_time") or now_str()

    if not start_time:
        print("処理開始時刻が未設定です (--start-time または manifest.processing.start_time)", file=sys.stderr)
        return 1

    try:
        out_path = render_summary(
            mpath,
            summary_draft,
            start_time,
            end_time,
            output_dir=Path(args.output_dir),
        )
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
