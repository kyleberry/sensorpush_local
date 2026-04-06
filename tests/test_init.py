# pylint: disable=unused-argument,protected-access
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sensorpush_local import async_setup_entry, async_unload_entry
from custom_components.sensorpush_local.const import DOMAIN, MANUFACTURER


@pytest.mark.asyncio
async def test_run_audit_service(hass, mock_coordinator):
    """Test that calling the run_audit service triggers a coordinator refresh."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)

    # 1. Set the state to SETUP_IN_PROGRESS so the coordinator allows the refresh
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)

    # 2. Link them up
    mock_coordinator.config_entry = mock_entry

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch.object(mock_entry, "async_create_background_task"),
    ):

        await async_setup_entry(hass, mock_entry)
        mock_coordinator.async_refresh.reset_mock()

        # Verify service call triggers refresh
        await hass.services.async_call(DOMAIN, "run_audit", blocking=True)
        mock_coordinator.async_refresh.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_concurrent_refresh_preserves_data(hass, mock_coordinator, caplog):
    """Test that a concurrent _async_update_data call returns existing data unchanged."""
    coordinator = mock_coordinator
    existing_data = {
        "AA:BB:CC:DD:EE:FF": {
            "voltage": 3.021,
            "rssi": -60,
            "is_legacy": True,
            "source": "hci0",
            "raw_v": 881,
            "temp_at_read": 22,
            "timestamp": "2026-03-21T22:00:00",
        }
    }
    coordinator.data = existing_data

    # Simulate the lock being held by another audit in progress
    async with coordinator.lock:
        result = await coordinator._async_update_data()

    assert result == existing_data
    assert "skipping concurrent refresh" in caplog.text


@pytest.mark.asyncio
async def test_unload_entry(hass, mock_coordinator):
    """Test that unloading removes the coordinator and service."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mock_coordinator.config_entry = mock_entry

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            return_value=True,
        ),
        patch.object(mock_entry, "async_create_background_task"),
    ):

        await async_setup_entry(hass, mock_entry)
        assert DOMAIN in hass.data
        assert hass.services.has_service(DOMAIN, "run_audit")

        await async_unload_entry(hass, mock_entry)
        assert mock_entry.entry_id not in hass.data.get(DOMAIN, {})
        assert not hass.services.has_service(DOMAIN, "run_audit")


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_initial_audit_scheduled_as_background_task(hass, mock_coordinator):
    """Test that setup schedules the initial audit as a background task, not blocking startup."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mock_coordinator.config_entry = mock_entry

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch.object(mock_entry, "async_create_background_task") as mock_bg_task,
    ):

        await async_setup_entry(hass, mock_entry)

        # Verify a background task was scheduled with the expected name
        mock_bg_task.assert_called_once()
        _, coro, task_name = mock_bg_task.call_args.args
        coro.close()  # prevent "coroutine was never awaited" warning — mock stores but never runs it
        assert task_name == "sensorpush_local_initial_audit"


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_audit_device_not_found(hass, mock_coordinator, caplog):
    """Test that audit_device returns {} and logs when BLE device is not found."""
    with patch(
        "custom_components.sensorpush_local.bluetooth.async_ble_device_from_address",
        return_value=None,
    ):
        result = await mock_coordinator.audit_device(
            "AA:BB:CC:DD:EE:FF", "Missing Sensor"
        )

    assert result == {}
    assert "not found by any proxies" in caplog.text


@pytest.mark.asyncio
async def test_audit_device_general_exception(hass, mock_coordinator, caplog):
    """Test that unexpected exceptions are caught and logged without raising."""
    mock_ble = MagicMock()
    mock_ble.address = "AA:BB:CC:DD:EE:FF"

    with (
        patch(
            "custom_components.sensorpush_local.bluetooth.async_ble_device_from_address",
            return_value=mock_ble,
        ),
        patch(
            "custom_components.sensorpush_local.establish_connection",
            side_effect=RuntimeError("proxy died"),
        ),
    ):

        result = await mock_coordinator.audit_device("AA:BB:CC:DD:EE:FF", "Boom Sensor")

    assert result == {}
    assert "RuntimeError" in caplog.text
    assert "proxy died" in caplog.text


@pytest.mark.asyncio
async def test_update_data_stores_successful_audit_result(hass, mock_coordinator):
    """Test that _async_update_data stores the result when audit_device succeeds."""
    dev_reg = dr.async_get(hass)
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    mock_entry.add_to_hass(hass)

    dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={("bluetooth", "AA:BB:CC:DD:EE:FF")},
        manufacturer=MANUFACTURER,
        name="Test Sensor",
    )

    audit_result = {
        "voltage": 3.0,
        "rssi": -55,
        "is_legacy": False,
        "source": "hci0",
        "raw_v": 3000,
        "temp_at_read": 21.0,
        "timestamp": "2026-03-22T00:00:00",
    }

    with patch.object(mock_coordinator, "audit_device", return_value=audit_result):
        result = await mock_coordinator._async_update_data()

    expected = {"AA:BB:CC:DD:EE:FF": audit_result}
    assert result == expected
    mock_coordinator._store.async_save.assert_called_once_with(expected)


@pytest.mark.asyncio
async def test_persisted_data_loaded_on_startup(hass, mock_coordinator):
    """Test that async_load_persisted_data seeds coordinator.data from storage."""
    stored = {"AA:BB:CC:DD:EE:FF": {"voltage": 3.0, "rssi": -55, "source": "hci0"}}
    mock_coordinator._store.async_load.return_value = stored

    await mock_coordinator.async_load_persisted_data()

    assert mock_coordinator.data == stored


@pytest.mark.asyncio
async def test_persisted_data_none_leaves_data_empty(hass, mock_coordinator):
    """Test that async_load_persisted_data with no stored data leaves coordinator.data unchanged."""
    mock_coordinator._store.async_load.return_value = None

    await mock_coordinator.async_load_persisted_data()

    assert mock_coordinator.data == {}


@pytest.mark.asyncio
async def test_setup_loads_persisted_data(hass, mock_coordinator):
    """Test that async_setup_entry calls async_load_persisted_data before the background audit."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mock_coordinator.config_entry = mock_entry

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch.object(mock_entry, "async_create_background_task"),
    ):

        await async_setup_entry(hass, mock_entry)

    mock_coordinator._store.async_load.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_update_data_skips_device_without_bluetooth_identifier(
    hass, mock_coordinator
):
    """Test that devices lacking a bluetooth identifier are skipped silently."""
    dev_reg = dr.async_get(hass)
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_entry_id", data={})
    mock_entry.add_to_hass(hass)

    # Register a SensorPush device with only a non-bluetooth identifier
    dev_reg.async_get_or_create(
        config_entry_id=mock_entry.entry_id,
        identifiers={("some_other_domain", "12345")},
        manufacturer=MANUFACTURER,
        name="Bluetooth-less Sensor",
    )

    result = await mock_coordinator._async_update_data()
    assert result == {}


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_daily_audit_callback_triggers_refresh(hass, mock_coordinator):
    """Test that the 3am daily callback schedules an async_refresh task."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={})
    mock_entry.add_to_hass(hass)
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mock_coordinator.config_entry = mock_entry

    captured_callback = None

    def fake_track_time_change(_hass, callback, **kwargs):
        nonlocal captured_callback
        captured_callback = callback
        return lambda: None

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch.object(mock_entry, "async_create_background_task"),
        patch(
            "custom_components.sensorpush_local.async_track_time_change",
            side_effect=fake_track_time_change,
        ),
    ):
        await async_setup_entry(hass, mock_entry)

    assert captured_callback is not None
    mock_coordinator.async_refresh.reset_mock()

    captured_callback(None)  # pylint: disable=not-callable  # simulate 3am firing
    await hass.async_block_till_done()

    mock_coordinator.async_refresh.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning")
async def test_options_update_triggers_reload(hass, mock_coordinator):
    """Test that updating options calls async_reload on the config entry."""
    mock_entry = MockConfigEntry(domain=DOMAIN, entry_id="mock_id", data={}, options={})
    mock_entry.add_to_hass(hass)
    mock_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    mock_coordinator.config_entry = mock_entry

    with (
        patch(
            "custom_components.sensorpush_local.SensorPushCoordinator",
            return_value=mock_coordinator,
        ),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"),
        patch.object(mock_entry, "async_create_background_task"),
        patch(
            "custom_components.sensorpush_local.async_track_time_change",
            return_value=lambda: None,
        ),
    ):
        await async_setup_entry(hass, mock_entry)

    with patch.object(hass.config_entries, "async_reload") as mock_reload:
        hass.config_entries.async_update_entry(
            mock_entry, options={"daily_audit_hour": 6}
        )
        await hass.async_block_till_done()
        mock_reload.assert_called_once_with(mock_entry.entry_id)
