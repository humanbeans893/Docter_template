# Dissertation manuscript

英文本体・日英要旨の博士論文を LuaLaTeX + `ltjsreport` で構築します。大学固有の提出要項は [SUBMISSION_CHECKLIST.md](SUBMISSION_CHECKLIST.md) と照合してください。

## Build interface

```bash
make pdf             # draft/main.pdf（リンク色・TODO表示あり）
make pdf-final       # draft/submission.pdf（提出表示）
make supplementary   # draft/supplementary.pdf
make check           # 通常の整合性検査
make check-final     # プレースホルダー、TODO、警告も失敗
make submission      # pdf-final + check-final
make clean-tex       # PDF以外の中間ファイルを削除
```

`latexmk` がなければ Makefile が LuaLaTeX → BibTeX → LuaLaTeX×2 へフォールバックします。

## Configuration

題目、著者、学位、所属、指導教員、提出日、キーワード、余白、行間、任意ページは `thesis-config.tex` だけで設定します。表紙や `main.tex` に値を重複させないでください。

任意ページのフラグ:

```latex
\ThesisIncludeDeclarationtrue
\ThesisIncludePublicationstrue
\ThesisIncludeAbbreviationstrue
\ThesisIncludeSymbolstrue
\ThesisPrintListOfFigurestrue
\ThesisPrintListOfTablestrue
```

図目次・表目次は、対応する図表を追加してから有効にします。

## Structure

| Path | Purpose |
|---|---|
| `main.tex` | 通常執筆版の文書構成 |
| `submission.tex` | TODOを非表示にする提出版入口 |
| `thesis-config.tex` | メタデータ、提出ページ、レイアウト |
| `preamble.tex` | 共通パッケージ、PDF設定、図の探索先 |
| `frontmatter/` | 表紙、日英要旨、謝辞、任意ページ |
| `chapters/` | 一般序論、study章、総合考察 |
| `backmatter/` | 付録 |
| `notation.tex` | 論文全体の記号マクロ |
| `reference.bib` | Zoteroから同期する共有文献DB |

表紙は無番号、前付けはローマ数字、本文はアラビア数字です。

## Labels and references

ラベル接頭辞は `ch:`, `sec:`, `subsec:`, `fig:`, `tab:`, `eq:`, `alg:`, `app:`。参照は `\cref` を使い、裸の `\ref` は使いません。

## Figures and tables

- 解析図は study のスクリプトから `projects/<study>/result/figures/` へ生成します。
- ファイル名は `<study>-<slug>` とし、本文ではパス・拡張子なしで参照します。
- 表は `write_latex_table` で生成し、`\input{../projects/<study>/result/tables/...}` します。
- `result/` 内の生成物を手編集しません。

## Bibliography

Zotero + Better BibTeX から `reference.bib` へ自動エクスポートします。citation key は `authYYYYfirstword` を使用し、`file`, `local-url`, `annotation` などの私的・端末固有フィールドを除外します。詳細は [../docs/integrations.md](../docs/integrations.md) を参照してください。

雛形の `lamport1994latex` と `\nocite` は、最初の実引用を追加した時点で削除します。引用情報を推測で作成しないでください。

## Submission mode

`make submission` は提出PDFを作成後、未入力メタデータ、空の要旨、TODO、未定義参照・引用、裸の `\ref`、ログ警告を検査します。雛形のままでは意図的に失敗します。
