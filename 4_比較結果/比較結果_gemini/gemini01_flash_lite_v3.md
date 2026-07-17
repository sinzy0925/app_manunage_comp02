# 要約比較レポート（品質のみ）— gemini-3.1-flash-lite（enrich v4）

**比較日:** 2026-07-18  
**対象動画:** https://www.youtube.com/watch?v=koBLOf-53_g  
**一次ソース:** `app_gemini01/jimaku/koBLOf-53_g_ai_bundle.json`（enrichment v4）  
**パイプライン:** Pass2 + must_cover_check + unit_consistency + enrich v4  
**出力:** `app_gemini01/result/flash_lite/koBLOf-53_g_summary.txt`

## 1. 観点別スコア

| ファイル | 方式 | モデル | 試行 | A忠実 | B一貫 | C充足 | D読易 | E形式 | 合計/10 |
|---|---|---|---|---|---|---|---|---|---|
| app_composer01/result/koBLOf-53_g_summary.txt | アプリ（IDE） | Composer2.5 | 1 | 2 | 2 | 2 | 2 | 2 | **10** |
| app_gemini01/result/koBLOf-53_g_summary.txt | Gemini API | gemini-3.5-flash | 3 | 2 | 2 | 2 | 2 | 2 | **10** |
| app_gemini01/result/flash_lite/koBLOf-53_g_summary.txt | Gemini API | gemini-3.1-flash-lite | 3 | 1 | 2 | 2 | 1 | 2 | **8** |
| （参考）v2 flash-lite | Gemini API | gemini-3.1-flash-lite | 2 | 1 | 2 | 1 | 1 | 2 | 7 |

**Step 8 合格基準（≥9点）:** ❌ 未達（8点）

---

## 2. 観点別コメント

### A. 事実忠実性（1点）

- 良い: `2024年4月2日` 記載、`300km`（kg幻覚なし）、817体/1379体
- 悪い: セグメント04「1日**3人**のミサイル生産」— 字幕は「1日に**3発**」（unit_consistency の誤修正）

### B. エンティティ一貫性（2点）

- 混同なし

### C. 情報の充足（2点）

- 良い: must_cover 25/25、R280、FP7X、ホーネット、パトリオット在庫の大枠
- 悪い: メディアゾナ15万6000人、第64旅団21回攻撃、デルタ165万件/日5000件、ロバートブロブディ10万82人の明示が欠落

### D. 構造・読みやすさ（1点）

- 章立てが段落2〜3文主体で、厚みノルマ（各■4〜7箇条）未達。セグメントは5本前後で改善。

### E. 形式遵守（2点）

- 必須3セクション、セグメント00〜07、メタ文なし

---

## 3. v2（7点）からの変化

| 項目 | v2 | v4 flash-lite |
|------|-----|----------------|
| 2024年4月2日 | 欠落 | ✅ |
| 817/1379 | 欠落 | ✅ |
| 章・セグメント厚み | 薄い | やや改善（章は依然薄い） |
| 新規問題 | — | 1日3人（誤修正） |

---

## 4. まとめ

- **flash-lite + enrich v4: 8/10**（v2比 +1、合格閾値9には未達）
- パイプライン改善の恩恵はあるが、**モデル能力の上限**で composer / 3.5-flash には届かない
- コスト重視の下書き用途向け。本番品質は **3.5-flash** を推奨
