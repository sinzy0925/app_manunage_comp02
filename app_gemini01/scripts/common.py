"""共通ユーティリティ。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

TIME_FMT = "%Y-%m-%d %H:%M:%S.%f"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JIMaku_DIR = PROJECT_ROOT / "jimaku"
RESULT_DIR = PROJECT_ROOT / "result"
TEMPLATE_PATH = (
    PROJECT_ROOT / ".cursor" / "skills" / "youtube-jimaku-summary" / "summary-template.md"
)


def configure_stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def now_str() -> str:
    return datetime.now().strftime(TIME_FMT)[:-3]


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, TIME_FMT)


def elapsed_sec(start_time: str, end_time: str) -> float:
    delta = parse_time(end_time) - parse_time(start_time)
    return round(delta.total_seconds(), 3)


def format_duration(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f}秒"
    minutes, remainder = divmod(int(sec), 60)
    if minutes < 60:
        return f"{minutes}分{remainder}秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}時間{minutes}分{remainder}秒"


def format_video_duration(sec: int | str) -> str:
    total = int(sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}時間{m}分{s}秒"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def format_segment_label(start_sec: float, end_sec: float) -> str:
    def _fmt(sec: float) -> str:
        h, rem = divmod(int(sec), 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    return f"{_fmt(start_sec)}〜{_fmt(end_sec)}"


def ensure_dirs() -> None:
    JIMaku_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)


def manifest_path(video_id: str, jimaku_dir: Path | None = None) -> Path:
    base = jimaku_dir or JIMaku_DIR
    return base / f"{video_id}_manifest.json"


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"manifest が見つかりません: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def update_manifest_processing(path: Path, **fields: object) -> dict:
    data = load_manifest(path)
    processing = data.setdefault("processing", {})
    processing.update(fields)
    save_manifest(path, data)
    return data
