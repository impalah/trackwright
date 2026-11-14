# Trackwright: common project tasks. Everything runs through uv (never pip, venv, pipx...).
# Usage: make <target>   (make help lists them)

.DEFAULT_GOAL := help
.PHONY: help sync lint format format-check typecheck test test-cov test-node test-integration \
	test-integration-write check build dist-check publish-test publish clean version doctor ping \
	bridge bridge-status bridge-stop serve-sim script-status script-install script-install-apply setup

UV ?= uv
TEST_TRACK ?= POC-TEST

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  \033[36m%-24s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ------------------------------------------------------------------ environment
sync: ## Create or update the environment (.venv) from uv.lock
	$(UV) sync

# ------------------------------------------------------------------ quality
lint: ## Lint with ruff
	$(UV) run ruff check src tests

format: ## Format the code with ruff (and apply safe lint fixes)
	$(UV) run ruff check --fix src tests
	$(UV) run ruff format src tests

format-check: ## Check the formatting without changing files
	$(UV) run ruff format --check src tests

typecheck: ## Type-check with mypy (strict)
	$(UV) run mypy

test: ## Run the tests (integration tests skip themselves)
	$(UV) run pytest

test-cov: ## Run the tests with coverage (fails below 95 %)
	$(UV) run pytest --cov --cov-report=term-missing

test-node: ## Only the Cubase script tests (needs node)
	$(UV) run pytest -m node

test-integration: ## Read-only tests against the real Cubase (bridge running, Cubase open)
	TRACKWRIGHT_INTEGRATION=1 $(UV) run pytest tests/integration -v

test-integration-write: ## Reversible write tests on TEST_TRACK (default POC-TEST); use a disposable project
	TRACKWRIGHT_INTEGRATION=1 TRACKWRIGHT_ALLOW_WRITES=1 TRACKWRIGHT_TEST_TRACK="$(TEST_TRACK)" \
		$(UV) run pytest tests/integration -v

check: lint format-check typecheck test-cov ## Every quality gate (same as scripts/check.sh)

# ------------------------------------------------------------------ packaging
build: ## Build the wheel and the sdist in dist/ (replaces the previous ones)
	rm -rf dist
	$(UV) build

dist-check: ## Validate the distribution metadata (twine check --strict, run with uvx)
	uvx twine check --strict dist/*

publish-test: build dist-check ## Upload to TestPyPI (needs UV_PUBLISH_TOKEN for test.pypi.org)
	$(UV) publish --publish-url https://test.pypi.org/legacy/

publish: build dist-check ## Upload to PyPI (needs UV_PUBLISH_TOKEN); a version can never be uploaded twice
	$(UV) publish

clean: ## Remove build and test artifacts
	rm -rf dist build .coverage .coverage.* htmlcov coverage.xml .pytest_cache .mypy_cache .ruff_cache
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +

# ------------------------------------------------------------------ running
version: ## Print the Trackwright version
	$(UV) run trackwright version

doctor: ## Check the whole chain (read-only)
	$(UV) run trackwright doctor

ping: ## Round trip Python -> Cubase -> Python
	$(UV) run trackwright ping

bridge: ## Run the bridge in the foreground (Ctrl+C to stop); normally serve starts it
	$(UV) run trackwright bridge

bridge-status: ## Show the bridge status
	$(UV) run trackwright bridge-status

bridge-stop: ## Stop the running bridge (for example after upgrading)
	$(UV) run trackwright bridge-stop

serve-sim: ## Run the MCP server on stdio against the built-in Cubase simulator
	$(UV) run trackwright serve --simulate

# ------------------------------------------------------------------ Cubase script and installation
script-status: ## Compare the installed Cubase script with the packaged one
	$(UV) run trackwright script status

script-install: ## Dry run: show where the Cubase script would be installed
	$(UV) run trackwright script install

script-install-apply: ## Install the Cubase script (then restart Cubase)
	$(UV) run trackwright script install --apply

setup: ## Guided installation (asks before every step)
	$(UV) run trackwright setup
