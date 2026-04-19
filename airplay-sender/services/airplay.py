"""Connects to an Apple TV via pyatv and streams an HLS URL using AirPlay."""

import asyncio
from typing import Callable, Optional

import pyatv
from pyatv.const import Protocol
from pyatv.interface import PairingHandler


class PinRequired(Exception):
    """Raised when the Apple TV requires a pairing PIN before streaming."""

    def __init__(self, pairing: PairingHandler):
        self.pairing = pairing
        super().__init__("Pairing PIN required")


async def stream_url(
    identifier: str,
    stream_url: str,
    pin_provider: Optional[Callable[[], str]] = None,
    timeout: float = 10.0,
) -> None:
    """Connect to the Apple TV identified by *identifier* and play *stream_url*.

    *pin_provider* is a zero-argument callable that returns the PIN string
    entered by the user.  It is invoked only when pairing is required.
    """
    loop = asyncio.get_event_loop()

    # Locate the specific device
    atvs = await pyatv.scan(loop, identifier=identifier, timeout=timeout)
    if not atvs:
        raise RuntimeError(f"Apple TV '{identifier}' not found on the network.")

    conf = atvs[0]

    # Attempt to pair AirPlay if no credentials are stored yet
    airplay_service = conf.get_service(Protocol.AirPlay)
    if airplay_service and not airplay_service.credentials:
        if pin_provider is None:
            raise PinRequired(None)

        pairing = await pyatv.pair(conf, Protocol.AirPlay, loop)
        await pairing.begin()

        if pairing.device_provides_pin:
            pin = pin_provider()
            pairing.pin(pin)
        else:
            pairing.pin(None)  # we provide the PIN; device shows it

        await pairing.finish()

        if not pairing.has_paired:
            raise RuntimeError("Pairing failed. Check the PIN and try again.")

    atv = await pyatv.connect(conf, loop)
    try:
        await atv.stream.stream_file(stream_url)
    finally:
        atv.close()


async def stop_playback(identifier: str, timeout: float = 10.0) -> None:
    """Connect to the Apple TV and stop any active playback."""
    loop = asyncio.get_event_loop()
    atvs = await pyatv.scan(loop, identifier=identifier, timeout=timeout)
    if not atvs:
        return

    atv = await pyatv.connect(atvs[0], loop)
    try:
        await atv.remote_control.stop()
    finally:
        atv.close()
