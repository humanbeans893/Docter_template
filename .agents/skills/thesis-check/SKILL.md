---
name: thesis-check
description: 博士論文の PDF をビルドし(make pdf)、原稿の整合性検査(make check。参照・引用・図・生成した数値・由来・書誌の照合)を実行して、結果を具体的な修正案つきでまとめる。版を人に送る前、章・図表・引用を大きく直した後、提出の前に使う
---

# 原稿を検査する

原稿をビルドし、整合性検査の結果を修正案つきでまとめます。

## 使うとき

- 原稿を指導教員・審査員に送る前
- 章・図表・引用・生成した数値を大きく直した後
- ユーザーが「論文をチェックして」「原稿を確認して」と言ったとき

## 手順

### 1. ビルドする

リポジトリのルートで(ホストの LuaLaTeX):

```bash
make pdf            # draft/main.pdf(bash draft/compile.sh main)
```

- `draft/` に古い中間ファイルがあると `compile.sh` は止まる。そのときは `make clean-tex` を実行してから
  やり直す。`draft/` の中で `lualatex`・`bibtex` を手で実行しない。
- 失敗したら、ログ `draft/build/main/main.log` の最初の `! ` で始まる行か `ファイル:行: ` の形の行から原因を特定し、
  平易な言葉で報告して**ここで止まる**(ビルドの誤りを先に直す)。
- 送る版を確かめるなら `make pdf-review`(ログは `draft/build/review/review.log`)、提出の前なら
  `make submission` まで進める。

### 2. 整合性を検査する

```bash
make check          # python3 tools/thesis_check.py --all(main・review・supplementary)
```

提出の前は `make check-final`(`python3 tools/thesis_check.py --main submission.tex --main supplementary.tex --submission --strict`。
提出版と補足資料を1回でまとめて厳格に検査し、どちらかで使う図・書誌は使われているとみなす。警告も失敗になる)。
各図表を作ったスクリプトの一覧は `python3 tools/thesis_check.py --list-generators` で出る。

### 3. 結果をまとめる

誤り・警告・情報に分けた表にし、各項目に `ファイル:行`、原因、**具体的な修正案**を添える。

| 記号 | 内容 | 直し方 |
|---|---|---|
| E1 / E2 | 参照先のラベルが無い / ラベルの重複 | ラベルの綴りを直す、ラベルを足す・付け替える |
| E3 | 引用キーが `reference.bib` に無い、またはその文書に `\bibliography` が無い | 文書に `\bibliography` が無ければ `\bibliography{reference}` を足す。キーが無ければ DOI で原典を確かめてから項目を足す。確かめられなければ「出典が必要」と報告する(捏造しない) |
| E4 | 図のファイルが見つからない | その図を作るスタディのスクリプトを実行する(`--list-generators`) |
| E5 | 読み込むファイルが無い | パスを直すか、ファイルを作るスクリプトを実行する |
| E6 / W8 | メタデータが未入力・雛形のまま | `draft/thesis-config.tex` を埋める(推測しない。ユーザーに確かめる) |
| E7 / I1 | TODO が残っている / TODO の一覧 | 片付けるか、ユーザーに残すかを確かめる |
| E8 | `\val`・`\valqty`・`\rawval` のキーが定義されていない | 値を書くスクリプト(`write_latex_values`)を実行し、そのファイルを `draft/values.tex` に登録する。キーの綴りを確かめる |
| E9 | 要旨・謝辞に本文が無い、または有効にした任意のページ(宣誓文・業績一覧・略語・記号)に雛形の文(行末が `% thesis:placeholder` の行)が残る(提出) | 本文を書く。任意のページは雛形の文を書き換えて印を消すか、`draft/thesis-config.tex` でそのページを無効にする |
| E10 | `projects/*/experiments/` や `projects/*/data/` の下を直接読み込んでいる | コードで `result/` へ昇格し、そこから読む |
| E11 | 値の定義が `\begin{document}` の後で読まれている | 章での `\input` をやめ、`draft/values.tex` に `\ThesisValues{…}` で登録する |
| W1 / W2 | 書誌のキーの重複 / 引用されない項目 | 重複を消す / 引用するか消す |
| W3 / W6 | 使われない図のファイル(`make check`・`make check-final` は検査する文書をまとめて調べるので、どの文書にも入っていない図)/ 同じ名前の図が複数の探索先にある | 不要な生成物を作るコードを直す / 名前を `<study>-<slug>` にする |
| W4 / W5 / W7 | 参照されない図表のラベル / ラベルの接頭辞 / 裸の `\ref` | 本文で `\cref` する / 接頭辞を直す / `\cref` にする |
| W9 / W10 / I2 | 重複したページのアンカー / はみ出した行 / ログの所見 | ログの該当箇所を直す |
| W11 | 図表・値に由来記録が無い、中身が記録と違う、または手作りの図が台帳に無い | 生成したスクリプトを実行し直す(`save_figure` などが記録を書く)/ `draft/figures/README.md` に行を足す |
| W12 | 同じ値のキーが2回定義されている | 値のファイルの登録の重複か、キーの重複を直す |
| W13 | 同じ DOI の書誌が2つある | 1つにまとめ、引用キーをそろえる |
| W14 | 撤回・中止・置き換えの実験、まだ「進行中」の実験、状態欄が状態の語で始まらない実験、索引に行の無い実験の生成物(提出では誤り)。由来記録の `sources` に記録した CSV や `data/processed/NNN_<slug>/` の元の実験も調べる | 有効な実験から作り直すか本文から外す。進行中なら、その `summary.md` と索引の行に答えを書く。昇格用スクリプトが読んだ CSV を `sources` に記録していなければ、記録するよう直す(記録しないと W14 は元の実験を調べられない) |
| W15 | 未コミットのコード(そのスタディの `src/`・`scripts/`・`config.py`・`experiments/` の `.py`、ルートの `config.py`・`pyproject.toml`・`uv.lock`)、実行中に変わったコード、またはコミット不明で作った生成物(提出では誤り)。実験の `run.py` が実行中にコードが変わった後に書いた生成物も W15 | コードをコミットし、実行中はコードを変えずにスクリプトを実行し直す(実験は `--overwrite` 付きで) |
| W16 | `result/` のファイル名が `<study>-` で始まらない | 名前を直してコードで作り直す |
| W17 | `draft/values.tex` に登録した値のファイルが無い(提出では誤り) | そのファイルを書くスクリプトを実行する |
| I3 | R3(そのまま載せた画像・書き写した数値)の一覧 | 誤りではない。ユーザーに示し、作り直せるものは作り直す |
| I4 | `verified` の欄が無い書誌(提出では誤り) | DOI で原典と照合し、`verified = {YYYY-MM-DD, doi:…}` を付ける |

**直し方の原則**: 図表・数値の誤りは、スタディのスクリプトや実験を Docker で実行し直して直す
(`docker compose exec research-template uv run python projects/<study>/…`。完了した実験は `--overwrite` 付きで)。
**`result/` の下のファイルを手で作ったり編集したりしない。** 由来記録(`.provenance.json`)も手で書かない。

### 4. 直して再実行する

ユーザーが直すことを望んだら適用し、誤りが 0 になるまで手順 1〜3 を繰り返す。終わったら、PDF のパスと
ページ数、最後の集計(誤り 0 / 警告 N / TODO M、I3 の件数)を報告する。
