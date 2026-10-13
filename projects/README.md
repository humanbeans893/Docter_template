# projects/ — 研究スタディ置き場

ここの各サブディレクトリが博士論文の **1つの研究(スタディ)** です。スタディは自前のデータ・コード・実験・結果を持つ自己完結な単位で、他のスタディのコードに依存しません。論文原稿はリポジトリのルートの `draft/` にあり、通常は 1スタディ = 1章です。

## スタディの構成

```text
projects/<study>/
├── data/
│   ├── raw/                 # 入力データ <dataset>/ と過去の結果 legacy/<source>/(不変・Git 対象外・Docker 内は読み取り専用)
│   ├── interim/             # 中間データ(acquired/ はコードがダウンロードしたもの)
│   ├── processed/           # 解析用データ(スクリプトが生成。実験の大きな出力は NNN_<slug>/)
│   └── README.md            # データ台帳(入手元・由来・チェックサム・再入手方法)
├── experiments/             # 番号付きの実験
│   ├── README.md            # 実験の手順と実行の仕組み(規則は AGENTS.md の「実験」)
│   ├── EXP_SUMMARY.md       # 実験の索引(状態の正。10000字以内、索引の行は1行200字まで)
│   ├── EXP_ARCHIVE.md       # 論文で使わなかった実験の行の保管庫
│   ├── JOBS.md              # 長時間ジョブの台帳
│   ├── _template/           # 新しい実験の雛形(summary.md, README.md, run.py, params.py。make experiment が複製)
│   ├── _import_template/    # 過去の結果を取り込む実験の雛形(同じ構成。make experiment-import が複製)
│   └── NNN_<slug>/          # 1実験 = 1ディレクトリ(summary.md, README.md, params.py, run.py, out/)
├── src/{utils,models,methods,analysis}/   # 再利用コード
│   └── utils/experiment.py, figures.py, tables.py, provenance.py   # 実験の実行の仕組み、図・表・数値の書き出しと来歴、過去の結果の検証
├── scripts/                 # 実行入口(薄く保つ。昇格スクリプトもここ)
├── result/{figures,tables,animations}/    # 論文に使う生成物(手で編集しない)
├── tests/                   # スタディ携行テスト(複製直後から通る)
├── config.py                # スタディ内の場所 + 論文共通の図の体裁・定数(結果を変えうる値は実験の params.py へ)
└── README.md
```

## 新しいスタディを作る

リポジトリのルートで(題に空白や記号が入るので、題は環境変数で渡します):

```bash
TITLE='Study 2: Title' make study NAME=study2
```

`tools/new_study.py` が `_template/` を `projects/study2/` に複製し、次をまとめて行います。

- 章ファイル `draft/chapters/NN-study2.tex` を作り、`draft/main.tex` の章の並びに足す(`NN` は作成順の番号で、章番号は `main.tex` の並び順で決まる)
- `draft/preamble.tex` と `draft/supplementary.tex` の `\graphicspath` に `result/figures/` を足す
- `docker-compose.yml` に `data/raw/` の読み取り専用マウントを足す
- `docs/thesis-plan.md` の章構成マップに行を足す

題に LaTeX の命令を使うときは `python3 tools/new_study.py study2 --title-tex '...'`、作る前に確かめるときは `--dry-run`。作った後は:

1. 実行中のジョブがないことを確かめてから(`docker compose top`、`STATE.md`、各スタディの `experiments/JOBS.md`)、`make up` でコンテナを作り直して新しいマウントを有効にする
2. `make test` で複製と登録が健全か確かめる
3. スタディの `README.md` と `docs/thesis-plan.md` の行を埋める

### 章を持たないスタディ

複数のスタディをまとめる総合解析(例: `synthesis`)や、背景章のための整理(例: `background`)など、自分の章を持たないスタディは `--no-chapter` で作ります。章ファイル・`main.tex` の行・章構成マップの行は作らず、`\graphicspath` と raw のマウントだけ登録します。

```bash
NOCHAPTER=1 make study NAME=synthesis
```

- 他のスタディの結果は、コミット済みの `result/tables/*.csv` をファイルとして読む。読んだファイルは、`save_figure`・`write_latex_table`・`write_latex_values`・`run.promote()`(`result/tables/` へ出すとき)の `sources=[...]` に渡して、パスと sha256 を来歴に記録する。`make check` はそこから、その CSV を作った実験をたどり、撤回・中止・置き換えの実験や、まだ `進行中` の実験の結果なら知らせる(W14)。他のスタディのコードは import しない。
- 複数のスタディで使う raw データは、1つのスタディ(持ち主)にだけ置き、他のスタディの台帳には持ち主のパスとチェックサムを書く。

## 実験を作る

```bash
make experiment STUDY=study1 SLUG=baseline_fit
SUMMARY='基準モデルの当てはめ' make experiment STUDY=study1 SLUG=baseline_fit   # summary.md と README の題も入れる
```

過去の結果を取り込むときは取り込み用の雛形を使います(手順は `docs/importing-past-results.md`):

```bash
make experiment-import STUDY=study1 SLUG=logger_drift SOURCE=logger-drift_runs_2026-07
# 元の場所を指定すると、利用者が実行するコピーのコマンドにそのまま入る
FROM=/path/to/old-repo/results LEGACY_ID=old-repo@1a2b3c4:experiments/012_drift \
  make experiment-import STUDY=study1 SLUG=logger_drift SOURCE=logger-drift_runs_2026-07
```

`tools/new_experiment.py` が番号を決めて雛形を複製し、索引 `experiments/EXP_SUMMARY.md` に `| NNN | slug | (実行前) | 進行中 | — | 新規 |`(取り込みなら由来 `取り込み`)の行を足します。規則は `AGENTS.md` の「実験」、手順と実行の仕組みは各スタディの `experiments/README.md` にあります。

## 命名

- **スタディ名**: 小文字で始まる英小文字・数字・`_`(例: `study1`, `coastal_mixing`)。`_template` は雛形なので使わない。
- **実験**: `NNN_<slug>`(スタディごとの3桁の連番 + 小文字・数字・`_`。例: `001_baseline_fit`)。
- **図・表・数値の名前**: `<スタディ名>-<内容>`(例: `study1-overview`)。論文はすべてのスタディの図を1つの名前空間で探すため、接頭辞がないと衝突する(`make check` が警告する)。
- **章のラベル**: `ch:<スタディ名>`、節は `sec:<スタディ名>-<内容>`。

## スタディの名前を変える・削除する

専用の道具はありません。次の登録をすべて同じコミットで直します。`tests/test_template_integrity.py` が、登録とスタディのディレクトリが双方向に対応しているかを検査するので、漏れがあればテストが落ちます。

名前を変える(`old` → `new`):

1. 実行中のジョブがないことを確かめる(`docker compose top`、`STATE.md`、`projects/old/experiments/JOBS.md`)。
2. ホストで `git mv projects/old projects/new`(Git に入っていない `data/raw/` などもディレクトリごと移る。raw の原本の場所を台帳の外に書いていれば、そこも直す)。
3. `docker-compose.yml` の raw のマウント(`source` と `target`)を新しい名前にする。
4. `draft/preamble.tex` と `draft/supplementary.tex` の `\graphicspath` の `../projects/old/result/figures/` を直す。
5. `draft/values.tex` の `\ThesisValues{../projects/old/...}` を直す。
6. 章ファイル `draft/chapters/NN-old.tex` を `NN-new.tex` に変え、`draft/main.tex` の `\include` を直す。ラベル `ch:old` / `sec:old-…` と、それを指すすべての `\cref` を直す。
7. 図・表・数値は名前を `new-…` にしてコードで作り直す(古い `old-…` のファイルは消す)。本文の `\includegraphics{old-…}`、`\input{…}`、`\val{old-…}` を直す。
8. `docs/thesis-plan.md`、`STATE.md`、スタディの `README.md` と `experiments/` の文書の中のパスを直す。
9. `make up` でコンテナを作り直し、`make test` と `make check` を通す。

削除する:

1. 実行中のジョブがないことを確かめ、raw と legacy の原本がバックアップ先にあることを確かめる。
2. `docker-compose.yml` のマウント、`\graphicspath` の項目(2ファイル)、`draft/values.tex` の行、`draft/main.tex` の `\include`、章ファイル、`docs/thesis-plan.md` の行を消す。
3. 他の章からの `\cref` と、他のスタディの来歴の `sources` にこのスタディのファイルが残っていないか確かめる。
4. `git rm -r projects/<study>` の後、`make up`、`make test`、`make check`。

## なぜ monorepo(git submodule にしない)か

1人の学位論文では、リポジトリの分割(submodule/subtree)は detached HEAD・二段のコミットなどの運用の手間ばかりが先に立ちます。全スタディを1リポジトリで管理し、後で単独公開が必要になったスタディだけ履歴ごと切り出します:

```bash
git subtree split --prefix=projects/<study> -b <study>-export
# 完全な書き換えが要るなら: git filter-repo --path projects/<study>/
```
