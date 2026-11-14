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

EVENTS = ("planned", "started", "zone_changed", "finished", "skipped", "stopped", "error", "pump_off", "dry_run",
          "suggestion", "weather", "flow_warning", "flow_drift", "offline", "online")
LANGUAGES = ("en", "sk")

ACTIONS = {
    "stop": "Stop",
    "skip": "Skip",
    "pump_on": "Turn pump ON",
    "accept": "Accept",
    "dismiss": "Dismiss",
}
ACTIONS_SK = {"stop": "Zastavi\u0165", "skip": "Presko\u010di\u0165", "pump_on": "Zapn\u00fa\u0165 \u010derpadlo",
              "accept": "Prija\u0165", "dismiss": "Zamietnu\u0165"}

COMMON_VARS = ["planner", "slots", "zones", "zone_list", "zone_count", "start_time", "end_time", "duration_min", "day",
               "source"]
VARIABLES: Dict[str, List[str]] = {
    "planned": COMMON_VARS + ["lead", "expected_water_l"],
    "started": COMMON_VARS + ["expected_water_l"],
    "zone_changed": COMMON_VARS + ["zone", "zone_minutes"],
    "finished": COMMON_VARS + ["actual_minutes", "water_l", "energy_kwh", "cost", "avg_flow"],
    "skipped": COMMON_VARS + ["reason", "expected_water_l"],
    "stopped": COMMON_VARS + ["reason", "actual_minutes", "water_l", "energy_kwh", "cost"],
    "error": COMMON_VARS + ["reason"],
    "pump_off": COMMON_VARS + ["pump"],
    "dry_run": COMMON_VARS + ["calls"],
    "suggestion": COMMON_VARS + ["action", "factor", "reason"],
    "weather": COMMON_VARS + ["action", "factor", "reason"],
    "flow_warning": ["planner", "zone", "flow", "usual", "direction"],
    "flow_drift": ["planner", "zone", "flow", "baseline", "change", "since"],
    "offline": ["planner", "reason", "since"],
    "online": ["planner", "since"],
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
    "suggestion": {"enabled": True, "title": "Weather: {{ action }} {{ slots }} {{ start_time }}?",
                   "message": "{{ reason }}.", "actions": ["accept", "dismiss"]},
    "weather": {"enabled": True, "title": "Weather: {{ slots }} {{ action }}",
                "message": "{{ reason }}.", "actions": []},
    "flow_warning": {"enabled": True, "title": "{{ zone }}: flow too {{ direction }}",
                     "message": "{{ flow }} L/min, usually {{ usual }} L/min. Check for a leak or a blocked valve.",
                     "actions": []},
    "flow_drift": {"enabled": True, "title": "{{ zone }}: flow is dropping",
                   "message": "{{ flow }} L/min in the last runs, {{ baseline }} L/min since {{ since }} ({{ change }} %). "
                              "Clean the filter, then reset the zone's flow in Stats.", "actions": []},
    "offline": {"enabled": True, "title": "{{ planner }}: controller offline",
                "message": "{{ reason }} (since {{ since }}). Scheduled runs are skipped until it is back.", "actions": []},
    "online": {"enabled": False, "title": "{{ planner }}: controller back online",
               "message": "Offline since {{ since }}. Runs are planned again.", "actions": []},
}

_SK = {
    "planned": ("Zavla\u017eovanie o {{ start_time }}", "{{ zone_list }} do {{ end_time }}."),
    "started": ("Zavla\u017eovanie spusten\u00e9", "{{ zone_list }}. Skon\u010d\u00ed o <b>{{ end_time }}</b>."),
    "zone_changed": ("Zavla\u017eovanie: {{ zone }}", "{{ zone }} na {{ zone_minutes }} min."),
    "finished": ("Zavla\u017eovanie skon\u010dilo", "{{ zone_list }} - {{ duration_min }} min."),
    "skipped": ("Zavla\u017eovanie presko\u010den\u00e9", "{{ slots }}: {{ reason }}."),
    "stopped": ("Zavla\u017eovanie zastaven\u00e9", "{{ reason }}."),
    "error": ("Chyba zavla\u017eovania", "{{ reason }}."),
    "pump_off": ("Zavla\u017eovanie be\u017e\u00ed - <b>\u010derpadlo je VYPNUT\u00c9</b>",
                 "{{ zone_list }} do {{ end_time }}, ale \u010derpadlo je vypnut\u00e9."),
    "dry_run": ("Sk\u00fa\u0161ka zavla\u017eovania", "Spustilo by sa {{ zone_list }} do {{ end_time }}."),
    "suggestion": ("Po\u010dasie: {{ action }} {{ slots }} {{ start_time }}?", "{{ reason }}."),
    "weather": ("Po\u010dasie: {{ slots }} {{ action }}", "{{ reason }}."),
    "flow_warning": ("{{ zone }}: pr\u00edtok je pr\u00edli\u0161 {{ direction }}",
                     "{{ flow }} L/min, zvy\u010dajne {{ usual }} L/min. Skontroluj \u00fanik alebo upchat\u00fd ventil."),
    "flow_drift": ("{{ zone }}: pr\u00edtok kles\u00e1",
                   "{{ flow }} L/min v posledn\u00fdch behoch, {{ baseline }} L/min od {{ since }} ({{ change }} %). "
                   "Vy\u010disti filter a potom v \u0160tatistik\u00e1ch resetuj pr\u00edtok z\u00f3ny."),
    "offline": ("{{ planner }}: ovl\u00e1da\u010d je offline",
                "{{ reason }} (od {{ since }}). Napl\u00e1novan\u00e9 behy sa presko\u010dia, k\u00fdm sa nevr\u00e1ti."),
    "online": ("{{ planner }}: ovl\u00e1da\u010d je op\u00e4\u0165 online", "Offline od {{ since }}. Behy sa znova pl\u00e1nuj\u00fa."),
}


def defaults(lang: str = "en", emoji: bool = True) -> Dict[str, Dict[str, Any]]:
    out = copy.deepcopy(DEFAULTS)
    if lang == "sk":
        for ev, (t, m) in _SK.items():
            out[ev]["title"], out[ev]["message"] = t, m
    if emoji:
        for ev in out:
            out[ev]["title"] = f"{EMOJI[ev]} {out[ev]['title']}"
    return out

# leading emoji per event (shown on every platform) and the Android status-bar icon / colour
EMOJI = {"planned": "\U0001f4c5", "started": "\U0001f4a7", "zone_changed": "\U0001f6bf", "finished": "\u2705",
         "skipped": "\u23ed\ufe0f", "stopped": "\u26d4", "error": "\u26a0\ufe0f", "pump_off": "\U0001f6b0",
         "dry_run": "\U0001f9ea", "suggestion": "\U0001f326\ufe0f", "weather": "\U0001f326\ufe0f", "flow_warning": "\U0001f6a8", "flow_drift": "\U0001f4c9", "offline": "\U0001f4f4", "online": "\U0001f4f6"}
ICON = {"planned": "mdi:calendar-clock", "started": "mdi:sprinkler-variant", "zone_changed": "mdi:sprinkler",
        "finished": "mdi:check-circle", "skipped": "mdi:skip-next-circle", "stopped": "mdi:stop-circle",
        "error": "mdi:alert-circle", "pump_off": "mdi:pump-off", "dry_run": "mdi:flask-outline",
        "suggestion": "mdi:weather-partly-rainy", "weather": "mdi:weather-partly-rainy", "flow_warning": "mdi:water-alert", "flow_drift": "mdi:trending-down",
        "offline": "mdi:lan-disconnect", "online": "mdi:lan-connect"}
COLOR = {"offline": "#e5484d", "error": "#e5484d", "flow_warning": "#e5484d", "pump_off": "#f5a524", "stopped": "#f5a524", "finished": "#2fbf71"}

ANDROID_MAX_ACTIONS = 3
FIELDS = ("enabled", "targets", "title", "message", "actions", "lead")


class NotifyConfigError(ValueError):
    pass


def merged(cfg: Optional[Dict[str, Any]], lang: str = "en") -> Dict[str, Any]:
    """Stored (partial) notification config -> full config with defaults (in lang). Validates.
    A stored text equal to a default of any language counts as 'not changed' and follows lang."""
    cfg = cfg or {}
    base = defaults(lang)
    all_defaults = {(ev, k): {defaults(x, e)[ev][k] for x in LANGUAGES for e in (True, False)}
                    for ev in EVENTS for k in ("title", "message")}
    targets = cfg.get("targets") or []
    plats = cfg.get("platforms") or {}
    if not isinstance(plats, dict) or any(v not in ("auto", "android", "ios", "other") for v in plats.values()):
        raise NotifyConfigError("notifications.platforms: per target auto / android / ios / other")
    if not isinstance(targets, list) or not all(isinstance(t, str) and t.startswith("notify.") and len(t) > 7 for t in targets):
        raise NotifyConfigError("notifications.targets: a list of notify.* services")
    events = {}
    given = cfg.get("events") or {}
    unknown = set(given) - set(EVENTS)
    if unknown:
        raise NotifyConfigError(f"notifications.events: unknown event(s) {', '.join(sorted(unknown))}; "
                                f"known: {', '.join(EVENTS)}")
    for ev in EVENTS:
        e = copy.deepcopy(base[ev])
        e["targets"] = None
        over = dict(given.get(ev) or {})
        for k in ("title", "message"):
            if over.get(k) in all_defaults[(ev, k)]:
                del over[k]
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
            tag: Optional[str] = None, lang: str = "en", event: Optional[str] = None) -> Dict[str, Any]:
    """Service data for notify.<target>. platform: android | ios | other."""
    names = ACTIONS_SK if lang == "sk" else ACTIONS
    if platform == "android":
        data: Dict[str, Any] = {"notification_icon": ICON.get(event or "", "mdi:sprinkler"), "channel": "Irrigation"}
        if event in COLOR:
            data["color"] = COLOR[event]
        if tag:
            data["tag"] = tag
        acts = actions[:ANDROID_MAX_ACTIONS]
        if acts:
            data["actions"] = [{"action": action_id(entry_id, a), "title": names[a]} for a in acts]
        return {"title": title, "message": message, "data": data}
    if platform == "ios":
        data = {}
        if tag:
            data["tag"] = tag
        if actions:
            data["actions"] = [{"action": action_id(entry_id, a), "title": names[a]} for a in actions]
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
        "zone_count": len(zones),
        "start_time": start[11:16], "end_time": end[11:16], "duration_min": dur,
        "day": run.get("day"), "source": (extra or {}).get("source"),
    }
    for k, val in (extra or {}).items():
        if isinstance(val, float) and val == int(val):
            val = int(val)          # 1.0 min -> 1 min
        v[k] = val
    for k in ("water_l", "energy_kwh", "cost", "avg_flow", "expected_water_l"):
        if v.get(k) is None:
            v[k] = "-"              # no meter: a dash instead of "None" in the text
    return {k: v.get(k) for k in VARIABLES[event]}
