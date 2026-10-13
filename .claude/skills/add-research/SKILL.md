---
name: add-research
description: 別の研究リポジトリにある研究(論文・実験の結果)を博士論文に取り込む。research.json に行を足し、projects/_template から projects/<id>/ を作って要約・図・表・数値をこのリポジトリの形に直し、章を作って書く。研究リポジトリの新しいコミットを反映するときにも使う。ユーザーが「この研究を論文に入れたい」「この論文を章にしたい」「研究リポジトリの新しい結果を反映して」と言ったときに使う
---

# 研究を取り込む

研究リポジトリの中身を、このリポジトリの決まった形(`research.json` の1行と `projects/<id>/`)に直して章にする。
研究リポジトリの構成は問わない。規則(読むだけ、コミットから写す、元の書き方、数値の元の選び方、撤回した結果)は
`AGENTS.md` の「研究を取り込む」にあり、ここでは繰り返さない。`<path>` は研究リポジトリのクローンの場所。

## 取り込む

1. **読む。** 場所が分からなければそれだけを聞く(`external/` に置くなら
   `mkdir -p external && ln -sfn "$(realpath <クローンの場所>)" external/<repo>`)。

   ```bash
   git -C <path> rev-parse --short=12 HEAD   # 写すコミット <sha>
   git -C <path> status --short              # 変更のあるファイルは、コミットされた版を写す
   git -C <path> ls-files                    # 構成をつかむ
   ```

   README・STATE.md などの記録、論文のソース(`\includegraphics`・`\input`・数値のマクロ・`.bib`)、結果の図・表・
   CSV、それを作ったスクリプト、撤回・訂正の記録(research-template なら `experiments/EXP_SUMMARY.md` と各
   `summary.md`、`docs/guardrails.md`)を読む。構成が分からなければ、論文が使う図・表・数値から元のファイルをたどる。

2. **案を1回で示す。** 読んで分かったこと(`id` の案、章にするか、写す図・表・数値と元、`<sha>`、論文の状況、
   共著者、写さない撤回・訂正の結果)をまとめて示し、リポジトリから分からないこと(転載の許諾、著者の貢献、
   正式な結果が決められないとき)だけを聞く。雛形の `study1` が残っていれば、消すこともこの案に入れる。

3. **雛形から作る。** 了承を得たら:

   ```bash
   cp -r projects/_template projects/<id>
   ```

   `research.json` の `research` に、既存の行と同じ欄で行を足す(並びは章の順。`source` は `<repo>@<sha>`、
   `status` は `構想`)。最初の研究なら雛形の `study1` を消す: `research.json` の行、`projects/study1/`、
   `draft/chapters/study1.tex`、`main.tex` の `\include{chapters/study1}`、`draft/values.tex` の `\ThesisValues` の行。

4. **図と表を写す。**

   ```bash
   git -C <path> show <sha>:<file> > projects/<id>/figures/<name>.pdf
   ```

   作業ツリーに変更が無ければ `cp` でもよい。図は `figures/`(PDF などベクターを優先)、表は `tables/<name>.tex`
   (tabular の部分だけ。表題とラベルは章に書く)。論文の表が数値のマクロを使っていれば `\val{<id>-<マクロ名>}` に
   直す。CSV しか無ければ値を変えずに booktabs で組む。撤回・訂正された行・列は写さず、除いたことを表の先頭の
   コメントに元と並べて書く。`README.md` の「図表」に1ファイル1行で元を書く。

5. **数値を `values.tex` に入れる。** 本文が使う数値を1行1定義で入れ、各行の上のコメントに元
   (`<repo>@<sha>:<file>` と行・列や節)を書く。research-template の `numbers.tex` は次で変換できる
   (見出しの行を落とし、元のコメントに `<repo>@<sha>:result/tables/` を付ける)。

   ```bash
   git -C <path> show <sha>:draft/tables/numbers.tex | sed -nE \
     -e 's|^% ([^ ]+\.csv )|% <repo>@<sha>:result/tables/\1|p' \
     -e 's/^\\newcommand\{\\([A-Za-z]+)\}/\\deftextvalue{<id>-\1}/p' >> projects/<id>/values.tex
   ```

   ほかの形の数値は手で写す。`draft/values.tex` の `% thesis:values:end` の上に
   `\ThesisValues{../projects/<id>/values}` を足す。

6. **カードを書く。** `projects/<id>/README.md` の `<…>` をすべて埋める(問い・方法・主な結果・言えないこと)。
   末尾の埋め方のコメントは消す。`research.json` の `status` を `取り込み済み` にする。

7. **章を作る。** `cp draft/chapters/_chapter-template.tex draft/chapters/<id>.tex` し、冒頭の `template-only` の
   塊を消して `<id>` と `<Research title>` を埋める。`draft/main.tex` の研究の章の並び(`research.json` の順)に
   `\include{chapters/<id>}` を足し、`research.json` の `chapter` に書く。章を持たない研究(図・数値を他の章で
   使うだけ)は `chapter` を `""` にしてこの手順と次を飛ばす。

8. **章を書く。** 論文とカードから博士論文の章として書く(`AGENTS.md` の「原稿」)。前書き(発表の状況と
   `\citet{<bibkey>}`、著者の貢献、転載の許諾、発表版との違い)のうちユーザーの答えを待つ項目は、コメントのまま
   `% TODO` にする。図・表・数値の書き方は雛形の末尾の例。

9. **書誌を足す**(`AGENTS.md` の「文献」)。使う項目を論文の `.bib` から `draft/reference.bib` に入れて照合し、
   `verified` を付ける。照合できない他人の文献は入れず、章に `% TODO: citation needed (<著者 年>, unverified)`。
   論文そのものの項目は `research.json` の `paper` に書き、`draft/frontmatter/publications.tex` の項目
   (雛形の `thesis:placeholder` の行はこれで置き換える)にする。最初の本当の引用なら `main.tex` の
   `\nocite{lamport1994latex}` と `reference.bib` のその項目を消す。

10. **検査する。** `make pdf` と `make check`(`thesis-check` スキル)で誤りが 0 になるまで直す。

11. **記録する。** `research.json` の `status` を進め(`執筆中`・`完成`)、撤回した主張があれば
    `docs/guardrails.md` に1行書き、`write-handoff` スキルで `STATE.md` を更新する。

## 新しいコミットを反映する

研究リポジトリで図・数値が直った・増えたとき。

1. `git -C <path> diff --stat <旧sha> <新sha> -- <写したパス>` で変わったファイルを見る。撤回・訂正の記録も読む。
2. 変わったものを手順 4・5 と同じく写し直す(`values.tex` は変わった定義を置き換える。`>>` で足すと重複して
   W12 になる。表も写し直す)。カードの元と `research.json` の `source` を新しい `<sha>` にする。
3. `git diff -- projects/<id>/values.tex` で変わった数値ごとに、それを使う本文・要旨・結論の言い回し(増えた・
   有意など)が合うかを確かめる。消えた数値は `make check` の E8 になる。
4. `make pdf` と `make check` を通す。結論が変わったら `research-log` スキルで記録する。

## 報告

`id`、`<repo>@<sha>`、写したファイル、本文で使う値の名前、写さなかった撤回・訂正の結果、ユーザーと研究
リポジトリに残る作業(許諾、照合できない文献、足りない図・数値)を短くまとめる。
