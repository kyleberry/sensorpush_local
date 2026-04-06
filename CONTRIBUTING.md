# Contributing

## Dev environment

This repo includes a devcontainer. Open it in VS Code and select **Reopen in Container** — the container installs all dependencies automatically via `postCreateCommand`.

To set up manually:

```bash
pip install -e .[test] --config-settings editable_mode=compat
```

## Running tests

```bash
# All tests
pytest tests/

# Single file
pytest tests/test_init.py

# Single test
pytest tests/test_init.py::test_function_name

# With coverage
pytest tests/ --cov=custom_components/sensorpush_local --cov-report=term-missing
```

Tests run with `asyncio_mode = "auto"` — all async tests are handled automatically.

## Linting and formatting

Four tools are enforced in CI. Run them locally before pushing:

```bash
black custom_components/ tests/                  # format
isort custom_components/ tests/                  # sort imports
flake8 custom_components/ tests/                 # style + unused imports
pylint custom_components/ tests/                 # static analysis
```

To check without modifying files:

```bash
black --check --target-version py313 custom_components/ tests/
isort --check-only custom_components/ tests/
```

Configuration lives in `pyproject.toml` (`[tool.black]`, `[tool.isort]`) and `setup.cfg` (`[flake8]`, `[pylint.messages_control]`).

## CI

The GitHub Actions workflow (`.github/workflows/tests.yml`) runs on every push and on PRs targeting `main`. It runs tests, then all four lint checks in sequence. All steps must pass before a PR can be merged.
