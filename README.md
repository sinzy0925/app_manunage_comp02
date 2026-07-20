# YoutubeのURLから字幕データを取得して、要約する作業をする。

この作業をする際、仕事丸投げ、スキル活用、アプリ活用でどのような差が出るのかテストを行う

まとめた内容は、以下の記事を参照ください。
[https://qiita.com/sinzy0925/items/7bfe17702cb31ccc9fed](https://qiita.com/sinzy0925/items/7bfe17702cb31ccc9fed)

## テストの比較ポイント

1. かかった時間
2. 要約の精度
3. トークン量（トークンコスト＝ドル換算）

### トークン量取得方法

[https://cursor.com/dashboard/usage](https://cursor.com/dashboard/usage) からCSVをダウンロードする。

### ドル換算

[https://cursor.com/ja/docs/models-and-pricing](https://cursor.com/ja/docs/models-and-pricing)　を参照する。

## 活用するＡＩツール

Cursor

## 活用するＡＩモデル

Cursorで一番安いモデルと、claudeで高価なモデルの遅い版で比較

- Composer2.5(Fastでない方)
- Claude-Opus-4.8-low-Thinking

## テスト方法

仕事丸投げ、スキル活用、アプリ活用について、AIモデル単位に３回テストをする。

テストを行う際は、完全に新規フォルダを作成して実施する。  
それぞれのフォルダに入れるものは、比較予定/の各フォルダ内容。

### 仕事丸投げ、スキル活用、アプリ活用

- Composer2.5 ＝＞　３回
- Claude-Opus-4.8-low-Thinking　＝＞　３回

## 対象のURLは以下で固定

https://www.youtube.com/watch?v=koBLOf-53_g

要約の精度が同程度になるように、プロンプトは編集済。

時間測定は、プロンプト入力直前から結果出力後までの全体
（アプリの場合は、アプリ処理時間と要約プロンプト入力直前から結果出力後まで）

要約の結果は、全作業終了後に以下のプロンプトで比較予定

- [要約比較プロンプト.md](要約比較プロンプト.md)

## 結論の出し方

本番判断と時間・コストの比較は、各モデル×各方式の**最高品質試行**を代表とする（品質があっての時間・コスト）。全18試行のばらつきは試行別レポート（`比較結果_claude/claude01〜03`、`比較結果_composer/composer01〜03`）で確認する。
