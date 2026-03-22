import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, MANUFACTURER

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up SensorPush entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    entities = []

    # Match existing SensorPush devices to our new native entities
    for device in [d for d in dev_reg.devices.values() if d.manufacturer == MANUFACTURER]:
        mac = next((i[1].upper()
                   for i in device.identifiers if i[0] == "bluetooth"), None)
        if mac:
            entities.append(SensorPushVoltageSensor(coordinator, device, mac))

    async_add_entities(entities)


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
        self._attr_unique_id = f"sp_{mac.replace(':', '').lower()}_volt_native"
        self._attr_device_info = DeviceInfo(identifiers=device.identifiers)

    @property
    def native_value(self):
        """Return the voltage from the last successful coordinator audit."""
        if not self.coordinator.data:
            return None
        device_data = self.coordinator.data.get(self._mac, {})
        return device_data.get("voltage")

    @property
    def extra_state_attributes(self):
        """Return the hardened audit attributes."""
        if not self.coordinator.data:
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
            "model_type": "Legacy (HT1)" if device_data.get("is_legacy") else "Modern (HT.w/HTP.xw)"
        }

    @property
    def available(self) -> bool:
        """Return True if the coordinator is healthy and this device has data."""
        if not super().available:
            return False
        if not self.coordinator.data:
            return True  # Audit pending after startup; not truly unavailable
        return self._mac in self.coordinator.data
