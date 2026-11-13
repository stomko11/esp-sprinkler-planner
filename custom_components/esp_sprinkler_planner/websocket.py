"""Websocket API for the card: read everything, preview a changed config, save it, set flags."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .model import ConfigError
from .notify_logic import ACTIONS, DEFAULTS, EVENTS, VARIABLES, merged


def _runtime(hass: HomeAssistant, entry_id: Optional[str]):
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
    if entry_id:
        entries = [e for e in entries if e.entry_id == entry_id]
    return entries[0].runtime_data if len(entries) == 1 else None


def _entities(hass, entry_id: str) -> Dict[str, str]:
    reg = er.async_get(hass)
    out = {}
    for e in er.async_entries_for_config_entry(reg, entry_id):
        key = (e.unique_id or "")[len(entry_id) + 1:]
        out[key] = e.entity_id
    return out


def snapshot(hass, rt, days: int) -> Dict[str, Any]:
    today = dt_util.now().date()
    sun = []
    for i in range(days):
        d = today + timedelta(days=i)
        rise = get_astral_event_date(hass, "sunrise", d)
        sset = get_astral_event_date(hass, "sunset", d)
        sun.append({"day": d.isoformat(), "sunrise": dt_util.as_local(rise).isoformat() if rise else None,
                    "sunset": dt_util.as_local(sset).isoformat() if sset else None})
    try:
        notif = merged(rt.config.get("notifications"))
    except Exception:  # noqa: BLE001 - show what is stored, the card reports the error
        notif = None
    notify_services = sorted(f"notify.{s}" for s in hass.services.async_services().get("notify", {}))
    return {
        "entry_id": rt.entry.entry_id, "title": rt.entry.title,
        "valves": [{k: v.get(k) for k in ("id", "name", "order", "enabled", "max_minutes", "valve_switch")}
                   for v in rt.valves],
        "config": rt.config, "notifications_full": notif,
        "notify_meta": {"events": list(EVENTS), "actions": ACTIONS, "variables": VARIABLES, "defaults": DEFAULTS},
        "notify_services": notify_services,
        "plan": rt.plan_dict(days),
        "timing": {"valve_overlap": rt.valve_overlap,
                   "pump_delay": (rt.pump.get("delay") if rt.pump.get("auto_on") else 0) if rt.pump else 0},
        "sun": sun, "now": dt_util.now().isoformat(),
        "status": rt.status, "error": rt.error, "flags": rt.flags, "active": rt.active,
        "active_zone": rt.active_zone, "next_run_key": None,
        "history": {d: rt.history[d] for d in sorted(rt.history)[-7:]}, "last_run": rt.last_run,
        "entities": _entities(hass, rt.entry.entry_id),
    }


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get", vol.Optional("entry_id"): str,
                                  vol.Optional("days", default=7): vol.All(int, vol.Range(1, 31))})
@callback
def ws_get(hass, connection, msg):
    rt = _runtime(hass, msg.get("entry_id"))
    if rt is None:
        connection.send_error(msg["id"], "not_found", "no planner found (or several: pass entry_id)")
        return
    connection.send_result(msg["id"], snapshot(hass, rt, msg["days"]))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list"})
@callback
def ws_list(hass, connection, msg):
    connection.send_result(msg["id"], [{"entry_id": e.entry_id, "title": e.title}
                                       for e in hass.config_entries.async_entries(DOMAIN)])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/preview", vol.Optional("entry_id"): str,
                                  vol.Required("config"): dict,
                                  vol.Optional("days", default=7): vol.All(int, vol.Range(1, 31))})
@callback
def ws_preview(hass, connection, msg):
    rt = _runtime(hass, msg.get("entry_id"))
    if rt is None:
        connection.send_error(msg["id"], "not_found", "no planner found")
        return
    cfg = {**rt.config, **msg["config"]}
    connection.send_result(msg["id"], rt.plan_dict(msg["days"], config=cfg))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/save", vol.Optional("entry_id"): str,
                                  vol.Required("config"): dict})
@websocket_api.async_response
async def ws_save(hass, connection, msg):
    rt = _runtime(hass, msg.get("entry_id"))
    if rt is None:
        connection.send_error(msg["id"], "not_found", "no planner found")
        return
    c = msg["config"]
    try:
        await rt.configure(c.get("zones"), c.get("slots"), c.get("settings"), c.get("notifications"), c.get("pump"))
    except ConfigError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], snapshot(hass, rt, 7))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/flag", vol.Optional("entry_id"): str,
                                  vol.Required("name"): vol.In(["enabled", "dry_run"]), vol.Required("value"): bool})
@websocket_api.async_response
async def ws_flag(hass, connection, msg):
    rt = _runtime(hass, msg.get("entry_id"))
    if rt is None:
        connection.send_error(msg["id"], "not_found", "no planner found")
        return
    await rt.set_flag(msg["name"], msg["value"])
    connection.send_result(msg["id"], {"flags": rt.flags})


def async_register(hass: HomeAssistant) -> None:
    for cmd in (ws_get, ws_list, ws_preview, ws_save, ws_flag):
        websocket_api.async_register_command(hass, cmd)
