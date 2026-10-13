# Study 1: Title

博士論文のスタディ `study1` です。このスタディのデータ・コード・実験・結果は、このディレクトリの中で完結させます(他のスタディのコードを import しない)。ディレクトリ名は研究の内容に合わせて変えて構いません(手順は `projects/README.md` の「スタディの名前を変える・削除する」)。

## 研究課題

- **問い**: <このスタディで明らかにすること>
- **答える研究課題**: <RQ の番号。対応は `docs/thesis-plan.md` の章構成マップと同じにする>
- **主張**: <結論を1〜2文で。決まったら書く>

## 対応する章

- **章**: `ch:study1`(`draft/chapters/02-study1.tex`)
- **基になる論文**: <既発表・投稿中の論文があれば bib キー。なければ「なし」>
- 執筆状況は `docs/thesis-plan.md` が正。

## データ

- 台帳: `data/README.md`(データを置いたら必ず記入する)
- 入力データは `data/raw/<dataset>/`、過去の結果は `data/raw/legacy/<source>/`。どちらも利用者がホストでコピーし、`raw/` には誰も書き込まない(Docker の中では読み取り専用)。
- 加工はスクリプト経由で `data/interim/` → `data/processed/`。大きなファイルは Git に入らない。

## 実験の進め方

試行錯誤は `experiments/` に番号付きの実験として積み上げます(規則は `AGENTS.md` の「実験」、手順と実行の仕組みは `experiments/README.md`)。

```bash
make experiment STUDY=study1 SLUG=baseline_fit
docker compose exec research-template uv run python projects/study1/experiments/001_baseline_fit/run.py --smoke
docker compose exec research-template uv run python projects/study1/experiments/001_baseline_fit/run.py
```

- 実験の結果は、その実験の `summary.md`(今の結論)と `README.md`(経緯)と索引 `experiments/EXP_SUMMARY.md` の行に、同じコミットで書く。状態の正は索引で、`summary.md` の「状態」も同じ語で始める。
- 結果を変えうる値(データの選び方・期間・閾値・モデルの設定・シード)は、すべて実験の `params.py` に固定する。`config.py` や環境変数から読まない。
- 先に `--smoke` で最後まで通す。本実行の前に `summary.md` の問いと判定の規則・`params.py`・`run.py` と変えたコードをコミットする(未コミットのコードで作った生成物は `make check` の W15 になる)。
- 完了した実験は書き換えない(条件を変えるなら新しい番号)。2つ以上の実験で使うロジックは `src/` へ。
- 長時間のジョブは `experiments/JOBS.md` に投入直後に書く。

## 過去の結果の取り込み

これまでの実験結果は、取り込み用の実験を作って論文に入れます。手順の全体は `docs/importing-past-results.md` にあります。

```bash
make experiment-import STUDY=study1 SLUG=logger_drift SOURCE=logger-drift_runs_2026-07
```

1. 表示されたコマンドで、利用者がホストで過去のファイルを `data/raw/legacy/<source>/` にコピーする。
2. マニフェスト `experiments/NNN_<slug>/inputs.sha256` を生成し、README の「由来」と `data/README.md` の台帳を埋める。
3. `run.py` は入力の照合と既報の数値との照合が通ってから、成果物ごとに R1(再計算)・R2(残っていた数値から再描画)・R3(画像や論文の数値をそのまま)で生成物を書く。`--smoke` で通してからコミットして本実行し、照合が通らなければ実行は失敗して `result/` は変わらない。
4. 進み具合は、その実験の `summary.md` の「残りの手順」に印をつけて残す。閉じるときは、`summary.md` と索引の状態を `完了` にし、索引の由来欄を `取り込み(R2)` のように書く。

## 図表と数値

図・表・本文中の数値は、すべてコードで `result/` に書き出します。手で編集せず、スクリプトで再生成します。

```python
from src.utils.figures import apply_visualization_defaults, import_figure, save_figure
from src.utils.tables import write_latex_table, write_latex_values

apply_visualization_defaults(cfg)
save_figure(fig, "study1-overview", cfg)                          # result/figures/
write_latex_table(df, "study1-summary", cfg, caption="Summary")   # result/tables/ (.tex + .csv)
write_latex_values({"n": 120, "rmse": 0.413}, "study1-main", cfg,
                   formats={"rmse": "{:.2f}"})                     # \val{study1-main-rmse}
import_figure(path, "study1-old-map", cfg, note="原データが失われた", license="own work")  # R3
```

- **名前は必ず `study1-<内容>`**。論文側(`draft/`)は全スタディの図を1つの `\graphicspath` 名前空間で探すため、接頭辞がないと衝突する。
- 実験の `run.py`(`experiment.start()` の中)で呼ぶと、生成物は `out/staged/` に置かれ、本実行が最後まで通ったときだけ `result/` に入る(`--smoke` や失敗した実行では `result/` は変わらない)。表にしないファイルは `run.promote()` で出す(`experiments/README.md` の「論文へ出すもの」)。`scripts/` のスクリプトから呼ぶと、すぐに `result/` に書く。
- どの関数も `<名前>.provenance.json` を横に書く(生成したスクリプト・実験番号・作った日時とコミット・ファイルの sha256・再現性・`sources` に渡した読んだファイル。実験の中では実行の開始時刻・シード・パラメータのハッシュも)。`make check` がこれを読む。
- `scripts/` のスクリプトで昇格するときは、読んだ CSV など(`result/tables/*.csv` や `data/processed/NNN_<slug>/` の中のファイル)を `sources=[...]` で渡して記録する(例: `save_figure(fig, "study1-fit", cfg, sources=[csv_path])`。`write_latex_table`・`write_latex_values` も同じ)。実験の `run.py` が他の実験の CSV を読むときも同じで、`run.promote()` にも渡す(例: `run.promote("study1-derived.csv", sources=[csv_path])`)。`make check` はそこから元の実験をたどり、撤回・中止・置き換え・進行中の実験の結果なら知らせる(W14)。`--list-generators` も同じ記録から作り直しの順(上流が先)を決める。
- 図の解像度・形式・フォントは、リポジトリのルートの `config.py` の `VISUALIZATION` から読む(論文全体で図の見た目をそろえるための設定で、数値は変えない)。
- 数値ファイル(`write_latex_values` の出力)は `draft/values.tex` に `\ThesisValues{../projects/study1/result/tables/study1-main}` の形で一度登録し、本文では `\val{study1-main-rmse}` と書く。結果の数値を本文に手で打たない。
- 表は章から `\input{../projects/study1/result/tables/study1-summary}` で読み込む。

`scripts/` のスクリプトでこのスタディの config を読む定型(`experiments/NNN_<slug>/run.py` では `parents[2]`):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # スタディのルート
import config as cfg
from src.utils.figures import save_figure  # 図表の関数は冒頭で import する
```

由来記録に入るコミットは、実験では `experiment.start()` が実行を始めた時点、`scripts/` のスクリプトでは `src.utils.figures`・`src.utils.tables` を import した時点のものです。実行の途中でコードが変わると警告が出て、その後に書いた生成物は未コミットのコードで作ったものとして記録されます(W15)。

実行はリポジトリのルートから、共有の Docker 環境で:

```bash
docker compose exec research-template uv run python projects/study1/scripts/<スクリプト>.py
```

## テスト

```bash
docker compose exec research-template uv run pytest projects/study1
```

`tests/` はこのスタディ自身のコード(`src/` と `scripts/`)のテストを置く場所で、複製した直後から通ります。`src/` に関数を足したら `tests/` にテストも足します。最初の `test_study_config.py` が書き方の見本で、スタディのモジュールは `conftest.py` の `load_module_by_path` でファイルのパスから読み込みます(どのスタディも同じ名前の `config.py`・`src` を持つため)。

`src/utils/` のヘルパーと実験の雛形は全スタディ共通で、テストはリポジトリの `tests/study_kit/` にあります。直すときは `projects/_template` で直して全スタディへ写します(`AGENTS.md` の「研究コード」)。
