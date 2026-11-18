"""Keep the saved valve mapping in step with the ESP: new valves, positions, valves that are gone.

Pure Python (no Home Assistant imports). Input: the saved valves (entry data) and the valves found on
the device now (discovery proposals, in ESP order). Output: the new saved list and what changed.

Rules
- A saved zone is the found valve that shares any of its entities with it. It keeps its id, name, use
  switch and history; its entities and maximum are taken from the device.
- A found valve no saved zone has is added as a new zone (next free id), so it shows in the card at
  once. It is in no slot yet, so it does not water until you add it to one.
- Positions follow the ESP whenever the ESP's own order changes (a valve added, removed or moved in
  the YAML). Positions set by hand in the card are kept while the ESP's order stays the same.
- A saved zone none of whose entities exist any more is reported, never removed: you decide (Repairs).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set

ENT_KEYS = ("duration", "enable_switch", "valve_switch")


@dataclass
class SyncResult:
    valves: List[Dict[str, Any]]
    added: List[Dict[str, Any]] = field(default_factory=list)       # new zones
    moved: bool = False                                              # positions changed
    missing: List[Dict[str, Any]] = field(default_factory=list)     # saved zones not on the device any more
    signature: str = ""                                              # the ESP's order, to notice a change
    changed: bool = False                                            # valves differ from the saved ones


def _ents(v: Any) -> Set[str]:
    get = v.get if isinstance(v, dict) else (lambda k: getattr(v, k, None))
    return {e for e in (get(k) for k in ENT_KEYS) if e}


def signature(found: Sequence[Any]) -> str:
    """The ESP's valve order as text: the duration (or enable / valve) entity of each valve, in order."""
    out = []
    for f in found:
        e = getattr(f, "duration", None) or getattr(f, "enable_switch", None) or getattr(f, "valve_switch", None)
        if e:
            out.append(e)
    return "|".join(out)


def next_free_id(taken: Set[str]) -> str:
    n = 1
    while f"zone_{n}" in taken:
        n += 1
    return f"zone_{n}"


def sync(saved: Sequence[Dict[str, Any]], found: Sequence[Any], existing: Set[str],
         last_signature: Optional[str], reserved: Sequence[str] = ()) -> SyncResult:
    """saved: entry valves; found: discovery proposals in ESP order (complete ones are used);
    existing: entity ids that exist now; last_signature: signature() at the last sync (None = never);
    reserved: zone ids that must not be given to a new valve."""
    found = [f for f in found if getattr(f, "enable_switch", None) and getattr(f, "duration", None)]
    sig = signature(found)
    out = copy.deepcopy(list(saved))
    by_found: Dict[int, Dict[str, Any]] = {}
    for v in out:
        ents = _ents(v)
        for i, f in enumerate(found):
            if i not in by_found and ents & _ents(f):
                by_found[i] = v
                for k in ENT_KEYS:
                    val = getattr(f, k, None)
                    if val:
                        v[k] = val
                if getattr(f, "max_minutes", None) is not None:
                    v["max_minutes"] = f.max_minutes
                break
    res = SyncResult(valves=out, signature=sig)
    taken = {v["id"] for v in out} | set(reserved)
    for i, f in enumerate(found):
        if i in by_found:
            continue
        nv = {"id": next_free_id(taken), "name": f.name, "order": i, "enabled": True,
              "valve_switch": getattr(f, "valve_switch", None), "enable_switch": f.enable_switch,
              "duration": f.duration, "max_minutes": getattr(f, "max_minutes", None)}
        taken.add(nv["id"])
        out.append(nv)
        by_found[i] = nv
        res.added.append(nv)
    if last_signature is None or sig != last_signature or res.added:
        # the ESP's order is the truth: matched and new zones take their place on the ESP,
        # zones not found keep their relative place after them
        before = {v["id"]: v.get("order") for v in out}
        pos = 0
        for i in range(len(found)):
            by_found[i]["order"] = pos
            pos += 1
        matched = {id(v) for v in by_found.values()}
        for v in sorted((v for v in out if id(v) not in matched), key=lambda v: (v.get("order", 0), v["id"])):
            v["order"] = pos
            pos += 1
        res.moved = any(before[v["id"]] != v["order"] for v in out if v not in res.added)
    matched = {id(v) for v in by_found.values()}
    res.missing = [v for v in out if id(v) not in matched and not (_ents(v) & existing)]
    out.sort(key=lambda v: (v.get("order", 0), v["id"]))
    res.changed = _norm(out) != _norm(saved)
    return res


def _norm(valves: Sequence[Dict[str, Any]]):
    return sorted((tuple(sorted((k, str(v.get(k))) for k in v)) for v in valves))
