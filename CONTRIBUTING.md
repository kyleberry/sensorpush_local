# Contributing

## Dev environment

This repo includes a devcontainer. Open it in VS Code and select **Reopen in Container** — the container installs all dependencies automatically via `postCreateCommand`.

To set up manually, install [uv](https://docs.astral.sh/uv/getting-started/installation/) then:

```bash
uv sync --extra test
```

This creates `.venv` and installs the exact versions locked in `uv.lock`. Prefix commands with `uv run`, or activate the venv (`source .venv/bin/activate`) to drop the prefix.

## Running tests

```bash
# All tests
uv run pytest tests/

# Single file
uv run pytest tests/test_init.py

# Single test
uv run pytest tests/test_init.py::test_function_name

# With coverage
uv run pytest tests/ --cov=custom_components/sensorpush_local --cov-report=term-missing
```

Tests run with `asyncio_mode = "auto"` — all async tests are handled automatically.

## Linting and formatting

Four tools are enforced in CI. Run them locally before pushing:

```bash
uv run black custom_components/ tests/                  # format
uv run isort custom_components/ tests/                  # sort imports
uv run flake8 custom_components/ tests/                 # style + unused imports
uv run pylint custom_components/ tests/                 # static analysis
```

To check without modifying files:

```bash
uv run black --check --target-version py313 custom_components/ tests/
uv run isort --check-only custom_components/ tests/
```

## Managing dependencies

Dependencies are pinned to exact versions in `pyproject.toml` and locked in `uv.lock`. After changing a version, run `uv lock` and commit the updated `uv.lock` alongside it — CI runs `uv sync --locked`, which fails if the two files disagree.

Configuration lives in `pyproject.toml` (`[tool.black]`, `[tool.isort]`) and `setup.cfg` (`[flake8]`, `[pylint.messages_control]`).

## CI

The Forgejo Actions workflow (`.forgejo/workflows/ci.yml`) runs on every push and on PRs targeting `main`. It runs tests, then all four lint checks in sequence. All steps must pass before a PR can be merged.

Dependency updates are managed by Renovate (`renovate.json`, `.forgejo/workflows/renovate.yml`) rather than Dependabot.
