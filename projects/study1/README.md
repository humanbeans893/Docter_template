# Study 1

This is the first study of the dissertation. To start another study, copy the template:

```bash
cp -r projects/_template projects/study2
```

## Contents

- `data/{raw,interim,processed}/` — study-local data. `raw/` is immutable; keep
  large files out of Git (they are gitignored).
- `src/{utils,models,methods,analysis}/` — reusable code for this study.
- `scripts/` — thin, reproducible entry points that orchestrate `src/`.
- `result/{figures,tables,animations}/` — generated outputs; regenerate from code.
- `config.py` — study-local paths (`RAW_DATA_DIR`, `FIGURE_DIR`, …) plus shared
  constants (`GEO`, `RANDOM`, `VISUALIZATION`) imported from the repo-root config.

## Running

From the repo root, inside the shared Docker environment:

```bash
docker compose exec research-template uv run python projects/<study>/scripts/<script>.py
```

In a script, import this study's config with:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # study root
import config as cfg
```
