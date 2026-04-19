"""Discovers Apple TV devices on the local network via mDNS/zeroconf."""

import asyncio
from typing import List, Dict

import pyatv


async def scan_devices(timeout: float = 5.0) -> List[Dict[str, str]]:
    """Return list of discovered Apple TV devices as dicts with name, address, identifier."""
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, timeout=timeout)

    results = []
    for atv in atvs:
        results.append(
            {
                "name": atv.name,
                "address": str(atv.address),
                "identifier": atv.identifier,
            }
        )
    return results
