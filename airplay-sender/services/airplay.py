"""Connects to an Apple TV via pyatv and controls AirPlay playback."""

import asyncio
from typing import Callable, Optional

import pyatv
from pyatv.const import Protocol
from pyatv.interface import PairingHandler


class PinRequired(Exception):
    def __init__(self, pairing: PairingHandler):
        self.pairing = pairing
        super().__init__("Pairing PIN required")


class AirPlaySession:
    """Holds a live pyatv connection for the duration of a playback session."""

    def __init__(self):
        self._atv = None

    async def connect(
        self,
        identifier: str,
        pin_provider: Optional[Callable[[], str]] = None,
        timeout: float = 10.0,
    ) -> None:
        loop = asyncio.get_event_loop()
        atvs = await pyatv.scan(loop, identifier=identifier, timeout=timeout)
        if not atvs:
            raise RuntimeError(f"Apple TV '{identifier}' not found on the network.")

        conf = atvs[0]

        airplay_service = conf.get_service(Protocol.AirPlay)
        if airplay_service and not airplay_service.credentials:
            if pin_provider is None:
                raise PinRequired(None)

            pairing = await pyatv.pair(conf, Protocol.AirPlay, loop)
            await pairing.begin()

            if pairing.device_provides_pin:
                pairing.pin(pin_provider())
            else:
                pairing.pin(None)

            await pairing.finish()

            if not pairing.has_paired:
                raise RuntimeError("Pairing failed. Check the PIN and try again.")

        self._atv = await pyatv.connect(conf, loop)

    async def stream(self, url: str) -> None:
        await self._atv.stream.stream_file(url)

    async def pause(self) -> None:
        await self._atv.remote_control.pause()

    async def resume(self) -> None:
        await self._atv.remote_control.play()

    async def seek(self, position_seconds: int) -> None:
        await self._atv.remote_control.set_position(position_seconds)

    async def position(self) -> tuple[int, int]:
        """Return (current_seconds, total_seconds), or (0, 0) on error."""
        try:
            playing = await self._atv.metadata.playing()
            return playing.position or 0, playing.total_time or 0
        except Exception:
            return 0, 0

    async def stop(self) -> None:
        if self._atv:
            try:
                await self._atv.remote_control.stop()
            except Exception:
                pass
            self.close()

    def close(self) -> None:
        if self._atv:
            self._atv.close()
            self._atv = None
