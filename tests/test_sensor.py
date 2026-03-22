import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from custom_components.sensorpush_local.const import DOMAIN
from .const import MOCK_MODEL_HTW, MOCK_MODEL_HT1, MOCK_BATT_860MV, MOCK_BATT_MALFORMED


def _mock_service_info(source="hci0", rssi=-60):
    """Return a minimal BluetoothServiceInfo mock."""
    si = MagicMock()
    si.source = source
    si.rssi = rssi
    return si


@pytest.mark.asyncio
async def test_audit_timeout_exhausted_after_retries(hass, mock_coordinator, caplog):
    """Test that all retry attempts are made and the final timeout is logged."""
    coordinator = mock_coordinator

    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.bluetooth.async_last_service_info", return_value=_mock_service_info()), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("asyncio.sleep") as mock_sleep:

        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = asyncio.TimeoutError
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Test Sensor")
        assert result == {}
        assert "Connection timeout" in caplog.text
        # All 3 attempts made, 2 sleeps between them
        assert mock_conn.call_count == 3
        assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_retry_succeeds_on_second_attempt(hass, mock_coordinator, caplog):
    """Test that a timeout on the first attempt is retried and succeeds."""
    from tests.const import MOCK_MODEL_HTW, MOCK_BATT_860MV
    coordinator = mock_coordinator

    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    mock_scanner = MagicMock()
    mock_scanner.name = "Living Room Hub"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.bluetooth.async_last_service_info", return_value=_mock_service_info()), \
         patch("custom_components.sensorpush_local.bluetooth.async_scanner_by_source", return_value=mock_scanner), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("asyncio.sleep") as mock_sleep:

        mock_client = AsyncMock()
        # First read_gatt_char call times out; second attempt returns valid data
        mock_client.read_gatt_char.side_effect = [
            asyncio.TimeoutError,   # attempt 1: model char times out
            MOCK_MODEL_HTW,         # attempt 2: model char OK
            MOCK_BATT_860MV,        # attempt 2: battery char OK
        ]
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Test Sensor")

        assert result["voltage"] == 0.86
        assert mock_conn.call_count == 2
        assert mock_sleep.call_count == 1
        assert "retrying" in caplog.text


@pytest.mark.asyncio
async def test_malformed_battery_payload(hass, mock_coordinator, caplog):
    """Test that a partial payload is rejected."""
    coordinator = mock_coordinator
    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.bluetooth.async_last_service_info", return_value=_mock_service_info()), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn:

        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HT1, MOCK_BATT_MALFORMED]
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Kitchen Sensor")
        assert result == {}
        assert "Malformed battery payload" in caplog.text


@pytest.mark.asyncio
async def test_coordinator_lock_contention(hass, mock_coordinator, caplog):
    """Test the lock guard using the helper method."""
    coordinator = mock_coordinator

    with patch.object(coordinator, "is_audit_locked", return_value=True):
        result = await coordinator.audit_device("AA:11", "Locked Sensor")

        assert result == {}
        assert "deferred: Lock is held" in caplog.text


@pytest.mark.asyncio
async def test_model_detection_logic(hass, mock_coordinator):
    """Test that HT1 and HT.w use different math, and that RSSI/source come from service_info."""
    coordinator = mock_coordinator

    def create_mock_ble(mac_addr):
        mock_ble = MagicMock()
        mock_ble.address = mac_addr
        return mock_ble

    mock_scanner = MagicMock()
    mock_scanner.name = "Living Room Hub"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address") as mock_bt_lookup, \
         patch("custom_components.sensorpush_local.bluetooth.async_last_service_info", return_value=_mock_service_info(source="hci0", rssi=-60)), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("custom_components.sensorpush_local.bluetooth.async_scanner_by_source", return_value=mock_scanner):

        mock_client = AsyncMock()
        mock_conn.return_value.__aenter__.return_value = mock_client

        # --- CASE 1: HT1 (Legacy/4-byte) ---
        mac_ht1 = "AA:11"
        mock_bt_lookup.return_value = create_mock_ble(mac_ht1)
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HT1, MOCK_BATT_860MV]

        res_ht1 = await coordinator.audit_device(mac_ht1, "HT1 Sensor")

        assert res_ht1["voltage"] == 3.0
        assert res_ht1["is_legacy"] is True
        assert res_ht1["rssi"] == -60
        assert res_ht1["source"] == "Living Room Hub"

        # --- CASE 2: HT.w (Modern/2-byte) ---
        mac_htw = "BB:22"
        mock_bt_lookup.return_value = create_mock_ble(mac_htw)
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HTW, MOCK_BATT_860MV]

        res_htw = await coordinator.audit_device(mac_htw, "HTw Sensor")

        assert res_htw["voltage"] == 0.86
        assert res_htw["is_legacy"] is False


@pytest.mark.asyncio
async def test_source_and_rssi_fallback_when_service_info_none(hass, mock_coordinator):
    """Test that source falls back to ble_device.details and rssi is None when service_info is unavailable."""
    mock_ble = MagicMock()
    mock_ble.address = "AA:11"
    mock_ble.details = {"source": "hci0"}

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.bluetooth.async_last_service_info", return_value=None), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("custom_components.sensorpush_local.bluetooth.async_scanner_by_source", return_value=None):

        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HTW, MOCK_BATT_860MV]
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await mock_coordinator.audit_device("AA:11", "Test Sensor")

    assert result["rssi"] is None
    assert result["source"] == "hci0"
