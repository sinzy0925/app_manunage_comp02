---
name: youtube-jimaku-summary
description: >-
  YouTube動画の要約ワークフロー。jimaku/ の要約前テキスト（ai_bundle.json）を元に
  IDE で要約し summary_draft.json を作成する。字幕取得はユーザーが手動でアプリ実行。
  Use when the user asks to summarize from jimaku/, summarize pre-summary text,
  youtube-jimaku-summary, or summarize a YouTube video after subtitles are fetched.
---

# YouTube字幕取得・要約スキル

## 役割分担（重要）

| 担当 | 処理 | 実行方法 |
|------|------|----------|
| **ユーザー（手動）** | 字幕取得・クリーニング・バンドル生成 | `python scripts/run_pipeline.py "URL" --steps fetch,clean,bundle` |
| **IDE エージェント（あなた）** | 要約作成 → `summary_draft.json` 保存 | 本スキルに従い `ai_bundle.json` のみ読んで要約 |
| **ユーザー（手動）** | レポート生成 | `python scripts/run_pipeline.py --video-id ID --steps render` |

> アプリの実行はユーザーが手動で行う。エージェントは **要約指示を受けたときだけ** 動く（字幕取得コマンドは実行しない）。

---

## 要約前テキストとは（jimaku/ 内）

要約の入力になるファイル。アプリ手動実行後に `jimaku/` に生成される。

| ファイル | 役割 | 要約時の優先度 |
|---------|------|----------------|
| `{video_id}_ai_bundle.json` | クリーニング済み字幕＋メタデータ＋要約指示 | **これだけ読む（必須）** |
| `{video_id}_summary_draft.json` | 既存の要約ドラフト | ある場合は AI 要約をスキップ |
| `{video_id}_manifest.json` | 動画ID・セグメント一覧 | **読まない**（bundle に含まれる） |
| `segment_00.txt` … | 10分単位の字幕 | **読まない**（bundle に含まれる） |
| `{video_id}_ja_full.txt` | 全文 | **読まない** |
| `{video_id}.ja.vtt` | 元字幕 | **読まない** |

**video_id の特定:** `jimaku/*_manifest.json` または `jimaku/*_ai_bundle.json` を探す。複数ある場合はユーザーに確認するか、最新の manifest を使う。

**トークン節約（重要）:** `manifest` や `segment_*.txt` を個別に読まないこと。内容はすべて `{video_id}_ai_bundle.json` に集約されている。

---

## モード A: 要約のみ（よく使う）

ユーザーがアプリを手動実行済みで、「jimaku/ を元に要約して」と指示した場合。

### トリガー例

```
@youtube-jimaku-summary
jimaku/ の要約前テキストを元に要約して

jimaku/ を読んで要約して

WztHP0mvTSc を要約して（jimaku/ にデータあり）
```

### 実行チェックリスト（要約のみ）

```
- [ ] 0. jimaku/{video_id}_summary_draft.json が既にあるか確認（あれば Step 4〜6 のみ）
- [ ] 1. 処理開始時刻を記録
- [ ] 2. jimaku/{video_id}_ai_bundle.json のみを読む
- [ ] 3. 要約を作成し jimaku/{video_id}_summary_draft.json に保存
- [ ] 4. ユーザーに render コマンドを案内（手動実行）
- [ ] 5. 処理終了時刻を記録・表示
```

### Step 0: 既存ドラフトの確認（キャッシュ）

`jimaku/{video_id}_summary_draft.json` が既に存在し、ユーザーが **再要約を明示していない** 場合:

- AI 要約は行わない
- ユーザーに render のみ案内する:

```powershell
python scripts/run_pipeline.py --video-id VIDEO_ID --steps render
```

「もう一度要約して」「作り直して」などの指示がある場合のみ Step 2 以降を実行する。

### Step 1: 処理開始時刻

指示を確認した時点で即座に取得:

```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

### Step 2: 要約前テキストを読んで要約

`jimaku/{video_id}_ai_bundle.json` **1ファイルのみ** を読み込む。

`summary-draft-schema.json` は通常読まなくてよい（スキーマは下記 JSON 形式に従えば足りる）。

#### ai_bundle の enrichment フィールド（必ず参照）

| フィールド | 使い方 |
|-----------|--------|
| `outline_hints` | `chapter_summary` の章構成に反映 |
| `entities_by_segment` | セグメントごとの固有名詞。組織・製品の混同防止 |
| `numeric_facts` | 数値・日付の照合用（高信号を優先して本文に入れる） |
| `must_cover` | **一発要約で落とさない優先ファクト**。章かセグメントのどちらかに必ず織り込む |
| `uncertain_spans` | **推測禁止**。年号欠落などは書かないか「不明」 |
| `instructions` | 厚みノルマ付き。bundle 内の指示を要約時の正本とする |

#### IDE 内の要約手順（1回の依頼で完結・詳細寄り）

再要約ループは行わない。1回の依頼の中で次の順に考える。本編事実は抜けなし（簡潔化は宣伝のみ）。章とセグメントの全文重複で厚くしない:

1. `outline_hints`・`must_cover`・`entities_by_segment` を把握
2. 各 `segments[]` を順に読み、セグメントごとに箇条 5〜8 本分の時系列ファクトを頭の中で列挙
3. `uncertain_spans` の箇所は推測しない
4. `must_cover` と高信号 `numeric_facts` のカバレッジを確認しながら、`conclusion` → `chapter_summary`（因果・対比）→ `segment_summaries`（時系列）を書く。同一ファクトは片方のみ
5. 保存前チェック（下記）

#### 厚みノルマ（必須・下限）

| 欄 | 下限 |
|----|------|
| `conclusion` | 箇条書き **3〜5点**（主張＋主要メカニズム名） |
| `chapter_summary` | 各 `■` の下に箇条書き **4〜7本**。導入・`outline_hints` 各章・締めを含む。因果・対比が主、数値は最小限 |
| `segment_summaries` | 各セグメント箇条書き **5〜8本**（1段落だけで終えない）。日付・距離・金額の主戦場 |
| ファクト | `must_cover` と高信号数値は章かセグメントに **おおよそ8割以上**（**どちらか一方**。両方に書かない） |

章＝テーマの因果・対比、セグメント＝時系列の事実列。同一エピソード・同一数値のフル再現は禁止。

#### 保存前チェックリスト

- [ ] セグメント数 = `segment_count`
- [ ] 各章が箇条 4 本以上、各セグメントが箇条 5 本以上
- [ ] `must_cover` の主要項目が本文に出ている（章かセグメントのどちらか一方）
- [ ] 章とセグメントで同じ固有イベントが二重に詳細化されていない
- [ ] エアロドロームとファイアポイント等、別組織の属性を混同していない
- [ ] `uncertain_spans` の年号を勝手に補完していない
- [ ] 英日混在表記（例: `イェラブuga`）がない
- [ ] メタ記述（「セグメント05と連続」等）が入っていない

#### 要約構成（必須）

1. **結論** — 箇条 3〜5点で全体主張と主要メカニズム
2. **章立て詳細要約** — テーマごとに ■ 見出し＋各 4〜7 箇条（`outline_hints` があれば従う）。因果・対比中心
3. **10分単位セグメント要約** — 各セグメント `--- セグメントNN（時刻範囲）---` ＋ 5〜8 箇条。時系列ファクト中心

#### 要約時の注意（厳守）

- `ai_bundle.json` の `entities_by_segment` / `numeric_facts` / `must_cover` / `uncertain_spans` / `instructions` を参照する
- 自動字幕の重複・[音楽]・タイムスタンプは無視
- 宣伝・おまけトークは簡潔化または省略（**本編は抜けなし。章とセグメントの重複で厚くしない**）
- **字幕にない年号・数値は推測しない**（`uncertain_spans` は省略または「不明」）
- **別組織・製品の属性を混同しない**（例: エアロドローム ≠ ファイアポイント）
- 数値・固有名詞は可能な限り正確に。英日混在表記を作らない

### Step 3: 要約ドラフトを保存

`jimaku/{video_id}_summary_draft.json` に保存:

```json
{
  "conclusion": "- 主張1\n- 主張2\n- 主張3",
  "chapter_summary": "■ 第1章：...\n- ...\n- ...",
  "segment_summaries": "--- セグメント00（0:00〜10:00）---\n- ...\n- ..."
}
```

エージェントはこの JSON ファイルに **直接書き込む**（`save_summary_draft.py` はユーザー向け）。

### Step 4: レポート生成の案内（ユーザー手動）

要約完了後、ユーザーに以下を伝える:

```powershell
python scripts/run_pipeline.py --video-id VIDEO_ID --steps render
```

出力先: `result/{video_id}_summary.txt`

### Step 5: 処理終了時刻

```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
```

ユーザーに表示: 処理開始・終了・処理時間・保存した draft パス・render コマンド

---

## モード B: 字幕取得から要約まで（URL 指定時）

URL も渡された場合のみ。字幕取得は **ユーザーが手動で済ませている前提** を優先し、
`jimaku/` にデータが無ければ取得コマンドを案内する（エージェントが勝手に実行しない）。

```
jimaku/ にデータが無い場合:
  → ユーザーに以下を案内
  python scripts/run_pipeline.py "URL" --steps fetch,clean,bundle
  → 完了後にモード A で要約
```

---

## エラー対応

| 症状 | 対処 |
|------|------|
| jimaku/ が空 | ユーザーにアプリ手動実行を案内 |
| ai_bundle が無い | `fetch,clean,bundle` の実行を案内 |
| 要約ドラフトが無い | モード A の Step 2〜3 を実施 |
| 要約ドラフトがある | render のみ案内（再要約指示時を除く） |
| 複数 video_id | ユーザーにどれを要約するか確認 |

## ユーザーへの依頼例

**要約のみ（アプリ実行済み）:**

```
@youtube-jimaku-summary
jimaku/ の要約前テキストを元に要約して
```

**URL 付き（未取得なら取得コマンドを案内）:**

```
@youtube-jimaku-summary
https://www.youtube.com/watch?v=VIDEO_ID
を要約して
```
