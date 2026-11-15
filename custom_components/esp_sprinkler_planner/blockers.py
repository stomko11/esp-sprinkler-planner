"""Blockers (pure Python, no Home Assistant imports).

Stored config (part of the planner config):

    "blockers": [
      {"id": "mower", "name": "Mower on the lawn", "enabled": true,
       "entity": "lawn_mower.robot", "op": "is", "value": "mowing",   # is | is_not | above | below | on | off
       "scope": "all" | "slots" | "zones", "slots": ["morning"], "zones": ["zone_4", "zone_5"],
       "action": "skip" | "wait" | "ask",
       "wait": 30,              # min: wait at most this long for the blocker to clear
       "after_wait": "skip" | "run",   # what happens when it is still blocked after waiting
       "ask_timeout": 15,       # min: no answer -> ask_default
       "ask_default": "skip" | "run" | "wait",
       "during": "ignore" | "stop"}    # blocker becomes active while a run is on
    ]

check() evaluates all blockers for one run against the current states and returns what to do:
nothing, drop some zones, or a run-level action (skip / wait / ask), with the reasons.
Precedence when several apply: skip > ask > wait.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

OPS = ("is", "is_not", "above", "below", "on", "off")
ACTIONS = ("skip", "wait", "ask")
SCOPES = ("all", "slots", "zones")
ON_STATES = ("on", "open", "home", "playing", "mowing", "cleaning", "heat", "cool", "detected", "true")


class BlockerConfigError(ValueError):
    pass


def from_list(raw: Optional[Iterable[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    out, ids = [], set()
    for i, b in enumerate(raw or []):
        where = f"blockers[{i}]"
        b = dict(b)
        bid = str(b.get("id") or f"b{i + 1}")
        if bid in ids:
            raise BlockerConfigError(f"{where}: id {bid!r} is used twice")
        ids.add(bid)
        ent = b.get("entity")
        if not isinstance(ent, str) or "." not in ent:
            raise BlockerConfigError(f"{where}: pick an entity")
        op = b.get("op") or "on"
        if op not in OPS:
            raise BlockerConfigError(f"{where}.op: one of {', '.join(OPS)}")
        if op in ("above", "below"):
            try:
                float(b.get("value"))
            except (TypeError, ValueError) as err:
                raise BlockerConfigError(f"{where}.value: a number for '{op}'") from err
        elif op in ("is", "is_not") and str(b.get("value") or "") == "":
            raise BlockerConfigError(f"{where}.value: the state to compare with")
        scope = b.get("scope") or "all"
        if scope not in SCOPES:
            raise BlockerConfigError(f"{where}.scope: one of {', '.join(SCOPES)}")
        action = b.get("action") or "skip"
        if action not in ACTIONS:
            raise BlockerConfigError(f"{where}.action: one of {', '.join(ACTIONS)}")
        if scope == "zones" and action != "skip":
            action = "skip"         # zone blockers only take those zones out of the run
        def num(k, d, lo, hi):
            try:
                v = float(b.get(k, d) if b.get(k) not in (None, "") else d)
            except (TypeError, ValueError) as err:
                raise BlockerConfigError(f"{where}.{k}: a number") from err
            if not lo <= v <= hi:
                raise BlockerConfigError(f"{where}.{k}: {lo} .. {hi}")
            return v
        after = b.get("after_wait") or "skip"
        adef = b.get("ask_default") or "skip"
        during = b.get("during") or "ignore"
        if after not in ("skip", "run") or adef not in ("skip", "run", "wait") or during not in ("ignore", "stop"):
            raise BlockerConfigError(f"{where}: after_wait skip/run, ask_default skip/run/wait, during ignore/stop")
        out.append({
            "id": bid, "name": str(b.get("name") or ent), "enabled": bool(b.get("enabled", True)),
            "entity": ent, "op": op, "value": b.get("value"),
            "scope": scope, "slots": list(b.get("slots") or []), "zones": list(b.get("zones") or []),
            "action": action, "wait": num("wait", 30, 1, 720), "after_wait": after,
            "ask_timeout": num("ask_timeout", 15, 1, 240), "ask_default": adef, "during": during,
        })
    return out


def active(b: Dict[str, Any], state: Optional[str]) -> bool:
    """Is the blocker's condition true for this entity state? Unknown / unavailable never blocks."""
    if state in (None, "unknown", "unavailable"):
        return False
    s = str(state).lower()
    op, v = b["op"], b.get("value")
    if op == "on":
        return s in ON_STATES
    if op == "off":
        return s not in ON_STATES
    if op == "is":
        return s == str(v).lower()
    if op == "is_not":
        return s != str(v).lower()
    try:
        x = float(state)
    except (TypeError, ValueError):
        return False
    return x > float(v) if op == "above" else x < float(v)


@dataclass
class Verdict:
    action: str = "run"                 # run | skip | wait | ask
    drop_zones: List[str] = field(default_factory=list)   # zone blockers: water the run without these
    reasons: List[str] = field(default_factory=list)
    blockers: List[Dict[str, Any]] = field(default_factory=list)   # the run-level blockers that apply

    @property
    def wait_min(self) -> float:
        return max([b["wait"] for b in self.blockers if b["action"] == "wait"] or [0])


def applies(b: Dict[str, Any], slot_ids: Iterable[str], zone_ids: Iterable[str]) -> bool:
    if not b["enabled"]:
        return False
    if b["scope"] == "all":
        return True
    if b["scope"] == "slots":
        return bool(set(b["slots"]) & set(slot_ids))
    return bool(set(b["zones"]) & set(zone_ids))


def check(blockers: List[Dict[str, Any]], states: Dict[str, Optional[str]], slot_ids: Iterable[str],
          zone_ids: Iterable[str], names: Optional[Dict[str, str]] = None) -> Verdict:
    slot_ids, zone_ids = list(slot_ids), list(zone_ids)
    v = Verdict()
    for b in blockers:
        if not applies(b, slot_ids, zone_ids) or not active(b, states.get(b["entity"])):
            continue
        if b["scope"] == "zones":
            hit = [z for z in b["zones"] if z in zone_ids and z not in v.drop_zones]
            v.drop_zones += hit
            if hit:
                v.reasons.append(f"{b['name']}: " + ", ".join((names or {}).get(z, z) for z in hit))
            continue
        v.blockers.append(b)
        v.reasons.append(b["name"])
    if set(v.drop_zones) >= set(zone_ids) and zone_ids:
        v.action = "skip"                # every zone of the run is blocked
    order = {"skip": 3, "ask": 2, "wait": 1}
    for b in v.blockers:
        if order[b["action"]] > order.get(v.action, 0):
            v.action = b["action"]
    return v


def still_blocked(blockers: List[Dict[str, Any]], states: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    return [b for b in blockers if active(b, states.get(b["entity"]))]
