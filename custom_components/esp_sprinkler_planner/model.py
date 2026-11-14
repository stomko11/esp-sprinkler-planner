"""Stored configuration <-> planner objects (pure Python, no Home Assistant imports).

Layout of the stored config (Home Assistant .storage, edited through the `configure` service now,
the card later):

    {
      "zones":    {"zone_1": {"name": "Lawn", "enabled": true, "max_per_run": 45, "max_per_day": 90}},
      "slots":    [{"id": "morning", "name": "Morning", "enabled": true, "reverse": true,
                    "anchor": {"mode": "finish", "ref": "sunrise", "at": null, "offset": -15},
                    "days": [0, 2, 4], "every_n_days": null, "every_n_from": null,
                    "use_multiplier": true,
                    "zones": [{"zone": "zone_1", "minutes": 15, "days": null, "enabled": true}]}],
      "settings": {"merge_mode": "window", "merge_window": 60, "same_zone": "longer"}
    }

Valves (the ESP mapping) come from the config entry; zone settings above only override name,
enabled flag and limits.
"""
from __future__ import annotations

from datetime import date, time
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .planner import Anchor, Run, Settings, Slot, SlotZone, Zone
except ImportError:  # the tests import the modules directly
    from planner import Anchor, Run, Settings, Slot, SlotZone, Zone

DEFAULT_SLOTS: List[Dict[str, Any]] = [
    {"id": "morning", "name": "Morning", "anchor": {"mode": "start", "ref": "time", "at": "05:00"}, "zones": []},
    {"id": "midday", "name": "Midday", "anchor": {"mode": "start", "ref": "time", "at": "12:00"}, "zones": []},
    {"id": "afternoon", "name": "Afternoon", "anchor": {"mode": "start", "ref": "time", "at": "16:00"}, "zones": []},
    {"id": "evening", "name": "Evening", "anchor": {"mode": "start", "ref": "time", "at": "20:00"}, "zones": []},
]

MERGE_MODES = ("window", "overlap", "shift")
SAME_ZONE = ("longer", "sum", "separate")
ANCHOR_MODES = ("start", "finish")
ANCHOR_REFS = ("time", "sunrise", "sunset")


class ConfigError(ValueError):
    """Invalid configuration; the message says where."""


PUMP_DOMAINS = ("switch", "input_boolean", "light", "fan")


def pump_from_dict(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the pump settings. Empty / no entity = no pump."""
    d = dict(d or {})
    ent = d.get("entity")
    if not ent:
        return {}
    if not isinstance(ent, str) or ent.split(".", 1)[0] not in PUMP_DOMAINS:
        raise ConfigError(f"pump.entity: a {' / '.join(PUMP_DOMAINS)} entity, got {ent!r}")
    bad = set(d) - {"entity", "auto_on", "auto_off", "delay", "warn_if_off"}
    if bad:
        raise ConfigError(f"pump: unknown field(s) {', '.join(sorted(bad))}")
    delay = _num(d.get("delay", 0), "pump.delay") or 0
    if delay > 600:
        raise ConfigError("pump.delay: at most 600 seconds")
    return {"entity": ent, "auto_on": bool(d.get("auto_on", True)), "auto_off": bool(d.get("auto_off", True)),
            "delay": int(delay), "warn_if_off": bool(d.get("warn_if_off", True))}


def _num(v, where: str, minimum: float = 0) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError) as err:
        raise ConfigError(f"{where}: not a number: {v!r}") from err
    if f < minimum:
        raise ConfigError(f"{where}: must be >= {minimum:g}")
    return f


def _time(v, where: str) -> Optional[time]:
    if v in (None, ""):
        return None
    try:
        hh, mm = str(v).split(":")[:2]
        return time(int(hh), int(mm))
    except (ValueError, TypeError) as err:
        raise ConfigError(f"{where}: time must be HH:MM, got {v!r}") from err


def _days(v, where: str) -> Optional[frozenset]:
    if v is None:
        return None
    try:
        out = frozenset(int(x) for x in v)
    except (TypeError, ValueError) as err:
        raise ConfigError(f"{where}: days must be a list of weekday numbers 0 (Mon) .. 6 (Sun)") from err
    if any(d < 0 or d > 6 for d in out):
        raise ConfigError(f"{where}: weekday numbers are 0 (Mon) .. 6 (Sun)")
    return out


def _choice(v, allowed: Iterable[str], where: str, default: str) -> str:
    v = default if v in (None, "") else v
    if v not in allowed:
        raise ConfigError(f"{where}: must be one of {', '.join(allowed)}, got {v!r}")
    return v


def zones_from(valves: List[Dict[str, Any]], zone_cfg: Dict[str, Dict[str, Any]]) -> List[Zone]:
    out = []
    for v in valves:
        c = zone_cfg.get(v["id"], {})
        where = f"zone {v['id']}"
        out.append(Zone(
            v["id"], c.get("name") or v.get("name") or v["id"], int(v.get("order", 0)),
            enabled=bool(c.get("enabled", v.get("enabled", True))),
            max_per_run=_num(c.get("max_per_run"), where + " max_per_run"),
            max_per_day=_num(c.get("max_per_day"), where + " max_per_day"),
            hard_max=_num(v.get("max_minutes"), where + " max"),
            weather=bool(c.get("weather", True)),
        ))
    return out


def anchor_from(d: Dict[str, Any], where: str) -> Anchor:
    mode = _choice(d.get("mode"), ANCHOR_MODES, where + " anchor.mode", "start")
    ref = _choice(d.get("ref"), ANCHOR_REFS, where + " anchor.ref", "time")
    at = _time(d.get("at"), where + " anchor.at")
    if ref == "time" and at is None:
        raise ConfigError(f"{where}: anchor.at is required for a fixed time")
    offset = int(_num(d.get("offset"), where + " anchor.offset", minimum=-1440) or 0)
    return Anchor(mode, ref, at, offset)


def slot_from_dict(d: Dict[str, Any], zone_ids: Iterable[str]) -> Slot:
    sid = str(d.get("id") or "").strip()
    if not sid:
        raise ConfigError("slot without id")
    where = f"slot {sid}"
    known = set(zone_ids)
    entries = []
    for i, e in enumerate(d.get("zones") or []):
        zid = e.get("zone")
        if e.get("enabled") is False:
            continue        # switched off in this slot: minutes / days are kept in the config, not planned
        if zid not in known:
            raise ConfigError(f"{where}: zone {zid!r} does not exist")
        minutes = _num(e.get("minutes"), f"{where} zone {zid} minutes")
        if not minutes:
            raise ConfigError(f"{where}: zone {zid} needs minutes > 0")
        entries.append(SlotZone(zid, minutes, _days(e.get("days"), f"{where} zone {zid}")))
    n = d.get("every_n_days")
    every = int(_num(n, where + " every_n_days", minimum=1)) if n not in (None, "") else None
    start = d.get("every_n_from")
    try:
        start_d = date.fromisoformat(start) if start else None
    except ValueError as err:
        raise ConfigError(f"{where}: every_n_from must be YYYY-MM-DD") from err
    return Slot(sid, d.get("name") or sid, anchor_from(d.get("anchor") or {}, where), tuple(entries),
                _days(d.get("days"), where), every, start_d,
                bool(d.get("reverse", False)), bool(d.get("enabled", True)), bool(d.get("use_multiplier", True)))


def settings_from_dict(d: Dict[str, Any], valve_overlap: int = 0, pump_delay: int = 0) -> Settings:
    return Settings(
        merge_mode=_choice(d.get("merge_mode"), MERGE_MODES, "settings.merge_mode", "window"),
        merge_window=int(_num(d.get("merge_window", 60), "settings.merge_window") or 0),
        same_zone=_choice(d.get("same_zone"), SAME_ZONE, "settings.same_zone", "longer"),
        valve_overlap=int(valve_overlap or 0), pump_delay=int(pump_delay or 0),
    )


def parse(cfg: Dict[str, Any], valves: List[Dict[str, Any]], valve_overlap: int = 0) -> Tuple[List[Zone], List[Slot], Settings]:
    """Whole stored config -> planner input. Raises ConfigError with a precise message."""
    zones = zones_from(valves, cfg.get("zones") or {})
    ids = [z.id for z in zones]
    slots, seen = [], set()
    for s in cfg.get("slots") or []:
        slot = slot_from_dict(s, ids)
        if slot.id in seen:
            raise ConfigError(f"slot id {slot.id!r} is used twice")
        seen.add(slot.id)
        slots.append(slot)
    pump = cfg.get("pump") or {}
    delay = int(pump.get("delay") or 0) if pump.get("entity") and pump.get("auto_on") else 0
    return zones, slots, settings_from_dict(cfg.get("settings") or {}, valve_overlap, delay)


def run_to_dict(run: Run, names: Dict[str, str]) -> Dict[str, Any]:
    return {
        "start": run.start.isoformat(), "end": run.end.isoformat(), "day": run.day.isoformat(),
        "slots": list(run.slot_ids), "merged": run.merged, "reverse": run.reverse,
        "zones": [{"zone": s.zone_id, "name": names.get(s.zone_id, s.zone_id), "minutes": s.minutes} for s in run.steps],
        "notes": list(run.notes),
    }
