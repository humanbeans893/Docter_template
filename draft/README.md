# draft/ — 学位論文原稿の決まりごと

原稿は LuaLaTeX + `ltjsreport`(英語本文・日本語混在可)。**必ず `main.tex` を起点に全体をビルド**します。

## ビルド

```bash
make pdf        # リポジトリルートから(推奨)。→ draft/main.pdf
make check      # 参照・引用・図の整合性チェック
make clean-tex  # 中間ファイルの掃除(PDF は残る)
```

`latexmk` が未導入なら一度だけ `sudo apt install latexmk`(なくても `make pdf` は手動シーケンスに自動フォールバック)。直接叩く場合は `cd draft && latexmk`。付録の `supplementary.tex` は独立文書: `cd draft && latexmk supplementary.tex`。

ビルドが失敗したら `draft/main.log` の最初の `!` 行を見る。よくあるエラーの対処表は `.claude/CLAUDE.md` の Pipeline 節にあります。

## ファイル構成

| 場所 | 役割 |
|---|---|
| `main.tex` | 全体の組み立て(章の `\include`)。タイトル・著者もここ |
| `preamble.tex` | パッケージと設定。**新スタディの `\graphicspath` 追加はここ** |
| `notation.tex` | 論文全体で使う記号マクロの定義(1記号=1マクロ) |
| `chapters/NN-<study>.tex` | 各スタディの章。`_chapter-template.tex` をコピーして作る |
| `frontmatter/` `backmatter/` | 表紙・要旨・謝辞/付録 |
| `reference.bib` | 文献データベース(論文全体で1つ) |
| `figures/` | 原稿専用の図(概念図など)。**解析図はここに置かない** |

## ラベル規約

接頭辞を必ず付ける(`make check` が違反を警告します):

| 接頭辞 | 対象 | 例 |
|---|---|---|
| `ch:` | 章 | `\label{ch:ocean-heat}` |
| `sec:` / `subsec:` | 節 / 小節 | `\label{sec:ocean-heat-methods}` |
| `fig:` | 図 | `\label{fig:ocean-heat-trend}` |
| `tab:` | 表 | `\label{tab:ocean-heat-summary}` |
| `eq:` | 数式 | `\label{eq:heat-budget}` |
| `alg:` / `app:` | アルゴリズム / 付録 | `\label{app:a}` |

参照は**常に `\cref`**(`Figure 3` などの語を自動で付ける)。素の `\ref` は使わない。

```latex
\cref{fig:ocean-heat-trend} shows ...        % → Figure 3.1 shows ...
\cref{fig:a,fig:b,tab:c}                     % 複数まとめて参照可
```

## 図(Figures)

1. 図は各スタディのスクリプトが `save_figure()` で `projects/<study>/result/figures/` に生成する(手動配置しない)
2. ファイル名は **`<study>-<内容>`**(例: `ocean-heat-trend`)。全スタディの図が1つの `\graphicspath` 名前空間を共有するため、接頭辞なしは衝突する
3. 本文からは**パスなし・拡張子なし**で参照:

```latex
\begin{figure}[tbp]
  \centering
  \includegraphics[width=0.8\linewidth]{ocean-heat-trend}
  \caption{図の要点を1文で。}
  \label{fig:ocean-heat-trend}
\end{figure}
```

4. 新しいスタディを章にするときは `preamble.tex` の `\graphicspath` に1行追加:

```latex
\graphicspath{{figures/}{../projects/study1/result/figures/}{../projects/<study>/result/figures/}}
```

## 表(Tables)

スタディ側で `write_latex_table()` が生成した `.tex` をそのまま読み込む:

```latex
\input{../projects/ocean-heat/result/tables/ocean-heat-summary.tex}
```

生成された `.tex` は手で編集しない(先頭に生成元と「do not edit by hand」が記載されます)。数値を直したければスクリプトを直して再生成。

## 引用(Citations)

- 文献は `reference.bib` に集約。**推奨ワークフロー**: Zotero でコレクション管理 → Better BibTeX プラグインで `reference.bib` に自動エクスポート(WSL2 での接続は `/zotero-connect`)
- 引用キーは Better BibTeX の `authYYYYfirstword` 形式(例: `smith2020ocean`)
- 本文では `\citep{smith2020ocean}`(括弧付き)/ `\citet{smith2020ocean}`(主語として)
- **雛形の `lamport1994latex` はプレースホルダ**。最初の実引用を入れたら、`reference.bib` のエントリと `main.tex` の `\nocite{lamport1994latex}` を削除する
- 引用スタイルは `unsrtnat`(出現順・番号)。変更する場合は `main.tex` の `\bibliographystyle` を編集

## 数式・記号(Notation)

繰り返し使う記号は `notation.tex` に **1回だけ** `\newcommand` で定義し、本文ではマクロを使う。表記ゆれ(`RMSE` と `rmse` の混在など)を構造的に防ぐ。

## 下書きメモ(TODO)

```latex
\todo{単位を確認}                 % 余白メモ
\todo[inline]{この節は要再構成}   % 本文中の目立つメモ
```

- `make check` が TODO を一覧化するので、消し忘れは提出前に必ず捕まる
- **最終版**: `preamble.tex` の `\draftnotestrue` → `\draftnotesfalse` で全メモが一括非表示

## 章の追加手順(スタディ→章)

1. `chapters/_chapter-template.tex` を `chapters/NN-<study>.tex` にコピー
2. `main.tex` の `\include` 行を有効化(コメントを外して実名に)
3. `preamble.tex` の `\graphicspath` にスタディを追加
4. `make pdf && make check` で緑を確認
