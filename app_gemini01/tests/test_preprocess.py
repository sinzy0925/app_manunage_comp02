#!/usr/bin/env python3
"""Step 3: 前処理スクリプト移植の検証。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from load_manifest import build_ai_bundle  # noqa: E402

REQUIRED_BUNDLE_KEYS = {
    "outline_hints",
    "entities_by_segment",
    "numeric_facts",
    "must_cover",
    "uncertain_spans",
    "instructions",
    "segments",
    "segment_count",
}

COMPOSER_BUNDLE = _ROOT.parent / "app_composer01" / "jimaku" / "koBLOf-53_g_ai_bundle.json"
FIXTURE_BUNDLE = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_ai_bundle.json"
FIXTURE_MANIFEST = _ROOT / "tests" / "fixtures" / "koBLOf-53_g_manifest.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_bundle() -> None:
    bundle = _load(FIXTURE_BUNDLE)
    missing = REQUIRED_BUNDLE_KEYS - set(bundle.keys())
    assert not missing, f"missing keys: {missing}"
    assert bundle["segment_count"] == 8
    assert len(bundle["segments"]) == 8
    assert len(bundle.get("must_cover", [])) > 0
    print(f"fixture bundle ok: {bundle['segment_count']} segments")


def test_structure_matches_composer() -> None:
    if not COMPOSER_BUNDLE.exists():
        print("skip structure compare (composer bundle not found)")
        return
    ours = _load(FIXTURE_BUNDLE)
    ref = _load(COMPOSER_BUNDLE)
    assert set(ours.keys()) == set(ref.keys()), (
        f"key mismatch: only in ours={set(ours)-set(ref)} only in ref={set(ref)-set(ours)}"
    )
    assert ours["segment_count"] == ref["segment_count"]
    print("structure matches app_composer01")


def _normalize_manifest_for_jimaku(manifest: dict, jimaku: Path) -> dict:
    """古い絶対パスを jimaku/ 内のファイル名に直す。"""
    data = dict(manifest)
    segment_paths = [Path(p).name for p in data.get("segment_paths", [])]
    data["segment_paths"] = segment_paths
    data["vtt_path"] = str(jimaku / Path(str(data.get("vtt_path", ""))).name)
    data["full_text_path"] = str(jimaku / Path(str(data.get("full_text_path", ""))).name)
    segments = []
    for seg in data.get("segments", []):
        seg_copy = dict(seg)
        seg_copy["path"] = Path(str(seg.get("path", ""))).name
        segments.append(seg_copy)
    data["segments"] = segments
    return data


def test_rebuild_bundle_from_manifest() -> None:
    """manifest + segment が jimaku にある場合に bundle を再生成できる。"""
    jimaku = _ROOT / "jimaku"
    composer_jimaku = _ROOT.parent / "app_composer01" / "jimaku"
    video_id = "koBLOf-53_g"

    manifest = _load(FIXTURE_MANIFEST)
    for path_str in manifest.get("segment_paths", []):
        name = Path(path_str).name
        dst = jimaku / name
        if not dst.exists():
            src = composer_jimaku / name
            if src.exists():
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    mpath = jimaku / f"{video_id}_manifest.json"
    mpath.write_text(
        json.dumps(_normalize_manifest_for_jimaku(manifest, jimaku), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    bundle = build_ai_bundle(mpath, jimaku)
    missing = REQUIRED_BUNDLE_KEYS - set(bundle.keys())
    assert not missing, f"missing keys: {missing}"
    assert bundle["segment_count"] == 8
    print(f"rebuild bundle ok: {bundle['segment_count']} segments")


if __name__ == "__main__":
    test_fixture_bundle()
    test_structure_matches_composer()
    test_rebuild_bundle_from_manifest()
    print("Step 3 合格")
