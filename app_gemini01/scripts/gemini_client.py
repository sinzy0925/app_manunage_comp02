"""Gemini Interactions API ラッパ。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
DEFAULT_THINKING = os.environ.get("GEMINI_THINKING_LEVEL", "low")


def get_client() -> genai.Client:
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip().strip('"').strip("'")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY が .env にありません")
    return genai.Client(api_key=api_key)


def create_text_interaction(
    *,
    input_text: str,
    system_instruction: str,
    model: str | None = None,
    thinking_level: str | None = None,
    response_schema: dict | None = None,
    temperature: float = 0.05,
) -> str:
    """Interactions API でテキスト生成。structured 時は JSON 文字列を返す。"""
    client = get_client()
    generation_config: dict[str, Any] = {
        "thinking_level": thinking_level or DEFAULT_THINKING,
        "temperature": temperature,
    }
    if response_schema:
        generation_config["response_mime_type"] = "application/json"
        generation_config["response_json_schema"] = response_schema

    try:
        interaction = client.interactions.create(
            model=model or DEFAULT_MODEL,
            system_instruction=system_instruction,
            input=input_text,
            generation_config=generation_config,
        )
    except Exception as exc:
        err = str(exc)
        if "429" in err or "quota" in err.lower() or "RateLimit" in type(exc).__name__:
            raise RuntimeError(
                f"Gemini API クォータ超過（model={model or DEFAULT_MODEL}）。"
                "別モデル（例: gemini-3.5-flash）を試すか、課金プランを確認してください。"
            ) from exc
        raise
    return interaction.output_text or ""


def ping(*, model: str = "gemini-3.5-flash", thinking_level: str = "low") -> str:
    """API 疎通確認用の短い呼び出し。"""
    return create_text_interaction(
        input_text='{"ok": true} という JSON だけ返してください。',
        system_instruction="JSONのみ返す。マークダウンや説明は不要。",
        model=model,
        thinking_level=thinking_level,
        response_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
    )
