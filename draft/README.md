# 博士論文の原稿(draft/)

英文の本文と日英の要旨からなる博士論文を、LuaLaTeX と `ltjsreport` で組みます。TeX はホストで動かし(コンテナには TeX がありません)、ビルドは必ず `make` か `bash draft/compile.sh` を通します。大学固有の提出要項は [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) と照らし合わせてください。

## ビルド

```bash
make pdf                          # draft/main.pdf と draft/supplementary.pdf
make pdf-review                   # draft/review.pdf(指導教員・審査員に送る版)
make pdf-review ONLY=02-study1    # draft/review-02-study1.pdf(1章だけ)
make pdf-final                    # draft/submission.pdf(提出用の版)
make supplementary                # draft/supplementary.pdf
make check                        # main・review・supplementary の整合性検査
make check-final                  # 提出用の厳しい検査(submission と supplementary を合わせて1回で)
make submission                   # submission と supplementary を作り、check-final を実行
make clean-tex                    # draft/build/ と draft/ に残った中間ファイルを消す(PDF と図は残す)
```

`make` の各ターゲットは `draft/compile.sh` を呼びます。直接使う場合は、作る版を並べます。

```bash
bash draft/compile.sh                        # main と supplementary(引数なしのとき)
bash draft/compile.sh main review            # 複数の版を順に
bash draft/compile.sh review --only 02-study1,03-study2
bash draft/compile.sh all                    # main review submission supplementary
bash draft/compile.sh --help
```

`compile.sh` は版ごとに `lualatex` → `bibtex`(参考文献があり、何かを引用している文書だけ) → `lualatex` → `lualatex` を実行します。中間ファイルはすべて Git 管理外の `draft/build/<版>/` に書き、PDF だけを `draft/` に置きます。画面にはエラー(ファイル名と行番号)だけを出し、記録は `draft/build/<版>/<版>.log` に残します(`make check` はこのログを読みます)。終わると `Built draft/main.pdf (11 pages)` のようにページ数を表示します。

- 1つの版が失敗しても、残りの版は作ります。失敗した版があれば、最後に `Failed: ...` と表示して 0 以外で終わります。
- 未定義の参照や引用が残っていると、PDF を書いたうえで 0 以外で終わります。
- `lualatex` と `bibtex` の1回の実行は `THESIS_TEX_TIMEOUT` 秒(既定 600)で打ち切ります。止まったままにはなりません。打ち切られた版、途中で止められた版、エラーで止まった版は、次のビルドで `draft/build/<版>/` を消して最初から作り直します(途中で切れた中間ファイルを読まないためです)。
- 使い方の誤りや、`draft/` に古い中間ファイルがあるときは 2 で終わります。

`draft/` の中で `lualatex` を手で実行しないでください。そこに残った `.aux` や `.bbl` が次のビルドで黙って読まれ、参照や参考文献が欠けた PDF ができます。`compile.sh` はそのようなファイルが `draft/` にある間はビルドを断るので、`make clean-tex` で消してから作り直します。

**以前の版から移行する場合**: `latexmk` でビルドしていた作業コピーには `draft/` に中間ファイルが残っています。最初に一度 `make clean-tex` を実行してください。

### 4種類の PDF

| PDF | 入口 | 用途 | 違い |
|---|---|---|---|
| `main.pdf` | `main.tex` | 執筆中の確認 | `\todo` の注記と色付きのリンクを表示。各ページの左上に `Draft <コミット>[-dirty] <日付>` |
| `review.pdf` | `review.tex` | 指導教員・審査員に送る | 表紙の後から行番号、行間 2.0(`\ThesisReviewLineSpacing`)。`\todo` は隠し、リンクは黒。左上に `Review copy <コミット>[-dirty] <日付>` |
| `submission.pdf` | `submission.tex` | 提出 | 注記も印もない。未定義の値や、まだ生成していない値のファイルがあるとビルドが止まる |
| `supplementary.pdf` | `supplementary.tex` | 製本しない補足資料 | 図表番号は S1, S2, ... |

本文はどの版でも同じで、`thesis-config.tex` の `\ifThesisFinal` と `\ifThesisReview` が体裁だけを切り替えます。印の `-dirty` は、作業ツリーに未コミットの変更があることを示します。

1章だけの審査用の版(`--only`、`make pdf-review ONLY=...`)は、`main.tex` の `\include` のうち指定した章だけを組みます。章番号・ページ番号・目次・他章への参照は全体の版と同じになります。そのために、全体の審査用の版(`draft/build/review/`)が原稿や `projects/*/result/` より古いときは、先にそれを作り直します。`--only` には `chapters/` 以下のファイル名(拡張子なし)か、`backmatter/appendix-a` のようなパスを書きます。

## 設定

題目、著者、学位、所属、指導教員、提出日、キーワード、余白、行間、任意のページは `thesis-config.tex` だけで設定します。表紙や `main.tex` に値を重複させないでください。

任意のページのフラグ:

```latex
\ThesisIncludeDeclarationtrue
\ThesisIncludePublicationstrue
\ThesisIncludeAbbreviationstrue
\ThesisIncludeSymbolstrue
\ThesisPrintListOfFigurestrue
\ThesisPrintListOfTablestrue
```

図目次・表目次は、対応する図表を追加してから有効にします。審査用の版の行間は `\ThesisReviewLineSpacing` で変えます。

宣誓文・業績一覧・略語・記号のページを有効にしたら、`frontmatter/` の該当するファイルで、行末に `% thesis:placeholder` が付いた雛形の文を書き換え、その印を消してください。印が残っていると `make check-final`(`make submission`)が E9 で止まります。

## 構成

| パス | 役割 |
|---|---|
| `main.tex` | 文書の構成(執筆中の版) |
| `review.tex` | 審査用の版の入口 |
| `submission.tex` | 提出用の版の入口 |
| `supplementary.tex` | 製本しない補足資料 |
| `compile.sh` | ビルド(上記) |
| `thesis-config.tex` | メタデータ、任意のページ、余白・行間、版の切り替え |
| `preamble.tex` | 共通のパッケージ、PDF の設定、図の探索先、ビルドの印 |
| `values.tex` | 生成した数値(`\val`)の定義と、値のファイルの登録 |
| `notation.tex` | 論文全体の記号のマクロ |
| `frontmatter/` | 表紙、日英の要旨、謝辞、任意のページ |
| `chapters/` | 一般序論、スタディの章、総合考察 |
| `chapters/_chapter-template.tex` | スタディの章の雛形(`make study` が使う) |
| `chapters/_background-template.tex` | 背景章(任意)の雛形 |
| `backmatter/` | 付録 |
| `figures/` | 手で作った図だけ。台帳は [figures/README.md](figures/README.md) |
| `reference.bib` | 書誌の正本 |
| `build/` | 中間ファイル(Git 管理外) |

表紙は無番号、前付けはローマ数字、本文はアラビア数字です。

## 章の追加と順序

- **スタディの章**: `TITLE='Study 2: Title' make study NAME=study2` を実行すると、`tools/new_study.py` が `_chapter-template.tex` から `chapters/NN-study2.tex` を作り、`main.tex` の `% thesis:study-chapters:end` の直前に `\include` を足し、`preamble.tex` と `supplementary.tex` の `\graphicspath` に図の置き場所を足します。
- **章の順序**: 印刷される章番号は `main.tex` の `\include` の並び順で決まります。ファイル名の `NN-` は作った順の目印にすぎません。論の流れに合わせて行を並べ替え、本文では番号ではなくラベル(`\cref{ch:study2}`)で参照します。
- **背景章(任意)**: 文献のまとめ、理論の枠組み、複数のスタディで共通のデータと方法を1章にまとめる場合は、`_background-template.tex` を手で `chapters/background.tex` に写し、先頭の `template-only` の部分を消して、`main.tex` の `% \include{chapters/background}` のコメントを外します。ラベルは `ch:background`、`sec:background-*` に固定です。
- **論文を基にした章**: 章の冒頭のコメント(発表の状況、引用、著者の貢献、転載の許諾、発表版との違い、任意の `\section*{Chapter Abstract}`)を埋めます。手順は [../docs/importing-past-results.md](../docs/importing-past-results.md) の「既発表・投稿中の論文を章にする」にあります。
- 各章の最後の `\section{Chapter Summary}` には、その章が答える研究課題と、次の章へのつながりを書きます。研究課題・貢献・章の対応は [../docs/thesis-plan.md](../docs/thesis-plan.md) と食い違わないようにします。

## ラベルと参照

ラベルの接頭辞は `ch:`, `sec:`, `subsec:`, `fig:`, `tab:`, `eq:`, `alg:`, `app:` です。参照には `\cref` を使い、裸の `\ref` は使いません。スタディの章の中のラベルは `sec:<study>-...` のようにスタディ名を含めます。

## 図・表・本文の数値

- **解析の図**は、スタディのコードが `save_figure` で `projects/<study>/result/figures/` に書き出し、原稿はそこから直接読みます(`\graphicspath`)。過去の画像しか残っていない図は `import_figure` で取り込みます。ファイル名は `<study>-<slug>` とし、本文ではパスと拡張子なしで参照します(`\includegraphics{study1-overview}`)。
- **手で作った図**(模式図、写真など)だけを `draft/figures/` に置き、[figures/README.md](figures/README.md) の台帳に1行足します。解析の図をここへ写すと由来の記録を迂回するので、しないでください。
- **表**は `write_latex_table` で `projects/<study>/result/tables/` に書き出し、`\input{../projects/<study>/result/tables/<name>}` で読みます。
- `projects/*/experiments/*/out/` や `projects/*/data/` のファイルを原稿から直接読んではいけません(`make check` が誤りにします)。使う図表は、コードで `result/` に書き出します。
- `result/` の生成物は手で直しません。直すときはスタディのスクリプトを実行し直します。

### 本文の数値(`\val`)

本文・要旨・図表の説明文に、結果の数値を手で書きません。スタディのコードが `write_latex_values` で値のファイル `projects/<study>/result/tables/<name>.tex` を書き出し、本文はその値をキーで参照します。

1. 値のファイルを `values.tex` に1回だけ登録します(`% thesis:values:end` の行の上。`make study` はこの行を足しません)。

   ```latex
   \ThesisValues{../projects/study1/result/tables/study1-main}
   ```

   要旨は章より前に組まれるので、値は `\begin{document}` より前にすべて定義しておく必要があります。登録をここに集めるのはそのためです。章の中で値のファイルを `\input` しないでください。

2. 本文ではキー `<name>-<key>` で参照します。

   ```latex
   We analysed \val{study1-main-n} samples (slope \val{study1-main-slope}).
   The maximum depth was \valqty{study1-main-depth-max}{\metre}.
   ```

   `\val` は数値を siunitx の `\num` で組み(`12345.6` → 12 345.6、`1.2e-05` → 1.2 × 10⁻⁵、`0.82 +- 0.03` → 0.82 ± 0.03)、文字列の値はそのまま出します。単位の付く量は `\valqty{<キー>}{<単位>}`(siunitx の `\qty`)で書きます。`\rawval` は値の文字列そのものを返します(表や siunitx の細かい指定に使う)。

値が無いときの動き:

| 版 | 未定義のキー | まだ生成していない値のファイル |
|---|---|---|
| main・review | 警告を出し、本文に `??<キー>` と印を付ける | 警告 |
| submission | ビルドが止まる | ビルドが止まる |

`compile.sh` は、警告があった版について最後に `Note:` を表示します。どのキーが未定義かは `make check` で確かめます。

注意: `\qty{\rawval{...}}{...}` のように siunitx の引数の中で使った `\rawval` は、値が無いと main・review でも siunitx の「Invalid number」というエラーでビルドが止まります。単位の付く量には `\valqty` を使えば、値が無くても印を付けて組み続けます。

## 由来の記録と R3

スタディのコードが書き出す図・表・値には、それぞれ由来の記録 `<name>.provenance.json`(作ったスクリプト、実験の番号、作った日時とコミット、実験の中で作ったものは実行(開始時刻・シード・パラメータのハッシュ)、ファイルの sha256、再現性レベル、読んだファイル `sources`)が付きます。日時とコミットは由来の記録にだけ入り、図・表・値のファイルそのものには入らないので、作り直して結果が同じなら、ファイルも変わりません(提出前の確かめ方は [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) の「技術的な検証」)。`make check` は由来の記録を読み、記録の無い図や中身が記録と違う図、台帳に無い手作りの図、撤回・中止・置き換え・進行中の実験の生成物(昇格スクリプトが `sources` に記録した CSV からも元の実験をたどる)、未コミットのコードで作った生成物を指摘します。

再現性レベル R3(過去の画像をそのまま載せた図や、論文から書き写した数値)は、作り直せない意識的な例外です。`make check` が I3 として一覧にするので、指導教員と確かめ、他者の図なら転載の許諾も確かめます。過去の結果の取り込み方は [../docs/importing-past-results.md](../docs/importing-past-results.md) を参照してください。

## 書誌

- 書誌の正本は `reference.bib` だけです。文献管理ソフトとは同期しません。自分のライブラリの書誌が要るときは、BibTeX などで書き出して渡します(エージェントは文献管理ソフトに接続しません)。
- 書誌を足すときは、エージェントが見つけたものも渡されたものも、DOI から原典(出版社のページ、Crossref、PMC、保存版)と照合してから入れます。引用する数値も原文で確かめます。
- 照合したら `verified = {YYYY-MM-DD, doi:10.xxxx/...}` の欄を書きます。DOI が無ければ `isbn:` か公式ページの `url:` を使います。`make check` は `verified` の無い項目を挙げ(提出の検査では誤り)、同じ DOI の項目が重なっていれば警告します。
- citation key は `authYYYYfirstword`(例: `smith2020ocean`)。`file`、`local-url`、`annotation` など私的・端末固有の欄は消してから入れます。
- 雛形の `lamport1994latex` と `main.tex` の `\nocite` は、最初の本当の引用を足した時点で消します。書誌を推測で作らないでください。

詳しくは [../docs/integrations.md](../docs/integrations.md) を参照してください。

## 付録と補足資料

- 各スタディの補足情報は、まず論文の付録に入れます。スタディごとに `backmatter/appendix-<study>.tex`(先頭に `\chapter{...}` と `\label{app:<study>}`)を手で作り、`main.tex` の `\appendix` の後に `\include{backmatter/appendix-<study>}` を足して、章からは `\cref{app:<study>}` で参照します。
- `supplementary.tex` は、製本に入れられない資料(長い表、データの一覧など)だけに使います。図表番号は S1, S2, ... で、`\val` と図の探索先は本文と同じです。文献は本文と同じ `reference.bib` から `\citet`・`\citep` で引用でき、引用があれば補足資料の末尾に参考文献の一覧が付きます。本文から `supplementary.pdf` の中を参照しないでください。

## 指導教員・審査員に送る版と指摘への対応

1. 送る前にコミットします(印に `-dirty` が付いた版は送らない)。
2. `make pdf-review`(1章だけなら `make pdf-review ONLY=02-study1`)で版を作ります。各ページの印で、どのコミットの版かが分かります。
3. 送った時点に `review/YYYY-MM-DD` のタグを付けます(タグの作成と push は本人が行います)。
4. 受けた指摘は [../docs/feedback/](../docs/feedback/README.md) に1回分ずつ記録し、対応を追います。前回送った版からの差分は `git diff --word-diff review/YYYY-MM-DD -- draft/chapters draft/frontmatter` で示せます。

## 提出モード

`make submission` は提出用の PDF と補足資料を作り、未入力のメタデータ、空の要旨・謝辞、有効にした任意のページ(宣誓文・業績一覧・略語・記号)に残る雛形の文、TODO、未定義の参照・引用・値、裸の `\ref`、照合していない書誌、ログの警告などを厳しく検査します。雛形のままでは意図的に失敗します。提出前の確認項目は [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) にあります。

検査(`make check-final`)は、2つの文書を1回で合わせて調べます。

```bash
python3 tools/thesis_check.py --main submission.tex --main supplementary.tex --submission --strict
```

図や書誌の項目は、どちらかの文書で使っていれば使っているとみなします(本文でだけ使う図も、補足資料でだけ引く文献も、未使用とはされません)。警告も誤りとして扱うので、警告が1つでも残れば失敗します。
