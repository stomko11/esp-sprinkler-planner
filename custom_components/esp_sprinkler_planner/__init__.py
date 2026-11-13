"""ESP Sprinkler Planner: plans and runs irrigation on an ESPHome sprinkler controller."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from . import websocket as ws_api
from .model import ConfigError
from .notify_logic import EVENTS
from .runtime import Runtime

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ENTRY = vol.Optional("config_entry_id")
SCHEMAS = {
    "configure": vol.Schema({ENTRY: cv.string, vol.Optional("zones"): dict, vol.Optional("slots"): list,
                             vol.Optional("settings"): dict, vol.Optional("notifications"): dict,
                             vol.Optional("pump"): dict, vol.Optional("weather"): dict,
                             vol.Optional("meters"): dict, vol.Optional("ui"): dict}),
    "test_notification": vol.Schema({ENTRY: cv.string, vol.Required("event"): vol.In(EVENTS),
                                     vol.Optional("targets"): [cv.string], vol.Optional("title"): cv.string,
                                     vol.Optional("message"): cv.string, vol.Optional("actions"): [cv.string]}),
    "get_plan": vol.Schema({ENTRY: cv.string, vol.Optional("days", default=7): vol.All(int, vol.Range(1, 31))}),
    "run_slot": vol.Schema({ENTRY: cv.string, vol.Required("slot"): cv.string}),
    "run_zone": vol.Schema({ENTRY: cv.string, vol.Required("zone"): cv.string,
                            vol.Required("minutes"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))}),
    "quick_run": vol.Schema({ENTRY: cv.string, vol.Required("zones"): [vol.Schema({
        vol.Required("zone"): cv.string,
        vol.Required("minutes"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=600))})],
        vol.Optional("reverse", default=False): cv.boolean}),
    "unskip": vol.Schema({ENTRY: cv.string, vol.Optional("run"): cv.string}),
    "answer_suggestion": vol.Schema({ENTRY: cv.string, vol.Required("run"): cv.string,
                                     vol.Required("accept"): cv.boolean}),
    "refresh_weather": vol.Schema({ENTRY: cv.string}),
    "get_stats": vol.Schema({ENTRY: cv.string, vol.Optional("period", default="week"): vol.In(["day", "week", "month", "year"]),
                             vol.Optional("count", default=12): vol.All(int, vol.Range(1, 400))}),
    "stop": vol.Schema({ENTRY: cv.string}),
    "skip_next": vol.Schema({ENTRY: cv.string}),
    "replan": vol.Schema({ENTRY: cv.string}),
}


def _runtime(hass: HomeAssistant, call: ServiceCall) -> Runtime:
    entries = [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None)]
    wanted = call.data.get("config_entry_id")
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if len(entries) != 1:
        raise ServiceValidationError("pass config_entry_id: none or several planners match")
    return entries[0].runtime_data


CARD_URL = f"/{DOMAIN}/esp-sprinkler-planner-card.js"


async def _register_card(hass: HomeAssistant) -> None:
    """Serve the card from the integration and load it on every dashboard (no manual resource)."""
    from pathlib import Path

    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / "frontend" / "esp-sprinkler-planner-card.js"
    version = str(int(path.stat().st_mtime)) if path.exists() else "0"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(path), False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")


async def async_setup(hass: HomeAssistant, config) -> bool:
    ws_api.async_register(hass)
    await _register_card(hass)
    async def handle(call: ServiceCall):
        rt = _runtime(hass, call)
        d = call.data
        try:
            if call.service == "configure":
                plan = await rt.configure(d.get("zones"), d.get("slots"), d.get("settings"),
                                          d.get("notifications"), d.get("pump"), d.get("weather"),
                                          d.get("meters"), d.get("ui"))
                return {"runs": len(plan.runs), "conflicts": [c.message for c in plan.conflicts]}
            if call.service == "test_notification":
                over = {k: d[k] for k in ("title", "message", "actions") if k in d}
                return {"sent_to": await rt.test_notification(d["event"], d.get("targets"), over)}
            if call.service == "get_plan":
                return rt.plan_dict(d["days"])
            if call.service == "run_slot":
                await rt.run_slot(d["slot"])
            elif call.service == "run_zone":
                await rt.run_zone(d["zone"], d["minutes"])
            elif call.service == "quick_run":
                await rt.quick_run(d["zones"], d["reverse"])
            elif call.service == "unskip":
                return {"unskipped": await rt.unskip(d.get("run"))}
            elif call.service == "answer_suggestion":
                await rt.answer_suggestion(d["run"], d["accept"])
            elif call.service == "refresh_weather":
                await rt.refresh_weather()
                await rt.async_replan()
            elif call.service == "get_stats":
                from homeassistant.util import dt as dt_util
                from .stats import aggregate, totals
                today = dt_util.now().date()
                return {**aggregate(rt.stats, today, d["period"], d["count"]), "totals": totals(rt.stats, today)}
            elif call.service == "stop":
                await rt.stop()
            elif call.service == "skip_next":
                return {"skipped": await rt.skip_next()}
            elif call.service == "replan":
                await rt.async_replan()
        except ConfigError as err:
            raise ServiceValidationError(str(err)) from err
        return None

    for name, schema in SCHEMAS.items():
        support = {"get_plan": SupportsResponse.ONLY, "configure": SupportsResponse.OPTIONAL,
                   "skip_next": SupportsResponse.OPTIONAL, "unskip": SupportsResponse.OPTIONAL,
                   "get_stats": SupportsResponse.ONLY,
                   "test_notification": SupportsResponse.OPTIONAL}.get(name, SupportsResponse.NONE)
        hass.services.async_register(DOMAIN, name, handle, schema=schema, supports_response=support)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    rt = Runtime(hass, entry)
    entry.runtime_data = rt
    await rt.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload))
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_stop()
    return ok
