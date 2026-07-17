# Forgejo Migration Design

**Date:** 2026-07-17
**Status:** Approved

## Goal

This repo's git remote already lives on Forgejo (`git.berry.house`), with a push mirror already configured (using a GitHub PAT stored as the `GH_RELEASE_TOKEN` secret) to sync commits and tags to GitHub on every push — GitHub stays the canonical distribution target because HACS reads releases/tags from GitHub directly. Three things remain:

1. Automate the release process (version bump → tag → GitHub release), since a plain push-mirror only moves git objects — it doesn't create GitHub Release entries.
2. Migrate the existing GitHub Actions CI workflow to Forgejo Actions.
3. Replace Dependabot with Renovate, matching the pattern already proven in the homelab repo.

## Constraints

- Secrets cannot be created by an agent — any new Forgejo Actions secret is a manual, day-2 step for the user.
- HACS requires GitHub to remain the place releases/tags are visible; nothing in this design changes where HACS looks.
- Mirror sync is push-triggered (near-instant), confirmed by the user — the release workflow can poll GitHub for the tag with a short timeout rather than a long interval-based wait.

---

## Component 1: Release automation — `.forgejo/workflows/release.yml`

**Trigger:** `workflow_dispatch` with a required `version` input (e.g. `1.0.3`, no `v` prefix).

**Jobs:**

1. **`validate`**
   - Checks `version` input matches `^[0-9]+\.[0-9]+\.[0-9]+$`
   - Fails immediately with a clear message if it doesn't

2. **`test`** (needs `validate`)
   - Runs the same full pre-push check CLAUDE.md documents: pytest, black --check, isort --check-only, flake8, pylint (--fail-under=9.5)
   - Reuses the same steps/container as the migrated `ci.yml` (`runs-on: debian-trixie`, `container: image: python:3.13-bookworm`)
   - A release can never ship on top of code that fails this gate

3. **`release`** (needs `test`)
   - Checks out `main` with `fetch-depth: 0` (needed for tag history)
   - Bumps version in three places: `custom_components/sensorpush_local/manifest.json`, `pyproject.toml`, and the version badge in `README.md`
   - Commits as `Release vX.Y.Z`, pushes to `main` on Forgejo (triggers the push mirror)
   - Creates an annotated tag `vX.Y.Z`, pushes the tag (triggers the mirror again)
   - Polls `GET https://api.github.com/repos/kyleberry/sensorpush_local/git/ref/tags/vX.Y.Z` using `GH_RELEASE_TOKEN`, retrying every 5s up to 60s total
   - Fails loudly if the tag never appears on GitHub within that window, with a message pointing at the push-mirror config as the likely culprit
   - Builds a changelog: `git log --pretty=format:"- %s (%h)" <previous-tag>..vX.Y.Z` (previous tag found via `git describe --tags --abbrev=0 HEAD^` before the bump commit)
   - Calls `POST /repos/kyleberry/sensorpush_local/releases` with `GH_RELEASE_TOKEN`, `tag_name: vX.Y.Z`, `name: vX.Y.Z`, and the generated changelog as `body`

**Secrets used:** `GH_RELEASE_TOKEN` (already present) — only for the two GitHub API calls (poll + create release). The version-bump commit and tag push to Forgejo use the workflow's default token, since that's a same-repo push.

**Failure modes handled:**
- Invalid version format → fails at `validate`, before any code changes
- Tests/lint failing → fails at `test`, before any version bump or tag
- Mirror not syncing in time → fails at the poll step with an actionable message, no orphaned GitHub release created
- Tag already exists → the `git tag` step fails naturally; not specially handled beyond that

---

## Component 2: CI migration — `.forgejo/workflows/ci.yml`

Direct port of `.github/workflows/tests.yml`, no behavior changes:
- Same triggers: `push` on all branches, `pull_request` targeting `main`
- Same fork-PR guard: `if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name != github.repository`
- `runs-on: debian-trixie`, `container: image: python:3.13-bookworm`
- Same steps in the same order: install system deps (build-essential, libudev-dev, bluez, git), checkout (same pinned SHA), `pip install -e .[test]`, pytest, black, isort, flake8, pylint
- No `permissions:` block (matches homelab's `ci.yml` — Forgejo doesn't scope tokens via that field; a comment notes this, same as homelab)

**Deleted:**
- `.github/workflows/tests.yml`
- `.github/workflows/dependabot-automerge.yml` — automerge responsibility moves entirely to Renovate's own `automerge` package rules (see Component 3); no separate automerge workflow is needed once Renovate is driving PRs.

---

## Component 3: Dependabot → Renovate

**Deleted:** `.github/dependabot.yml`

**Added: `renovate.json`** (repo root), modeled on the homelab config, trimmed to what this repo actually has (pip via `pyproject.toml` PEP 621 deps, and GitHub/Forgejo Actions):

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "timezone": "America/Chicago",
  "schedule": ["on monday"],
  "dependencyDashboard": true,
  "rebaseWhen": "conflicted",
  "minimumReleaseAge": "3 days",
  "packageRules": [
    {
      "groupName": "github actions",
      "matchManagers": ["github-actions"]
    },
    {
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true
    },
    {
      "matchUpdateTypes": ["major"],
      "automerge": false
    }
  ],
  "assignees": ["kyleberry"]
}
```

Renovate's default `github-actions` manager file matching already covers `.forgejo/workflows/*.yml` (confirmed by the homelab repo's working config), so no `fileMatch` override is needed.

**Added: `.forgejo/workflows/renovate.yml`**, same shape as homelab's:

```yaml
name: Renovate

on:
  schedule:
    - cron: '0 3 * * 1'  # Monday at 03:00
  workflow_dispatch:
  issues:
    types: [edited]
  issue_comment:
    types: [created]
  pull_request:
    types: [closed]

jobs:
  renovate:
    name: Renovate
    runs-on: debian-trixie
    steps:
      - name: Run Renovate
        run: renovate
        env:
          RENOVATE_TOKEN: ${{ secrets.RENOVATE_TOKEN }}
          RENOVATE_PLATFORM: forgejo
          RENOVATE_ENDPOINT: ${{ github.server_url }}
          RENOVATE_REPOSITORIES: ${{ github.repository }}
          GITHUB_COM_TOKEN: ${{ secrets.GITHUBCOM_TOKEN }}
          LOG_LEVEL: info
```

**Manual prerequisite (user, day-2, not automatable by an agent):** `RENOVATE_TOKEN` and `GITHUBCOM_TOKEN` are already available as user-level Forgejo Actions secrets (confirmed working in another repo) — no per-repo secret setup needed for those. Before Renovate's automerge actually takes effect here, the user still needs to (day-2, in the repo settings UI): configure branch protection on `main` with the CI job(s) as required status checks, and enable auto-merge on the repository.

---

## Documentation updates

- **`CLAUDE.md`** — "Version bumping" section rewritten to describe triggering `.forgejo/workflows/release.yml` with a version input instead of manually editing both files and pushing tags.
- **`CONTRIBUTING.md`** — update any references to the GitHub Actions CI workflow / Dependabot to point at the Forgejo equivalents.

## Out of scope

- Changing where the repo is hosted primarily (already done — Forgejo is primary, GitHub is a mirror).
- Adding a GitHub Actions workflow on the GitHub side — GitHub is now a passive mirror target only, no Actions run there.
- HACS-side changes — HACS reads tags/releases directly from GitHub via API; nothing about how HACS discovers releases changes.
