import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.sensorpush_local import SensorPushCoordinator
from custom_components.sensorpush_local.const import DOMAIN

@pytest.fixture(autouse=True)
def auto_enable_bluetooth(enable_bluetooth):
    """Enable bluetooth for all tests automatically."""
    return

@pytest.fixture
async def mock_coordinator(hass):
    """Create a coordinator instance for tests."""
    # 1. Create a proper MockConfigEntry for the coordinator to latch onto
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_id",
        data={}
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address") as mock_bt:
        mock_device = MagicMock()
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_bt.return_value = mock_device

        # 2. Pass the mock_entry as the required second argument
        coordinator = SensorPushCoordinator(hass, mock_entry)

        # We mock async_refresh so we don't actually trigger BLE audits in tests
        coordinator.async_refresh = AsyncMock()

        return coordinator