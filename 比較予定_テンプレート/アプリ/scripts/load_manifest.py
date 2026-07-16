#!/usr/bin/env python3
"""jimaku/ の manifest とセグメントを読み込み、AI 入力バンドルを生成する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    JIMaku_DIR,
    configure_stdout_utf8,
    format_segment_label,
    load_manifest,
    manifest_path,
)
from enrich_bundle import INSTRUCTIONS, enrich_bundle


def build_ai_bundle(manifest_file: Path, jimaku_dir: Path | None = None) -> dict:
    data = load_manifest(manifest_file)
    base = jimaku_dir or manifest_file.parent
    segment_minutes = int(data.get("segment_minutes", 10))
    segments_out: list[dict] = []

    segment_paths = sorted(data.get("segment_paths", []))
    segment_meta = data.get("segments", [])
    expected = data.get("segment_count", len(segment_paths))

    if not segment_meta:
        for i, path_str in enumerate(segment_paths):
            segment_meta.append(
                {
                    "index": i,
                    "start_sec": i * segment_minutes * 60,
                    "end_sec": (i + 1) * segment_minutes * 60,
                    "path": path_str,
                }
            )

    if len(segment_meta) != expected or len(segment_paths) != expected:
        raise ValueError(
            f"segment 数が一致しません: meta={len(segment_meta)} "
            f"count={expected} paths={len(segment_paths)}"
        )

    for i, path_str in enumerate(segment_paths):
        seg_path = Path(path_str)
        if not seg_path.is_absolute():
            candidates = [base / seg_path.name, base / seg_path, Path(path_str)]
            seg_path = next((p for p in candidates if p.exists()), base / seg_path.name)
        if not seg_path.exists():
            raise FileNotFoundError(f"セグメントファイルが見つかりません: {path_str}")

        meta = segment_meta[i] if i < len(segment_meta) else {}
        start = float(meta.get("start_sec", i * segment_minutes * 60))
        end = float(meta.get("end_sec", (i + 1) * segment_minutes * 60))
        segments_out.append(
            {
                "index": meta.get("index", i),
                "label": format_segment_label(start, end),
                "start_sec": start,
                "end_sec": end,
                "text": seg_path.read_text(encoding="utf-8"),
            }
        )

    segments_out.sort(key=lambda x: int(x["index"]))

    bundle = {
        "video_id": data["video_id"],
        "url": data.get("url", ""),
        "metadata": data.get("metadata", {}),
        "segment_count": data.get("segment_count", len(segments_out)),
        "segment_minutes": segment_minutes,
        "segments": segments_out,
        "instructions": INSTRUCTIONS,
    }
    return enrich_bundle(bundle)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 入力バンドルを生成")
    parser.add_argument("video_id", help="動画 ID")
    parser.add_argument("--jimaku-dir", default=str(JIMaku_DIR))
    parser.add_argument("--output", help="出力 JSON パス（省略時は stdout）")
    args = parser.parse_args()

    configure_stdout_utf8()
    base = Path(args.jimaku_dir)
    mpath = manifest_path(args.video_id, base)

    try:
        bundle = build_ai_bundle(mpath, base)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    out_path = Path(args.output) if args.output else base / f"{args.video_id}_ai_bundle.json"
    out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"bundle_path": str(out_path), "segment_count": bundle["segment_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
