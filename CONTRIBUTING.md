# Contributing

Thanks for taking a look. This is a small integration with a big test suite: most of what it does happens over Bluetooth at 3am, so the tests are how changes get checked before anyone's freezer sensor finds out.

## Where things live

Development happens on a self-hosted Forgejo instance. [GitHub](https://github.com/kyleberry/sensorpush_local) and [Codeberg](https://codeberg.org/kyleberry/sensorpush_local) are push mirrors of it, and releases are published on all three. Bug reports and feature requests go to [GitHub issues](https://github.com/kyleberry/sensorpush_local/issues).

Pull requests are welcome on GitHub or Codeberg. Development happens on the Forgejo instance, so I'll bring your PR over there to run CI and merge it, and your commits keep your name. Expect a short delay between opening it and seeing it merged.

`CLAUDE.md` is the detailed maintainer reference: architecture, release process, secrets and the reasons behind the dependency rules. This file covers what you need day to day.

## Dev environment

The repo includes a devcontainer. Open it in VS Code and choose **Reopen in Container**; `postCreateCommand` installs everything. The same Dockerfile builds the CI image, so the devcontainer and CI run the same Python and system packages.

To set up without it, install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
uv sync --extra test
```

This creates `.venv` with the exact versions in `uv.lock`, fetching Python 3.14 if you don't have it. Prefix commands with `uv run`, or activate the venv (`source .venv/bin/activate`) to drop the prefix.

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

Tests run with `asyncio_mode = "auto"`, so async tests need no decorator. The test harness is `pytest-homeassistant`, Home Assistant's own package, pinned to the same version as `homeassistant`.

A couple of ERROR lines from `habluetooth.scanner` and `homeassistant.config_entries` show up in every run. They come from the test harness and are harmless; `CLAUDE.md` lists them.

## Linting and formatting

CI enforces four tools. To format and lint in place:

```bash
uv run black custom_components/ tests/ scripts/    # format
uv run isort custom_components/ tests/ scripts/    # sort imports
uv run flake8 custom_components/ tests/ scripts/   # style + unused imports
uv run pylint custom_components/ tests/ scripts/   # static analysis (threshold 9.5/10)
```

The full check CI runs, as one command to use before pushing:

```bash
uv run pytest tests/ && uv run black --check --target-version py313 custom_components/ tests/ scripts/ && uv run isort --check-only custom_components/ tests/ scripts/ && uv run flake8 custom_components/ tests/ scripts/ && uv run pylint custom_components/ tests/ scripts/
```

Configuration lives in `pyproject.toml` (`[tool.black]`, `[tool.isort]`) and `setup.cfg` (`[flake8]`, `[pylint.messages_control]`).

### pre-commit hooks

`.pre-commit-config.yaml` runs ShellCheck and actionlint over shell scripts and Forgejo workflows. To use it, install `pre-commit` and the pinned `shellcheck-py` release from `.pre-commit-config.yaml` into a venv, put that venv's `bin` directory on `PATH`, then run `pre-commit run --all-files`. The actionlint hook requires ShellCheck on `PATH`, so inline shell checks can't be skipped by accident.

## Managing dependencies

Dependencies are locked in `uv.lock`, which is committed. Most are pinned to exact versions in `pyproject.toml`. The exceptions are packages that follow Home Assistant (`bleak-retry-connector`, `habluetooth`, `aioesphomeapi` and friends) and `pytest-asyncio`/`pytest-cov`. They're left unpinned on purpose, and the lock records their versions. Don't pin them; `CLAUDE.md` explains why.

After changing a version, run `uv lock` and commit `uv.lock` with it. CI runs `uv sync --locked`, which fails if the two files disagree.

Renovate keeps dependencies current (see below), so hand edits are rare.

## CI

CI runs on Forgejo Actions. `.forgejo/workflows/ci.yml` runs on pull requests to `main`, not on branch pushes, so open a PR to get CI. It has three jobs, and branch protection requires all of them (`CI / * (pull_request)`):

* **test:** the test suite, then black, isort, flake8 and pylint.
* **Secret scan:** the shared ci-tools Gitleaks action scans the full Git history, including secrets deleted before HEAD, so the checkout uses `fetch-depth: 0`. Findings fail the check with redacted output. Exceptions belong in `.gitleaks.toml` or `.gitleaksignore`, kept narrow and documented. The action uses this repo's Gitleaks pre-commit pin when there is one, otherwise its own.
* **Workflow lint:** the shared ci-tools `workflow-lint` action checks every Forgejo workflow, including inline shell blocks with ShellCheck. Version pins live in `.pre-commit-config.yaml`, and Forgejo-specific exceptions in `.forgejo/actionlint.yaml`. Standalone shell scripts are checked only if they're listed in the job's `shell-files` input, so add new scripts there. The local ShellCheck hook finds them on its own.

### CI image

`.forgejo/workflows/ci-image.yml` builds `.devcontainer/Dockerfile` into the CI image, `registry.berry.house/sensorpush-local/ci`, using ci-tools' `image-build`, `image-publish` and `image-cleanup` actions. Each build runs `.devcontainer/smoke-test.sh` and the full test suite inside the image before anything is published. Builds use `--pull`, and a manual run forces a rebuild. PRs that touch the image build it under a unique local tag and never publish. Cleanup runs whether the build passed or failed.

### Releases

Releases are cut by the **Release** workflow (`.forgejo/workflows/release.yml`), run by hand with a version number. It bumps the version, opens a release PR, and once that merges, tags it and publishes release notes on Forgejo, GitHub and Codeberg. Don't bump versions or push tags by hand. `CLAUDE.md` has the details.

## Dependency updates (Renovate)

Renovate (`renovate.json`, `.forgejo/workflows/renovate.yml`) runs daily at 12:00 UTC. The config extends `local>kyleberry/ci-tools//renovate/base` from ci-tools' main branch, which sets the shared policy: five concurrent PRs, a three-day release age, rebasing only on conflicts, squash automerge for minor and patch updates, and majors on Sundays.

On top of that, this repo's `renovate.json` adds:

* **Home Assistant ecosystem** (`homeassistant`, `pytest-homeassistant` and Python version bumps): grouped together and never automerged. Someone reviews and merges these by hand.
* **Lock file maintenance:** Mondays, automerged.
* **CI image** (the Dockerfile's base image digest, Node.js and uv): grouped and automerged, since `ci-image.yml` only publishes an image that passes its tests.
* **ci-tools actions:** their own group, with no release-age or Sunday delay. Minor and patch updates still need CI before automerge, and majors need review.

## AI reviews

Two advisory, model-written comments help with review. Neither gates merging, and if the model or API fails they leave a "review unavailable" note instead.

**PR review** (`.forgejo/workflows/ai-review.yml`, the shared `ci-tools/ai-review` action, SENS-6). Each PR gets one comment, updated on later pushes; a rebase that doesn't change the diff skips the model call. GPT 6.1 Sol reviews by default, and Claude Sonnet reviews PRs with a GPT co-author trailer. Renovate, release, WIP and fork PRs are skipped. The repo-specific prompt is `.forgejo/ai-review-prompt.md`, and the model also sees `CLAUDE.md` and `CONTRIBUTING.md`.

**Renovate update research** (`.forgejo/workflows/renovate-major-summary.yml`, the shared `ci-tools/renovate-major-summary` action, SENS-14 and SENS-16). It comments once on same-repo `renovate/` branches labeled `major` or `ha-ecosystem`. Both labels must exist in the repo for Renovate to apply them, and the action rechecks the live labels before calling the model. Python version updates get the `ha-ecosystem` label; CI-image Python digest and pin updates don't.

* Ordinary majors use `.forgejo/renovate-major-summary-prompt.md` for a changelog and usage summary.
* Home Assistant ecosystem PRs (any update type, including majors with both labels) use `.forgejo/renovate-ha-research-prompt.md`. The research gathers release notes, current PyPI metadata, deprecation notices, migration pointers and relevant upstream issues and PRs, alongside the local declared and locked constraints and how the integration and tests use the package. Upstream content is treated as untrusted evidence. The comment separates runtime changes from test and CI compatibility, cites sources, and says when evidence was unavailable or inconclusive. It doesn't replace the resolver, the tests, or a real Bluetooth audit.

The comment is updated in place, and unchanged inputs skip both the research and the model. Upstream evidence can refresh on a later PR event once a seven-day cache window passes; nothing polls on a schedule. Research is capped by request count, time and text size, and uses no upstream credentials.

Both reviews use the `OPENROUTER_API_KEY` Forgejo secret, which homelab's `terraform/openrouter.tf` creates and writes (HOME-433). `CLAUDE.md` says how to rotate it.
