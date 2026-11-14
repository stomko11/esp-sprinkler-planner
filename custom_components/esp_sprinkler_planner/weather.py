"""Weather rules (pure Python, no Home Assistant imports).

Stored config (part of the planner config):

    "weather": {
      "mode": "off" | "suggest" | "auto",
      "entity": "weather.home",          # forecast source (hourly preferred, daily as fallback)
      "rain_sensor": "sensor.rain_daily", # optional: any rain counter in mm (event, daily, monthly, total ...)
      "rain_window": 24,     # h: rain that fell in this many hours before now counts (tracked by the planner)
      "temp_sensor": "sensor.outdoor",   # optional: current temperature instead of the forecast
      "skip_rain": 4,        # mm: fallen + expected rain at or above this -> skip the run
      "scale_rain": true,    # less rain than skip_rain reduces the minutes in proportion
      "window": 12,          # h: forecast rain counted from the run start this many hours ahead
      "min_probability": 50, # %: forecast hours below this probability are not counted
      "skip_wind": 40,       # km/h at the run start -> skip (0 = off)
      "skip_cold": 4,        # deg C at the run start below this -> skip (frost)
      "base_temp": 22,       # deg C: daily maximum where the factor is 1.0
      "per_degree": 4,       # %: factor change per degree above / below base_temp (0 = off)
      "min_factor": 50, "max_factor": 160,   # %
      "horizon": 24          # h: suggestions are made only for runs this close
    }

Forecast items are the Home Assistant weather.get_forecasts items (datetime, temperature,
templow, precipitation, precipitation_probability, wind_speed), normalised to deg C, mm, km/h.

decide() returns a Decision for one run: action run | adjust | skip, the factor for the minutes
and the reasons in plain words. The planner applies the factor per day (all slots that use the
multiplier); a skip is per run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

MODES = ("off", "suggest", "auto")
DEFAULTS: Dict[str, Any] = {
    "mode": "off", "entity": None, "rain_sensor": None, "temp_sensor": None,
    "humidity_sensor": None, "wind_sensor": None, "gust_sensor": None, "rain_now": None, "skip_gust": 60.0,
    "rain_window": 24,
    "skip_rain": 4.0, "scale_rain": True, "window": 12, "min_probability": 50,
    "skip_wind": 40.0, "skip_cold": 4.0, "base_temp": 22.0, "per_degree": 4.0,
    "min_factor": 50.0, "max_factor": 160.0, "horizon": 24,
    "answers": "keep",   # keep: an accepted / dismissed suggestion is final; follow: it follows forecast changes
}
ANSWERS = ("keep", "follow")
NUMBERS = {"rain_window": (1, 72), "skip_gust": (0, 250), "skip_rain": (0, 200), "window": (0, 72), "min_probability": (0, 100), "skip_wind": (0, 200),
           "skip_cold": (-30, 30), "base_temp": (-10, 45), "per_degree": (0, 25), "min_factor": (0, 100),
           "max_factor": (100, 300), "horizon": (1, 168)}


SENSORS = ("entity", "rain_sensor", "temp_sensor", "humidity_sensor", "wind_sensor", "gust_sensor", "rain_now")


class WeatherConfigError(ValueError):
    pass


def merged(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Stored (partial) weather config -> full config. Validates."""
    cfg = dict(cfg or {})
    bad = set(cfg) - set(DEFAULTS)
    if bad:
        raise WeatherConfigError(f"weather: unknown field(s) {', '.join(sorted(bad))}")
    out = {**DEFAULTS, **{k: v for k, v in cfg.items() if v is not None and v != ""}}
    if out["mode"] not in MODES:
        raise WeatherConfigError(f"weather.mode: one of {', '.join(MODES)}")
    if out["answers"] not in ANSWERS:
        raise WeatherConfigError(f"weather.answers: one of {', '.join(ANSWERS)}")
    for k in SENSORS:
        v = out[k]
        if v is not None and (not isinstance(v, str) or "." not in v):
            raise WeatherConfigError(f"weather.{k}: an entity id, got {v!r}")
    if out["entity"] and not out["entity"].startswith("weather."):
        raise WeatherConfigError("weather.entity: a weather.* entity")
    if out["mode"] != "off" and not any(out[k] for k in SENSORS):
        raise WeatherConfigError("weather: pick a weather entity or a sensor, or set the mode to off")
    for k, (lo, hi) in NUMBERS.items():
        try:
            out[k] = float(out[k])
        except (TypeError, ValueError) as err:
            raise WeatherConfigError(f"weather.{k}: not a number: {out[k]!r}") from err
        if not lo <= out[k] <= hi:
            raise WeatherConfigError(f"weather.{k}: between {lo} and {hi}")
    if out["min_factor"] > out["max_factor"]:
        raise WeatherConfigError("weather: min_factor is above max_factor")
    out["scale_rain"] = bool(out["scale_rain"])
    return out


# ------------------------------------------------------------------ units
def to_c(v, unit: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    v = float(v)
    return (v - 32) * 5 / 9 if unit and "F" in unit else v


def to_mm(v, unit: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    v = float(v)
    return v * 25.4 if unit in ("in", "inch", "inches") else v * 10 if unit == "cm" else v


def to_kmh(v, unit: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    v = float(v)
    return {"m/s": v * 3.6, "mph": v * 1.609344, "kn": v * 1.852, "ft/s": v * 1.09728}.get(unit or "km/h", v)


def normalise(items: Iterable[Dict[str, Any]], units: Dict[str, Optional[str]], parse) -> List[Dict[str, Any]]:
    """Forecast items -> [{t, temp, low, rain, prob, wind}] with t a datetime (parse: str -> datetime)."""
    out = []
    for it in items or []:
        t = it.get("datetime")
        t = parse(t) if isinstance(t, str) else t
        if t is None:
            continue
        out.append({"t": t, "temp": to_c(it.get("temperature"), units.get("temperature")),
                    "low": to_c(it.get("templow"), units.get("temperature")),
                    "rain": to_mm(it.get("precipitation"), units.get("precipitation")) or 0.0,
                    "prob": it.get("precipitation_probability"),
                    "wind": to_kmh(it.get("wind_speed"), units.get("wind_speed")), "cond": it.get("condition")})
    out.sort(key=lambda x: x["t"])
    return out


# ------------------------------------------------------------------ rain that fell
def rain_increment(prev: Optional[float], new: Optional[float]) -> float:
    """mm that fell between two readings of a rain counter.

    Works with any counter: event / daily / monthly / yearly / total (grows, then resets to 0)
    and rolling "last 24 h" sensors (shrink slowly as old rain drops out of their window).
    A drop to (nearly) zero is a reset: the new value is rain since the reset. A partial drop
    is a rolling window letting old rain go: nothing new fell.
    """
    if new is None or prev is None:
        return 0.0
    if new >= prev:
        return new - prev
    if new <= 0.5 or new <= prev * 0.1:
        return new
    return 0.0


def increments(readings: Iterable[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
    """(time, value) readings, oldest first -> (time, mm fell) for every rise."""
    out, prev = [], None
    for t, v in readings:
        inc = rain_increment(prev, v)
        if inc > 0:
            out.append((t, round(inc, 2)))
        prev = v
    return out


def fallen_since(events: Iterable[Tuple[datetime, float]], now: datetime, hours: float) -> float:
    start = now - timedelta(hours=hours)
    return round(sum(mm for t, mm in events if start < t <= now), 1)


# ------------------------------------------------------------------ decision
@dataclass
class Decision:
    action: str = "run"                 # run | adjust | skip
    factor: float = 1.0
    reasons: List[str] = field(default_factory=list)
    rain: float = 0.0                   # mm counted (fallen + expected)
    temp: Optional[float] = None        # daily maximum used for the factor
    wind: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "factor": self.factor, "reasons": list(self.reasons),
                "rain": round(self.rain, 1), "temp": None if self.temp is None else round(self.temp, 1),
                "wind": None if self.wind is None else round(self.wind, 1)}


def _counted(item, cfg) -> float:
    p = item.get("prob")
    if p is not None and float(p) < cfg["min_probability"]:
        return 0.0
    return float(item.get("rain") or 0.0)


def expected_rain(cfg, hourly, daily, start: datetime) -> float:
    """Forecast rain from the run start to start + window. Hourly if available, else the day total."""
    end = start + timedelta(hours=cfg["window"])
    if hourly and hourly[-1]["t"] >= start:
        return sum(_counted(h, cfg) for h in hourly if start <= h["t"] < end)
    day = start.date() if hasattr(start, "date") else start
    return sum(_counted(d, cfg) for d in daily or [] if d["t"].date() == day)


def at(series, when: datetime, key: str, gap: timedelta = timedelta(hours=2)):
    """Value of key in the forecast item nearest to when, if one is within gap (else None)."""
    best, dist = None, None
    for it in series or []:
        if it.get(key) is None:
            continue
        dd = abs(it["t"] - when)
        if dd <= gap and (dist is None or dd < dist):
            best, dist = it[key], dd
    return best


def _deg(v: float) -> str:
    return f"{round(v) + 0:d}"


def day_max(hourly, daily, day: date) -> Optional[float]:
    for d in daily or []:
        if d["t"].date() == day and d.get("temp") is not None:
            return d["temp"]
    vals = [h["temp"] for h in hourly or [] if h["t"].date() == day and h.get("temp") is not None]
    return max(vals) if vals else None


def temp_factor(cfg, tmax: Optional[float]) -> float:
    if tmax is None or not cfg["per_degree"]:
        return 1.0
    return 1.0 + (tmax - cfg["base_temp"]) * cfg["per_degree"] / 100.0


def _clamp(cfg, f: float) -> float:
    f = max(cfg["min_factor"] / 100.0, min(cfg["max_factor"] / 100.0, f))
    return round(round(f * 20) / 20, 2)   # 5 % steps


TEXT = {
    "en": {"fell": "{0} mm rain fell", "expected": "{0} mm rain expected", "skip_rain": "at least {0} mm -> skip",
           "wind": "wind {0} km/h -> skip", "frost": "{0} \u00b0C at the start -> skip (frost)", "max": "max {0} \u00b0C",
           "pct": "{0} % of the minutes", "gust": "gusts {0} km/h -> skip", "raining": "raining now -> skip"},
    "sk": {"fell": "spadlo {0} mm", "expected": "o\u010dak\u00e1va sa {0} mm", "skip_rain": "aspo\u0148 {0} mm -> presko\u010di\u0165",
           "wind": "vietor {0} km/h -> presko\u010di\u0165", "frost": "{0} \u00b0C na za\u010diatku -> presko\u010di\u0165 (mr\u00e1z)",
           "max": "max {0} \u00b0C", "pct": "{0} % min\u00fat", "gust": "n\u00e1razy {0} km/h -> presko\u010di\u0165",
           "raining": "pr\u00e1ve pr\u0161\u00ed -> presko\u010di\u0165"},
}


def decide(cfg: Dict[str, Any], start: datetime, now: datetime, hourly=None, daily=None,
           fallen: Optional[float] = None, current_temp: Optional[float] = None, lang: str = "en",
           current: Optional[Dict[str, Any]] = None) -> Decision:
    """Decision for a run starting at start. cfg = merged(). Times timezone-aware."""
    tx = TEXT.get(lang, TEXT["en"])
    d = Decision()
    if cfg["mode"] == "off":
        return d
    soon = (start - now) <= timedelta(hours=24)
    exp = expected_rain(cfg, hourly, daily, start)
    fell = (fallen or 0.0) if soon else 0.0
    d.rain = fell + exp
    if fell:
        d.reasons.append(tx["fell"].format(f"{fell:.1f}"))
    if exp:
        d.reasons.append(tx["expected"].format(f"{exp:.1f}"))
    t_start = current_temp if (current_temp is not None and (start - now) <= timedelta(hours=1)) \
        else at(hourly, start, "temp")
    if t_start is None and start.hour < 10:   # beyond the hourly forecast: a morning run is near the daily low
        t_start = next((x["low"] for x in daily or [] if x["t"].date() == start.date() and x.get("low") is not None), None)
    now_ish = (start - now) <= timedelta(hours=1)
    cur = current or {}
    if now_ish and cur.get("raining"):
        d.action, d.factor = "skip", 0.0
        d.reasons.append(tx["raining"])
        return d
    if now_ish and cfg["skip_gust"] and cur.get("gust") is not None and cur["gust"] >= cfg["skip_gust"]:
        d.action, d.factor, d.wind = "skip", 0.0, cur.get("wind")
        d.reasons.append(tx["gust"].format(f"{cur['gust']:.0f}"))
        return d
    d.wind = cur.get("wind") if now_ish and cur.get("wind") is not None else at(hourly, start, "wind")
    if d.wind is None:
        d.wind = next((x["wind"] for x in daily or [] if x["t"].date() == start.date() and x.get("wind") is not None), None)
    if cfg["skip_rain"] and d.rain >= cfg["skip_rain"]:
        d.action, d.factor = "skip", 0.0
        d.reasons.append(tx["skip_rain"].format(f"{cfg['skip_rain']:g}"))
        return d
    if cfg["skip_wind"] and d.wind is not None and d.wind >= cfg["skip_wind"]:
        d.action, d.factor = "skip", 0.0
        d.reasons.append(tx["wind"].format(f"{d.wind:.0f}"))
        return d
    if t_start is not None and t_start < cfg["skip_cold"]:
        d.action, d.factor = "skip", 0.0
        d.reasons.append(tx["frost"].format(_deg(t_start)))
        return d
    d.temp = day_max(hourly, daily, start.date())
    if d.temp is None and current_temp is not None and soon:
        d.temp = current_temp
    f = temp_factor(cfg, d.temp)
    if d.temp is not None and cfg["per_degree"]:
        d.reasons.append(tx["max"].format(_deg(d.temp)))
    if cfg["scale_rain"] and cfg["skip_rain"] and d.rain:
        f *= max(0.0, 1.0 - d.rain / cfg["skip_rain"])
    d.factor = _clamp(cfg, f)
    if abs(d.factor - 1.0) >= 0.05:
        d.action = "adjust"
        d.reasons.append(tx["pct"].format(round(d.factor * 100)))
    return d
