"""Repairs that can be fixed with one click: a zone whose valve is gone from the ESP."""
from __future__ import annotations

from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant

from .model import ConfigError


class RemoveZonesFlow(RepairsFlow):
    """Remove the zones whose valve is not on the ESP any more."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = data

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None) -> data_entry_flow.FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: Optional[Dict[str, Any]] = None) -> data_entry_flow.FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._data.get("entry_id") or "")
        rt = getattr(entry, "runtime_data", None) if entry else None
        if rt is None:
            return self.async_abort(reason="not_loaded")
        zones = [z for z in self._data.get("zones") or [] if z in {v["id"] for v in rt.valves}]
        names = rt.zone_names()
        if user_input is not None:
            for z in zones:
                try:
                    await rt.remove_zone(z)
                except ConfigError as err:
                    return self.async_abort(reason="remove_failed", description_placeholders={"error": str(err)})
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}), description_placeholders={
            "zones": ", ".join(names.get(z, z) for z in zones) or "-", "planner": entry.title})


async def async_create_fix_flow(hass: HomeAssistant, issue_id: str, data: Optional[Dict[str, Any]]) -> RepairsFlow:
    return RemoveZonesFlow(dict(data or {}))
