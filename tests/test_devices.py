# pylint: disable=redefined-outer-name,unused-argument
"""Device ownership tests against the real device and entity registries.

Since HA 2026.8 a device belongs to one config entry. The core sensorpush
integration owns the devices; this integration must only link to them.
"""

from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensorpush_local.const import DOMAIN

from .const import MANUFACTURER

MAC = "AA:BB:CC:DD:EE:FF"
UNIQUE_ID = "sp_aabbccddeeff_volt_native"


@pytest.fixture
def our_entry(hass, enable_custom_integrations):
    """The sensorpush_local config entry."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="local_entry_id", data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def core_device(hass, sp_entry):
    """A SensorPush device owned by the core sensorpush integration."""
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=sp_entry.entry_id,
        identifiers={("bluetooth", MAC)},
        connections={(dr.CONNECTION_BLUETOOTH, MAC)},
        manufacturer=MANUFACTURER,
        name="Kitchen",
    )


async def _setup(hass, entry):
    # No BLE device is reachable, so the background audit exits immediately.
    with patch(
        "custom_components.sensorpush_local.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_fresh_install_links_entity_to_core_device(hass, our_entry, core_device):
    """A new entity is linked to the core device and no device is created."""
    await _setup(hass, our_entry)

    ent_reg = er.async_get(hass)
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, UNIQUE_ID)
    assert entity_id is not None
    assert ent_reg.async_get(entity_id).device_id == core_device.id
    assert not dr.async_entries_for_config_entry(dr.async_get(hass), our_entry.entry_id)
    assert hass.states.get(entity_id).name == "Kitchen Battery Voltage"


async def test_setup_removes_duplicate_device_and_keeps_entity(
    hass, our_entry, core_device
):
    """A duplicate device owned by us (left by the 2026.8 split) is removed.

    The existing entity, including a user-customized entity_id, moves to the
    core device.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    duplicate = dev_reg.async_get_or_create(
        config_entry_id=our_entry.entry_id,
        identifiers={("bluetooth", MAC)},
        manufacturer=MANUFACTURER,
        name="Kitchen",
    )
    assert duplicate.id != core_device.id
    ent_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        UNIQUE_ID,
        config_entry=our_entry,
        device_id=duplicate.id,
        suggested_object_id="kitchen_battery_custom",
    )

    await _setup(hass, our_entry)

    assert dev_reg.async_get(duplicate.id) is None
    assert not dr.async_entries_for_config_entry(dev_reg, our_entry.entry_id)
    entry = ent_reg.async_get("sensor.kitchen_battery_custom")
    assert entry is not None
    assert entry.unique_id == UNIQUE_ID
    assert entry.device_id == core_device.id


async def test_setup_removes_orphaned_device(hass, our_entry):
    """A device we own with no matching core device is removed with its entity."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    orphan = dev_reg.async_get_or_create(
        config_entry_id=our_entry.entry_id,
        identifiers={("bluetooth", MAC)},
        name="Gone",
    )
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, UNIQUE_ID, config_entry=our_entry, device_id=orphan.id
    )

    await _setup(hass, our_entry)

    assert dev_reg.async_get(orphan.id) is None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, UNIQUE_ID) is None


async def test_core_device_removed_removes_entity(hass, our_entry, core_device):
    """Removing the sensor from the core integration removes our entity too."""
    await _setup(hass, our_entry)
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, UNIQUE_ID) is not None

    dr.async_get(hass).async_remove_device(core_device.id)
    await hass.async_block_till_done()

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, UNIQUE_ID) is None


async def test_removed_device_with_other_core_copy_keeps_entity(
    hass, our_entry, core_device
):
    """A removed device whose MAC still has a core device keeps the entity."""
    await _setup(hass, our_entry)
    ent_reg = er.async_get(hass)

    other_entry = MockConfigEntry(domain="govee_ble", data={})
    other_entry.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    other = dev_reg.async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("bluetooth", MAC)}
    )
    dev_reg.async_remove_device(other.id)
    await hass.async_block_till_done()

    assert ent_reg.async_get_entity_id("sensor", DOMAIN, UNIQUE_ID) is not None
