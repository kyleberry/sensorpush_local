# pylint: disable=protected-access
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensorpush_local import SensorPushCoordinator
from custom_components.sensorpush_local.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_bluetooth(enable_bluetooth):  # pylint: disable=unused-argument
    """Enable bluetooth for all tests automatically."""
    return


@pytest.fixture(autouse=True)
def expected_lingering_timers() -> bool:
    """Tolerate BaseHaScanner's periodic expire-devices timer at teardown.

    homeassistant's bluetooth component (via habluetooth) schedules a
    recurring `_async_expire_devices_schedule_next` timer when the scanner
    starts. pytest_homeassistant_custom_component's `enable_bluetooth`
    fixture correctly unloads the "bluetooth" domain's own config entry at
    teardown, but that doesn't reach this timer in every homeassistant/
    habluetooth version combination — confirmed as a known upstream
    core-vs-harness interaction (not a bug in this integration's code) via
    https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/issues/153,
    where the same `expected_lingering_timers` pattern is the accepted
    workaround. Not observed with the versions pinned as of this writing
    (homeassistant==2026.2.3) — added ahead of the next homeassistant bump
    so it doesn't reappear as a surprise CI failure.
    """
    return True


@pytest.fixture
async def mock_coordinator(hass):
    """Create a coordinator instance for tests."""
    # 1. Create a proper MockConfigEntry for the coordinator to latch onto
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    mock_entry.add_to_hass(hass)

    with patch(
        "custom_components.sensorpush_local.bluetooth.async_ble_device_from_address"
    ) as mock_bt:
        mock_device = MagicMock()
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_bt.return_value = mock_device

        # 2. Pass the mock_entry as the required second argument
        coordinator = SensorPushCoordinator(hass, mock_entry)

        # We mock async_refresh so we don't actually trigger BLE audits in tests
        coordinator.async_refresh = AsyncMock()

        # Mock storage so tests don't touch the filesystem
        coordinator._store.async_load = AsyncMock(return_value=None)
        coordinator._store.async_save = AsyncMock()

        return coordinator
