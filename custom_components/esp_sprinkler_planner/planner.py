"""Planning core of ESP Sprinkler Planner.

Plain Python, no Home Assistant imports, so every rule can be tested on its own.

Input: zones, slots and settings (what the user configured), a date range, a time zone,
optionally sun times and a multiplier. Output: a Plan - the runs that will actually be
started (ordered steps with final minutes, start and end) and the conflicts / notices the
card and notifications can show.

Order: the ESP sprinkler controller runs the enabled valves in the order they are defined on the
device, or reversed via its reverse switch. A run therefore always follows the zone order
(Zone.order = position on the ESP) or its reverse - the executor only sets the enable switches,
the durations and the reverse switch, then starts one cycle.

Minutes in a Step are FINAL: multiplier and limits are already applied. The executor writes
them to the ESP duration numbers and runs the ESP with multiplier 1, so a slot can opt out of
the heat multiplier without affecting the other slots in the same run.

All time arithmetic is done in UTC and converted back, so runs that cross a DST change keep
their real length.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

UTC = timezone.utc

# ---------------------------------------------------------------- configuration model


@dataclass(frozen=True)
class Zone:
    """A logical zone mapped to one ESP valve. Minutes are per run / per day limits."""

    id: str
    name: str = ""
    order: int = 0                     # position in the default order
    enabled: bool = True               # disabled = never planned, whatever the ESP has
    max_per_run: Optional[float] = None
    max_per_day: Optional[float] = None
    hard_max: Optional[float] = None   # the ESP run_duration number max_value
    weather: bool = True               # False: the weather never changes or skips this zone (greenhouse, indoor)
    passes: int = 1                    # cycle & soak: split the zone's minutes into this many passes
    soak: int = 0                      # minutes the water soaks in between two passes of the zone


@dataclass(frozen=True)
class Anchor:
    """When a slot happens.

    mode: "start" (the run starts at the time) or "finish" (the run ends at the time).
    ref:  "time" (at), "sunrise" or "sunset"; offset in minutes is added in every case.
    """

    mode: str = "start"
    ref: str = "time"
    at: Optional[time] = None
    offset: int = 0


@dataclass(frozen=True)
class SlotZone:
    """A zone inside a slot, with this slot's own duration and optionally its own weekdays."""

    zone_id: str
    minutes: float
    days: Optional[frozenset] = None   # own weekdays 0=Mon..6=Sun, override the slot's days; None = the slot's days


@dataclass(frozen=True)
class Slot:
    id: str
    name: str = ""
    anchor: Anchor = Anchor(at=time(5, 0))
    zones: Tuple[SlotZone, ...] = ()
    days: Optional[frozenset] = None   # weekdays; None = every day
    every_n_days: Optional[int] = None  # instead of weekdays: every N days ...
    every_n_from: Optional[date] = None  # ... counted from this date
    reverse: bool = False              # run the zones in reverse ESP order
    enabled: bool = True
    use_multiplier: bool = True
    soak_mode: str = "fill"            # cycle & soak: fill = other zones run while one soaks; wait = only pauses


@dataclass(frozen=True)
class Settings:
    merge_mode: str = "window"   # window: merge when closer than merge_window or overlapping
                                 # overlap: merge only when overlapping
                                 # shift: never merge, start the later run after the earlier one
    merge_window: int = 60       # minutes
    same_zone: str = "longer"    # zone in both merged runs: longer | sum | separate
                                 # (separate: those two runs are not merged, see _decide)
    valve_overlap: int = 0       # seconds two valves are open together (shortens a run)
    valve_gap: int = 0           # seconds between two valves (lengthens a run)
    pump_delay: int = 0          # seconds between pump on and the first valve


# ---------------------------------------------------------------- result model


@dataclass
class Step:
    zone_id: str
    minutes: float        # final: multiplier and limits applied
    base_minutes: float   # as configured in the slot
    slot_id: str


@dataclass
class Run:
    day: date                  # the planning day of the (first) slot
    start: datetime
    end: datetime
    steps: List[Step]
    slot_ids: List[str]
    anchor_mode: str           # which edge is fixed: "start" or "finish"
    target: datetime           # the anchored edge as planned (start or finish time)
    notes: List[str] = field(default_factory=list)
    reverse: bool = False      # run in reverse ESP order (sets the ESP reverse switch)
    pass_no: int = 1           # cycle & soak: this run is pass N of `passes` of the same slot run
    passes: int = 1

    @property
    def merged(self) -> bool:
        return len(self.slot_ids) > 1

    @property
    def duration(self) -> timedelta:
        # in UTC: two datetimes with the same local tzinfo subtract as wall-clock time,
        # which is wrong across a DST change
        return self.end.astimezone(UTC) - self.start.astimezone(UTC)

    def zone_ids(self) -> List[str]:
        return [s.zone_id for s in self.steps]


@dataclass
class Conflict:
    kind: str                 # no_sun | unknown_zone | limit | finish_missed | dropped
    day: date
    slot_ids: Tuple[str, ...]
    message: str


@dataclass
class Plan:
    runs: List[Run]
    conflicts: List[Conflict]


SunTimes = Callable[[date], Optional[Tuple[datetime, datetime]]]
Multiplier = Union[float, Callable[..., float]]   # value, f(day) or f(day, slot_id); 0 drops the weather zones

# ---------------------------------------------------------------- helpers


def slot_active_on(slot: Slot, day: date) -> bool:
    if not slot.enabled:
        return False
    if slot.every_n_days:
        origin = slot.every_n_from or day
        delta = (day - origin).days
        return delta >= 0 and delta % slot.every_n_days == 0
    return slot.days is None or day.weekday() in slot.days


def zone_on(slot: Slot, entry: "SlotZone", day: date, slot_on: bool) -> bool:
    """Does this zone of the slot water on this day?

    Own weekdays replace the slot's weekdays (the zone can run on a day the slot has off).
    For an every-N-days slot they narrow it (only the N-th days that are also on those weekdays).
    """
    if not slot.enabled:
        return False
    if entry.days is None:
        return slot_on
    if slot.every_n_days:
        return slot_on and day.weekday() in entry.days
    return day.weekday() in entry.days


def run_length(steps: Sequence[Step], settings: Settings) -> timedelta:
    """Pump delay + all valves + the gap/overlap between consecutive valves."""
    if not steps:
        return timedelta(0)
    secs = sum(s.minutes * 60 for s in steps) + settings.pump_delay
    secs += (len(steps) - 1) * (settings.valve_gap - settings.valve_overlap)
    return timedelta(seconds=max(0.0, secs))


def anchor_time(anchor: Anchor, day: date, tz: tzinfo, sun: Optional[SunTimes]) -> Optional[datetime]:
    """The anchored instant (UTC) for a day, or None when it needs sun data that is missing."""
    if anchor.ref == "time":
        local = datetime.combine(day, anchor.at or time(0, 0)).replace(tzinfo=tz)
        base = local.astimezone(UTC)
    else:
        times = sun(day) if sun else None
        if not times:
            return None
        base = (times[0] if anchor.ref == "sunrise" else times[1]).astimezone(UTC)
    return base + timedelta(minutes=anchor.offset)


def _ordered(zones: Dict[str, Zone], items, reverse: bool, key=lambda x: x.zone_id):
    """ESP order (Zone.order), or its reverse."""
    out = sorted(items, key=lambda x: (zones[key(x)].order, key(x)))
    return list(reversed(out)) if reverse else out


def _cap_run(zone: Zone, minutes: float) -> Tuple[float, Optional[str]]:
    """Apply the per-run limits of a zone. Returns (minutes, note or None)."""
    limits = [x for x in (zone.max_per_run, zone.hard_max) if x is not None]
    if limits and minutes > min(limits):
        cap = min(limits)
        return cap, f"{zone.name or zone.id}: {minutes:g} min capped to {cap:g} min per run"
    return minutes, None


def _place(run: Run, settings: Settings) -> None:
    """Recompute start/end from the steps, keeping the anchored edge at run.target."""
    length = run_length(run.steps, settings)
    if run.anchor_mode == "finish":
        run.end = run.target
        run.start = run.end - length
    else:
        run.start = run.target
        run.end = run.start + length


# ---------------------------------------------------------------- building runs


def _initial_runs(zones, slots, settings, first_day, days, tz, sun, multiplier, conflicts):
    runs: List[Run] = []
    for i in range(days):
        day = first_day + timedelta(days=i)
        for slot in slots:
            slot_on = slot_active_on(slot, day)
            if not slot_on and not (slot.enabled and not slot.every_n_days and any(e.days for e in slot.zones)):
                continue
            if callable(multiplier):
                try:
                    mult = multiplier(day, slot.id)
                except TypeError:
                    mult = multiplier(day)
            else:
                mult = multiplier
            entries = []
            for e in slot.zones:
                zone = zones.get(e.zone_id)
                if zone is None:
                    conflicts.append(Conflict("unknown_zone", day, (slot.id,),
                                              f"{slot.name or slot.id}: zone {e.zone_id} does not exist"))
                    continue
                if not zone.enabled or e.minutes <= 0:
                    continue
                if not zone_on(slot, e, day, slot_on):
                    continue
                entries.append(e)
            if not entries:
                continue
            at = anchor_time(slot.anchor, day, tz, sun)
            if at is None:
                conflicts.append(Conflict("no_sun", day, (slot.id,),
                                          f"{slot.name or slot.id}: no sunrise/sunset data for {day}"))
                continue
            steps, notes = [], []
            dropped = [e for e in entries if mult <= 0 and slot.use_multiplier and zones[e.zone_id].weather]
            if dropped:
                entries = [e for e in entries if e not in dropped]
                notes.append("weather: " + ", ".join(zones[e.zone_id].name or e.zone_id for e in dropped) + " skipped")
                if not entries:
                    continue
            for e in _ordered(zones, entries, slot.reverse):
                zone = zones[e.zone_id]
                minutes = e.minutes * (mult if slot.use_multiplier and zone.weather else 1.0)
                minutes, note = _cap_run(zones[e.zone_id], minutes)
                if note:
                    notes.append(note)
                    conflicts.append(Conflict("limit", day, (slot.id,), note))
                steps.append(Step(e.zone_id, round(minutes, 2), e.minutes, slot.id))
            run = Run(day, at, at, steps, [slot.id], slot.anchor.mode, at, notes, slot.reverse)
            _place(run, settings)
            runs.append(run)
    return runs


# ---------------------------------------------------------------- merging


def _decide(a: Run, b: Run, settings: Settings) -> Optional[str]:
    """a starts first. Returns "merge", "shift" or None."""
    gap = b.start - a.end
    overlap = gap < timedelta(0)
    shared = set(a.zone_ids()) & set(b.zone_ids())
    if settings.merge_mode == "shift" or (shared and settings.same_zone == "separate"):
        return "shift" if overlap else None
    if settings.merge_mode == "overlap":
        return "merge" if overlap else None
    return "merge" if gap <= timedelta(minutes=settings.merge_window) else None


def _shift(a: Run, b: Run, settings: Settings, conflicts: List[Conflict]) -> None:
    """Start b when a ends. A finish-by run that now ends late is a conflict."""
    length = run_length(b.steps, settings)
    b.start, b.end = a.end, a.end + length
    note = f"shifted to start after {', '.join(a.slot_ids)}"
    b.notes.append(note)
    if b.anchor_mode == "finish" and b.end > b.target:
        late = int((b.end - b.target).total_seconds() // 60)
        msg = f"{', '.join(b.slot_ids)}: finishes {late} min after its finish-by time ({note})"
        conflicts.append(Conflict("finish_missed", b.day, tuple(b.slot_ids), msg))
    # from now on b is fixed by its start
    b.anchor_mode, b.target = "start", b.start


def _merge(a: Run, b: Run, settings: Settings, zones: Dict[str, Zone], conflicts) -> Run:
    """a starts first. One ESP cycle for both:
    - order: the bigger run's direction (more zones; equal -> a's), zones in ESP order;
    - a zone in both: one step (longer or sum, see Settings.same_zone);
    - timing: if any part is finish-by, the merged run finishes by the earliest finish-by time,
      otherwise it starts at a's start."""
    big = a if len(a.steps) >= len(b.steps) else b
    notes = list(a.notes) + list(b.notes)
    groups: Dict[str, List[Step]] = {}
    for st in a.steps + b.steps:
        groups.setdefault(st.zone_id, []).append(st)
    steps: List[Step] = []
    for zid, group in groups.items():
        if len(group) == 1:
            steps.append(group[0])
        elif settings.same_zone == "sum":
            capped, note = _cap_run(zones[zid], sum(x.minutes for x in group))
            if note:
                notes.append(note)
                conflicts.append(Conflict("limit", a.day, tuple(a.slot_ids + b.slot_ids), note))
            steps.append(Step(zid, round(capped, 2), sum(x.base_minutes for x in group), group[0].slot_id))
        else:  # longer
            keep = max(group, key=lambda x: x.minutes)
            steps.append(Step(zid, keep.minutes, keep.base_minutes, keep.slot_id))
    steps = _ordered(zones, steps, big.reverse)
    finishes = [r.target for r in (a, b) if r.anchor_mode == "finish"]
    if finishes:
        mode, target = "finish", min(finishes)
    else:
        mode, target = "start", a.target
    merged = Run(a.day, a.start, a.end, steps, a.slot_ids + b.slot_ids, mode, target,
                 notes + [f"merged {', '.join(a.slot_ids)} + {', '.join(b.slot_ids)}"], big.reverse)
    _place(merged, settings)
    if a.reverse != b.reverse:
        merged.notes.append(f"runs {'reversed' if big.reverse else 'in ESP order'} (direction of the bigger part)")
    return merged


def _resolve(runs: List[Run], settings: Settings, zones, conflicts) -> List[Run]:
    runs = sorted(runs, key=lambda r: r.start)
    changed = True
    while changed:
        changed = False
        runs.sort(key=lambda r: r.start)
        for i in range(len(runs) - 1):
            a, b = runs[i], runs[i + 1]
            what = _decide(a, b, settings)
            if what == "merge":
                runs[i:i + 2] = [_merge(a, b, settings, zones, conflicts)]
                changed = True
                break
            if what == "shift":
                _shift(a, b, settings, conflicts)
                changed = True
                break
    return runs


# ---------------------------------------------------------------- per-day limits


def _apply_day_limits(runs: List[Run], zones: Dict[str, Zone], settings: Settings, conflicts) -> List[Run]:
    used: Dict[Tuple[date, str], float] = {}
    kept: List[Run] = []
    for run in sorted(runs, key=lambda r: r.start):
        new_steps = []
        for s in run.steps:
            zone = zones[s.zone_id]
            key = (run.day, s.zone_id)
            before = used.get(key, 0.0)
            minutes = s.minutes
            if zone.max_per_day is not None and before + minutes > zone.max_per_day:
                allowed = max(0.0, zone.max_per_day - before)
                label = zone.name or zone.id
                if allowed <= 0:
                    note = f"{label}: left out, {zone.max_per_day:g} min per day already planned"
                    run.notes.append(note)
                    conflicts.append(Conflict("limit", run.day, tuple(run.slot_ids), note))
                    continue
                note = f"{label}: {minutes:g} min capped to {allowed:g} min (daily limit {zone.max_per_day:g})"
                run.notes.append(note)
                conflicts.append(Conflict("limit", run.day, tuple(run.slot_ids), note))
                minutes = round(allowed, 2)
            used[key] = before + minutes
            new_steps.append(Step(s.zone_id, minutes, s.base_minutes, s.slot_id))
        if not new_steps:
            conflicts.append(Conflict("dropped", run.day, tuple(run.slot_ids),
                                      f"{', '.join(run.slot_ids)}: nothing left to run after daily limits"))
            continue
        if new_steps != run.steps:
            run.steps = new_steps
            _place(run, settings)
        kept.append(run)
    return kept


# ---------------------------------------------------------------- entry point


# ---------------------------------------------------------------- cycle & soak

def _split(minutes: float, n: int) -> List[float]:
    """10 min in 3 passes -> [3.33, 3.33, 3.34] (rounded to 0.01, the total stays exact)."""
    part = round(minutes / n, 2)
    return [part] * (n - 1) + [round(minutes - part * (n - 1), 2)]


def _expand_passes(run: Run, zones: Dict[str, Zone], settings: Settings, soak_mode: str) -> List[Run]:
    """One run -> passes. Pass 1 waters every zone (its first share), later passes only the zones
    split into more passes. Zones keep the ESP order of the run. A zone's next share starts at
    least `soak` minutes after its previous share ended: with soak_mode 'fill' the other zones of
    the pass count as soak time, with 'wait' the next pass waits the full pause after the last one."""
    n = max([zones[s.zone_id].passes for s in run.steps if s.zone_id in zones] + [1])
    if n <= 1:
        return [run]
    per = {}
    for s in run.steps:
        z = zones.get(s.zone_id)
        k = max(1, min(z.passes if z else 1, n))
        per[s.zone_id] = _split(s.minutes, k)
    gapsec = settings.valve_gap - settings.valve_overlap
    passes: List[Run] = []
    t = run.start
    last_end: Dict[str, datetime] = {}           # zone -> end of its previous share
    for k in range(n):
        steps = [Step(s.zone_id, per[s.zone_id][k], s.base_minutes, s.slot_id) for s in run.steps if k < len(per[s.zone_id])]
        if not steps:
            break
        if k:
            # earliest start so every zone in this pass has soaked long enough since its last share
            offs, need = 0.0, t
            pd = settings.pump_delay
            for st in steps:
                z = zones.get(st.zone_id)
                soak = timedelta(minutes=z.soak if z else 0)
                ready = last_end.get(st.zone_id, t) + soak
                cand = ready - timedelta(seconds=pd + offs)
                if cand > need:
                    need = cand
                offs += st.minutes * 60 + gapsec
            if soak_mode == "wait":
                need = max(need, passes[-1].end + timedelta(minutes=max((zones[s.zone_id].soak for s in steps if s.zone_id in zones), default=0)))
            t = max(need, passes[-1].end)
        start = t
        p = Run(run.day, start, start + run_length(steps, settings), steps, list(run.slot_ids), "start", start,
                list(run.notes) if k == 0 else [], run.reverse, k + 1, n)
        offs = settings.pump_delay
        for st in steps:
            last_end[st.zone_id] = start + timedelta(seconds=offs + st.minutes * 60)
            offs += st.minutes * 60 + gapsec
        passes.append(p)
        t = p.end
    if run.anchor_mode == "finish":               # keep the planned end: move all passes back
        shift = passes[-1].end - run.end
        for p in passes:
            p.start, p.end, p.target = p.start - shift, p.end - shift, p.start - shift
    if len(passes) > 1:
        passes[0].notes.append(f"cycle & soak: {len(passes)} passes, until {passes[-1].end.strftime('%H:%M')}")
    return passes


def plan(zones: Iterable[Zone], slots: Iterable[Slot], settings: Settings, first_day: date, days: int,
         tz: tzinfo, sun: Optional[SunTimes] = None, multiplier: Multiplier = 1.0) -> Plan:
    """Plan `days` days starting at `first_day`. Times in the result are in `tz`."""
    zone_map = {z.id: z for z in zones}
    conflicts: List[Conflict] = []
    slots = list(slots)
    runs = _initial_runs(zone_map, slots, settings, first_day, days, tz, sun, multiplier, conflicts)
    runs = _resolve(runs, settings, zone_map, conflicts)
    runs = _apply_day_limits(runs, zone_map, settings, conflicts)
    mode_of = {sl.id: sl.soak_mode for sl in slots}
    runs = [p for r in runs for p in _expand_passes(r, zone_map, settings, mode_of.get(r.slot_ids[0], "fill"))]
    for r in runs:
        r.start, r.end, r.target = r.start.astimezone(tz), r.end.astimezone(tz), r.target.astimezone(tz)
    return Plan(sorted(runs, key=lambda r: r.start), conflicts)
