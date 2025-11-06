from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import MatisHub

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    hub: MatisHub = hass.data[DOMAIN][entry.entry_id]

    entities = [MatisSwitch(hub, s) for s in hub.switches]
    async_add_entities(entities)

    @callback
    def _maybe_add_new_switches(_now=None):
        new = []
        current_ids = {e.unique_id for e in entities}
        for s in hub.switches:
            if s["unique_id"] not in current_ids:
                ent = MatisSwitch(hub, s)
                entities.append(ent)
                new.append(ent)
        if new:
            async_add_entities(new)

    hass.helpers.event.async_track_time_interval(_maybe_add_new_switches, hass.helpers.event.timedelta(seconds=15))

class MatisSwitch(SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, hub: MatisHub, desc: dict):
        self.hub = hub
        self._desc = desc
        self._state = None
        self._attr_unique_id = desc["unique_id"]
        self._attr_name = desc["name"]

    @property
    def is_on(self) -> bool | None:
        # state sensor value if present (0/1)
        key = f"{self._desc['unique_id']}_state"
        base = self.hub.get_value(key)
        if base is None:
            # fall back to reading switch oid value via value cache of state sensor with same oid
            base = self.hub.get_value(self._desc["unique_id"])
        if base is None:
            return None
        try:
            return float(base) == 1.0
        except Exception:
            return None

    async def async_turn_on(self, **kwargs):
        await self.hub.async_set_switch(self._desc["oid"], True)

    async def async_turn_off(self, **kwargs):
        await self.hub.async_set_switch(self._desc["oid"], False)