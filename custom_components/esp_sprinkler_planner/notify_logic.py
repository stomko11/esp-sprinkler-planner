"""Notification settings and payloads (pure Python, no Home Assistant imports).

Stored config (part of the planner config):

    "notifications": {
      "targets": ["notify.mobile_app_pixel", "notify.mobile_app_iphone"],   # default for every event
      "events": {
        "started": {"enabled": true, "targets": null, "title": "...", "message": "...", "actions": ["stop"]},
        "planned": {"enabled": true, "lead": 30, ...}
      }
    }

Only fields that differ from the defaults need to be stored; merged() fills in the rest.
Titles and messages are Home Assistant templates; the variables available for an event are in
VARIABLES (the editor offers only those).

Platform limits handled in payload():
  - Android: up to 3 action buttons; notification_icon, channel, color; simple HTML (<b>, <i>, <br>).
  - iOS: actions (no hard limit, the first few show without expanding); no icon / channel /
    color, no HTML -> tags are stripped, <br> becomes a newline.
  - anything else (persistent_notification, telegram, e-mail ...): title + plain message only.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

EVENTS = ("planned", "started", "zone_changed", "finished", "skipped", "stopped", "error", "pump_off", "dry_run")

ACTIONS = {
    "stop": "Stop",
    "skip": "Skip",
    "pump_on": "Turn pump ON",
}

COMMON_VARS = ["planner", "slots", "zones", "zone_list", "start_time", "end_time", "duration_min", "day", "source"]
VARIABLES: Dict[str, List[str]] = {
    "planned": COMMON_VARS + ["lead"],
    "started": COMMON_VARS,
    "zone_changed": COMMON_VARS + ["zone", "zone_minutes"],
    "finished": COMMON_VARS + ["actual_minutes"],
    "skipped": COMMON_VARS + ["reason"],
    "stopped": COMMON_VARS + ["reason"],
    "error": COMMON_VARS + ["reason"],
    "pump_off": COMMON_VARS + ["pump"],
    "dry_run": COMMON_VARS + ["calls"],
}

DEFAULTS: Dict[str, Dict[str, Any]] = {
    "planned": {"enabled": False, "lead": 30, "title": "Irrigation at {{ start_time }}",
                "message": "{{ zone_list }} until {{ end_time }}.", "actions": ["skip"]},
    "started": {"enabled": True, "title": "Irrigation started",
                "message": "{{ zone_list }}. It will finish at <b>{{ end_time }}</b>.", "actions": ["stop"]},
    "zone_changed": {"enabled": False, "title": "Irrigation: {{ zone }}",
                     "message": "{{ zone }} for {{ zone_minutes }} min.", "actions": []},
    "finished": {"enabled": True, "title": "Irrigation finished",
                 "message": "{{ zone_list }} - {{ duration_min }} min.", "actions": []},
    "skipped": {"enabled": True, "title": "Irrigation skipped",
                "message": "{{ slots }}: {{ reason }}.", "actions": []},
    "stopped": {"enabled": True, "title": "Irrigation stopped",
                "message": "{{ reason }}.", "actions": []},
    "error": {"enabled": True, "title": "Irrigation error",
              "message": "{{ reason }}.", "actions": []},
    "pump_off": {"enabled": True, "title": "Irrigation started - <b>pump is OFF</b>",
                 "message": "{{ zone_list }} until {{ end_time }}, but the pump is off.", "actions": ["pump_on", "stop"]},
    "dry_run": {"enabled": False, "title": "Irrigation dry run",
                "message": "Would run {{ zone_list }} until {{ end_time }}.", "actions": []},
}

ANDROID_MAX_ACTIONS = 3
FIELDS = ("enabled", "targets", "title", "message", "actions", "lead")


class NotifyConfigError(ValueError):
    pass


def merged(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Stored (partial) notification config -> full config with defaults. Validates."""
    cfg = cfg or {}
    targets = cfg.get("targets") or []
    if not isinstance(targets, list) or not all(isinstance(t, str) and t.startswith("notify.") for t in targets):
        raise NotifyConfigError("notifications.targets: a list of notify.* services")
    events = {}
    given = cfg.get("events") or {}
    unknown = set(given) - set(EVENTS)
    if unknown:
        raise NotifyConfigError(f"notifications.events: unknown event(s) {', '.join(sorted(unknown))}; "
                                f"known: {', '.join(EVENTS)}")
    for ev in EVENTS:
        e = copy.deepcopy(DEFAULTS[ev])
        e["targets"] = None
        over = given.get(ev) or {}
        bad = set(over) - set(FIELDS)
        if bad:
            raise NotifyConfigError(f"notifications.events.{ev}: unknown field(s) {', '.join(sorted(bad))}")
        e.update(over)
        if e["targets"] is not None and not all(isinstance(t, str) and t.startswith("notify.") for t in e["targets"]):
            raise NotifyConfigError(f"notifications.events.{ev}.targets: a list of notify.* services")
        acts = e.get("actions") or []
        if not all(a in ACTIONS for a in acts):
            raise NotifyConfigError(f"notifications.events.{ev}.actions: allowed {', '.join(ACTIONS)}")
        if ev == "planned":
            try:
                e["lead"] = int(e.get("lead") or 0)
            except (TypeError, ValueError) as err:
                raise NotifyConfigError("notifications.events.planned.lead: minutes") from err
        events[ev] = e
    return {"targets": targets, "events": events}


def targets_for(full: Dict[str, Any], event: str) -> List[str]:
    e = full["events"][event]
    if not e["enabled"]:
        return []
    return list(e["targets"] if e["targets"] is not None else full["targets"])


_TAG = re.compile(r"<[^>]+>")


def plain(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text or "", flags=re.I)
    return _TAG.sub("", text).strip()


def action_id(entry_id: str, action: str) -> str:
    return f"ESP_SPRINKLER_{action.upper()}_{entry_id}"


def parse_action(action: str):
    """'ESP_SPRINKLER_PUMP_ON_<entry>' -> ('pump_on', '<entry>') or None."""
    if not action or not action.startswith("ESP_SPRINKLER_"):
        return None
    rest = action[len("ESP_SPRINKLER_"):]
    for name in sorted(ACTIONS, key=len, reverse=True):
        p = name.upper() + "_"
        if rest.startswith(p):
            return name, rest[len(p):]
    return None


def payload(platform: str, title: str, message: str, actions: List[str], entry_id: str,
            tag: Optional[str] = None) -> Dict[str, Any]:
    """Service data for notify.<target>. platform: android | ios | other."""
    if platform == "android":
        data: Dict[str, Any] = {"notification_icon": "mdi:sprinkler", "channel": "Irrigation"}
        if tag:
            data["tag"] = tag
        acts = actions[:ANDROID_MAX_ACTIONS]
        if acts:
            data["actions"] = [{"action": action_id(entry_id, a), "title": ACTIONS[a]} for a in acts]
        return {"title": title, "message": message, "data": data}
    if platform == "ios":
        data = {}
        if tag:
            data["tag"] = tag
        if actions:
            data["actions"] = [{"action": action_id(entry_id, a), "title": ACTIONS[a]} for a in actions]
        out = {"title": plain(title), "message": plain(message)}
        if data:
            out["data"] = data
        return out
    return {"title": plain(title), "message": plain(message)}


def variables(event: str, run: Optional[Dict[str, Any]], slot_names: Dict[str, str], planner_name: str,
              extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Template variables for an event (run = model.run_to_dict output, times ISO with offset)."""
    run = run or {}
    zones = [z["name"] for z in run.get("zones") or []]
    start, end = run.get("start") or "", run.get("end") or ""
    dur = None
    if start and end:
        from datetime import datetime
        dur = round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60)
    v = {
        "planner": planner_name,
        "slots": ", ".join(slot_names.get(s, s) for s in run.get("slots") or []),
        "zones": zones,
        "zone_list": ", ".join(zones) or "-",
        "start_time": start[11:16], "end_time": end[11:16], "duration_min": dur,
        "day": run.get("day"), "source": (extra or {}).get("source"),
    }
    for k, val in (extra or {}).items():
        if isinstance(val, float) and val == int(val):
            val = int(val)          # 1.0 min -> 1 min
        v[k] = val
    return {k: v.get(k) for k in VARIABLES[event]}
