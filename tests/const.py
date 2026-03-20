"""Constants for SensorPush Local tests."""

DOMAIN = "sensorpush_local"

# GATT Characteristics
CHAR_BATTERY = "ef090007-11d6-42ba-93b8-9DD7EC090AA9"
CHAR_MODEL = "ef090002-11d6-42ba-93b8-9DD7EC090AA9"

# Model IDs
MOCK_MODEL_HT1 = b"\x01\x02\x03\x04"
MOCK_MODEL_HTW = b"\x01\x02"

# Battery Payloads (Little Endian)
# 860mV raw -> 0x035C
MOCK_BATT_860MV = b"\x5c\x03\x00\x00"

# 3180mV raw -> 0x0C6C
MOCK_BATT_3180MV = b"\x6c\x0c\x00\x00"

# Malformed
MOCK_BATT_MALFORMED = b"\x5c\x03"
