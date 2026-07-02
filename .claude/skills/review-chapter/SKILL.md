---
name: review-chapter
description: Deep-review one thesis chapter (argument structure, methods-results consistency against the study's code and outputs, clarity) using parallel subagents, and write a dated report to docs/reviews/. Never edits the chapter itself.
---

# /review-chapter

章を3つの観点から並列レビューし、日付入りレポートを `docs/reviews/` に書き出す。**章そのものは編集しない**(修正の採否はユーザーが決める)。

使い方: `/review-chapter chapters/02-study1.tex`(章ファイル指定。省略時はどの章かを確認する)

## Steps

### 1. 対象の特定と読み込み

- 章ファイルと対応するスタディを特定する(`draft/main.tex` の \include 構成と章番号から判断)
- 以下を読む: 章本文全体 / `projects/<study>/scripts/`・`src/` の解析コード / `result/figures/`・`result/tables/` の生成物一覧 / `draft/notation.tex`

### 2. 並列サブエージェントによるレビュー

Task ツールで3系統のレビューを**並列**起動する。各エージェントには章全文と必要な文脈を渡し、Critical / Major / Minor のタグ付き所見(該当箇所の原文引用付き)を返させる:

1. **論証構成**: 各節が章の主張を前進させているか / IMRaD の流れ / 序論で立てた問いと結果・考察の対応 / 段落間の接続
2. **手法-結果の整合**: 本文の全ての主張が実際のスクリプト・図表に遡れるか / 本文中の数値が生成された表・図と一致するか / 図表の参照順序 / 根拠の示されていない結果がないか
3. **明瞭さと文体**: 曖昧・冗長な表現 / 時制の一貫性(例: Methods は過去形) / 用語・記号が `notation.tex` と一貫しているか

### 3. 引用の過不足

出典が必要なのに引用がない主張を列挙する。**引用を捏造しない** — 「ここに出典が必要」という指摘に留め、具体的な文献はユーザーか Zotero(/zotero-connect)で確認する。

### 4. レポート作成

`docs/reviews/YYYY-MM-DD-<chapter-slug>.md` に統合して書き出す:

- 総評(3行以内)
- Critical / Major / Minor 別の所見(「原文引用 → 修正案」の形式)
- 不足アーティファクトのチェックリスト(未生成の図表・未整備のデータ台帳など)

### 5. 報告

上位3件の課題をインラインで要約し、レポートのパスを示す。
