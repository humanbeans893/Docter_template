# AGENTS.md

このファイルは、Claude Code・Codex CLI など、このリポジトリで作業するすべてのコーディングエージェントの共通規約です。`CLAUDE.md` はこのファイルへの参照だけを持ちます。

## 前提

- 思考は英語で行い、回答はユーザーの言語(既定は日本語)で書く。
- 日本語で書くときは、日本語で自然に書ける一般語を英語で書かない(コードの識別子と正式名称は除く)。日本語と英語が頻繁に入れ替わる文体を避ける。
- 目的は博士論文を仕上げること。大学・研究科固有の要件(提出様式、審査手続き、業績数の条件など)は推測で書き足さない。必要ならユーザーに確かめる。

## リポジトリの構成

複数の研究(スタディ)と、それらを章として統合する博士論文を一つのリポジトリで管理します。

- `projects/<study>/` — 1スタディ(通常は1章)分のデータ・コード・実験・結果・テスト。自己完結させ、兄弟スタディのコードを import しない。
- `projects/<study>/experiments/` — そのスタディの番号付き実験、索引 `EXP_SUMMARY.md`(と `EXP_ARCHIVE.md`)、長時間ジョブの台帳 `JOBS.md`。
- `projects/_template/` — 新しいスタディの雛形。`make study` が複製するので壊さない。ここに実験を作らない。
- `draft/` — 博士論文(LuaLaTeX `ltjsreport`、本文は英語、要旨は和英)と補足資料。
- `tools/` — 標準ライブラリだけのツール(`thesis_check.py`、`new_study.py`、`new_experiment.py`、`archive_thesis.py`、`public_repo_check.py`)。ホストの `python3`(3.10 以上)で動く。
- `docs/` — 人間向けの文書(論文計画、取り込みの手引き、繰り返さないこと、案、研究ログ、意思決定記録、レビュー、指摘への対応)。使い方は `docs/README.md`。
- `STATE.md` — 運用状態の単一ページ。`tests/` — リポジトリ全体の構造と制約のテスト。

## コマンド

```bash
# 環境(Python はコンテナ内。初回と、pyproject.toml・uv.lock を変えた後に build)
make build                 # イメージを作る(uv.lock の依存を /opt/venv に焼き込む)
make up                    # 起動・作り直し(作り直すと実行中のジョブが止まる。先に確かめる)
                           # GPU と /external は .env の COMPOSE_FILE で有効にする(「実行環境」)
make down                  # 停止
make lock                  # uv.lock を更新(使い捨ての uv コンテナで実行)
make test                  # 全テスト(コンテナ内の pytest)
make lint                  # ruff check と ruff format --check   make format: 自動修正
docker compose exec research-template uv run python projects/<study>/experiments/NNN_<slug>/run.py --smoke
docker compose exec research-template uv run pytest projects/<study>
#   端末のない実行(エージェント)では exec -T を付ける

# スタディと実験
TITLE='Study title' make study NAME=<study>          # 章と登録まで作る。章の無いスタディは NOCHAPTER=1
make experiment STUDY=<study> SLUG=<slug>            # 新しい実験(SUMMARY='問いの要約' を前に置ける)
make experiment-import STUDY=<study> SLUG=<slug> SOURCE=<source> FROM=<path> LEGACY_ID=<repo>@<sha>:experiments/NNN_x

# 原稿(ホストの LuaLaTeX。中間ファイルは draft/build/<job>/)
make pdf                   # draft/main.pdf
make pdf-review            # draft/review.pdf(行番号・広い行間・ビルド印)。ONLY=02-study1 で章だけ
make pdf-final             # draft/submission.pdf
make supplementary         # draft/supplementary.pdf
make check                 # 原稿の整合性検査(main・review・supplementary)
make check-final           # 提出用の厳格検査(提出版と補足資料を1回でまとめて検査)
make submission            # 提出版と補足資料をビルドして check-final
make clean-tex             # 中間ファイルを消す(PDF は残す)
make archive TAG=<tag>     # make submission の後、提出物一式を dist/<tag>/ に書き出す

# 公開前
make security              # 秘密情報・大容量・Action の固定を検査   make security-history: 履歴も
make hooks                 # pre-commit を入れる   make precommit: 全ファイルに実行
```

`make help` が一覧を出します。直接呼ぶ場合は `bash draft/compile.sh [main|review|submission|supplementary|all]`(引数なしは main と supplementary)、`python3 tools/thesis_check.py --all`、`python3 tools/new_study.py`、`python3 tools/new_experiment.py` です。`make check-final` は `python3 tools/thesis_check.py --main submission.tex --main supplementary.tex --submission --strict` で、`--main` を重ねた文書は `--all` と同じく1回でまとめて検査する(どれかの文書で使う図・書誌は使われているとみなす)。

## セッション状態と引き継ぎ

チャットの文脈は、新しいセッションにも、Claude Code と Codex の切り替えにも引き継がれません。残す価値のあることは起きたときに正本のファイルへ書き、どこで途切れてもファイルだけで再開できるようにします。

- **開始時**に次の順で読む。
  1. `STATE.md`(今どこにいて、次に何をするか。実行中のジョブ)
  2. `docs/thesis-plan.md`(主張・研究課題・章構成と執筆状況)
  3. `STATE.md` の「現在の焦点」に挙がったスタディと、このセッションで触るスタディの `projects/<study>/experiments/EXP_SUMMARY.md`(何を試し、何が残り、何を撤回したか)
  4. `docs/guardrails.md`(撤回した主張と、繰り返さない失敗)

  何かを始める前に `STATE.md` の実行中ジョブを確かめ、前のセッションのジョブを放置も二重実行もしない。
- **作業中**は「あとで」ではなく、その場で書く。
  - 実験の結果 → その実験の `summary.md`・`README.md` と索引の行(同じコミットで)
  - 撤回・訂正・置き換え → 「実験」の「状態と撤回」の手順どおりに
  - 繰り返さない失敗 → `docs/guardrails.md`、新しい案・却下した案 → `docs/ideas.md`
  - 章の対応・執筆状況の変化 → `docs/thesis-plan.md`、指摘への対応 → `docs/feedback/`
  - 状態の変化(段階、ジョブの投入・終了、決定) → `STATE.md`
- **完了を報告する前**(結果・判断・ジョブ・次の作業が変わったとき)、**長時間・高コストのジョブの前**、状態が大きく変わったときに、`write-handoff` スキルで `STATE.md` を更新する(報告はその後)。セッションがいつ終わるかは分からず、チャットでの報告は残らない。「セッションの終わり」を待たない。
- 長時間ジョブの前に `docs/launch-checklist.md` を上から確かめ、そのスタディの `experiments/JOBS.md` に投入時と完了時の行を書く。
- `STATE.md` は運用状態だけを持つ。下の正本へリンクし、内容を写さない。
- 常に読む文書には文字数の上限がある: `STATE.md` 6000字、`docs/thesis-plan.md` 8000字、`docs/guardrails.md` 8000字、各 `EXP_SUMMARY.md` 10000字。索引の行は1行200字まで。行数ではなく文字数で数えるので、行を長くしても収まらない。あふれたら古い決定を研究ログ・意思決定記録へ、実験の詳細をその `summary.md`・`README.md` へ、失敗の経緯を研究ログへ、論文で使わない完了済み実験の行を `EXP_ARCHIVE.md` へ移す。`tests/test_repo_structure.py` が検査する。
- エージェントの記憶(Claude Code の自動メモリなど)は道具と端末ごとに分かれ、もう一方のエージェントや別の複製からは読めない。記憶には研究の状態を置かず、ファイルに置く。記憶とファイルが食い違ったらファイルを正とする。

## 単一の正本

情報ごとに正本は1か所です。同じ表を2つのファイルに持ちません(この表もここだけに置き、他の文書はここを参照します)。

| 情報 | 正本 |
|---|---|
| 現在の状態・実行中のジョブと確認方法・次の作業 | `STATE.md` |
| 論文の骨格(主張・研究課題・貢献の要約と ID、章と根拠の対応、執筆状況) | `docs/thesis-plan.md` |
| 論文の文章(主張・研究課題・結論の表現) | `draft/` の原稿 |
| 発表論文の一覧・著者貢献 | `draft/frontmatter/publications.tex` |
| 実験の索引と状態(撤回を含む) | `projects/<study>/experiments/EXP_SUMMARY.md`(論文で使わない完了行は `EXP_ARCHIVE.md`) |
| 1つの実験の今の結論 | `projects/<study>/experiments/NNN_<slug>/summary.md` |
| 1つの実験の経緯(目的・方法・結果・考察・由来) | `projects/<study>/experiments/NNN_<slug>/README.md` |
| 長時間・高コストのジョブの状態と履歴 | `projects/<study>/experiments/JOBS.md` |
| 撤回した主張・繰り返さない失敗 | `docs/guardrails.md` |
| 有望な案・却下した案 | `docs/ideas.md` |
| 経緯と判断の理由 | `docs/research-log.md`、`docs/decisions/` |
| 指導教員・審査員の指摘と対応 | `docs/feedback/` |
| データ(過去の結果を含む)の由来 | `projects/<study>/data/README.md` |
| 生成物ごとの由来と再現性 | 生成物の隣の `<name>.provenance.json`(コードが書く) |
| 手作りの図の由来 | `draft/figures/README.md` |
| 論文中の数値 | `projects/<study>/result/tables/*.csv`(生成した `.tex` を読み込む。本文に手で書かない) |
| 論文のメタデータ | `draft/thesis-config.tex` |
| 書誌 | `draft/reference.bib` |
| 作業規約 | `AGENTS.md`(実験の手順と仕組みは各スタディの `experiments/README.md`) |

## 作業の流れ

### 作業の前

1. 対象のファイルと近くの実装を読む。
2. `pwd && git branch && git status` で場所・ブランチ・未コミットの変更を確かめる。自分が作っていない未コミットの変更は残す。
3. `main` は保護ブランチ。`agent/<slug>` などの作業ブランチで作業し、PR で統合する。作業ブランチにいればそのまま続ける。
4. 残っている TODO を `rg -n "TODO|FIXME" .` で確かめる。
5. コードから決められないこと(研究上の判断、欠けたデータ、どの過去の結果が正式か)だけをユーザーに確かめる。

### 作業中

- 入力は早い段階で明示的に検証する。
- 書く前に探す: `rg -n "<概念>" projects/<study>/src projects/<study>/scripts projects/<study>/experiments`。あるものを使い、近くの動いている例に倣う。足りない再利用部品は先に `src/` の適切な場所へ足す。同じ計算を2か所に書かない。共有の関数の動作を変えるときは呼び出し元を確かめる。
- スクリプトは薄く保ち、`src/` の関数を組み合わせるだけにする。
- 生成物は手で直さず、コードから作り直す。

### コミットの前

- 変更に見合う最小の検証を走らせる(下の「検証」)。
- 解決した TODO とデバッグ出力を消す。意図したファイルだけを stage し、`git status` で確かめてからコミット・push する。

## 実験

試行錯誤は各スタディの `experiments/` に、1実験1ディレクトリで積み上げます。規則はこの節だけに書きます。手順と実行の仕組みの説明は各スタディの `experiments/README.md`(どのスタディでも同じ内容)にあります。

### 構成

- 名前は `NNN_<slug>`(スタディごとの3桁の連番と、英小文字・数字・`_` の slug。例: `001_baseline_fit`)。`make experiment STUDY=<study> SLUG=<slug>`(過去の結果なら `make experiment-import`)が番号を決め、雛形を複製し、索引に行を足す。実験のディレクトリと索引の行は消さず、番号を使い回さない。やめた実験は `中止` にする。
- 各実験は `summary.md`(今の結論。50行・3000字まで。書き直してよいのはこのファイルだけ)、`README.md`(経緯の記録。追記と誤字の修正だけ)、`run.py`(入口)、`params.py`(シード `SEED`・データの選び方・期間・閾値・モデルの設定など結果を変えうる値のすべてと、`--smoke` の値 `SMOKE`。`config.py` や環境変数から読まない)、`out/`(Git 管理外)で自己完結する。終わった実験の `run.py`・`params.py` は変えず、条件を変えるなら新しい番号にする。
- 読む順は 索引の行 → `summary.md` → `README.md`。実験を前提にする・引用する・章に書く前に `summary.md` を読み、`README.md` は方法を再現・拡張・点検するときだけ開く。数値には出所の CSV(行・列)を添え、食い違えば CSV を正とする。

### 実行

- `run.py` は全体を `with experiment.start(__file__, params) as run:` で包む(`src/utils/experiment.py`)。冒頭の sys.path の処理と `import config`・`from src.utils import experiment, figures, tables` は消さず、関数の中へ移さない(スタディはパッケージとして入っていない)。記録や進捗のコードは `run.py` に書かず、`experiment.py` を直す。
- 先に `--smoke`(`params.SMOKE` を当てた小さな実行。`out/smoke/` に書き、`result/` を変えない。段階ごとの所要時間が本実行の見積もりになる)、それから本実行。完了した本実行は `--overwrite` なしでは繰り返せない(残すなら新しい実験にする)。記録は `out/params_used.json`(状態・シード・パラメータ・コミットと未コミットのコード・段階の時刻・出したファイル)。
- 作業用の出力は `run.out()` で自分の `out/` へ。論文や他の実験が使うものはコードで出す: 図は `save_figure`(過去の画像は `import_figure`)、表は `write_latex_table`、本文の数値は `write_latex_values`、それ以外のファイルは `run.promote()`(`result/tables/` へ。大きな出力は `dest_dir=config.PROCESSED_DATA_DIR / run.name`)。実行中はどれも `out/staged/` に置かれ、**本実行が最後まで通ったときだけ** `result/`(と `data/processed/NNN_<slug>/`)にまとめて入る(失敗・中断・`--smoke` では変わらない)。手でコピーせず、論文や他の実験から `out/` を読まず、他の実験の `run.py` を import しない。2つ目の実験が必要とするロジックは `src/` へ移す。
- 本実行の前に、`summary.md` の問いと判定の規則・`params.py`・`run.py` と変えたコードをコミットする。コード(そのスタディの `src/`・`scripts/`・`config.py`・`experiments/` の `.py`、ルートの `config.py`・`pyproject.toml`・`uv.lock`)に未コミットの変更があったり、実行中に変わったりすると(同じスタディで新しい実験を作ることも含む)、その後に書いた生成物は未コミットのコードの扱いになる(由来記録の `git_dirty`、`make check` の W15)。原稿・文書・`STATE.md`・`result/` の変更は数えない。
- 体裁だけを変える図などは `src/` か `scripts/` の昇格スクリプトに置いて `result/tables/*.csv` や `data/processed/NNN_<slug>/` を読み、読んだファイルを `sources=[...]` で由来記録に残す(`make check` はそこから元の実験をたどる)。

### 状態と撤回

- 索引(`EXP_SUMMARY.md`。論文で使わずに終わった完了・中止の行は `EXP_ARCHIVE.md`)の列は `| # | slug | 一行で | 状態 | 論文 | 由来 |`。状態欄と `summary.md` の「状態」は同じ語で始める: `進行中`(結論がまだない)・`完了`(答えが立っている)・`中止`(結論を出さずにやめた)・`訂正`(一部を直した。主な結論は保たれる)・`撤回`(主な結論を取り下げた)・`置き換え`(後の実験が同じ問いに答え直した)。後ろに `(YYYY-MM-DD、→ NNN_<slug>)` を足してよく、理由は `summary.md` に書く。論文欄は章のラベルか `—`。由来欄は `新規`、取り込みは `取り込み`、閉じたら `取り込み(R2)` のように再現性を書く。
- 本実行の後に、`summary.md` の答え・主な数値・本実行と、索引の一行で・状態を同じコミットで直す(`--smoke` では直さない。`--overwrite` で作り直したら本実行と主な数値も)。
- 撤回・訂正・置き換えは同じコミットで直す。「あとで書く」と、実際には書かれない。(1) `summary.md` の状態と答えを書き直し(取り下げた記述は消さずに取り消し線で残す)、「訂正・撤回・置き換え」の行に日付と根拠を書く。(2) 索引の状態欄を同じ語で始める(行が `EXP_ARCHIVE.md` にあれば索引へ戻す)。(3) 撤回なら `docs/guardrails.md` に1行足す。原稿(W14 が挙げる生成物と、その結論を書いた章・要旨・結論・`docs/thesis-plan.md`)は、原稿を直す作業を任されていれば同じ作業で直し、任されていなければ `STATE.md` の次の作業に P0 で書く。
- `make check` の W14 は、撤回・中止・置き換えの実験と、まだ `進行中` の実験から来た生成物を知らせる(提出の検査では誤り)。`tests/test_repo_structure.py` がディレクトリ・索引・`summary.md` の対応と状態の一致を検査する。

### 速く回る実験を書く

何時間もかかる実験は時間を失うだけではありません。再実行されなくなり、再実行しない解析は確かめられなくなります。どの実験も何度も実行するものとして書きます。

- **動かす前に測る。** 計時が必要を示すまで、HPC への移植、並列化、間引きをしない。1台に収まらないように見えるデータも、読み方を工夫すれば収まることが多い。
- **使うものだけ読む。** データを開くときに不要な変数を落とす(`xarray` は `interp` などで残った変数をすべて実体化する)。各ファイルは一度だけ開いて使い回し、点ごとの参照はループではなく一度のベクトル化した呼び出しにまとめる。
- **層の中で一定の量は、層ごとに一度だけ計算する。** 行ごとに計算しない。
- **段階ごとに進捗を出す。** 扱っている行数も出す。何も出さない実行は、止まっている実行と区別できない。
- **遅い部分を最後に置く。** 抽出・検証・安い厳密な検査を高価な当てはめの前に走らせ、間違いが数時間後ではなく数秒で分かるようにする。安い検査で候補を絞れるなら先に行う。

## 過去の結果の取り込み

これまでの実験結果は、手引き `docs/importing-past-results.md` に従い、`import-results` スキルで取り込みます。要点:

- 1つの主張を支える1組の結果ごとに取り込み実験を1つ作る(`make experiment-import`)。使う実行(正式な1回)を決め、合成データやデモの出力は結果として扱わない。古いリポジトリで撤回・中止された実験は、ユーザーが決めない限り取り込まない。
- 過去の出力は `projects/<study>/data/raw/legacy/<source>/` に、過去の入力データは `projects/<study>/data/raw/<dataset>/` に置く。そこへコピーするのは**ユーザー**で、エージェントはコマンドを示すだけ(頼まれても実行しない)。マニフェスト `inputs.sha256` は raw を読むだけなのでエージェントが生成してよい。ハッシュを手で打たない。
- 取り込みの `run.py` は 入力の照合 → `out/` での作り直し → 既報の数値との照合 → ヘルパー の順に進め、照合が通らなければ `result/` は変わらない。再現性は生成物ごとに決め、由来記録に入る: **R1** ここで計算し直して一致を確かめた / **R2** 残った数値から図表を作り直した(計算はしていない) / **R3** 画像や論文の数値をそのまま載せた(`make check` の I3 に一覧が出る)。
- 取り込み実験が `完了` になるまで、その結果を本文で使わない。由来は README の「由来」と `data/README.md` の台帳に、ホストの絶対パスではなく `<repo>@<sha>:<path>` で書く。

## 研究コード

- 再利用するロジックは `src/`(`utils/`・`models/`・`methods/`・`analysis/`)、薄い実行入口は `scripts/`、試行錯誤は `experiments/`。
- 失敗は明示する。必須の入力は `assert` などで分かりやすい文言とともに検証し、既定値やダミー値で処理を続けない。例外を黙って握りつぶさない。広い `try`/`except` は、その失敗を意図して扱うときだけ使う。試し書きの既定値は、`src/` やスクリプトへ移す前に明示的な検証に直す。
- 図表と数値の名前は `<study>-<slug>`(全スタディで一つの名前空間。`make check` の W16 が接頭辞を検査する)。
- スタディの `config.py` の名前を使う(`STUDY_ROOT`、`RAW_DATA_DIR`、`FIGURE_DIR`、`TABLE_DIR`、`EXPERIMENTS_DIR` など)。research-template の名前 `PROJECT_ROOT`・`DATA_ROOT` と古い名前 `EXP_DIR`(`EXPERIMENTS_DIR` と同じ)も使えるが、`PROJECT_ROOT` はスタディのルートで、`DRAFT_DIR` と `/data` は無い。書き込みは `*_DIR` の下だけにする。
- ルートの `config.py` には、全章の図の体裁 `VISUALIZATION`(すべての章の見た目をそろえる。数値は変えない)と物理定数 `GEO` だけを置く。結果を変えうる値(シード、データの選び方、閾値、モデルの設定)は実験の `params.py` に置き、`config.py` には置かない。
- 複数のスタディを総合する解析は、総合用のスタディ(`make study NAME=synthesis NOCHAPTER=1` など、章を持たないスタディ)に置く。他のスタディのコミット済みの `result/tables/*.csv` をファイルとして読み、由来記録の `sources` に sha256 とともに記録する。他のスタディのコードは import しない。
- import の書き方はリポジトリ内でそろえる。新しい計算にはテストを足す。

## データ

- `data/raw/` は不変。エージェントは書き込まない。Claude Code ではフックと拒否設定(`.claude/settings.json`)が止め、コンテナの中では読み取り専用のマウントが止める。Codex などをホストで動かすときは何も止めないので、`data/raw/` を書き換えうるコマンド(`cp`・`mv`・`rsync`・`rm`・リダイレクトなど)を自分で避ける。止まったら回避せず、ユーザーが自分の端末で実行するコマンドを示す。
- 共有する生データは1つのスタディが持ち、他のスタディは台帳にパスと sha256 で参照する。
- コードがダウンロードしたデータは `data/interim/acquired/<dataset>/` にマニフェストとともに書き、ユーザーがホストで `data/raw/<dataset>/` へ移す。R1 の再実行では入力を取り直さず、保管したコピーを使う。
- リポジトリに置けないデータは、`.env` の `EXTERNAL_FILES_DIR` と `COMPOSE_FILE`(`docker-compose.files.yml` を加える)で `/external` に読み取り専用で付ける(`docs/integrations.md`)。
- `data/interim/` と `data/processed/` はスクリプトで作り直す。手で編集しない。
- データを置いたら `projects/<study>/data/README.md` に入手元・取得日・ライセンス・チェックサム・スキーマ・再入手の方法を書く。過去の結果は「過去の結果(legacy)の記録」のブロックに、元の場所・実施時期・実施者・生成コードとコミット・再現性・取り込み実験・公開可否・バックアップ先・マニフェストを書く。
- 生データと大きなファイルを Git に入れない(追跡するファイルは 1 MB まで)。データを消すのはユーザーの明示の確認の後だけ。

## 原稿

- ビルドは `make pdf` などか `bash draft/compile.sh` だけ。`draft/` の中で `lualatex`・`bibtex` を手で実行しない(残った `.aux`・`.bbl` が黙って読まれ、参照の欠けた PDF ができる)。`compile.sh` は `draft/` に古い中間ファイルを見つけると止まるので、`make clean-tex` で消す。中間ファイルとログは `draft/build/<job>/`(例: `draft/build/main/main.log`)。
- 論文のメタデータは `draft/thesis-config.tex` だけに書く。
- ラベルは `ch:`・`sec:`・`subsec:`・`fig:`・`tab:`・`eq:`・`alg:`・`app:`。スタディの章は `ch:<study>`、節は `sec:<study>-…`。参照は `\cref` だけ(裸の `\ref` は使わない)。章番号は `draft/main.tex` の並びで決まり、ファイル名の `NN-` は作った順の目印にすぎない。章はラベルで指す。
- 解析の図は `projects/<study>/result/figures/` から `\includegraphics{<study>-<slug>}`(パスと拡張子なし。`\graphicspath` で探す)。`draft/figures/` には手作りの図(模式図、写真など)だけを置き、`draft/figures/README.md` の台帳に行を足す。`experiments/*/out/` や `data/` の下を直接読み込まない(E10)。
- 表は `write_latex_table` が書いた `.tex` を `\input{../projects/<study>/result/tables/<name>}` で読む。
- 本文・要旨・図表の説明の数値は手で書かない。`write_latex_values` で書き出し、そのファイルを `draft/values.tex` の終わりの目印より上に `\ThesisValues{../projects/<study>/result/tables/<name>}` で登録し、本文で `\val{<name>-<key>}`(数として組む)、`\valqty{<name>-<key>}{<単位>}`(単位付きの量)、`\rawval{…}`(文字列のまま)と書く。章の中で値のファイルを `\input` しない(要旨は章より前に組まれる。E11)。
- 生成物には由来記録(`.provenance.json`)が付く。未コミットのコードで作った生成物(W15。「コード」の範囲は「実験」)と、撤回・中止・置き換え・進行中の実験の生成物(W14)を提出版に残さない。由来記録のコミットは実行の始め(`scripts/` ではヘルパーの import 時)のもの。図・表・数値のファイルそのものには日時もコミットも入れない(同じコードからは同じファイルができる。日時・コミット・未コミットの有無は由来記録だけが持つ)。
- ある章の結果が変わったら、和英の要旨・結論・`docs/thesis-plan.md` を同じ作業で直す。
- 補足情報は、まず論文内の付録(`backmatter/appendix-<study>.tex`、`\label{app:<study>}`、`\appendix` の後に手で `\include`)に置く。製本できない資料だけを `supplementary.tex` に入れる。本文からは付録を `\cref` で参照し、補足資料の PDF の中を指さない。
- 背景・理論の章が要るときは `chapters/_background-template.tex` を `chapters/background.tex` に写し、テンプレート専用の部分を消して `main.tex` の行のコメントを外す(ラベルは `ch:background`・`sec:background-*`)。
- 既発表・投稿中の論文を章にするときは `docs/importing-past-results.md` の「既発表・投稿中の論文を章にする」の手順に従う。
- 指導教員・審査員へ送る版は `make pdf-review`(行番号と、コミットと日付の印が付く)。ユーザーが `review/YYYY-MM-DD` のタグを付け、受けた指摘は `docs/feedback/` に記録する。
- 原稿を変えたら `make pdf` と `make check`。提出前は `make submission` と生成物の作り直しの確認(`draft/SUBMISSION_CHECKLIST.md`)、その後 `make archive TAG=<tag>`。

## 何をテストするか

- 解析の正しさを担保するもの: 答えの分かっている合成データでの推定、単位・分母・丸めの独立な計算との照合、再現の入口(誤った入力で止まる、既存の結果を上書きしない)。各スタディの `projects/<study>/tests/` に置き、複製した直後から通る状態を保つ。
- システムの制約: 実行環境と読み取り専用の生データ(`tests/test_runtime_constraints.py`)、引き継ぎの構造(`tests/test_repo_structure.py`)、雛形と登録の整合(`tests/test_template_integrity.py`)、各ツールとフック(`tests/test_*.py`)。
- 原稿は、PDF を黙って壊す構造だけを検査する(参照・引用・図・値・由来。`tools/thesis_check.py`)。見出し・語数・文言・主張は固定しない。文章は著者が確かめる。
- テストを足すのは、新しい計算・実際に起きた不具合・システムの制約に対して。文章を直すたびに増えるテストは、やがて実行されなくなる。

## 実行環境

- Python・uv・パッケージの追加・テストはコンテナ内(`docker compose exec research-template uv run|add …`)。Git・ファイル操作・Docker・LaTeX、標準ライブラリだけの `tools/` はホストで実行する。
- ホストにプロジェクトの `.venv`・`venv` を作らない。ホストで `python -m venv`・`virtualenv`・`uv venv`・`uv sync`・`uv run`・`uv add`・プロジェクトの `pip install` を実行しない。ホストの `python3` は標準ライブラリだけの `tools/` とフックに使う(3.10 以上)。Claude Code では `.claude/settings.json` がホストの `python`・`python3 -m venv`・`python3 -m pip`・`pip`・`pip3`・`virtualenv`・`uv` を拒否する(`python3` の `tools/` と `uvx pre-commit` は使える)。Codex にはこの仕組みが無いので、Codex ではこの規則だけが歯止めになる。
- 依存環境はイメージ内の `/opt/venv`(`uv.lock` から焼き込む)。`HOME` と uv のキャッシュは名前付きボリュームで、キャッシュ類は `HOME` の下にあり、`/workspace`(ホスト)には環境のものが書かれない。
- `uv add` はコンテナ内で実行し、その後 `make lock && make build` でイメージに焼き直し、`uv.lock` をコミットする。ビルドは lock を固定版で入れるので、古い lock では止まる(`pyproject.toml` の名前を変えた後の `Missing workspace member` など)。
- 各スタディの `data/raw/` はコンテナ内で読み取り専用(`docker-compose.yml` のスタディごとの bind。元が無ければ起動に失敗する)。新しいスタディは `make up` で作り直すまでマウントされず、その間はコンテナからも書けてしまう(`tests/test_runtime_constraints.py` が検出する)。
- コンテナを作り直すと(`make up`、`make build` の後の起動、compose の変更)、`docker compose exec` で動いているジョブはすべて止まる。作り直す前に `docker compose top`・`STATE.md`・各スタディの `experiments/JOBS.md` で実行中のジョブを確かめる。
- GPU と `/external` は `.env` の `COMPOSE_FILE` に一度書く(GPU は `COMPOSE_FILE=docker-compose.yml:docker-compose.gpu.yml`、`/external` は `:docker-compose.files.yml` を加えて `EXTERNAL_FILES_DIR` も書く)。以後の `docker compose` と `make` はすべてそれを使い、起動は `make up` だけ。`-f` を1回のコマンドに付けるだけでは、次の `make up`(`make study` や `uv add` の後)や `make test` の自動起動で、エラーなしに外れる。`COMPOSE_FILE` を変えたら、実行中のジョブを確かめてから `make up`。
- `.env` は任意(`.env.example` を写す。`COMPOSE_FILE`、`EXTERNAL_FILES_DIR`、`docker compose` を直接使うときの `UID`/`GID`)。`make` は UID と GID を自動で渡す。
- コンテナはポートを公開しない(`docker-compose.yml` に `ports` を足さない)。
- LaTeX はホストの `lualatex` を `draft/compile.sh` から使う(コンテナに TeX は無い)。

## 文献

- 書誌の正本は `draft/reference.bib` だけ。文献管理ソフトと同期しない。
- エージェントは Zotero などの文献管理ソフトに接続しない。ユーザーが自分のライブラリの書誌を使いたいときは、BibTeX などで書き出して渡してもらう。
- 書誌を足す前に、見つけたものも渡されたものも、DOI から原典(出版社のページ、Crossref、PMC、保存版)と照合する。引用する数値も原文で確かめる。照合したら `verified = {YYYY-MM-DD, doi:10.…}` の欄を付ける(DOI が無ければ `isbn:` か公式ページの `url:`)。`make check` の I4 が欄の無い項目を挙げ、提出の検査では誤りになる。W13 は DOI の重複を挙げる。
- 引用キーは `authYYYYfirstword`。`file`・`local-url`・`annote` など手元のパスや私的なメモの欄は消す。
- 引用を捏造しない。確かめられないときは「出典が必要な箇所」として報告する。
- 雛形の `lamport1994latex` と `\nocite` は、最初の本当の引用を足したときに消す。

## 公開リポジトリの安全

- `main` へ直接 push しない。force push と履歴の書き換えは、ユーザーの明示の指示なしに行わない。
- `.env`、資格情報、個人情報、未公開データ、文献管理ソフトのデータベース、文献の PDF を読まない・コミットしない。`.codex/config.toml` もコミットしない。
- 追跡するファイルにホストの絶対パス(`/home/<user>/`、`/Users/<name>/`、WSL の `/mnt/c/Users/<name>/`、Windows の `C:\Users\<name>\`)を書かない。過去の結果の場所は `<repo>@<sha>:<path>` で書く。
- 外部アプリの資格情報は環境変数か Git 管理外のクライアント設定に置く。外部の同期フォルダは読み取り専用でマウントする。
- GitHub Actions は最小権限と、コミット SHA での完全な固定を保つ。
- 公開・push の前に `make security` と `git diff --check` を実行する。

## 検証

- Python を変えた: 対象のテスト → `make test lint`。
- `experiments/`・`STATE.md`・`docs/`・スキルを変えた: 少なくとも `docker compose exec research-template uv run pytest tests/test_repo_structure.py`。
- 原稿を変えた: `make pdf check`。成功したら PDF のパスとページ数を報告する。人に送る版は `make pdf-review` と `make check`。
- GitHub・CI を変えた: YAML の構文、Action の固定、PR 上のすべての検査を確かめる。
- push の前に、意図したファイルだけが stage されていることを確かめる。

## 破壊的な操作と外部への操作

次は事前にユーザーの意図を確かめます: ファイル・ディレクトリの削除、データの上書き、パッケージの追加・削除、履歴の書き換え、GitHub の公開範囲・リモート・認証の変更、タグの作成と push、実行中のジョブがあるときのコンテナの作り直し、スタディの削除・改名(手順は `projects/README.md`)、その他取り返しのつかない操作や費用のかかる操作。ファイルの読み取り、テスト、ビルド、`git status`・`git diff`・`git log` は確認不要です。

## スキル

Claude Code は `.claude/skills/`、Codex は `.agents/skills/` から読み込みます。両方にあるスキルは同じ内容に保ちます(テストが一致を検査します)。

- `write-handoff`(両方) — 完了の報告の前・長時間ジョブの前・状態が大きく変わったときに `STATE.md` を更新し、ファイルだけで再開できる状態にする。
- `import-results`(両方) — 過去の実験結果を由来つきで取り込み、章へつなぐ。
- `thesis-check`(両方) — PDF をビルドし、整合性検査の結果を修正案つきでまとめる。
- `research-log`(両方) — 結果・判断・行き止まりを研究ログ・意思決定記録・`docs/guardrails.md` に記録する。
- `review-chapter`(Claude Code) — 1章を並列のサブエージェントで査読し、`docs/reviews/` に報告を書く。
- `review-thesis`(Claude Code) — 論文全体の一貫性を並列のサブエージェントで査読し、`docs/reviews/YYYY-MM-DD-thesis.md` に書く。
