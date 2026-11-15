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
    # role: (domain, word groups that identify it; names are compared without accents)
    "main_switch": ("switch", (("cycle", "start"), ("main",), ("cycle",), ("cyklus",), ("spustit",), ("hlavny",),
                               ("start",), ("zyklus",), ("hauptschalter",))),
    "auto_advance": ("switch", (("auto", "advance"), ("automaticky",), ("auto",))),
    "reverse": ("switch", (("reverse",), ("opacne",), ("obratene",), ("reverz",), ("umgekehrt",), ("odwrotnie",))),
    "standby": ("switch", (("standby",), ("pohotovost",), ("pauza",), ("pause",), ("bereitschaft",))),
    "queue_enable": ("switch", (("queue",), ("rad",), ("fronta",))),
    "multiplier": ("number", (("multiplier",), ("nasobic",), ("nasobok",), ("koeficient",), ("faktor",), ("multiplikator",),
                              ("mnoznik",))),
    "repeat": ("number", (("repeat",), ("opakovanie",), ("opakovat",), ("opakovani",), ("wiederholung",), ("powtorz",))),
}
# words that mark a run duration number / an enable switch (any of these languages)
DURATION_WORDS = ("duration", "run", "time", "min", "mins", "minutes", "trvanie", "cas", "doba", "dlzka", "minut",
                  "minuty", "dauer", "laufzeit", "zeit", "czas", "trwania", "durata", "duree", "tiempo")
ENABLE_WORDS = ("enable", "enabled", "povolit", "povolene", "povol", "povoleny", "zapnut", "zapnute", "aktivny",
                "aktivovat", "aktivni", "aktivieren", "freigabe", "aktiv", "wlacz", "aktywny", "attiva", "activer", "use")


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


def _fold(text: str) -> str:
    """'Záhony Povoliť' -> 'zahony povolit' (letters with accents count as the plain letter)."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def words(text: str) -> List[str]:
    return _WORD.findall(_fold(text))


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

    controller_ids = set()
    for role, (domain, patterns) in CONTROLLER_ROLES.items():
        if domain == "number":
            for e in numbers:
                if any(all(p in words(e.name) for p in pat) for pat in patterns):
                    controller_ids.add(e.entity_id)

    def pair(n, base) -> ValveProposal:
        v = ValveProposal(name=" ".join(base).title(), duration=n.entity_id, max_minutes=n.max)
        free = [s for s in switches if s.entity_id not in used]
        for s in free:                                  # 1) keyword match
            sw = words(s.name)
            if any(w in sw for w in ENABLE_WORDS) and _base(sw, ENABLE_WORDS) == base:
                v.enable_switch = v.enable_switch or s.entity_id
            elif tuple(sw) == base:
                v.valve_switch = v.valve_switch or s.entity_id
        if not v.enable_switch:                         # 2) any language: same name plus exactly one more word
            extra = [s for s in free if s.entity_id != v.valve_switch
                     and set(base) <= set(words(s.name)) and len(words(s.name)) == len(base) + 1]
            if len(extra) == 1:
                v.enable_switch = extra[0].entity_id
        return v

    # valves: every duration number is a valve
    for n in sorted(numbers, key=lambda e: e.order):
        if n.entity_id in controller_ids:
            continue
        ws = words(n.name)
        if not any(w in ws for w in DURATION_WORDS):
            continue
        base = _base(ws, DURATION_WORDS)
        if not base:
            continue
        v = pair(n, base)
        used.add(n.entity_id)
        for x in (v.enable_switch, v.valve_switch):
            if x:
                used.add(x)
        prop.valves.append(v)
    # no duration word in any language: a number that shares its whole name with a switch is a valve
    if not prop.valves:
        for n in sorted(numbers, key=lambda e: e.order):
            if n.entity_id in controller_ids or n.entity_id in used:
                continue
            nws = words(n.name)
            # the number's name minus its last word (often the language's "duration") must name a switch
            for cut in (nws[:-1], nws[1:], nws):
                base = tuple(cut)
                if base and any(tuple(words(s.name)) == base for s in switches if s.entity_id not in used):
                    v = pair(n, base)
                    used.add(n.entity_id)
                    for x in (v.enable_switch, v.valve_switch):
                        if x:
                            used.add(x)
                    prop.valves.append(v)
                    break
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
