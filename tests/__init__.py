import asyncio
import logging
import struct
from datetime import timedelta

from bleak_retry_connector import BleakClientWithServiceCache as BleakClient
from bleak_retry_connector import (
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CHAR_BATTERY, CHAR_MODEL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SensorPush Local from a config entry."""
    coordinator = SensorPushCoordinator(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    async def handle_manual_audit(call):  # pylint: disable=unused-argument
        _LOGGER.info("Manual SensorPush Local Audit triggered")
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

    def __init__(self, hass: HomeAssistant):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=24),
        )
        self.lock = asyncio.Lock()

    async def audit_device(self, mac: str, name: str):
        """Perform a single GATT audit using the shared lock."""
        if self.lock.locked():
            _LOGGER.debug("Audit for %s deferred: Lock is held...", mac)
            return {}

        async with self.lock:
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, mac, connectable=True
            )
            if not ble_device:
                _LOGGER.debug("Device %s (%s) not found by any proxies.", mac, name)
                return {}

            try:
                async with await establish_connection(
                    BleakClient, ble_device, name, timeout=45.0
                ) as client:
                    res_model = await asyncio.wait_for(
                        client.read_gatt_char(CHAR_MODEL), 10.0
                    )
                    res_batt = await asyncio.wait_for(
                        client.read_gatt_char(CHAR_BATTERY), 10.0
                    )

                    if len(res_batt) != 4:
                        _LOGGER.error(
                            "Malformed battery payload from %s: %d bytes",
                            name,
                            len(res_batt),
                        )
                        return {}

                    v_raw, t_at_read = struct.unpack("<HH", res_batt)
                    is_legacy = len(res_model) == 4
                    voltage = (
                        (float(v_raw) + 2140.0) / 1000.0
                        if is_legacy
                        else float(v_raw) / 1000.0
                    )

                    return {
                        "voltage": round(voltage, 3),
                        "rssi": ble_device.rssi,
                        "raw_v": v_raw,
                        "temp_at_read": t_at_read,
                        "source": ble_device.details.get("source", "unknown"),
                        "timestamp": dt_util.utcnow().isoformat(),
                        "is_legacy": is_legacy,
                    }

            except asyncio.TimeoutError:
                _LOGGER.warning("Connection timeout for %s (%s).", name, mac)
            except Exception as err:  # pylint: disable=broad-exception-caught
                _LOGGER.error(
                    "Audit error for %s: %s - %s", name, type(err).__name__, err
                )

            return {}

    async def _async_update_data(self):
        """Mandatory for Coordinator but we use audit_device manually."""
        return {}
