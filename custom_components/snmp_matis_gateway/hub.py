from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Callable, Optional
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# ✅ API ĐÚNG CHO PYSMNP 7.x TRÊN HA 2025.11
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    setCmd,
    nextCmd,
)

from pysnmp.proto.rfc1902 import Integer

from .const import DOMAIN, CONF_READ_COMMUNITY, CONF_WRITE_COMMUNITY


async def _snmp_get(ip: str, community: str, oid: str) -> Optional[str]:
    engine = SnmpEngine()
    errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
        engine,
        CommunityData(community, mpModel=1),
        UdpTransportTarget((ip, 161), timeout=1, retries=1),
        ContextData(),
        ObjectType(ObjectIdentity(oid))
    )
    await engine.transportDispatcher.closeDispatcher()
    if
