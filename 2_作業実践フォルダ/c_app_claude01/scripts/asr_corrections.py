"""自動字幕の既知誤変換を置換する辞書ローダ。"""

from __future__ import annotations

import json
from pathlib import Path

CORRECTIONS_PATH = Path(__file__).resolve().parent.parent / "config" / "asr_corrections.json"


def load_corrections(path: Path | None = None) -> dict[str, str]:
    file_path = path or CORRECTIONS_PATH
    if not file_path.exists():
        return {}
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def apply_corrections(text: str, corrections: dict[str, str] | None = None) -> str:
    mapping = corrections if corrections is not None else load_corrections()
    if not mapping:
        return text
    for src in sorted(mapping, key=len, reverse=True):
        text = text.replace(src, mapping[src])
    for src, dst in {"タタタールスタン": "タタールスタン"}.items():
        text = text.replace(src, dst)
    return text
