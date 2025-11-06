# sensor.py
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import MatisHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up SNMP MATIS Gateway sensors."""
    hub: MatisHub = hass.data[DOMAIN][entry.entry_id]

    # Create initial entities
    entities = [MatisSensor(hub, s) for s in hub.sensors]
    async_add_entities(entities)

    # Dynamic add new discovered sensors on future rediscover
    @callback
    def _maybe_add_new_entities(_now=None):
        new = []
        current_ids = {e.unique_id for e in entities}
        for s in hub.sensors:
            if s["unique_id"] not in current_ids:
                ent = MatisSensor(hub, s)
                entities.append(ent)
                new.append(ent)
        if new:
            async_add_entities(new)

    # poll to detect if new ones appended by hub
    hass.helpers.event.async_track_time_interval(
        _maybe_add_new_entities, hass.helpers.event.timedelta(seconds=15)
    )


class MatisSensor(CoordinatorEntity, SensorEntity):
    """Representation of a MATIS SNMP Sensor."""

    _attr_has_entity_name = True

    def __init__(self, hub: MatisHub, desc: dict):
        """Initialize the sensor."""
        super().__init__(hub.coordinator)
        self.hub = hub
        self._desc = desc
        self._attr_unique_id = desc["unique_id"]
        self._attr_name = desc["name"]
        self._attr_native_unit_of_measurement = desc.get("unit")

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        return self.hub.get_value(self._desc["unique_id"])
