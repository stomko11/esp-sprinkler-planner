"""Diagnostics download: Settings -> Devices & services -> ESP Sprinkler Planner -> ... -> Download diagnostics."""
from __future__ import annotations

from typing import Any, Dict

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import websocket as ws_api

REDACT = {"access_token", "token", "password", "api_key", "latitude", "longitude"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> Dict[str, Any]:
    rt = entry.runtime_data
    snap = ws_api.snapshot(hass, rt, 7)
    return async_redact_data({
        "entry": {"title": entry.title, "data": dict(entry.data), "options": dict(entry.options), "version": entry.version},
        "status": rt.status, "error": rt.error, "flags": rt.flags, "health": rt.health,
        "config": rt.config, "plan": snap.get("plan"), "weather_now": snap.get("weather_now"),
        "held": rt.held, "pause_until": rt.pause_until, "active": rt.active, "active_zone": rt.active_zone,
        "skip": rt.skip, "suggestions": rt.suggestions, "log": rt.log[-100:],
        "states": {eid: (hass.states.get(eid).state if hass.states.get(eid) else None)
                   for eid in snap.get("entities", {}).values()},
    }, REDACT)
