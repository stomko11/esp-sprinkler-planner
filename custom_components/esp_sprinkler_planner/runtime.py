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
from homeassistant.util import dt as dt_util

from . import executor, model, planner
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
                                     "active": self.active})

    def _event(self, kind: str, **data) -> None:
        payload = {"entry_id": self.entry.entry_id, "type": kind, **data}
        self.last_event = {**payload, "time": dt_util.utcnow().isoformat()}
        self.hass.bus.async_fire(EVENT, payload)
        _LOGGER.info("%s: %s %s", self.entry.title, kind, data.get("reason") or "")

    # ------------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        data = await self.store.async_load() or {}
        self.config = data.get("config") or {"zones": {}, "slots": copy.deepcopy(model.DEFAULT_SLOTS), "settings": {}}
        self.flags.update(data.get("flags") or {})
        self.skip = data.get("skip") or []
        self.active = data.get("active")
        main = self.controller.get("main_switch")
        if main:
            self._unsubs.append(async_track_state_change_event(self.hass, [main], self._on_main))
        self._unsubs.append(async_track_time_interval(self.hass, self._periodic, timedelta(minutes=15)))
        await self._resume()
        await self.async_replan()

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for t in (self._timer, self._watchdog, self._dry_timer):
            if t:
                t()
        self._timer = self._watchdog = self._dry_timer = None

    async def _periodic(self, _now) -> None:
        await self.async_replan()

    # ------------------------------------------------------------------ planning
    def _sun(self, day):
        rise = get_astral_event_date(self.hass, "sunrise", day)
        sset = get_astral_event_date(self.hass, "sunset", day)
        return (rise, sset) if rise and sset else None

    def compute(self, days: int = PLAN_DAYS, config: Optional[Dict[str, Any]] = None) -> planner.Plan:
        zones, slots, settings = model.parse(config or self.config, self.valves, self.valve_overlap)
        tz = dt_util.get_default_time_zone()
        return planner.plan(zones, slots, settings, dt_util.now().date(), days, tz, self._sun, 1.0)

    async def async_replan(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None
        try:
            self.plan = self.compute()
            self.error = None
        except model.ConfigError as err:
            self.plan, self.next_run, self.error = None, None, str(err)
            _LOGGER.error("%s: configuration error: %s", self.entry.title, err)
            self._changed()
            return
        now = dt_util.utcnow()
        keys = {run_key(r) for r in self.plan.runs}
        if any(k not in keys for k in self.skip):   # forget skips of runs that are gone
            self.skip = [k for k in self.skip if k in keys]
            await self._save()
        upcoming = [r for r in self.plan.runs if r.start > now and run_key(r) not in self.skip]
        self.next_run = upcoming[0] if upcoming else None
        if self.next_run and not self.active:
            self._timer = async_track_point_in_utc_time(self.hass, self._fire, dt_util.as_utc(self.next_run.start))
        self._changed()

    async def _fire(self, _now) -> None:
        self._timer = None
        run = self.next_run
        if run is not None:
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
        if not self.flags["enabled"]:
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
        self.active = {"run": rd, "dry_run": self.flags["dry_run"], "snapshot": snapshot, "source": source,
                       "started": dt_util.utcnow().isoformat(), "expected_end": dt_util.as_utc(run.end).isoformat(),
                       "calls": texts}
        self._confirmed = False
        await self._save()
        if self.active["dry_run"]:
            for t in texts:
                _LOGGER.info("%s DRY RUN would call: %s", self.entry.title, t)
            self._event("dry_run", run=rd, calls=texts, source=source)
            self._dry_timer = async_track_point_in_utc_time(self.hass, self._dry_done, dt_util.as_utc(run.end))
            self._changed()
            return
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
        self._event("started", run=rd, source=source)
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
        await self._save()
        self._event(kind, reason=reason, run=(active or {}).get("run"))
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

    async def configure(self, zones=None, slots=None, settings=None) -> planner.Plan:
        new = copy.deepcopy(self.config)
        if zones is not None:
            new["zones"] = zones
        if slots is not None:
            new["slots"] = slots
        if settings is not None:
            new["settings"] = settings
        result = self.compute(days=7, config=new)   # raises ConfigError
        self.config = new
        await self._save()
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
        zones, _slots, settings = model.parse(self.config, self.valves, self.valve_overlap)
        if zone_id not in {z.id for z in zones}:
            raise model.ConfigError(f"zone {zone_id!r} does not exist")
        now = dt_util.now() + timedelta(seconds=2)
        slot = planner.Slot("manual", "manual", planner.Anchor("start", "time", now.time().replace(microsecond=0)),
                            (planner.SlotZone(zone_id, float(minutes)),), use_multiplier=False)
        plan = planner.plan(zones, [slot], settings, now.date(), 1, dt_util.get_default_time_zone())
        if not plan.runs:
            raise model.ConfigError(f"zone {zone_id!r} is disabled")
        await self.execute(plan.runs[0], "manual")

    async def stop(self) -> None:
        if not self.active:
            return
        if self.active.get("dry_run"):
            await self._finish("stopped", reason="stopped by user (dry run)")
        else:
            await self._turn_off_main()
            if self.active:   # the state listener may not have fired yet
                await self._finish("stopped", reason="stopped by user")

    async def skip_next(self) -> Optional[str]:
        if not self.next_run:
            return None
        key = run_key(self.next_run)
        self.skip.append(key)
        await self._save()
        self._event("skip_set", run=model.run_to_dict(self.next_run, self.zone_names()))
        await self.async_replan()
        return key

    def plan_dict(self, days: int = 7) -> Dict[str, Any]:
        try:
            p = self.compute(days=days)
        except model.ConfigError as err:
            return {"error": str(err), "runs": [], "conflicts": []}
        names = self.zone_names()
        return {"runs": [model.run_to_dict(r, names) for r in p.runs],
                "conflicts": [{"kind": c.kind, "day": c.day.isoformat(), "slots": list(c.slot_ids), "message": c.message}
                              for c in p.conflicts],
                "skipped": list(self.skip)}
