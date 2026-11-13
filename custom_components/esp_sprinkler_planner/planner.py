"""Planning core of ESP Sprinkler Planner.

Plain Python, no Home Assistant imports, so every rule can be tested on its own.

Input: zones, slots and settings (what the user configured), a date range, a time zone,
optionally sun times and a multiplier. Output: a Plan - the runs that will actually be
started (ordered steps with final minutes, start and end) and the conflicts / notices the
card and notifications can show.

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
    days: Optional[frozenset] = None   # weekdays 0=Mon..6=Sun; None = the slot's days


@dataclass(frozen=True)
class Slot:
    id: str
    name: str = ""
    anchor: Anchor = Anchor(at=time(5, 0))
    zones: Tuple[SlotZone, ...] = ()
    days: Optional[frozenset] = None   # weekdays; None = every day
    every_n_days: Optional[int] = None  # instead of weekdays: every N days ...
    every_n_from: Optional[date] = None  # ... counted from this date
    order: str = "default"             # default | reverse | custom
    custom_order: Tuple[str, ...] = ()  # zone ids, for order=custom
    enabled: bool = True
    use_multiplier: bool = True


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
Multiplier = Union[float, Callable[[date], float]]

# ---------------------------------------------------------------- helpers


def slot_active_on(slot: Slot, day: date) -> bool:
    if not slot.enabled:
        return False
    if slot.every_n_days:
        origin = slot.every_n_from or day
        delta = (day - origin).days
        return delta >= 0 and delta % slot.every_n_days == 0
    return slot.days is None or day.weekday() in slot.days


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


def _ordered(slot: Slot, zones: Dict[str, Zone], entries: List[SlotZone]) -> List[SlotZone]:
    by_default = sorted(entries, key=lambda e: (zones[e.zone_id].order, e.zone_id))
    if slot.order == "reverse":
        return list(reversed(by_default))
    if slot.order == "custom":
        pos = {zid: i for i, zid in enumerate(slot.custom_order)}
        listed = sorted((e for e in by_default if e.zone_id in pos), key=lambda e: pos[e.zone_id])
        rest = [e for e in by_default if e.zone_id not in pos]
        return listed + rest
    return by_default


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
        mult = multiplier(day) if callable(multiplier) else multiplier
        for slot in slots:
            if not slot_active_on(slot, day):
                continue
            entries = []
            for e in slot.zones:
                zone = zones.get(e.zone_id)
                if zone is None:
                    conflicts.append(Conflict("unknown_zone", day, (slot.id,),
                                              f"{slot.name or slot.id}: zone {e.zone_id} does not exist"))
                    continue
                if not zone.enabled or e.minutes <= 0:
                    continue
                if e.days is not None and day.weekday() not in e.days:
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
            for e in _ordered(slot, zones, entries):
                minutes = e.minutes * (mult if slot.use_multiplier else 1.0)
                minutes, note = _cap_run(zones[e.zone_id], minutes)
                if note:
                    notes.append(note)
                    conflicts.append(Conflict("limit", day, (slot.id,), note))
                steps.append(Step(e.zone_id, round(minutes, 2), e.minutes, slot.id))
            run = Run(day, at, at, steps, [slot.id], slot.anchor.mode, at, notes)
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
    """a starts first. The run with more zones keeps its anchored edge; the smaller one joins
    on the side where it was planned (earlier -> in front, later -> behind). Equal size: a."""
    big, small = (a, b) if len(a.steps) >= len(b.steps) else (b, a)
    prepend = small is a
    steps = (small.steps + big.steps) if prepend else (big.steps + small.steps)
    big_ids = {id(s) for s in big.steps}
    notes = list(a.notes) + list(b.notes)

    # same zone in both: one step, at the position it has in the bigger run
    groups: Dict[str, List[Step]] = {}
    for st in steps:
        groups.setdefault(st.zone_id, []).append(st)
    result: List[Step] = []
    for st in steps:
        group = groups[st.zone_id]
        if len(group) == 1:
            result.append(st)
            continue
        pos = next((x for x in group if id(x) in big_ids), group[0])
        if st is not pos:
            continue
        if settings.same_zone == "sum":
            capped, note = _cap_run(zones[st.zone_id], sum(x.minutes for x in group))
            if note:
                notes.append(note)
                conflicts.append(Conflict("limit", a.day, tuple(a.slot_ids + b.slot_ids), note))
            result.append(Step(st.zone_id, round(capped, 2), sum(x.base_minutes for x in group), pos.slot_id))
        else:  # longer
            keep = max(group, key=lambda x: x.minutes)
            result.append(Step(st.zone_id, keep.minutes, keep.base_minutes, keep.slot_id))

    merged = Run(a.day, big.start, big.end, result, a.slot_ids + b.slot_ids, big.anchor_mode, big.target,
                 notes + [f"merged {', '.join(a.slot_ids)} + {', '.join(b.slot_ids)}"])
    if merged.anchor_mode == "start" and prepend:
        # the bigger run's own zones keep their time: the run starts earlier by what was put in front
        added = run_length(merged.steps, settings) - run_length(big.steps, settings)
        merged.target = big.target - max(added, timedelta(0))
    _place(merged, settings)
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


def plan(zones: Iterable[Zone], slots: Iterable[Slot], settings: Settings, first_day: date, days: int,
         tz: tzinfo, sun: Optional[SunTimes] = None, multiplier: Multiplier = 1.0) -> Plan:
    """Plan `days` days starting at `first_day`. Times in the result are in `tz`."""
    zone_map = {z.id: z for z in zones}
    conflicts: List[Conflict] = []
    runs = _initial_runs(zone_map, list(slots), settings, first_day, days, tz, sun, multiplier, conflicts)
    runs = _resolve(runs, settings, zone_map, conflicts)
    runs = _apply_day_limits(runs, zone_map, settings, conflicts)
    for r in runs:
        r.start, r.end, r.target = r.start.astimezone(tz), r.end.astimezone(tz), r.target.astimezone(tz)
    return Plan(sorted(runs, key=lambda r: r.start), conflicts)
