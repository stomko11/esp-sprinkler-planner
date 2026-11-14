import os, sys, unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))
import weather as W  # noqa: E402
import stats as S    # noqa: E402

TZ = timezone(timedelta(hours=1))
NOW = datetime(2026, 7, 10, 3, 0, tzinfo=TZ)
START = datetime(2026, 7, 10, 5, 0, tzinfo=TZ)


def hourly(rain=0.0, prob=90, temp=20.0, wind=10.0, hours=24, at_hour=None):
    out = []
    for h in range(hours):
        t = NOW + timedelta(hours=h)
        r = rain if (at_hour is None or t.hour == at_hour) else 0.0
        out.append({"t": t, "temp": temp, "low": None, "rain": r, "prob": prob, "wind": wind})
    return out


def cfg(**k):
    return W.merged({"mode": "auto", "entity": "weather.home", **k})


class WeatherTest(unittest.TestCase):
    def test_off_runs(self):
        d = W.decide(W.merged({}), START, NOW, hourly(rain=10))
        self.assertEqual((d.action, d.factor), ("run", 1.0))

    def test_rain_skip(self):
        d = W.decide(cfg(), START, NOW, hourly(rain=5, at_hour=9))
        self.assertEqual(d.action, "skip")
        self.assertIn("5.0 mm rain expected", d.reasons)

    def test_rain_outside_window_not_counted(self):
        d = W.decide(cfg(window=2), START, NOW, hourly(rain=5, at_hour=12, temp=22))
        self.assertEqual(d.action, "run")

    def test_low_probability_ignored(self):
        d = W.decide(cfg(), START, NOW, hourly(rain=5, prob=20, at_hour=9, temp=22))
        self.assertEqual(d.action, "run")

    def test_fallen_rain_plus_scale(self):
        d = W.decide(cfg(per_degree=0), START, NOW, hourly(temp=22), fallen=2.0)
        self.assertEqual(d.action, "adjust")
        self.assertEqual(d.factor, 0.5)

    def test_fallen_rain_ignored_for_later_runs(self):
        later = START + timedelta(days=2)
        d = W.decide(cfg(per_degree=0), later, NOW, [], [], fallen=10.0)
        self.assertEqual(d.action, "run")

    def test_heat_factor_clamped(self):
        d = W.decide(cfg(), START, NOW, hourly(temp=40))
        self.assertEqual(d.factor, 1.6)
        self.assertEqual(d.action, "adjust")
        d = W.decide(cfg(), START, NOW, hourly(temp=27))
        self.assertEqual(d.factor, 1.2)

    def test_cool_reduces(self):
        d = W.decide(cfg(skip_cold=0), START, NOW, hourly(temp=12))
        self.assertEqual(d.factor, 0.6)

    def test_wind_and_frost_skip(self):
        self.assertEqual(W.decide(cfg(), START, NOW, hourly(wind=55, temp=22)).action, "skip")
        self.assertEqual(W.decide(cfg(), START, NOW, hourly(temp=2)).action, "skip")

    def test_daily_fallback(self):
        daily = [{"t": datetime(2026, 7, 10, 12, tzinfo=TZ), "temp": 22, "low": 12, "rain": 6, "prob": 80, "wind": 5}]
        self.assertEqual(W.decide(cfg(), START, NOW, [], daily).action, "skip")

    def test_beyond_hourly_uses_daily(self):
        far = START + timedelta(days=3)
        daily = [{"t": datetime(2026, 7, 13, 12, tzinfo=TZ), "temp": 22, "low": 1, "rain": 0, "prob": 0, "wind": 5}]
        d = W.decide(cfg(), far, NOW, hourly(temp=20), daily)
        self.assertEqual(d.action, "skip")
        self.assertIn("1 \u00b0C at the start -> skip (frost)", d.reasons)
        evening = far.replace(hour=19)
        self.assertEqual(W.decide(cfg(), evening, NOW, hourly(temp=2), daily).action, "run")

    def test_slovak_reasons(self):
        d = W.decide(cfg(), START, NOW, hourly(rain=5, at_hour=9), lang="sk")
        self.assertIn("o\u010dak\u00e1va sa 5.0 mm", d.reasons)

    def test_metered_minutes(self):
        st = {}
        S.add_zone(st, "2026-07-10", "z", 2)
        S.add_zone(st, "2026-07-10", "z", 1, l=12, kwh_=0.011)
        z = S.aggregate(st, date(2026, 7, 10), "day", 1)["rows"][0]["zones"]["z"]
        self.assertEqual((z["min"], z["lmin"], z["emin"], z["l"]), (3, 1, 1, 12))

    def test_current_sensors(self):
        soon = NOW + timedelta(minutes=30)
        self.assertEqual(W.decide(cfg(), soon, NOW, hourly(temp=22), current={"raining": True}).action, "skip")
        d = W.decide(cfg(), soon, NOW, hourly(temp=22), current={"gust": 70, "wind": 20})
        self.assertEqual(d.action, "skip")
        self.assertIn("gusts 70 km/h -> skip", d.reasons)
        self.assertEqual(W.decide(cfg(), soon, NOW, hourly(temp=22), current={"wind": 45}).action, "skip")
        # far runs ignore current values
        self.assertEqual(W.decide(cfg(), START + timedelta(days=1), NOW, hourly(temp=22, hours=60),
                                  current={"raining": True}).action, "run")

    def test_prices(self):
        self.assertEqual(S.meters_from_dict({"water_price": "2.5"})["water_price"], 2.5)
        with self.assertRaises(S.MetersConfigError):
            S.meters_from_dict({"energy_price": -1})

    def test_no_minus_zero(self):
        d = W.decide(cfg(), START, NOW, hourly(temp=-0.2))
        self.assertIn("0 \u00b0C at the start -> skip (frost)", d.reasons)

    def test_units(self):
        items = [{"datetime": "2026-07-10T05:00:00+01:00", "temperature": 86, "precipitation": 0.1,
                  "wind_speed": 10, "precipitation_probability": 50}]
        n = W.normalise(items, {"temperature": "\u00b0F", "precipitation": "in", "wind_speed": "m/s"},
                        datetime.fromisoformat)
        self.assertAlmostEqual(n[0]["temp"], 30.0)
        self.assertAlmostEqual(n[0]["rain"], 2.54)
        self.assertAlmostEqual(n[0]["wind"], 36.0)

    def test_validation(self):
        for bad in ({"mode": "x"}, {"mode": "auto"}, {"entity": "sensor.x"}, {"skip_rain": -1}, {"foo": 1},
                    {"min_factor": 90, "max_factor": 100, "per_degree": 2, "mode": "off", "base_temp": 99}):
            with self.assertRaises(W.WeatherConfigError):
                W.merged(bad)


class StatsTest(unittest.TestCase):
    def test_meters(self):
        self.assertEqual(S.meters_from_dict({"flow": "sensor.f", "pump_power": ""}), {"flow": "sensor.f", "flow_warn": 30.0, "drift_warn": 15.0})
        with self.assertRaises(S.MetersConfigError):
            S.meters_from_dict({"flow": "switch.x"})
        with self.assertRaises(S.MetersConfigError):
            S.meters_from_dict({"bogus": 1})

    def test_units(self):
        self.assertEqual(S.litres(1.5, "m\u00b3"), 1500)
        self.assertAlmostEqual(S.l_per_min(0.6, "m\u00b3/h"), 10)
        self.assertEqual(S.kwh(500, "Wh"), 0.5)
        self.assertEqual(S.watts(1.2, "kW"), 1200)

    def test_integrator(self):
        t = datetime(2026, 7, 10, 5, 0, tzinfo=TZ)
        i = S.Integrator(t, 10.0)             # 10 L/min
        i.add(t + timedelta(minutes=3), 20.0)
        self.assertAlmostEqual(i.total(t + timedelta(minutes=5)), 70.0)
        self.assertAlmostEqual(i.average(), 14.0)
        p = S.Integrator(t, 600.0, per_minute=False)   # 600 W for 30 min = 300 Wh
        self.assertAlmostEqual(p.total(t + timedelta(minutes=30)) / 1000, 0.3)

    def test_aggregate_and_totals(self):
        st = {}
        S.add_run(st, "2026-07-06")
        S.add_zone(st, "2026-07-06", "zone_1", 10, l=100, kwh_=0.1)
        S.add_zone(st, "2026-07-07", "zone_2", 5)
        S.add_skip(st, "2026-07-08", {"zone_1": 15})
        S.add_pump_energy(st, "2026-07-08", 0.05)
        S.add_zone(st, "2026-06-30", "zone_1", 7)
        today = date(2026, 7, 10)
        a = S.aggregate(st, today, "week", 2)
        self.assertEqual([r["key"] for r in a["rows"]], ["2026-W27", "2026-W28"])
        w = a["rows"][1]
        self.assertEqual((w["min"], w["l"], w["runs"], w["skips"], w["skipped_min"]), (15, 100, 1, 1, 15))
        self.assertAlmostEqual(w["kwh"], 0.15)
        self.assertEqual(a["rows"][0]["min"], 7)
        t = S.totals(st, today)
        self.assertEqual(t["week"]["min"], 15)
        self.assertEqual(t["month"]["min"], 15)
        self.assertEqual(t["year"]["min"], 22)
        self.assertIsNone(S.totals({"2026-07-07": {"zones": {"z": {"min": 1, "runs": 1}}}}, today)["week"]["l"])
        self.assertEqual(len(S.aggregate(st, today, "month", 3)["rows"]), 3)
        self.assertEqual(S.aggregate(st, today, "year", 1)["rows"][0]["min"], 22)

    def test_prune_seed(self):
        st = {"2020-01-01": {}, "2026-07-01": {}}
        S.prune(st, date(2026, 7, 10))
        self.assertEqual(list(st), ["2026-07-01"])
        S.seed_from_history(st, {"2026-07-02": {"zone_1": 3}, "2026-07-01": {"zone_1": 9}})
        self.assertEqual(st["2026-07-02"]["zones"]["zone_1"]["min"], 3)
        self.assertEqual(st["2026-07-01"], {})

    def test_flow_check(self):
        s = []
        for v in (10, 10.5, 9.8, 10.2):
            s = S.push_sample(s, v)
        self.assertIsNone(S.flow_check(s, 11, 30))
        self.assertEqual(S.flow_check(s, 15, 30)[0], "high")
        self.assertEqual(S.flow_check(s, 5, 30)[0], "low")
        self.assertIsNone(S.flow_check(s[:2], 5, 30))


if __name__ == "__main__":
    unittest.main()


class DriftTest(unittest.TestCase):
    def test_baseline_and_slow_drift(self):
        self.assertIsNone(S.baseline_from([10, 10, 10]))
        self.assertEqual(S.baseline_from([10, 10.2, 9.8, 10.1, 9.9, 5]), 10.0)
        samples = []
        for v in (10, 10, 9.8, 9.6, 9.3, 9.0, 8.7, 8.4, 8.1, 7.8):   # 2-3 % per run: no single jump
            self.assertIsNone(S.flow_check(samples, v, 30))
            samples = S.push_sample(samples, v)
        d = S.drift_check(10.0, samples, 15)
        self.assertIsNotNone(d)
        self.assertEqual((d[0], d[1], d[2]), (8.4, 10.0, -16))
        self.assertIsNone(S.drift_check(10.0, samples, 20))
        self.assertIsNone(S.drift_check(None, samples, 15))

    def test_meter_settings(self):
        self.assertEqual(S.meters_from_dict({})["drift_warn"], 15)
        with self.assertRaises(S.MetersConfigError):
            S.meters_from_dict({"drift_warn": 95})
