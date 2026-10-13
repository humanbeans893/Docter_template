---
name: thesis-check
description: 博士論文の PDF をビルドし(make pdf)、原稿の整合性検査(make check。参照・引用・図・表・数値・research.json・書誌の照合)を実行して、結果を具体的な修正案つきでまとめる。版を人に送る前、章・図表・引用を大きく直した後、研究を取り込んだ・更新した後、提出の前に使う
---

# 原稿を検査する

## 手順

1. **ビルドする。** リポジトリのルートで `make pdf`(ホストの LuaLaTeX)。
   - `draft/` に古い中間ファイルがあって止まったら `make clean-tex` してやり直す。`draft/` で `lualatex`・`bibtex` を
     手で実行しない。
   - PDF が書かれなかったら(`Failed:`)`draft/build/main/main.log` の最初の `! ` の行か `ファイル:行:` の行から
     原因を特定し、平易に報告して**ここで止まる**。未定義の参照・引用だけなら(PDF は書かれる)止まらずに 2 へ
     進む(`make check` の E1/E3 が `ファイル:行` を示す)。
   - 送る版は `make pdf-review`、提出の前は `make submission` まで進める。

2. **検査する。** `make check`(`python3 tools/thesis_check.py --all`。main・review・supplementary をまとめて
   調べる)。提出の前は `make check-final`(提出版と補足資料を厳格に。警告も失敗)。

3. **まとめる。** 誤り・警告・情報に分け、各項目に `ファイル:行`、原因、**具体的な修正案**を添える。

| 記号 | 内容 | 直し方 |
|---|---|---|
| E1 / E2 | 参照先のラベルが無い / ラベルの重複 | 綴りを直す、ラベルを足す・付け替える |
| E3 | 引用キーが `reference.bib` に無い、または文書に `\bibliography` が無い | `\bibliography{reference}` を足す。キーが無ければ DOI で原典を確かめて項目を足す。確かめられなければ「出典が必要」と報告する(捏造しない) |
| E4 | 図のファイルが見つからない | 研究の図なら研究リポジトリから `projects/<id>/figures/` に写す(`add-research` スキル)か `<id>/figures/<name>` の綴りを直す。手作りの図は `draft/figures/` に置き台帳に行を足す |
| E5 | 読み込むファイルが無い | パスを直す。研究の表なら `projects/<id>/tables/` に写す |
| E6 / W8 | メタデータが未入力・雛形のまま | `draft/thesis-config.tex` を埋める(推測せずユーザーに確かめる) |
| E7 / I1 | TODO が残る(提出) / TODO の一覧 | 片付けるか、残すかをユーザーに確かめる |
| E8 | `\val`・`\valqty`・`\rawval` のキーが定義されていない | `projects/<id>/values.tex` でキーの綴りを確かめる。無い数値は研究リポジトリから元をコメントに書いて足す。研究リポジトリにも無ければそちらで作ってもらう(本文に手で書かない) |
| E9 | 要旨・謝辞に本文が無い、または有効にした任意のページに雛形の文(`% thesis:placeholder` の行)が残る(提出) | 本文を書く。任意のページは雛形を書き換えて印を消すか、`draft/thesis-config.tex` で無効にする |
| E10 | 図・`\input`・`\ThesisValues`・`\graphicspath` がリポジトリの外か `external/` の下を指す | ファイルを `projects/<id>/` に写し、そこから読む |
| E11 | 値の定義が `\begin{document}` の後で読まれている | 章での `\input` をやめ、`draft/values.tex` に `\ThesisValues{…}` で登録する |
| E12 | `research.json` が読めない・形や欄が違う、`id` が不正・重複、`projects/<id>/` が無い、`chapter` のファイルが無いか `main.tex` が読み込んでいない | 指摘の行を直す。足りないものは `add-research` スキルの手順で作る |
| W1 / W2 | 書誌のキーの重複 / 引用されない項目 | 重複を消す / 引用するか消す |
| W3 | `draft/figures/` の図がどの文書にも入っていない | 使わない図はユーザーに確かめてから台帳の行と一緒に消す |
| W4 / W5 / W7 | 参照されない図表のラベル / ラベルの接頭辞 / 裸の `\ref` | 本文で `\cref` する / 接頭辞を直す / `\cref` にする |
| W9 / W10 / I2 | 重複したページのアンカー / はみ出した行 / ログの所見 | ログの該当箇所を直す |
| W11 | `draft/figures/` の手作りの図が台帳 `draft/figures/README.md` に無い | 台帳に行(出所・作り方)を足す |
| W12 | 同じ値のキーが2回定義されている | 登録の重複かキーの重複を直す |
| W13 | 同じ DOI の書誌が2つある | 1つにまとめ、引用キーをそろえる |
| W17 | `draft/values.tex` に登録した値のファイルが無い(提出では誤り) | パスを直すか `projects/<id>/values.tex` を作る。使わないなら登録の行を消す |
| I4 | `verified` の欄が無い書誌(提出では誤り) | DOI で原典と照合し `verified = {YYYY-MM-DD, doi:…}` を付ける(自分の未発表の論文は `AGENTS.md` の「文献」) |
| I6 | 検査が展開できないマクロ(`\def`・`\NewDocumentCommand` など)の中の `\includegraphics`・`\label`・`\ref`・`\cite`・`\val` | `\newcommand` で定義し直すか、本文に直接書く |

**直し方の原則**: 図表・数値の誤りの元は研究リポジトリにある。そちらで直してもらい、新しいコミットから写し直す
(`add-research` スキルの「新しいコミットを反映する」)。研究リポジトリにはここから書き込まない。

4. **直して再実行する。** ユーザーが望んだら直し、誤りが 0 になるまで 1〜3 を繰り返す。終わったら PDF のパスと
   ページ数、最後の集計(誤り 0 / 警告 N / TODO M)を報告する。
