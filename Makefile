# Host-side entry point for the dissertation repository.
# Python runs inside Docker; LaTeX and stdlib-only checks run on the host.

.DEFAULT_GOAL := help

COMPOSE := docker compose
EXEC    := $(COMPOSE) exec research-template
TEXFLAGS := -interaction=nonstopmode -file-line-error -halt-on-error

.PHONY: help up up-files down sync lock test lint format check check-final \
	pdf pdf-final supplementary submission bib clean-tex security security-history \
	zotero-forward zotero-check hooks precommit

help: ## List available targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Build (if needed) and start the research container
	$(COMPOSE) up -d --build

up-files: ## Start with EXTERNAL_FILES_DIR mounted read-only at /external
	$(COMPOSE) -f docker-compose.yml -f docker-compose.files.yml up -d --build

down: ## Stop and remove the research container
	$(COMPOSE) down

sync: ## Install the Python environment from uv.lock
	$(EXEC) uv sync --locked

lock: ## Re-resolve dependencies and refresh uv.lock
	$(EXEC) uv lock

test: ## Run all tests inside Docker
	$(EXEC) uv run pytest

lint: ## Ruff lint + format check inside Docker
	$(EXEC) uv run ruff check .
	$(EXEC) uv run ruff format --check .

format: ## Auto-fix lint findings and reformat inside Docker
	$(EXEC) uv run ruff check --fix .
	$(EXEC) uv run ruff format .

check: ## Check manuscript references, citations, figures, metadata, and log
	python3 tools/thesis_check.py

check-final: ## Strict submission check; placeholders, TODOs, and warnings fail
	python3 tools/thesis_check.py --main submission.tex --submission --strict

pdf: ## Build draft/main.pdf
	$(MAKE) bib JOB=main

pdf-final: ## Build draft/submission.pdf with draft annotations disabled
	$(MAKE) bib JOB=submission

supplementary: ## Build draft/supplementary.pdf
	@if command -v latexmk >/dev/null 2>&1; then \
		cd draft && latexmk supplementary.tex; \
	else \
		cd draft && lualatex $(TEXFLAGS) supplementary.tex \
			&& lualatex $(TEXFLAGS) supplementary.tex; \
	fi

submission: pdf-final check-final ## Build and validate the submission PDF

bib: ## Build JOB.tex with LuaLaTeX + BibTeX (JOB defaults to main)
	@if command -v latexmk >/dev/null 2>&1; then \
		cd draft && latexmk $(or $(JOB),main).tex; \
	else \
		cd draft \
			&& lualatex $(TEXFLAGS) $(or $(JOB),main).tex \
			&& bibtex $(or $(JOB),main) \
			&& lualatex $(TEXFLAGS) $(or $(JOB),main).tex \
			&& lualatex $(TEXFLAGS) $(or $(JOB),main).tex; \
	fi

clean-tex: ## Remove LaTeX build artifacts while keeping PDFs
	@if command -v latexmk >/dev/null 2>&1; then \
		cd draft && latexmk -c main.tex && latexmk -c submission.tex && latexmk -c supplementary.tex; \
	fi
	find draft \( -name '*.aux' -o -name '*.bbl' -o -name '*.blg' -o -name '*.out' \
		-o -name '*.toc' -o -name '*.lof' -o -name '*.lot' -o -name '*.fls' \
		-o -name '*.fdb_latexmk' -o -name '*.synctex.gz' -o -name '*.tdo' \
		-o -name '*.log' \) -delete

security: ## Scan tracked files for secrets, private data, large files, and unpinned Actions
	python3 tools/public_repo_check.py

security-history: ## Also require GitHub noreply email in every commit
	python3 tools/public_repo_check.py --history

zotero-forward: ## Forward WSL2 localhost to the Windows Zotero local API
	@nohup python3 .claude/scripts/zotero-forward.py --port "$${ZOTERO_PORT:-23119}" \
		>/tmp/zotero-forward.log 2>&1 & echo $$! >/tmp/zotero-forward.pid
	@sleep 1
	@cat /tmp/zotero-forward.log

zotero-check: ## Check whether the local Zotero connector endpoint responds
	@code=$$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 \
		"http://127.0.0.1:$${ZOTERO_PORT:-23119}/connector/ping" || true); \
		test "$$code" != "000" && echo "Zotero local API responded with HTTP $$code" \
		|| { echo "Zotero local API did not respond" >&2; exit 1; }

hooks: ## Install host-side pre-commit hooks
	uvx pre-commit install

precommit: ## Run pre-commit hooks against all files
	uvx pre-commit run --all-files
