# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

Think in English. **Respond in Japanese by default**; switch only if the user writes in another language.

---

## Collaboration Principles

The user may be a researcher with little coding-agent experience. Do not assume git/Docker/LaTeX fluency.

- Before running a command, say in one plain sentence what it does and why.
- After every step, report the outcome **and the exact path of any produced file** (figure, table, PDF, log).
- Propose the next concrete step; never leave the user wondering what to do.
- Confirm before anything destructive or irreversible (deleting files, overwriting data, git push, package installs).
- When something fails, explain the cause in plain language first, then the fix.
- Prefer the `make` targets below over raw commands — they are the documented, user-visible interface.

---

## Quick Reference

```bash
make up      # build + start the Docker container
make test    # all tests (repo + every study), inside Docker
make lint    # ruff check + format check, inside Docker
make format  # auto-fix + reformat, inside Docker
make pdf     # build draft/main.pdf (latexmk, falls back to manual sequence)
make check   # manuscript consistency checks (tools/thesis_check.py)

# Run a study script (Python always goes through Docker)
docker compose exec research-template uv run python projects/<study>/scripts/<script>.py

# Package install (asks for confirmation — keep it that way), then refresh the lock
docker compose exec research-template uv add <package> && make lock

# Pre-git check
pwd && git branch && git status
```

Raw LaTeX fallback (when latexmk is unavailable): `cd draft && lualatex -interaction=nonstopmode main.tex && bibtex main && lualatex ... && lualatex ...` — this is what `make bib` runs.

---

## Project Overview

Monorepo for a PhD dissertation: self-contained studies under `projects/` plus the integrated LuaLaTeX manuscript under `draft/` (`ltjsreport` class; thesis text in **English**; user-facing docs in Japanese).

- `projects/<study>/` — one study: `data/{raw,interim,processed}`, `src/{utils,models,methods,analysis}`, `scripts/`, `result/{figures,tables,animations}`, `tests/`, `config.py`, `data/README.md` (data dictionary). `projects/_template/` is the skeleton to copy.
- `draft/` — `main.tex` (+ `\include`d chapters, one per study), `preamble.tex`, `notation.tex`, `reference.bib`, conventions in `draft/README.md`.
- `config.py` (repo root) — shared constants only (`GEO`, `RANDOM`, `VISUALIZATION`).
- `tools/thesis_check.py` — stdlib-only manuscript checker behind `make check`.
- `docs/` — research log, ADRs (`decisions/`), chapter reviews (`reviews/`).

Studies never depend on sibling studies. Extraction later: `git subtree split --prefix=projects/<study>`.

---

## The Dissertation Pipeline

The end-to-end flow this repo exists for. Know where a request sits in it and drive it to the next verifiable state.

### 1. New study

```bash
cp -r projects/_template projects/<study>
docker compose exec research-template uv run pytest projects/<study>   # copy sanity check
```

A study becomes a chapter only when there is something to write; wiring a chapter is step 5.

### 2. Data intake

- New raw data goes to `data/raw/` — **immutable**; a PreToolUse hook blocks agent writes there. Never work around it (no shell redirects into `data/raw/` either).
- Immediately record the dataset in the study's `data/README.md`: source, retrieval date, license, checksum, schema, re-download command. Large data never enters git; this ledger is the only recovery path.
- Derived data is produced by scripts into `data/interim/` → `data/processed/`, never by hand.

### 3. Analysis code

- Reusable logic in `src/` (fail-explicit, see Error Handling); thin entry points in `scripts/`; run via Docker.
- Add or extend tests under the study's `tests/` for new `src/` functions.
- Verify: `make test && make lint`.

### 4. Figures and tables

- Always produce them from scripts using the study helpers:
  - `src/utils/figures.py` → `save_figure(fig, "<study>-<slug>", cfg)` — applies shared style, writes `result/figures/<study>-<slug>.png` + a provenance sidecar (script, commit, timestamp).
  - `src/utils/tables.py` → `write_latex_table(df, "<study>-<slug>", cfg, caption=...)` — booktabs `.tex` into `result/tables/`, ready for `\input`.
- **File names must be study-prefixed** (`ocean-heat-trend`, not `fig1`): all studies share one flat `\graphicspath` namespace.
- Never hand-edit anything under `result/` — rerun the generating script instead.

### 5. Chapter wiring (once per study)

1. Copy `draft/chapters/_chapter-template.tex` → `chapters/NN-<study>.tex`.
2. Enable its `\include{chapters/NN-<study>}` line in `draft/main.tex`.
3. Add the study's figures directory to `\graphicspath` in `draft/preamble.tex`.

### 6. Writing

Conventions live in `draft/README.md`; the essentials:

- Labels: `ch:` `sec:` `subsec:` `fig:` `tab:` `eq:` `alg:` `app:` prefixes; reference with `\cref{...}` (never bare `\ref`).
- Citations: single `draft/reference.bib`; keys `authYYYYfirstword` (Zotero Better BibTeX export). Never invent bib entries — ask the user or use Zotero (`/zotero-connect`).
- Figures: `\includegraphics[width=...]{<study>-<slug>}` — no path, no extension. Tables: `\input{../projects/<study>/result/tables/<name>.tex}`.
- Recurring symbols: define once in `draft/notation.tex`, use the macro everywhere.
- Draft margin notes: `\todo{...}`; the whole layer switches off via `\draftnotesfalse` in `preamble.tex` for the final document.
- Delete the placeholder `\nocite{lamport1994latex}` in `main.tex` (and its entry in `reference.bib`) once the first real citation exists.

### 7. Build to PDF and fix errors

```bash
make pdf    # → draft/main.pdf
```

On failure, open `draft/main.log` and find the **first** line starting with `!`. Common cases:

| Log message | Likely cause | Fix |
|---|---|---|
| `! Undefined control sequence` | typo in a macro / package not loaded | fix the macro or add the package in `preamble.tex` |
| `! LaTeX Error: File '...' not found` | missing `\input` target or package | check the path; chapter files need `.tex` on disk |
| `LaTeX Warning: Citation '...' undefined` | key missing from `reference.bib` or bibtex not run | add the key / rebuild (`make pdf` reruns bibtex) |
| `! Missing $ inserted` | math symbols (`_`, `^`, `\alpha`) outside math mode | wrap in `$...$` or escape `\_` |
| `! File ended while scanning use of ...` | unbalanced `{}` in an edited block | find the unmatched brace near the reported line |
| figure not appearing | script not run / name not study-prefixed / graphicspath missing | regenerate; `make check` E4 pinpoints it |

Report success as: PDF path + page count. Never claim a build succeeded without seeing latexmk/lualatex exit cleanly.

### 8. Quality gates and knowledge capture

- Code changed → `make test && make lint`. Manuscript changed → `make pdf && make check`. Sharing a draft → `/thesis-check`.
- At milestones run `/research-log` (results, decisions with rationale, dead ends → `docs/research-log.md`; big decisions → ADR in `docs/decisions/`).
- Chapter drafted → `/review-chapter` writes a structured review to `docs/reviews/`.

---

## Environment Rules

- Python execution and package management go through Docker: `docker compose exec research-template uv run ...` / `uv add ...`. Never use host Python or a host `.venv`.
- `uv.lock` is committed; after `uv add`, run `make lock` and commit the lock change.
- LaTeX compiles on the **host** (`make pdf`; the container has no TeX).
- Container caches live under `/workspace/.cache/`. Host port for Jupyter is `${JUPYTER_PORT:-8889}` (set in `.env` when the default collides).

## Error Handling

In `src/` code, fail explicitly:

```python
assert "key" in data, f"Expected 'key' in data. Got: {list(data.keys())}"
value = data["key"]
```

- No dummy values to make code run; no silently swallowed exceptions; broad `try`/`except` only when the failure mode is deliberately handled.
- Exploratory/notebook code may use defensive defaults, but convert to explicit validation before it moves into `src/` or `scripts/`.
- Documented exception: provenance collection in the figure/table helpers degrades to `"unknown"` rather than failing an output write.

## Code Reuse

1. Search before writing: `rg -n "<concept>" projects config.py`.
2. Check nearby working examples (`src/utils/figures.py`, `tables.py`, study tests) before inventing new calling patterns.
3. Missing reusable logic goes into the study's `src/` module areas (`utils`/`models`/`methods`/`analysis`), not into scripts.
4. Do not create near-duplicate helpers or change shared helper behavior without checking callers.

## Prohibitions

- **Git**: no unnecessary files; no push without verification; no history rewrites or reverting others' changes without an explicit request.
- **Data**: `data/raw/` is immutable (hook-enforced; do not bypass via Bash redirects). Do not hand-edit `interim`/`processed` — regenerate. Never delete data without explicit confirmation. Never commit large data (pre-commit blocks >1 MB).
- **Generated outputs**: `result/` is script-generated; regenerate rather than edit. Small figures/tables are committed (the thesis needs them); animations are gitignored.
- **Secrets**: never hardcode credentials; machine-local settings and secrets live in `.env` (gitignored; agents must not read it).

## Skills

| Skill | Purpose |
|---|---|
| `/thesis-check` | build PDF + `make check`, summarize errors with fixes, iterate to zero |
| `/research-log` | record session findings/decisions/dead ends to `docs/research-log.md` (+ ADRs) — confirm before writing |
| `/review-chapter` | 3-perspective parallel review of one chapter → report in `docs/reviews/` |
| `/session-save` | save session summary to memory + `.claude/sessions/` |
| `/zotero-connect` | WSL2 port forward to the Windows Zotero (bibliography workflows) |

## Permissions

- Usually safe (pre-allowed in `.claude/settings.json`): reading files, `make test/lint/check/pdf`, TeX compiles, `git status/diff/log/branch`.
- Confirm first: deleting files/directories, `uv add`, changing remotes/visibility/auth, anything irreversible or expensive.
- `settings.json` changes take effect after a session restart.
