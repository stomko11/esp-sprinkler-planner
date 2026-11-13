"""Buttons: stop the active run, skip the next run."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .sensor import _Base


class Stop(_Base, ButtonEntity):
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, entry):
        super().__init__(entry, "stop", "Stop")

    async def async_press(self) -> None:
        await self.rt.stop()


class SkipNext(_Base, ButtonEntity):
    _attr_icon = "mdi:skip-next-circle-outline"

    def __init__(self, entry):
        super().__init__(entry, "skip_next", "Skip next run")

    async def async_press(self) -> None:
        await self.rt.skip_next()


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Stop(entry), SkipNext(entry)])
