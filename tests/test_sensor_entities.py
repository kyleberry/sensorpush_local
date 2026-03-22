import pytest
from homeassistant.helpers import device_registry as dr
from custom_components.sensorpush_local.const import DOMAIN
from custom_components.sensorpush_local.sensor import SensorPushVoltageSensor
from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.mark.asyncio
async def test_sensor_state_reporting(hass, mock_coordinator):
    """Test the SensorPush battery entity logic directly."""

    # 1. Setup mock entry and add to Hass
    entry_id = "mock_entry_id"
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        data={}
    )
    entry.add_to_hass(hass)

    mac_addr = "AA:BB:CC:DD:EE:FF"
    device_name = "Test Kitchen Sensor"

    # 2. Setup mock data in coordinator
    # Your sensor pulls from self.coordinator.data.get(self._mac)
    mock_coordinator.data = {
        mac_addr: {
            "voltage": 3.021,
            "rssi": -60,
            "is_legacy": True,
            "source": "hci0",
            "raw_v": 3021,
            "temp_at_read": 22.5,
            "timestamp": "2026-03-21T22:00:00"
        }
    }

    # 3. Add mock device to registry
    dev_reg = dr.async_get(hass)
    device_obj = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", mac_addr)},
        manufacturer="SensorPush",
        name=device_name
    )

    # 4. Manually instantiate the sensor
    # Match the positional args in your sensor.py: coordinator, device, mac
    sensor = SensorPushVoltageSensor(
        mock_coordinator,
        device_obj,
        mac_addr
    )
    sensor.hass = hass

    # 5. Verify Core Logic (Directly hits sensor.py code)
    assert sensor.native_value == 3.021
    assert sensor.available is True

    # 6. Verify Austin Ranch Mapping (Checking your aliased keys)
    attrs = sensor.extra_state_attributes

    assert attrs["rssi_at_read"] == -60
    assert attrs["proxy_source"] == "hci0"
    assert attrs["raw_value"] == 3021
    assert attrs["temp_at_read"] == 22.5
    assert attrs["last_audit"] == "2026-03-21T22:00:00"
    assert attrs["model_type"] == "Legacy (HT1)"

    # 7. Verify unique_id
    assert sensor.unique_id == f"sp_{mac_addr.replace(':', '').lower()}_volt_native"

    # 8. Coverage for the 'Unavailable' logic branch
    mock_coordinator.data = {}
    assert sensor.available is False