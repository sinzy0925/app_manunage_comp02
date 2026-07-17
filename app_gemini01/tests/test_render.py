#!/usr/bin/env python3
"""Step 6: render_summary の検証。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from common import now_str  # noqa: E402
from postprocess_draft import postprocess_draft  # noqa: E402
from render_summary import render_summary  # noqa: E402

VIDEO_ID = "koBLOf-53_g"
JIMaku = _ROOT / "jimaku"
RESULT = _ROOT / "result" / f"{VIDEO_ID}_summary.txt"


def test_render_summary() -> None:
    import json

    mpath = JIMaku / f"{VIDEO_ID}_manifest.json"
    draft_path = JIMaku / f"{VIDEO_ID}_summary_draft.json"
    bundle_path = JIMaku / f"{VIDEO_ID}_ai_bundle.json"

    assert mpath.exists(), mpath
    assert draft_path.exists(), draft_path

    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    expected = None
    if bundle_path.exists():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        expected = int(bundle.get("segment_count", 0)) or None
    draft = postprocess_draft(draft, expected_segments=expected)

    start = "2026-07-17 22:00:00.000"
    end = now_str()

    out = render_summary(mpath, draft, start, end, output_dir=_ROOT / "result")
    assert out == RESULT
    assert RESULT.exists()

    text = RESULT.read_text(encoding="utf-8")
    assert "【結論】" in text
    assert "【章立て詳細要約】" in text
    assert "【10分単位セグメント要約】" in text
    assert f"処理開始時刻: {start}" in text
    assert "処理終了時刻:" in text

    headers = re.findall(r"---\s*セグメント\d+", text)
    assert len(headers) >= 8, f"segment headers: {len(headers)}"

    print(f"render ok: {RESULT}")
    print(f"segment headers in report: {len(headers)}")


if __name__ == "__main__":
    test_render_summary()
    print("Step 6 合格")
