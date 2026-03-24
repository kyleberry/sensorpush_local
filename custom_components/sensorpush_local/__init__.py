import logging
import asyncio
import struct
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_change
from homeassistant.components import bluetooth
from homeassistant.util import dt as dt_util

from bleak import BleakError
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache as BleakClient

from .const import (
    DOMAIN, CHAR_BATTERY, CHAR_MODEL, MANUFACTURER,
    CONF_DAILY_AUDIT_HOUR, CONF_MAX_RETRIES,
    DEFAULT_DAILY_AUDIT_HOUR, DEFAULT_MAX_RETRIES,
)

_LOGGER = logging.getLogger(__name__)

_RETRY_DELAY_SECS = 10    # seconds between retry attempts
_STORAGE_KEY = f"{DOMAIN}.data"
_STORAGE_VERSION = 1


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SensorPush Local from a config entry."""
    coordinator = SensorPushCoordinator(hass, entry)

    # Seed coordinator with last-known values so entities are not "Unavailable"
    # immediately after a restart while the background audit is still running.
    await coordinator.async_load_persisted_data()

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

    # Schedule the recurring daily audit at the configured hour.
    daily_hour = entry.options.get(CONF_DAILY_AUDIT_HOUR, DEFAULT_DAILY_AUDIT_HOUR)

    def _handle_daily_audit(_now):
        _LOGGER.info("Scheduled daily SensorPush Local audit firing (hour=%d)", daily_hour)
        hass.async_create_task(
            coordinator.async_refresh(),
            "sensorpush_local_daily_audit",
        )

    coordinator._unsub_daily_audit = async_track_time_change(
        hass, _handle_daily_audit, hour=int(daily_hour), minute=0, second=0
    )

    # Reload the entry when options change so the new schedule/retry values take effect.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator._unsub_daily_audit:
            coordinator._unsub_daily_audit()
        hass.services.async_remove(DOMAIN, "run_audit")
    return unload_ok


class SensorPushCoordinator(DataUpdateCoordinator):
    """Manage Bluetooth audits centrally with a global lock."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,
            config_entry=entry,
        )
        self.lock = asyncio.Lock()
        self.data = {}
        self._store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._unsub_daily_audit = None

    def is_audit_locked(self) -> bool:
        """Check if the shared lock is currently held."""
        return self.lock.locked()

    async def async_load_persisted_data(self):
        """Seed coordinator data from storage so entities survive a restart."""
        stored = await self._store.async_load()
        if stored:
            self.data = stored
            _LOGGER.debug("Loaded persisted data for %d device(s)", len(stored))

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

        updated = 0
        for device in sensor_devices:
            mac = next((i[1].upper() for i in device.identifiers if i[0] == "bluetooth"), None)
            if not mac:
                continue

            name = device.name_by_user or device.name or "Unknown Sensor"

            # Perform the GATT audit
            result = await self.audit_device(mac, name)

            if result:
                new_data[mac] = result
                updated += 1

        _LOGGER.info("SensorPush Local audit complete — %d/%d device(s) updated", updated, len(sensor_devices))
        await self._store.async_save(new_data)
        return new_data

    async def audit_device(self, mac: str, name: str):
        """Perform a GATT audit, retrying on timeout or BLE errors.

        Retry count is read from entry options at call time (default: DEFAULT_MAX_RETRIES).
        The lock is released between retry attempts so that other devices in the
        audit queue are not blocked during the backoff sleep.  Each attempt calls
        async_ble_device_from_address fresh, so a retry may be routed to a
        different (now-free) proxy than the one that failed.
        """
        max_retries = self.config_entry.options.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES)
        max_attempts = int(max_retries) + 1

        for attempt in range(1, max_attempts + 1):
            should_retry = False
            if self.is_audit_locked():
                _LOGGER.debug("Audit for %s (%s) deferred: Lock is held...", name, mac)
                return {}

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
                    should_retry = True
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
                except BleakError as err:
                    should_retry = True
                    if attempt < max_attempts:
                        _LOGGER.warning(
                            "BLE error for %s (%s): %s — attempt %d/%d, retrying in %ds",
                            name, mac, err, attempt, max_attempts, _RETRY_DELAY_SECS,
                        )
                    else:
                        _LOGGER.warning(
                            "BLE error for %s (%s): %s — all %d attempts exhausted.",
                            name, mac, err, max_attempts,
                        )
                except Exception as err:
                    _LOGGER.error("Audit error for %s: %s - %s", name, type(err).__name__, err)
                    return {}

            # Lock released. Wait before retry so the proxy has time to free up
            # and HA may select a different proxy on the next attempt.
            if should_retry and attempt < max_attempts:
                await asyncio.sleep(_RETRY_DELAY_SECS)

        return {}
