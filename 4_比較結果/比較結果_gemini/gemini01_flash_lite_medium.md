# 要約比較レポート — gemini-3.1-flash-lite + thinking medium

**比較日:** 2026-07-17  
**注記:** API は `normal` 非対応のため **`thinking_level: medium`** で実行（`minimal`/`low`/`medium`/`high` のみ）

## スコア

| モデル | thinking | 合計 | 合格 |
|--------|----------|------|------|
| gemini-3.5-flash | low | **9** | ✅ |
| gemini-3.1-flash-lite | minimal | **7** | ❌ |
| **gemini-3.1-flash-lite** | **medium** | **7** | ❌ |

| 観点 | medium | minimal |
|------|--------|---------|
| A | 1 | 1 |
| B | 2 | 2 |
| C | 1 | 1 |
| D | 1 | 1 |
| E | 2 | 2 |

**所要時間:** ~27秒（minimal ~24秒とほぼ同じ）

## medium vs minimal の差

**改善:**
- セグメント箇条書きがやや厚い（5本前後が増えた）
- マリウポリ71%・トラック26430台・デンマーク工場言及などカバレッジ微増

**悪化・同じ:**
- **「2024年1月2日」** — 字幕は「2024年4月2日」と「1月2日朝」が別。月の誤結合（minimal は「1月2日」のみで年号誤りはなかった）
- 817/1379・メディアゾナ・R280 は依然欠落
- 章立ては段落主体で箇条書きノルマ未達

## 出力

- `app_gemini01/result/flash_lite_medium/koBLOf-53_g_summary.txt`
- `app_gemini01/jimaku/koBLOf-53_g_summary_draft_flash_lite_medium.json`

## 結論

flash-lite で thinking を minimal→medium に上げても **7点止まり**。品質のボトルネックは推論量よりモデル容量側。本番は引き続き **3.5-flash** 推奨。
