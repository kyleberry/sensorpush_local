from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DAILY_AUDIT_HOUR,
    CONF_MAX_RETRIES,
    DEFAULT_DAILY_AUDIT_HOUR,
    DEFAULT_MAX_RETRIES,
    DOMAIN,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    return {
        "options": {
            "daily_audit_hour": entry.options.get(
                CONF_DAILY_AUDIT_HOUR, DEFAULT_DAILY_AUDIT_HOUR
            ),
            "max_retries": entry.options.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES),
        },
        "coordinator": {
            "device_count": len(coordinator.data) if coordinator.data else 0,
            "audit_locked": coordinator.is_audit_locked(),
            "last_update_success": coordinator.last_update_success,
        },
        "devices": {
            mac: {
                "voltage": data.get("voltage"),
                "rssi_at_read": data.get("rssi"),
                "proxy_source": data.get("source"),
                "model_type": (
                    "Legacy (HT1)" if data.get("is_legacy") else "Modern (HT.w/HTP.xw)"
                ),
                "last_audit": data.get("timestamp"),
            }
            for mac, data in (coordinator.data or {}).items()
        },
    }
