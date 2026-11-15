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

from . import blockers as blk_mod, executor, leak as leak_mod, model, notify_logic, planner, stats as stats_mod, weather as wx_mod
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
        self._actor: Optional[str] = None     # HA user behind the service call / notification button being handled
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
        self._sim_timers: List[Callable[[], None]] = []
        # milestone 5: weather, suggestions, stats
        self.wx: Dict[str, Any] = {"hourly": [], "daily": [], "fallen": None, "temp": None, "updated": None, "error": None}
        self.decisions: Dict[str, Dict[str, Any]] = {}   # run key -> weather decision (+ status)
        self.wx_skip: List[str] = []                      # run keys skipped because of the weather
        self.suggestions: Dict[str, Dict[str, Any]] = {}  # run key -> {status, action, factor, reasons, ...}
        self.skip_done: List[str] = []                    # user skips whose start has passed (shown dimmed)
        self.stats: Dict[str, Any] = {}
        self.flow_samples: Dict[str, List[float]] = {}
        self.log: List[Dict[str, Any]] = []               # event log for the card (newest last, 500 entries)
        self.pause_until: Optional[str] = None            # local date, inclusive: no scheduled runs until then
        self.held: Optional[Dict[str, Any]] = None        # a run waiting for a blocker: key, until, mode, reasons
        self._held_timer = None
        self.leak = leak_mod.LeakWatch()
        self.leak_alarm: Optional[Dict[str, Any]] = None   # active alarm for the card
        self.leak_snooze_until: Optional[str] = None
        self._last_end: Optional[datetime] = None
        self._last_zone: Optional[str] = None
        self._stuck_timer = None
        self.tmax_log: Dict[str, float] = {}             # local day -> highest temperature seen (deg C), 30 days
        self.rain_log: List[List[Any]] = []               # [iso time, mm] increments of the rain counter (72 h)
        self._rain_last: Optional[float] = None           # last reading of the rain counter, mm
        self._rain_entity: Optional[str] = None
        self.flow_base: Dict[str, Dict[str, Any]] = {}    # zone -> {"flow": L/min, "since": iso, "warned": bool}
        self._base_samples: Dict[str, List[float]] = {}   # first runs after setup / reset (for the baseline)
        self._meter: Dict[str, Dict[str, Any]] = {}       # zone id -> readings while open
        self._run_meter: Optional[Dict[str, Any]] = None  # pump energy over the whole run
        self._dyn_unsubs: List[Callable[[], None]] = []
        self._wx_refresh_at = None
        self.health: Dict[str, Any] = {"missing": [], "unavailable": [], "since": None, "notified": False}
        self._health_timer = None

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
        if self.health["missing"] or self.health["unavailable"]:
            return "offline"
        if self.active:
            return "dry_run" if self.active.get("dry_run") else "running"
        if not self.flags["enabled"]:
            return "disabled"
        if self.paused:
            return "paused"
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
    def blockers(self) -> List[Dict[str, Any]]:
        try:
            return blk_mod.from_list(self.config.get("blockers"))
        except blk_mod.BlockerConfigError:
            return []

    @property
    def paused(self) -> bool:
        return bool(self.pause_until and dt_util.now().date().isoformat() <= self.pause_until)

    @property
    def leak_cfg(self) -> Dict[str, Any]:
        try:
            return leak_mod.merged(self.config.get("leak"))
        except leak_mod.LeakConfigError:
            return leak_mod.merged({})

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
                                     "flow_base": self.flow_base, "base_samples": self._base_samples,
                                     "rain_log": self.rain_log, "rain_last": self._rain_last, "tmax_log": self.tmax_log,
                                     "leak_snooze_until": self.leak_snooze_until, "pause_until": self.pause_until,
                                     "log": self.log,
                                     "rain_entity": self._rain_entity,
                                     "suggestions": self.suggestions, "skip_done": self.skip_done})

    LOG_KINDS = {"started", "finished", "stopped", "skipped", "error", "weather", "suggestion", "blocked", "blocker_ask",
                 "leak", "valve_stuck", "flow_warning", "flow_drift", "offline", "online", "paused", "resumed", "skip_set",
                 "pump_off"}

    ACTOR_KINDS = {"started", "stopped", "skipped", "skip_set", "paused", "resumed", "blocked", "suggestion"}

    async def set_actor(self, user_id: Optional[str]) -> None:
        """Remember who triggered the action being handled (shown as "by" in the log)."""
        name = None
        if user_id:
            user = await self.hass.auth.async_get_user(user_id)
            name = (user.name if user else None) or None
        self._actor = name

    async def _as_user(self, user_id: Optional[str], coro) -> None:
        await self.set_actor(user_id)
        try:
            await coro
        finally:
            self._actor = None

    def _log_event(self, kind: str, data: Dict[str, Any]) -> None:
        rr = data.get("run") or {}
        entry = {"t": dt_util.utcnow().isoformat(), "kind": kind,
                 "slots": rr.get("slots"), "day": rr.get("day"), "start": rr.get("start"),
                 "zones": [z.get("name") for z in rr.get("zones") or []] or None,
                 "pass": f"{rr.get('pass_no')}/{rr.get('passes')}" if (rr.get("passes") or 1) > 1 else None,
                 "dry": bool(data.get("dry") or (kind in ("started", "finished", "stopped") and self.flags.get("dry_run")))}
        for k in ("reason", "action", "factor", "zone", "flow", "usual", "minutes", "since", "until", "actual_minutes",
                  "water_l", "energy_kwh", "cost", "source"):
            if data.get(k) not in (None, "", []):
                entry[k] = data[k]
        if self._actor and kind in self.ACTOR_KINDS:
            entry["by"] = self._actor
        self.log.append({k: v for k, v in entry.items() if v not in (None, False)})
        del self.log[:-500]

    def _event(self, kind: str, **data) -> None:
        if kind in self.LOG_KINDS:
            self._log_event(kind, data)
            self.hass.async_create_task(self._save())
        payload = {"entry_id": self.entry.entry_id, "type": kind, **data}
        self.last_event = {**payload, "time": dt_util.utcnow().isoformat()}
        self._changed()
        self.hass.bus.async_fire(EVENT, payload)
        _LOGGER.info("%s: %s %s", self.entry.title, kind, data.get("reason") or "")
        rr = data.get("run") or {}
        if (rr.get("passes") or 1) > 1:     # cycle & soak: one started / finished for the whole slot run
            if (kind in ("planned", "started", "dry_run") and rr.get("pass_no", 1) != 1) or \
               (kind == "finished" and rr.get("pass_no") != rr.get("passes")):
                return
        if kind in notify_logic.EVENTS:
            extra = {k: v for k, v in data.items() if k not in ("run", "calls")}
            if kind in ("planned", "started", "skipped"):
                extra.setdefault("expected_water_l", self.expected_water(data.get("run")))
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
        # dry run: everything is sent like for real, marked so it cannot be mistaken for watering
        if extra.get("dry") or (self.flags.get("dry_run") and event in ("planned", "skipped", "weather", "suggestion")):
            title = ("\U0001f9ea Sk\u00fa\u0161ka: " if self.lang == "sk" else "\U0001f9ea Test: ") + title
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
                 "direction": "high", "baseline": 14.2, "change": -18, "since": "01.05.2026",
                 "water_l": 245.5, "energy_kwh": 0.42, "avg_flow": 12.3,
                 "cost": f"0.89 {self.hass.config.currency or ''}".strip(), "expected_water_l": 250}
        return await self._send(event, rd, extra, force=targets, override=override)

    @callback
    def _on_action(self, event: Event) -> None:
        parsed = notify_logic.parse_action(event.data.get("action") or event.data.get("actionName") or "")
        if not parsed or parsed[1] != self.entry.entry_id:
            return
        name = parsed[0]
        uid = event.context.user_id if event.context else None
        _LOGGER.info("%s: notification action %s", self.entry.title, name)
        if name == "stop":
            self.hass.async_create_task(self._as_user(uid, self.stop()))
        elif name == "skip":
            self.hass.async_create_task(self._as_user(uid, self.skip_next()))
        elif name == "pump_on":
            self.hass.async_create_task(self._as_user(uid, self._pump_switch(True, by_user=True)))
        elif name in ("blk_run", "blk_skip", "blk_wait") and self.held:
            self.hass.async_create_task(self._as_user(uid, self.answer_blocker({"blk_run": "run", "blk_skip": "skip", "blk_wait": "wait"}[name])))
        elif name == "leak_snooze":
            self.hass.async_create_task(self._as_user(uid, self.leak_snooze()))
        elif name == "pump_off":
            self.hass.async_create_task(self._as_user(uid, self._pump_switch(False)))
        elif name in ("accept", "dismiss"):
            pend = sorted(k for k, v in self.suggestions.items() if v.get("status") == "pending")
            if pend:
                self.hass.async_create_task(self._as_user(uid, self.answer_suggestion(pend[0], name == "accept")))

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
        if self.active and not self.active.get("dry_run"):
            m = self.active.setdefault("metered", {"l": 0.0, "kwh": 0.0, "lmin": 0.0, "has_l": False, "has_kwh": False})
            if litres is not None:
                m["l"] += litres
                m["lmin"] += minutes
                m["has_l"] = True
            if kwh is not None:
                m["kwh"] += kwh
                m["has_kwh"] = True
        if litres is not None and minutes >= 0.5:
            flow = litres / minutes
            warn = stats_mod.flow_check(self.flow_samples.get(zid, []), flow, self.meters.get("flow_warn", 30))
            if warn:
                name = self.zone_names().get(zid, zid)
                sk = self.lang == "sk"
                direction = ({"high": "vysok\u00fd", "low": "n\u00edzky"} if sk else {"high": "high", "low": "low"})[warn[0]]
                self._event("flow_warning", zone=name, flow=warn[1], usual=warn[2], direction=direction)
            self.flow_samples[zid] = stats_mod.push_sample(self.flow_samples.get(zid, []), flow)
            self._track_baseline(zid, flow)

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

    def _run_meter_stop(self) -> Optional[float]:
        rm, self._run_meter = self._run_meter, None
        if not rm:
            return None
        kwh = None
        if rm["energy0"] is not None:
            e1 = self._total("pump_energy")
            if e1 is not None and e1 >= rm["energy0"]:
                kwh = e1 - rm["energy0"]
        elif rm["power"]:
            kwh = rm["power"].total(dt_util.utcnow()) / 1000.0
        if kwh:
            stats_mod.add_pump_energy(self.stats, dt_util.now().date().isoformat(), kwh)
        return kwh

    def _track_baseline(self, zid: str, flow: float) -> None:
        base = self.flow_base.get(zid)
        if base is None:
            got = self._base_samples.setdefault(zid, [])
            got.append(round(flow, 2))
            b = stats_mod.baseline_from(got)
            if b is not None:
                self.flow_base[zid] = {"flow": b, "since": dt_util.utcnow().isoformat(), "warned": False}
                self._base_samples.pop(zid, None)
            return
        drift = stats_mod.drift_check(base["flow"], self.flow_samples.get(zid, []), self.meters.get("drift_warn", 15))
        if drift and not base.get("warned"):
            base["warned"] = True
            since = dt_util.as_local(dt_util.parse_datetime(base["since"])).strftime("%d.%m.%Y")
            self._event("flow_drift", zone=self.zone_names().get(zid, zid), flow=drift[0], baseline=drift[1],
                        change=drift[2], since=since)
        elif not drift and base.get("warned"):
            base["warned"] = False          # back to normal (e.g. filter cleaned): warn again next time

    async def reset_flow(self, zone: Optional[str] = None) -> List[str]:
        """Forget the normal flow of one zone (or all): the next runs define it again."""
        zones = [zone] if zone else list({*self.flow_base, *self.flow_samples, *self._base_samples})
        for z in zones:
            self.flow_base.pop(z, None)
            self.flow_samples.pop(z, None)
            self._base_samples.pop(z, None)
        await self._save()
        self._changed()
        return zones

    async def clear_stats(self) -> None:
        """Delete all statistics (minutes, water, energy, skips) and the flow baselines."""
        self.stats = {}
        self.history = {}
        self.last_run = {}
        await self.reset_flow()

    def _usage(self, metered: Optional[Dict[str, Any]], run_kwh: Optional[float]) -> Dict[str, Any]:
        """Water / energy / cost of a finished run for the notification variables (None = no meter)."""
        m = metered or {}
        water = round(m["l"], 1) if m.get("has_l") else None
        kwh = run_kwh if run_kwh is not None else (m["kwh"] if m.get("has_kwh") else None)
        kwh = round(kwh, 3) if kwh is not None else None
        meters = self.meters
        cost = None
        if (water is not None and meters.get("water_price")) or (kwh is not None and meters.get("energy_price")):
            c = (water or 0) / 1000 * (meters.get("water_price") or 0) + (kwh or 0) * (meters.get("energy_price") or 0)
            cost = f"{c:.2f} {self.hass.config.currency or ''}".strip()
        avg = round(m["l"] / m["lmin"], 1) if m.get("has_l") and m.get("lmin") else None
        return {"water_l": water, "energy_kwh": kwh, "cost": cost, "avg_flow": avg}

    def expected_water(self, run: Optional[Dict[str, Any]]) -> Optional[float]:
        """Litres a run will use from each zone's usual flow; None until every zone has samples."""
        if not run:
            return None
        total = 0.0
        for z in run.get("zones") or []:
            s = sorted(self.flow_samples.get(z["zone"]) or [])
            if not s:
                return None
            total += s[len(s) // 2] * float(z["minutes"])
        return round(total, 0)

    # ------------------------------------------------------------------ leak alarm
    def _leak_quiet(self, now) -> bool:
        """No alarm while watering, shortly before a run and shortly after one."""
        c = self.leak_cfg
        if self.active and not self.active.get("dry_run"):
            return True
        if self.next_run and dt_util.as_utc(self.next_run.start) - now <= timedelta(minutes=c["quiet_before"]):
            return True
        return bool(self._last_end and now - self._last_end <= timedelta(minutes=c["quiet_after"]))

    def _leak_snoozed(self, now) -> bool:
        return bool(self.leak_snooze_until and dt_util.parse_datetime(self.leak_snooze_until) > now)

    @callback
    def _leak_check(self, *_args) -> None:
        if not self.meters.get("flow"):
            return
        now = dt_util.utcnow()
        flow = self._rate("flow")
        c = self.leak_cfg
        hit = self.leak.step(c, now, flow, self._leak_quiet(now), self._leak_snoozed(now), dt_util.as_local(now))
        was = self.leak_alarm
        if hit:
            since = dt_util.as_local(self.leak.since).strftime("%H:%M")
            self.leak_alarm = {"since": self.leak.since.isoformat(), "flow": round(flow, 1)}
            self._event("leak", flow=round(flow, 1), minutes=round(self.leak.minutes(now)), since=since)
            if c["pump_off"]:
                self.hass.async_create_task(self._pump_switch(False))
        elif was and not self.leak.alarmed:
            self.leak_alarm = None             # flow stopped (or a run took over)
        if was != self.leak_alarm:
            self._changed()

    async def leak_snooze(self, minutes: Optional[float] = None) -> str:
        until = dt_util.utcnow() + timedelta(minutes=minutes or self.leak_cfg["snooze"])
        self.leak_snooze_until = until.isoformat()
        self.leak_alarm = None
        self.leak.alarmed = False
        self.leak.since = None
        await self._save()
        self._changed()
        return self.leak_snooze_until

    def _arm_stuck_check(self) -> None:
        c = self.leak_cfg
        if self._stuck_timer:
            self._stuck_timer()
            self._stuck_timer = None
        if c["mode"] != "on" or not c["stuck"] or not self.meters.get("flow"):
            return

        async def _check(_now):
            self._stuck_timer = None
            flow = self._rate("flow")
            if self.active or flow is None or flow < c["min_flow"] or self._leak_snoozed(dt_util.utcnow()):
                return
            self._event("valve_stuck", flow=round(flow, 1), zone=self._last_zone or "-", minutes=round(c["stuck"]))
            if c["pump_off"]:
                await self._pump_switch(False)

        self._stuck_timer = async_track_point_in_utc_time(self.hass, _check, dt_util.utcnow() + timedelta(minutes=c["stuck"]))

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
            # tracked from every change of the counter, so a daily sensor that reset at midnight
            # still counts last evening's rain for the morning run
            wx["fallen"] = self.fallen(cfg["rain_window"])
        if cfg["temp_sensor"]:
            v, u = self._read(cfg["temp_sensor"])
            if v is not None:
                wx["temp"] = wx_mod.to_c(v, u)
        wx["current"] = self.current_conditions(cfg)
        self.wx = wx

    # ------------------------------------------------------------------ rain log
    def _rain_mm(self, state) -> Optional[float]:
        try:
            return wx_mod.to_mm(float(state.state), state.attributes.get("unit_of_measurement"))
        except (TypeError, ValueError, AttributeError):
            return None

    def fallen(self, hours: float) -> float:
        now = dt_util.utcnow()
        ev = [(dt_util.parse_datetime(t), mm) for t, mm in self.rain_log]
        return wx_mod.fallen_since([(t, mm) for t, mm in ev if t], now, hours)

    def _prune_rain(self) -> None:
        cut = (dt_util.utcnow() - timedelta(hours=72)).isoformat()
        self.rain_log = [e for e in self.rain_log if e[0] >= cut]

    @callback
    def _on_rain(self, event: Event) -> None:
        new = event.data.get("new_state")
        v = self._rain_mm(new) if new is not None else None
        if v is None:
            return                         # unavailable: keep the last reading, no rain counted
        inc = wx_mod.rain_increment(self._rain_last, v)
        self._rain_last = v
        if inc > 0:
            self.rain_log.append([new.last_changed.isoformat(), round(inc, 2)])
            self._prune_rain()
            _LOGGER.debug("%s: rain +%.1f mm (counter %.1f)", self.entry.title, inc, v)
        self.hass.async_create_task(self._save())

    async def _seed_rain(self, entity: str) -> None:
        """Fill the rain log from the recorder (last 72 h) for a new rain sensor, or after a gap."""
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import state_changes_during_period
        except ImportError:
            return
        start = dt_util.utcnow() - timedelta(hours=72)
        try:
            hist = await get_instance(self.hass).async_add_executor_job(
                state_changes_during_period, self.hass, start, None, entity, True, False, None, True)
        except Exception as err:  # noqa: BLE001 - recorder off / not ready: start tracking from now
            _LOGGER.debug("%s: no rain history for %s: %s", self.entry.title, entity, err)
            return
        unit = (self.hass.states.get(entity).attributes.get("unit_of_measurement")
                if self.hass.states.get(entity) else None)
        readings = []
        for st in hist.get(entity, []):
            try:
                readings.append((st.last_changed, wx_mod.to_mm(float(st.state), unit)))
            except (TypeError, ValueError):
                continue
        if not readings:
            return
        known = {e[0] for e in self.rain_log}
        for t, mm in wx_mod.increments(readings):
            if t.isoformat() not in known:
                self.rain_log.append([t.isoformat(), mm])
        self.rain_log.sort()
        self._rain_last = readings[-1][1]
        self._prune_rain()
        _LOGGER.info("%s: rain history of %s: %.1f mm in the last %d h", self.entry.title, entity,
                     self.fallen(self.weather_cfg["rain_window"]), self.weather_cfg["rain_window"])

    async def _setup_rain(self) -> None:
        ent = self.weather_cfg.get("rain_sensor") if self.weather_cfg["mode"] != "off" else None
        if ent != self._rain_entity:            # another sensor: its own history, not the old one's
            self.rain_log, self._rain_last, self._rain_entity = [], None, ent
        if ent:
            await self._seed_rain(ent)
            if self._rain_last is None:          # no history yet: count from the current reading on
                st = self.hass.states.get(ent)
                self._rain_last = self._rain_mm(st) if st is not None else None
        await self._save()

    # ------------------------------------------------------------------ daily maximum log (weekly average)
    def _temp_source(self) -> Optional[str]:
        cfg = self.weather_cfg
        return cfg.get("temp_sensor") or cfg.get("entity") if cfg["mode"] != "off" else None

    def _temp_of(self, st) -> Optional[float]:
        if st is None:
            return None
        try:
            # recorder history states have no .domain: take it from the entity id
            if str(getattr(st, "entity_id", "")).startswith("weather."):
                return wx_mod.to_c(st.attributes.get("temperature"), st.attributes.get("temperature_unit"))
            return wx_mod.to_c(float(st.state), st.attributes.get("unit_of_measurement"))
        except (TypeError, ValueError):
            return None

    def _log_tmax(self, when, value: Optional[float]) -> bool:
        if value is None:
            return False
        day = dt_util.as_local(when).date().isoformat()
        if self.tmax_log.get(day) is None or value > self.tmax_log[day]:
            self.tmax_log[day] = round(value, 1)
            cut = (dt_util.now().date() - timedelta(days=30)).isoformat()
            for k in [k for k in self.tmax_log if k < cut]:
                del self.tmax_log[k]
            return True
        return False

    @callback
    def _on_temp(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is not None and self._log_tmax(new.last_changed, self._temp_of(new)):
            self.hass.async_create_task(self._save())

    async def _seed_tmax(self) -> None:
        """Fill missing days of the daily-max log from the recorder (14 days)."""
        ent = self._temp_source()
        if not ent:
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.history import state_changes_during_period
            start = dt_util.utcnow() - timedelta(days=14)
            hist = await get_instance(self.hass).async_add_executor_job(
                state_changes_during_period, self.hass, start, None, ent, False, False, None, True)
        except Exception as err:  # noqa: BLE001 - recorder off: the log fills from now on
            _LOGGER.debug("%s: no temperature history for %s: %s", self.entry.title, ent, err)
            return
        try:
            for st in hist.get(ent, []):
                self._log_tmax(st.last_changed, self._temp_of(st))
        except Exception as err:  # noqa: BLE001 - a bad history row must never stop the planner
            _LOGGER.warning("%s: temperature history of %s not used: %s", self.entry.title, ent, err)
        st = self.hass.states.get(ent)
        if st is not None:
            self._log_tmax(st.last_changed, self._temp_of(st))
        await self._save()

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
            zone_cfg = {z.id: z for z in model.zones_from(self.valves, cfg_all.get("zones") or {})}
            _z, slot_list, _st = model.parse(cfg_all, self.valves, self.valve_overlap)
            slot_weather = {sl.id: sl.use_multiplier for sl in slot_list}
        except model.ConfigError:
            zone_cfg, slot_weather = {}, {}
        names = self.zone_names()
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
            # steps the weather may change: zone follows the weather AND its slot has "adjust by weather"
            follows = [st for st in r.steps
                       if (zone_cfg.get(st.zone_id) is None or zone_cfg[st.zone_id].weather)
                       and slot_weather.get(st.slot_id, True)]
            if not follows:
                continue                    # nothing in this run listens to the weather: no decision
            kept = [names.get(st.zone_id, st.zone_id) for st in r.steps if st not in follows]
            d = wx_mod.decide(cfg, dt_util.as_utc(r.start), now, self.wx.get("hourly"), self.wx.get("daily"),
                              self.wx.get("fallen"), self.wx.get("temp"), self.lang,
                              self.wx.get("current"), self.tmax_log,
                              dt_util.as_local(r.start).date()).as_dict()
            if cfg["mode"] == "suggest":
                sug = self.suggestions.get(key)
                if sug and sug.get("status") in ("accepted", "dismissed") and cfg["answers"] == "follow" \
                        and d["action"] != sug.get("asked", sug["action"]):
                    sug = None                  # the forecast now says something else: ask again
                d["status"] = sug["status"] if sug else ("pending" if d["action"] != "run" else "none")
                if sug and sug["status"] == "accepted" and cfg["answers"] == "keep":
                    d.update({k: sug[k] for k in ("action", "factor", "reasons")})   # frozen at accept time
                applied = d["status"] == "accepted"
            else:
                sug = self.suggestions.get(key)
                d["status"] = "dismissed" if sug and sug["status"] == "dismissed" else "auto"
                applied = d["status"] == "auto"
            if kept:
                d["partial"] = True          # the weather changes only part of the run
                d["kept"] = kept
                d["changed"] = len(follows)
                d["total"] = len(r.steps)
            decisions[key] = d
            if not applied:
                continue
            if d["action"] == "skip" and not kept:
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
            if sug is None or (sug.get("status") != "pending" and d["status"] == "pending"):
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

    async def answer_suggestion(self, key: str, accept: Optional[bool]) -> None:
        """accept True / False answers the suggestion; None takes the answer back (undecided again)."""
        if accept is None:
            if self.suggestions.pop(key, None) is None:
                raise model.ConfigError(f"run {key} has no answered suggestion")
            await self._save()
            await self.async_replan()
            return
        await self._answer(key, accept)

    async def _answer(self, key: str, accept: bool) -> None:
        sug = self.suggestions.get(key)
        if sug is None:
            # runs beyond the suggestion horizon show the weather decision too: answering creates it
            d = self.decisions.get(key)
            if d is None or d["action"] == "run":
                raise model.ConfigError(f"no weather suggestion for {key}")
            sug = self.suggestions[key] = {"action": d["action"], "factor": d["factor"], "reasons": d["reasons"],
                                           "created": dt_util.utcnow().isoformat()}
        live = self.decisions.get(key) or {}
        if live.get("action") and live["action"] != "run":
            sug.update({"action": live["action"], "factor": live["factor"], "reasons": live["reasons"]})
        sug["asked"] = sug["action"]
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
        if m.get("flow") and self.leak_cfg["mode"] == "on":
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, [m["flow"]], self._leak_check))
            self._dyn_unsubs.append(async_track_time_interval(self.hass, self._leak_check, timedelta(minutes=1)))
        cfg = self.weather_cfg
        watch = [cfg[k] for k in ("entity", "rain_sensor", "rain_now") if cfg["mode"] != "off" and cfg.get(k)]
        if watch:
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, watch, self._on_weather_change))
        if cfg["mode"] != "off" and cfg.get("rain_sensor"):
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, [cfg["rain_sensor"]], self._on_rain))
        if self._temp_source():
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, [self._temp_source()], self._on_temp))
        bents = sorted({b["entity"] for b in self.blockers})
        if bents:
            self._dyn_unsubs.append(async_track_state_change_event(self.hass, bents, self._on_blocker_state))

    @callback
    def _on_weather_change(self, _event: Event) -> None:
        now = dt_util.utcnow()
        if self._wx_refresh_at and now - self._wx_refresh_at < timedelta(minutes=5):
            return
        self._wx_refresh_at = now
        self.hass.async_create_task(self._periodic(now))

    # ------------------------------------------------------------------ controller health
    OFFLINE_GRACE = timedelta(minutes=3)   # short ESP reconnects do not notify

    @callback
    def _on_controller_state(self, _event: Event) -> None:
        self._check_health()

    def _check_health(self, startup: bool = False) -> None:  # noqa: ARG002 - startup: same grace period
        states = {eid: {"state": st.state} for eid in executor.involved_entities(self.valves, self.controller)
                  if (st := self.hass.states.get(eid)) is not None}
        h = executor.health(self.valves, self.controller, states)
        bad = bool(h["missing"] or h["unavailable"])
        was_bad = bool(self.health["missing"] or self.health["unavailable"])
        if bad and not was_bad:
            self.health.update(h, since=dt_util.utcnow().isoformat(), notified=False)
            if self._health_timer:
                self._health_timer()
            # at startup the ESP may simply not be connected yet: give it the grace period too
            self._health_timer = async_track_point_in_utc_time(self.hass, self._health_notify,
                                                               dt_util.utcnow() + self.OFFLINE_GRACE)
            _LOGGER.warning("%s: controller %s: %s", self.entry.title,
                            "entities missing" if h["missing"] else "unavailable",
                            ", ".join(h["missing"] or h["unavailable"]))
            self._changed()
        elif bad:
            self.health.update(h)
            self._changed()
        elif was_bad:
            since, notified = self.health["since"], self.health["notified"]
            self.health = {"missing": [], "unavailable": [], "since": None, "notified": False}
            if self._health_timer:
                self._health_timer()
                self._health_timer = None
            _LOGGER.info("%s: controller back online", self.entry.title)
            if notified:
                self._event("online", since=self._local_hm(since))
            self._changed()

    def _local_hm(self, iso: Optional[str]) -> str:
        return dt_util.as_local(dt_util.parse_datetime(iso)).strftime("%d.%m. %H:%M") if iso else ""

    async def _health_notify(self, _now) -> None:
        self._health_timer = None
        h = self.health
        if not (h["missing"] or h["unavailable"]) or h["notified"]:
            return
        h["notified"] = True
        def short(ids):
            return ", ".join(ids[:3]) + (f" and {len(ids) - 3} more" if len(ids) > 3 else "")
        reason = (f"{len(h['missing'])} entities not found (device removed or renamed?): {short(h['missing'])}"
                  if h["missing"] else f"unavailable: {short(h['unavailable'])}")
        self._event("offline", reason=reason, since=self._local_hm(h["since"]))

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
        self.flow_base = data.get("flow_base") or {}
        self.rain_log = data.get("rain_log") or []
        self.tmax_log = data.get("tmax_log") or {}
        self.leak_snooze_until = data.get("leak_snooze_until")
        self.pause_until = data.get("pause_until")
        self.log = data.get("log") or []
        self._rain_last = data.get("rain_last")
        self._rain_entity = data.get("rain_entity")
        self._base_samples = data.get("base_samples") or {}
        self.suggestions = data.get("suggestions") or {}
        if (self.config.get("weather") or {}).get("mode", "off") != "suggest":
            self.suggestions = {k: v for k, v in self.suggestions.items() if v.get("status") != "pending"}
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
        watched = executor.involved_entities(self.valves, self.controller)
        if watched:
            self._unsubs.append(async_track_state_change_event(self.hass, watched, self._on_controller_state))
        self._check_health(startup=True)
        self._unsubs.append(async_track_time_interval(self.hass, self._periodic, timedelta(minutes=15)))
        self._subscribe_dynamic()
        await self._setup_rain()
        await self._seed_tmax()
        await self._resume()
        await self.refresh_weather()
        await self.async_replan()
        self._update_repairs()

    async def async_stop(self) -> None:
        for u in self._unsubs + self._dyn_unsubs:
            u()
        self._unsubs.clear()
        self._dyn_unsubs.clear()
        self._cancel_sim()
        if self._stuck_timer:
            self._stuck_timer()
            self._stuck_timer = None
        if self._held_timer:
            self._held_timer()
            self._held_timer = None
        for t in (self._timer, self._watchdog, self._dry_timer, self._planned_timer, self._health_timer):
            if t:
                t()
        self._timer = self._watchdog = self._dry_timer = self._planned_timer = self._health_timer = None

    async def _periodic(self, _now) -> None:
        await self.refresh_weather()
        await self.async_replan()
        self._update_repairs()

    # ------------------------------------------------------------------ repairs (Settings -> Repairs)
    def _update_repairs(self) -> None:
        from homeassistant.helpers import issue_registry as ir
        eid = self.entry.entry_id

        def issue(key: str, show: bool, **ph) -> None:
            iid = f"{key}_{eid}"
            if show:
                ir.async_create_issue(self.hass, DOMAIN, iid, is_fixable=False, is_persistent=False,
                                      severity=ir.IssueSeverity.ERROR if key == "controller_missing" else ir.IssueSeverity.WARNING,
                                      translation_key=key, translation_placeholders={"planner": self.entry.title, **ph})
            else:
                ir.async_delete_issue(self.hass, DOMAIN, iid)
        h = self.health
        issue("controller_missing", bool(h["missing"]), entities=", ".join(h["missing"][:3]))
        long_offline = bool(h["unavailable"] and h["since"]
                            and dt_util.utcnow() - dt_util.parse_datetime(h["since"]) > timedelta(hours=1))
        issue("controller_offline", long_offline, since=self._local_hm(h["since"]))
        w = self.weather_cfg
        bad_wx = bool(w["mode"] != "off" and w.get("entity") and self.hass.states.get(w["entity"]) is None)
        issue("weather_missing", bad_wx, entity=w.get("entity") or "")
        try:
            targets = notify_logic.merged(self.config.get("notifications"), self.lang)["targets"]
        except notify_logic.NotifyConfigError:
            targets = []
        svcs = self.hass.services.async_services().get("notify", {})
        gone = [t for t in targets if t.split(".", 1)[1] not in svcs and self.hass.states.get(t) is None]
        issue("notify_missing", bool(gone), services=", ".join(gone))

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
            if k in self.skip and r.start <= now and r.pass_no == r.passes:   # skipped run is over (all passes)
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
        if self.pause_until and dt_util.now().date().isoformat() > self.pause_until:
            self.pause_until = None              # pause over
            self._event("resumed")
            await self._save()
        paused = {run_key(r) for r in self.plan.runs if self.pause_until and r.day.isoformat() <= self.pause_until}
        blocked = set(self.skip) | set(self.wx_skip) | paused
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
            self.notify("planned", rd, lead=lead, expected_water_l=self.expected_water(rd))

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
            fresh = next((r for r in (self.plan.runs if self.plan else [])
                          if run_key(r) == key and r.pass_no == run.pass_no), None)
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
        await self._start_checked(run)

    # ------------------------------------------------------------------ blockers
    def _blk_states(self) -> Dict[str, Optional[str]]:
        return {b["entity"]: (self.hass.states.get(b["entity"]).state if self.hass.states.get(b["entity"]) else None)
                for b in self.blockers}

    def _txt(self, en: str, sk: str) -> str:
        return sk if self.lang == "sk" else en

    async def _start_checked(self, run: planner.Run, answered: Optional[str] = None) -> None:
        """Start a scheduled run unless a blocker says otherwise (skip, drop zones, wait, ask)."""
        key = run_key(run)
        names = self.zone_names()
        v = blk_mod.check(self.blockers, self._blk_states(), run.slot_ids, run.zone_ids(), names)
        rd = model.run_to_dict(run, names)
        reason = ", ".join(v.reasons)
        if answered == "run":
            v.action = "run"                      # the user said "run anyway": only zone blockers still apply
        if v.action == "skip":
            self._clear_held()
            stats_mod.add_skip(self.stats, run.day.isoformat(), {s.zone_id: s.minutes for s in run.steps})
            self._event("blocked", run=rd, reason=reason, action=self._txt("skipped", "presko\u010den\u00e9"))
            await self._save()
            await self.async_replan()
            return
        if v.action in ("wait", "ask"):
            if self.held and self.held["key"] == key:
                return                            # already waiting / asking for this run
            blk = v.blockers
            if v.action == "ask":
                tmo = max(b["ask_timeout"] for b in blk if b["action"] == "ask")
                dflt = next(b["ask_default"] for b in blk if b["action"] == "ask")
                self._hold(run, "ask", tmo, reason, dflt)
                self._event("blocker_ask", run=rd, reason=reason, timeout=round(tmo),
                            default={"skip": self._txt("skip", "presko\u010di\u0165"), "run": self._txt("run", "spusti\u0165"),
                                     "wait": self._txt("wait", "po\u010dka\u0165")}[dflt])
            else:
                after = next(b["after_wait"] for b in blk if b["action"] == "wait")
                self._hold(run, "wait", v.wait_min, reason, after)
                self._event("blocked", run=rd, reason=reason,
                            action=self._txt(f"waiting up to {round(v.wait_min)} min", f"\u010dak\u00e1 najviac {round(v.wait_min)} min"))
            return
        self._clear_held()
        if v.drop_zones:                          # zone blockers: water the rest
            steps = [st for st in run.steps if st.zone_id not in v.drop_zones]
            if not steps:
                return await self._skip_blocked(run, {"reason": reason})
            settings = model.parse(self.config, self.valves, self.valve_overlap)[2]
            start = dt_util.now()
            run = dataclasses.replace(run, steps=steps, notes=list(run.notes) + [f"blocked: {reason}"],
                                      start=start, end=start + planner.run_length(steps, settings))
            self._event("blocked", run=model.run_to_dict(run, names), reason=reason,
                        action=self._txt("without blocked zones", "bez blokovan\u00fdch z\u00f3n"))
        await self.execute(run, "schedule")

    def _hold(self, run: planner.Run, mode: str, minutes: float, reason: str, then: str) -> None:
        until = dt_util.utcnow() + timedelta(minutes=minutes)
        self.held = {"key": run_key(run), "pass_no": run.pass_no, "mode": mode, "until": until.isoformat(),
                     "reason": reason, "then": then, "since": dt_util.utcnow().isoformat()}
        if self._held_timer:
            self._held_timer()
        self._held_timer = async_track_point_in_utc_time(self.hass, self._held_tick, until)
        self._changed()

    def _clear_held(self) -> None:
        if self._held_timer:
            self._held_timer()
            self._held_timer = None
        if self.held:
            self.held = None
            self._changed()

    def _held_run(self) -> Optional[planner.Run]:
        if not self.held:
            return None
        return next((r for r in (self.plan.runs if self.plan else [])
                     if run_key(r) == self.held["key"] and r.pass_no == self.held["pass_no"]), None)

    async def _held_tick(self, _now=None) -> None:
        """Wait / ask time is over: do what was configured."""
        self._held_timer = None
        h, run = self.held, self._held_run()
        if not h or run is None:
            self._clear_held()
            return
        then = h["then"]
        if then == "wait" and h["mode"] == "ask":   # ask with default "wait": wait for the blockers' wait time
            blk = [b for b in self.blockers if b["action"] == "ask"]
            self._hold(run, "wait", max([b["wait"] for b in blk] or [30]), h["reason"],
                       next((b["after_wait"] for b in blk), "skip"))
            return
        if then == "run":
            self._clear_held()
            await self._start_checked(run, "run")          # "run anyway" after the wait / no answer
        else:
            await self._skip_blocked(run, h)

    async def _skip_blocked(self, run: planner.Run, h: Dict[str, Any]) -> None:
        stats_mod.add_skip(self.stats, run.day.isoformat(), {s.zone_id: s.minutes for s in run.steps})
        self._event("blocked", run=model.run_to_dict(run, self.zone_names()), reason=h["reason"],
                    action=self._txt("skipped", "presko\u010den\u00e9"))
        self._clear_held()
        await self._save()
        await self.async_replan()

    @callback
    def _on_blocker_state(self, _event: Event) -> None:
        """A held run starts as soon as its blockers clear; an active run stops if a 'stop' blocker turns on."""
        st = self._blk_states()
        if self.held and self.held["mode"] == "wait":
            run = self._held_run()
            if run is not None and blk_mod.check(self.blockers, st, run.slot_ids, run.zone_ids()).action == "run":
                self._clear_held()
                self.hass.async_create_task(self._start_checked(run))
        if self.active:
            rr = self.active["run"]
            for b in self.blockers:
                if b["during"] == "stop" and blk_mod.applies(b, rr.get("slots") or [], [z["zone"] for z in rr["zones"]]) \
                        and blk_mod.active(b, st.get(b["entity"])):
                    self.hass.async_create_task(self._stop_blocked(b))
                    break

    async def _stop_blocked(self, b: Dict[str, Any]) -> None:
        if not self.active:
            return
        if self.active.get("dry_run"):
            await self._finish("stopped", reason=self._txt(f"blocked by {b['name']}", f"zablokovan\u00e9: {b['name']}"))
        else:
            await self._turn_off_main()
            if self.active:
                await self._finish("stopped", reason=self._txt(f"blocked by {b['name']}", f"zablokovan\u00e9: {b['name']}"))

    async def answer_blocker(self, answer: str) -> None:
        """Answer to an 'ask' (or override a wait): run | skip | wait."""
        h, run = self.held, self._held_run()
        if not h or run is None:
            raise model.ConfigError("no run is waiting for an answer")
        if answer == "skip":
            self.held = None
            await self._skip_blocked(run, h)
        elif answer == "run":
            self._clear_held()
            await self._start_checked(run, "run")
        else:
            blk = [b for b in self.blockers if b["action"] in ("ask", "wait")]
            self._hold(run, "wait", 30, h["reason"], next((b["after_wait"] for b in blk), "skip"))

    # ------------------------------------------------------------------ pause
    async def pause(self, until: Optional[str] = None, days: Optional[int] = None) -> Optional[str]:
        """No scheduled runs until this local date (inclusive). until=None and days=None resumes."""
        if days:
            until = (dt_util.now().date() + timedelta(days=int(days) - 1)).isoformat()
        if until:
            from datetime import date as _date
            try:
                _date.fromisoformat(until)
            except ValueError as err:
                raise model.ConfigError("pause: until must be YYYY-MM-DD") from err
            self.pause_until = until
            self._event("paused", until=dt_util.parse_date(until).strftime("%d.%m.%Y"))
        else:
            self.pause_until = None
            self._event("resumed")
        await self._save()
        await self.async_replan()
        return self.pause_until

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
            # simulate the whole run: same notifications and states as a real one, nothing sent
            self._event("started", run=rd, source=source, dry=True)
            self._simulate(run)
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

    def _simulate(self, run: planner.Run) -> None:
        """Dry run: walk the zones on the planned timing (pump delay, valve overlap), like the ESP would."""
        self._cancel_sim()
        pump = self.pump
        t = dt_util.as_utc(run.start) + timedelta(seconds=pump["delay"] if pump and pump["auto_on"] else 0)
        names = self.zone_names()
        for st in run.steps:
            start, end = t, t + timedelta(minutes=st.minutes)

            async def _zone_on(_now, zid=st.zone_id, minutes=st.minutes, start=start, end=end):
                if not (self.active and self.active.get("dry_run")) or end <= dt_util.utcnow():
                    return
                self.active_zone = {"zone": zid, "name": names.get(zid, zid), "since": start.isoformat(),
                                    "minutes": minutes, "until": end.isoformat(), "dry": True}
                self.notify("zone_changed", self.active["run"], zone=names.get(zid, zid), zone_minutes=minutes, dry=True)
                self._changed()

            self._sim_timers.append(async_track_point_in_utc_time(self.hass, _zone_on, max(start, dt_util.utcnow())))
            t = end - timedelta(seconds=self.valve_overlap)

    def _cancel_sim(self) -> None:
        for u in getattr(self, "_sim_timers", []):
            u()
        self._sim_timers = []

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
        if active and active.get("dry_run"):
            self._cancel_sim()
            self.active_zone = None
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
        if active and not active.get("dry_run"):
            self._last_end = dt_util.utcnow()
            zs = (active.get("run") or {}).get("zones") or []
            self._last_zone = zs[-1]["name"] if zs else None
            self._arm_stuck_check()
        if active and not active.get("dry_run") and p and p["auto_off"] and active.get("pump_started"):
            await self._pump_switch(False)
        run_kwh = self._run_meter_stop() if active and not active.get("dry_run") else None
        await self._save()
        actual = round(sum(((active or {}).get("actual") or {}).values()), 1)
        if active and active.get("dry_run") and not actual:
            actual = round(sum(z["minutes"] for z in active["run"]["zones"]), 1) if kind == "finished" else actual
        self._event(kind, reason=reason, run=(active or {}).get("run"), actual_minutes=actual,
                    dry=bool(active and active.get("dry_run")), **self._usage((active or {}).get("metered"), run_kwh))
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
                try:
                    zones, slots, settings = model.parse(self.config, self.valves, self.valve_overlap)
                    r = self.active["run"]
                    steps = [planner.Step(z["zone"], z["minutes"], z["minutes"], (r.get("slots") or ["?"])[0]) for z in r["zones"]]
                    start = dt_util.parse_datetime(r["start"])
                    self._simulate(planner.Run(start.date(), start, end, steps, r.get("slots") or [], "start", start))
                except Exception:  # noqa: BLE001 - only the display of the simulated zone is lost
                    pass
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
                        weather=None, meters=None, ui=None, leak=None, blockers=None) -> planner.Plan:
        new = copy.deepcopy(self.config)
        if blockers is not None:
            try:
                new["blockers"] = blk_mod.from_list(blockers)
            except blk_mod.BlockerConfigError as err:
                raise model.ConfigError(str(err)) from err
        if leak is not None:
            try:
                leak_mod.merged(leak)
            except leak_mod.LeakConfigError as err:
                raise model.ConfigError(str(err)) from err
            new["leak"] = {k: v for k, v in leak.items() if v is not None and v != ""}
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
        resub = (new.get("weather"), new.get("meters"), new.get("leak"), new.get("blockers")) != (
            self.config.get("weather"), self.config.get("meters"), self.config.get("leak"), self.config.get("blockers"))
        if (new.get("weather") or {}).get("mode", "off") != "suggest":
            # leaving suggest mode: open questions are gone (auto decides, off ignores the weather);
            # answers stay - a dismissed skip still means "run anyway" in auto mode
            self.suggestions = {k: v for k, v in self.suggestions.items() if v.get("status") != "pending"}
        self.config = new
        await self._save()
        if resub:
            self._subscribe_dynamic()
            await self._setup_rain()
            await self._seed_tmax()
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
        zones = [dataclasses.replace(z, passes=1) for z in zones]
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
        zones = [dataclasses.replace(z, passes=1) for z in zones]
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

    async def clear_skips(self, answers: bool = True) -> Dict[str, int]:
        """Undo every skip you set for upcoming runs and (optionally) every weather answer."""
        n_skip, n_ans = len(self.skip), 0
        self.skip = []
        if answers:
            n_ans = len(self.suggestions)
            self.suggestions = {}
        await self._save()
        await self.async_replan()
        return {"skips": n_skip, "answers": n_ans}

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
                "paused": [run_key(r) for r in p.runs if self.pause_until and r.day.isoformat() <= self.pause_until],
                "suggestions": {k: v for k, v in self.suggestions.items() if v.get("status") == "pending"}
                if self.weather_cfg["mode"] == "suggest" else {}}
