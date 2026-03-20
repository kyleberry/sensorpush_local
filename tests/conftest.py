import pytest
from unittest.mock import patch, MagicMock
from custom_components.sensorpush_local.const import DOMAIN
from custom_components.sensorpush_local import SensorPushCoordinator

@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Required by pytest-homeassistant-custom-component to load local code."""
    yield

@pytest.fixture
async def mock_coordinator(hass):
    """Create a coordinator instance for tests."""
    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address") as mock_bt:
        mock_device = MagicMock()
        mock_device.address = "AA:BB:CC:DD:EE:FF"
        mock_bt.return_value = mock_device

        coordinator = SensorPushCoordinator(hass)
        hass.data[DOMAIN] = {"mock_entry_id": coordinator}
        yield coordinator