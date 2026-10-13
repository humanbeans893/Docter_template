# 貢献の手引き

## 作業の流れ

1. `main` から作業用のブランチを作ります。
2. 変更に見合う検証を行います: 原稿は `make pdf check`、Python・文書・設定は `make test lint`、公開に関わる変更は `make security`。テストは、実際に起きた不具合と守るべき制約に対してだけ足します。
3. pull request を作り、CI が通り、未解決のコメントが無いことを確かめます。本文には目的、主な変更、利用者への影響、行った検証を書きます。

`main` への直接の push と force push はしません。構成や運用を変えたら `README.md` と `AGENTS.md` を一緒に直し、影響の大きい判断は `docs/decisions/` に残します。

## コミットしないもの

研究データ、個人情報、資格情報、`.env`、文献の PDF、文献管理ソフト(Zotero など)のデータベース、`external/`、ホストの絶対パス。追跡するファイルは 1 MB まで(`projects/*/figures/` だけ 10 MB まで)です。

## 書誌

書誌は `draft/reference.bib` だけで管理します。文献管理ソフトから BibTeX で書き出したものを受け取り、各項目を DOI などで原典と照合してから `verified` の欄を付けて足します(`AGENTS.md` の「文献」)。
