# Host-side entry point for the dissertation repository.
# Python runs inside Docker; LaTeX (draft/compile.sh) and the stdlib-only tools under tools/ run
# on the host. `make` or `make help` lists the targets.

.DEFAULT_GOAL := help

# docker-compose.yml runs the container as "${UID}:${GID}" so that files written in /workspace
# stay owned by you. Bash does not export UID/GID, so every target gets them from here.
export UID := $(shell id -u)
export GID := $(shell id -g)

COMPOSE  := docker compose
SERVICE  := research-template
EXEC     := $(COMPOSE) exec $(SERVICE)
# The uv image the Dockerfile builds on, so `make lock` resolves with the same Python.
UV_IMAGE := $(shell sed -n 's/^FROM //p' Dockerfile | head -n 1)

# Show what runs in the container before a command that may recreate or stop it: recreating
# the container stops every `docker compose exec` job (check STATE.md and the experiments/JOBS.md
# files).
define show_running_jobs
	@out="$$($(COMPOSE) top 2>/dev/null)"; \
	if [ -n "$$out" ]; then \
		echo "Running in the container now. Recreating or stopping it ends these processes"; \
		echo "(see STATE.md and projects/*/experiments/JOBS.md for long jobs):"; \
		printf '%s\n' "$$out"; \
	fi
endef

# LaTeX intermediates left in draft/ by a lualatex run outside draft/compile.sh. STALE_TEX is
# the set compile.sh refuses to build with (anywhere in draft/); EXTRA_TEX is left alone in
# draft/figures/, which holds hand-made figure files.
STALE_TEX := -name '*.aux' -o -name '*.bbl' -o -name '*.toc' -o -name '*.lof' -o -name '*.lot' \
	-o -name '*.out' -o -name '*.blg' -o -name '*.fls' -o -name '*.fdb_latexmk'
EXTRA_TEX := -name '*.log' -o -name '*.synctex.gz' -o -name '*.tdo' -o -name '*.bcf' \
	-o -name '*.run.xml' -o -name '*.xdv'

.PHONY: help build up down ensure-up lock test lint format \
	check check-final pdf pdf-review pdf-final supplementary submission clean-tex \
	study experiment experiment-import archive security security-history hooks precommit

help: ## List the targets
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Container ------------------------------------------------------------------------------

build: ## Rebuild the image after pyproject.toml or uv.lock changes
	$(COMPOSE) build

# GPU and the read-only /external mount are not targets of their own: list
# docker-compose.gpu.yml / docker-compose.files.yml once in COMPOSE_FILE in .env (see
# .env.example). Every docker compose command, `make up` and the automatic start before
# `make test` then keep them; a one-off `-f` would be lost on the next `make up`.
up: ## Start the container (jobs stop on recreate; GPU and /external: COMPOSE_FILE in .env)
	$(show_running_jobs)
	$(COMPOSE) up -d --build

down: ## Stop and remove the container (running jobs stop)
	$(show_running_jobs)
	$(COMPOSE) down

ensure-up:
	@$(COMPOSE) ps --status running --services | grep -qx $(SERVICE) || $(COMPOSE) up -d

lock: ## Update uv.lock in a throwaway uv container (no host Python), then run make build
	docker run --rm -u "$(UID):$(GID)" -e UV_CACHE_DIR=/tmp/uv-cache \
		-v "$(CURDIR)":/work -w /work $(UV_IMAGE) uv lock
	@echo "uv.lock updated. Bake it into the image with: make build"

# --- Code -----------------------------------------------------------------------------------

test: ensure-up ## pytest in the container; options with ARGS="-k name"
	$(EXEC) uv run pytest $(ARGS)

lint: ensure-up ## ruff check + format check in the container
	$(EXEC) uv run ruff check .
	$(EXEC) uv run ruff format --check .

format: ensure-up ## Auto-fix lint findings and reformat in the container
	$(EXEC) uv run ruff check --fix .
	$(EXEC) uv run ruff format .

# --- Manuscript -----------------------------------------------------------------------------

pdf: ## Build draft/main.pdf and draft/supplementary.pdf
	bash draft/compile.sh

pdf-review: ## Build draft/review.pdf for the supervisor; one chapter: ONLY=02-study1
	bash draft/compile.sh review $(if $(ONLY),--only "$(ONLY)")

pdf-final: ## Build draft/submission.pdf (final layout, no draft notes)
	bash draft/compile.sh submission

supplementary: ## Build draft/supplementary.pdf
	bash draft/compile.sh supplementary

check: ## Check main, review and supplementary (refs, citations, figures, values, provenance)
	python3 tools/thesis_check.py --all

# One run checks both documents as one: a figure or bib entry either of them uses is used
# (tests/test_thesis_check.py runs this exact command).
check-final: ## Strict submission checks of submission.tex and supplementary.tex together
	python3 tools/thesis_check.py --main submission.tex --main supplementary.tex --submission --strict

submission: ## Build submission.pdf and supplementary.pdf, then run make check-final
	bash draft/compile.sh submission supplementary
	@$(MAKE) --no-print-directory check-final

clean-tex: ## Remove draft/build/ and stray LaTeX files in draft/ (keeps PDFs and figures)
	rm -rf draft/build
	find draft -type f \( $(STALE_TEX) \) -print -exec rm -f -- {} +
	find draft -path draft/figures -prune -o -type f \( $(EXTRA_TEX) \) -print -exec rm -f -- {} +

# --- Studies and experiments ----------------------------------------------------------------
# Titles and summaries are passed through the environment ("$$TITLE"), so quotes, $ and
# backslashes reach the tools unchanged: TITLE='Study 2: Effects' make study NAME=study2.
# DRY_RUN=1 shows the plan without writing anything.

study: ## New study + chapter: TITLE='Chapter title' make study NAME=<name> (TITLE_TEX=, NOCHAPTER=1)
	@if [ -z "$${NAME:-}" ]; then \
		echo "usage: TITLE='Chapter title' make study NAME=<name>" >&2; \
		echo "       TITLE_TEX='LaTeX title' make study NAME=<name>   (title inserted as LaTeX)" >&2; \
		echo "       make study NAME=<name> NOCHAPTER=1               (a study without its own chapter)" >&2; \
		exit 2; \
	fi; \
	set -- "$$NAME"; \
	if [ -n "$${NOCHAPTER:-}" ] && [ "$$NOCHAPTER" != 0 ]; then set -- "$$@" --no-chapter; fi; \
	if [ -n "$${TITLE:-}" ]; then set -- "$$@" --title "$$TITLE"; fi; \
	if [ -n "$${TITLE_TEX:-}" ]; then set -- "$$@" --title-tex "$$TITLE_TEX"; fi; \
	if [ "$$#" -eq 1 ]; then \
		echo "make study: set TITLE (or TITLE_TEX, or NOCHAPTER=1), e.g. TITLE='Study 2: Effects' make study NAME=$$NAME" >&2; \
		exit 2; \
	fi; \
	if [ -n "$${DRY_RUN:-}" ]; then set -- "$$@" --dry-run; fi; \
	python3 tools/new_study.py "$$@"

experiment: ## New experiment: make experiment STUDY=<study> SLUG=<slug> [SUMMARY='question in a few words']
	@if [ -z "$${STUDY:-}" ] || [ -z "$${SLUG:-}" ]; then \
		echo "usage: make experiment STUDY=<study> SLUG=<slug> [SUMMARY='question in a few words']" >&2; \
		exit 2; \
	fi; \
	set -- "$$STUDY" "$$SLUG"; \
	if [ -n "$${SUMMARY:-}" ]; then set -- "$$@" --summary "$$SUMMARY"; fi; \
	if [ -n "$${DRY_RUN:-}" ]; then set -- "$$@" --dry-run; fi; \
	python3 tools/new_experiment.py "$$@"

experiment-import: ## Import a past result: make experiment-import STUDY=<study> SLUG=<slug> [SOURCE= FROM= LEGACY_ID= SUMMARY=]
	@if [ -z "$${STUDY:-}" ] || [ -z "$${SLUG:-}" ]; then \
		echo "usage: make experiment-import STUDY=<study> SLUG=<slug> [SOURCE=<name under data/raw/legacy/>]" >&2; \
		echo "         [FROM=<path of the past files>] [LEGACY_ID=<repo>@<sha>:experiments/NNN_x]" >&2; \
		echo "         [SUMMARY='question in a few words']" >&2; \
		exit 2; \
	fi; \
	set -- "$$STUDY" "$$SLUG" --import; \
	if [ -n "$${SOURCE:-}" ]; then set -- "$$@" --source "$$SOURCE"; fi; \
	if [ -n "$${FROM:-}" ]; then set -- "$$@" --from "$$FROM"; fi; \
	if [ -n "$${LEGACY_ID:-}" ]; then set -- "$$@" --legacy-id "$$LEGACY_ID"; fi; \
	if [ -n "$${SUMMARY:-}" ]; then set -- "$$@" --summary "$$SUMMARY"; fi; \
	if [ -n "$${DRY_RUN:-}" ]; then set -- "$$@" --dry-run; fi; \
	python3 tools/new_experiment.py "$$@"

archive: ## Archive the submitted version: make archive TAG=<tag at HEAD> (runs make submission)
	@if [ -z "$${TAG:-}" ]; then \
		echo "usage: make archive TAG=<tag>   (create the tag on HEAD first: git tag <tag>)" >&2; \
		exit 2; \
	fi
	@$(MAKE) --no-print-directory submission
	python3 tools/archive_thesis.py --tag "$$TAG"

# --- Repository -----------------------------------------------------------------------------

security: ## Scan tracked files for secrets, private data, large files, and unpinned Actions
	python3 tools/public_repo_check.py

security-history: ## Also require a GitHub noreply email in every commit
	python3 tools/public_repo_check.py --history

hooks: ## Install host-side pre-commit hooks
	uvx pre-commit install

precommit: ## Run pre-commit hooks against all files
	uvx pre-commit run --all-files
