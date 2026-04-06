from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensorpush_local.config_flow import SensorPushConfigFlow
from custom_components.sensorpush_local.const import (
    CONF_DAILY_AUDIT_HOUR,
    CONF_MAX_RETRIES,
    DOMAIN,
)


def _flow_patches(mock_integration):
    """Return the standard loader patches needed to init a config flow."""
    return (
        patch(
            "homeassistant.loader.async_get_integration", return_value=mock_integration
        ),
        patch(
            "homeassistant.requirements.async_get_integration_with_requirements",
            return_value=mock_integration,
        ),
        patch("homeassistant.setup.async_process_deps_reqs", return_value=True),
    )


@pytest.mark.asyncio
async def test_user_form(hass):
    """Test that the user setup form is shown on first init."""
    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):
        p1, p2, p3 = _flow_patches(mock_integration)
        with p1, p2, p3:
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

    assert result["type"] == "form"
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_user_form_creates_entry(hass):
    """Test that submitting the form creates a config entry."""
    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):
        p1, p2, p3 = _flow_patches(mock_integration)
        with p1, p2, p3:
            await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                list(hass.config_entries.flow.async_progress())[0]["flow_id"],
                user_input={},
            )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "SensorPush Local"
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_single_instance_abort(hass):
    """Test that a second setup attempt is aborted."""
    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):
        p1, p2, p3 = _flow_patches(mock_integration)
        with p1, p2, p3:
            # First flow — complete it so an entry exists
            await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            await hass.config_entries.flow.async_configure(
                list(hass.config_entries.flow.async_progress())[0]["flow_id"],
                user_input={},
            )

            # Second flow — should abort
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_single_instance_abort_direct(hass):
    """Test async_step_user line 11: abort when _async_current_entries returns entries."""
    flow = SensorPushConfigFlow()
    flow.hass = hass
    with patch.object(flow, "_async_current_entries", return_value=[MagicMock()]):
        result = await flow.async_step_user()
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_options_flow_shows_defaults(hass):
    """Test that the options form shows default values when no options are set."""
    entry = MockConfigEntry(
        domain=DOMAIN, entry_id="test_options_id", data={}, options={}
    )
    entry.add_to_hass(hass)

    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):
        p1, p2, p3 = _flow_patches(mock_integration)
        with p1, p2, p3:
            result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    schema_keys = {str(k): k for k in result["data_schema"].schema}
    assert CONF_DAILY_AUDIT_HOUR in schema_keys
    assert CONF_MAX_RETRIES in schema_keys


@pytest.mark.asyncio
async def test_options_flow_saves_values(hass):
    """Test that submitting the options form persists the chosen values."""
    entry = MockConfigEntry(
        domain=DOMAIN, entry_id="test_options_id", data={}, options={}
    )
    entry.add_to_hass(hass)

    mock_integration = AsyncMock()
    mock_integration.domain = DOMAIN

    with patch.dict(config_entries.HANDLERS, {DOMAIN: SensorPushConfigFlow}):
        p1, p2, p3 = _flow_patches(mock_integration)
        with p1, p2, p3:
            result = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                result["flow_id"],
                user_input={CONF_DAILY_AUDIT_HOUR: 6, CONF_MAX_RETRIES: 3},
            )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DAILY_AUDIT_HOUR] == 6
    assert entry.options[CONF_MAX_RETRIES] == 3
