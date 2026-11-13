"""Switches: planner enabled, dry run."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .sensor import _Base


class Flag(_Base, SwitchEntity):
    def __init__(self, entry, key: str, name: str, icon: str, category=None) -> None:
        super().__init__(entry, key, name)
        self._key = key
        self._attr_icon = icon
        self._attr_entity_category = category

    @property
    def is_on(self) -> bool:
        return bool(self.rt.flags.get(self._key))

    async def async_turn_on(self, **kwargs) -> None:
        await self.rt.set_flag(self._key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.rt.set_flag(self._key, False)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        Flag(entry, "enabled", "Planner enabled", "mdi:calendar-check"),
        Flag(entry, "dry_run", "Dry run", "mdi:test-tube", EntityCategory.CONFIG),
    ])
