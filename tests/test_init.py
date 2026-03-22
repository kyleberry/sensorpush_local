import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from custom_components.sensorpush_local.const import DOMAIN
from custom_components.sensorpush_local import async_setup_entry
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.config_entries import ConfigEntryState


@pytest.mark.asyncio
async def test_run_audit_service(hass, mock_coordinator):
    """Test that calling the run_audit service triggers a coordinator refresh."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)

    # 1. Set the state to SETUP_IN_PROGRESS so the coordinator allows the refresh
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    # 2. Link them up
    mock_coordinator.config_entry = mock_entry

    with patch("custom_components.sensorpush_local.SensorPushCoordinator", return_value=mock_coordinator), \
         patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"):

        await async_setup_entry(hass, mock_entry)

        # Verify service call triggers refresh
        await hass.services.async_call(DOMAIN, "run_audit", blocking=True)
        mock_coordinator.async_refresh.assert_called_once()
