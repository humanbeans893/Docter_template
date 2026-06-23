# Dissertation repository

A monorepo for a PhD dissertation: multiple self-contained studies plus the
integrated thesis manuscript.

## Environment

```bash
docker compose up -d
docker compose exec research-template uv sync
```

## Container

```bash
docker compose start
docker compose stop
docker compose exec research-template bash
docker compose exec research-template uv add <package>
```

A single shared Python environment serves all studies.

## Layout

```text
Docter_template/
├── projects/               # One self-contained study per subdirectory
│   ├── _template/          # Copy this to start a new study
│   └── study1/             # data/ src/ scripts/ result/ config.py
├── draft/                  # Integrated thesis (LuaLaTeX, ltjsreport)
│   ├── main.tex            # \include of chapters
│   ├── preamble.tex        # packages + \graphicspath
│   ├── frontmatter/        # titlepage, abstract, acknowledgments
│   ├── chapters/           # NN-*.tex (one chapter per study) + _chapter-template.tex
│   ├── backmatter/         # appendices
│   ├── supplementary.tex   # standalone supplementary document
│   └── reference.bib       # shared bibliography
├── config.py               # repo-level shared constants (GEO, RANDOM, VISUALIZATION)
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Studies

Each study under `projects/` is self-contained (its own `data/`, `src/`,
`scripts/`, `result/`, and `config.py`). See `projects/README.md` for how to add
a study and why this is a monorepo rather than git submodules. Study-local data
under `projects/<study>/data/` is kept out of Git except for the directory
structure.

## Manuscript

The thesis is split across files and compiled from `draft/main.tex` with
LuaLaTeX:

```bash
cd draft && lualatex -interaction=nonstopmode main.tex
bibtex main && lualatex main.tex && lualatex main.tex
```

Each study becomes a chapter under `draft/chapters/`. Figures are pulled directly
from each study's `result/figures/` via `\graphicspath` in `draft/preamble.tex`,
so they stay in sync with the code that generates them.
