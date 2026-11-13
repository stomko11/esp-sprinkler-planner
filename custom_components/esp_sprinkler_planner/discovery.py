"""Find the ESPHome sprinkler controller entities on a device and propose a valve mapping.

Pure Python: input is a list of entity descriptions (as read from the entity registry), output a
proposal the config flow shows for confirmation. Names on the device are free text (one user has
"Irrigation Lawn West", another "R1"), so pairing is only a suggestion - every field can be
changed by hand in the config flow.

ESPHome creates, per valve: a valve switch, an enable switch and (optionally) a run duration
number; for the controller: main switch, auto advance, reverse, standby, queue switches and the
multiplier / repeat numbers. Pairing works on the names: the duration number's name minus
"duration" is the valve's base name; the enable switch is the switch with that base plus "enable";
the valve switch is the switch with exactly that base.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

CONTROLLER_ROLES = {
    # role: (domain, words that identify it)
    "main_switch": ("switch", (("cycle", "start"), ("main",), ("cycle",))),
    "auto_advance": ("switch", (("auto", "advance"),)),
    "reverse": ("switch", (("reverse",),)),
    "standby": ("switch", (("standby",),)),
    "queue_enable": ("switch", (("queue",),)),
    "multiplier": ("number", (("multiplier",),)),
    "repeat": ("number", (("repeat",),)),
}


@dataclass
class Entity:
    entity_id: str
    name: str                 # friendly / original name without the device name
    domain: str = ""
    max: Optional[float] = None
    order: int = 0            # registry position (ESPHome registers entities in YAML order)

    def __post_init__(self):
        if not self.domain:
            self.domain = self.entity_id.split(".", 1)[0]


@dataclass
class ValveProposal:
    name: str
    valve_switch: Optional[str] = None
    enable_switch: Optional[str] = None
    duration: Optional[str] = None
    max_minutes: Optional[float] = None
    order: int = 0


@dataclass
class Proposal:
    controller: Dict[str, Optional[str]] = field(default_factory=dict)
    valves: List[ValveProposal] = field(default_factory=list)
    unassigned: List[str] = field(default_factory=list)   # switches / numbers nothing claimed


_WORD = re.compile(r"[a-z0-9]+")


def words(text: str) -> List[str]:
    return _WORD.findall((text or "").lower())


def _strip_device(name: str, device_name: str) -> str:
    """'Gardenwatering8Ch Irrigation Field' -> 'Irrigation Field'."""
    if device_name and name.lower().startswith(device_name.lower()):
        return name[len(device_name):].strip(" -_:")
    return name


def _base(ws: Sequence[str], drop: Sequence[str]) -> tuple:
    return tuple(w for w in ws if w not in drop)


def propose(entities: Sequence[Entity], device_name: str = "") -> Proposal:
    ents = [Entity(e.entity_id, _strip_device(e.name, device_name), e.domain, e.max, e.order) for e in entities]
    switches = [e for e in ents if e.domain == "switch"]
    numbers = [e for e in ents if e.domain == "number"]
    used: set = set()
    prop = Proposal()

    # valves: every duration number is a valve
    for n in sorted(numbers, key=lambda e: e.order):
        ws = words(n.name)
        if "duration" not in ws:
            continue
        base = _base(ws, ("duration", "run", "time", "min", "minutes"))
        if not base:
            continue
        v = ValveProposal(name=" ".join(base).title(), duration=n.entity_id, max_minutes=n.max)
        used.add(n.entity_id)
        for s in switches:
            if s.entity_id in used:
                continue
            sw = words(s.name)
            if "enable" in sw and _base(sw, ("enable", "enabled")) == base:
                v.enable_switch = s.entity_id
            elif tuple(sw) == base:
                v.valve_switch = s.entity_id
        for x in (v.enable_switch, v.valve_switch):
            if x:
                used.add(x)
        # display name: drop a word every valve shares (e.g. "Irrigation")
        prop.valves.append(v)
    shared = None
    for v in prop.valves:
        ws = set(words(v.name))
        shared = ws if shared is None else shared & ws
    if shared and len(prop.valves) > 1:
        for v in prop.valves:
            rest = [w for w in words(v.name) if w not in shared]
            if rest:
                v.name = " ".join(rest).title()
    # ESP order: registry order of the valve switch (ESPHome registers in YAML order), else the number's
    order_of = {e.entity_id: e.order for e in ents}
    prop.valves.sort(key=lambda v: order_of.get(v.valve_switch or v.enable_switch or v.duration, 0))
    for i, v in enumerate(prop.valves):
        v.order = i

    # controller entities
    for role, (domain, patterns) in CONTROLLER_ROLES.items():
        cands = [e for e in ents if e.domain == domain and e.entity_id not in used]
        hit = None
        for pat in patterns:
            hit = next((e for e in cands if all(p in words(e.name) for p in pat)), None)
            if hit:
                break
        prop.controller[role] = hit.entity_id if hit else None
        if hit:
            used.add(hit.entity_id)

    prop.unassigned = [e.entity_id for e in ents if e.domain in ("switch", "number") and e.entity_id not in used]
    return prop
