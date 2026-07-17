#!/usr/bin/env python3
"""Step 2: gemini_client の疎通テスト。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.gemini_client import create_text_interaction, get_client, ping  # noqa: E402


def test_get_client() -> None:
    client = get_client()
    assert client is not None


def test_ping() -> None:
    raw = ping()
    data = json.loads(raw)
    assert data.get("ok") is True, raw


def test_create_text_interaction() -> None:
    out = create_text_interaction(
        input_text='{"status": "ok"} だけ返して',
        system_instruction="JSONのみ返す",
        model="gemini-3.1-flash-lite",
        thinking_level="minimal",
        response_schema={
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    )
    data = json.loads(out)
    assert "status" in data


if __name__ == "__main__":
    print("get_client...", end=" ")
    test_get_client()
    print("ok")

    print("ping...", end=" ")
    test_ping()
    print("ok")

    print("create_text_interaction...", end=" ")
    test_create_text_interaction()
    print("ok")

    print("Step 2 合格")
