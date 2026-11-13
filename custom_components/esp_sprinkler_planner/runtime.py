"""Runtime: stored config, plan, timer, execution on the ESP (or dry run), monitoring, restore."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (async_track_point_in_utc_time, async_track_state_change_event,
                                         async_track_time_interval)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.template import Template
from homeassistant.util import slugify
from homeassistant.util import dt as dt_util

from . import executor, model, notify_logic, planner, stats as stats_mod, weather as wx_mod
from .const import (CONF_CONTROLLER, CONF_VALVE_OVERLAP, CONF_VALVES, DEFAULT_WATCHDOG, DOMAIN, EVENT, OPT_RESTORE,
                    OPT_WATCHDOG, PLAN_DAYS, STORAGE_VERSION)

_LOGGER = logging.getLogger(__name__)


def run_key(run: planner.Run) -> str:
    return f"{run.day.isoformat()}|{'+'.join(run.slot_ids)}"


class Runtime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.config: Dict[str, Any] = {}
        self.flags: Dict[str, bool] = {"enabled": True, "dry_run": True}
        self.skip: List[str] = []
        self.active: Optional[Dict[str, Any]] = None   # the run being executed (persisted)
        self.plan: Optional[planner.Plan] = None
        self.next_run: Optional[planner.Run] = None
        self.error: Optional[str] = None
        self.last_event: Optional[Dict[str, Any]] = None
        self._listeners: List[Callable[[], None]] = []
        self._unsubs: List[Callable[[], None]] = []
        self._timer = None
        self._watchdog = None
        self._dry_timer = None
        self._confirmed = False   # main switch seen ON for the active run
        self.history: Dict[str, Dict[str, float]] = {}    # "YYYY-MM-DD" -> zone id -> minutes actually watered
        self.last_run: Dict[str, Dict[str, Any]] = {}     # zone id -> {"start", "end", "minutes"}
        self.active_zone: Optional[Dict[str, Any]] = None
        self._zone_on: Dict[str, datetime] = {}
        self._valve_of: Dict[str, str] = {}
        self._planned_timer = None
        self._noticed: set = set()
        # milestone 5: weather, suggestions, stats
        self.wx: Dict[str, Any] = {"hourly": [], "daily": [], "fallen": None, "temp": None, "updated": None, "error": None}
        self.decisions: Dict[str, Dict[str, Any]] = {}   # run key -> weather decision (+ status)
        self.wx_skip: List[str] = []                      # run keys skipped because of the weather
        self.suggestions: Dict[str, Dict[str, Any]] = {}  # run key -> {status, action, factor, reasons, ...}
        self.skip_done: List[str] = []                    # user skips whose start has passed (shown dimmed)
        self.stats: Dict[str, Any] = {}
        self.flow_samples: Dict[str, List[float]] = {}
        self._meter: Dict[str, Dict[str, Any]] = {}       # zone id -> readings while open
        self._run_meter: Optional[Dict[str, Any]] = None  # pump energy over the whole run
        self._dyn_unsubs: List[Callable[[], None]] = []
        self._wx_refresh_at = None

    # ------------------------------------------------------------------ properties
    @property
    def valves(self) -> List[Dict[str, Any]]:
        return self.entry.data[CONF_VALVES]

    @property
    def controller(self) -> Dict[str, Optional[str]]:
        return self.entry.data[CONF_CONTROLLER]

    @property
    def valve_overlap(self) -> int:
        return int(self.entry.options.get(CONF_VALVE_OVERLAP, self.entry.data.get(CONF_VALVE_OVERLAP, 0)) or 0)

    @property
    def status(self) -> str:
        if self.error:
            return "error"
        if self.active:
            return "dry_run" if self.active.get("dry_run") else "running"
        if not self.flags["enabled"]:
            return "disabled"
        return "scheduled" if self.next_run else "idle"

    @property
    def lang(self) -> str:
        want = ((self.config.get("ui") or {}).get("language") or "auto")
        if want in notify_logic.LANGUAGES:
            return want
        return "sk" if str(self.hass.config.language or "").lower().startswith("sk") else "en"

    @property
    def weather_cfg(self) -> Dict[str, Any]:
        try:
            return wx_mod.merged(self.config.get("weather"))
        except wx_mod.WeatherConfigError:
            return wx_mod.merged({})

    @property
    def meters(self) -> Dict[str, Any]:
        try:
            return stats_mod.meters_from_dict(self.config.get("meters"))
        except stats_mod.MetersConfigError:
            return {}

    def zone_names(self) -> Dict[str, str]:
        names = {v["id"]: v.get("name") or v["id"] for v in self.valves}
        for zid, c in (self.config.get("zones") or {}).items():
            if c.get("name"):
                names[zid] = c["name"]
        return names

    # ------------------------------------------------------------------ listeners / persistence
    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    @callback
    def _changed(self) -> None:
        for cb in list(self._listeners):
            cb()

    async def _save(self) -> None:
        await self.store.async_save({"config": self.config, "flags": self.flags, "skip": self.skip,
                                     "active": self.active, "history": self.history, "last_run": self.last_run,
                                     "stats": self.stats, "flow_samples": self.flow_samples,
                                     "suggestions": self.suggestions, "skip_done": self.skip_done})

    def _event(self, kind: str, **data) -> None:
        payload = {"entry_id": self.entry.entry_id, "type": kind, **data}
        self.last_event = {**payload, "time": dt_util.utcnow().isoformat()}
        self.hass.bus.async_fire(EVENT, payload)
        _LOGGER.info("%s: %s %s", self.entry.title, kind, data.get("reason") or "")
        if kind in notify_logic.EVENTS:
            extra = {k: v for k, v in data.items() if k not in ("run", "calls")}
            if kind == "dry_run":
                extra["calls"] = len(data.get("calls") or [])
            self.notify(kind, data.get("run"), **extra)

    # ------------------------------------------------------------------ notifications
    def notify(self, event: str, run: Optional[Dict[str, Any]] = None, **extra) -> None:
        self.hass.async_create_task(self._send(event, run, extra))

    def _render(self, text: str, variables: Dict[str, Any]) -> str:
        try:
            return str(Template(text, self.hass).async_render(variables, parse_result=False))
        except Exception as err:  # noqa: BLE001 - a broken template must not stop irrigation
            _LOGGER.warning("%s: notification template error (%s): %s", self.entry.title, err, text)
            return text

    def _platform(self, target: str) -> str:
        over = ((self.config.get("notifications") or {}).get("platforms") or {}).get(target)
        if over in ("android", "ios", "other"):
            return over
        svc = target.split(".", 1)[1]
        if not svc.startswith("mobile_app_"):
            return "other"
        for ent in self.hass.config_entries.async_entries("mobile_app"):
            if "mobile_app_" + slugify(ent.data.get("device_name") or "") == svc:
                os_name = str(ent.data.get("os_name") or "").lower()
                return "ios" if ("ios" in os_name or "ipados" in os_name) else "android"
        return "android"

    async def _send(self, event: str, run: Optional[Dict[str, Any]], extra: Dict[str, Any], force=None,
                    override: Optional[Dict[str, Any]] = None) -> List[str]:
        try:
            full = notify_logic.merged(self.config.get("notifications"), self.lang)
        except notify_logic.NotifyConfigError as err:
            _LOGGER.warning("%s: notifications not sent: %s", self.entry.title, err)
            return []
        targets = force if force is not None else notify_logic.targets_for(full, event)
        e = {**full["events"][event], **{k: v for k, v in (override or {}).items() if v is not None}}
        slot_names = {x["id"]: x.get("name") or x["id"] for x in self.config.get("slots") or []}
        v = notify_logic.variables(event, run, slot_names, self.entry.title, extra)
        title, msg = self._render(e["title"], v), self._render(e["message"], v)
        sent = []
        for t in targets:
            data = notify_logic.payload(self._platform(t), title, msg, e.get("actions") or [], self.entry.entry_id,
                                        tag=f"esp_sprinkler_{self.entry.entry_id}", lang=self.lang, event=event)
            dom, svc = t.split(".", 1)
            try:
                if not self.hass.services.has_service(dom, svc) and self.hass.states.get(t) is not None:
                    # a notify entity (new style): title + message only
                    await self.hass.services.async_call("notify", "send_message",
                                                        {"entity_id": t, "title": notify_logic.plain(data["title"]),
                                                         "message": notify_logic.plain(data["message"])}, blocking=False)
                else:
                    await self.hass.services.async_call(dom, svc, data, blocking=False)
                sent.append(t)
                _LOGGER.info("%s: notified %s (%s): %s - %s", self.entry.title, t, event, data["title"], data["message"])
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("%s: notification to %s failed: %s", self.entry.title, t, err)
        return sent

    async def test_notification(self, event: str, targets: Optional[List[str]] = None,
                                override: Optional[Dict[str, Any]] = None) -> List[str]:
        run = self.next_run or (self.plan.runs[0] if self.plan and self.plan.runs else None)
        rd = model.run_to_dict(run, self.zone_names()) if run else None
        extra = {"reason": "test", "source": "test", "zone": (rd or {}).get("zones", [{}])[0].get("name") if rd else None,
                 "zone_minutes": 5, "actual_minutes": 0, "pump": (self.config.get("pump") or {}).get("entity"),
                 "lead": 30, "calls": 0, "action": "skip", "factor": "70 %", "flow": 12.5, "usual": 9.8,
                 "direction": "high"}
        return await self._send(event, rd, extra, force=targets, override=override)

    @callback
    def _on_action(self, event: Event) -> None:
        parsed = notify_logic.parse_action(event.data.get("action") or event.data.get("actionName") or "")
        if not parsed or parsed[1] != self.entry.entry_id:
            return
        name = parsed[0]
        _LOGGER.info("%s: notification action %s", self.entry.title, name)
        if name == "stop":
            self.hass.async_create_task(self.stop())
        elif name == "skip":
            self.hass.async_create_task(self.skip_next())
        elif name == "pump_on":
            self.hass.async_create_task(self._pump_switch(True, by_user=True))
        elif name in ("accept", "dismiss"):
            pend = sorted(k for k, v in self.suggestions.items() if v.get("status") == "pending")
            if pend:
                self.hass.async_create_task(self.answer_suggestion(pend[0], name == "accept"))

    # ------------------------------------------------------------------ pump
    @property
    def pump(self) -> Dict[str, Any]:
        try:
            return model.pump_from_dict(self.config.get("pump"))
        except model.ConfigError:
            return {}

    def _pump_is_on(self) -> bool:
        p = self.pump
        st = self.hass.states.get(p["entity"]) if p else None
        return bool(st and st.state == "on")

    async def _pump_switch(self, on: bool, by_user: bool = False) -> None:
        p = self.pump
        if not p:
            return
        try:
            await self.hass.services.async_call("homeassistant", "turn_on" if on else "turn_off",
                                                {"entity_id": p["entity"]}, blocking=True)
            if on and by_user and self.active:
                self.active["pump_started"] = True   # turned on for this run -> off after it (auto_off)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: pump %s failed: %s", self.entry.title, "on" if on else "off", err)

    # ------------------------------------------------------------------ valve tracking
    @callback
    def _on_valve(self, event: Event) -> None:
        zid = self._valve_of.get(event.data.get("entity_id"))
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if zid is None or new is None or old is None:
            return
        if new.state == "on" and old.state != "on":
            self._zone_on[zid] = new.last_changed
            self._meter_start(zid, new.last_changed)
            planned = None
            if self.active:
                planned = next((z["minutes"] for z in self.active["run"]["zones"] if z["zone"] == zid), None)
            self.active_zone = {"zone": zid, "name": self.zone_names().get(zid, zid),
                                "since": new.last_changed.isoformat(), "minutes": planned,
                                "until": (new.last_changed + timedelta(minutes=planned)).isoformat() if planned else None}
            if self.active and not self.active.get("dry_run"):
                self.notify("zone_changed", self.active["run"], zone=self.active_zone["name"], zone_minutes=planned)
            self._changed()
        elif new.state != "on" and old.state == "on":
            since = self._zone_on.pop(zid, None) or old.last_changed
            minutes = round(max(0.0, (new.last_changed - since).total_seconds()) / 60, 2)
            day = dt_util.as_local(since).date().isoformat()
            self.history.setdefault(day, {})
            self.history[day][zid] = round(self.history[day].get(zid, 0) + minutes, 2)
            for d in sorted(self.history)[:-14]:
                del self.history[d]
            self.last_run[zid] = {"start": since.isoformat(), "end": new.last_changed.isoformat(), "minutes": minutes}
            self._meter_stop(zid, day, minutes, new.last_changed)
            if self.active and not self.active.get("dry_run"):
                act = self.active.setdefault("actual", {})
                act[zid] = round(act.get(zid, 0) + minutes, 2)
            if self.active_zone and self.active_zone["zone"] == zid:
                self.active_zone = None
            self.hass.async_create_task(self._save())
            self._changed()

    # ------------------------------------------------------------------ meters
    def _read(self, eid: Optional[str]):
        st = self.hass.states.get(eid) if eid else None
        if st is None:
            return None, None
        try:
            return float(st.state), st.attributes.get("unit_of_measurement")
        except (TypeError, ValueError):
            return None, None

    def _rate(self, key: str) -> Optional[float]:
        v, u = self._read(self.meters.get(key))
        if v is None:
            return None
        return stats_mod.l_per_min(v, u) if key == "flow" else stats_mod.watts(v, u)

    def _total(self, key: str) -> Optional[float]:
        v, u = self._read(self.meters.get(key))
        if v is None:
            return None
        return stats_mod.litres(v, u) if key == "water_total" else stats_mod.kwh(v, u)

    def _meter_start(self, zid: str, t) -> None:
        m = self.meters
        self._meter[zid] = {
            "water0": self._total("water_total") if m.get("water_total") else None,
            "energy0": self._total("pump_energy") if m.get("pump_energy") else None,
            "flow": stats_mod.Integrator(t, self._rate("flow")) if m.get("flow") else None,
            "power": stats_mod.Integrator(t, self._rate("pump_power"), per_minute=False) if m.get("pump_power") else None,
        }

    def _meter_stop(self, zid: str, day: str, minutes: float, t) -> None:
        mt = self._meter.pop(zid, None)
        litres = kwh = None
        if mt:
            w1 = self._total("water_total") if mt["water0"] is not None else None
            e1 = self._total("pump_energy") if mt["energy0"] is not None else None
            if w1 is not None and w1 >= mt["water0"]:
                litres = w1 - mt["water0"]
            elif mt["flow"]:
                litres = mt["flow"].total(t)
            if e1 is not None and e1 >= mt["energy0"]:
                kwh = e1 - mt["energy0"]
            elif mt["power"]:
                kwh = mt["power"].total(t) / 1000.0
        stats_mod.add_zone(self.stats, day, zid, minutes, litres, kwh)
        if litres is not None and minutes >= 0.5:
            flow = litres / minutes
            warn = stats_mod.flow_check(self.flow_samples.get(zid, []), flow, self.meters.get("flow_warn", 30))
            if warn:
                name = self.zone_names().get(zid, zid)
                sk = self.lang == "sk"
                direction = ({"high": "vysok\u00fd", "low": "n\u00edzky"} if sk else {"high": "high", "low": "low"})[warn[0]]
                self._event("flow_warning", zone=name, flow=warn[1], usual=warn[2], direction=direction)
            self.flow_samples[zid] = stats_mod.push_sample(self.flow_samples.get(zid, []), flow)

    @callback
    def _on_meter(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is None:
            return
        m = self.meters
        key = "flow" if event.data.get("entity_id") == m.get("flow") else "pump_power"
        rate = self._rate(key)
        name = "flow" if key == "flow" else "power"
        for mt in list(self._meter.values()) + ([self._run_meter] if self._run_meter else []):
            integ = mt.get(name)
            if integ:
                integ.add(new.last_changed, rate)

    def _run_meter_start(self) -> None:
        m = self.meters
        now = dt_util.utcnow()
        self._run_meter = {"energy0": self._total("pump_energy") if m.get("pump_energy") else None,
                           "power": stats_mod.Integrator(now, self._rate("pump_power"), per_minute=False)
                           if m.get("pump_power") else None,
                           "flow": None}

    def _run_meter_stop(self) -> None:
        rm, self._run_meter = self._run_meter, None
        if not rm:
            return
        kwh = None
        if rm["energy0"] is not None:
            e1 = self._total("pump_energy")
            if e1 is not None and e1 >= rm["energy0"]:
                kwh = e1 - rm["energy0"]
        elif rm["power"]:
            kwh = rm["power"].total(dt_util.utcnow()) / 1000.0
        if kwh:
            stats_mod.add_pump_energy(self.stats, dt_util.now().date().isoformat(), kwh)

    # ------------------------------------------------------------------ weather
    async def refresh_weather(self) -> None:
        cfg = self.weather_cfg
        wx = {"hourly": [], "daily": [], "fallen": None, "temp": None, "updated": dt_util.utcnow().isoformat(),
              "error": None}
        if cfg["mode"] == "off":
            self.wx = wx
            return
        ent = cfg["entity"]
        if ent:
            st = self.hass.states.get(ent)
            units = {"temperature": (st.attributes.get("temperature_unit") if st else None),
                     "precipitation": (st.attributes.get("precipitation_unit") if st else None),
                     "wind_speed": (st.attributes.get("wind_speed_unit") if st else None)}
            for kind in ("hourly", "daily"):
                try:
                    resp = await self.hass.services.async_call("weather", "get_forecasts",
                                                               {"entity_id": ent, "type": kind},
                                                               blocking=True, return_response=True)
                    items = ((resp or {}).get(ent) or {}).get("forecast") or []
                    wx[kind] = wx_mod.normalise(items, units, dt_util.parse_datetime)
                except Exception as err:  # noqa: BLE001 - not every weather entity has both kinds
                    _LOGGER.debug("%s: %s forecast from %s not available: %s", self.entry.title, kind, ent, err)
            if not wx["hourly"] and not wx["daily"]:
                wx["error"] = f"{ent}: no forecast"
            if st is not None and st.attributes.get("temperature") is not None:
                wx["temp"] = wx_mod.to_c(st.attributes.get("temperature"), units["temperature"])
        if cfg["rain_sensor"]:
            v, u = self._read(cfg["rain_sensor"])
            wx["fallen"] = wx_mod.to_mm(v, u) if v is not None else None
        if cfg["temp_sensor"]:
            v, u = self._read(cfg["temp_sensor"])
            if v is not None:
                wx["temp"] = wx_mod.to_c(v, u)
        wx["current"] = self.current_conditions(cfg)
        self.wx = wx

    def current_conditions(self, cfg=None) -> Dict[str, Any]:
        """Live sensor values (deg C, %, km/h, mm, raining) for the card and the start check."""
        cfg = cfg or self.weather_cfg
        out: Dict[str, Any] = {}
        for key, conv in (("temp_sensor", wx_mod.to_c), ("wind_sensor", wx_mod.to_kmh), ("gust_sensor", wx_mod.to_kmh),
                          ("rain_sensor", wx_mod.to_mm), ("humidity_sensor", None)):
            v, u = self._read(cfg.get(key))
            if v is not None:
                out[key.split("_")[0] if key != "rain_sensor" else "rain"] = round(conv(v, u) if conv else v, 1)
        rn = cfg.get("rain_now")
        st = self.hass.states.get(rn) if rn else None
        if st is not None:
            if st.domain in ("binary_sensor", "input_boolean"):
                out["raining"] = st.state == "on"
            else:
                try:
                    out["rain_rate"] = float(st.state)
                    out["raining"] = out["rain_rate"] > 0
                except (TypeError, ValueError):
                    pass
        return out

    def _evaluate(self, base: planner.Plan, cfg_all: Dict[str, Any]):
        """Weather decisions for the runs of an un-multiplied plan -> (decisions, day factors, skip keys)."""
        try:
            cfg = wx_mod.merged(cfg_all.get("weather"))
        except wx_mod.WeatherConfigError:
            cfg = wx_mod.merged({})
        decisions: Dict[str, Dict[str, Any]] = {}
        factors: Dict[Any, float] = {}     # (day, slot id) -> factor; 0 = drop the zones that follow the weather
        skips: List[str] = []
        if cfg["mode"] == "off":
            return decisions, factors, skips
        try:
            fixed = {z.id for z in model.zones_from(self.valves, cfg_all.get("zones") or {}) if not z.weather}
        except model.ConfigError:
            fixed = set()
        now = dt_util.utcnow()
        have = bool(self.wx.get("hourly") or self.wx.get("daily") or self.wx.get("fallen") is not None
                    or self.wx.get("temp") is not None)
        last = max([x["t"] for x in (self.wx.get("hourly") or []) + (self.wx.get("daily") or [])], default=None)
        for r in base.runs:
            if r.start <= now - timedelta(minutes=1) or not have:
                continue
            if last is not None and r.start > last + timedelta(hours=24):
                continue   # beyond the forecast: no decision
            key = run_key(r)
            d = wx_mod.decide(cfg, dt_util.as_utc(r.start), now, self.wx.get("hourly"), self.wx.get("daily"),
                              self.wx.get("fallen"), self.wx.get("temp"), self.lang,
                              self.wx.get("current")).as_dict()
            if cfg["mode"] == "suggest":
                sug = self.suggestions.get(key)
                d["status"] = sug["status"] if sug else ("pending" if d["action"] != "run" else "none")
                if sug and sug["status"] == "accepted":
                    d.update({k: sug[k] for k in ("action", "factor", "reasons")})
                applied = d["status"] == "accepted"
            else:
                sug = self.suggestions.get(key)
                d["status"] = "dismissed" if sug and sug["status"] == "dismissed" else "auto"
                applied = d["status"] == "auto"
            decisions[key] = d
            if not applied:
                continue
            if d["action"] == "skip" and not (fixed & set(r.zone_ids())):
                skips.append(key)           # the whole run follows the weather: keep it in the plan, dimmed
            else:
                for sid in r.slot_ids:      # skip: drop only the weather zones; adjust: scale them
                    factors[(r.day, sid)] = 0.0 if d["action"] == "skip" else d["factor"]
        return decisions, factors, skips

    def _update_suggestions(self, horizon_h: float) -> bool:
        """Create / refresh pending suggestions for runs within the horizon. True if something new."""
        if self.weather_cfg["mode"] != "suggest":
            return False
        now = dt_util.utcnow()
        new = False
        runs = {run_key(r): r for r in (self.plan.runs if self.plan else [])}
        for key, d in self.decisions.items():
            r = runs.get(key)
            if r is None or r.start - now > timedelta(hours=horizon_h):
                continue
            sug = self.suggestions.get(key)
            if d["action"] == "run":
                if sug and sug["status"] == "pending":
                    del self.suggestions[key]
                continue
            if sug is None:
                self.suggestions[key] = {"status": "pending", "action": d["action"], "factor": d["factor"],
                                         "reasons": d["reasons"], "created": now.isoformat()}
                new = True
                self._event("suggestion", run=model.run_to_dict(r, self.zone_names()), **self._wx_vars(d))
            elif sug["status"] == "pending":
                sug.update({"action": d["action"], "factor": d["factor"], "reasons": d["reasons"]})
        for k in [k for k in self.suggestions if k not in runs]:
            del self.suggestions[k]
        return new

    def _wx_vars(self, d: Dict[str, Any]) -> Dict[str, Any]:
        sk = self.lang == "sk"
        act = {"skip": "presko\u010di\u0165" if sk else "skip",
               "adjust": "upravi\u0165" if sk else "adjust", "run": "spusti\u0165" if sk else "run"}[d["action"]]
        return {"action": act, "factor": f"{round(d['factor'] * 100)} %", "reason": ", ".join(d["reasons"])}

    async def answer_suggestion(self, key: str, accept: bool) -> None:
        sug = self.suggestions.get(key)
        if sug is None:
            raise model.ConfigError(f"no suggestion for {key}")
        sug["status"] = "accepted" if accept else "dismissed"
        await self._save()
        await self.async_replan()

    def _subscribe_dynamic(self) -> None:
        for u in self._dyn_unsubs:
            u()
        self._dyn_unsubs = []
        m = self.meters
        rates = [m[k] for k in ("flow", "pump_power") if m.get(k)]
        if rates:
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, rates, self._on_meter))
        cfg = self.weather_cfg
        watch = [cfg[k] for k in ("entity", "rain_sensor", "rain_now") if cfg["mode"] != "off" and cfg.get(k)]
        if watch:
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, watch, self._on_weather_change))

    @callback
    def _on_weather_change(self, _event: Event) -> None:
        now = dt_util.utcnow()
        if self._wx_refresh_at and now - self._wx_refresh_at < timedelta(minutes=5):
            return
        self._wx_refresh_at = now
        self.hass.async_create_task(self._periodic(now))

    def minutes_today(self, zid: str) -> float:
        return self.history.get(dt_util.now().date().isoformat(), {}).get(zid, 0.0)

    # ------------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        data = await self.store.async_load() or {}
        self.config = data.get("config") or {"zones": {}, "slots": copy.deepcopy(model.DEFAULT_SLOTS), "settings": {}}
        self.flags.update(data.get("flags") or {})
        self.skip = data.get("skip") or []
        self.active = data.get("active")
        self.history = data.get("history") or {}
        self.last_run = data.get("last_run") or {}
        self.stats = data.get("stats") or {}
        if not self.stats and self.history:
            stats_mod.seed_from_history(self.stats, self.history)
        self.flow_samples = data.get("flow_samples") or {}
        self.suggestions = data.get("suggestions") or {}
        self.skip_done = data.get("skip_done") or []
        # a zone removed by Reconfigure: drop it from the slots instead of failing the whole plan
        known = {v["id"] for v in self.valves}
        dropped = []
        for sl in self.config.get("slots") or []:
            before = len(sl.get("zones") or [])
            sl["zones"] = [z for z in sl.get("zones") or [] if z.get("zone") in known]
            if len(sl["zones"]) != before:
                dropped.append(sl.get("id"))
        for zid in list((self.config.get("zones") or {})):
            if zid not in known:
                del self.config["zones"][zid]
        if dropped:
            _LOGGER.warning("%s: removed zones dropped from slot(s) %s", self.entry.title, ", ".join(dropped))
            await self._save()
        self._valve_of = {v["valve_switch"]: v["id"] for v in self.valves if v.get("valve_switch")}
        if self._valve_of:
            self._unsubs.append(async_track_state_change_event(self.hass, list(self._valve_of), self._on_valve))
            for eid, zid in self._valve_of.items():   # open during a restart: count it from when it opened
                st = self.hass.states.get(eid)
                if st and st.state == "on":
                    self._zone_on[zid] = st.last_changed
                    self._meter_start(zid, st.last_changed)
        for ev in ("mobile_app_notification_action", "ios.notification_action_fired"):
            self._unsubs.append(self.hass.bus.async_listen(ev, self._on_action))
        main = self.controller.get("main_switch")
        if main:
            self._unsubs.append(async_track_state_change_event(self.hass, [main], self._on_main))
        self._unsubs.append(async_track_time_interval(self.hass, self._periodic, timedelta(minutes=15)))
        self._subscribe_dynamic()
        await self._resume()
        await self.refresh_weather()
        await self.async_replan()

    async def async_stop(self) -> None:
        for u in self._unsubs + self._dyn_unsubs:
            u()
        self._unsubs.clear()
        self._dyn_unsubs.clear()
        for t in (self._timer, self._watchdog, self._dry_timer, self._planned_timer):
            if t:
                t()
        self._timer = self._watchdog = self._dry_timer = self._planned_timer = None

    async def _periodic(self, _now) -> None:
        await self.refresh_weather()
        await self.async_replan()

    # ------------------------------------------------------------------ planning
    def _sun(self, day):
        rise = get_astral_event_date(self.hass, "sunrise", day)
        sset = get_astral_event_date(self.hass, "sunset", day)
        return (rise, sset) if rise and sset else None

    def compute(self, days: int = PLAN_DAYS, config: Optional[Dict[str, Any]] = None) -> planner.Plan:
        return self._compute(days, config)[0]

    def _compute(self, days: int = PLAN_DAYS, config: Optional[Dict[str, Any]] = None):
        """Plan with the weather applied -> (plan, decisions, weather skip keys)."""
        cfg = config or self.config
        zones, slots, settings = model.parse(cfg, self.valves, self.valve_overlap)
        tz = dt_util.get_default_time_zone()
        base = planner.plan(zones, slots, settings, dt_util.now().date(), days, tz, self._sun, 1.0)
        decisions, factors, skips = self._evaluate(base, cfg)
        if not factors:
            return base, decisions, skips
        final = planner.plan(zones, slots, settings, dt_util.now().date(), days, tz, self._sun,
                             lambda day, sid: factors.get((day, sid), 1.0))
        return final, decisions, skips

    async def async_replan(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None
        try:
            self.plan, self.decisions, self.wx_skip = self._compute()
            self.error = None
        except model.ConfigError as err:
            self.plan, self.next_run, self.error = None, None, str(err)
            _LOGGER.error("%s: configuration error: %s", self.entry.title, err)
            self._changed()
            return
        now = dt_util.utcnow()
        keys = {run_key(r) for r in self.plan.runs}
        changed = False
        for r in self.plan.runs:                     # a user skip whose time has come: count it once
            k = run_key(r)
            if k in self.skip and r.start <= now:
                self.skip.remove(k)
                self.skip_done.append(k)
                stats_mod.add_skip(self.stats, r.day.isoformat(), {s.zone_id: s.minutes for s in r.steps})
                changed = True
        if any(k not in keys for k in self.skip + self.skip_done):   # forget skips of runs that are gone
            self.skip = [k for k in self.skip if k in keys]
            self.skip_done = [k for k in self.skip_done if k in keys]
            changed = True
        if self._update_suggestions(self.weather_cfg["horizon"]):
            changed = True
            self.plan, self.decisions, self.wx_skip = self._compute()
        stats_mod.prune(self.stats, dt_util.now().date())
        if changed:
            await self._save()
        blocked = set(self.skip) | set(self.wx_skip)
        upcoming = [r for r in self.plan.runs if r.start > now and run_key(r) not in blocked]
        self.next_run = upcoming[0] if upcoming else None
        if self.next_run and not self.active:
            self._timer = async_track_point_in_utc_time(self.hass, self._fire, dt_util.as_utc(self.next_run.start))
        self._arm_planned_notice(now)
        self._changed()

    def _arm_planned_notice(self, now) -> None:
        if self._planned_timer:
            self._planned_timer()
            self._planned_timer = None
        run = self.next_run
        if not run or self.active:
            return
        try:
            full = notify_logic.merged(self.config.get("notifications"), self.lang)
        except notify_logic.NotifyConfigError:
            return
        e = full["events"]["planned"]
        key = run_key(run)
        if not notify_logic.targets_for(full, "planned") or key in self._noticed:
            return
        at = dt_util.as_utc(run.start) - timedelta(minutes=e["lead"])
        if at <= now:
            return
        rd, lead = model.run_to_dict(run, self.zone_names()), e["lead"]

        async def _fire(_now):
            self._planned_timer = None
            self._noticed.add(key)
            self.notify("planned", rd, lead=lead)

        self._planned_timer = async_track_point_in_utc_time(self.hass, _fire, at)

    async def _fire(self, _now) -> None:
        self._timer = None
        run = self.next_run
        if run is None:
            return
        key = run_key(run)
        if self.weather_cfg["mode"] != "off":
            await self.refresh_weather()
            try:
                self.plan, self.decisions, self.wx_skip = self._compute()
            except model.ConfigError:
                pass
            fresh = next((r for r in (self.plan.runs if self.plan else []) if run_key(r) == key), None)
            if fresh is None or fresh.start > dt_util.utcnow() + timedelta(seconds=30):
                await self.async_replan()   # moved or gone after the new forecast
                return
            run = fresh
            d = self.decisions.get(key)
            rd = model.run_to_dict(run, self.zone_names())
            if key in self.wx_skip:
                stats_mod.add_skip(self.stats, run.day.isoformat(), {s.zone_id: s.minutes for s in run.steps})
                self._event("weather", run=rd, **self._wx_vars(d))
                await self._save()
                await self.async_replan()
                return
            if d and d["action"] == "adjust" and d["status"] in ("auto", "accepted"):
                self._event("weather", run=rd, **self._wx_vars(d))
        await self.execute(run, "schedule")

    # ------------------------------------------------------------------ execution
    def _states(self) -> Dict[str, Dict[str, Any]]:
        out = {}
        for eid in executor.involved_entities(self.valves, self.controller):
            st = self.hass.states.get(eid)
            if st:
                out[eid] = {"state": st.state, "attributes": dict(st.attributes)}
        return out

    async def execute(self, run: planner.Run, source: str) -> None:
        rd = model.run_to_dict(run, self.zone_names())
        if self.active:
            self._event("skipped", reason="another run is active", run=rd, source=source)
            return
        if not self.flags["enabled"] and source == "schedule":   # the master switch stops the schedule, not manual runs
            self._event("skipped", reason="planner disabled", run=rd, source=source)
            await self.async_replan()
            return
        states = self._states()
        why = executor.precheck(run, self.valves, self.controller, states)
        if why:
            self._event("skipped", reason=why, run=rd, source=source)
            await self.async_replan()
            return
        calls = executor.start_calls(run, self.valves, self.controller, states)
        snapshot = executor.take_snapshot(self.valves, self.controller, states)
        texts = [c.as_text() for c in calls]
        pump = self.pump
        pump_off_warn = False
        if pump:
            if pump["auto_on"] and not self._pump_is_on():
                texts.insert(0, f"homeassistant.turn_on {pump['entity']} (pump; then wait {pump['delay']} s)")
            elif not pump["auto_on"] and pump["warn_if_off"] and not self._pump_is_on():
                pump_off_warn = True
        self.active = {"run": rd, "dry_run": self.flags["dry_run"], "snapshot": snapshot, "source": source,
                       "started": dt_util.utcnow().isoformat(), "expected_end": dt_util.as_utc(run.end).isoformat(),
                       "calls": texts, "actual": {}, "pump_started": False}
        self._confirmed = False
        await self._save()
        if self.active["dry_run"]:
            for t in texts:
                _LOGGER.info("%s DRY RUN would call: %s", self.entry.title, t)
            self._event("dry_run", run=rd, calls=texts, source=source)
            self._dry_timer = async_track_point_in_utc_time(self.hass, self._dry_done, dt_util.as_utc(run.end))
            self._changed()
            return
        if pump and pump["auto_on"] and not self._pump_is_on():
            await self._pump_switch(True)
            self.active["pump_started"] = True
            if pump["delay"]:
                await asyncio.sleep(pump["delay"])
        try:
            for c in calls:
                await self.hass.services.async_call(c.domain, c.service, {"entity_id": c.entity_id, **c.data},
                                                    blocking=True)
                await asyncio.sleep(0.25)
        except Exception as err:  # noqa: BLE001 - anything here must leave the ESP safe
            _LOGGER.exception("%s: starting the run failed", self.entry.title)
            await self._turn_off_main()
            await self._finish("error", reason=f"start failed: {err}")
            return
        for _ in range(40):   # wait up to 10 s for the controller to report the cycle as running
            st = self.hass.states.get(self.controller["main_switch"])
            if st and st.state == "on":
                self._confirmed = True
                break
            await asyncio.sleep(0.25)
        if not self._confirmed:
            await self._finish("error", reason="the controller did not start the cycle")
            return
        self._arm_watchdog()
        self._run_meter_start()
        stats_mod.add_run(self.stats, dt_util.now().date().isoformat())
        self._event("started", run=rd, source=source)
        if pump_off_warn and not self._pump_is_on():
            self._event("pump_off", run=rd, pump=pump["entity"], source=source)
        self._changed()

    def _arm_watchdog(self) -> None:
        if self._watchdog:
            self._watchdog()
        margin = int(self.entry.options.get(OPT_WATCHDOG, DEFAULT_WATCHDOG))
        end = dt_util.parse_datetime(self.active["expected_end"]) + timedelta(minutes=margin)
        self._watchdog = async_track_point_in_utc_time(self.hass, self._on_watchdog, end)

    async def _on_watchdog(self, _now) -> None:
        self._watchdog = None
        if self.active and not self.active.get("dry_run"):
            await self._turn_off_main()
            await self._finish("stopped", reason="watchdog: the run took longer than planned")

    async def _dry_done(self, _now) -> None:
        self._dry_timer = None
        if self.active and self.active.get("dry_run"):
            await self._finish("finished", reason="dry run")

    async def _turn_off_main(self) -> None:
        main = self.controller.get("main_switch")
        if main:
            try:
                await self.hass.services.async_call("switch", "turn_off", {"entity_id": main}, blocking=True)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("%s: could not turn off %s", self.entry.title, main)

    async def _finish(self, kind: str, reason: str = "") -> None:
        active, self.active = self.active, None
        for attr in ("_watchdog", "_dry_timer"):
            t = getattr(self, attr)
            if t:
                t()
                setattr(self, attr, None)
        self._confirmed = False
        if active and not active.get("dry_run") and self.entry.options.get(OPT_RESTORE, True):
            for c in executor.restore_calls(active.get("snapshot") or {}):
                try:
                    await self.hass.services.async_call(c.domain, c.service, {"entity_id": c.entity_id, **c.data},
                                                        blocking=True)
                except Exception:  # noqa: BLE001
                    _LOGGER.warning("%s: restore failed for %s", self.entry.title, c.entity_id)
        p = self.pump
        if active and not active.get("dry_run") and p and p["auto_off"] and active.get("pump_started"):
            await self._pump_switch(False)
        if active and not active.get("dry_run"):
            self._run_meter_stop()
        await self._save()
        actual = round(sum(((active or {}).get("actual") or {}).values()), 1)
        self._event(kind, reason=reason, run=(active or {}).get("run"), actual_minutes=actual)
        await self.async_replan()

    @callback
    def _on_main(self, event: Event) -> None:
        new = event.data.get("new_state")
        if not self.active or self.active.get("dry_run") or new is None:
            return
        if new.state == "on":
            self._confirmed = True
        elif new.state == "off" and self._confirmed:
            self.hass.async_create_task(self._finish("finished"))

    async def _resume(self) -> None:
        """After a restart: pick up a run that was active."""
        if not self.active:
            return
        if self.active.get("dry_run"):
            end = dt_util.parse_datetime(self.active["expected_end"])
            if end > dt_util.utcnow():
                self._dry_timer = async_track_point_in_utc_time(self.hass, self._dry_done, end)
            else:
                await self._finish("finished", reason="dry run (after restart)")
            return
        st = self.hass.states.get(self.controller.get("main_switch") or "")
        if st and st.state == "on":
            self._confirmed = True
            self._arm_watchdog()
        elif st and st.state == "off":
            await self._finish("finished", reason="ended while Home Assistant was restarting")
        else:
            self._confirmed = True   # ESP not connected yet: the state listener finishes it when it reports off
            self._arm_watchdog()

    # ------------------------------------------------------------------ actions
    async def set_flag(self, name: str, value: bool) -> None:
        self.flags[name] = value
        await self._save()
        await self.async_replan()

    async def configure(self, zones=None, slots=None, settings=None, notifications=None, pump=None,
                        weather=None, meters=None, ui=None) -> planner.Plan:
        new = copy.deepcopy(self.config)
        if weather is not None:
            try:
                wx_mod.merged(weather)
            except wx_mod.WeatherConfigError as err:
                raise model.ConfigError(str(err)) from err
            new["weather"] = {k: v for k, v in weather.items() if v is not None and v != ""}
        if meters is not None:
            try:
                new["meters"] = stats_mod.meters_from_dict(meters)
            except stats_mod.MetersConfigError as err:
                raise model.ConfigError(str(err)) from err
        if ui is not None:
            lang = ui.get("language") or "auto"
            if lang not in ("auto",) + notify_logic.LANGUAGES:
                raise model.ConfigError(f"ui.language: auto, {', '.join(notify_logic.LANGUAGES)}")
            title = str(ui.get("title") or "").strip()
            if len(title) > 60:
                raise model.ConfigError("ui.title: at most 60 characters")
            new["ui"] = {"language": lang, **({"title": title} if title else {})}
        if notifications is not None:
            try:
                notify_logic.merged(notifications)
            except notify_logic.NotifyConfigError as err:
                raise model.ConfigError(str(err)) from err
            new["notifications"] = notifications
        if pump is not None:
            new["pump"] = model.pump_from_dict(pump)
        if zones is not None:
            new["zones"] = zones
        if slots is not None:
            new["slots"] = slots
        if settings is not None:
            new["settings"] = settings
        result = self.compute(days=7, config=new)   # raises ConfigError
        resub = (new.get("weather"), new.get("meters")) != (self.config.get("weather"), self.config.get("meters"))
        self.config = new
        await self._save()
        if resub:
            self._subscribe_dynamic()
            await self.refresh_weather()
        await self.async_replan()
        return result

    async def run_slot(self, slot_id: str) -> None:
        zones, slots, settings = model.parse(self.config, self.valves, self.valve_overlap)
        slot = next((s for s in slots if s.id == slot_id), None)
        if slot is None:
            raise model.ConfigError(f"slot {slot_id!r} does not exist")
        now = dt_util.now() + timedelta(seconds=2)
        manual = dataclasses.replace(slot, anchor=planner.Anchor("start", "time", now.time().replace(microsecond=0)),
                                     days=None, every_n_days=None, enabled=True,
                                     zones=tuple(dataclasses.replace(z, days=None) for z in slot.zones))
        plan = planner.plan(zones, [manual], settings, now.date(), 1, dt_util.get_default_time_zone())
        if not plan.runs:
            raise model.ConfigError(f"slot {slot_id!r} has no enabled zones")
        await self.execute(plan.runs[0], "manual")

    async def run_zone(self, zone_id: str, minutes: float) -> None:
        await self.quick_run([{"zone": zone_id, "minutes": minutes}], reverse=False)

    async def quick_run(self, items: List[Dict[str, Any]], reverse: bool = False) -> None:
        """Run the given zones once, now, in ESP order (or reverse), minutes as given (no multiplier)."""
        zones, _slots, settings = model.parse(self.config, self.valves, self.valve_overlap)
        known = {z.id: z for z in zones}
        entries = []
        for it in items or []:
            zid, minutes = it.get("zone"), float(it.get("minutes") or 0)
            if zid not in known:
                raise model.ConfigError(f"zone {zid!r} does not exist")
            if not known[zid].enabled:
                raise model.ConfigError(f"zone {known[zid].name} is disabled")
            if not 0 < minutes <= 600:
                raise model.ConfigError(f"zone {known[zid].name}: minutes 0 .. 600")
            entries.append(planner.SlotZone(zid, minutes))
        if not entries:
            raise model.ConfigError("pick at least one zone")
        now = dt_util.now() + timedelta(seconds=2)
        slot = planner.Slot("quick", "Quick run", planner.Anchor("start", "time", now.time().replace(microsecond=0)),
                            tuple(entries), reverse=bool(reverse), use_multiplier=False)
        plan = planner.plan(zones, [slot], settings, now.date(), 1, dt_util.get_default_time_zone())
        if not plan.runs:
            raise model.ConfigError("nothing to run")
        await self.execute(plan.runs[0], "manual")

    async def unskip(self, key: Optional[str] = None) -> Optional[str]:
        """Undo a skip (the given run key, or the earliest one). Also undoes an accepted weather skip."""
        key = key or (sorted(self.skip)[0] if self.skip else None)
        if key is None:
            return None
        if key in self.skip:
            self.skip.remove(key)
        elif key in self.suggestions and self.suggestions[key]["action"] == "skip":
            self.suggestions[key]["status"] = "dismissed"
        elif key in self.wx_skip:
            self.suggestions[key] = {"status": "dismissed", "action": "skip", "factor": 0, "reasons": ["undone"],
                                     "created": dt_util.utcnow().isoformat()}
        else:
            raise model.ConfigError(f"run {key} is not skipped")
        await self._save()
        await self.async_replan()
        return key

    async def stop(self) -> None:
        if not self.active:
            return
        if self.active.get("dry_run"):
            await self._finish("stopped", reason="stopped by user (dry run)")
        else:
            await self._turn_off_main()
            if self.active:   # the state listener may not have fired yet
                await self._finish("stopped", reason="stopped by user")

    async def skip_run(self, key: str) -> str:
        """Skip one planned run (key 'YYYY-MM-DD|slot[+slot]')."""
        run = next((r for r in (self.plan.runs if self.plan else []) if run_key(r) == key), None)
        if run is None or run.start <= dt_util.utcnow():
            raise model.ConfigError(f"no upcoming run {key}")
        if key not in self.skip:
            self.skip.append(key)
            await self._save()
            self._event("skip_set", run=model.run_to_dict(run, self.zone_names()))
            await self.async_replan()
        return key

    async def skip_next(self) -> Optional[str]:
        if not self.next_run:
            return None
        key = run_key(self.next_run)
        self.skip.append(key)
        await self._save()
        self._event("skip_set", run=model.run_to_dict(self.next_run, self.zone_names()))
        await self.async_replan()
        return key

    def zone_next(self, zid: str):
        """(start, minutes) of the next planned run that waters this zone, or (None, None)."""
        now = dt_util.utcnow()
        for r in (self.plan.runs if self.plan else []):
            if r.start > now and run_key(r) not in self.skip and run_key(r) not in self.wx_skip:
                for st in r.steps:
                    if st.zone_id == zid:
                        return r.start, st.minutes
        return None, None

    def plan_dict(self, days: int = 7, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            p, decisions, wx_skip = self._compute(days=days, config=config)
        except model.ConfigError as err:
            return {"error": str(err), "runs": [], "conflicts": []}
        names = self.zone_names()
        return {"runs": [model.run_to_dict(r, names) for r in p.runs],
                "conflicts": [{"kind": c.kind, "day": c.day.isoformat(), "slots": list(c.slot_ids), "message": c.message}
                              for c in p.conflicts],
                "skipped": list(self.skip) + list(self.skip_done), "weather": decisions, "weather_skipped": wx_skip,
                "suggestions": {k: v for k, v in self.suggestions.items() if v.get("status") == "pending"}}
