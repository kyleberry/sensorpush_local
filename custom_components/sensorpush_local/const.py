"""Constants for the SensorPush Local integration."""

DOMAIN = "sensorpush_local"
MANUFACTURER = "SensorPush"

# GATT Characteristics
CHAR_MODEL = "EF090002-11D6-42BA-93B8-9DD7EC090AA9"
CHAR_BATTERY = "EF090007-11D6-42BA-93B8-9DD7EC090AA9"

# Options keys and defaults
CONF_DAILY_AUDIT_HOUR = "daily_audit_hour"
CONF_MAX_RETRIES = "max_retries"
DEFAULT_DAILY_AUDIT_HOUR = 3
DEFAULT_MAX_RETRIES = 2
