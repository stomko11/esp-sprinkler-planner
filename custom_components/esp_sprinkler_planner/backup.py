"""Settings backup: export all planner settings to a file, restore them when the planner is added again.

Pure Python (no Home Assistant imports) so it can be tested on its own.

What a backup holds: the planner config (zones, slots, settings, notifications, pump, weather, meters,
UI, leak, blockers), the zone mapping that goes with it (zone id, name, ESP entities), the planner and test
mode switches, and the history (statistics, watered minutes, last runs, learned flow, log, temperature and
rain logs). It does not hold the state of a run in progress, skips or a pause.

Zone ids are the keys of everything in the config. When the planner is added again the new valves are
matched with the saved ones by their ESP entities (then by name), so a zone keeps its id and with it its
slots, days and minutes.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

KIND = "esp_sprinkler_planner_backup"
VERSION = 1
MAX_BYTES = 5_000_000

CONFIG_KEYS = ("zones", "slots", "settings", "notifications", "pump", "weather", "meters", "ui", "leak", "blockers")
VALVE_KEYS = ("id", "name", "order", "enabled", "valve_switch", "enable_switch", "duration", "max_minutes")
FLAG_KEYS = ("enabled", "dry_run")
DATA_KEYS = ("history", "last_run", "stats", "flow_samples", "flow_base", "base_samples", "log", "tmax_log", "rain_log")


class BackupError(ValueError):
    """The file is not a usable backup."""


ENTRY_KEYS = ("valve_overlap", "watchdog_margin")


def build(title: str, integration_version: str, controller: Dict[str, Any], valves: Sequence[Dict[str, Any]],
          config: Dict[str, Any], now: Optional[datetime] = None, entry: Optional[Dict[str, Any]] = None,
          flags: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    return {
        "kind": KIND, "version": VERSION, "exported": now.isoformat(timespec="seconds"),
        "integration_version": integration_version, "title": title,
        "controller": {k: v for k, v in (controller or {}).items() if v},
        "entry": {k: entry[k] for k in ENTRY_KEYS if entry and isinstance(entry.get(k), (int, float))},
        "valves": [{k: v.get(k) for k in VALVE_KEYS if v.get(k) is not None} for v in valves],
        "config": copy.deepcopy({k: config[k] for k in CONFIG_KEYS if k in config}),
        "flags": {k: bool(flags[k]) for k in FLAG_KEYS if flags and k in flags},
        "data": copy.deepcopy({k: data[k] for k in DATA_KEYS if data and data.get(k)}),
    }


def parse(text: str) -> Dict[str, Any]:
    """Read and check a backup file. Raises BackupError with a short reason."""
    if len(text.encode("utf-8", "replace")) > MAX_BYTES:
        raise BackupError("file too large")
    try:
        data = json.loads(text)
    except ValueError as err:
        raise BackupError("not a JSON file") from err
    if not isinstance(data, dict) or data.get("kind") != KIND:
        raise BackupError("not an ESP Sprinkler Planner backup")
    if not isinstance(data.get("version"), int) or data["version"] > VERSION:
        raise BackupError("made by a newer version of the planner")
    if not isinstance(data.get("config"), dict):
        raise BackupError("no settings in the file")
    valves = data.get("valves")
    if not isinstance(valves, list) or not all(isinstance(v, dict) and v.get("id") for v in valves):
        raise BackupError("no zones in the file")
    return data


def match_valve(cand: Dict[str, Any], saved: Sequence[Dict[str, Any]], used: Sequence[str] = ()) -> Optional[Dict[str, Any]]:
    """The saved valve a newly mapped valve is the same as: by any of its ESP entities, then by name."""
    free = [v for v in saved if v["id"] not in used]
    ents = {e for e in (cand.get("duration"), cand.get("enable_switch"), cand.get("valve_switch")) if e}
    if ents:
        for v in free:
            if ents & {v.get("duration"), v.get("enable_switch"), v.get("valve_switch")}:
                return v
    name = str(cand.get("name") or "").strip().casefold()
    if name:
        for v in free:
            if str(v.get("name") or "").strip().casefold() == name:
                return v
    return None


def _tokens(name: Any) -> List[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in str(name or "").casefold()).split() if w]


def guess(name: Any, candidates: Sequence[Tuple[str, str]]) -> Optional[str]:
    """Best candidate id for a backup zone that no ESP entity matched, by its name: all words of the
    shorter name in the longer one ("Lawn South" ~ "Lawn South 1"). None when nothing is close."""
    want = _tokens(name)
    if not want:
        return None
    best, score = None, 0.0
    for cid, cname in candidates:
        got = _tokens(cname)
        if not got:
            continue
        short, long_ = (want, got) if len(want) <= len(got) else (got, want)
        if not all(w in long_ for w in short):
            continue
        s = len(short) / len(long_)
        if s > score:
            best, score = cid, s
    return best


def next_free_id(taken: Sequence[str]) -> str:
    n = 1
    while f"zone_{n}" in taken:
        n += 1
    return f"zone_{n}"


def prepare(backup: Dict[str, Any], zone_ids: Sequence[str]) -> Tuple[Dict[str, Any], List[str]]:
    """The config to start with: the backup's, without anything that points at a zone that is not there now.
    Returns (config, notes about what was left out)."""
    cfg = copy.deepcopy(backup["config"])
    have = set(zone_ids)
    names = {v["id"]: v.get("name") or v["id"] for v in backup.get("valves") or []}
    notes: List[str] = []
    refs = set(cfg.get("zones") or {})
    refs |= {s_z.get("zone") for s in cfg.get("slots") or [] for s_z in s.get("zones") or []}
    refs |= {z for b in cfg.get("blockers") or [] for z in b.get("zones") or []}
    gone = sorted(str(z) for z in refs if z and z not in have)
    if isinstance(cfg.get("zones"), dict):
        cfg["zones"] = {z: c for z, c in cfg["zones"].items() if z in have}
    for s in cfg.get("slots") or []:
        s["zones"] = [z for z in s.get("zones") or [] if z.get("zone") in have]
    for b in cfg.get("blockers") or []:
        if "zones" in b:
            b["zones"] = [z for z in b["zones"] if z in have]
    if gone:
        notes.append("Not restored (no matching valve found): " + ", ".join(names.get(z, z) for z in gone))
    return cfg, notes
