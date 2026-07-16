# AGENTS.md

このファイルは Claude Code、Codex CLI など、このリポジトリで作業する全コーディングエージェントの共通規約です。

思考は英語、回答はユーザーの言語（既定は日本語）で行います。

## Repository contract

このリポジトリは、自己完結した複数の研究スタディと英語本文の博士論文を統合するモノレポです。

- `projects/<study>/`: 1スタディ分のデータ、コード、結果、テスト。
- `projects/_template/`: 新規スタディの正本。コピー可能性を壊さないこと。
- `draft/`: LuaLaTeX (`ltjsreport`) の博士論文と補足資料。
- `tools/thesis_check.py`: 原稿整合性チェック。
- `tools/public_repo_check.py`: 公開前の秘密情報・大容量ファイルチェック。
- `docs/`: 研究ログ、ADR、レビュー、外部連携ガイド。

兄弟スタディ間の依存は禁止します。共通化が必要でも、研究固有ロジックは各スタディ内に保ちます。

## Commands

```bash
make up              # Docker環境を起動
make sync            # uv.lockから同期
make test            # 全pytest
make lint            # Ruff（変更なし）
make format          # Ruff自動修正
make pdf             # draft/main.pdf
make supplementary   # draft/supplementary.pdf
make check            # 原稿整合性
make check-final      # 提出前厳格検査
make security         # 公開前検査
```

Pythonは Docker 内、LaTeXはホストで実行します。`tools/` の標準ライブラリのみのチェッカーはホスト実行可能です。

## Workflow

### Before editing

1. 対象ファイルと近傍の実装を読む。
2. `git status -sb` と現在ブランチを確認する。
3. `main` では作業せず、`agent/<slug>` などの feature branch を使う。
4. 研究上の判断、欠損データ、大学固有様式など、コードから決められない事項だけ確認する。

### Research code

- 再利用ロジックは `src/`、薄い実行入口は `scripts/` に置く。
- 必須入力は明示的に検証し、ダミー値や例外の握りつぶしで処理を続けない。
- 新しいロジックには対応する pytest を追加する。
- 図は `save_figure`、表は `write_latex_table` を使い、`result/` を手編集しない。
- 図表名は `<study>-<slug>` とし、全スタディ共通の名前空間で衝突させない。

### Data

- `data/raw/` は不変。エージェントによる書き込みを回避・迂回しない。
- `interim/` と `processed/` はスクリプトで再生成する。
- データ台帳に入手元、取得日、ライセンス、チェックサム、スキーマ、再取得方法を残す。
- 生データや大容量データを Git に追加しない。

### Manuscript

- `draft/main.tex` を起点に全体をビルドする。
- 論文メタデータは `draft/thesis-config.tex` のみで定義する。
- ラベルは `ch:`, `sec:`, `subsec:`, `fig:`, `tab:`, `eq:`, `alg:`, `app:` を使う。
- 参照は `\cref`、引用は `draft/reference.bib` に実在するキーだけを使う。
- 引用を捏造しない。候補が確認できない場合は出典が必要な箇所として報告する。
- 解析図は study の `result/figures/` から参照し、原稿側へコピーしない。
- 原稿変更後は `make pdf check`、提出前は `make submission` を実行する。

## Public repository security

- `main` への直接 push、force push、履歴改変はユーザーの明示指示なしに行わない。
- `.env`、資格情報、個人情報、未公開データ、Zotero DB、文献PDFを読み込んだりコミットしたりしない。
- 外部アプリの資格情報は環境変数または Git 管理外のクライアント設定に置く。
- 外部同期フォルダは原則読み取り専用でマウントする。
- GitHub Actions は最小権限と完全な commit SHA pinning を維持する。
- 公開前と push 前に `make security` と `git diff --check` を実行する。

## Verification

- Python変更: 対象テスト → `make test lint`。
- TeX変更: `make pdf check`。成功時は PDF パスとページ数を報告する。
- GitHub/CI変更: YAML構文、Action pin、PR上の全checkを確認する。
- 変更を push する前に、意図したファイルだけが staged されていることを確認する。

## Destructive and external actions

削除、データ上書き、パッケージ追加、履歴書き換え、GitHub公開範囲変更など、不可逆または外部影響の大きい操作は事前にユーザーの意図を確認します。通常のテスト、ビルド、読み取り専用調査は確認不要です。

## Repository skills

- `/thesis-check`: PDFビルドと原稿整合性検査。
- `/research-log`: 研究上の結果・判断・行き止まりを記録。
- `/review-chapter`: 章を論証・整合性・文体の観点でレビュー。
- `/zotero-connect`: WSL2からWindows ZoteroのローカルAPIへ接続。
