# Security policy

## Reporting a vulnerability

脆弱性、秘密情報の露出、個人情報・未公開研究データの混入を見つけた場合は、公開 Issue や pull request に詳細を書かないでください。

GitHub の **Security** タブから private vulnerability report を作成してください。利用できない場合は、リポジトリ所有者へ非公開の連絡手段で、影響範囲、再現手順、該当 commit を送ってください。資格情報そのものや研究データのコピーは添付しないでください。

受領後は内容を確認し、必要に応じて影響する資格情報の失効、履歴からの除去、修正版の公開を行います。

## Scope

- GitHub Actions、Docker、Python依存関係の脆弱性
- 生データ、文献PDF、Zoteroデータベース、個人情報の誤公開
- APIキー、トークン、秘密鍵などの資格情報
- 外部アプリ連携による意図しない書き込みやファイル公開

研究結果の誤りや通常の不具合は公開 Issue で報告できます。ただし、未公開データを含めないでください。

## Supported versions

このテンプレートは既定ブランチ `main` の最新版のみをサポートします。
