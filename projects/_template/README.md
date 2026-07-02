# スタディ雛形(_template)

新しいスタディはこのディレクトリをコピーして始めます(このディレクトリ自体は編集しない):

```bash
cp -r projects/_template projects/<スタディ名>
docker compose exec research-template uv run pytest projects/<スタディ名>   # 複製の健全性確認
```

## 中身

- `data/{raw,interim,processed}/` — スタディ内データ。`raw/` は不変、加工は必ずスクリプト経由で `interim/`→`processed/` へ。大きなファイルは Git に入りません(gitignore 済み)
- `data/README.md` — **データ台帳**。データを置いたら入手元・取得日・チェックサム・再入手方法を記入する
- `src/{utils,models,methods,analysis}/` — このスタディの再利用コード
- `scripts/` — `src/` の関数を呼ぶだけの薄い実行入口
- `result/{figures,tables,animations}/` — 生成物。**手で編集せず、スクリプトで再生成**
- `tests/` — スタディ携行テスト。コピー直後から `pytest` が通る状態を保つ
- `config.py` — スタディ内パス(`RAW_DATA_DIR`, `FIGURE_DIR`, …)+ 共有定数(`GEO`, `RANDOM`, `VISUALIZATION`)

## 実行方法

リポジトリルートから、共有 Docker 環境で:

```bash
docker compose exec research-template uv run python projects/<スタディ名>/scripts/<スクリプト>.py
```

スクリプト内でこのスタディの config を読む定型:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # スタディルート
import config as cfg
```

## 図表ヘルパー

スタイル統一と来歴記録(生成スクリプト・コミット・日時)が自動で付きます:

```python
from src.utils.figures import apply_visualization_defaults, save_figure
from src.utils.tables import write_latex_table

apply_visualization_defaults(cfg)
save_figure(fig, "<スタディ名>-overview", cfg)     # → result/figures/ (+ .provenance.json)
write_latex_table(df, "<スタディ名>-summary", cfg, caption="Summary")  # → result/tables/
```

**図表のファイル名は必ず `<スタディ名>-<内容>`**。論文側(`draft/`)は全スタディの図を1つの `\graphicspath` 名前空間で解決するため、接頭辞がないと衝突します。

## テスト

```bash
docker compose exec research-template uv run pytest projects/<スタディ名>
```

`src/` に関数を足したら `tests/` にテストも足すこと。既存の `test_figures_helper.py` などが書き方の見本になります。
