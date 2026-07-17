#!/usr/bin/env python3
"""処理時刻の記録・経過時間計算。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import configure_stdout_utf8, elapsed_sec, format_duration, now_str, update_manifest_processing


def main() -> int:
    parser = argparse.ArgumentParser(description="処理時刻の記録")
    sub = parser.add_subparsers(dest="command", required=True)

    now_cmd = sub.add_parser("now", help="現在時刻を出力")
    now_cmd.add_argument("--json", action="store_true", help="JSON で出力")

    end_cmd = sub.add_parser("end", help="終了時刻と経過時間を計算")
    end_cmd.add_argument("--start", required=True, help="開始時刻")
    end_cmd.add_argument("--json", action="store_true", help="JSON で出力")

    manifest_cmd = sub.add_parser("manifest", help="manifest に processing を書き込む")
    manifest_cmd.add_argument("manifest_path", type=Path)
    manifest_cmd.add_argument("--start", help="開始時刻（省略時は now）")
    manifest_cmd.add_argument("--end", help="終了時刻（省略時は now）")

    wait_cmd = sub.add_parser("wait", help="テスト用: N 秒待機")
    wait_cmd.add_argument("seconds", type=float)

    args = parser.parse_args()
    configure_stdout_utf8()

    if args.command == "now":
        value = now_str()
        if args.json:
            print(json.dumps({"time": value}, ensure_ascii=False))
        else:
            print(value)
        return 0

    if args.command == "end":
        end = now_str()
        sec = elapsed_sec(args.start, end)
        payload = {
            "start_time": args.start,
            "end_time": end,
            "elapsed_sec": sec,
            "elapsed_human": format_duration(sec),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"開始: {payload['start_time']}")
            print(f"終了: {payload['end_time']}")
            print(f"経過: {payload['elapsed_human']} ({sec}秒)")
        return 0

    if args.command == "manifest":
        fields: dict[str, object] = {}
        if args.start:
            fields["start_time"] = args.start
        if args.end:
            fields["end_time"] = args.end
        if not fields:
            fields["start_time"] = now_str()
        if "start_time" in fields and "end_time" in fields:
            fields["elapsed_sec"] = elapsed_sec(str(fields["start_time"]), str(fields["end_time"]))
            fields["elapsed_human"] = format_duration(float(fields["elapsed_sec"]))
        update_manifest_processing(args.manifest_path, **fields)
        print(json.dumps(fields, ensure_ascii=False, indent=2))
        return 0

    if args.command == "wait":
        time.sleep(args.seconds)
        print(now_str())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
