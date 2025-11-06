from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Callable, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta

from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    setCmd,
)

from .const import DOMAIN, CONF_READ_COMMUNITY, CONF_WRITE_COMMUNITY

async def _snmp_get(ip: str, community: str, oid: str) -> Optional[str]:
    engine = SnmpEngine()
    errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
        engine,
        CommunityData(community),
        UdpTransportTarget((ip, 161), timeout=1, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )
    await engine.transportDispatcher.closeDispatcher()
    if errorIndication or errorStatus:
        return None
    return str(varBinds[0][1])

async def _snmp_set(ip: str, community: str, oid: str, value: int) -> bool:
    from pysnmp.proto.rfc1902 import Integer
    engine = SnmpEngine()
    errorIndication, errorStatus, errorIndex, varBinds = await setCmd(
        engine,
        CommunityData(community),
        UdpTransportTarget((ip, 161), timeout=1, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid), Integer(int(value)))
    )
    await engine.transportDispatcher.closeDispatcher()
    return not (errorIndication or errorStatus)

TRANSFORMS: Dict[str, Callable[[Optional[str]], Optional[float]]] = {
    "raw_int": lambda v: float(v) if v is not None else None,
    "div100": lambda v: (float(v)/100.0) if v is not None else None,
    "div1000": lambda v: (float(v)/1000.0) if v is not None else None,
    "div10": lambda v: (float(v)/10.0) if v is not None else None,
    "kW_div100_to_W": lambda v: (float(v)/100.0*1000.0) if v is not None else None,
    "kW_div1000_to_W": lambda v: (float(v)/1000.0*1000.0) if v is not None else None,
}

class MatisHub:
    def __init__(self, hass: HomeAssistant, cfg: Dict[str, Any]) -> None:
        self.hass = hass
        self.host: str = cfg.get("host")
        self.read_com: str = cfg.get(CONF_READ_COMMUNITY, "public")
        self.write_com: str = cfg.get(CONF_WRITE_COMMUNITY, "private")

        self.sensors: List[Dict[str, Any]] = []
        self.switches: List[Dict[str, Any]] = []

        self.coordinator = DataUpdateCoordinator(
            hass,
            logger=hass.logger,
            name="matis_snmp",
            update_method=self._async_poll_all,
            update_interval=timedelta(seconds=5),
        )

        self._values: Dict[str, Any] = {}

    async def async_first_poll(self):
        await self.coordinator.async_config_entry_first_refresh()

    async def async_discover(self) -> None:
        # keep your discovery logic untouched
        await self.coordinator.async_request_refresh()

    async def _async_poll_all(self) -> Dict[str, Any]:
        results = {}

        async def fetch(oid: str):
            results[oid] = await _snmp_get(self.host, self.read_com, oid)

        await asyncio.gather(*(fetch(s["oid"]) for s in self.sensors))

        for s in self.sensors:
            raw = results.get(s["oid"])
            tf = TRANSFORMS.get(s["tf"], lambda x: x)
            try:
                self._values[s["unique_id"]] = tf(raw)
            except Exception:
                self._values[s["unique_id"]] = None

        return self._values

    def get_value(self, unique_id: str):
        return self._values.get(unique_id)

    async def async_set_switch(self, oid: str, state: bool) -> bool:
        return await _snmp_set(self.host, self.write_com, oid, 1 if state else 0)
