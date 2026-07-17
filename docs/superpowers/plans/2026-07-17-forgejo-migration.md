# Forgejo Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate CI off GitHub Actions onto Forgejo Actions, replace Dependabot with Renovate, and add a Forgejo workflow that automates the GitHub release process (version bump → tag → GitHub release), working with the push mirror that's already syncing commits/tags from Forgejo to GitHub.

**Architecture:** Three independent Forgejo Actions workflow files under `.forgejo/workflows/`, one Renovate config file at the repo root, and doc updates. No application code changes — this is entirely CI/CD tooling. The existing `.github/workflows/*.yml` and `.github/dependabot.yml` are deleted as each piece is replaced.

**Tech Stack:** Forgejo Actions (GitHub Actions-compatible YAML), Renovate, bash, curl + GitHub REST API, jq.

## Global Constraints

- `runs-on: debian-trixie` for every job (matches the homelab repo's shared act-runner).
- No `permissions:` block in any workflow — Forgejo doesn't scope tokens via that field (matches homelab's `ci.yml` convention; include the same explanatory comment).
- GitHub API calls use the `GH_RELEASE_TOKEN` secret (already present in this repo).
- Tag convention stays `vX.Y.Z` (from CLAUDE.md).
- Version must stay in sync across `custom_components/sensorpush_local/manifest.json`, `pyproject.toml`, and the README badge.
- This repo's `.venv` has PyYAML available (`.venv/bin/python -c "import yaml"`) — use it for YAML syntax verification steps below. No `yamllint` or `shellcheck` binary is installed in this environment.

---

### Task 1: Migrate CI workflow to Forgejo Actions

**Files:**
- Create: `.forgejo/workflows/ci.yml`
- Delete: `.github/workflows/tests.yml`

**Interfaces:**
- Produces: a Forgejo Actions workflow named `CI` that Task 3's release workflow's `test` job steps are modeled on (same container image, same step order).

- [ ] **Step 1: Create `.forgejo/workflows/ci.yml`**

```yaml
name: CI

# No `permissions:` block — Forgejo doesn't scope FORGEJO_TOKEN/GITHUB_TOKEN
# via this field (GitHub-compat syntax only, a no-op here).

on:
  push:
    branches: ["**"]
  pull_request:
    branches: ["main"]

jobs:
  test:
    if: github.event_name == 'push' || github.event.pull_request.head.repo.full_name != github.repository
    runs-on: debian-trixie
    container:
      image: python:3.13-bookworm

    steps:
      - name: Install System Dependencies
        run: |
          apt-get update
          apt-get install -y build-essential libudev-dev bluez git

      - name: Checkout Code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6

      - name: Install Python Dependencies
        run: |
          python -m pip install --upgrade pip setuptools wheel
          pip install -e .[test] --config-settings editable_mode=compat

      - name: Run Tests
        run: |
          pytest tests/

      - name: Check formatting (black)
        run: |
          black --check --target-version py313 custom_components/ tests/

      - name: Check import order (isort)
        run: |
          isort --check-only custom_components/ tests/

      - name: Lint (flake8)
        run: |
          flake8 custom_components/ tests/

      - name: Lint (pylint)
        run: |
          pylint custom_components/ tests/ --fail-under=9.5
```

- [ ] **Step 2: Verify YAML syntax**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.forgejo/workflows/ci.yml'))" && echo VALID`
Expected: `VALID`

- [ ] **Step 3: Diff against the original to confirm no accidental behavior change**

Run: `diff <(tail -n +1 .github/workflows/tests.yml) <(tail -n +1 .forgejo/workflows/ci.yml)`
Expected: only the header comment block and the (unused) `name: Python Tests` → `name: CI` line differ — no step content, trigger, or condition differences. If anything else differs, fix `.forgejo/workflows/ci.yml` to match before proceeding.

- [ ] **Step 4: Delete the old GitHub Actions workflow**

```bash
git rm .github/workflows/tests.yml
```

- [ ] **Step 5: Commit**

```bash
git add .forgejo/workflows/ci.yml
git commit -m "Migrate CI workflow from GitHub Actions to Forgejo Actions"
```

---

### Task 2: Replace Dependabot with Renovate

**Files:**
- Create: `renovate.json`
- Create: `.forgejo/workflows/renovate.yml`
- Delete: `.github/dependabot.yml`
- Delete: `.github/workflows/dependabot-automerge.yml`

**Interfaces:**
- Consumes: none from other tasks.
- Produces: nothing consumed by other tasks — independent of Task 1 and Task 3.

- [ ] **Step 1: Create `renovate.json`**

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

- [ ] **Step 2: Verify JSON syntax**

Run: `jq empty renovate.json && echo VALID`
Expected: `VALID`

- [ ] **Step 3: Create `.forgejo/workflows/renovate.yml`**

```yaml
name: Renovate

on:
  schedule:
    - cron: '0 3 * * 1'  # Monday at 03:00
  workflow_dispatch:
  # Dependency dashboard checkbox interactions and PR comment commands.
  issues:
    types: [edited]
  issue_comment:
    types: [created]
  # Update dashboard and process follow-on work when a PR is merged or closed.
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
          # Needed to look up GitHub Actions releases without hitting API rate limits.
          GITHUB_COM_TOKEN: ${{ secrets.GITHUBCOM_TOKEN }}
          LOG_LEVEL: info
```

- [ ] **Step 4: Verify YAML syntax**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.forgejo/workflows/renovate.yml'))" && echo VALID`
Expected: `VALID`

- [ ] **Step 5: Delete Dependabot config and automerge workflow**

```bash
git rm .github/dependabot.yml .github/workflows/dependabot-automerge.yml
```

- [ ] **Step 6: Commit**

```bash
git add renovate.json .forgejo/workflows/renovate.yml
git commit -m "Replace Dependabot with Renovate"
```

---

### Task 3: Release automation workflow

**Files:**
- Create: `.forgejo/workflows/release.yml`

**Interfaces:**
- Consumes: the same container image and step sequence as `.forgejo/workflows/ci.yml` (Task 1) for its `test` job.
- Produces: nothing consumed by other tasks.

This task has no unit tests to write (it's a CI workflow, not application code), so verification is: (a) dry-run the exact shell logic against real repo files/tags before embedding it in YAML, and (b) syntax-check the final YAML and its embedded scripts.

- [ ] **Step 1: Dry-run the version-bump `sed` commands against real files**

```bash
mkdir -p /tmp/release-dryrun
cp custom_components/sensorpush_local/manifest.json pyproject.toml README.md /tmp/release-dryrun/
cd /tmp/release-dryrun
VERSION=9.9.9
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$VERSION\"/" manifest.json
sed -i "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" pyproject.toml
sed -i "s/version-[0-9]*\.[0-9]*\.[0-9]*-blue/version-$VERSION-blue/" README.md
grep '"version"' manifest.json
grep '^version = ' pyproject.toml
grep 'img.shields.io/badge/version' README.md
cd -
rm -rf /tmp/release-dryrun
```

Expected output:
```
  "version": "9.9.9",
version = "9.9.9"
![Version](https://img.shields.io/badge/version-9.9.9-blue.svg)
```

If any line didn't change, fix the `sed` pattern against the actual current file content (check with `grep` on the real files) before continuing.

- [ ] **Step 2: Dry-run the changelog generation against real tags**

```bash
git describe --tags --abbrev=0 v1.0.2^
git log --pretty=format:"- %s (%h)" v1.0.1..v1.0.2
```

Expected: first command prints `v1.0.1`; second prints a bullet list of commit subjects between those two tags (already confirmed working — 4 lines ending in `(a64f9fd)`).

- [ ] **Step 3: Create `.forgejo/workflows/release.yml`**

```yaml
name: Release

# No `permissions:` block — see .forgejo/workflows/ci.yml.
#
# Requires this repo's Actions "Workflow permissions" to be set to
# "Read and write" (repo Settings > Actions > General) so the default
# checkout token can push the version-bump commit and tag back to main.
# GH_RELEASE_TOKEN is only used for the two GitHub API calls below —
# it never touches the Forgejo git push.

on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Version to release (e.g. 1.0.3, no v prefix)'
        required: true
        type: string

jobs:
  validate:
    name: Validate version input
    runs-on: debian-trixie
    steps:
      - name: Check version format
        env:
          VERSION: ${{ inputs.version }}
        run: |
          if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "::error::Version '$VERSION' is not in X.Y.Z format"
            exit 1
          fi

  test:
    name: Test
    needs: validate
    runs-on: debian-trixie
    container:
      image: python:3.13-bookworm

    steps:
      - name: Install System Dependencies
        run: |
          apt-get update
          apt-get install -y build-essential libudev-dev bluez git

      - name: Checkout Code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6

      - name: Install Python Dependencies
        run: |
          python -m pip install --upgrade pip setuptools wheel
          pip install -e .[test] --config-settings editable_mode=compat

      - name: Run Tests
        run: |
          pytest tests/

      - name: Check formatting (black)
        run: |
          black --check --target-version py313 custom_components/ tests/

      - name: Check import order (isort)
        run: |
          isort --check-only custom_components/ tests/

      - name: Lint (flake8)
        run: |
          flake8 custom_components/ tests/

      - name: Lint (pylint)
        run: |
          pylint custom_components/ tests/ --fail-under=9.5

  release:
    name: Release
    needs: test
    runs-on: debian-trixie
    steps:
      - name: Checkout Code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6
        with:
          fetch-depth: 0

      - name: Bump version in manifest.json, pyproject.toml, README.md
        env:
          VERSION: ${{ inputs.version }}
        run: |
          sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$VERSION\"/" custom_components/sensorpush_local/manifest.json
          sed -i "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" pyproject.toml
          sed -i "s/version-[0-9]*\.[0-9]*\.[0-9]*-blue/version-$VERSION-blue/" README.md

      - name: Commit version bump
        env:
          VERSION: ${{ inputs.version }}
        run: |
          git config user.name "forgejo-actions"
          git config user.email "actions@git.berry.house"
          git add custom_components/sensorpush_local/manifest.json pyproject.toml README.md
          git commit -m "Release v$VERSION"
          git push origin HEAD:main

      - name: Tag release
        env:
          VERSION: ${{ inputs.version }}
        run: |
          git tag -a "v$VERSION" -m "Release v$VERSION"
          git push origin "v$VERSION"

      - name: Wait for push mirror to sync tag to GitHub
        env:
          VERSION: ${{ inputs.version }}
          GH_TOKEN: ${{ secrets.GH_RELEASE_TOKEN }}
        run: |
          for i in $(seq 1 12); do
            status=$(curl -s -o /dev/null -w "%{http_code}" \
              -H "Authorization: Bearer $GH_TOKEN" \
              "https://api.github.com/repos/kyleberry/sensorpush_local/git/ref/tags/v$VERSION")
            if [ "$status" = "200" ]; then
              echo "Tag v$VERSION found on GitHub"
              exit 0
            fi
            echo "Tag not on GitHub yet (attempt $i/12), waiting 5s..."
            sleep 5
          done
          echo "::error::Tag v$VERSION never appeared on GitHub after 60s — check the push mirror config in repo settings"
          exit 1

      - name: Generate changelog
        id: changelog
        env:
          VERSION: ${{ inputs.version }}
        run: |
          PREVIOUS_TAG=$(git describe --tags --abbrev=0 "v$VERSION^" 2>/dev/null || echo "")
          if [ -n "$PREVIOUS_TAG" ]; then
            LOG=$(git log --pretty=format:"- %s (%h)" "$PREVIOUS_TAG..v$VERSION")
          else
            LOG=$(git log --pretty=format:"- %s (%h)" "v$VERSION")
          fi
          {
            echo "changelog<<CHANGELOG_EOF"
            echo "$LOG"
            echo "CHANGELOG_EOF"
          } >> "$GITHUB_OUTPUT"

      - name: Create GitHub release
        env:
          VERSION: ${{ inputs.version }}
          CHANGELOG: ${{ steps.changelog.outputs.changelog }}
          GH_TOKEN: ${{ secrets.GH_RELEASE_TOKEN }}
        run: |
          jq -n \
            --arg tag "v$VERSION" \
            --arg name "v$VERSION" \
            --arg body "$CHANGELOG" \
            '{tag_name: $tag, name: $name, body: $body}' > /tmp/release_payload.json

          http_status=$(curl -s -o /tmp/release_response.json -w "%{http_code}" \
            -X POST \
            -H "Authorization: Bearer $GH_TOKEN" \
            -H "Accept: application/vnd.github+json" \
            "https://api.github.com/repos/kyleberry/sensorpush_local/releases" \
            -d @/tmp/release_payload.json)

          if [ "$http_status" != "201" ]; then
            echo "::error::GitHub release creation failed with status $http_status"
            cat /tmp/release_response.json
            exit 1
          fi

          echo "Release created: $(jq -r '.html_url' /tmp/release_response.json)"
```

- [ ] **Step 4: Verify YAML syntax**

Run: `.venv/bin/python -c "import yaml; yaml.safe_load(open('.forgejo/workflows/release.yml'))" && echo VALID`
Expected: `VALID`

- [ ] **Step 5: Syntax-check each embedded shell script**

For each `run: |` block in the `release` job (bump, commit, tag, wait, changelog, create-release), extract it to a temp file and run `bash -n` to catch unbalanced quotes/heredocs before this ever runs on a runner:

```bash
mkdir -p /tmp/release-shellcheck
cat > /tmp/release-shellcheck/bump.sh <<'SCRIPT_EOF'
VERSION=1.2.3
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$VERSION\"/" custom_components/sensorpush_local/manifest.json
sed -i "s/^version = \"[^\"]*\"/version = \"$VERSION\"/" pyproject.toml
sed -i "s/version-[0-9]*\.[0-9]*\.[0-9]*-blue/version-$VERSION-blue/" README.md
SCRIPT_EOF
bash -n /tmp/release-shellcheck/bump.sh && echo "bump.sh OK"

cat > /tmp/release-shellcheck/wait.sh <<'SCRIPT_EOF'
VERSION=1.2.3
GH_TOKEN=dummy
for i in $(seq 1 12); do
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $GH_TOKEN" \
    "https://api.github.com/repos/kyleberry/sensorpush_local/git/ref/tags/v$VERSION")
  if [ "$status" = "200" ]; then
    echo "Tag v$VERSION found on GitHub"
    exit 0
  fi
  echo "Tag not on GitHub yet (attempt $i/12), waiting 5s..."
  sleep 5
done
echo "::error::Tag v$VERSION never appeared on GitHub after 60s — check the push mirror config in repo settings"
exit 1
SCRIPT_EOF
bash -n /tmp/release-shellcheck/wait.sh && echo "wait.sh OK"

cat > /tmp/release-shellcheck/changelog.sh <<'SCRIPT_EOF'
VERSION=1.2.3
PREVIOUS_TAG=$(git describe --tags --abbrev=0 "v$VERSION^" 2>/dev/null || echo "")
if [ -n "$PREVIOUS_TAG" ]; then
  LOG=$(git log --pretty=format:"- %s (%h)" "$PREVIOUS_TAG..v$VERSION")
else
  LOG=$(git log --pretty=format:"- %s (%h)" "v$VERSION")
fi
{
  echo "changelog<<CHANGELOG_EOF"
  echo "$LOG"
  echo "CHANGELOG_EOF"
} >> "$GITHUB_OUTPUT"
SCRIPT_EOF
GITHUB_OUTPUT=/tmp/release-shellcheck/out.txt bash -n /tmp/release-shellcheck/changelog.sh && echo "changelog.sh OK"

cat > /tmp/release-shellcheck/create_release.sh <<'SCRIPT_EOF'
VERSION=1.2.3
CHANGELOG="- example commit (abc1234)"
GH_TOKEN=dummy
jq -n \
  --arg tag "v$VERSION" \
  --arg name "v$VERSION" \
  --arg body "$CHANGELOG" \
  '{tag_name: $tag, name: $name, body: $body}' > /tmp/release_payload.json

http_status=$(curl -s -o /tmp/release_response.json -w "%{http_code}" \
  -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/kyleberry/sensorpush_local/releases" \
  -d @/tmp/release_payload.json)

if [ "$http_status" != "201" ]; then
  echo "::error::GitHub release creation failed with status $http_status"
  cat /tmp/release_response.json
  exit 1
fi

echo "Release created: $(jq -r '.html_url' /tmp/release_response.json)"
SCRIPT_EOF
bash -n /tmp/release-shellcheck/create_release.sh && echo "create_release.sh OK"

rm -rf /tmp/release-shellcheck
```

Expected: `bump.sh OK`, `wait.sh OK`, `changelog.sh OK`, `create_release.sh OK` — all four print, no `bash: ... syntax error` lines.

- [ ] **Step 6: Actually run the `jq` payload construction to confirm it produces valid JSON**

```bash
VERSION=1.2.3
CHANGELOG="- example commit (abc1234)
- another commit (def5678)"
jq -n \
  --arg tag "v$VERSION" \
  --arg name "v$VERSION" \
  --arg body "$CHANGELOG" \
  '{tag_name: $tag, name: $name, body: $body}' | jq empty && echo "PAYLOAD VALID"
```

Expected: `PAYLOAD VALID` (confirms the multi-line changelog string doesn't break JSON construction — this is the main risk in the release-creation step).

- [ ] **Step 7: Commit**

```bash
git add .forgejo/workflows/release.yml
git commit -m "Add Forgejo release automation workflow"
```

---

### Task 4: Update documentation

**Files:**
- Modify: `CLAUDE.md:111-117` (the "## Version bumping" section)
- Modify: `CONTRIBUTING.md:51-53` (the "## CI" section)

**Interfaces:**
- Consumes: nothing (pure doc text, references the workflow names created in Tasks 1 and 3).

- [ ] **Step 1: Replace the "Version bumping" section in `CLAUDE.md`**

Find:
```markdown
## Version bumping

Version is tracked in two files — both must match:
- `custom_components/sensorpush_local/manifest.json`
- `pyproject.toml`

Tags follow `vX.Y.Z` convention. Create and push separately: `git tag vX.Y.Z && git push origin vX.Y.Z`.
```

Replace with:
```markdown
## Version bumping

Releases are automated via the `.forgejo/workflows/release.yml` workflow. Trigger it manually (`workflow_dispatch`) with a `version` input (e.g. `1.0.3`, no `v` prefix). It runs the full test/lint suite, then bumps the version in `custom_components/sensorpush_local/manifest.json`, `pyproject.toml`, and the README badge, commits, tags `vX.Y.Z`, waits for the push mirror to sync the tag to GitHub, and creates the GitHub release with an auto-generated changelog.

Do not bump these files or create tags manually — the workflow is the only supported release path.
```

- [ ] **Step 2: Replace the "CI" section in `CONTRIBUTING.md`**

Find:
```markdown
## CI

The GitHub Actions workflow (`.github/workflows/tests.yml`) runs on every push and on PRs targeting `main`. It runs tests, then all four lint checks in sequence. All steps must pass before a PR can be merged.
```

Replace with:
```markdown
## CI

The Forgejo Actions workflow (`.forgejo/workflows/ci.yml`) runs on every push and on PRs targeting `main`. It runs tests, then all four lint checks in sequence. All steps must pass before a PR can be merged.

Dependency updates are managed by Renovate (`renovate.json`, `.forgejo/workflows/renovate.yml`) rather than Dependabot.
```

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -rn "\.github/workflows/tests\.yml\|dependabot" CLAUDE.md CONTRIBUTING.md`
Expected: no output (empty — confirms all references were updated).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md CONTRIBUTING.md
git commit -m "Update docs for Forgejo CI/release/Renovate migration"
```

---

## Manual follow-up (not part of this plan, day-2 in repo settings UI)

These cannot be done by an agent and are not implementation tasks — listed here so nothing gets lost:

1. Confirm this repo's Actions "Workflow permissions" is set to "Read and write" (Settings → Actions → General) so `release.yml` can push the version-bump commit/tag.
2. Configure branch protection on `main` with the CI job as a required status check, and enable auto-merge on the repository, so Renovate's `automerge: true` package rules actually take effect.
   - **Interaction to check:** `release.yml`'s `release` job does `git push origin HEAD:main` directly. If branch protection blocks direct pushes, confirm it either exempts the token/actor the workflow pushes as, or the release push will be rejected — leaving a local commit that never reaches `main` (a half-completed release).
3. Trigger `.forgejo/workflows/release.yml` once for a real (or throwaway) version bump to confirm the end-to-end flow works against the live push mirror and GitHub API — nothing in this plan exercises the workflow on an actual runner. This run also validates that the act-runner version in use populates `${{ inputs.version }}` for `workflow_dispatch` (the modern shorthand used throughout this workflow) rather than requiring the older `${{ github.event.inputs.version }}` form.
