.DEFAULT_GOAL := help
.PHONY: help venv install lint format test test-cov docker-build docker-up docker-down run watch clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv: ## Create a virtual environment
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv ## Install package and dev dependencies into .venv
	$(PIP) install -e ".[dev]"

lint: ## Run ruff linter and mypy
	ruff check .
	ruff format --check .
	mypy replaytagger/

format: ## Auto-format code with ruff
	ruff format .
	ruff check --fix .

test: ## Run test suite
	pytest

test-cov: ## Run tests and open HTML coverage report
	pytest --cov-report=html
	open htmlcov/index.html 2>/dev/null || xdg-open htmlcov/index.html

docker-build: ## Build Docker image locally
	docker build -t replaytagger:dev .

docker-up: ## Start with docker-compose (watch mode)
	docker compose up

docker-down: ## Stop docker-compose
	docker compose down

run: ## Process all clips once and exit
	replaytagger run

watch: ## Watch for new clips (runs forever)
	replaytagger watch

youtube-auth: ## Authorize YouTube uploads (opens browser)
	replaytagger youtube-auth

status: ## Show state DB statistics
	replaytagger status

clean: ## Remove build artifacts and cache
	rm -rf dist/ build/ *.egg-info .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
