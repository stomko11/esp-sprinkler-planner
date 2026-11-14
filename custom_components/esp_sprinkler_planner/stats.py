"""Watering statistics (pure Python, no Home Assistant imports).

Meters (optional, part of the planner config):

    "meters": {
      "flow": "sensor.water_flow",          # L/min or m3/h (integrated while a zone is open)
      "water_total": "sensor.water_meter",  # L or m3, increasing (difference per zone, preferred)
      "pump_power": "sensor.pump_power",    # W or kW (integrated while the pump is on)
      "pump_energy": "sensor.pump_energy",  # kWh or Wh, increasing (difference, preferred)
      "flow_warn": 30,                      # % jump from the zone's usual flow (last runs) -> warning (0 = off)
      "drift_warn": 15                      # % slow drop below the zone's baseline -> warning (0 = off)
    }

Daily store: {"YYYY-MM-DD": {"zones": {zone: {"min", "runs", "l", "kwh"}}, "skipped": {zone: min},
              "runs": n, "skips": n, "kwh": pump energy that day (also outside zones)}}.
Per zone a short list of recent flow samples (L/min) is kept for the usual-flow check.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

METER_KEYS = ("flow", "water_total", "pump_power", "pump_energy")
KEEP_DAYS = 3 * 366
FLOW_SAMPLES = 10


class MetersConfigError(ValueError):
    pass


def meters_from_dict(d: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    d = dict(d or {})
    bad = set(d) - set(METER_KEYS) - {"flow_warn", "drift_warn", "water_price", "energy_price"}
    if bad:
        raise MetersConfigError(f"meters: unknown field(s) {', '.join(sorted(bad))}")
    out: Dict[str, Any] = {}
    for k in METER_KEYS:
        v = d.get(k)
        if v in (None, ""):
            continue
        if not isinstance(v, str) or not v.startswith("sensor."):
            raise MetersConfigError(f"meters.{k}: a sensor.* entity, got {v!r}")
        out[k] = v
    try:
        out["flow_warn"] = float(d.get("flow_warn", 30) or 0)
    except (TypeError, ValueError) as err:
        raise MetersConfigError("meters.flow_warn: a percentage") from err
    if not 0 <= out["flow_warn"] <= 100:
        raise MetersConfigError("meters.flow_warn: 0 .. 100 %")
    try:
        out["drift_warn"] = float(d.get("drift_warn", 15) or 0)
    except (TypeError, ValueError) as err:
        raise MetersConfigError("meters.drift_warn: a percentage") from err
    if not 0 <= out["drift_warn"] <= 90:
        raise MetersConfigError("meters.drift_warn: 0 .. 90 %")
    for k in ("water_price", "energy_price"):   # per m3 / per kWh, in the HA currency
        v = d.get(k)
        if v in (None, ""):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError) as err:
            raise MetersConfigError(f"meters.{k}: a price") from err
        if not 0 <= out[k] <= 1000:
            raise MetersConfigError(f"meters.{k}: 0 .. 1000")
    return out


# ------------------------------------------------------------------ units
def litres(v: float, unit: Optional[str]) -> float:
    u = (unit or "L").replace("\u00b3", "3").lower()
    return v * 1000 if u in ("m3", "m^3") else v * 3.785411784 if u == "gal" else v


def l_per_min(v: float, unit: Optional[str]) -> float:
    u = (unit or "L/min").replace("\u00b3", "3").lower()
    return {"m3/h": v * 1000 / 60, "l/h": v / 60, "l/s": v * 60, "gal/min": v * 3.785411784}.get(u, v)


def kwh(v: float, unit: Optional[str]) -> float:
    u = (unit or "kWh").lower()
    return v / 1000 if u == "wh" else v * 1000 if u == "mwh" else v


def watts(v: float, unit: Optional[str]) -> float:
    return v * 1000 if (unit or "W").lower() == "kw" else v


class Integrator:
    """Left-rectangle integration of a sampled rate. add(t, value) with value in per-minute or
    per-hour units; total() returns value x minutes (per_minute=True) or value x hours."""

    def __init__(self, t: datetime, value: Optional[float], per_minute: bool = True) -> None:
        self.t, self.v, self.sum, self.per_minute = t, value, 0.0, per_minute
        self.seconds = 0.0

    def add(self, t: datetime, value: Optional[float]) -> None:
        dt = max(0.0, (t - self.t).total_seconds())
        if self.v is not None:
            self.sum += self.v * dt / (60.0 if self.per_minute else 3600.0)
            self.seconds += dt
        self.t, self.v = t, value

    def total(self, t: datetime) -> float:
        self.add(t, self.v)
        return self.sum

    def average(self) -> Optional[float]:
        if not self.seconds:
            return None
        return self.sum / (self.seconds / (60.0 if self.per_minute else 3600.0))


# ------------------------------------------------------------------ daily store
def _day(stats: Dict[str, Any], day: str) -> Dict[str, Any]:
    d = stats.setdefault(day, {})
    d.setdefault("zones", {})
    d.setdefault("skipped", {})
    d.setdefault("runs", 0)
    d.setdefault("skips", 0)
    d.setdefault("kwh", 0.0)
    return d


def add_zone(stats, day: str, zone: str, minutes: float, l: Optional[float] = None, kwh_: Optional[float] = None):
    z = _day(stats, day)["zones"].setdefault(zone, {"min": 0.0, "runs": 0})
    z["min"] = round(z["min"] + minutes, 2)
    z["runs"] += 1
    if l is not None:            # minutes with a meter, for the average flow
        z["l"] = round(z.get("l", 0.0) + l, 1)
        z["lmin"] = round(z.get("lmin", 0.0) + minutes, 2)
    if kwh_ is not None:
        z["kwh"] = round(z.get("kwh", 0.0) + kwh_, 4)
        z["emin"] = round(z.get("emin", 0.0) + minutes, 2)


def add_run(stats, day: str) -> None:
    _day(stats, day)["runs"] += 1


def add_skip(stats, day: str, zones: Dict[str, float]) -> None:
    d = _day(stats, day)
    d["skips"] += 1
    for z, m in zones.items():
        d["skipped"][z] = round(d["skipped"].get(z, 0.0) + m, 2)


def add_pump_energy(stats, day: str, kwh_: float) -> None:
    d = _day(stats, day)
    d["kwh"] = round(d["kwh"] + kwh_, 4)


def prune(stats: Dict[str, Any], today: date) -> None:
    cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
    for k in [k for k in stats if k < cut]:
        del stats[k]


def seed_from_history(stats, history: Dict[str, Dict[str, float]]) -> None:
    """One-time: minutes from the old 14-day history when there are no stats yet."""
    for day, zones in (history or {}).items():
        if day in stats:
            continue
        for z, m in zones.items():
            add_zone(stats, day, z, m)


# ------------------------------------------------------------------ flow check
def flow_check(samples: List[float], flow: Optional[float], warn: float) -> Optional[Tuple[str, float, float]]:
    """('high'|'low', flow, usual) when flow deviates more than warn % from the median of samples."""
    if flow is None or not warn or len(samples) < 3:
        return None
    s = sorted(samples)
    usual = s[len(s) // 2]
    if usual <= 0:
        return None
    dev = (flow - usual) / usual * 100
    if abs(dev) >= warn:
        return ("high" if dev > 0 else "low", round(flow, 1), round(usual, 1))
    return None


BASELINE_RUNS = 5   # the first runs (after setup or a reset) define the zone's normal flow
RECENT_RUNS = 5     # the drift check uses the median of this many latest runs


def baseline_from(samples: List[float]) -> Optional[float]:
    if len(samples) < BASELINE_RUNS:
        return None
    s = sorted(samples[:BASELINE_RUNS])
    return round(s[len(s) // 2], 2)


def drift_check(baseline: Optional[float], samples: List[float], pct: float) -> Optional[Tuple[float, float, float]]:
    """(recent flow, baseline, change %) when the recent median is pct % or more below the baseline.
    Catches a slowly clogging filter, which the run-to-run check misses because its median follows."""
    if not baseline or not pct or len(samples) < RECENT_RUNS:
        return None
    r = sorted(samples[-RECENT_RUNS:])
    recent = r[len(r) // 2]
    change = (recent - baseline) / baseline * 100
    return (round(recent, 1), round(baseline, 1), round(change)) if change <= -pct else None


def push_sample(samples: List[float], flow: Optional[float]) -> List[float]:
    if flow is None or flow <= 0:
        return samples
    return (samples + [round(flow, 2)])[-FLOW_SAMPLES:]


# ------------------------------------------------------------------ aggregation
def _bucket(day: date, period: str) -> str:
    if period == "day":
        return day.isoformat()
    if period == "week":
        y, w, _ = day.isocalendar()
        return f"{y}-W{w:02d}"
    if period == "month":
        return f"{day.year}-{day.month:02d}"
    return str(day.year)


def _buckets(today: date, period: str, count: int) -> List[str]:
    out: List[str] = []
    d = today
    while len(out) < count:
        b = _bucket(d, period)
        if b not in out:
            out.append(b)
        d -= timedelta(days=1)
        if (today - d).days > 3700:
            break
    return list(reversed(out))


def aggregate(stats: Dict[str, Any], today: date, period: str = "week", count: int = 12) -> Dict[str, Any]:
    """Totals per bucket (day/week/month/year) and per zone, oldest first."""
    if period not in ("day", "week", "month", "year"):
        raise ValueError(period)
    keys = _buckets(today, period, count)
    rows = {k: {"key": k, "zones": {}, "min": 0.0, "l": 0.0, "kwh": 0.0, "runs": 0, "skips": 0,
                "skipped_min": 0.0, "has_l": False, "has_kwh": False} for k in keys}
    for ds, d in stats.items():
        try:
            day = date.fromisoformat(ds)
        except ValueError:
            continue
        r = rows.get(_bucket(day, period))
        if r is None:
            continue
        r["runs"] += d.get("runs", 0)
        r["skips"] += d.get("skips", 0)
        r["skipped_min"] += sum((d.get("skipped") or {}).values())
        zone_kwh = 0.0
        for z, v in (d.get("zones") or {}).items():
            t = r["zones"].setdefault(z, {"min": 0.0, "l": 0.0, "kwh": 0.0, "runs": 0, "lmin": 0.0, "emin": 0.0})
            t["lmin"] += v.get("lmin", 0.0)
            t["emin"] += v.get("emin", 0.0)
            t["min"] += v.get("min", 0.0)
            t["runs"] += v.get("runs", 0)
            r["min"] += v.get("min", 0.0)
            if "l" in v:
                t["l"] += v["l"]
                r["l"] += v["l"]
                r["has_l"] = True
            if "kwh" in v:
                t["kwh"] += v["kwh"]
                zone_kwh += v["kwh"]
                r["has_kwh"] = True
        day_kwh = d.get("kwh") or 0.0
        if day_kwh:
            r["has_kwh"] = True
        r["kwh"] += max(day_kwh, zone_kwh)
    out = [rows[k] for k in keys]
    for r in out:
        for k in ("min", "l", "kwh", "skipped_min"):
            r[k] = round(r[k], 3 if k == "kwh" else 1)
        for t in r["zones"].values():
            for k in ("min", "l", "kwh", "lmin", "emin"):
                t[k] = round(t[k], 3 if k == "kwh" else 1)
    return {"period": period, "rows": out}


def totals(stats: Dict[str, Any], today: date) -> Dict[str, Any]:
    """This week / month / year and all time, for the summary tiles."""
    def tot(pred):
        m = l = e = 0.0
        runs = skips = 0
        has_l = has_e = False
        for ds, d in stats.items():
            try:
                day = date.fromisoformat(ds)
            except ValueError:
                continue
            if not pred(day):
                continue
            runs += d.get("runs", 0)
            skips += d.get("skips", 0)
            ze = 0.0
            for v in (d.get("zones") or {}).values():
                m += v.get("min", 0.0)
                if "l" in v:
                    l += v["l"]
                    has_l = True
                if "kwh" in v:
                    ze += v["kwh"]
                    has_e = True
            if d.get("kwh"):
                has_e = True
            e += max(d.get("kwh") or 0.0, ze)
        return {"min": round(m, 1), "l": round(l, 1) if has_l else None, "kwh": round(e, 3) if has_e else None,
                "runs": runs, "skips": skips}
    y, w, _ = today.isocalendar()
    return {
        "week": tot(lambda d: d.isocalendar()[:2] == (y, w)),
        "month": tot(lambda d: (d.year, d.month) == (today.year, today.month)),
        "year": tot(lambda d: d.year == today.year),
        "all": tot(lambda d: True),
    }
