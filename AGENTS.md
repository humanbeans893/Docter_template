# AGENTS.md

Claude Code・Codex CLI など、このリポジトリで作業するすべてのエージェントの共通規約です。`CLAUDE.md` はこのファイルを参照するだけです。

## 前提

- 思考は英語、回答はユーザーの言語(既定は日本語)で書く。日本語で自然に書ける一般語を英語で書かない(識別子と正式名称は除く)。
- このリポジトリは、別々の研究リポジトリで行った研究を集めて博士論文に仕上げる場所。実験・データ・計算はここでは行わない。
- 体裁は一般的な博士論文の形に従う。大学・研究科固有の要件(様式、審査手続き、業績の条件)は推測で足さず、ユーザーに確かめる。
- 小さく保つ。仕組み・テスト・文書を足す前に、無いと本当に困るかを考える。

## 構成

```text
research.json            研究の一覧 = 研究の章の構成(正本)
projects/_template/      1つの研究を論文で読める形にまとめる雛形(写して使う。直接埋めない)
projects/<id>/           取り込んだ研究: README.md(要約カード)・figures/・tables/・values.tex
draft/                   博士論文(LuaLaTeX ltjsreport。本文は英語、要旨は和英)
docs/                    論文計画・繰り返さないこと・案・研究ログ・意思決定記録・査読・指摘(docs/README.md)
tools/                   標準ライブラリだけのツール(thesis_check.py・archive_thesis.py・public_repo_check.py)
tests/                   リポジトリの構造とツールのテスト(コンテナの pytest)
external/                任意・Git 管理外: 研究リポジトリの手元のクローンへのリンク(読むだけ)
STATE.md                 運用状態(セッションの最初に読む)
DYNAMIC_WORKFLOW.md      動的ワークフローの運用手引き(正本)
.agent-runs/             Claude Code・Codex 共通の実行記録(案内と道具だけ Git 管理)
```

雛形の `study1` は仮の研究で、最初の本当の研究を取り込むときに消します(`add-research` スキル)。

### research.json

`{"research": [ … ]}` の1行が1つの研究です。行の並び = `draft/main.tex` の研究の章の並び。

| 欄 | 内容 |
|---|---|
| `id` | `[a-z][a-z0-9_]*`。`projects/<id>/`、章のファイル `draft/chapters/<id>.tex`、ラベル `ch:<id>`、値のキーの接頭辞 `<id>-` |
| `title` | 仮の題(英語でも日本語でも) |
| `chapter` | 章のファイル `draft/chapters/<id>.tex`。章を持たない研究(図・数値を他の章で使うだけ)は `""` |
| `source` | 写す元 `<repo>@<sha>`(行を足すときに書く。雛形の `study1` だけ `""`)。ホストのパスは書かない |
| `paper` | 章の基になる論文の bib キー。無ければ `""` |
| `paper_status` | `出版済み`・`採録`・`投稿中`・`準備中`、論文が無ければ `""` |
| `status` | `構想`(projects/<id>/ を雛形から作っただけ)→ `取り込み済み`(projects/<id>/ を埋めた)→ `執筆中` → `完成` |

`<repo>` は研究リポジトリの名前(リモートの名前。無ければユーザーに決めてもらう)で、`external/<repo>` のリンクにも同じ名前を使います。`<sha>` は `git -C <path> rev-parse --short=12 HEAD` の12文字です。

### projects/<id>/

| ファイル | 中身 |
|---|---|
| `README.md` | 要約カード: id・出典・論文、問い、方法の要約、主な結果、言えないこと・注意、図表の一覧と元。章を書くときに読む |
| `figures/` | 章が使う図(PDF・PNG・JPG)。研究リポジトリから写す。1ファイル 10 MB まで |
| `tables/` | 章が `\input` する表(`.tex`)。中身は `tabular` だけ(`table` 環境・`\caption`・`\label` は章に書く)。セルの数値は元のまま書き、先頭のコメントに元 |
| `values.tex` | 本文が使う数値。1行1定義で、各行の上のコメントに元 |

`values.tex` の定義は2種類です。`\deftextvalue{<id>-<name>}{<値>}` は書いたとおりに出し(既定)、`\defvalue{<id>-<name>}{<数>}` は siunitx で数として組みます。`<name>` は研究リポジトリの数値のマクロ名があればそのまま(例 `<id>-NSubjects`)、無ければ同じ形の英数字。

## コマンド

```bash
make pdf                 # draft/main.pdf と draft/supplementary.pdf(ホストの LuaLaTeX。ログは draft/build/<job>/<job>.log)
make pdf-review          # draft/review.pdf: 指導教員・審査員に送る版(行番号・ビルド印)
make pdf-final           # draft/submission.pdf: 提出版
make check               # 原稿の整合性検査(make check-final: 提出用の厳格な検査)
make submission          # 提出版と補足資料を作って check-final(保存は make archive TAG=<tag>)
make test                # テスト(コンテナの pytest)。make lint: ruff
make security            # 公開前の検査(秘密情報・個人のパス・大きなファイル・external/)
```

ほかは `make help`。直接呼ぶなら `bash draft/compile.sh [main|review|submission|supplementary|all]` と `python3 tools/<ツール>.py`。

- LaTeX と `tools/` はホストで動く(`lualatex`、標準ライブラリだけの `python3` 3.10 以上)。Python のテストと ruff はコンテナの中だけ。
- ホストで `python`・`pip`・`uv`・`virtualenv` を実行せず、`.venv` を作らない(`python3 tools/…` と `uvx pre-commit` は使える)。Claude Code では `.claude/settings.json` が拒否し、Codex ではこの規則だけが歯止めになる。

## 引き継ぎ

チャットの内容は、次のセッションにも、Claude Code と Codex の切り替えにも残りません。エージェントの記憶にも研究の状態を置きません。残す価値のあることは、起きたその場で正本のファイルに書きます。

- 開始時に読む順: `STATE.md` → 下の「動的ワークフロー」の台帳 → `research.json` → `docs/thesis-plan.md` → `docs/guardrails.md` → 触る研究の `projects/<id>/README.md`。
- 完了を報告する前、ユーザーや研究リポジトリの作業を待つことになったとき、状態が大きく変わったときに、`write-handoff` スキルで `STATE.md` を更新する。
- 毎回読む文書には文字数の上限がある: `STATE.md` 6000字、`docs/thesis-plan.md` 8000字、`docs/guardrails.md` 8000字(テストが検査する)。あふれたら古いものを研究ログ・意思決定記録へ移す。

## 動的ワークフロー

- 複数のエージェントを動かす動的ワークフローは [`DYNAMIC_WORKFLOW.md`](DYNAMIC_WORKFLOW.md) に従う。
- 起動前に、作業の内容・段階・作業者の数からトークン使用量と総量を見積もる。
- 同時実行数は、段階ごとの実測と利用枠の残り・再設定までの時間から決める(固定数や推測で決めない)。
- Codex が書き、Opus がレビューと最終確認をする。
- 止まった実行は台帳にブランチごとの続きの地点(次の段階と直前の報告のキー)を残し、新しい実行で続ける。同じ実行の引数を変えて再開しない。
- Claude Code・Codex の両方が `.agent-runs/` に実行を記録し、[読み書きの手順](.agent-runs/README.md)に従う。
- セッション開始時と引き継ぎ時は `STATE.md` に続けて `.agent-runs/README.md`、`.agent-runs/sessions.jsonl` の末尾、最新の `.agent-runs/runs/<run>/` の `manifest.json`・`results.json`・`stages.jsonl` を読む(未作成なら初回として扱う)。
- 開始時と終了時に `index_sessions.py` で一覧を更新し、実行の完了・停止・失敗時に `export_workflow_run.py` で記録を書き出す。
- 台帳の道具は `.agent-runs/shared/tools/` にあり、ホストで許可された `python3 tools/…` の対象外なのでコンテナで動かす。
- コマンドは台帳の README の `docker run --rm --network none … <python-image> python3 …` を使い、記録をホストと同じパスに読み取り専用でつなぐ。
- Codex の段階には、ローカルの `.claude/settings.local.json` に許可規則 `Bash(codex exec --approve-for-me:*)` が必要。この設定はコミットしない。

## 単一の正本

情報ごとに正本は1か所です。同じ内容を2つのファイルに持たず、他からはリンクします。

| 情報 | 正本 |
|---|---|
| 研究の一覧・章の並び・出典のコミット・状態 | `research.json` |
| 1つの研究の内容(問い・方法・結果・限界・図表の元) | `projects/<id>/README.md` |
| 本文の数値 | `projects/<id>/values.tex` |
| 実験・データ・計算・図の作り方 | 研究リポジトリ |
| 論文の文章 | `draft/` |
| メタデータと体裁の切り替え | `draft/thesis-config.tex` |
| 発表論文の一覧・著者の貢献 | `draft/frontmatter/publications.tex` |
| 書誌 | `draft/reference.bib` |
| 手作りの図の由来 | `draft/figures/README.md` |
| 運用状態・待ち・次の作業 | `STATE.md` |
| 動的ワークフローの運用手順 | `DYNAMIC_WORKFLOW.md` |
| エージェントのセッション一覧・実行記録・続きの地点 | `.agent-runs/`(読み書きは `.agent-runs/README.md`) |
| 主張・研究課題・貢献・マイルストーン | `docs/thesis-plan.md` |
| 撤回した主張・繰り返さない失敗 | `docs/guardrails.md` |
| 案・却下した案 | `docs/ideas.md` |
| 経緯と判断の理由 | `docs/research-log.md`・`docs/decisions/` |
| 指導教員・審査員の指摘と対応 | `docs/feedback/` |
| 査読の報告 | `docs/reviews/` |

## 研究を取り込む

手順は `add-research` スキルにあります(正本)。流れ: 研究リポジトリを読む → 案をユーザーに示す → `cp -r projects/_template projects/<id>` と `research.json` の行 → 図・表・数値・カードを埋める → 章・`\include`・`\ThesisValues` → 章を書く → `make pdf check`。

規則:

- 研究リポジトリはここから読むだけ。ファイルを編集せず、スクリプトを実行せず、コミット・`checkout`・`pull`・`stash` もしない。使う git は `git -C <path> rev-parse|status|log|show|diff|ls-files` だけ(`<path>` はユーザーが示すクローンの場所か `external/<repo>`)。
- 研究リポジトリの形は問わない。README・STATE.md・論文の原稿・結果・図や数値を作ったコードを読み、どれが正式な結果かを確かめる。決められなければユーザーに聞く。
- コミットした状態から写し、元を `<repo>@<sha>:<path>` で書く(カードの図表の表、`values.tex` と表のコメント)。
- 計算・データ・実験は研究リポジトリに残す。ここで再計算・再描画・図の加工をしない。欠けた図や数値は研究リポジトリで作ってもらい、そのコミットから写す。
- 数値の元は、結果のファイル(CSV などの行・列)> 研究リポジトリの論文の原稿(`<repo>@<sha>:<file>` の節)> 出版版(bib キーと表・ページ)の順に選ぶ。値は元の表記のまま写す。論文と同じ桁に丸めるのはよい(元の値もコメントに書く)が、換算・差・比など計算の要る値は研究リポジトリで作ってもらう。
- 撤回・訂正された結果は、表の行・列も含めて写さない。撤回した主張は `docs/guardrails.md` に1行書く。
- カードは要約する。論文の全文を貼らない。

## 原稿

- ビルドは make か `bash draft/compile.sh` だけ。`draft/` の中で `lualatex`・`bibtex` を手で実行しない(残った `.aux`・`.bbl` が黙って読まれる)。`compile.sh` が古い中間ファイルで止まったら `make clean-tex`。
- 本文・図表の説明・LaTeX のコメントは英語。要旨は和文と英文。
- 体裁: 表紙(題名 和英・著者・学位・大学・研究科・専攻・指導教員・日付)、和英の要旨、謝辞、業績一覧、目次、図目次・表目次、章、参考文献、付録。前付けはローマ数字、本文からアラビア数字。メタデータと体裁の切り替え(業績一覧・図表目次・余白・行間など)は `draft/thesis-config.tex` だけで変える。大学の要項はユーザーが示したときだけ反映する。
- 研究の章は `draft/chapters/<id>.tex`。章番号は `draft/main.tex` の並びで決まる。章はラベルで指す。
- ラベルは `ch:`・`sec:`・`subsec:`・`fig:`・`tab:`・`eq:`・`alg:`・`app:`。研究の章は `ch:<id>`、節は `sec:<id>-…`、図表は `fig:<id>-…`・`tab:<id>-…`。参照は `\cref` だけ(裸の `\ref` は使わない)。
- 図: `\includegraphics{<id>/figures/<name>}`(拡張子なし。`\graphicspath` が `draft/figures/` と `projects/` を探す)。`draft/figures/` には手作りの図(模式図・写真)だけを置き、台帳 `draft/figures/README.md` に行を足す。研究リポジトリや `external/` を直接読まない(E10)。
- 表: `table` 環境の中で `\input{../projects/<id>/tables/<name>}`。`\caption` と `\label` は章に書く。
- 数値: 結果の数値(測定値・推定値・統計量・件数)を本文・要旨・結論・図表の説明に手で書かない。`\val{<id>-<name>}`、単位付きは `\valqty{<id>-<name>}{<単位>}`、文字列のままなら `\rawval{<id>-<name>}`。値のファイルは `draft/values.tex` に登録し、章の中で `\input` しない(E11)。
- 論文を基にした章: 雛形の前書き(出版の状況と `\citet{<bibkey>}`、著者の貢献、転載の許諾・著作権、発表版との違い)を埋め、Introduction / Methods / Results / Discussion / Summary として書き直す。ユーザーにしか分からない項目は、答えが来るまでコメントのまま `% TODO` にする。論文を貼るのではなく、博士論文の1章として書く: 総合序論と重なる背景は削って `\cref` で指し、Summary で答えた研究課題と次の章へのつながりを書く。出版社の規程で学位論文への再利用が許されるかはユーザーに確かめる。
- 1つの研究の結果が変わったら、和英の要旨・結論・`docs/thesis-plan.md` を同じ作業で直す。
- 付録は `backmatter/appendix-<id>.tex`(`\label{app:<id>}`)を `\appendix` の後に `\include` する。製本できない資料だけを `supplementary.tex` に入れる。
- 背景・理論の章が要るときは `chapters/_background-template.tex` を `chapters/background.tex` に写し、`main.tex` のその行のコメントを外す。
- 指導教員・審査員に送る版は `make pdf-review`。`review/YYYY-MM-DD` のタグはユーザーが付ける。受けた指摘は `docs/feedback/` に記録する。

## 文献

- 書誌の正本は `draft/reference.bib` だけ。エージェントは Zotero などの文献管理ソフトに接続しない。ユーザーのライブラリの書誌は BibTeX で書き出して渡してもらう。
- 足す前に、見つけたものも渡されたものも DOI から原典(出版社のページ、Crossref など)と照合し、`verified = {YYYY-MM-DD, doi:10.…}` の欄を付ける(DOI が無ければ `isbn:` か公式ページの `url:`)。研究リポジトリの論文の `.bib` から写す項目も同じ。
- 自分の未発表の論文(`投稿中`・`準備中`)は原稿と照合し、`verified = {YYYY-MM-DD, <repo>@<sha>:<原稿のパス>}` とする。出版されたら DOI で照合し直す。
- 引用キーは `authYYYYfirstword`。`file`・`local-url`・`annote` など手元のパスや私的なメモの欄は消す。
- 引用を捏造しない。照合できない文献は入れず、章のその箇所に `% TODO: citation needed (<著者 年>, unverified)` と書く(`make check` の TODO の一覧に出て、提出の検査で止まる)。
- `reference.bib` の項目の外(コメント)に `@` を書かない。BibTeX が項目と読んでビルドが止まる。
- 雛形の仮の書誌 `lamport1994latex` と `main.tex` の `\nocite` は、最初の本当の引用を足したときに消す。

## 公開リポジトリの安全

- このテンプレートは公開リポジトリ。実際の博士論文はテンプレートから private のリポジトリとして作る(未発表の結果や、転載の許諾が要る図が入るため)。
- 追跡するファイルにホストの絶対パス(`/home/<user>/`、`/Users/<name>/`、`C:\Users\<name>\` など)を書かない。研究リポジトリは `<repo>@<sha>:<path>` で書く。
- `.env`・資格情報・個人情報・文献の PDF・文献管理ソフトのデータベースを読まない・コミットしない。`external/` をコミットしない。
- 追跡するファイルは 1 MB まで(`projects/*/figures/` だけ 10 MB まで)。
- `main` へ直接 push しない。force push と履歴の書き換えはユーザーの明示の指示なしに行わない。push の前に `make security` と `git diff --check`。
- GitHub Actions は最小権限と、コミット SHA での固定を保つ。

## 検証

- 原稿・`projects/`・`research.json` を変えた: `make pdf check`(誤り 0)。報告には PDF のパスとページ数を書く。人に送る版は `make pdf-review` と `make check`。`make check` の記号の意味と直し方は `thesis-check` スキル。
- 文書・スキル・Python・設定を変えた: `make test`(Python は `make lint` も)。
- 提出: `draft/SUBMISSION_CHECKLIST.md` を確かめ、`make submission`、タグを付けて `make archive TAG=<tag>`。

## 破壊的な操作

- 研究リポジトリには書き込まない。直すべきことは、研究リポジトリでの作業としてユーザーに伝え、`STATE.md` の待ちに書く。
- 次は事前にユーザーに確かめる: ファイル・ディレクトリの削除、上書き、研究の削除・改名(`projects/<id>/`・`research.json` の行・章・`\include`・`\ThesisValues` をまとめて)、パッケージの追加・削除、履歴の書き換え、タグの作成と push、GitHub の公開範囲・リモート・認証の変更、その他取り返しのつかない操作。
- 読み取り、テスト、ビルド、`git status`・`git diff`・`git log` は確認不要。

## スキル

Claude Code は `.claude/skills/`、Codex は `.agents/skills/` から読みます。両方にあるスキルは同じ内容に保ちます(テストが一致を検査します)。

- `add-research`(両方) — 研究リポジトリを読み、`projects/<id>/`・`research.json` の行・章を作って埋める。後の更新も。
- `write-handoff`(両方) — 完了の報告の前などに `STATE.md` を更新し、ファイルだけで再開できる状態にする。
- `thesis-check`(両方) — PDF をビルドし、`make check` の結果を修正案つきでまとめる。
- `research-log`(両方) — 判断・行き止まりを研究ログ・意思決定記録・`docs/guardrails.md` に記録する。
- `review-chapter`(Claude Code) — 1章を並列のサブエージェントで査読し、`docs/reviews/` に書く。
- `review-thesis`(Claude Code) — 論文全体の一貫性を査読し、`docs/reviews/YYYY-MM-DD-thesis.md` に書く。
