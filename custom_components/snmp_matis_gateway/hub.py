# hub.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Callable, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import timedelta

from pysnmp.hlapi import (
    SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
    ObjectType, ObjectIdentity, getCmd
)

from .const import CONF_READ_COMMUNITY, CONF_WRITE_COMMUNITY


def _snmp_get(ip: str, community: str, oid: str) -> Optional[str]:
    """Perform SNMP GET operation."""
    iterator = getCmd(
        SnmpEngine(),
        CommunityData(community),
        UdpTransportTarget((ip, 161), timeout=1.0, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )
    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
    if errorIndication or errorStatus:
        return None
    for vb in varBinds:
        return str(vb[1])
    return None


def _snmp_set(ip: str, community: str, oid: str, value: int) -> bool:
    """Perform SNMP SET operation."""
    # lazy import to avoid cost if not needed
    from pysnmp.hlapi import setCmd, Integer
    iterator = setCmd(
        SnmpEngine(),
        CommunityData(community),
        UdpTransportTarget((ip, 161), timeout=1.0, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid), Integer(int(value)))
    )
    errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
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
    """Hub for MATIS SNMP communication."""

    def __init__(self, hass: HomeAssistant, cfg: Dict[str, Any]) -> None:
        """Initialize."""
        self.hass = hass
        self.host: str = cfg.get("host", "")
        self.read_com: str = cfg.get(CONF_READ_COMMUNITY, "public")
        self.write_com: str = cfg.get(CONF_WRITE_COMMUNITY, "private")

        self.sensors: List[Dict[str, Any]] = []
        self.switches: List[Dict[str, Any]] = []

        # coordinator to poll all sensor oids
        self.coordinator = DataUpdateCoordinator(
            hass,
            logger=hass.logger,
            name="matis_snmp",
            update_method=self._async_poll_all,
            update_interval=timedelta(seconds=5),
        )

        # cache values
        self._values: Dict[str, Any] = {}

    async def async_first_poll(self):
        """Perform first poll."""
        await self.coordinator.async_config_entry_first_refresh()

    async def async_discover(self) -> None:
        """Dynamic discovery of present OIDs / indices."""
        new_sensors: List[Dict[str, Any]] = []
        new_switches: List[Dict[str, Any]] = []

        # ---- SDM220 ---- (prefix 14.11.3.1)
        sdm = {
            "energy_total": (".1.3.6.1.4.1.45797.14.11.3.1.7.1", "kWh", "div100"),
            "power_W": (".1.3.6.1.4.1.45797.14.11.3.1.9.1", "W", "kW_div100_to_W"),
            "voltage": (".1.3.6.1.4.1.45797.14.11.3.1.14.1", "V", "div100"),
            "current": (".1.3.6.1.4.1.45797.14.11.3.1.39.1", "A", "div100"),
        }
        for key, (oid, unit, tf) in sdm.items():
            val = await asyncio.to_thread(_snmp_get, self.host, self.read_com, oid)
            if val is not None:
                new_sensors.append({
                    "unique_id": f"sdm220_{key}",
                    "name": f"SDM220 {key.replace('_', ' ').title()}",
                    "oid": oid, "unit": unit, "tf": tf
                })

        # ---- DDS ---- (prefix 14.21.3.1)
        dds = {
            "energy_total": (".1.3.6.1.4.1.45797.14.21.3.1.7.1", "kWh", "div100"),
            "power_W": (".1.3.6.1.4.1.45797.14.21.3.1.9.1", "W", "kW_div1000_to_W"),
            "voltage": (".1.3.6.1.4.1.45797.14.21.3.1.15.1", "V", "div100"),
            "current": (".1.3.6.1.4.1.45797.14.21.3.1.14.1", "A", "div1000"),
        }
        for key, (oid, unit, tf) in dds.items():
            val = await asyncio.to_thread(_snmp_get, self.host, self.read_com, oid)
            if val is not None:
                new_sensors.append({
                    "unique_id": f"dds_{key}",
                    "name": f"DDS {key.replace('_', ' ').title()}",
                    "oid": oid, "unit": unit, "tf": tf
                })

        # ---- Battery cells ---- (prefix 14.9.5.1 .x.{n})
        # Probe up to 32 cells
        for n in range(1, 33):
            soc_oid = f".1.3.6.1.4.1.45797.14.9.5.1.11.{n}"
            soc = await asyncio.to_thread(_snmp_get, self.host, self.read_com, soc_oid)
            if soc is None:
                continue  # cell not present
            new_sensors.append({
                "unique_id": f"battery_cell_{n}_soc",
                "name": f"Battery Cell {n} SOC",
                "oid": soc_oid, "unit": "%", "tf": "div100"
            })
            volt_oid = f".1.3.6.1.4.1.45797.14.9.5.1.3.{n}"
            curr_oid = f".1.3.6.1.4.1.45797.14.9.5.1.4.{n}"
            temp_oid = f".1.3.6.1.4.1.45797.14.9.5.1.7.{n}"
            new_sensors.append({
                "unique_id": f"battery_cell_{n}_voltage",
                "name": f"Battery Cell {n} Voltage",
                "oid": volt_oid, "unit": "V", "tf": "div100"
            })
            new_sensors.append({
                "unique_id": f"battery_cell_{n}_current",
                "name": f"Battery Cell {n} Current",
                "oid": curr_oid, "unit": "A", "tf": "div100"
            })
            new_sensors.append({
                "unique_id": f"battery_cell_{n}_temperature",
                "name": f"Battery Cell {n} Temperature",
                "oid": temp_oid, "unit": "°C", "tf": "div10"
            })

        # ---- Attomat switches (prefix 14.18.3.1.3.{idx}) ----
        for idx in range(1, 9):  # up to 8 channels
            oid = f".1.3.6.1.4.1.45797.14.18.3.1.3.{idx}"
            val = await asyncio.to_thread(_snmp_get, self.host, self.read_com, oid)
            if val is None:
                continue
            new_switches.append({
                "unique_id": f"attomat_{idx}",
                "name": f"Attomat {idx}",
                "oid": oid
            })
            # also expose state sensor (0/1) if desired
            new_sensors.append({
                "unique_id": f"attomat_{idx}_state",
                "name": f"Attomat {idx} State",
                "oid": oid, "unit": None, "tf": "raw_int"
            })

        # Merge without duplicates
        def _merge(old, new, key="unique_id"):
            have = {e[key] for e in old}
            for e in new:
                if e[key] not in have:
                    old.append(e)

        _merge(self.sensors, new_sensors)
        _merge(self.switches, new_switches)

        # inform coordinator to refresh soon
        await self.coordinator.async_request_refresh()

    async def _async_poll_all(self) -> Dict[str, Any]:
        """Pull values for all sensor OIDs."""
        results = {}
        tasks = []

        async def fetch(oid: str):
            v = await asyncio.to_thread(_snmp_get, self.host, self.read_com, oid)
            results[oid] = v

        for s in self.sensors:
            tasks.append(fetch(s["oid"]))
        if tasks:
            await asyncio.gather(*tasks)

        # transform stage
        for s in self.sensors:
            raw = results.get(s["oid"])
            tf = TRANSFORMS.get(s["tf"], lambda x: x)
            try:
                self._values[s["unique_id"]] = tf(raw)
            except Exception:
                self._values[s["unique_id"]] = None
        return self._values

    def get_value(self, unique_id: str):
        """Get cached value for unique_id."""
        return self._values.get(unique_id)

    async def async_set_switch(self, oid: str, state: bool) -> bool:
        """Set switch state."""
        return await asyncio.to_thread(_snmp_set, self.host, self.write_com, oid, 1 if state else 0)
