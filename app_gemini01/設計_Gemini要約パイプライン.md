# Gemini 要約パイプライン設計書（ステップ実装・テスト付き）

**目的:** `app_composer01` の前処理・後処理を維持し、AI要約のみを **Gemini Interactions API** に置き換える。  
**品質目標:** 現行 IDE 要約（`app_composer01` 10点 / `koBLOf-53_g`）に **同等以上** を狙う。  
**方針:** 新規アプリ `app_gemini01/` として分離し、ステップごとに実装 → 単体テスト → 結合確認する。

---

## 0. 設計方針（おすすめ構成）

### なぜ別アプリか

| 項目 | 現行 `app_composer01` | 本設計 `app_gemini01` |
|------|----------------------|----------------------|
| 前処理 | fetch / clean / enrich_bundle | **同一コードをコピー or 共有**（変更しない） |
| 要約 | IDE エージェント（Composer 2.5） | **Gemini API（バッチ）** |
| 後処理 | postprocess_draft + render | **同一** |
| 品質の鍵 | enrichment + SKILL ルール | enrichment + **同等プロンプト** + structured JSON |

### 品質を最大化するための推奨設定

> 以前の確認で `gemini-3.1-flash-lite` は実装可能だが、**品質最優先なら本番モデルは別枠**とする。

| 設定 | 推奨値 | 理由 |
|------|--------|------|
| **本番モデル（品質）** | `gemini-2.5-pro` | 事実忠実性・長文理解に強い。比較ベースの IDE 10点に最も近づきやすい |
| **代替（速度・コスト）** | `gemini-3.5-flash` + `thinking_level: low` | 品質とコストのバランス |
| **実験・大量処理** | `gemini-3.1-flash-lite` + `thinking_level: minimal` | 安いが10点同等は未保証 |
| **thinking** | **`low` または `minimal`** | `high` は推測補完（幻覚）リスク増。字幕要約は「事実抽出」寄り |
| **要約方式** | **一括要約（IDE 同等）** | map-reduce は統合時に情報落ち。71分・8セグメントは 1M コンテキスト内 |
| **出力** | **Structured Output（JSON Schema）** | `summary_draft.json` 形式を強制 |
| **入力** | `ai_bundle.json` のみ | `must_cover` / `uncertain_spans` 等をすべてプロンプトに明示 |
| **API** | Interactions API | `system_instruction` + `generation_config` + structured output |
| **認証** | `.env` の `GOOGLE_API_KEY` | `python-dotenv` で読み込み |

### パイプライン全体像

```
[Step 1-3] 前処理（既存と同じ）
  URL → fetch → clean → bundle → ai_bundle.json

[Step 4-6] Gemini 要約（新規）
  ai_bundle.json → prompt 構築 → Gemini API → summary_draft.json

[Step 7-8] 後処理（既存と同じ）
  summary_draft.json → postprocess_draft → render → result/*.txt

[Step 9] 品質検証
  app_composer01 結果と A〜E スコア比較
```

### ディレクトリ構成（完成形）

```
app_gemini01/
├── .env                          # GOOGLE_API_KEY（gitignore）
├── .env.example                  # キー名のサンプルのみ
├── requirements.txt
├── 実行方法.txt
├── 設計_Gemini要約パイプライン.md  # 本ファイル（コピー可）
├── scripts/
│   ├── common.py                 # app_composer01 からコピー
│   ├── fetch_subs.py
│   ├── clean_subs.py
│   ├── enrich_bundle.py
│   ├── load_manifest.py
│   ├── asr_corrections.py
│   ├── postprocess_draft.py
│   ├── render_summary.py
│   ├── gemini_client.py          # ★新規: API ラッパ
│   ├── build_prompt.py           # ★新規: enrichment 全渡し
│   ├── summarize_gemini.py       # ★新規: 要約本体
│   └── run_pipeline.py           # ★改修: --provider gemini
├── jimaku/                       # 中間データ
├── result/                       # 最終レポート
└── tests/
    ├── test_gemini_client.py
    ├── test_build_prompt.py
    ├── test_summarize_gemini.py
    └── fixtures/
        └── koBLOf-53_g_ai_bundle.json  # 既存からコピー
```

---

## ステップ一覧（実装順）

| Step | 内容 | 単体テスト | 完了条件 |
|------|------|-----------|----------|
| 1 | プロジェクト骨格・依存関係 | `pip install` | import 成功 |
| 2 | `.env` 読み込み・Gemini 接続 | API 疎通 | 1文応答が返る |
| 3 | 前処理スクリプト移植 | fetch→bundle | `ai_bundle.json` 生成 |
| 4 | プロンプト構築 | unit test | enrichment 全フィールド含有 |
| 5 | Structured 要約（1回呼び出し） | draft JSON 保存 | 必須3キーが存在 |
| 6 | 後処理・レポート生成 | render | `result/*.txt` 出力 |
| 7 | パイプライン統合 CLI | E2E 1本 | URL→result まで完走 |
| 8 | 品質ベンチマーク | 比較レポート | A〜E 合計 ≥ 9 |

---

## Step 1: プロジェクト骨格・依存関係

### 目的

`app_gemini01/` を作成し、Python 環境とパッケージを固定する。

### 作業

1. `app_composer01/` をベースに `app_gemini01/` を作成（`jimaku/` `result/` `scripts/` のうち後で使うものだけ）
2. `requirements.txt` を作成:

```text
google-genai>=1.0.0
python-dotenv>=1.0.0
```

3. `.env.example` を作成:

```text
GOOGLE_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-pro
GEMINI_THINKING_LEVEL=low
```

4. `.gitignore` に `.env` を追加（未設定なら）

### テスト

```powershell
cd app_gemini01
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from google import genai; import dotenv; print('ok')"
```

### 合格基準

- [ ] `google-genai` / `python-dotenv` の import が成功する
- [ ] `.env` がリポジトリにコミットされない

---

## Step 2: `.env` 読み込み・Gemini 接続（`gemini_client.py`）

### 目的

API キーとモデル設定を一元管理し、以降のステップから再利用する。

### 実装: `scripts/gemini_client.py`

```python
"""Gemini Interactions API ラッパ。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# app_gemini01 ルートの .env を読む
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")
DEFAULT_THINKING = os.environ.get("GEMINI_THINKING_LEVEL", "low")


def get_client() -> genai.Client:
    api_key = os.environ.get("GOOGLE_API_KEY")
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
) -> str:
    """Interactions API でテキスト生成。structured 時は JSON 文字列を返す。"""
    client = get_client()
    generation_config: dict = {
        "thinking_level": thinking_level or DEFAULT_THINKING,
        "temperature": 0.15,
    }
    if response_schema:
        generation_config["response_mime_type"] = "application/json"
        generation_config["response_json_schema"] = response_schema

    interaction = client.interactions.create(
        model=model or DEFAULT_MODEL,
        system_instruction=system_instruction,
        input=input_text,
        generation_config=generation_config,
    )
    return interaction.output_text or ""
```

### テスト: `tests/test_gemini_client.py`

```powershell
cd app_gemini01
python -c "
from scripts.gemini_client import create_text_interaction
out = create_text_interaction(
    input_text='JSONで {\"ok\": true} だけ返して',
    system_instruction='JSONのみ返す',
    model='gemini-3.1-flash-lite',
    thinking_level='minimal',
)
print(out[:200])
"
```

### 合格基準

- [ ] `.env` の `GOOGLE_API_KEY` で API 呼び出しが成功する
- [ ] キー未設定時に明確なエラーメッセージが出る
- [ ] `thinking_level=minimal` で応答が返る（コスト確認用に `usage` ログを任意で表示）

### 注意

- 本番品質用の既定モデルは `gemini-2.5-pro`。疎通テストだけ `gemini-3.1-flash-lite` でも可。
- API キーはログに出力しない。

---

## Step 3: 前処理スクリプト移植（変更なし）

### 目的

品質の土台である **enrichment 付き `ai_bundle.json`** を、現行と同一ロジックで生成する。

### 作業

`app_composer01/scripts/` から以下を **そのままコピー**（ロジック変更禁止）:

- `common.py`
- `fetch_subs.py`
- `clean_subs.py`
- `asr_corrections.py`
- `enrich_bundle.py`
- `load_manifest.py`

比較用に、既存の `jimaku/koBLOf-53_g_ai_bundle.json` を `tests/fixtures/` にもコピー。

### テスト A: 既存バンドルでスキップ実行

```powershell
cd app_gemini01
# fixtures を jimaku にコピーして確認
Copy-Item tests\fixtures\koBLOf-53_g_* jimaku\ -ErrorAction SilentlyContinue
python -c "
import json
from pathlib import Path
b = json.loads(Path('jimaku/koBLOf-53_g_ai_bundle.json').read_text(encoding='utf-8'))
assert b['segment_count'] == 8
assert 'must_cover' in b and 'uncertain_spans' in b
print('bundle ok', b['segment_count'], 'segments')
"
```

### テスト B: フル前処理（ネットワーク必要）

```powershell
python scripts/fetch_subs.py "https://www.youtube.com/watch?v=koBLOf-53_g"
python scripts/clean_subs.py koBLOf-53_g
python scripts/load_manifest.py koBLOf-53_g
# または run_pipeline --steps fetch,clean,bundle（Step 7 で統合）
```

### 合格基準

- [ ] `ai_bundle.json` に `outline_hints`, `entities_by_segment`, `numeric_facts`, `must_cover`, `uncertain_spans`, `instructions` が含まれる
- [ ] `segment_count` が 8（`koBLOf-53_g` の場合）
- [ ] `app_composer01` で生成した bundle とフィールド構造が一致する

---

## Step 4: プロンプト構築（`build_prompt.py`）

### 目的

IDE/SKILL と **同等の情報量** を Gemini に渡す。現行 `summarize.py` の欠落（`must_cover` 未渡し等）を解消する。

### 実装方針

**システム指示（固定）** + **ユーザ入力（bundle 由来 JSON）** の2層。

#### `SYSTEM_INSTRUCTION`（要旨）

`app_composer01/.cursor/skills/youtube-jimaku-summary/SKILL.md` の以下を prose 化して埋め込む:

- 推測禁止（`uncertain_spans` 遵守）
- 章とセグメントの役割分担（重複禁止）
- 厚みノルマ（conclusion 3〜5 / 章 4〜7 / セグメント 5〜8 箇条）
- `must_cover` 8割以上カバー
- 宣伝は最終セグメントのみ簡潔化
- 英日混在表記禁止

#### `build_user_payload(bundle: dict) -> str`

以下を **すべて** JSON に含めて `input` に渡す:

```python
{
  "metadata": bundle["metadata"],
  "outline_hints": bundle["outline_hints"],
  "entities_by_segment": bundle["entities_by_segment"],
  "numeric_facts": bundle["numeric_facts"],
  "must_cover": bundle["must_cover"],
  "uncertain_spans": bundle["uncertain_spans"],
  "segment_count": bundle["segment_count"],
  "segments": bundle["segments"],  # 全文（一括要約）
  "instructions": bundle["instructions"],
}
```

> **品質のため map-reduce は使わない。** 71分・8セグメントは `gemini-2.5-pro` の 1M コンテキスト内。

### テスト: `tests/test_build_prompt.py`

```python
# 疑似テスト（pytest なしでも可）
from scripts.build_prompt import build_user_payload, SYSTEM_INSTRUCTION
import json
from pathlib import Path

bundle = json.loads(Path("tests/fixtures/koBLOf-53_g_ai_bundle.json").read_text(encoding="utf-8"))
payload = json.loads(build_user_payload(bundle))

assert "must_cover" in payload and len(payload["must_cover"]) > 0
assert "uncertain_spans" in payload
assert len(payload["segments"]) == payload["segment_count"]
assert "推測" in SYSTEM_INSTRUCTION or "uncertain" in SYSTEM_INSTRUCTION.lower()
print("prompt build ok")
```

### 合格基準

- [ ] `must_cover` / `uncertain_spans` / `outline_hints` が payload に含まれる
- [ ] 全セグメント本文が payload に含まれる（切り詰めなし、または 1M 超のみ末尾省略＋警告）
- [ ] `SYSTEM_INSTRUCTION` が SKILL.md の必須ルールを網羅している

---

## Step 5: Gemini 要約本体（`summarize_gemini.py`）

### 目的

**1回の API 呼び出し**で `summary_draft.json` を生成する（IDE 一括要約と同型）。

### JSON Schema

`summary-draft-schema.json` をベースに structured output 用スキーマを定義:

```python
SUMMARY_SCHEMA = {
    "type": "object",
    "required": ["conclusion", "chapter_summary", "segment_summaries"],
    "properties": {
        "conclusion": {"type": "string"},
        "chapter_summary": {"type": "string"},
        "segment_summaries": {"type": "string"},
    },
    "additionalProperties": False,
}
```

### 実装フロー

```python
def summarize_bundle_gemini(bundle: dict, *, model: str | None = None) -> dict:
    from scripts.build_prompt import SYSTEM_INSTRUCTION, build_user_payload
    from scripts.gemini_client import create_text_interaction
    from scripts.postprocess_draft import postprocess_draft
    import json

    raw = create_text_interaction(
        system_instruction=SYSTEM_INSTRUCTION,
        input_text=build_user_payload(bundle),
        model=model,
        thinking_level="low",  # 品質: low / コスト: minimal
        response_schema=SUMMARY_SCHEMA,
    )
    draft = json.loads(raw)
    expected = int(bundle.get("segment_count", 0)) or None
    return postprocess_draft(draft, expected_segments=expected)
```

### CLI

```powershell
python scripts/summarize_gemini.py koBLOf-53_g
# → jimaku/koBLOf-53_g_summary_draft.json
```

### テスト

```powershell
cd app_gemini01
python scripts/summarize_gemini.py koBLOf-53_g --model gemini-2.5-pro
python -c "
import json
from pathlib import Path
d = json.loads(Path('jimaku/koBLOf-53_g_summary_draft.json').read_text(encoding='utf-8'))
for k in ('conclusion','chapter_summary','segment_summaries'):
    assert k in d and len(d[k]) > 100, k
print('draft ok')
"
```

### 合格基準

- [ ] `conclusion` / `chapter_summary` / `segment_summaries` の3キーが存在
- [ ] セグメントヘッダが 8 個（`postprocess_draft` の警告なし）
- [ ] `uncertain_spans` 対象の年号を勝手に補完していない（目視または下記 Step 8）
- [ ] API エラー時に JSON パース失敗のメッセージが分かる

### 品質向けオプション（Step 5.5・任意）

一括要約でセグメント数不一致が出た場合のみ **リトライ1回**:

- 入力に `previous_draft` と `_warnings` を付けて「セグメント数を修正せよ」と再送
- 2回失敗したらエラー終了（無限ループ禁止）

---

## Step 6: 後処理・レポート生成

### 目的

現行と同一の `postprocess_draft` + `render_summary` で最終 TXT を出す。

### 作業

`app_composer01/scripts/` からコピー:

- `postprocess_draft.py`（Step 5 で既に使用）
- `render_summary.py`
- `.cursor/skills/youtube-jimaku-summary/summary-template.md`

### テスト

```powershell
python scripts/render_summary.py koBLOf-53_g
# → result/koBLOf-53_g_summary.txt
```

### 合格基準

- [ ] `result/koBLOf-53_g_summary.txt` が生成される
- [ ] 結論・章立て・セグメント00〜07 の見出しがある
- [ ] 処理開始・終了時刻がテンプレートに埋まる

---

## Step 7: パイプライン統合（`run_pipeline.py`）

### 目的

1コマンドで URL から最終レポートまで実行できる CLI を提供する。

### コマンド設計

```powershell
# フル実行（Gemini 要約込み）
python scripts/run_pipeline.py "https://www.youtube.com/watch?v=koBLOf-53_g" --provider gemini

# 段階実行（デバッグ用）
python scripts/run_pipeline.py "URL" --steps fetch,clean,bundle
python scripts/run_pipeline.py --video-id koBLOf-53_g --steps summarize --provider gemini
python scripts/run_pipeline.py --video-id koBLOf-53_g --steps render
```

### `run_pipeline.py` 改修ポイント

| 既存 | 追加 |
|------|------|
| `--use-api`（OpenAI） | `--provider gemini`（本設計） |
| IDE 引き渡しメッセージ | `--provider gemini` 時は `summarize_gemini` を自動呼び出し |
| steps: fetch,clean,bundle,render | steps に `summarize` を明示可能に |

### E2E テスト

```powershell
cd app_gemini01
python scripts/run_pipeline.py "https://www.youtube.com/watch?v=koBLOf-53_g" --provider gemini --model gemini-2.5-pro
```

### 合格基準

- [ ] 1コマンドで `result/{video_id}_summary.txt` まで完走
- [ ] 処理時間・トークン使用量（任意ログ）が表示される
- [ ] 既存 `jimaku/` データのみでも `--steps summarize,render` で再実行可能

### `実行方法.txt`（完成版の例）

```text
# フル（Gemini・品質モデル）
python scripts/run_pipeline.py "https://www.youtube.com/watch?v=VIDEO_ID" --provider gemini --model gemini-2.5-pro

# コスト優先
python scripts/run_pipeline.py "URL" --provider gemini --model gemini-3.1-flash-lite

# 要約のみ（前処理済み）
python scripts/run_pipeline.py --video-id VIDEO_ID --steps summarize,render --provider gemini
```

---

## Step 8: 品質ベンチマーク（必須）

### 目的

「実装できた」ではなく **現行10点と同等か** を検証する。

### 手順

1. ベースライン: `app_composer01/result/koBLOf-53_g_summary.txt`（IDE 10点）
2. 新規: `app_gemini01/result/koBLOf-53_g_summary.txt`
3. 一次ソース: `jimaku/koBLOf-53_g_ja_full.txt` または `ai_bundle.json`
4. `要約比較プロンプト.md` を使い、A〜E 観点で採点

### 合格基準（リリース判定）

| 観点 | 目標 |
|------|------|
| A. 事実忠実性 | ≥ 2（Planet・勝利パレード等の幻覚なし） |
| B. エンティティ一貫性 | ≥ 2 |
| C. 情報充足 | ≥ 2 |
| D. 構造・読みやすさ | ≥ 1（理想 2） |
| E. 形式遵守 | ≥ 2 |
| **合計** | **≥ 9 / 10**（理想 10） |

### 不合格時のチューニング順

1. モデルを `gemini-2.5-pro` に上げる（flash-lite のままなら先に変更）
2. `thinking_level` を `low` に（`high` は使わない）
3. `SYSTEM_INSTRUCTION` に SKILL の保存前チェックリストを追記
4. `must_cover` をプロンプト先頭に「必須チェックリスト」として再掲
5. それでも不足なら **セグメント検証パス**（Step 5.5）を追加

---

## モデル選定チートシート

| 用途 | モデル | thinking | 期待 |
|------|--------|----------|------|
| **品質本番（推奨）** | `gemini-2.5-pro` | `low` | IDE 10点に最接近 |
| バランス | `gemini-3.5-flash` | `low` | 8〜10点帯 |
| コスト試験 | `gemini-3.1-flash-lite` | `minimal` | 実装確認用。品質未保証 |

---

## リスクと対策

| リスク | 対策 |
|--------|------|
| 幻覚（年号・場所の付加） | `uncertain_spans` 明示 + thinking `low/minimal` + temperature 0.15 |
| セグメント数不一致 | structured schema + `postprocess_draft` 警告 + 1回リトライ |
| トークン超過 | 1M 内に収まるか事前に文字数チェック。超過時のみ末尾セグメント分割要約（最終手段） |
| API コスト | 開発は flash-lite、品質判定は 2.5-pro のみ |
| `.env` 漏洩 | gitignore + `.env.example` のみコミット |

---

## 実装スケジュール（目安）

| Step | 作業時間目安 | 依存 |
|------|-------------|------|
| 1 | 30分 | — |
| 2 | 1時間 | Step 1 |
| 3 | 30分 | Step 1 |
| 4 | 2時間 | Step 3 |
| 5 | 2〜3時間 | Step 2, 4 |
| 6 | 30分 | Step 5 |
| 7 | 1〜2時間 | Step 5, 6 |
| 8 | 1時間 | Step 7 |

**合計:** 約 1〜2 日（品質チューニング除く）

---

## 次のアクション

1. **Step 1** から順に実装（飛ばさない）
2. 各 Step 完了時に「合格基準」チェックリストをすべて ✅ にする
3. Step 8 で **合計 9 点未満** なら本番リリースしない
4. 合格後、`実行方法/実行方法_アプリ.md` に Gemini 版の節を追記

---

## 参考リンク

- [Interactions API overview](https://ai.google.dev/gemini-api/docs/interactions-overview)
- [Structured outputs](https://ai.google.dev/gemini-api/docs/interactions/structured-output)
- [Thinking（level 制御）](https://ai.google.dev/gemini-api/docs/interactions/thinking)
- [gemini-2.5-pro / gemini-3.1-flash-lite モデル一覧](https://ai.google.dev/gemini-api/docs/models)
