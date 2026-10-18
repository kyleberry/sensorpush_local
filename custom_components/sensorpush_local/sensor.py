import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import EVENT_DEVICE_REGISTRY_UPDATED
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSORPUSH_DOMAIN
from .devices import async_get_source_devices, mac_from_identifiers

_LOGGER = logging.getLogger(__name__)


def _unique_id(mac: str) -> str:
    return f"sp_{mac.replace(':', '').lower()}_volt_native"


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up SensorPush entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    ent_reg = async_get_entity_registry(hass)

    async_add_entities(
        [
            SensorPushVoltageSensor(coordinator, device, mac)
            for device, mac in async_get_source_devices(hass)
        ]
    )

    @callback
    def _handle_device_added(device_id):
        # (device, None) when the device isn't owned by a sensorpush entry
        device, sp_entry = dr.async_get_device_and_config_entry_for_domain(
            hass, device_id, domain=SENSORPUSH_DOMAIN, include_child_devices=False
        )
        if device is None or sp_entry is None:
            return
        mac = mac_from_identifiers(device.identifiers)
        if not mac:
            return
        if ent_reg.async_get_entity_id("sensor", DOMAIN, _unique_id(mac)):
            return
        async_add_entities([SensorPushVoltageSensor(coordinator, device, mac)])

    @callback
    def _handle_device_removed(device_dict):
        mac = mac_from_identifiers(tuple(i) for i in device_dict.get("identifiers", ()))
        if not mac:
            return
        # Only drop our entity once no core SensorPush device has this MAC
        if any(m == mac for _d, m in async_get_source_devices(hass)):
            return
        # Defer: HA is still dispatching the entity registry update that
        # detaches our entity from the removed device, and removing the entity
        # mid-dispatch makes that update fail.
        hass.loop.call_soon(_remove_entity, mac)

    @callback
    def _remove_entity(mac):
        if entity_id := ent_reg.async_get_entity_id("sensor", DOMAIN, _unique_id(mac)):
            _LOGGER.info("SensorPush device %s removed; removing %s", mac, entity_id)
            ent_reg.async_remove(entity_id)

    @callback
    def _handle_device_registry_update(event):
        action = event.data.get("action")
        if action == "create":
            _handle_device_added(event.data["device_id"])
        elif action == "remove":
            _handle_device_removed(event.data.get("device") or {})

    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_DEVICE_REGISTRY_UPDATED, _handle_device_registry_update
        )
    )


class SensorPushVoltageSensor(CoordinatorEntity, SensorEntity):
    """Native Voltage Sensor pulling from the central Coordinator."""

    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "V"
    _attr_has_entity_name = True
    _attr_name = "Battery Voltage"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, device, mac):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = _unique_id(mac)
        # Link to the core sensorpush device instead of declaring DeviceInfo.
        # Since HA 2026.8, DeviceInfo always creates a device owned by *this*
        # config entry, which shows up as a duplicate of the sensor.
        self.device_entry = device

    @property
    def native_value(self):
        """Return the voltage from the last successful coordinator audit."""
        if self.coordinator.data is None:
            return None
        device_data = self.coordinator.data.get(self._mac, {})
        return device_data.get("voltage")

    @property
    def extra_state_attributes(self):
        """Return the hardened audit attributes."""
        if self.coordinator.data is None:
            return {}
        device_data = self.coordinator.data.get(self._mac, {})

        if not device_data:
            return {}

        return {
            "rssi_at_read": device_data.get("rssi"),
            "proxy_source": device_data.get("source"),
            "raw_value": device_data.get("raw_v"),
            "temp_at_read": device_data.get("temp_at_read"),
            "last_audit": device_data.get("timestamp"),
            "model_type": (
                "Legacy (HT1)"
                if device_data.get("is_legacy")
                else "Modern (HT.w/HTP.xw)"
            ),
        }

    @property
    def available(self) -> bool:
        """Return True if the coordinator is healthy and this device has data."""
        if not super().available:
            return False
        if self.coordinator.data is None:
            return True  # Audit pending after startup; not truly unavailable
        return self._mac in self.coordinator.data
