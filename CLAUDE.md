# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Full pre-push check (tests + all linters)
uv run pytest tests/ && uv run black --check --target-version py313 custom_components/ tests/ && uv run isort --check-only custom_components/ tests/ && uv run flake8 custom_components/ tests/ && uv run pylint custom_components/ tests/

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

## Architecture

This is a Home Assistant custom integration that provides 100% local Bluetooth monitoring for SensorPush environmental sensors via Bluetooth proxies.

### Core Components

**`custom_components/sensorpush_local/__init__.py`** — `SensorPushCoordinator` (extends `DataUpdateCoordinator`) is the heart of the integration. It:
- Discovers registered SensorPush devices dynamically from the HA device registry
- Performs GATT audits on a fixed daily schedule at a configurable hour (default 3:00am local time), registered via `async_track_time_change` (`update_interval` is `None`). The hour is read from `entry.options.get(CONF_DAILY_AUDIT_HOUR, DEFAULT_DAILY_AUDIT_HOUR)`. The `_handle_daily_audit` callback is decorated with `@callback` — this is required for `hass.async_create_task` to be callable from within it; omitting it causes HA's thread-safety checker to raise a `RuntimeError` and silently drop the task. The unsub callback is stored on `coordinator._unsub_daily_audit` and called during unload.
- Schedules the initial audit as a background task on setup (not blocking — `async_config_entry_first_refresh` is intentionally not used; GATT connections take 10–45s per device and would exceed HA's stage 2 bootstrap timeout). The 3am recurring schedule is separate from this and fires independently each day.
- Exposes a `sensorpush_local.run_audit` service to trigger manual audits

**`audit_device()`** reads two GATT characteristics (Model and Battery UUIDs in `const.py`) and applies hardware-generation-specific voltage math:
- **HT1 (legacy)**: `(raw_mv + 2140) / 1000` V — detected by a 4-byte model characteristic response
- **HT.w / HTP.xw (modern)**: `raw_mv / 1000` V

RSSI is obtained from `bluetooth.async_last_service_info(hass, mac)` before connecting — `BLEDevice.rssi` was removed in newer bleak/habluetooth. After a successful read, the raw `source` identifier from `service_info` is resolved to a friendly name via `bluetooth.async_scanner_by_source(hass, source)` — this covers both local adapters (`hci0`) and ESPHome Bluetooth proxies (identified by MAC). Falls back to the raw identifier if the scanner is not found.

**`custom_components/sensorpush_local/sensor.py`** — `SensorPushVoltageSensor` pulls from coordinator cache keyed by MAC address. The entity is named "Battery Voltage" and defaults to 2 decimal places via `_attr_suggested_display_precision`. Extra state attributes include `rssi_at_read`, `proxy_source`, `raw_value`, `temp_at_read` (raw `uint16` from device — units are device-dependent, not calibrated °C), `last_audit`, and `model_type`.

`async_setup_entry` registers a `EVENT_DEVICE_REGISTRY_UPDATED` listener via `entry.async_on_unload` so that new SensorPush devices added after setup automatically get an entity without requiring an integration reload. Deduplication is handled by checking HA's entity registry (`async_get_entity_id`) rather than an in-memory set — this correctly handles device removal and re-addition without requiring an integration reload.

**`custom_components/sensorpush_local/config_flow.py`** — Single-instance only; no user input beyond clicking through. Exposes an `OptionsFlowHandler` with two configurable fields: `daily_audit_hour` (0–23, default 3) and `max_retries` (0–5, default 2), rendered as integer number boxes. Changing options triggers an entry reload via `entry.add_update_listener` → `_async_reload_entry`.

**`custom_components/sensorpush_local/diagnostics.py`** — Implements the HA diagnostics platform (`async_get_config_entry_diagnostics`). Returns current option values, coordinator state (device count, lock state, last update success), and per-device audit data (voltage, RSSI, proxy source, model type, last audit timestamp).

### Data Flow

```
HA startup / 3am daily schedule / manual service call
  → SensorPushCoordinator._async_update_data()
    → early exit if lock is already held (preserves existing data)
    → device_registry lookup (dynamic discovery)
    → for each device: audit_device() acquires lock, performs GATT read, releases lock
      → RSSI and source from bluetooth.async_last_service_info (pre-connection)
      → source resolved to friendly name via bluetooth.async_scanner_by_source
    → coordinator.data dict updated (keyed by MAC)
    → INFO log emitted: "audit complete — X/Y device(s) updated"
  → SensorPushVoltageSensor reads coordinator.data
```

**Important:** `_async_update_data` seeds `new_data` from the existing `self.data` dict before the audit loop. This means a device that is temporarily unreachable keeps its last-known value rather than disappearing from `coordinator.data`. Only successful audits overwrite an entry. Do not change this to `new_data = {}`.

### Dependencies note

`aiousbwatcher` and `pyserial` in `pyproject.toml` are not used by this integration directly. They are hard-imported by `homeassistant.components.usb` (loaded transitively via the bluetooth stack) but are absent from HA's wheel `install_requires`. Without them declared explicitly, dependency installation in a clean environment (e.g. CI) fails with `ModuleNotFoundError`. Do not remove them.

### Dependency management (uv)

Dependencies are managed with [uv](https://docs.astral.sh/uv/), pinned to exact versions in `pyproject.toml` and locked in `uv.lock` (committed — do not gitignore it). CI runs `uv sync --extra test --locked`, which fails the build if `uv.lock` is out of sync with `pyproject.toml` instead of silently regenerating it — always run `uv lock` after hand-editing a dependency version and commit the result.

`uv.lock` embeds this project's own version number in a self-referencing entry, so `.forgejo/workflows/release.yml`'s release job runs `uv lock` again after bumping the version and includes it in the release commit — don't remove that step if you touch the release workflow.

`homeassistant`, `pytest-homeassistant-custom-component`, `bleak-retry-connector`, `pytest-asyncio`, `pytest-cov`, `habluetooth`, and the `python`/`requires-python` version are grouped together in `renovate.json`'s "home assistant ecosystem" `packageRule` (with `automerge: false`) because they have hard version constraints on each other — bumping one without the others produces a combination that either can't resolve or silently installs an incompatible version. `habluetooth` in particular is transitive (pulled in by `bleak-retry-connector`/`homeassistant`, never imported directly) but pinned explicitly anyway: Renovate's `uv lock --upgrade-package X` only moves the named packages, so an undeclared transitive dependency stays frozen at whatever's already locked even when it's no longer actually compatible — declaring it gives Renovate something to name.

### Test Files

| File | What it covers |
|------|---------------|
| `tests/test_init.py` | Coordinator logic: service registration, unload, lock behaviour, background task scheduling, `_async_update_data`, `audit_device` error paths |
| `tests/test_sensor_entities.py` | `SensorPushVoltageSensor` entity: state, attributes, availability, `async_setup_entry` entity creation |
| `tests/test_config_flow.py` | Config flow: form display, entry creation, single-instance abort, options flow defaults and save |
| `tests/test_diagnostics.py` | Diagnostics: default options output, custom options + live device data |
| `tests/test_sensor.py` | `audit_device` happy paths: model detection, voltage math, RSSI/source from service_info, scanner name resolution, timeout/lock/malformed-payload error paths |

### Test Fixtures

`tests/conftest.py` provides:
- `mock_coordinator` — coordinator instance with mocked Bluetooth and a no-op `async_refresh`
- `auto_enable_bluetooth` — enables BLE for all tests (auto-used)

## Linting and formatting

```bash
uv run black custom_components/ tests/       # format
uv run isort custom_components/ tests/       # sort imports
uv run flake8 custom_components/ tests/      # style + unused imports
uv run pylint custom_components/ tests/      # static analysis (threshold: 9.5/10)
```

Config: `[tool.black]` and `[tool.isort]` in `pyproject.toml`; `[flake8]` and `[pylint.messages_control]` in `setup.cfg`. All four run in CI after tests.

## Version bumping

Releases are automated via the `.forgejo/workflows/release.yml` workflow. Trigger it manually (`workflow_dispatch`) with a `version` input (e.g. `1.0.3`, no `v` prefix). It runs the full test/lint suite, then bumps the version in `custom_components/sensorpush_local/manifest.json`, `pyproject.toml`, and the README badge, refreshes `uv.lock`'s self-version entry, commits, tags `vX.Y.Z`, creates a release on this Forgejo instance, waits for the push mirror to sync the tag to GitHub, and creates the GitHub release with an auto-generated changelog.

Do not bump these files or create tags manually — the workflow is the only supported release path.

## Devcontainer / ~/.claude mounts

Mount only cross-platform-safe subdirectories — not `~/.claude` wholesale. Plugins are platform-specific binaries; mounting them from macOS into Linux breaks them. Safe to share: `settings.json`, `skills/`, `projects/`.
