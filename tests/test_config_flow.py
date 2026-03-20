import pytest
from unittest.mock import patch, MagicMock
from homeassistant import config_entries, data_entry_flow
from custom_components.sensorpush_local.const import DOMAIN


@pytest.mark.asyncio
async def test_user_form(hass):
    """Test the user setup form flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={},
    )
    await hass.async_block_till_done()

    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "SensorPush Local"


@pytest.mark.asyncio
async def test_single_instance_allowed(hass):
    """Test that we can only have one instance of the integration."""
    entry = MagicMock()
    entry.domain = DOMAIN
    # Use the local DOMAIN string instead of a mock for the comparison
    with patch("homeassistant.config_entries.ConfigFlow._async_current_entries", return_value=[entry]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.ABORT
        assert result["reason"] == "single_instance_allowed"
