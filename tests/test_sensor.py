import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from custom_components.sensorpush_local.const import DOMAIN
from .const import MOCK_MODEL_HTW, MOCK_MODEL_HT1, MOCK_BATT_860MV, MOCK_BATT_MALFORMED

@pytest.mark.asyncio
async def test_audit_timeout_handling(hass, mock_coordinator, caplog):
    """Test that a stalled GATT read triggers a TimeoutError and logs it."""
    coordinator = mock_coordinator

    # Mock a device so we get past the "not found" check
    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    # Patch the lookup AND the connection
    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn:

        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = asyncio.TimeoutError
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Test Sensor")
        assert result == {}
        assert "Connection timeout" in caplog.text

@pytest.mark.asyncio
async def test_malformed_battery_payload(hass, mock_coordinator, caplog):
    """Test that a partial payload is rejected."""
    coordinator = mock_coordinator
    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
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
    """Test that HT1 and HT.w use different math."""
    coordinator = mock_coordinator

    # 1. Create a reusable mock BLE device that Home Assistant's bluetooth component would return
    def create_mock_ble(mac_addr):
        mock_ble = MagicMock()
        mock_ble.address = mac_addr
        mock_ble.rssi = -60
        mock_ble.details = {"source": "hci0"}
        return mock_ble

    # 2. Patch BOTH the bluetooth lookup and the connection establishment
    mock_scanner = MagicMock()
    mock_scanner.name = "Living Room Hub"

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address") as mock_bt_lookup, \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("custom_components.sensorpush_local.bluetooth.async_scanner_by_source", return_value=mock_scanner):

        mock_client = AsyncMock()
        mock_conn.return_value.__aenter__.return_value = mock_client

        # --- CASE 1: HT1 (Legacy/4-byte) ---
        mac_ht1 = "AA:11"
        mock_bt_lookup.return_value = create_mock_ble(mac_ht1)

        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HT1, MOCK_BATT_860MV]

        res_ht1 = await coordinator.audit_device(mac_ht1, "HT1 Sensor")

        # Verify Ranch Math: (860 + 2140) / 1000 = 3.0
        assert res_ht1["voltage"] == 3.0
        assert res_ht1["is_legacy"] is True
        assert res_ht1["source"] == "Living Room Hub"

        # --- CASE 2: HT.w (Modern/2-byte) ---
        mac_htw = "BB:22"
        mock_bt_lookup.return_value = create_mock_ble(mac_htw)

        # Reset the mock for the second call
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HTW, MOCK_BATT_860MV]

        res_htw = await coordinator.audit_device(mac_htw, "HTw Sensor")

        # Verify Modern Math: 860 / 1000 = 0.86
        assert res_htw["voltage"] == 0.86
        assert res_htw["is_legacy"] is False


@pytest.mark.asyncio
async def test_source_falls_back_to_raw_when_scanner_not_found(hass, mock_coordinator):
    """Test that source falls back to raw identifier when scanner lookup returns None."""
    mock_ble = MagicMock()
    mock_ble.address = "AA:11"
    mock_ble.rssi = -70
    mock_ble.details = {"source": "hci0"}

    with patch("custom_components.sensorpush_local.bluetooth.async_ble_device_from_address", return_value=mock_ble), \
         patch("custom_components.sensorpush_local.establish_connection") as mock_conn, \
         patch("custom_components.sensorpush_local.bluetooth.async_scanner_by_source", return_value=None):

        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = [MOCK_MODEL_HTW, MOCK_BATT_860MV]
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await mock_coordinator.audit_device("AA:11", "Test Sensor")

    assert result["source"] == "hci0"
