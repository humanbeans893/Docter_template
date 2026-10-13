# NNN_<slug>: <実験の題>

- **日付**: YYYY-MM-DD
- **今の結論と状態**: [summary.md](summary.md)。この README は経緯の記録です。古い記述は消さず、訂正は末尾の「訂正・追記」に日付をつけて足します。

## 目的

<この実験で何を確かめたいか。判定の規則は summary.md に書く。>

## 背景

<なぜこの実験が必要か。先行する実験(例: `003_baseline_fit`)、決定記録(`docs/decisions/`)、研究ログ(`docs/research-log.md`)、文献(bib キー)への参照。>

## 方法

- パラメータ: `params.py`(値の正。ここには要点だけ書く)
- 入力: <使うデータ(`data/README.md` の台帳の名前)と上流の表。他の実験の `out/` は読まない。>
- 実行(リポジトリのルートで、`--smoke` を先に。本実行の前に `summary.md` の問いと判定の規則・`params.py`・`run.py` と変えたコードをコミットする):

```bash
docker compose exec research-template uv run python projects/study1/experiments/NNN_<slug>/run.py --smoke
docker compose exec research-template uv run python projects/study1/experiments/NNN_<slug>/run.py
```

## 結果

<本実行の日付とコミット(`out/params_used.json`)、得られた図・数値。数値には出所の CSV(行・列)を添え、作業用の図表は `out/` のファイル名で参照する。食い違ったら CSV が正。>

## 考察

<結果から何が言えるか。想定との差。>

## 次にやること

- [ ] <次の実験・確認事項>

## 訂正・追記

<日付をつけて足す。前の記述は消さない。なければ「なし」。>
