import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from homeassistant import config_entries, data_entry_flow
from custom_components.sensorpush_local.const import DOMAIN

@pytest.mark.asyncio
async def test_user_form(hass):
    """Test the user setup form flow."""

    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    from custom_components.sensorpush_local.config_flow import SensorPushConfigFlow
    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):

        with patch("homeassistant.loader.async_get_integration", return_value=mock_integration), \
             patch("homeassistant.requirements.async_get_integration_with_requirements", return_value=mock_integration), \
             patch("homeassistant.setup.async_process_deps_reqs", return_value=True):

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == "form"
            assert result["step_id"] == "user"