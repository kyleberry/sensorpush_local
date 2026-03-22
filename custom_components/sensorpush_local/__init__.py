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

from .const import DOMAIN, CHAR_BATTERY, CHAR_MODEL, MANUFACTURER

_LOGGER = logging.getLogger(__name__)

_MAX_AUDIT_RETRIES = 2    # retries after first failure (3 total attempts)
_RETRY_DELAY_SECS = 10    # seconds between retry attempts


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SensorPush Local from a config entry."""
    coordinator = SensorPushCoordinator(hass, entry)

    # Store the coordinator for the sensors to use
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Set up the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    # Register the manual audit service
    async def handle_manual_audit(call):
        _LOGGER.info("Manual SensorPush Local Audit triggered")
        await coordinator.async_refresh()

    hass.services.async_register(DOMAIN, "run_audit", handle_manual_audit)

    # Run the initial audit in the background so HA startup is not blocked.
    # GATT connections can take 10-45s per device; blocking setup causes the
    # stage 2 bootstrap timeout to fire on systems with multiple sensors.
    entry.async_create_background_task(
        hass,
        coordinator.async_refresh(),
        "sensorpush_local_initial_audit",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.services.async_remove(DOMAIN, "run_audit")
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
        if self.lock.locked():
            _LOGGER.debug("Audit already in progress — skipping concurrent refresh to preserve existing data.")
            return self.data

        from homeassistant.helpers import device_registry as dr

        dev_reg = dr.async_get(self.hass)
        # Carry forward last-known data; only overwrite on successful audit
        new_data = dict(self.data or {})

        # Find all devices from the 'SensorPush' manufacturer
        sensor_devices = [d for d in dev_reg.devices.values() if d.manufacturer == MANUFACTURER]

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
        """Perform a GATT audit, retrying on timeout up to _MAX_AUDIT_RETRIES times.

        The lock is released between retry attempts so that other devices in the
        audit queue are not blocked during the backoff sleep.  Each attempt calls
        async_ble_device_from_address fresh, so a retry may be routed to a
        different (now-free) proxy than the one that timed out.
        """
        max_attempts = _MAX_AUDIT_RETRIES + 1

        for attempt in range(1, max_attempts + 1):
            if self.is_audit_locked():
                _LOGGER.debug("Audit for %s (%s) deferred: Lock is held...", name, mac)
                return {}

            timed_out = False
            async with self.lock:
                ble_device = bluetooth.async_ble_device_from_address(self.hass, mac, connectable=True)
                if not ble_device:
                    _LOGGER.debug("Device %s (%s) not found by any proxies.", mac, name)
                    return {}

                # Capture pre-connection advertisement data for RSSI and source.
                # BLEDevice.rssi was removed in newer bleak/habluetooth; service_info
                # is the correct way to obtain it in HA.
                service_info = bluetooth.async_last_service_info(self.hass, mac, connectable=True)

                try:
                    async with await establish_connection(BleakClient, ble_device, name, timeout=45.0) as client:
                        # Read GATT chars
                        res_model = await asyncio.wait_for(client.read_gatt_char(CHAR_MODEL), 10.0)
                        res_batt = await asyncio.wait_for(client.read_gatt_char(CHAR_BATTERY), 10.0)

                        if len(res_batt) != 4:
                            _LOGGER.error("Malformed battery payload from %s: %d bytes", name, len(res_batt))
                            return {}

                        # v_raw: millivolts; t_at_read: raw uint16 from device (units device-dependent)
                        v_raw, t_at_read = struct.unpack('<HH', res_batt)
                        is_legacy = (len(res_model) == 4)

                        voltage = (float(v_raw) + 2140.0) / 1000.0 if is_legacy else float(v_raw) / 1000.0

                        source = service_info.source if service_info else (ble_device.details or {}).get("source", "unknown")
                        scanner = bluetooth.async_scanner_by_source(self.hass, source)
                        source_name = scanner.name if (scanner and scanner.name) else source

                        return {
                            "voltage": round(voltage, 3),
                            "rssi": service_info.rssi if service_info else None,
                            "raw_v": v_raw,
                            "temp_at_read": t_at_read,
                            "is_legacy": is_legacy,
                            "source": source_name,
                            "timestamp": dt_util.utcnow().isoformat()
                        }

                except asyncio.TimeoutError:
                    timed_out = True
                    if attempt < max_attempts:
                        _LOGGER.warning(
                            "Timeout for %s (%s) — attempt %d/%d, retrying in %ds",
                            name, mac, attempt, max_attempts, _RETRY_DELAY_SECS,
                        )
                    else:
                        _LOGGER.warning(
                            "Connection timeout for %s (%s) — all %d attempts exhausted.",
                            name, mac, max_attempts,
                        )
                except Exception as err:
                    _LOGGER.error("Audit error for %s: %s - %s", name, type(err).__name__, err)
                    return {}

            # Lock released. Wait before retry so the proxy has time to free up
            # and HA may select a different proxy on the next attempt.
            if timed_out and attempt < max_attempts:
                await asyncio.sleep(_RETRY_DELAY_SECS)

        return {}
