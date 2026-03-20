import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from custom_components.sensorpush_local.const import DOMAIN
from .const import MOCK_MODEL_HTW, MOCK_MODEL_HT1, MOCK_BATT_860MV, MOCK_BATT_MALFORMED

@pytest.mark.asyncio
async def test_audit_timeout_handling(hass, mock_coordinator, caplog):
    """Test that a stalled GATT read triggers a TimeoutError and logs it."""
    coordinator = mock_coordinator

    async def stalled_read(*args, **kwargs):
        await asyncio.sleep(20)
        return b"\x00"

    with patch("custom_components.sensorpush_local.establish_connection") as mock_conn:
        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = stalled_read
        mock_conn.return_value.__aenter__.return_value = mock_client

        result = await coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Test Sensor")

        assert result == {}
        assert "Connection timeout" in caplog.text


@pytest.mark.asyncio
async def test_malformed_battery_payload(hass, mock_coordinator, caplog):
    """Test that a partial payload is rejected before unpacking."""
    coordinator = mock_coordinator

    with patch("custom_components.sensorpush_local.establish_connection") as mock_conn:
        mock_client = AsyncMock()
        mock_client.read_gatt_char.side_effect = [
            MOCK_MODEL_HT1, MOCK_BATT_MALFORMED]
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

    with patch("custom_components.sensorpush_local.establish_connection") as mock_conn:
        mock_client = AsyncMock()
        mock_conn.return_value.__aenter__.return_value = mock_client

        # CASE 1: HT1 (4-byte)
        mock_client.read_gatt_char.side_effect = [
            MOCK_MODEL_HT1, MOCK_BATT_860MV]
        res_ht1 = await coordinator.audit_device("AA:11", "HT1 Sensor")
        assert res_ht1["voltage"] == 3.0

        # CASE 2: HT.w (2-byte)
        mock_client.read_gatt_char.side_effect = [
            MOCK_MODEL_HTW, MOCK_BATT_860MV]
        res_htw = await coordinator.audit_device("BB:22", "HTw Sensor")
        assert res_htw["voltage"] == 0.86
