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

The Forgejo Actions workflow (`.forgejo/workflows/ci.yml`) runs on PRs targeting `main`, not on branch pushes, so open a PR to get CI. It runs tests, then all four lint checks in sequence. Branch protection requires `CI / * (pull_request)`, covering `CI / test (pull_request)`, `CI / Secret scan (pull_request)` and `CI / Workflow lint (pull_request)`. All three must pass before a PR can be merged.

The devcontainer's Dockerfile also builds the CI image (`.forgejo/workflows/ci-image.yml`, published to `registry.berry.house/sensorpush-local/ci`), so CI runs with the same Python and system packages as the devcontainer.

The CI image workflow uses ci-tools v1.5.0's `image-build`, `image-publish`
and `image-cleanup` actions (CI-15). This repo keeps its smoke script, full
in-image test suite, credential loading/login and publish gates. Builds use
`--pull`; manual runs force a rebuild. PRs use unique local tags and never
publish. Cleanup runs after failures as well as successful runs.

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

Renovate majors and every manually merged Home Assistant ecosystem update receive one advisory comment through `ci-tools/renovate-major-summary` (SENS-14, SENS-16). The workflow keeps its existing filename, `renovate-major-summary.yml`, with the display name "Renovate update research". It runs only for same-repo `renovate/` branches carrying `major` or `ha-ecosystem`; both repository labels must exist for Renovate to apply them. The action rechecks live labels before calling the model. Python version updates receive the ecosystem label; CI-image Python digest/pin updates do not.

Ordinary majors keep `.forgejo/renovate-major-summary-prompt.md` and its changelog/usage summary. HA ecosystem PRs, including minor/patch updates and majors carrying both labels, select `.forgejo/renovate-ha-research-prompt.md` once. Research adds release-specific and current PyPI metadata/descriptions, project-page deprecation notices, bounded migration pointers and targeted upstream issues/PRs, alongside local declared/locked constraints and integration/test context. All upstream content is untrusted evidence; the comment distinguishes runtime changes from test/CI compatibility, cites sources and reports unavailable or inconclusive evidence. It cannot replace the resolver, tests or a real Bluetooth audit.

The existing comment is updated in place and unchanged inputs skip research and the model. A seven-day cache bucket permits an upstream-evidence refresh on a later PR event; there is no scheduled polling. Research has request/time/text caps and uses no upstream credentials. Unavailable sources, PyPI browser challenges and unsupported discussions are explicit gaps. Reviews remain advisory and ecosystem PRs continue to require manual merge. Both modes use the same vault key as the ordinary PR reviewer, which still excludes Renovate branches.

## Secret scanning

CI-14 uses the shared ci-tools Gitleaks action to scan the full checked-out
Git history, including secrets deleted before HEAD. Checkout must use
`fetch-depth: 0`; findings fail the Secret scan check with redacted output.
Repository exceptions belong in `.gitleaks.toml` or `.gitleaksignore` and
must be narrow and documented. The initial full-history baseline found no
findings requiring new exceptions.

The action uses this repository's Gitleaks pre-commit release pin when present,
otherwise its own Renovate-maintained pin. Local staged hooks remain enabled
where configured. The shared action owns installation, checksum verification,
caching and scanning.

## Workflow and shell lint

CI's Workflow lint job uses ci-tools/workflow-lint to check every Forgejo
workflow, including inline shell blocks with ShellCheck. Version pins live in
`.pre-commit-config.yaml`; Forgejo exceptions stay in `.forgejo/actionlint.yaml`.
CI checks the standalone scripts listed in the workflow’s `shell-files`
input. Add new shell scripts to that list; the local ShellCheck hook discovers
all tracked shell scripts automatically.

For local hooks, install `pre-commit` and the pinned `shellcheck-py` release
from `.pre-commit-config.yaml` into a repo venv, put its `bin` directory on
PATH, then run `pre-commit run --all-files`. The actionlint hook explicitly
requires ShellCheck on PATH so inline checks cannot be silently skipped.
