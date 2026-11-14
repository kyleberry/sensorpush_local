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
uv run black custom_components/ tests/ scripts/                  # format
uv run isort custom_components/ tests/ scripts/                  # sort imports
uv run flake8 custom_components/ tests/ scripts/                 # style + unused imports
uv run pylint custom_components/ tests/ scripts/                 # static analysis
```

To check without modifying files:

```bash
uv run black --check --target-version py313 custom_components/ tests/ scripts/
uv run isort --check-only custom_components/ tests/ scripts/
```

## Managing dependencies

Dependencies are pinned to exact versions in `pyproject.toml` and locked in `uv.lock`. After changing a version, run `uv lock` and commit the updated `uv.lock` alongside it — CI runs `uv sync --locked`, which fails if the two files disagree.

Configuration lives in `pyproject.toml` (`[tool.black]`, `[tool.isort]`) and `setup.cfg` (`[flake8]`, `[pylint.messages_control]`).

## CI

The Forgejo Actions workflow (`.forgejo/workflows/ci.yml`) runs on PRs targeting `main`, not on branch pushes, so open a PR to get CI. It runs tests, then all four lint checks in sequence. Its `CI / test (pull_request)` job is the required status check: all steps must pass before a PR can be merged.

The devcontainer's Dockerfile also builds the CI image (`.forgejo/workflows/ci-image.yml`, published to `registry.berry.house/sensorpush-local/ci`), so CI runs with the same Python and system packages as the devcontainer.

Dependency updates are managed by Renovate (`renovate.json`, `.forgejo/workflows/renovate.yml`) rather than Dependabot.

The configuration extends `local>kyleberry/ci-tools//renovate/base` from
ci-tools' main branch: five concurrent PRs, a three-day release age,
conflict-only rebasing, squash automerge for minor/patch updates and Sunday
majors. Renovate runs daily at 12:00 UTC. Minor and patch updates can open
throughout the week; the Home Assistant ecosystem group still requires manual
review, and lock file maintenance stays on Monday. Repository-specific
compatibility and Docker rules remain in `renovate.json`. Internal ci-tools
action updates use a separate group with no release-age or Sunday delay;
minor/patch updates still need CI before automerge, and majors require manual
review.

PRs also receive an advisory AI review through the shared `ci-tools/ai-review` action (SENS-6). It posts one comment and updates it on later pushes; rebases with an unchanged PR diff skip the model call. GPT 6.1 Sol reviews by default, with Claude Sonnet used for PRs carrying a GPT co-author trailer. Reviews never gate merging, and model/API failures leave a “review unavailable” note. Renovate, release, WIP and fork PRs are skipped. The repo-specific prompt is `.forgejo/ai-review-prompt.md`; the bundle includes CLAUDE.md and CONTRIBUTING.md. The key comes from the Sensorpush-Local 1Password vault.

Renovate major-update PRs receive a separate advisory summary through `ci-tools/renovate-major-summary` (SENS-14). The `major` repository label was created as part of SENS-14 and must exist for Renovate to apply it. Renovate adds that label; the workflow runs only for same-repo `renovate/` branches with that label. It reads the PR release notes, fetches supported upstream changelogs, and maps breaking changes to visible package usages. One comment is updated in place, and failures do not gate merging. The prompt is `.forgejo/renovate-major-summary-prompt.md`; it uses the same vault key as the ordinary PR reviewer.
