# Dissertation research template

複数の研究スタディ、再現可能な解析、博士論文原稿を一つのリポジトリで管理するためのテンプレートです。各スタディは自己完結し、生成した図表を LuaLaTeX 原稿が直接参照します。

```text
projects/<study>/data
        │
        ▼
projects/<study>/scripts ──► result/{figures,tables}
                                      │
                                      ▼
                              draft/main.tex ──► PDF
```

## Design

- **Study isolation**: `projects/<study>/` はデータ、コード、結果、テストを所有し、兄弟スタディへ依存しません。
- **Reproducible artifacts**: 図表はスクリプトから生成し、`result/` を手編集しません。
- **Integrated manuscript**: 各スタディを `draft/chapters/` の章として統合します。
- **Public by design**: 生データ、資格情報、文献PDF、アプリのデータベースを Git に含めません。
- **Protected delivery**: `main` は PR と CI を経由して更新します。

## Requirements

- Docker Compose
- Git
- LuaLaTeX、BibTeX（`latexmk` 推奨）
- `uv`（ホスト側の pre-commit 用）

Python の実行環境は Docker、TeX のコンパイルはホストを正とします。

## Commands

```bash
make up              # 解析コンテナを起動
make sync            # uv.lock から環境を同期
make test            # 全スタディを含む pytest
make lint            # Ruff lint + format check
make pdf             # draft/main.pdf
make supplementary   # draft/supplementary.pdf
make check            # 原稿の静的整合性検査
make check-final      # 提出前の厳格検査
make security         # 公開前の秘密情報・大容量ファイル検査
```

`make submission` は提出モード PDF を作成し、未入力メタデータ、TODO、警告が残っていれば失敗します。

## Repository layout

```text
.
├── projects/              # 自己完結した研究スタディ
│   ├── _template/         # 新規スタディの雛形
│   └── study1/
├── draft/                 # 博士論文・補足資料（LuaLaTeX）
├── docs/                  # 研究ログ、ADR、連携ガイド
├── tools/                 # 原稿・公開前チェッカー
├── tests/                 # リポジトリ構造のテスト
├── AGENTS.md              # 全コーディングエージェント共通規約
└── Makefile               # 公開コマンドインターフェース
```

詳細は [projects/README.md](projects/README.md)、[draft/README.md](draft/README.md)、[docs/integrations.md](docs/integrations.md) を参照してください。

## Study to chapter

```bash
cp -r projects/_template projects/<study>
docker compose exec research-template uv run pytest projects/<study>
```

1. 生データを `projects/<study>/data/raw/` に置き、`data/README.md` に入手元、ライセンス、チェックサム、再取得方法を記録します。
2. 再利用ロジックを `src/`、実行入口を `scripts/` に実装します。
3. 図表を `<study>-<slug>` の名前で `result/` に生成します。
4. 章テンプレートをコピーし、`draft/main.tex` と `draft/preamble.tex` に登録します。
5. `make test lint pdf check` を通します。

## Bibliography and external files

文献情報は Zotero + Better BibTeX から `draft/reference.bib` へ自動エクスポートできます。文献PDFやクラウド同期フォルダは追跡せず、必要な場合だけ読み取り専用でコンテナへマウントします。設定方法は [docs/integrations.md](docs/integrations.md) にあります。

## Contribution and security

- `main` へ直接 push せず、feature branch と pull request を使用してください。
- 生データ、`.env`、APIキー、Zoteroデータベース、文献PDFをコミットしないでください。
- コード変更は `make test lint`、原稿変更は `make pdf check`、公開前は `make security` を実行してください。
- 脆弱性は公開 Issue ではなく [SECURITY.md](SECURITY.md) の手順で報告してください。

貢献手順は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

[MIT License](LICENSE)
