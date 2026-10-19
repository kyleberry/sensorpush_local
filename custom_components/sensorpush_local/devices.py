"""Find the SensorPush devices this integration attaches its entities to.

Since Home Assistant 2026.8 a device belongs to exactly one config entry. The
devices for SensorPush sensors are owned by the core ``sensorpush`` integration;
this integration only links its entities to them and must never own devices
itself.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.helper_integration import async_remove_helper_devices

from .const import SENSORPUSH_DOMAIN

_LOGGER = logging.getLogger(__name__)


def mac_from_identifiers(identifiers) -> str | None:
    """Return the upper-case MAC from a device's ("bluetooth", mac) identifier."""
    return next(
        (str(i[1]).upper() for i in identifiers if i[0] == "bluetooth"),
        None,
    )


@callback
def async_get_source_devices(hass: HomeAssistant) -> list[tuple[dr.DeviceEntry, str]]:
    """Return (device, mac) for every device owned by a core sensorpush entry."""
    dev_reg = dr.async_get(hass)
    devices = []
    for sp_entry in hass.config_entries.async_entries(SENSORPUSH_DOMAIN):
        for device in dr.async_entries_for_config_entry(dev_reg, sp_entry.entry_id):
            if mac := mac_from_identifiers(device.identifiers):
                devices.append((device, mac))
    return devices


@callback
def async_remove_duplicate_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove devices this integration owns and relink its entities.

    HA 2026.8 split every device that was shared with the core sensorpush
    integration into one copy per config entry, so each sensor showed up twice.
    Earlier versions of this integration also created such copies directly via
    DeviceInfo. Relink our entities to the core device and delete the copies.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    own_devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)

    for device, _mac in async_get_source_devices(hass):
        # Other integrations may have linked entities to our copy — e.g. after
        # the 2026.8 split, Battery Notes' entities ended up on it next to our
        # voltage sensor. async_remove_helper_devices only relinks *our*
        # entities and HA detaches the rest when the device is removed, so
        # move every entity on the copy to the core device first.
        for duplicate in own_devices:
            if not (
                duplicate.identifiers & device.identifiers
                or duplicate.connections & device.connections
            ):
                continue
            for entity in er.async_entries_for_device(
                ent_reg, duplicate.id, include_disabled_entities=True
            ):
                if entity.config_entry_id != entry.entry_id:
                    _LOGGER.info(
                        "Moving %s from duplicate device %s to %s",
                        entity.entity_id,
                        duplicate.id,
                        device.id,
                    )
                    ent_reg.async_update_entity(entity.entity_id, device_id=device.id)

        async_remove_helper_devices(
            hass,
            helper_config_entry_id=entry.entry_id,
            source_device_id=device.id,
        )

    # Anything still owned by this entry has no matching core device (the
    # sensor was removed from the sensorpush integration). Removing the device
    # also removes our entities that were linked to it.
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        _LOGGER.info(
            "Removing orphaned SensorPush Local device %s (%s)",
            device.name,
            device.id,
        )
        dev_reg.async_remove_device(device.id)
