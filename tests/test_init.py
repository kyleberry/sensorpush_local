import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from custom_components.sensorpush_local.const import DOMAIN
from custom_components.sensorpush_local import async_setup_entry


@pytest.mark.asyncio
async def test_run_audit_service(hass, mock_coordinator):
    """Test that calling the run_audit service triggers a coordinator refresh."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "mock_entry_id"
    mock_entry.domain = DOMAIN

    with patch("custom_components.sensorpush_local.SensorPushCoordinator", return_value=mock_coordinator), \
            patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"):
        await async_setup_entry(hass, mock_entry)

    with patch.object(mock_coordinator, "async_refresh", AsyncMock()) as mock_refresh:
        await hass.services.async_call(DOMAIN, "run_audit", {}, blocking=True)
        mock_refresh.assert_called_once()
