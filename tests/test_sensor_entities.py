import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from homeassistant.helpers import device_registry as dr
from custom_components.sensorpush_local.const import DOMAIN, MANUFACTURER
from custom_components.sensorpush_local.sensor import SensorPushVoltageSensor, async_setup_entry
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

    # 8. Coverage for the 'Unavailable' logic branch (audit ran, device absent)
    mock_coordinator.data = {}
    assert sensor.available is False
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    # 9. Coverage for the 'audit pending' branch (coordinator never ran)
    mock_coordinator.data = None
    assert sensor.available is True
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    # 10. Coverage for coordinator failure branch (last_update_success = False)
    mock_coordinator.last_update_success = False
    assert sensor.available is False
    mock_coordinator.last_update_success = True


@pytest.mark.asyncio
async def test_sensor_async_setup_entry_creates_entities(hass, mock_coordinator):
    """Test that async_setup_entry creates one entity per registered SensorPush device."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    entry.add_to_hass(hass)

    # Link coordinator into hass.data as the real setup would
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    # Register two SensorPush devices in the device registry
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", "AA:BB:CC:DD:EE:FF")},
        manufacturer=MANUFACTURER,
        name="Sensor One",
    )
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", "11:22:33:44:55:66")},
        manufacturer=MANUFACTURER,
        name="Sensor Two",
    )

    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    assert len(added) == 2
    macs = {e._mac for e in added}
    assert macs == {"AA:BB:CC:DD:EE:FF", "11:22:33:44:55:66"}
    assert all(isinstance(e, SensorPushVoltageSensor) for e in added)


@pytest.mark.asyncio
async def test_new_device_auto_creates_entity(hass, mock_coordinator):
    """Test that a SensorPush device added after setup automatically gets an entity."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    dev_reg = dr.async_get(hass)
    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 0  # no devices present at setup time

    # Simulate a new SensorPush device appearing (e.g. paired via the official app)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", "AA:BB:CC:DD:EE:FF")},
        manufacturer=MANUFACTURER,
        name="New Bedroom Sensor",
    )
    await hass.async_block_till_done()

    assert len(added) == 1
    assert isinstance(added[0], SensorPushVoltageSensor)
    assert added[0]._mac == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_new_device_no_duplicate_entity(hass, mock_coordinator):
    """Test that a device present at setup time doesn't get a second entity if the registry event fires."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", "AA:BB:CC:DD:EE:FF")},
        manufacturer=MANUFACTURER,
        name="Existing Sensor",
    )

    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
    assert len(added) == 1

    # A spurious update event for the same device should not create a second entity
    hass.bus.async_fire(
        "device_registry_updated",
        {"action": "create", "device_id": next(
            d.id for d in dev_reg.devices.values() if d.manufacturer == MANUFACTURER
        )},
    )
    await hass.async_block_till_done()

    assert len(added) == 1


@pytest.mark.asyncio
async def test_device_registry_listener_ignores_non_create_events(hass, mock_coordinator):
    """Test that update/remove events on the device registry don't create entities."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    hass.bus.async_fire("device_registry_updated", {"action": "update", "device_id": "irrelevant"})
    await hass.async_block_till_done()

    assert len(added) == 0


@pytest.mark.asyncio
async def test_device_registry_listener_ignores_non_sensorpush_devices(hass, mock_coordinator):
    """Test that a newly created device from a different manufacturer is ignored."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = mock_coordinator

    dev_reg = dr.async_get(hass)
    added = []
    await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("bluetooth", "AA:BB:CC:DD:EE:FF")},
        manufacturer="Govee",
        name="Not a SensorPush",
    )
    await hass.async_block_till_done()

    assert len(added) == 0