---
name: review-thesis
description: 博士論文全体の一貫性(研究課題と答え、要旨・結論と各章の結果と数値、貢献と根拠、用語と記号、章のつながり、research.json と章の並び、業績一覧と各章)を並列のサブエージェントで査読し、docs/reviews/YYYY-MM-DD-thesis.md に報告を書く。原稿は編集しない
---

# /review-thesis

論文全体を章をまたいだ一貫性の観点から並列に査読し、報告を `docs/reviews/YYYY-MM-DD-thesis.md` に書く。
**原稿は編集しない**。1章の中身は `/review-chapter` で見る。使うとき: 全体を送る前、章を足した・大きく直した後、提出の前。

## 手順

1. **材料を集める。**
   - `docs/thesis-plan.md`(主張・研究課題・貢献・一貫性チェック)、`research.json`、`docs/guardrails.md`
   - `draft/main.tex` の章の並び、`draft/frontmatter/`(和英の要旨、謝辞、`publications.tex`)、各章、`draft/backmatter/`、
     `draft/notation.tex`
   - `draft/values.tex` と各 `projects/<id>/values.tex`、各 `projects/<id>/README.md`(要約カード)
   - `make pdf` の後の `python3 tools/thesis_check.py --all` の結果

2. **並列のサブエージェントで査読する。** 次の観点を**並列**に起動し、重大 / 要修正 / 軽微 の印、該当箇所(ファイルと
   行、またはラベル)、原文の引用、修正案を付けた所見を返させる。
   1. **研究課題と答え**: 序論の各研究課題に結論の章が答え、根拠の章・図表を `\cref` で示しているか。答えの無い
      研究課題、研究課題に対応しない章が無いか。`docs/thesis-plan.md` と原稿が一致しているか
   2. **要旨・結論と結果**: 和英の要旨と結論の結果・数値が各章と一致し、章と同じ `\val` のキーを使っているか
      (手で書いた数値を挙げる)。和文と英文の要旨が食い違っていないか
   3. **貢献と根拠**: 主張する貢献が章・図表・値で裏付けられ、各研究のカードの「言えないこと・注意」を越えて
      いないか。撤回・訂正された結果や `docs/guardrails.md` の撤回した主張に頼っていないか
   4. **用語と記号**: 用語・記号・略語が `notation.tex`・一覧と一致し、章によって揺れていないか
   5. **章のつながり**: 各章のまとめが答えた研究課題と次の章へのつながりを述べ、序論の構成の説明が実際の章の並び
      (`main.tex` = `research.json` の順)と一致しているか。背景・方法が章をまたいで重複していないか
   6. **業績と章**: `publications.tex`、各章の前書き(発表の状況、引用、著者の貢献、転載の許諾)、`research.json` の
      `paper`・`paper_status` が一致しているか

3. **報告を書く。** `docs/reviews/YYYY-MM-DD-thesis.md` に、総評(3行以内)、`docs/thesis-plan.md` の一貫性チェックの
   各項目の判定(満たす / 満たさない / 確かめられない)と根拠、観点ごとの所見、撤回・訂正された結果に頼る主張
   (無ければ「なし」)、手で書かれた数値・値の不一致、`docs/thesis-plan.md`・`research.json` と原稿の食い違いを書く。
   重大な課題の上位3件をその場で要約し、報告のパスを示す。原稿を直すのはユーザーが望んだときだけ。
