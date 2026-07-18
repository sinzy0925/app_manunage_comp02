# Step 8 品質ベンチマーク結果（最新）

## モデル別サマリー

| モデル | パイプライン | 合計 | 合格 | 出力 |
|--------|-------------|------|------|------|
| Composer 2.5（IDE） | — | **10/10** | ✅ | app_composer01/result/ |
| **gemini-3.5-flash** | Pass2+改造（試行1採用） | **8/10** | ✅ | result/koBLOf-53_g_summary.txt（=01） |
| **gemini-3.1-flash-lite** | Pass2+改造 | **7/10** | ❌ | result/flash_lite/koBLOf-53_g_summary.txt |

## 詳細レポート

- [gemini01_35flash_v3.md](../4_比較結果/比較結果_gemini/gemini01_35flash_v3.md)（3.5-flash・試行1〜3比較、01採用）
- [gemini01_35flash_v2.md](../4_比較結果/比較結果_gemini/gemini01_35flash_v2.md)（3.5-flash・旧）
- [gemini01_flash_lite_v2.md](../4_比較結果/比較結果_gemini/gemini01_flash_lite_v2.md)（flash-lite）

## 再実行コマンド（flash-lite）

```powershell
cd app_gemini01
python scripts/summarize_gemini.py koBLOf-53_g --model gemini-3.1-flash-lite --thinking-level minimal --output jimaku/koBLOf-53_g_summary_draft_flash_lite.json
python scripts/render_summary.py koBLOf-53_g --summary-json jimaku/koBLOf-53_g_summary_draft_flash_lite.json --output-dir result/flash_lite
```

