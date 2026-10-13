# 博士論文テンプレート

別々の研究リポジトリで進めた研究を集めて、博士論文(LuaLaTeX。本文は英語、要旨は和英)に仕上げるための雛形です。研究の取り込みや検査はコーディングエージェント(Claude Code・Codex CLI)に任せる前提で、エージェント向けの規約は [`AGENTS.md`](AGENTS.md) が正本です。大学・研究科の提出要項は含めていません。

## 流れ

```text
研究リポジトリ(実験・データ・計算・論文)
   │  読むだけ。コミット <repo>@<sha> から図・表・数値を写す(add-research スキル)
   ▼
research.json(研究の一覧 = 章の構成)
projects/<id>/(要約カード README.md・figures/・tables/・values.tex)
   │  \includegraphics・\input・\val
   ▼
draft/ → main.pdf・review.pdf(指導教員向け)・submission.pdf(提出版)
   │  make check
   ▼
make submission → make archive TAG=<tag>
```

1. [`docs/thesis-plan.md`](docs/thesis-plan.md) に論文の主張と研究課題を書く。
2. 研究ごとに、エージェントに「この研究リポジトリを取り込んで」と頼む。`research.json` に行が足され、`projects/<id>/` と章ができる。
3. 章を書き、`make pdf check`。指導教員には `make pdf-review` の版を送り、指摘は [`docs/feedback/`](docs/feedback/README.md) に記録する。
4. [`draft/SUBMISSION_CHECKLIST.md`](draft/SUBMISSION_CHECKLIST.md) を確かめて `make submission`、タグを付けて `make archive TAG=<tag>`。

## 必要なもの

- TeX Live(LuaLaTeX・BibTeX・日本語。Debian/Ubuntu なら `texlive-luatex texlive-lang-japanese texlive-latex-extra texlive-science`)
- Python 3.10 以上(`python3`。標準ライブラリだけの `tools/` が使う)と Git
- Docker Compose(テストと lint だけ)

## 初期設定

1. GitHub の「Use this template」で、**private** のリポジトリを作る(未発表の結果や、転載の許諾が要る図が入るため)。
2. [`draft/thesis-config.tex`](draft/thesis-config.tex) に題名・著者・学位・大学・研究科・専攻・指導教員・日付を書く。
3. `make pdf check` で雛形がビルドできることを確かめる。
4. (任意)研究リポジトリの手元のクローンを `mkdir -p external && ln -sfn "$(realpath <クローンの場所>)" external/<repo>` でつなぐ。Git 管理外で、エージェントは読むだけ。
5. (任意)テストを動かすなら `make build` の後に `make test`。

## 日常のコマンド

| コマンド | 内容 |
|---|---|
| `make pdf` | `draft/main.pdf` と `draft/supplementary.pdf` |
| `make pdf-review` | 指導教員・審査員向けの `draft/review.pdf`(行番号・ビルド印) |
| `make pdf-final` | 提出版の `draft/submission.pdf` |
| `make check` / `make check-final` | 原稿の整合性検査 / 提出用の厳格な検査 |
| `make submission` / `make archive TAG=<tag>` | 提出版を作って検査 / 提出物一式を `dist/<tag>/` に |
| `make clean-tex` | LaTeX の中間ファイルを消す |
| `make test` / `make lint` | テスト / ruff(コンテナ内) |
| `make security` | 公開前の検査(秘密情報・個人のパス・大きなファイル) |

`make help` で一覧が出ます。`draft/` の中で `lualatex` を手で実行しないでください。

## ライセンス

このリポジトリのコード・設定・文書・原稿の雛形は [MIT License](LICENSE) です。研究リポジトリや論文から写した図・表・文章、研究データ、第三者の素材には MIT License は適用されません。権利者・出版社の規程・共同研究の契約に従ってください。脆弱性の報告は [SECURITY.md](SECURITY.md)、貢献の手順は [CONTRIBUTING.md](CONTRIBUTING.md) にあります。
