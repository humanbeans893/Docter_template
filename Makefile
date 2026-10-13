# Host-side entry point of the doctoral thesis repository. Experiments run in separate research
# repositories; this repository gathers their content into projects/<id>/ (listed in
# research.json) and writes the thesis in draft/. LaTeX (draft/compile.sh) and the stdlib-only
# tools under tools/ run on the host; a small container runs pytest and ruff.
# `make` or `make help` lists the targets.

.DEFAULT_GOAL := help

# docker-compose.yml runs the container as "${UID}:${GID}" so that files written in /workspace
# stay owned by you. Bash does not export UID/GID, so every target gets them from here.
export UID := $(shell id -u)
export GID := $(shell id -g)

COMPOSE  := docker compose
SERVICE  := research-template
EXEC     := $(COMPOSE) exec $(SERVICE)
# Start the container when it is not running (first recipe line of test, lint and format).
START    := @$(COMPOSE) ps --status running --services | grep -qx $(SERVICE) || $(COMPOSE) up -d
# The uv image the Dockerfile builds on, so `make lock` resolves with the same Python.
UV_IMAGE := $(shell sed -n 's/^FROM //p' Dockerfile | head -n 1)

# LaTeX intermediates left in draft/ by a lualatex run outside draft/compile.sh. STALE_TEX is
# the set compile.sh refuses to build with (anywhere in draft/); EXTRA_TEX is left alone in
# draft/figures/, which holds hand-made figure files.
STALE_TEX := -name '*.aux' -o -name '*.bbl' -o -name '*.toc' -o -name '*.lof' -o -name '*.lot' \
	-o -name '*.out' -o -name '*.blg' -o -name '*.fls' -o -name '*.fdb_latexmk'
EXTRA_TEX := -name '*.log' -o -name '*.synctex.gz' -o -name '*.tdo' -o -name '*.bcf' \
	-o -name '*.run.xml' -o -name '*.xdv'

.PHONY: help build up down lock test lint format \
	pdf pdf-review pdf-final supplementary check check-final submission clean-tex archive \
	security security-history hooks precommit

help: ## ターゲットを一覧する
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-17s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Container (pytest and ruff only) -------------------------------------------------------

build: ## pyproject.toml・uv.lock を変えた後にイメージを作り直す
	$(COMPOSE) build

up: ## コンテナを起動する(設定が変わっていれば作り直す)
	$(COMPOSE) up -d --build

down: ## コンテナを止めて削除する
	$(COMPOSE) down

lock: ## uv.lock を使い捨ての uv コンテナで更新する(次に make build)
	docker run --rm -u "$(UID):$(GID)" -e UV_CACHE_DIR=/tmp/uv-cache \
		-v "$(CURDIR)":/work -w /work $(UV_IMAGE) uv lock

# --- Code -----------------------------------------------------------------------------------

test: ## コンテナ内の pytest。オプションは ARGS="-k name"
	$(START)
	$(EXEC) uv run pytest $(ARGS)

lint: ## コンテナ内の ruff check と ruff format --check
	$(START)
	$(EXEC) uv run ruff check .
	$(EXEC) uv run ruff format --check .

format: ## コンテナ内の ruff で自動修正と整形をする
	$(START)
	$(EXEC) uv run ruff check --fix .
	$(EXEC) uv run ruff format .

# --- Thesis ---------------------------------------------------------------------------------

pdf: ## draft/main.pdf と draft/supplementary.pdf を作る
	bash draft/compile.sh

pdf-review: ## 指導教員向けの draft/review.pdf を作る
	bash draft/compile.sh review

pdf-final: ## 提出用の体裁で draft/submission.pdf を作る(下書きの注記なし)
	bash draft/compile.sh submission

supplementary: ## draft/supplementary.pdf を作る
	bash draft/compile.sh supplementary

check: ## 原稿を検査する(参照・引用・図・数値・research.json)
	python3 tools/thesis_check.py --all

# One run checks both documents as one: a figure or bib entry either of them uses is used.
check-final: ## submission.tex と supplementary.tex を合わせて提出用に厳しく検査する
	python3 tools/thesis_check.py --main submission.tex --main supplementary.tex --submission --strict

submission: ## submission.pdf と supplementary.pdf を作り、make check-final を実行する
	bash draft/compile.sh submission supplementary
	@$(MAKE) --no-print-directory check-final

clean-tex: ## draft/build/ と draft/ に残った LaTeX の中間ファイルを消す(PDF と図は残す)
	rm -rf draft/build
	find draft -type f \( $(STALE_TEX) \) -print -exec rm -f -- {} +
	find draft -path draft/figures -prune -o -type f \( $(EXTRA_TEX) \) -print -exec rm -f -- {} +

archive: ## 提出版を保存する: make archive TAG=<HEAD に付けたタグ>(make submission も実行する)
	@if [ -z "$${TAG:-}" ]; then \
		echo "使い方: make archive TAG=<tag>   (先に HEAD にタグを付ける: git tag <tag>)" >&2; \
		exit 2; \
	fi
	@$(MAKE) --no-print-directory submission
	python3 tools/archive_thesis.py --tag "$$TAG"

# --- Repository -----------------------------------------------------------------------------

security: ## 追跡するファイルの秘密情報・個人のパス・大きなファイル・external/・固定していない Actions を調べる
	python3 tools/public_repo_check.py

security-history: ## さらに全コミットの作者メールが GitHub の noreply であることを確かめる
	python3 tools/public_repo_check.py --history

hooks: ## ホストに pre-commit のフックを入れる
	uvx pre-commit install

precommit: ## 全ファイルに pre-commit のフックをかける
	uvx pre-commit run --all-files
