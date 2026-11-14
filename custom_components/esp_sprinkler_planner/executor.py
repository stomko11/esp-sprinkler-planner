"""Turn a planned run into the service calls that make the ESP run it (pure Python).

One run = one ESP cycle:
  1. multiplier -> 1 (durations are already final) and repeat -> 0, when those entities exist
  2. the run's durations into the valves' duration numbers (unit read from the number: min / s / h)
  3. enable switches: off for every other valve, on for the run's valves
  4. reverse switch per run
  5. main switch on - the ESP does sequence, overlap and timing from here
After the cycle (main switch back off) the snapshot taken before step 1 is put back.

The Home Assistant side executes the calls in order; in dry-run it only records them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .planner import Run
except ImportError:
    from planner import Run

Unavailable = ("unavailable", "unknown", None)


@dataclass
class Call:
    domain: str
    service: str
    entity_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        extra = ", ".join(f"{k}={v}" for k, v in self.data.items())
        return f"{self.domain}.{self.service} {self.entity_id}" + (f" ({extra})" if extra else "")


def _state(states, eid):
    s = states.get(eid) or {}
    return s.get("state")


def _attr(states, eid, name, default=None):
    return ((states.get(eid) or {}).get("attributes") or {}).get(name, default)


def involved_entities(valves: List[Dict[str, Any]], controller: Dict[str, Optional[str]]) -> List[str]:
    out = [e for e in (controller.get("main_switch"), controller.get("reverse"), controller.get("multiplier"),
                       controller.get("repeat"), controller.get("standby")) if e]
    for v in valves:
        out += [e for e in (v.get("enable_switch"), v.get("duration")) if e]
    return out


def health(valves: List[Dict[str, Any]], controller: Dict[str, Optional[str]], states) -> Dict[str, List[str]]:
    """Controller entities that do not exist (device removed / renamed) or are unavailable (ESP offline)."""
    missing, unavailable = [], []
    for eid in involved_entities(valves, controller):
        if eid not in states:
            missing.append(eid)
        elif _state(states, eid) in Unavailable:
            unavailable.append(eid)
    return {"missing": missing, "unavailable": unavailable}


def precheck(run: Run, valves, controller, states) -> Optional[str]:
    """Reason not to start, or None."""
    main = controller.get("main_switch")
    if not main:
        return "no main switch configured"
    if _state(states, main) == "on":
        return "a cycle is already running on the controller"
    standby = controller.get("standby")
    if standby and _state(states, standby) == "on":
        return "the controller is in standby"
    by_id = {v["id"]: v for v in valves}
    missing = []
    for st in run.steps:
        v = by_id.get(st.zone_id)
        if not v or not v.get("enable_switch") or not v.get("duration"):
            return f"zone {st.zone_id} has no enable switch / duration number mapped"
    for eid in involved_entities(valves, controller):
        if _state(states, eid) in Unavailable:
            missing.append(eid)
    if missing:
        return "unavailable: " + ", ".join(missing)
    return None


def to_number_value(minutes: float, states, eid) -> float:
    """Minutes -> the number entity's unit, clamped to its min/max and rounded to its step."""
    unit = str(_attr(states, eid, "unit_of_measurement", "min") or "min").lower()
    factor = {"s": 60, "sec": 60, "h": 1 / 60}.get(unit, 1)
    value = minutes * factor
    step = float(_attr(states, eid, "step", 0) or 0)
    if step > 0:
        value = math.floor(value / step + 0.5) * step   # half up: 22.5 min -> 23
    mx, mn = _attr(states, eid, "max"), _attr(states, eid, "min")
    if mx is not None:
        value = min(value, float(mx))
    if mn is not None:
        value = max(value, float(mn))
    value = round(value, 3)
    return int(value) if value == int(value) else value


def start_calls(run: Run, valves, controller, states) -> List[Call]:
    calls: List[Call] = []
    if controller.get("multiplier"):
        calls.append(Call("number", "set_value", controller["multiplier"], {"value": 1}))
    if controller.get("repeat"):
        calls.append(Call("number", "set_value", controller["repeat"], {"value": 0}))
    by_id = {v["id"]: v for v in valves}
    in_run = {s.zone_id for s in run.steps}
    for st in run.steps:
        num = by_id[st.zone_id]["duration"]
        calls.append(Call("number", "set_value", num, {"value": to_number_value(st.minutes, states, num)}))
    for v in valves:
        if v.get("enable_switch") and v["id"] not in in_run:
            calls.append(Call("switch", "turn_off", v["enable_switch"]))
    for st in run.steps:
        calls.append(Call("switch", "turn_on", by_id[st.zone_id]["enable_switch"]))
    if controller.get("reverse"):
        calls.append(Call("switch", "turn_on" if run.reverse else "turn_off", controller["reverse"]))
    calls.append(Call("switch", "turn_on", controller["main_switch"]))
    return calls


def take_snapshot(valves, controller, states) -> Dict[str, Any]:
    snap = {}
    for eid in involved_entities(valves, controller):
        if eid in (controller.get("main_switch"), controller.get("standby")):
            continue
        st = _state(states, eid)
        if st not in Unavailable:
            snap[eid] = st
    return snap


def restore_calls(snapshot: Dict[str, Any]) -> List[Call]:
    calls = []
    for eid, st in snapshot.items():
        if eid.startswith("number."):
            try:
                calls.append(Call("number", "set_value", eid, {"value": float(st)}))
            except (TypeError, ValueError):
                continue
        elif eid.startswith("switch.") and st in ("on", "off"):
            calls.append(Call("switch", "turn_" + st, eid))
    return calls
