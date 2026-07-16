# Contributing

## Workflow

1. `main` から feature branch を作成します。
2. 変更範囲に応じたテストを追加します。
3. `make test lint` を実行します。原稿変更では `make pdf check`、公開関連では `make security` も実行します。
4. pull request を作成し、CI と未解決コメントが残っていないことを確認します。

`main` への直接 push、force push、生成物の手編集は行いません。

## Data and privacy

- 生データ、個人情報、資格情報、Zotero DB、文献PDFを commit しないでください。
- 再現に必要なデータ情報は各 study の `data/README.md` に記録します。
- 研究結果の図表はスクリプトから再生成できる状態にしてください。

## Pull requests

PR本文には目的、主要変更、利用者への影響、実行した検証を記載してください。方法論やリポジトリ設計に影響する判断は ADR も追加します。
