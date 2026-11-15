import os, sys, unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))
import leak as L  # noqa: E402

TZ = timezone(timedelta(hours=1))
T0 = datetime(2026, 7, 10, 14, 0, tzinfo=TZ)


def cfg(**k):
    return L.merged({"mode": "on", **k})


def run(c, flows, quiet=lambda m: False, snoozed=lambda m: False, start=T0):
    """flows: list of (minute, L/min); returns the minutes at which an alarm fired."""
    w, out = L.LeakWatch(), []
    for m, f in flows:
        t = start + timedelta(minutes=m)
        if w.step(c, t, f, quiet(m), snoozed(m), t):
            out.append(m)
    return out


class LeakTest(unittest.TestCase):
    def test_off(self):
        self.assertEqual(run(L.merged({}), [(m, 10) for m in range(60)]), [])

    def test_alarm_after_duration_once(self):
        self.assertEqual(run(cfg(duration=20), [(m, 8) for m in range(60)]), [20])

    def test_short_use_no_alarm(self):
        flows = [(m, 8 if m % 30 < 10 else 0) for m in range(120)]   # 10 min of water every 30 min
        self.assertEqual(run(cfg(duration=20), flows), [])

    def test_below_min_flow(self):
        self.assertEqual(run(cfg(min_flow=1.0), [(m, 0.6) for m in range(60)]), [])

    def test_quiet_window_resets(self):
        flows = [(m, 8) for m in range(60)]
        self.assertEqual(run(cfg(duration=20), flows, quiet=lambda m: m < 30), [50])

    def test_snooze(self):
        self.assertEqual(run(cfg(duration=20), [(m, 8) for m in range(90)], snoozed=lambda m: m < 70), [70])

    def test_night_is_stricter(self):
        c = cfg(duration=20, night=True, night_from="23:00", night_to="05:00", night_duration=5)
        self.assertEqual(run(c, [(m, 8) for m in range(30)], start=T0.replace(hour=23, minute=30)), [5])
        self.assertTrue(L.is_night(c, T0.replace(hour=2)))
        self.assertFalse(L.is_night(c, T0.replace(hour=12)))

    def test_alarm_again_after_flow_stops(self):
        flows = [(m, 8 if m < 25 or m >= 40 else 0) for m in range(80)]
        self.assertEqual(run(cfg(duration=20), flows), [20, 60])

    def test_validation(self):
        for bad in ({"mode": "x"}, {"min_flow": 0}, {"night_from": "25"}, {"foo": 1}):
            with self.assertRaises(L.LeakConfigError):
                L.merged(bad)
