# 博士論文テンプレート

複数の研究(スタディ)の実験・解析と、それらを章として束ねる博士論文の原稿を、一つのリポジトリで最後まで仕上げるための雛形です。これまでの実験結果も、由来を記録したまま論文の根拠として取り込めます。

- この **README.md は人間向けの入口**です。コーディングエージェント(Claude Code・Codex CLI など)向けの規約は [`AGENTS.md`](AGENTS.md) が正本です。
- 大学・研究科ごとの提出要項は含めていません。最新版の要項を正とし、[`draft/SUBMISSION_CHECKLIST.md`](draft/SUBMISSION_CHECKLIST.md) と照らし合わせてください。

## 目的と方針

1. **論文の数値・図・表はすべてコードから作る** — 本文に数値を手で書かず、スタディの結果(CSV)から生成した値を `\val{…}` で読み込みます。結果が変われば、要旨から結論まで同じ値に追従します。
2. **由来を残す** — 生成した図・表・数値には、作ったスクリプト・実験・コミット・再現性を記録したファイル(`.provenance.json`)が隣に付きます。`make check` が、由来の無い図、撤回した実験の図、未コミットのコードで作った図を見つけます(実験の CSV から図を描く昇格用スクリプトの図は、読んだ CSV を由来記録の `sources` に残したときだけ、元の実験までたどれます)。
3. **スタディは自己完結** — `projects/<study>/` がデータ・コード・実験・結果・テストを持ち、兄弟スタディのコードに依存しません。通常は1スタディが1章です。
4. **実験は番号付きで積み上げる** — 試行錯誤は `projects/<study>/experiments/NNN_<slug>/` に残し、終わった実験は書き換えません。今の結論は各実験の `summary.md` に書き、索引 `EXP_SUMMARY.md` で撤回も一目で分かるようにします。
5. **生データは不変** — `data/raw/` は手で編集せず、コンテナからは読み取り専用です。エージェントも書き込みません。
6. **実行環境は Docker + uv、原稿はホストの LuaLaTeX** — 依存はイメージ内の `/opt/venv` に置き、ホストに `.venv` を作りません。
7. **ファイルだけで再開できる** — 状態は `STATE.md`、論文の骨格は `docs/thesis-plan.md` に書き、チャットの記憶に頼りません。

## 全体の流れ

```text
 これまでの実験結果                         新しい実験
 (ユーザーがホストでコピー)                 make experiment
          │                                    │
          ▼                                    │
 projects/<study>/data/raw/legacy/<source>/    │
          │ make experiment-import             │
          ▼                                    ▼
 projects/<study>/experiments/NNN_<slug>/  projects/<study>/experiments/NNN_<slug>/
 (inputs.sha256 で照合 → R1/R2/R3)         (summary.md・README.md・run.py・params.py・out/)
          │                                    │
          └──────────────┬─────────────────────┘
                         │  run.py --smoke → 本実行。save_figure / write_latex_table /
                         │  write_latex_values / import_figure / run.promote が書いたものは、
                         ▼  本実行が最後まで通ったときだけ入る
          projects/<study>/result/{figures,tables}/   (+ <name>.provenance.json)
                         │  \includegraphics / \input / \val
                         ▼
          draft/  →  main.pdf ・ review.pdf ・ submission.pdf ・ supplementary.pdf
                         │  make check(参照・引用・図・数値・由来)
                         ▼
          make submission  →  make archive TAG=<tag>
```

## 必要なもの

- Docker Compose、Git
- ホストの Python 3.10 以上(`python3`。標準ライブラリだけの `tools/` を動かす `make check`・`make study`・`make experiment`・`make archive`・`make security` と、Claude Code の生データ保護フックが使います。macOS 標準の `/usr/bin/python3` は 3.9 なので、Homebrew などで新しい版を入れてください)
- ホストの TeX Live(LuaLaTeX、BibTeX、日本語。Debian/Ubuntu なら `texlive-luatex texlive-lang-japanese texlive-latex-extra texlive-science`)。ページ数の表示に `pdfinfo`(任意)
- `uv`(ホストで pre-commit を動かす場合だけ。`uvx pre-commit`)

## 初期設定

1. **リポジトリを作る。** GitHub の「Use this template」から作るのがおすすめです。
2. **名前を決める。** `pyproject.toml` の `name`・`description` と、この README の題名を書き換えます。名前を変えたら、最初のビルドの前に `make lock` で `uv.lock` を更新します(古いままだと `Missing workspace member` で止まります)。`docker-compose.yml` のサービス名 `research-template` は変えません(すべてのコマンドがこの名前を使います)。イメージ名はディレクトリ名から決まるので、他のリポジトリとは衝突しません。
3. **`.env` を用意する(任意)。** `cp .env.example .env`。GPU や外部の同期フォルダを使うマシンでは `COMPOSE_FILE`(と `EXTERNAL_FILES_DIR`)を書きます(下の「GPU と外部の同期フォルダ」)。`docker compose` を直接使うときの `UID`/`GID` もここに書けます。`make` は UID と GID を自動で渡します。
4. **イメージを作って起動する。**

   ```bash
   make build && make up
   make test        # 実行環境・読み取り専用の生データ・構造のテストが通れば完了
   ```

5. **古い中間ファイルを一度だけ消す。** 以前の版(latexmk で `draft/` の中にビルドしていた版)から移ってきた作業コピーでは、`draft/` に `.aux`・`.bbl` が残っています。`draft/compile.sh` はそれを見つけると止まるので、最初に一度 `make clean-tex` を実行します。
6. **原稿をビルドして検査する。**

   ```bash
   make pdf         # draft/main.pdf
   make check       # 雛形のままでも誤りが無いこと
   ```

7. **最初のコミット**をして、GitHub で `main` を保護します(「Git の運用」)。

## 論文を仕上げる流れ

1. **骨格を決める。** [`docs/thesis-plan.md`](docs/thesis-plan.md) に論文の主張(1〜2文)、研究課題(RQ)、独自の貢献、章とスタディの対応を書きます。以後の作業はこの表を基準に進めます。
2. **スタディを作る。** `TITLE='Study 2: …' make study NAME=<study>` が `projects/_template` を複製し、章のファイル、`draft/main.tex` の `\include`、図の探索先、生データの読み取り専用マウント、`docs/thesis-plan.md` の行をまとめて登録します。実行中のジョブが無いことを確かめてから `make up` でマウントを反映し、`make test` を通します。
3. **データを置く。** 生データを `projects/<study>/data/raw/<dataset>/` に置き(ホストで)、`data/README.md` の台帳に入手元・取得日・ライセンス・チェックサム・再入手の方法を書きます。
4. **実験を回す。** `make experiment STUDY=<study> SLUG=<slug>` で番号付きの実験を作り、問いと判定の規則を `summary.md` に書き、`run.py` を実装して Docker で `--smoke` → 本実行と進め、結論を `summary.md` と索引に書きます(経緯は実験の `README.md`)。
5. **これまでの結果を取り込む。** 下の「これまでの実験結果の取り込み」を参照してください。
6. **図・表・数値を論文へ昇格する。** `save_figure`・`write_latex_table`・`write_latex_values` で `result/` に書き出します。数値のファイルは `draft/values.tex` に一行で登録し、本文では `\val{<name>-<key>}` と書きます。
7. **章を書く。** 図は `\includegraphics{<study>-<slug>}`、表は `\input{../projects/<study>/result/tables/<name>}`、数値は `\val{…}`。章の最後の「Chapter Summary」で、どの研究課題に答え、次の章へどうつながるかを書きます。`docs/thesis-plan.md` の執筆状況を更新します。
8. **序論・結論・要旨を合わせる。** 結論で各研究課題に答え、要旨の数値も `\val` で章と同じ値を使います。
9. **指導教員に見てもらう。** `make pdf-review` で行番号とビルド印(コミットと日付)の付いた版を作り、送った時点に `review/YYYY-MM-DD` のタグを付けます。受けた指摘は [`docs/feedback/`](docs/feedback/README.md) に記録して一つずつ対応します。
10. **全体を見直す。** Claude Code の `/review-thesis`(全体の一貫性)と `/review-chapter`(1章)で査読し、`make check` の警告を片付けます。
11. **提出する。** 要項と [`draft/SUBMISSION_CHECKLIST.md`](draft/SUBMISSION_CHECKLIST.md) を確かめ、`make submission` を通します(提出版と補足資料を1回の検査でまとめて調べます)。次に、すべてをコミットしたきれいな作業ツリーで、`python3 tools/thesis_check.py --list-generators` が出すコマンド(実験は `--overwrite` 付きで、上流が先に並ぶ)を上から順にすべて実行し直し、`git status --porcelain -- 'projects/*/result/*' ':(exclude)*.provenance.json'` が何も出さないことを確かめます。図・表・数値のファイルには日時もコミットも入らないので、同じコードからは同じファイルができます。由来記録(`*.provenance.json`)は作成日時とコミットだけが変わるので、確かめたらコミットします。そのうえで提出版にタグを付け、`make archive TAG=<tag>` で提出物一式を残します。

## これまでの実験結果の取り込み

過去の結果は、残っているもの(コード・数値・画像・論文中の数値だけ)に応じて取り込み方を選びます。手順の全体は [`docs/importing-past-results.md`](docs/importing-past-results.md) にあり、エージェントは `import-results` スキルでこの手順を進めます。

| 再現性 | 意味 | 典型例 |
|---|---|---|
| R1 再計算可能 | 入力とコードが残り、ここで計算し直して元の出力と一致を確かめた | 旧リポジトリのスクリプトを移植して再実行 |
| R2 再描画可能 | 数値の出力(CSV・JSON など)が残り、図表をここでコードから作り直した | 旧 `results/*.csv` から図を作り直す |
| R3 再生成不可 | 画像や論文中の数値しか残っておらず、そのまま載せた | 装置が出力した画像、元データが失われた図 |

```bash
make experiment-import STUDY=<study> SLUG=<slug> SOURCE=<source> FROM=<過去の結果のパス>
# 表示されたコピーのコマンドを、ユーザーが自分の端末で実行する(生データの置き場には本人だけが書く)
```

## 日常のコマンド

| コマンド | 内容 |
|---|---|
| `make build` / `make up` / `make down` | イメージを作る / 起動・作り直し / 停止(作り直すと実行中のジョブが止まる。GPU と `/external` は `.env` の `COMPOSE_FILE` で) |
| `make lock` | `uv.lock` を更新(`uv add` の後は `make lock && make build`) |
| `make test` / `make lint` / `make format` | テスト / ruff の検査 / 自動修正(すべてコンテナ内) |
| `TITLE='…' make study NAME=<study>` | 新しいスタディと章を作って登録(章の無いスタディは `NOCHAPTER=1`) |
| `make experiment STUDY=<study> SLUG=<slug>` | 新しい実験(`SUMMARY='…'` で問いの要約を `summary.md` と README の題に) |
| `make experiment-import STUDY=<study> SLUG=<slug>` | 過去の結果を取り込む実験(`SOURCE`・`FROM`・`LEGACY_ID` を指定できる) |
| `make pdf` / `make supplementary` | `draft/main.pdf` / `draft/supplementary.pdf` |
| `make pdf-review` | 指導教員・審査員向けの `draft/review.pdf`(`ONLY=02-study1` で章だけ) |
| `make pdf-final` | 提出表示の `draft/submission.pdf` |
| `make check` / `make check-final` | 原稿の整合性検査 / 提出用の厳格検査(提出版と補足資料を1回でまとめて検査) |
| `make submission` | 提出版と補足資料をビルドして厳格検査 |
| `make archive TAG=<tag>` | 提出物一式(PDF・ソース・データのマニフェスト)を `dist/<tag>/` に |
| `make clean-tex` | LaTeX の中間ファイルを消す(PDF は残す) |
| `make security` / `make security-history` | 公開前の秘密情報・大容量ファイルの検査 / 履歴のメールも検査 |

Python は `docker compose exec research-template uv run python <script>`、テストの一部は `docker compose exec research-template uv run pytest projects/<study>` で実行します。ホストでは `python`・`pip`・`uv` を実行しません(ホストの `python3` は標準ライブラリだけの `tools/` 用、`uvx` は pre-commit 用です)。Claude Code ではコミットしてある `.claude/settings.json` がこれらを拒否し、Codex には同じ仕組みが無いので `AGENTS.md` の規則で守ります。原稿は `bash draft/compile.sh [main|review|submission|supplementary|all]` でも作れます(中間ファイルは `draft/build/<job>/`)。`draft/` の中で `lualatex` を手で実行しないでください。コンテナはポートを公開しません(ほかのプロジェクトのコンテナとポートが重ならないようにするためです)。

### GPU と外部の同期フォルダ

ベース構成は CPU だけで、`/external` もありません。使うマシンでは `.env` に一度だけ書けば、以後の `docker compose` と `make` はすべてその構成で動きます。起動はいつも `make up` です。NVIDIA GPU を使うマシンでは:

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml
```

外部の同期フォルダを `/external` に読み取り専用で付けるマシンでは(GPU も使うなら `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml:docker-compose.files.yml`):

```dotenv
COMPOSE_FILE=docker-compose.yml:docker-compose.files.yml
EXTERNAL_FILES_DIR=/absolute/path/to/synced/research-files
```

`-f docker-compose.gpu.yml` などを1回のコマンドに付けて起動するだけでは、次に `make up`(`make study` や `uv add` の後など)を実行したときや、`make test` がコンテナを自動で起動したときに、GPU や `/external` の無いコンテナに黙って作り直されます。`COMPOSE_FILE` を変えたら、実行中のジョブが無いことを確かめて `make up` します。外部の同期フォルダの扱いは [`docs/integrations.md`](docs/integrations.md) にあります。

## 構成

```text
.
├── projects/                  # 研究スタディ(1スタディ = 通常1章)
│   ├── _template/             # 新しいスタディの雛形(make study が複製する)
│   └── <study>/
│       ├── data/              # raw/(不変。過去の結果は raw/legacy/)・interim/・processed/・README.md(台帳)
│       ├── experiments/       # 番号付き実験 NNN_<slug>/{summary.md, README.md, run.py, params.py, out/}、EXP_SUMMARY.md(索引)、JOBS.md(長時間ジョブ)
│       ├── src/               # 再利用コード(utils/ に図・表・数値・由来の補助関数)
│       ├── scripts/           # 薄い実行入口・昇格用スクリプト
│       ├── result/            # 論文に使う図・表・数値(コードが書く。手で編集しない)
│       ├── tests/             # スタディのテスト(複製した直後から通る)
│       └── config.py          # スタディ内のパス(結果を変えうる値は実験の params.py に置く)
├── draft/                     # 博士論文(LuaLaTeX)。main / review / submission / supplementary
│   ├── chapters/              # 序論・各スタディの章・結論、章と背景章の雛形
│   ├── frontmatter/           # 表紙・要旨(和英)・謝辞・業績など
│   ├── backmatter/            # 付録
│   ├── figures/               # 手作りの図だけ(台帳 README.md)
│   ├── values.tex             # 生成した数値ファイルの登録
│   └── compile.sh             # ビルド(中間ファイルは draft/build/)
├── docs/                      # 論文計画・取り込みの手引き・繰り返さないこと・案・研究ログ・意思決定記録・レビュー・指摘
├── tools/                     # 標準ライブラリだけのツール(原稿の検査、スタディ・実験の作成、提出物の保存、公開前の検査)
├── tests/                     # リポジトリ全体の構造と制約のテスト
├── .claude/ ・ .agents/        # Claude Code と Codex のスキル
├── STATE.md                   # 運用状態(セッションの最初に読む)
├── AGENTS.md                  # エージェント向けの規約の正本
├── CLAUDE.md                  # AGENTS.md への参照だけ
├── Makefile                   # 日常のコマンド
├── Dockerfile・docker-compose*.yml・pyproject.toml・uv.lock
└── config.py                  # 全章の図の体裁(VISUALIZATION)と物理定数(GEO)。結果を変えうる値は置かない
```

詳しくは [`projects/README.md`](projects/README.md)、[`draft/README.md`](draft/README.md)、[`docs/README.md`](docs/README.md) を参照してください。

## 文書の役割

| ファイル | 役割 | 更新のきっかけ |
|---|---|---|
| `README.md` | 人間向けの入口(方針・手順・コマンド) | 構成や手順を変えたとき、`AGENTS.md` と同時に |
| `AGENTS.md` | エージェント向けの規約の正本。各情報の正本の一覧(「単一の正本」)もここ | 運用の規則を変えたとき |
| `CLAUDE.md` | `AGENTS.md` への参照だけ | 内容を足さない |
| `STATE.md` | 運用状態(段階・現在の焦点・実行中のジョブ・決定・次の作業) | 状態が変わったその場で。報告の前と長時間ジョブの前は `write-handoff` で。6000字以内 |
| `docs/thesis-plan.md` | 論文の骨格(主張・研究課題・貢献・章と根拠の対応・執筆状況) | 章の対応や執筆状況が変わったとき。8000字以内 |
| `docs/guardrails.md` | 撤回した主張と、繰り返さない失敗 | 撤回や失敗が起きたその場で。8000字以内 |
| `projects/<study>/experiments/EXP_SUMMARY.md` | 実験の索引と状態(撤回を含む)。状態はここが正で、各 `summary.md` にも同じ語で書く | 実験を作ったとき、結論が変わったとき。10000字以内、索引の行は1行200字以内 |
| `projects/<study>/experiments/NNN_<slug>/summary.md` | 今の結論 | 作ったとき・本実行の後・結論が変わったとき。50行・3000字まで |
| `projects/<study>/experiments/NNN_<slug>/README.md` | 経緯の記録(追記だけ。目的・方法・結果・考察・由来) | 作ったときと、意味のある実行のたび |
| `docs/` | 研究ログ・意思決定記録・繰り返さないこと・案・レビュー・指摘への対応 | 随時(使い方は [`docs/README.md`](docs/README.md)) |

文字数の上限があるのは、セッションの最初に毎回読む4つの文書と、各実験の `summary.md` です(行数ではなく文字数で数えるので、行を長くしても収まりません。`tests/test_repo_structure.py` が検査します)。各情報の正本は1か所だけで、同じ表を複数のファイルに持ちません。チャットの内容は次のセッションにも、もう一方のエージェントにも残らないので、残す価値のあることはその場でファイルに書きます。構成・実行環境・手順を変えたら `README.md` と `AGENTS.md` をセットで直します。

## Git の運用

- `main` は保護ブランチです(PR 必須・承認1人・force push 禁止・ブランチ削除禁止)。作業は `agent/<slug>` などのブランチで行い、PR でマージします。
- PR では CI(Python のテスト・lint・公開前の検査と、原稿の全ビルドと検査)が通ることを確かめます。
- 指導教員・審査員に送った版には `review/YYYY-MM-DD`、提出した版にはタグを付けます(タグの作成と push は本人が行います)。前回の版からの差分は `git diff --word-diff review/<日付> -- draft/chapters draft/frontmatter` で見られます。
- このテンプレートから作ったリポジトリでも、最初の push の後に保護を設定します。

  ```bash
  gh api repos/<owner>/<repo>/rulesets -X POST --input - <<'JSON'
  {
    "name": "protect-main",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [
      { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request" }
    ],
    "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
    "rules": [
      { "type": "deletion" },
      { "type": "non_fast_forward" },
      { "type": "pull_request",
        "parameters": {
          "required_approving_review_count": 1,
          "dismiss_stale_reviews_on_push": false,
          "require_code_owner_review": false,
          "require_last_push_approval": false,
          "required_review_thread_resolution": false } }
    ]
  }
  JSON
  ```

- 生データ、`.env`、資格情報、文献管理ソフトのデータベース、文献の PDF はコミットしません。公開前に `make security` を実行し、脆弱性は公開の Issue ではなく [SECURITY.md](SECURITY.md) の手順で報告してください。貢献の手順は [CONTRIBUTING.md](CONTRIBUTING.md) にあります。

## ライセンス

このリポジトリのコード、設定ファイル、文書と原稿の雛形は [MIT License](LICENSE) で公開しています。

このテンプレートから作ったリポジトリに後から加える研究データ、論文の原稿、図表、第三者に由来する素材(過去の論文の図、転載した画像など)には、MIT License が自動的に適用されるわけではありません。それぞれの権利者、データの提供元、共同研究の契約、倫理審査、出版社の規程に従って、公開範囲とライセンスを個別に決めてください。

## エージェントのスキル

Claude Code は `.claude/skills/`、Codex は `.agents/skills/` からスキルを読み込みます。どちらも先頭に YAML の見出し(`name`・`description`)が要ります。両方に置くスキルは同じ内容で、テストが一致を検査します。

- **`write-handoff`**(両方) — 完了の報告の前、長時間ジョブの前、状態が大きく変わったときに `STATE.md` を更新し、次のセッションがファイルだけで再開できるようにします。
- **`import-results`**(両方) — 過去の実験結果を、由来と再現性を記録しながら取り込み、章へつなぎます。
- **`thesis-check`**(両方) — PDF をビルドして整合性検査を行い、修正案つきでまとめます。
- **`research-log`**(両方) — 結果・判断・行き止まりを研究ログと意思決定記録に、繰り返さない失敗と撤回を `docs/guardrails.md` に記録します(撤回・訂正・置き換えの手順は `AGENTS.md` の「実験」)。
- **`/review-chapter`**(Claude Code) — 1章を論証・方法と結果の整合・文体の観点から並列で査読します。
- **`/review-thesis`**(Claude Code) — 論文全体の一貫性(研究課題と答え、要旨と結果、貢献と根拠、用語、章のつながり)を並列で査読します。

査読の2つは Claude Code のサブエージェントを並列に使うので、Claude Code だけに置いています。作業の状態は Claude のメモリではなく `STATE.md` に書くので、どちらのエージェントからも、別の端末の複製からも再開できます。
