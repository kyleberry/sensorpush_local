"""Exercise audit cleanup through Home Assistant's config-entry lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant.common import MockConfigEntry

from custom_components.sensorpush_local import async_unload_entry
from custom_components.sensorpush_local.const import DOMAIN


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("trigger", ["initial", "daily", "manual"])
async def test_unload_cancels_running_audit(hass, trigger):
    """Unloading cancels each audit source and releases both coordinator locks."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    started = asyncio.Event()
    release = asyncio.Event()
    audit_task = None
    service_task = None
    unsubscribe = MagicMock()

    async def connect(*_args, **_kwargs):
        nonlocal audit_task
        audit_task = asyncio.current_task()
        started.set()
        await release.wait()
        raise TimeoutError

    devices = [(MagicMock(name_by_user="Kitchen"), "AA:BB:CC:DD:EE:FF")]
    with (
        patch(
            "custom_components.sensorpush_local.Store.async_load",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "custom_components.sensorpush_local.Store.async_save",
            new_callable=AsyncMock,
        ),
        patch("custom_components.sensorpush_local.async_get_source_devices") as sources,
        patch(
            "custom_components.sensorpush_local.bluetooth.async_ble_device_from_address"
        ),
        patch("custom_components.sensorpush_local.bluetooth.async_last_service_info"),
        patch(
            "custom_components.sensorpush_local.establish_connection",
            side_effect=connect,
        ),
        patch(
            "custom_components.sensorpush_local.async_track_time_change",
            return_value=unsubscribe,
        ) as schedule,
    ):
        sources.return_value = devices if trigger == "initial" else []
        assert await hass.config_entries.async_setup(entry.entry_id)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        try:
            if trigger != "initial":
                await hass.async_block_till_done(wait_background_tasks=True)
                sources.return_value = devices
                if trigger == "daily":
                    schedule.call_args.args[1](None)
                else:
                    service_task = asyncio.create_task(
                        hass.services.async_call(DOMAIN, "run_audit", blocking=True)
                    )
            await asyncio.wait_for(started.wait(), timeout=5)
            assert coordinator.is_audit_running()
            assert coordinator.is_audit_locked()

            assert await hass.config_entries.async_unload(entry.entry_id)
            assert entry.state is ConfigEntryState.NOT_LOADED
            unsubscribe.assert_called_once_with()
            assert entry.entry_id not in hass.data[DOMAIN]
            assert not hass.services.has_service(DOMAIN, "run_audit")
            assert audit_task.cancelled()
            assert not coordinator.is_audit_running()
            assert not coordinator.is_audit_locked()
        finally:
            # Also clean up on failure, so a regression cannot leave a BLE task behind.
            for task in (audit_task, service_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(task for task in (audit_task, service_task) if task is not None),
                return_exceptions=True,
            )


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("unload_ok", [True, False])
async def test_unload_daily_subscription(hass, unload_ok):
    """Unsubscribe and remove service/data only after successful platform unload."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    unsubscribe = MagicMock()
    with (
        patch(
            "custom_components.sensorpush_local.Store.async_load",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "custom_components.sensorpush_local.Store.async_save",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.sensorpush_local.async_track_time_change",
            return_value=unsubscribe,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=unload_ok
        ):
            if unload_ok:
                assert await hass.config_entries.async_unload(entry.entry_id)
            else:
                # Inspect the failed-platform contract before framework teardown.
                assert not await async_unload_entry(hass, entry)
        if unload_ok:
            unsubscribe.assert_called_once_with()
            assert entry.entry_id not in hass.data[DOMAIN]
            assert not hass.services.has_service(DOMAIN, "run_audit")
        else:
            unsubscribe.assert_not_called()
            assert hass.data[DOMAIN][entry.entry_id] is coordinator
            assert hass.services.has_service(DOMAIN, "run_audit")
        if not unload_ok:
            assert await hass.config_entries.async_unload(entry.entry_id)
