# Study 1

博士論文の最初のスタディです。**ディレクトリ名は研究内容に合わせてリネームして構いません**(その場合は `draft/preamble.tex` の `\graphicspath` も合わせて変更)。

このスタディの研究概要・目的・進捗をここに書いてください:

- **研究課題**: (何を明らかにするか)
- **データ**: (何を使うか → 詳細は `data/README.md` の台帳へ)
- **対応する章**: `draft/chapters/02-study1.tex`

## 中身

- `data/{raw,interim,processed}/` — スタディ内データ。`raw/` は不変、加工はスクリプト経由。大きなファイルは Git に入りません
- `data/README.md` — データ台帳(データを置いたら必ず記入)
- `src/{utils,models,methods,analysis}/` — 再利用コード(`utils/` に図表ヘルパーが入っています)
- `scripts/` — 薄い実行入口
- `result/{figures,tables,animations}/` — 生成物(手で編集せず再生成)
- `tests/` — スタディ携行テスト
- `config.py` — スタディ内パス + 共有定数

## 実行方法

```bash
docker compose exec research-template uv run python projects/study1/scripts/<スクリプト>.py
docker compose exec research-template uv run pytest projects/study1
```

スクリプト内で config を読む定型:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # スタディルート
import config as cfg
```

## 図表ヘルパー

```python
from src.utils.figures import apply_visualization_defaults, save_figure
from src.utils.tables import write_latex_table

apply_visualization_defaults(cfg)
save_figure(fig, "study1-overview", cfg)                       # → result/figures/
write_latex_table(df, "study1-summary", cfg, caption="Summary")  # → result/tables/
```

**図表のファイル名は `study1-<内容>` 形式**(論文側の `\graphicspath` は全スタディ共有の名前空間のため)。
