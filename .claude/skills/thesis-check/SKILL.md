---
name: thesis-check
description: Build the thesis PDF and run manuscript consistency checks (references, citations, figures, TODOs), then summarize findings with concrete fixes. Use before sharing a draft or after substantial manuscript edits.
---

# /thesis-check

論文原稿をビルドし、整合性チェック(未定義参照・未引用文献・図の欠落・TODO)を実行して、結果を修正案付きで要約する。

## When to use

- 原稿を共有・提出する前の最終確認
- 章・図表・引用を大きく編集した後
- ユーザーが「論文チェックして」「原稿確認して」と言ったとき

## Steps

### 1. PDF ビルド

リポジトリルートで:

```bash
make pdf
```

- 失敗したら `draft/main.log` の最初の `!` で始まる行から原因を特定し、平易な言葉で報告して**ここで停止**する(ビルドエラーの修正が先)。
- よくあるエラーと対処は `draft/README.md` を参照。

### 2. 整合性チェック

```bash
make check
```

コンテナが止まっている場合のフォールバック: `python3 tools/thesis_check.py`

### 3. 結果の要約

Error / Warning / TODO をグループ化した表で提示する:

- 各 Error に `file:line`・原因・**具体的な修正案**を添える(label の typo 修正、reference.bib へのキー追加、図を生成するスクリプトの実行など)
- 図の欠落(E4)は `projects/<study>/scripts/` の該当スクリプトを実行して解決するのが原則。**`result/` 配下のファイルを手で作成・編集しない**

### 4. 修正と再実行

ユーザーが修正を望んだら適用し、Error が 0 になるまで手順 1〜3 を繰り返す。完了時に `draft/main.pdf` の場所と最終サマリ(0 errors / N warnings / M TODOs)を報告する。
