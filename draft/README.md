# 博士論文の原稿(draft/)

LuaLaTeX と `ltjsreport` で組みます。本文は英語、要旨は和文と英文です。TeX はホストで動かし(コンテナには TeX がありません)、ビルドは必ず `make` か `bash draft/compile.sh` を通します。

## ビルド

```bash
make pdf                          # main.pdf と supplementary.pdf
make pdf-review                   # review.pdf(指導教員・審査員に送る版)
make pdf-final                    # submission.pdf(提出用)
make supplementary                # supplementary.pdf
make check                        # 参照・引用・図・数値・research.json の検査
make submission                   # submission と supplementary を作り、厳しい検査(make check-final)
make clean-tex                    # draft/build/ と、draft/ に残った中間ファイルを消す
```

中間ファイルは Git 管理外の `draft/build/<版>/` に書き、PDF だけを `draft/` に置きます。ログは `draft/build/<版>/<版>.log` です。失敗した版や未定義の参照・引用が残った版があると 0 以外で終わります。`draft/` で `lualatex` を手で実行しないでください(残った `.aux`・`.bbl` が次のビルドで黙って読まれます。`compile.sh` が止まったら `make clean-tex`)。

| PDF | 用途 | 違い |
|---|---|---|
| `main.pdf` | 執筆中の確認 | `\todo` の注記と色付きのリンク。各ページの左上に `Draft <コミット>[-dirty] <日付>` |
| `review.pdf` | 指導教員・審査員に送る | 表紙の後から行番号、行間 2.0。`\todo` は隠す。左上に `Review copy <コミット>[-dirty] <日付>` |
| `submission.pdf` | 提出 | 印も注記もない。未定義の値があるとビルドが止まる |
| `supplementary.pdf` | 製本しない補足資料 | 図表番号は S1, S2, ... |

## 体裁

一般的な博士論文の体裁です(特定の大学の様式ではありません)。

- 順序: 表紙 → 和文要旨 → Abstract → 謝辞 → 業績一覧 → 目次 → 図目次 → 表目次 →(略語・記号)→ 序論・研究の章・結論 → 参考文献 → 付録。
- 表紙は番号なし、前付けはローマ数字、本文の最初の章からアラビア数字。ページ番号は下中央。
- 用紙・文字の大きさ・余白・行間の既定値は `thesis-config.tex` にあります。見出しは本文と同じ書体の太字。
- 参考文献は番号順(natbib の `unsrtnat`)で、目次に載ります。

設定は `thesis-config.tex` だけで変えます: メタデータ(題目・著者・学位・大学・研究科・専攻・指導教員・日付・キーワード)、印刷するページ(`\ThesisIncludePublications`、`\ThesisPrintListOfFigures`、`\ThesisPrintListOfTables`、`\ThesisIncludeDeclaration`、`\ThesisIncludeAbbreviations`、`\ThesisIncludeSymbols`)、`\ThesisClassOptions`(用紙・文字の大きさ。両面印刷なら `twoside,openright`)、余白、行間。大学の要項があれば、それに合わせてここを変えます。

印刷するページの雛形の文(行末に `% thesis:placeholder`)は書き換えて印を消します。残っていると `make check-final` が E9 で止まります。

## 構成

| パス | 役割 |
|---|---|
| `main.tex` | 文書の構成(章の並び) |
| `review.tex`・`submission.tex` | 審査用・提出用の入口(`main.tex` を別の体裁で読む) |
| `supplementary.tex` | 製本しない補足資料 |
| `thesis-config.tex` | メタデータと体裁の切り替え |
| `preamble.tex` | パッケージ、書式、図の探索先、ビルドの印 |
| `values.tex` | `\val` の定義と、各研究の `values.tex` の登録 |
| `notation.tex` | 論文全体の記号のマクロ |
| `frontmatter/` | 表紙、要旨、謝辞、業績一覧、任意のページ |
| `chapters/` | 序論、研究の章、結論と、章の雛形(`_chapter-template.tex`・`_background-template.tex`) |
| `backmatter/` | 付録 |
| `figures/` | 手で作った図だけ(台帳 [figures/README.md](figures/README.md)) |
| `reference.bib` | 書誌の正本 |

## 章・図・表・数値

章・図・表・数値・ラベル・付録の書き方は [AGENTS.md](../AGENTS.md) の「原稿」に、書誌の決まりは「文献」にあります。

## 送る版と提出

1. コミットしてから `make pdf-review` で作ります(印に `-dirty` が付いた版は送りません)。送った時点に `review/YYYY-MM-DD` のタグを付け(本人が行う)、指摘は [../docs/feedback/](../docs/feedback/) に記録します。
2. 提出前に [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) を確かめ、`make submission` を誤り 0 にします。雛形のままでは意図的に失敗します。
