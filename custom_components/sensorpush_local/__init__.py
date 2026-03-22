import logging
import asyncio
import struct
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components import bluetooth
from homeassistant.util import dt as dt_util

from bleak_retry_connector import establish_connection, BleakClientWithServiceCache as BleakClient

from .const import DOMAIN, CHAR_BATTERY, CHAR_MODEL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SensorPush Local from a config entry."""
    coordinator = SensorPushCoordinator(hass, entry)

    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator for the sensors to use
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Register the manual audit service
    async def handle_manual_audit(call):
        _LOGGER.info("Manual SensorPush Local Audit triggered")
        # This tells the coordinator to refresh all entities it manages
        await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "run_audit", handle_manual_audit)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class SensorPushCoordinator(DataUpdateCoordinator):
    """Manage Bluetooth audits centrally with a global lock."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=24),
            config_entry=entry,
        )
        self.lock = asyncio.Lock()
        self.data = {}

    def is_audit_locked(self) -> bool:
        """Check if the shared lock is currently held."""
        return self.lock.locked()

    async def _async_update_data(self):
        """Fetch data for all registered SensorPush devices in a serial loop."""
        from homeassistant.helpers import device_registry as dr

        dev_reg = dr.async_get(self.hass)
        new_data = {}

        # Find all devices from the 'SensorPush' manufacturer
        sensor_devices = [d for d in dev_reg.devices.values() if d.manufacturer == "SensorPush"]

        for device in sensor_devices:
            mac = next((i[1].upper() for i in device.identifiers if i[0] == "bluetooth"), None)
            if not mac:
                continue

            name = device.name_by_user or device.name or "Unknown Sensor"

            # Perform the GATT audit
            result = await self.audit_device(mac, name)

            if result:
                new_data[mac] = result

        return new_data

    async def audit_device(self, mac: str, name: str):
        """Perform a single GATT audit using the shared lock."""
        # 1. Immediate exit if another sensor is currently auditing
        if self.is_audit_locked():
            _LOGGER.debug(f"Audit for {name} ({mac}) deferred: Lock is held...")
            return {}

        async with self.lock:
            ble_device = bluetooth.async_ble_device_from_address(self.hass, mac, connectable=True)
            if not ble_device:
                _LOGGER.debug(f"Device {mac} ({name}) not found by any proxies.")
                return {}

            try:
                async with await establish_connection(BleakClient, ble_device, name, timeout=45.0) as client:
                    # Read GATT chars
                    res_model = await asyncio.wait_for(client.read_gatt_char(CHAR_MODEL), 10.0)
                    res_batt = await asyncio.wait_for(client.read_gatt_char(CHAR_BATTERY), 10.0)

                    if len(res_batt) != 4:
                        _LOGGER.error(f"Malformed battery payload from {name}: {len(res_batt)} bytes")
                        return {}

                    v_raw, t_at_read = struct.unpack('<HH', res_batt)
                    is_legacy = (len(res_model) == 4)

                    voltage = (float(v_raw) + 2140.0) / 1000.0 if is_legacy else float(v_raw) / 1000.0

                    return {
                        "voltage": round(voltage, 3),
                        "rssi": ble_device.rssi,
                        "raw_v": v_raw,
                        "temp_at_read": t_at_read,
                        "is_legacy": is_legacy,
                        "source": ble_device.details.get("source", "unknown"),
                        "timestamp": dt_util.utcnow().isoformat()
                    }

            except asyncio.TimeoutError:
                _LOGGER.warning(f"Connection timeout for {name} ({mac}).")
            except Exception as err:
                _LOGGER.error(f"Audit error for {name}: {type(err).__name__} - {err}")

            return {}
