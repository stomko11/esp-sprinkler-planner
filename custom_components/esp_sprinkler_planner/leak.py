"""Leak alarm (pure Python, no Home Assistant imports).

Stored config (part of the planner config):

    "leak": {
      "mode": "off" | "on",
      "min_flow": 1.0,        # L/min: below this is no flow
      "duration": 20,         # min: flow outside irrigation this long in a row -> alarm
      "quiet_before": 15,     # min before a run: flow is never alarmed (pump starts, you prepare)
      "quiet_after": 15,      # min after a run: never alarmed (pressure settles, you use water)
      "night": false,         # stricter at night
      "night_from": "23:00", "night_to": "05:00",
      "night_duration": 5,    # min at night
      "stuck": 3,             # min after a run's end: still flowing -> "valve did not close" (0 = off)
      "pump_off": false,      # switch the pump off on an alarm
      "snooze": 60            # min the "That's me" button silences the alarm
    }

LeakWatch.step() is called on every flow change and once a minute; it returns "leak" once when
an alarm starts. The runtime decides what "quiet" means (a run is active, or a run starts or
ended within the quiet window) and whether the alarm is snoozed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "mode": "off", "min_flow": 1.0, "duration": 20, "quiet_before": 15, "quiet_after": 15,
    "night": False, "night_from": "23:00", "night_to": "05:00", "night_duration": 5,
    "stuck": 3, "pump_off": False, "snooze": 60,
}
NUMBERS = {"min_flow": (0.05, 100), "duration": (1, 600), "quiet_before": (0, 240), "quiet_after": (0, 240),
           "night_duration": (1, 240), "stuck": (0, 60), "snooze": (5, 1440)}


class LeakConfigError(ValueError):
    pass


def _hm(v, where: str) -> time:
    try:
        hh, mm = str(v).split(":")[:2]
        return time(int(hh), int(mm))
    except (TypeError, ValueError) as err:
        raise LeakConfigError(f"leak.{where}: time HH:MM") from err


def merged(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(cfg or {})
    bad = set(cfg) - set(DEFAULTS)
    if bad:
        raise LeakConfigError(f"leak: unknown field(s) {', '.join(sorted(bad))}")
    out = {**DEFAULTS, **{k: v for k, v in cfg.items() if v is not None and v != ""}}
    if out["mode"] not in ("off", "on"):
        raise LeakConfigError("leak.mode: off or on")
    for k, (lo, hi) in NUMBERS.items():
        try:
            out[k] = float(out[k])
        except (TypeError, ValueError) as err:
            raise LeakConfigError(f"leak.{k}: not a number") from err
        if not lo <= out[k] <= hi:
            raise LeakConfigError(f"leak.{k}: between {lo:g} and {hi:g}")
    for k in ("night", "pump_off"):
        out[k] = bool(out[k])
    _hm(out["night_from"], "night_from")
    _hm(out["night_to"], "night_to")
    return out


def is_night(cfg: Dict[str, Any], local: datetime) -> bool:
    if not cfg["night"]:
        return False
    a, b, t = _hm(cfg["night_from"], "night_from"), _hm(cfg["night_to"], "night_to"), local.time()
    return (a <= t or t < b) if a > b else (a <= t < b)


@dataclass
class LeakWatch:
    since: Optional[datetime] = None     # flow above the limit, outside irrigation, since
    alarmed: bool = False                # an alarm was raised for this flow period

    def step(self, cfg: Dict[str, Any], now: datetime, flow: Optional[float], quiet: bool,
             snoozed: bool, local: datetime) -> Optional[str]:
        if cfg["mode"] != "on" or flow is None:
            return None
        if quiet or flow < cfg["min_flow"]:
            self.since, self.alarmed = None, False     # reset: a later flow starts counting again
            return None
        if self.since is None:
            self.since = now
        limit = cfg["night_duration"] if is_night(cfg, local) else cfg["duration"]
        if not self.alarmed and not snoozed and now - self.since >= timedelta(minutes=limit):
            self.alarmed = True
            return "leak"
        return None

    def minutes(self, now: datetime) -> float:
        return round((now - self.since).total_seconds() / 60, 1) if self.since else 0.0
