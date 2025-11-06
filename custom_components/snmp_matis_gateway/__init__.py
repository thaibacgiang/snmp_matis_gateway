from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import DOMAIN, PLATFORMS
from .hub import MatisHub

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = MatisHub(hass, entry.data)
    await hub.async_discover()  # initial discovery
    await hub.async_first_poll()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # background: periodic rediscovery (every 30 minutes)
    def _schedule_rediscover(now):
        hass.async_create_task(hub.async_discover())

    async_track_time_interval(hass, _schedule_rediscover, timedelta(minutes=30))

    # periodic polling already handled inside platforms via coordinator in hub
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok