# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Full pre-push check (tests + all linters)
uv run pytest tests/ && uv run black --check --target-version py313 custom_components/ tests/ scripts/ && uv run isort --check-only custom_components/ tests/ scripts/ && uv run flake8 custom_components/ tests/ scripts/ && uv run pylint custom_components/ tests/ scripts/

# Install with test dependencies
uv sync --extra test

# Run all tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_init.py

# Run a single test
uv run pytest tests/test_init.py::test_function_name

# Run with coverage (shows missing lines)
uv run pytest tests/ --cov=custom_components/sensorpush_local --cov-report=term-missing
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contributor workflow.

Tests run with `asyncio_mode = "auto"` — all async tests are automatically handled.

### Expected log noise in tests

The following ERROR lines appear in every test run and are benign — do not chase them:
- `habluetooth.scanner: Failed to force stop scanner: 'NoneType' object has no attribute 'send'` — BLE scanner teardown in the test harness
- `homeassistant.config_entries: An entry with the id mock_entry_id already exists` — fixture reuse across tests that share an entry ID

`tests/conftest.py`'s `expected_lingering_timers` fixture tolerates `BaseHaScanner`'s recurring expire-devices timer not always being cancelled by the harness's `enable_bluetooth` fixture across homeassistant/habluetooth version combinations — see the fixture's docstring for the upstream issue. Not observed as of `homeassistant==2026.11.1` with `pytest-homeassistant`; kept defensively.

## Architecture

This is a Home Assistant custom integration that provides 100% local Bluetooth monitoring for SensorPush environmental sensors via Bluetooth proxies.

### Core Components

**`custom_components/sensorpush_local/__init__.py`** — `SensorPushCoordinator` (extends `DataUpdateCoordinator`) is the heart of the integration. It:
- Discovers SensorPush devices dynamically: every device owned by a config entry of the core `sensorpush` integration (`devices.async_get_source_devices`), not by manufacturer name
- On setup, calls `devices.async_remove_duplicate_devices` before forwarding the sensor platform — see **Device ownership** below
- Performs GATT audits on a fixed daily schedule at a configurable hour (default 3:00am local time), registered via `async_track_time_change` (`update_interval` is `None`). The hour is read from `entry.options.get(CONF_DAILY_AUDIT_HOUR, DEFAULT_DAILY_AUDIT_HOUR)`. The `_handle_daily_audit` callback is decorated with `@callback` — this is required for `hass.async_create_task` to be callable from within it; omitting it causes HA's thread-safety checker to raise a `RuntimeError` and silently drop the task. The unsub callback is stored on `coordinator._unsub_daily_audit` and called during unload.
- Schedules the initial audit as a background task on setup (not blocking — `async_config_entry_first_refresh` is intentionally not used; GATT connections take 10–45s per device and would exceed HA's stage 2 bootstrap timeout). The 3am recurring schedule is separate from this and fires independently each day.
- Exposes a `sensorpush_local.run_audit` service to trigger manual audits

**`audit_device()`** reads two GATT characteristics (Model and Battery UUIDs in `const.py`) and applies hardware-generation-specific voltage math:
- **HT1 (legacy)**: `(raw_mv + 2140) / 1000` V — detected by a 4-byte model characteristic response
- **HT.w / HTP.xw (modern)**: `raw_mv / 1000` V

RSSI is obtained from `bluetooth.async_last_service_info(hass, mac)` before connecting — `BLEDevice.rssi` was removed in newer bleak/habluetooth. After a successful read, the raw `source` identifier from `service_info` is resolved to a friendly name via `bluetooth.async_scanner_by_source(hass, source)` — this covers both local adapters (`hci0`) and ESPHome Bluetooth proxies (identified by MAC). Falls back to the raw identifier if the scanner is not found.

**`custom_components/sensorpush_local/sensor.py`** — `SensorPushVoltageSensor` pulls from coordinator cache keyed by MAC address. The entity is named "Battery Voltage" and defaults to 2 decimal places via `_attr_suggested_display_precision`. Extra state attributes include `rssi_at_read`, `proxy_source`, `raw_value`, `temp_at_read` (raw `uint16` from device — units are device-dependent, not calibrated °C), `last_audit`, and `model_type`.

`async_setup_entry` registers a `EVENT_DEVICE_REGISTRY_UPDATED` listener via `entry.async_on_unload`. On `create` of a device owned by a `sensorpush` entry, it adds an entity without requiring an integration reload; deduplication is handled by checking HA's entity registry (`async_get_entity_id`) rather than an in-memory set. On `remove`, it deletes our entity once no core SensorPush device with that MAC remains — deferred with `hass.loop.call_soon`, because HA is still dispatching the entity registry update that detaches our entity, and removing it mid-dispatch makes that update raise.

**`custom_components/sensorpush_local/devices.py`** — Device discovery (`async_get_source_devices`, `mac_from_identifiers`) and duplicate clean-up (`async_remove_duplicate_devices`).

### Device ownership (HA 2026.8+)

Since HA 2026.8 a device belongs to exactly one config entry; identifiers are only unique per config entry. The SensorPush devices are owned by the core `sensorpush` integration. This integration **must not own devices**:
- `SensorPushVoltageSensor` links to the core device by setting `self.device_entry` in `__init__`. Do not set `_attr_device_info` — any `DeviceInfo` creates a separate device owned by this config entry, which shows up as a duplicate of the sensor.
- HA's 2026.8 registry migration split every previously shared device into one copy per config entry, leaving each sensor duplicated. `async_remove_duplicate_devices` runs HA's `helper_integration.async_remove_helper_devices` once per core device to relink our entities and delete our copy, then removes any remaining device this entry owns (orphans whose core device is gone — their entities go with them). Before that, it moves *other* integrations' entities off each duplicate onto the core device: after the split, Battery Notes' entities ended up on our copy, and HA detaches a removed device's foreign entities rather than relinking them (only our own are relinked by the helper).

**`custom_components/sensorpush_local/config_flow.py`** — Single-instance only; no user input beyond clicking through. Exposes an `OptionsFlowHandler` with two configurable fields: `daily_audit_hour` (0–23, default 3) and `max_retries` (0–5, default 2), rendered as integer number boxes. Changing options triggers an entry reload via `entry.add_update_listener` → `_async_reload_entry`.

**`custom_components/sensorpush_local/diagnostics.py`** — Implements the HA diagnostics platform (`async_get_config_entry_diagnostics`). Returns current option values, coordinator state (device count, connection lock state, whether an audit is running, last update success), and per-device audit data (voltage, RSSI, proxy source, model type, last audit timestamp).

### Data Flow

```
HA startup / 3am daily schedule / manual service call
  → SensorPushCoordinator._async_update_data()
    → early exit if an audit is already running (preserves existing data)
    → holds _audit_lock for the whole pass
    → devices owned by core sensorpush config entries (dynamic discovery)
    → for each device: audit_device() acquires lock, performs GATT read, releases lock
      → RSSI and source from bluetooth.async_last_service_info (pre-connection)
      → source resolved to friendly name via bluetooth.async_scanner_by_source
    → coordinator.data dict updated (keyed by MAC)
    → INFO log emitted: "audit complete — X/Y device(s) updated"
  → SensorPushVoltageSensor reads coordinator.data
```

**Two locks:** `coordinator.lock` is held per GATT connection (inside `audit_device`) and is released between sensors and during the retry wait. `coordinator._audit_lock` is held for the whole `_async_update_data` pass, so a manual `run_audit` or scheduled refresh that arrives mid-audit is skipped instead of starting a second, overlapping pass. Don't make `audit_device` check `_audit_lock` — it runs inside it.

**Important:** `_async_update_data` seeds `new_data` from the existing `self.data` dict before the audit loop. This means a device that is temporarily unreachable keeps its last-known value rather than disappearing from `coordinator.data`. Only successful audits overwrite an entry. Do not change this to `new_data = {}`.

### Dependencies note

`aiousbwatcher` and `pyserial` in `pyproject.toml` are not used by this integration directly. They are hard-imported by `homeassistant.components.usb` (loaded transitively via the bluetooth stack) but are absent from HA's wheel `install_requires`. Without them declared explicitly, dependency installation in a clean environment (e.g. CI) fails with `ModuleNotFoundError`. Do not remove them.

### Dependency management (uv)

Dependencies are managed with [uv](https://docs.astral.sh/uv/), pinned to exact versions in `pyproject.toml` and locked in `uv.lock` (committed — do not gitignore it). The exception is `pytest-asyncio` and `pytest-cov`, listed unpinned in `[test]`: the test harness pins `pytest-asyncio` exactly, so an exact pin here broke `uv lock` whenever Renovate bumped one ahead of it (PR #50). They're out of Renovate's home assistant group for the same reason; they move when the harness does. The harness is `pytest-homeassistant`, Home Assistant's own package (with the `bluetooth` extra for `enable_bluetooth`); its version always equals the `homeassistant` release it was built from, so the two pins must match. It replaced `pytest-homeassistant-custom-component`, discontinued upstream in 2026-11 with no release for HA 2026.11 (SENS-8). `[tool.uv] environments` limits the lock to Linux and Apple Silicon macOS: on Intel macOS, `aioesphomeapi` caps `cryptography` below what `homeassistant` pins, so the lock can't resolve there. `requires-python` is capped `<3.15` so uv doesn't pick a 3.15 pre-release (pyyaml fails to build under it). Renovate leaves `requires-python` alone (a `pep621`/`requires-python` rule disables it): raising the floor to each new 3.14.x patch makes `uv lock` need that exact Python, which older uv builds, including the one in the Renovate runner image, can't download. Another rule holds the `python` package (the CI and devcontainer Docker images) below 3.15 until Home Assistant moves. CI runs `uv sync --extra test --locked`, which fails the build if `uv.lock` is out of sync with `pyproject.toml` instead of silently regenerating it — always run `uv lock` after hand-editing a dependency version and commit the result.

`uv.lock` embeds this project's own version number in a self-referencing entry, so `.forgejo/workflows/release.yml`'s release job runs `uv lock` again after bumping the version and includes it in the release commit — don't remove that step if you touch the release workflow.

`homeassistant`, `pytest-homeassistant`, `bleak-retry-connector`, `habluetooth`, `serialx`, `aioesphomeapi`, and the `python` Docker image version are grouped together in `renovate.json`'s "home assistant ecosystem" `packageRule` (with `automerge: false`) because they have hard version constraints on each other — bumping one without the others produces a combination that either can't resolve or silently installs an incompatible version. `habluetooth` in particular is transitive (pulled in by `bleak-retry-connector`/`homeassistant`, never imported directly) but pinned explicitly anyway: Renovate's `uv lock --upgrade-package X` only moves the named packages, so an undeclared transitive dependency stays frozen at whatever's already locked even when it's no longer actually compatible — declaring it gives Renovate something to name.

### Test Files

| File | What it covers |
|------|---------------|
| `tests/test_init.py` | Coordinator logic: service registration, unload, lock behaviour, background task scheduling, `_async_update_data`, `audit_device` error paths |
| `tests/test_sensor_entities.py` | `SensorPushVoltageSensor` entity: state, attributes, availability, `async_setup_entry` entity creation |
| `tests/test_devices.py` | Device ownership against the real registries: entity linked to the core device, duplicate/orphan clean-up on setup, entity removed with its core device |
| `tests/test_config_flow.py` | Config flow: form display, entry creation, single-instance abort, options flow defaults and save |
| `tests/test_diagnostics.py` | Diagnostics: default options output, custom options + live device data |
| `tests/test_sensor.py` | `audit_device` happy paths: model detection, voltage math, RSSI/source from service_info, scanner name resolution, timeout/lock/malformed-payload error paths |

### Test Fixtures

`tests/conftest.py` provides:
- `mock_coordinator` — coordinator instance with mocked Bluetooth and a no-op `async_refresh`
- `auto_enable_bluetooth` — enables BLE for all tests (auto-used)
- `sp_entry` — a core `sensorpush` config entry; register test SensorPush devices under it, not under the `sensorpush_local` entry

## Linting and formatting

```bash
uv run black custom_components/ tests/ scripts/       # format
uv run isort custom_components/ tests/ scripts/       # sort imports
uv run flake8 custom_components/ tests/ scripts/      # style + unused imports
uv run pylint custom_components/ tests/ scripts/      # static analysis (threshold: 9.5/10)
```

Config: `[tool.black]` and `[tool.isort]` in `pyproject.toml`; `[flake8]` and `[pylint.messages_control]` in `setup.cfg`. All four run in CI after tests.

## Version bumping

Releases are automated via the `.forgejo/workflows/release.yml` workflow, split across two triggers because `main` is a protected branch and Forgejo Actions cannot push to a protected branch directly (open upstream bug: [forgejo#11159](https://codeberg.org/forgejo/forgejo/issues/11159) — the pre-receive hook crashes trying to resolve the synthetic Actions user). Trigger it manually (`workflow_dispatch`) with a `version` input (e.g. `1.0.3`, no `v` prefix):

1. **`prepare-release`** runs the full test/lint suite, bumps the version in `manifest.json`, `pyproject.toml`, and the README badge, refreshes `uv.lock`'s self-version entry, commits to a new `release/vX.Y.Z` branch (not `main` — unaffected by the bug), opens a PR, and schedules auto-merge.
2. **`finalize-release`** triggers on that PR's merge (`pull_request: types: [closed]`, filtered to merged PRs on a `release/*` branch), tags `vX.Y.Z` (tag pushes aren't covered by branch protection, so unaffected by the bug), creates a release on this Forgejo instance, waits for the push mirrors to sync the tag to GitHub and then Codeberg, and creates a release on each. All three releases get the notes from `scripts/release_notes.py` (see below).

**Secrets come from 1Password** (SENS-11), the same pattern as homelab's workflows. The only Forgejo repo secret the workflows use is `OP_SERVICE_ACCOUNT_TOKEN`, a 1Password service account that can read just the `Sensorpush-Local` vault. Each job loads its secrets with `1password/load-secrets-action` (`export-env: true`). To rotate a secret, update its 1Password item; the workflows don't change. Env var names avoid the `FORGEJO_`, `GITHUB_` and `GITEA_` prefixes: the runner sets its own variables there (`FORGEJO_TOKEN` is the automatic Actions token, mirrored as `GITHUB_TOKEN`), and Forgejo rejects secret and variable names that use them. That rule is why the old Forgejo secrets were named `FORGEJORELEASE_TOKEN` and `GH_RELEASE_TOKEN`. 1Password item titles have no such limit.

| Env var | 1Password item (`Sensorpush-Local` vault) | Used by |
| --- | --- | --- |
| `RELEASE_BOT_FORGEJO_TOKEN` | `FORGEJO_RELEASE_TOKEN` / `password` | `prepare-release`: release branch push, PR, auto-merge |
| `RELEASE_BOT_GPG_KEY` | `Release Bot GPG Key` / file `release-bot-private.key` | signing the release commit and tag |
| `OPENROUTER_API_KEY` | `OpenRouter PR Review API Key` / `password` | advisory AI PR reviews and Renovate major-update summaries |
| `RELEASE_BOT_OPENROUTER_KEY` | `Release Bot OpenRouter Key` / `password` | `scripts/release_notes.py` |
| `GH_RELEASE_TOKEN` | `GITHUB_RELEASE_TOKEN` / `password` | GitHub tag poll and release |
| `CODEBERG_RELEASE_TOKEN` | `CODEBERG_RELEASE_TOKEN` / `password` | Codeberg tag poll and release |

`prepare-release` also resolves `finalize-release`'s secrets, without exporting them, so a missing or renamed item fails the run before the release branch exists. Otherwise it would fail after `finalize-release` had already pushed the tag. Renovate's secrets (`RENOVATE_TOKEN`, `RENOVATE_GIT_PRIVATE_KEY`, `GITHUBCOM_TOKEN` in `renovate.yml`) aren't repo secrets and aren't in this vault.

`prepare-release`'s branch push and PR/auto-merge API calls use `RELEASE_BOT_FORGEJO_TOKEN`: a Personal Access Token from the release-bot Forgejo account (repository read and write), not the default Actions token. This is required for a reason beyond the branch-protection bug: Forgejo never triggers new workflow runs from a push or PR made with the default token (anti-recursion), so `ci.yml`'s required status check would never run on the release branch and auto-merge would wait forever.

GitHub and Codeberg are public push mirrors of this repo (repo Settings > Repository > Mirror settings, sync on commit), so tags reach them on their own. Their releases are created through each host's API: `GH_RELEASE_TOKEN` for GitHub (a fine-grained PAT with Contents read/write on this repo only), and `CODEBERG_RELEASE_TOKEN` (SENS-7) for Codeberg (repository read/write on this repo only). Codeberg runs Forgejo, so its release call is the same API as the Forgejo one. It runs last, so a Codeberg problem can't hold up the GitHub release.

The release commit and the `vX.Y.Z` tag are GPG-signed as `Release Bot <release-bot@berry.house>`, the account behind `RELEASE_BOT_FORGEJO_TOKEN`. `RELEASE_BOT_GPG_KEY` is that key's armored private key (no passphrase), the `release-bot-private.key` file on the vault's `Release Bot GPG Key` item; the public half is verified on the release-bot account. Forgejo verifies a signature against the committer email, so keep the workflow's git identity matching the key's UID and the account email. The fingerprint is `RELEASE_BOT_GPG_FINGERPRINT` at the top of `release.yml`; change it there when rotating the key. Renovate's commits are signed with the renovate-bot key through `RENOVATE_GIT_PRIVATE_KEY` in `renovate.yml`.

**Release notes** (SENS-9): `scripts/release_notes.py` sends the commits since the previous tag (subjects and bodies, co-author lines removed), plus version facts it works out itself (the HA version tested against, the minimum HA version from `hacs.json`, pin changes in `pyproject.toml`), to OpenRouter (`openai/gpt-6.1-sol`, the model homelab's AI review uses). The model returns JSON: a short summary and bullets for four sections (New & improved, Fixes, Home Assistant compatibility, Maintenance). The script renders the Markdown itself, drops empty sections, and always appends the full commit list (in a `<details>` block) and a compare link, which points at Forgejo, GitHub or Codeberg depending on the release. Any model failure, including a missing key or an unusable reply, logs a warning and falls back to the plain commit list, so the notes never block a release. The key is `RELEASE_BOT_OPENROUTER_KEY`, Release Bot's own OpenRouter key with a $10/month limit. Calls identify themselves to OpenRouter as `sensorpush_local Release Bot` (hidden from public rankings). To check the output for an existing tag without releasing, run the **Release notes preview** workflow (`release-notes.yml`). `python3 scripts/release_notes.py vX.Y.Z --out-dir /tmp/rn --print-prompt` prints the model input locally, and `tests/test_release_notes.py` covers rendering and the fallback.

Do not bump these files or create tags manually — the workflow is the only supported release path. If auto-merge doesn't fire (e.g. the required status check config changes), merge the `release/vX.Y.Z` PR manually — `finalize-release` still triggers on any merge of a matching branch, however it happened. Auto-merge is scheduled as `fast-forward-only`, the repo's default style, so Release Bot's signed commit lands on main unchanged. The old `merge` style isn't allowed here, so Forgejo accepted the schedule but couldn't complete it; v1.0.5 was squashed by hand. If main moved during CI, use "Update branch by rebase" rather than a squash.

## CI image

`.devcontainer/Dockerfile` builds one image for both the devcontainer and CI (SENS-10): Python 3.14 (the integration's version), the test suite's system packages, gnupg for Release Bot's signing, and Node.js for the runner's JavaScript actions. `.forgejo/workflows/ci-image.yml` builds it, runs `.devcontainer/smoke-test.sh` and the full test suite inside it, and publishes it as `registry.berry.house/sensorpush-local/ci` with two tags: the Dockerfile's hash and `:latest`. It runs on every push to `main` but only builds when `:latest` isn't already the current Dockerfile's image, so a failed publish is redone by the next merge. PRs that touch the image build and check it under a throwaway local tag and never push. Change the Python version or system packages only in the Dockerfile.

Pushing uses the Zot user `sensorpush-local`, which can push only under `sensorpush-local/` (homelab HOME-359; the shared `ci` user can't push there). Its credentials are the `Zot Registry sensorpush-local Push` item, which exists in both the Sensorpush-Local vault (for this workflow) and homelab's Homelab vault (for the zot Ansible role). A 1Password service account's vault access can't be changed after it's created, so each side has its own copy: rotate both together, then rerun homelab's zot play.

## Devcontainer / ~/.claude mounts

Mount only cross-platform-safe subdirectories — not `~/.claude` wholesale. Plugins are platform-specific binaries; mounting them from macOS into Linux breaks them. Safe to share: `settings.json`, `skills/`, `projects/`.

Because `~/.claude/plugins` isn't mounted, `.devcontainer/post-create.sh` installs the `kyle-dev` and `berry-mcp` plugins (kyleberry/claude-plugins) inside the container. kyle-dev's guard hook blocks commits on main and needs `jq`, which the Dockerfile installs (the same Dockerfile builds the CI image, see above). If gitea.berry.house is unreachable at create time, the script warns and carries on; rerun it later.

berry-mcp needs `MCP_BEARER_TOKEN`, passed in via `containerEnv` from the environment of whatever starts the container. Open VS Code from a terminal in this repo (`code .`), so direnv has loaded it from `~/git/.envrc`. `runArgs` points the container's DNS at AdGuard (192.168.86.2) so `mcp.berry.house` resolves to Caddy on the LAN, as on the host.
