#!/usr/bin/env python3
"""IDE（エージェント）が作成した要約ドラフトを検証して jimaku/ に保存する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import JIMaku_DIR, configure_stdout_utf8, load_manifest, manifest_path

REQUIRED_KEYS = ("conclusion", "chapter_summary", "segment_summaries")


def validate_draft(data: dict) -> None:
    for key in REQUIRED_KEYS:
        if key not in data:
            raise ValueError(f"要約ドラフトに '{key}' がありません")
        if not str(data[key]).strip():
            raise ValueError(f"要約ドラフトの '{key}' が空です")


def save_summary_draft(
    video_id: str,
    draft: dict,
    jimaku_dir: Path | None = None,
) -> Path:
    base = jimaku_dir or JIMaku_DIR
    validate_draft(draft)
    mpath = manifest_path(video_id, base)
    load_manifest(mpath)
    out_path = base / f"{video_id}_summary_draft.json"
    out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="要約ドラフト JSON を保存")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--input", "-i", type=Path, required=True, help="要約ドラフト JSON")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    args = parser.parse_args()

    configure_stdout_utf8()
    try:
        draft = json.loads(args.input.read_text(encoding="utf-8"))
        out_path = save_summary_draft(args.video_id, draft, Path(args.jimaku_dir))
    except (json.JSONDecodeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
