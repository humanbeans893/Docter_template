# Host-side entry point for the dissertation repo.
# Python runs inside Docker; LaTeX compiles on the host. Run `make` for help.

.DEFAULT_GOAL := help

COMPOSE := docker compose
EXEC    := $(COMPOSE) exec research-template

.PHONY: help up down sync lock test lint format check pdf bib clean-tex hooks precommit

help: ## List available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Build (if needed) and start the research container
	$(COMPOSE) up -d --build

down: ## Stop and remove the research container
	$(COMPOSE) down

sync: ## Install the Python environment from uv.lock
	$(EXEC) uv sync

lock: ## Re-resolve dependencies and refresh uv.lock
	$(EXEC) uv lock

test: ## Run all tests (repo-level + every study) inside Docker
	$(EXEC) uv run pytest

lint: ## Ruff lint + format check inside Docker (source of truth)
	$(EXEC) uv run ruff check .
	$(EXEC) uv run ruff format --check .

format: ## Auto-fix lint findings and reformat inside Docker
	$(EXEC) uv run ruff check --fix .
	$(EXEC) uv run ruff format .

check: ## Manuscript consistency checks (tools/thesis_check.py)
	$(EXEC) uv run python tools/thesis_check.py

pdf: ## Build draft/main.pdf (latexmk; falls back to the manual sequence)
	@if command -v latexmk >/dev/null 2>&1; then \
		cd draft && latexmk; \
	else \
		echo "latexmk not found (install once: sudo apt install latexmk); using the manual sequence"; \
		$(MAKE) bib; \
	fi

bib: ## Manual full build: lualatex -> bibtex -> lualatex x2
	cd draft \
		&& lualatex -interaction=nonstopmode -file-line-error main.tex \
		&& bibtex main \
		&& lualatex -interaction=nonstopmode -file-line-error main.tex \
		&& lualatex -interaction=nonstopmode -file-line-error main.tex

clean-tex: ## Remove LaTeX build artifacts (keeps main.pdf)
	@if command -v latexmk >/dev/null 2>&1; then cd draft && latexmk -c; fi
	find draft \( -name '*.aux' -o -name '*.bbl' -o -name '*.blg' -o -name '*.out' \
		-o -name '*.toc' -o -name '*.lof' -o -name '*.lot' -o -name '*.fls' \
		-o -name '*.fdb_latexmk' -o -name '*.synctex.gz' -o -name '*.tdo' \
		-o -name '*.log' \) -delete

hooks: ## Install git pre-commit hooks on the host (one-time)
	uvx pre-commit install

precommit: ## Run all pre-commit hooks against the whole repo
	uvx pre-commit run --all-files
