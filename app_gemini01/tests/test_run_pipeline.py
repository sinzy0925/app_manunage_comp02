#!/usr/bin/env python3
"""Step 7: run_pipeline 統合テスト。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from run_pipeline import run_pipeline  # noqa: E402

VIDEO_ID = "koBLOf-53_g"
RESULT = _ROOT / "result" / f"{VIDEO_ID}_summary.txt"


def test_render_only() -> None:
    """既存ドラフトから render のみ。"""
    result = run_pipeline(
        "https://www.youtube.com/watch?v=PLACEHOLDER",
        steps=["render"],
        provider="gemini",
        video_id=VIDEO_ID,
        jimaku_dir=_ROOT / "jimaku",
        result_dir=_ROOT / "result",
    )
    assert result["result_path"]
    assert Path(result["result_path"]).exists()
    print(f"render-only ok: {result['result_path']}")


def test_summarize_render() -> None:
    """前処理済み jimaku から summarize → render。"""
    model = os.environ.get("GEMINI_TEST_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.5-flash"))
    thinking = os.environ.get("GEMINI_TEST_THINKING", os.environ.get("GEMINI_THINKING_LEVEL", "low"))

    result = run_pipeline(
        "https://www.youtube.com/watch?v=PLACEHOLDER",
        steps=["summarize", "render"],
        provider="gemini",
        video_id=VIDEO_ID,
        model=model,
        thinking_level=thinking,
        jimaku_dir=_ROOT / "jimaku",
        result_dir=_ROOT / "result",
    )

    assert result["video_id"] == VIDEO_ID
    assert result["result_path"]
    assert Path(result["result_path"]).exists()
    assert RESULT.exists()

    text = RESULT.read_text(encoding="utf-8")
    assert "【結論】" in text
    assert result["elapsed_sec"] >= 0

    print(f"pipeline ok: {result['result_path']}")
    print(f"elapsed: {result['elapsed_human']}")


def test_fetch_clean_bundle_only() -> None:
    """ネットワーク: 前処理のみ（要約 API なし）。"""
    result = run_pipeline(
        "https://www.youtube.com/watch?v=koBLOf-53_g",
        steps=["fetch", "clean", "bundle"],
        provider="gemini",
        jimaku_dir=_ROOT / "jimaku",
        result_dir=_ROOT / "result",
    )
    bundle = _ROOT / "jimaku" / f"{result['video_id']}_ai_bundle.json"
    assert bundle.exists()
    data = json.loads(bundle.read_text(encoding="utf-8"))
    assert data["segment_count"] == 8
    print(f"preprocess ok: {bundle}")


if __name__ == "__main__":
    test_render_only()
    if os.environ.get("RUN_GEMINI_SUMMARIZE_TEST", "1") == "1":
        test_summarize_render()
    if os.environ.get("RUN_FETCH_TEST") == "1":
        test_fetch_clean_bundle_only()
    print("Step 7 合格")
