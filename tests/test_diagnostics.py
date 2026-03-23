import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.sensorpush_local.const import (
    DOMAIN,
    CONF_DAILY_AUDIT_HOUR,
    CONF_MAX_RETRIES,
    DEFAULT_DAILY_AUDIT_HOUR,
    DEFAULT_MAX_RETRIES,
)
from custom_components.sensorpush_local.diagnostics import async_get_config_entry_diagnostics


@pytest.mark.asyncio
async def test_diagnostics_default_options(hass, mock_coordinator):
    """Test diagnostics output when no options are set (shows defaults)."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={}, options={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator
    mock_coordinator.data = {}

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["options"]["daily_audit_hour"] == DEFAULT_DAILY_AUDIT_HOUR
    assert result["options"]["max_retries"] == DEFAULT_MAX_RETRIES
    assert result["coordinator"]["device_count"] == 0
    assert result["coordinator"]["last_update_success"] is True
    assert result["devices"] == {}


@pytest.mark.asyncio
async def test_diagnostics_with_options_and_data(hass, mock_coordinator):
    """Test diagnostics output with custom options and live device data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="mock_entry_id",
        data={},
        options={CONF_DAILY_AUDIT_HOUR: 6, CONF_MAX_RETRIES: 0},
    )
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator
    mock_coordinator.data = {
        "AA:BB:CC:DD:EE:FF": {
            "voltage": 3.021,
            "rssi": -60,
            "source": "Living Room Hub",
            "is_legacy": False,
            "timestamp": "2026-03-23T03:00:00",
        }
    }

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["options"]["daily_audit_hour"] == 6
    assert result["options"]["max_retries"] == 0
    assert result["coordinator"]["device_count"] == 1
    assert "AA:BB:CC:DD:EE:FF" in result["devices"]
    device = result["devices"]["AA:BB:CC:DD:EE:FF"]
    assert device["voltage"] == 3.021
    assert device["proxy_source"] == "Living Room Hub"
    assert device["model_type"] == "Modern (HT.w/HTP.xw)"
    assert device["last_audit"] == "2026-03-23T03:00:00"
