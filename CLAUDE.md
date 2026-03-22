# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install with test dependencies
pip install -e .[test] --config-settings editable_mode=compat

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_init.py

# Run a single test
pytest tests/test_init.py::test_function_name

# Run with coverage (shows missing lines)
pytest tests/ --cov=custom_components/sensorpush_local --cov-report=term-missing
```

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
- Performs GATT audits on a 24-hour schedule, with a global `asyncio.Lock()` to prevent concurrent Bluetooth proxy contention
- Runs an initial audit on setup
- Exposes a `sensorpush_local.run_audit` service to trigger manual audits

**`audit_device()`** reads two GATT characteristics (Model and Battery UUIDs in `const.py`) and applies hardware-generation-specific voltage math:
- **HT1 (legacy)**: `(raw_mv + 2140) / 1000` V — detected by a 4-byte model characteristic response
- **HT.w / HTP.xw (modern)**: `raw_mv / 1000` V

After a successful read, the raw `source` identifier from `ble_device.details` is resolved to a friendly name via `bluetooth.async_scanner_by_source(hass, source)` — this covers both local adapters (`hci0`) and ESPHome Bluetooth proxies (identified by MAC). Falls back to the raw identifier if the scanner is not found.

**`custom_components/sensorpush_local/sensor.py`** — `SensorPushVoltageSensor` pulls from coordinator cache keyed by MAC address. Extra state attributes include `rssi_at_read`, `proxy_source`, `raw_value`, `temp_at_read` (raw `uint16` from device — units are device-dependent, not calibrated °C), `last_audit`, and `model_type`.

**`custom_components/sensorpush_local/config_flow.py`** — Single-instance only; no user input beyond clicking through.

### Data Flow

```
HA startup / manual service call
  → SensorPushCoordinator._async_update_data()
    → early exit if lock is already held (preserves existing data)
    → device_registry lookup (dynamic discovery)
    → for each device: audit_device() acquires lock, performs GATT read, releases lock
    → coordinator.data dict updated (keyed by MAC)
  → SensorPushVoltageSensor reads coordinator.data
```

**Important:** `_async_update_data` seeds `new_data` from the existing `self.data` dict before the audit loop. This means a device that is temporarily unreachable keeps its last-known value rather than disappearing from `coordinator.data`. Only successful audits overwrite an entry. Do not change this to `new_data = {}`.

### Test Files

| File | What it covers |
|------|---------------|
| `tests/test_init.py` | Coordinator logic: service registration, unload, lock behaviour, `_async_update_data`, `audit_device` error paths |
| `tests/test_sensor_entities.py` | `SensorPushVoltageSensor` entity: state, attributes, availability, `async_setup_entry` entity creation |
| `tests/test_config_flow.py` | Config flow: form display, entry creation, single-instance abort |
| `tests/test_sensor.py` | `audit_device` happy paths: model detection, voltage math, scanner name resolution, timeout/lock/malformed-payload error paths |

### Test Fixtures

`tests/conftest.py` provides:
- `mock_coordinator` — coordinator instance with mocked Bluetooth and a no-op `async_refresh`
- `auto_enable_bluetooth` — enables BLE for all tests (auto-used)
