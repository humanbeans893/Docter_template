# 博士論文リポジトリテンプレート

複数の研究(スタディ)と学位論文原稿を **1つのリポジトリ** で管理し、**Claude Code(AIエージェント)と協働して** データ解析から論文 PDF の完成までを再現可能に進めるためのテンプレートです。

コーディングエージェントを使ったことがない人でも、この README の順番どおりに進めれば動くように書いてあります。

## 目次

1. [これは何?(全体像)](#1-これは何全体像)
2. [必要なもの](#2-必要なもの)
3. [初回セットアップ(約15分)](#3-初回セットアップ約15分)
4. [Claude Code と一緒に進める](#4-claude-code-と一緒に進める)
5. [研究の進め方(スタディ編)](#5-研究の進め方スタディ編)
6. [論文の書き方(原稿編)](#6-論文の書き方原稿編)
7. [コマンド早見表](#7-コマンド早見表)
8. [トラブルシューティング](#8-トラブルシューティング)
9. [ディレクトリリファレンス](#9-ディレクトリリファレンス)
10. [FAQ](#10-faq)

---

## 1. これは何?(全体像)

このリポジトリは3つの設計思想でできています。

1. **スタディは自己完結** — 研究テーマごとに `projects/<スタディ名>/` を作り、データ・コード・結果をその中で完結させる。他のスタディに依存しない。
2. **図表はコードから再生成** — 図や表は必ずスクリプトが `result/` に出力する。手で画像を修正しない。「この図どうやって作ったっけ?」を根絶する。
3. **原稿は結果を直接参照** — `draft/`(LuaLaTeX)は各スタディの `result/figures/` から図を直接読み込む。解析をやり直せば、次のビルドで論文の図も自動的に新しくなる。

```text
データ投入 → 解析スクリプト → result/figures・tables → draft/ が参照 → make pdf → 論文PDF
   ↑              ↑                                        ↑
 data/raw     src/ の関数を                            /thesis-check で
 (不変)      scripts/ から実行                         整合性チェック
```

Python は Docker コンテナ内で動くので環境構築の再現性があり、LaTeX はホスト(手元のマシン)でコンパイルします。

> **これはテンプレートです**: 実際の研究はこのリポジトリをコピーして作った自分のリポジトリで行ってください([FAQ](#10-faq) 参照)。

## 2. 必要なもの

| ツール | 用途 | インストール確認コマンド |
|---|---|---|
| Docker | Python 実行環境 | `docker --version` |
| git | バージョン管理 | `git --version` |
| TeX Live(LuaLaTeX) | 論文のコンパイル | `lualatex --version` |
| latexmk | LaTeX ビルド自動化(推奨) | `latexmk --version` |
| Node.js + Claude Code | AIエージェント | `claude --version` |
| uv | pre-commit 実行(任意) | `uvx --version` |

- **Docker**: [Docker Desktop](https://docs.docker.com/get-docker/)(Windows/Mac)または Docker Engine(Linux)。
- **TeX Live**: Ubuntu/WSL2 なら `sudo apt install texlive-full` が確実(容量大)。`latexmk` が入っていなければ `sudo apt install latexmk` を追加。
- **Claude Code**: [公式ドキュメント](https://docs.anthropic.com/en/docs/claude-code) に従い `npm install -g @anthropic-ai/claude-code`。
- **WSL2 の人へ**: このリポジトリは WSL2 内に置いてください(`/mnt/c/...` 配下はファイルアクセスが遅く不安定)。

## 3. 初回セットアップ(約15分)

### 3-1. 自分のリポジトリを作る

GitHub 上でこのテンプレートから新しいリポジトリを作成し(`Use this template` ボタン、なければ clone して remote を差し替え)、手元に clone します。

```bash
git clone <自分のリポジトリのURL> my-dissertation
cd my-dissertation
```

### 3-2. Python 環境(Docker)を起動する

```bash
make up      # コンテナのビルドと起動(初回は数分)
make sync    # uv.lock どおりの Python 環境をコンテナ内に構築
```

> `make` が「そんなターゲットはない」と言う場合は、リポジトリのルート(`Makefile` がある場所)にいるか確認してください。

### 3-3. 動作確認

```bash
make test
```

`32 passed`(数字は増えていてもOK)のように**すべて緑**になれば環境は正常です。

### 3-4. 論文の雛形 PDF を作ってみる

```bash
make pdf
```

成功すると `draft/main.pdf` ができます(タイトルページ+空の章立てが入った9ページ程度の PDF)。これがあなたの学位論文の出発点です。

### 3-5. コミット前チェックを入れる(推奨)

```bash
make hooks
```

以後 `git commit` のたびに、コード整形と **1MB を超えるファイルの誤コミット防止**(データ混入ガード)が自動で走ります。

## 4. Claude Code と一緒に進める

### 起動と最初の一言

リポジトリのルートで:

```bash
claude
```

初めてなら、まずこう聞いてみてください:

> このリポジトリの構成と、私がこれから何をすればいいかを説明して

Claude はこのリポジトリの決まりごと(`.claude/CLAUDE.md`)を自動で読み込んでおり、日本語で答えます。

### 確認ダイアログの意味

Claude がファイル変更やコマンド実行をする前に、許可を求めるダイアログが出ることがあります。**内容を読んで Yes/No を選ぶだけ**です。定型作業(テスト実行・PDF ビルドなど)は許可済みなので頻繁には出ません。危険な操作(データ削除など)ほど必ず確認が入る設計です。

### 大きな作業はプランモードで

「まず計画を見せて」と頼むか、プロンプト入力時に **Shift+Tab** でプランモードに切り替えると、Claude は先に計画を提示し、承認してから実行します。章の書き直しや解析方針の変更など、影響の大きい作業ほどこれが安全です。

### スキル(スラッシュコマンド)

よく使う定型ワークフローはスキルとして登録済みです。`/` に続けて入力します:

| スキル | いつ使う | 何が起きる |
|---|---|---|
| `/thesis-check` | 原稿を共有・提出する前 | PDF をビルドし、壊れた参照・引用漏れ・図の欠落・TODO を一覧化して修正案を提示 |
| `/research-log` | 解析や執筆の節目 | その日の結果・判断・行き止まりを `docs/research-log.md` に記録(書き込み前に必ず内容確認あり) |
| `/review-chapter` | 章の草稿ができたとき | 章を「論証構成・結果との整合・文章」の3観点で並列レビューし、レポートを `docs/reviews/` に保存 |
| `/session-save` | セッションの終わりに | 作業内容のまとめをメモリとログに保存 |
| `/zotero-connect` | 文献管理に Zotero を使うとき(WSL2) | Windows 側の Zotero への接続を確立 |

### 頼み方の例文集

具体的に頼むほど良い結果になります。**ファイル名・スタディ名・目的**を入れるのがコツ:

- 「`projects/ocean-heat/data/raw/` に置いた NetCDF を読み込んで月平均を計算する関数を `src/` に作り、`scripts/` から実行できるようにして。テストも書いて」
- 「study1 の解析結果から、緯度別の傾向を示す図を作って `result/figures/` に保存して」
- 「第2章の Methods 節を、`scripts/build_dataset.py` の実際の処理と一致するように書き直す案を見せて」
- 「この bibtex エラーの原因を調べて直して」
- 「今日やったことを `/research-log` で記録して」

困ったときはそのまま聞いてください:「テストが落ちた理由を調べて」「この警告は無視していい?」

### エージェントが変なことをしたら

すべて git で守られています。慌てずに:

```bash
git status          # 何が変わったか一覧
git diff            # 変更内容の中身を確認
git restore <file>  # そのファイルの変更を取り消す
```

Claude 自身に「さっきの変更を元に戻して」と頼んでも構いません。

## 5. 研究の進め方(スタディ編)

### 5-1. 新しいスタディを作る

**自分でやる場合:**

```bash
cp -r projects/_template projects/<スタディ名>
docker compose exec research-template uv run pytest projects/<スタディ名>
```

コピー直後にテストが通る=雛形が正しく複製された、という確認までがセットです。

**Claude に頼む場合:**

> `_template` をコピーして `ocean-heat` というスタディを作り、テストが通ることを確認して

### 5-2. データを置く

- 入手した生データは `projects/<スタディ名>/data/raw/` へ。**このディレクトリは不変**(編集・上書き禁止。エージェントにも書き込みブロックが掛かっています)。
- 置いたら **`data/README.md`(データ台帳)に記入**:入手元・取得日・ライセンス・チェックサム・再入手方法。大きなデータは Git に入らない設定なので、この台帳だけが復元の頼りです。
- 加工したデータはスクリプト経由で `data/interim/`(中間)→ `data/processed/`(解析用)へ。

**Claude に頼む場合:**

> data/raw に置いた `sst_monthly.nc` の中身を調べて、data/README.md に台帳エントリを書いて

### 5-3. 解析コードを書く

役割分担のルール:

- `src/` — 再利用する関数・クラス(データ読み込み、統計処理、作図関数など)
- `scripts/` — `src/` の関数を呼び出すだけの薄い実行入口(1スクリプト=1つの再現可能な処理)
- 実行はすべて Docker 経由: `docker compose exec research-template uv run python projects/<スタディ名>/scripts/<スクリプト>.py`

**Claude に頼む場合:**

> processed の月平均データからトレンドを推定する関数を `src/methods/` に作り、`scripts/fit_trend.py` から実行して結果を表示して。関数にはテストも付けて

### 5-4. 図表を作る

テンプレート付属のヘルパーを使うと、解像度・フォントの統一と**来歴記録**(どのスクリプトが・どのコミットで・いつ生成したか)が自動で付きます:

```python
from src.utils.figures import apply_visualization_defaults, save_figure
from src.utils.tables import write_latex_table

apply_visualization_defaults(cfg)
save_figure(fig, "ocean-heat-trend", cfg)          # → result/figures/ocean-heat-trend.png (+ 来歴JSON)
write_latex_table(df, "ocean-heat-summary", cfg, caption="Summary statistics")
                                                    # → result/tables/ocean-heat-summary.tex
```

**図のファイル名は必ず「スタディ名-内容」にしてください**(例: `ocean-heat-trend`)。論文側は全スタディの図を1つの名前空間で探すため、`fig1.png` のような名前は衝突します。

## 6. 論文の書き方(原稿編)

原稿の詳しい決まりごと(ラベル命名・引用キー・図の参照方法)は **[draft/README.md](draft/README.md)** にまとまっています。ここでは流れだけ:

### 6-1. 章を追加する

1. `draft/chapters/_chapter-template.tex` を `draft/chapters/03-<スタディ名>.tex` にコピー
2. `draft/main.tex` の `% \include{chapters/03-study2}` の行を実名に変えて有効化
3. `draft/preamble.tex` の `\graphicspath` にそのスタディの `result/figures/` を1行追加

**Claude に頼む場合:**

> ocean-heat スタディ用の章を追加して、main.tex と graphicspath への登録までやって

### 6-2. 図表・引用を入れる

- 図: `\includegraphics[width=0.8\linewidth]{ocean-heat-trend}`(パス・拡張子なし)+ `\label{fig:ocean-heat-trend}`
- 表: `\input{../projects/ocean-heat/result/tables/ocean-heat-summary.tex}`
- 参照: 常に `\cref{fig:ocean-heat-trend}`(`\ref` は使わない)
- 引用: 文献は `draft/reference.bib` に集約(Zotero + Better BibTeX でのエクスポート推奨)、本文は `\citep{smith2020ocean}`

### 6-3. ビルドとチェック

```bash
make pdf     # → draft/main.pdf
make check   # 壊れた参照・引用漏れ・図の欠落を機械チェック
```

または Claude に `/thesis-check` と入力すれば、ビルド→チェック→修正案の提示までまとめてやります。

### 6-4. 提出前

- `draft/preamble.tex` の `\draftnotestrue` を `\draftnotesfalse` にすると、下書き用の `\todo` メモが一括で消えます。
- `/review-chapter` で章ごとのレビューを受けると、論理の飛躍や本文と図表の食い違いを潰せます。

## 7. コマンド早見表

すべてリポジトリのルートで実行します(`make` だけ打つと一覧が出ます):

| コマンド | 何をするか | 目安時間 |
|---|---|---|
| `make up` | Docker コンテナをビルド・起動 | 初回数分、以後数秒 |
| `make sync` | Python 環境を uv.lock どおりに同期 | 初回数分 |
| `make test` | 全テスト実行(リポジトリ+全スタディ) | 数秒〜 |
| `make lint` | コード検査(自動修正なし) | 数秒 |
| `make format` | コード整形+自動修正 | 数秒 |
| `make pdf` | 論文 PDF をビルド | 1〜3分 |
| `make check` | 原稿の整合性チェック | 数秒 |
| `make clean-tex` | LaTeX の中間ファイル掃除(PDF は残す) | 数秒 |
| `make hooks` | コミット前チェックの導入(初回のみ) | 数秒 |
| `make precommit` | コミット前チェックを全ファイルに手動実行 | 初回数分 |
| `make lock` | パッケージ追加後に uv.lock を更新 | 数十秒 |
| `make down` | コンテナ停止 | 数秒 |

## 8. トラブルシューティング

**`make up` が「Bind for 0.0.0.0:8889 failed: port is already allocated」で失敗する**
→ 別のコンテナが同じポートを使っています。`.env.example` を `.env` にコピーし、`JUPYTER_PORT=8890` のように空いている番号へ変更して再度 `make up`。

**`make pdf` が「latexmk not found」と言う**
→ `sudo apt install latexmk` を一度実行してください。なくても手動シーケンスで自動的にビルドされますが、latexmk の方が速く確実です。

**`make pdf` が失敗する / PDF が更新されない**
→ `draft/main.log` の `!` で始まる行が原因です。Claude に「main.log を見てビルドエラーを直して」と頼むのが早道です。

**bibtex 関連のエラーが出る**
→ `reference.bib` のエントリが壊れているか、`\cite` したキーが存在しないケースが大半。`make check` が原因箇所を指摘します。

**論文に図が出ない(「File not found」)**
→ (1) 図を生成するスクリプトを実行済みか、(2) ファイル名がスタディ名プレフィックス付きか、(3) `preamble.tex` の `\graphicspath` にそのスタディを登録したか、を確認。`make check` の E4 がこれを検出します。

**日本語(または特定のフォント)が文字化けする**
→ このテンプレートは LuaLaTeX + 原ノ味フォント構成です。`lualatex` でなく `pdflatex` でビルドしていないか確認してください(`make pdf` を使えば正しいエンジンが選ばれます)。

**Docker 内で作ったファイルの所有者が root になってしまう**
→ 通常は起きない設定ですが、起きた場合は `.env` に `UID`/`GID`(`id -u` / `id -g` の値)を書いて `make up` し直してください。

**エージェントが意図しない変更をした**
→ [4章の「エージェントが変なことをしたら」](#エージェントが変なことをしたら)参照。`git diff` で確認して `git restore <file>` で戻せます。

## 9. ディレクトリリファレンス

```text
.
├── projects/                  # 研究本体(1スタディ=1ディレクトリ)
│   ├── _template/             # 新スタディの雛形(直接編集しない)
│   └── study1/                # 最初のスタディ(リネームして使ってよい)
│       ├── data/raw/          # 🔒 生データ(不変・Git対象外)
│       ├── data/interim/      # 中間データ(スクリプトが生成)
│       ├── data/processed/    # 解析用データ(スクリプトが生成)
│       ├── data/README.md     # 📝 データ台帳(必ず記入)
│       ├── src/               # 再利用コード(utils/models/methods/analysis)
│       ├── scripts/           # 実行入口(薄く保つ)
│       ├── result/            # 🤖 生成物(手で編集しない)
│       ├── tests/             # スタディ携行テスト
│       └── config.py          # スタディ内のパス定義
├── draft/                     # 学位論文原稿(LuaLaTeX)→ draft/README.md 参照
├── docs/                      # 研究ログ・意思決定記録(ADR)・章レビュー
├── tools/thesis_check.py      # 原稿の整合性チェッカー(make check)
├── tests/                     # リポジトリ整合性テスト
├── config.py                  # 全スタディ共有の定数(GEO/RANDOM/VISUALIZATION)
├── Makefile                   # コマンド入口(make で一覧)
├── .claude/                   # エージェント設定(CLAUDE.md・スキル・保護フック)
└── docker-compose.yml / Dockerfile / pyproject.toml / uv.lock
```

🔒 = 書き込み禁止(エージェントにはブロックが掛かっています) / 🤖 = スクリプトからのみ生成 / 📝 = 手で記入するドキュメント

## 10. FAQ

**Q. データは Git にコミットされますか?**
A. されません。`data/` 配下と大容量拡張子(.nc, .h5, .parquet など)は gitignore 済みで、さらに pre-commit が 1MB 超のファイルをブロックします。だからこそ `data/README.md`(再入手方法)の記入が重要です。

**Q. 別の PC で続きをやるには?**
A. clone → `make up` → `make sync` で環境は完全に再現されます(uv.lock がバージョンを固定)。データだけは各スタディの `data/README.md` に従って再取得してください。

**Q. このテンプレート自体を改良したくなったら?**
A. テンプレートのリポジトリ(このリポジトリの元)に変更をコミットし、研究リポジトリには必要な変更だけ手で持ち込むのがシンプルです。

**Q. パッケージを追加したい**
A. `docker compose exec research-template uv add <パッケージ>` のあと `make lock` を実行し、`uv.lock` の変更もコミットしてください。Claude に頼む場合は確認ダイアログが出ます(意図的な設計です)。

**Q. 英語版のドキュメントは?**
A. この README は日本語のみです。コード・コミットメッセージ・論文本体は英語で統一しています(コード内 docstring がそのまま英語の仕様書になります)。

**Q. Jupyter を使いたい**
A. まず `docker compose exec research-template uv add --dev jupyterlab`(初回のみ。`make lock` も忘れずに)。その後 `docker compose exec research-template uv run jupyter lab --ip 0.0.0.0 --port 8888` で起動し、ブラウザで `localhost:8889`(`.env` の `JUPYTER_PORT` の値)へ。探索が終わったら、安定したロジックは `src/` と `scripts/` へ移してください。
