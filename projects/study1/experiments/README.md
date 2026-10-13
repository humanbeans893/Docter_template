# experiments/ — このスタディの実験

試行錯誤の実験を、番号付きディレクトリとして積み上げる場所です。規則は `AGENTS.md` の「実験」だけに書き、ここには手順と、実行の仕組み(`src/utils/experiment.py`)の振る舞いを書きます。どのスタディでも同じ内容です(`tests/test_repo_structure.py` が `projects/_template` との一致を検査します。スタディ固有のことはスタディの `README.md` へ)。

## ファイル

| ファイル | 役割 | 書くとき |
|---|---|---|
| `EXP_SUMMARY.md` | 索引(1実験1行)。セッションの初めに読む | 実験を作ったとき、状態・結論が変わったとき |
| `EXP_ARCHIVE.md` | 論文で使わずに終わった完了・中止の行の保管庫 | 索引が長くなったとき |
| `JOBS.md` | 長時間・高コストのジョブの台帳 | 投入した直後と、終わったとき |
| `NNN_<slug>/summary.md` | 今の結論(50行・3000字まで)。前提にする・引用する前に読む | 作ったとき(問い・判定の規則)、本実行の後、結論が変わったとき |
| `NNN_<slug>/README.md` | 経緯の記録(追記だけ。状態は書かない) | 意味のある実行のたびに |
| `NNN_<slug>/run.py`・`params.py` | 入口と、結果を変えうる値のすべて | 本実行の前にコミットし、終わったら変えない |
| `NNN_<slug>/inputs.sha256` | 取り込み実験だけ。過去のファイルのマニフェスト | 生成してコミットする |
| `NNN_<slug>/out/` | 出力(Git 管理外) | `run.py` が書く |

## 新しい実験

リポジトリのルートで:

```bash
make experiment STUDY=study1 SLUG=baseline_fit
SUMMARY='基準モデルで誤差が下がるか' make experiment STUDY=study1 SLUG=baseline_fit
```

`tools/new_experiment.py` が番号を決めて `_template/` を複製し、名前・スタディ・日付(と `SUMMARY` を `summary.md` と README の題)を埋め、索引に `| NNN | slug | (実行前) | 進行中 | — | 新規 |` を足します。

1. `summary.md` に問いと判定の規則を書き、`params.py`(`SEED`・`PARAMS`・`SMOKE`)を決めて、一緒にコミットする。
2. `run.py` を実装する。ロジックは `src/` に置いて呼び、冒頭の `sys.path` の処理と import は消さない。
3. `--smoke` で最後まで通し、段階ごとの所要時間を見る。長い実行なら `docs/launch-checklist.md` を通す。
4. `git status` でコードがコミット済みであることを確かめて、本実行する。
5. `README.md` に日付をつけて経緯を足し、`summary.md`(答え・言えないこと・主な数値・本実行・昇格)と索引の行(一行で・状態)を同じコミットで直す。

```bash
docker compose exec research-template uv run python projects/study1/experiments/NNN_<slug>/run.py --smoke
docker compose exec research-template uv run python projects/study1/experiments/NNN_<slug>/run.py
```

## 実行の仕組み

`run.py` は `with experiment.start(__file__, params) as run:` の中で動きます(設定は `run.py` が import したこのスタディの `config`)。

| | 本実行 | `--smoke` |
|---|---|---|
| パラメータ | `params.PARAMS` | `params.PARAMS` に `params.SMOKE` を上書き |
| 出力先 | `out/` | `out/smoke/` |
| 論文へ出すもの | `out/staged/` に置かれ、最後まで通ったら `result/`(と `data/processed/NNN_<slug>/`)へまとめて入る | 確かめるだけ(`out/smoke/staged/` で中身を見られる)。`result/` には入らない |
| 記録 | `out/params_used.json` | `out/smoke/params_used.json` |

- **始める前の確認.** 同じ出力先で別の実行が動いていれば止まる(`out/.lock`)。完了した本実行があれば `--overwrite` が要る。記録の無いファイルが出力先にあっても `--overwrite` が要る。`running` のまま止まった記録(強制終了・メモリ不足・コンテナの作り直し)は、次の実行が片づける。`params.py` の `SEED`・`PARAMS`・`SMOKE` は、何かを消す前に確かめる。
- **前の出力を消す.** 始めるときに、前の実行がその出力先に残したものを消す(`.gitkeep`・`.lock` と、本実行なら `smoke/` は残す)。`--overwrite` はここで前の `out/` を消すので、その実行が失敗しても前の `out/` は戻らない(`result/` は前のまま)。
- **段階と記録.** `run.stage("…")` が段階の始まりを表示し、記録に時刻を残す。`out/params_used.json` は始め・各段階・終わりに書き直す: 状態(`running`・`completed`・`failed`)、シード、パラメータとそのハッシュ、開始時のコミットと未コミットのコードの一覧、`code_state`(`clean`・`uncommitted`・`changed_during_run`・`unknown`)、段階、`result/` に出したファイル(`promoted`)と消したファイル(`removed`)、失敗ならトレースバック。SIGTERM・SIGHUP・Ctrl-C で止めた実行は `failed` になる。ただし公開がファイルを入れ替え始めた後に来た停止は、記録が `completed`(`promoted`・`removed` 入り)になるまで待ってから効く(終了コードは 130・143 のまま)。
- **出力の場所.** `run.out("名前")` は `out/` の下の作業用のパス。外を指す名前や、`staged/`・記録・ロック(本実行では `smoke/` も)を指す名前は止まる。取り込み実験の照合の記録(`verify_inputs` のキャッシュ)は `data/interim/NNN_<slug>/` に置き、実行をまたいで使う。
- **呼んだ時点の確認.** ヘルパーと `run.promote()` は、呼んだ時点で次を確かめて止まる(`--smoke` でも): 名前が `study1-` で始まらない(W16)、同じ名前を1回の実行で2回書く、`result/` にある同じ名前の表・数値・ファイルと種類が違う、雛形(`_template`・`_import_template`)の本実行で書こうとした、`run.promote()` の行き先が `result/tables/` と `config.PROCESSED_DATA_DIR / run.name` の外。実験の `run.py` が `experiment.start()` の外でヘルパーを呼んでも止まる。
- **公開.** 本実行が最後まで通ると、`out/staged/` の生成物を `result/` へまとめて入れる(全部か、何もしないか。公開の途中で強制終了したら、そのスタディの次の本実行が始めに元に戻す。それまでは `result/.publication.json` が残り、`make check` が E12 で知らせるので、PDF を作る前に止まった実験をもう一度本実行する。`--smoke` では戻らない)。同じ名前の前の生成物は丸ごと入れ替わり(別の形式で残っていた図も消える)、この実験が前に出して今回は出さなかった生成物も消える(記録の `removed`。Git から戻せる)。`data/processed/NNN_<slug>/` は、この実行がそこへ昇格したときだけ丸ごと入れ替わる。
- **コードの状態.** 由来記録のコミットは実行を始めたときのもの。未コミットのコードで始めた実行や、実行中にコードが変わった後に書いた生成物(`run.promote()` のファイルは公開する時点で確かめる)は `git_dirty: true` になり、警告が出る(`make check` の W15。提出前にコミットして作り直す)。実行中に同じスタディで新しい実験を作っても、コードが変わった扱いになる(`experiments/` の `.py` もコードに数える)ので、次に使う実験は長い本実行の前に作ってコミットしておく。
- **同時に動かす.** 1つの実験の本実行と `--smoke` は同時に動かせる。同じ出力先の2つ目は止まる。ロックは1台(1つのコンテナ)の中でしか効かない(共有のファイルシステムの上で、別の計算機から同じ実験を動かさない)。
- **作り直しの確認.** 提出前の作り直し(`python3 tools/thesis_check.py --list-generators`)は、実験を `--overwrite` 付きで、上流の実験から順に並べる。

## 論文へ出すもの

論文や他の実験が使うものは、`experiment.start()` の中で**コードで**出します。手でコピーせず、論文から `out/` を読みません(`make check` の E10)。

| 出すもの | 書き方 | 入る場所 |
|---|---|---|
| 図 | `figures.save_figure(fig, "study1-overview", config)` | `result/figures/` |
| 再生成できない過去の画像 | `figures.import_figure(path, "study1-map", config, note=..., license=...)` | `result/figures/`(R3) |
| 表 | `tables.write_latex_table(df, "study1-summary", config)` | `result/tables/`(`.tex` と `.csv`) |
| 本文中の数値 | `tables.write_latex_values(values, "study1-main", config, formats=...)` | `result/tables/`(`.tex` と `.csv`) |
| 表にしないファイル(図を描くための CSV など) | `run.promote("study1-points.csv")`(`run.out()` で書いたもの) | `result/tables/` |
| 大きな出力 | `run.promote("grid.nc", dest_dir=config.PROCESSED_DATA_DIR / run.name)` | `data/processed/NNN_<slug>/`(Git 管理外) |

- どれも `<名前>.provenance.json` を横に書き、実験・スクリプト・開始時のコミット・実行(開始時刻・シード・パラメータのハッシュ)を記録する(`data/processed/` を除く)。`make check` はこれを読んで、撤回・中止・置き換えの実験や、まだ `進行中` の実験の生成物(W14)、未コミットのコードで作った生成物(W15)を知らせる。
- 数値ファイルは `draft/values.tex` に一度登録し、本文では `\val{study1-main-<キー>}` と書く。
- 他の実験の `result/tables/*.csv` や `data/processed/NNN_<slug>/` を読んで作るものは、読んだファイルを `sources=[...]` で渡す: ヘルパーにも、`run.promote("study1-derived.csv", sources=[csv_path])` にも(`run.promote()` は `result/tables/` に出すときだけ記録できる)。`make check` の W14 と `--list-generators` は、由来記録の `sources` から上流の実験をたどる。渡さないと、上流の実験を撤回しても W14 が出ず、作り直しの一覧から上流の実験が抜ける。
- 図の体裁だけを直すコードは `src/`(例: `src/analysis/plots.py`)か `scripts/` の昇格スクリプトに置き、`result/tables/*.csv` や `data/processed/NNN_<slug>/` を読む。読んだファイルは `sources=[...]` で由来記録に残す(`make check` はそこから元の実験をたどる)。`scripts/` は実験の外なので、書いた生成物はすぐに `result/` に入る。完了した実験の `run.py` は直さない(条件を変えるなら新しい番号の実験にする)。
- 論文で使わなくなった生成物(撤回・中止・置き換えにした実験のもの、完了した実験が出す診断用の図など)は `result/` に残してよい。公開が実験の前の生成物を入れ替え・消すのは、同じ実験をもう一度本実行したときだけ。`make check` は、どの文書にも入っていない生成した図を I5(情報。`--strict` でも失敗しない)で挙げるだけで、本文が使えば W14 が知らせる。提出前の作り直し(`--list-generators`)は、論文が使う生成物を作った実験とスクリプトだけを実行し直す。完了した実験が出す使わない図は、作り直すと同じ中身でもう一度出るので、手で消さず、`run.py` も直さない(消していると `git status` に `??` で出る)。撤回・中止・置き換えの実験は並ばないので、その生成物はコミットしたまま変わらない。記録として残すか、本文で使わなくなってから由来記録(`.provenance.json`)と一緒に `git rm` する(どのファイルかは由来記録の `experiment` 欄と `summary.md` の「昇格」で分かる。消す前にユーザーに確かめる)。

## 過去の結果を取り込む

```bash
make experiment-import STUDY=study1 SLUG=logger_drift SOURCE=logger-drift_runs_2026-07
```

`_import_template/` から作り、索引に `| NNN | slug | (実行前) | 進行中 | — | 取り込み |` を足し、利用者がホストで実行するコピーとマニフェスト生成のコマンドを表示します(README の「取り込み元とコマンド」にも残る)。残りの手順は `summary.md` の「残りの手順」に印をつけて進めます。`run.py` は 入力の照合 → `out/` での作り直し → 既報の数値との照合(照合の表は `run.promote()` で `result/tables/study1-<slug>-crosscheck.csv` に出る)→ 生成物を書く、の順に進み、照合が通らなければ実行は `failed` になって `result/` は変わりません。閉じるときに状態を `完了`、由来欄を `取り込み(R2)` のようにします。手順の全体は `docs/importing-past-results.md` にあります。
