import os
import sys
import unittest
from datetime import date, time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import executor as X  # noqa: E402
import model as M  # noqa: E402
import planner as P  # noqa: E402

TZ = ZoneInfo("Europe/Bratislava")
VALVES = [
    {"id": "zone_1", "name": "Drippers", "order": 0, "enable_switch": "switch.en1", "duration": "number.d1", "max_minutes": 90},
    {"id": "zone_2", "name": "Field", "order": 1, "enable_switch": "switch.en2", "duration": "number.d2", "max_minutes": 45},
    {"id": "zone_3", "name": "Lawn", "order": 2, "enable_switch": "switch.en3", "duration": "number.d3", "max_minutes": 60},
]
CTRL = {"main_switch": "switch.main", "reverse": "switch.rev", "standby": "switch.standby",
        "multiplier": "number.mult", "repeat": "number.rep"}


def states(**over):
    s = {"switch.main": "off", "switch.rev": "off", "switch.standby": "off", "number.mult": "1.5", "number.rep": "0",
         "switch.en1": "on", "switch.en2": "off", "switch.en3": "on",
         "number.d1": "60", "number.d2": "25", "number.d3": "15"}
    s.update(over)
    out = {k: {"state": v, "attributes": {}} for k, v in s.items()}
    for n, mx in (("number.d1", 90), ("number.d2", 45), ("number.d3", 60)):
        out[n]["attributes"] = {"unit_of_measurement": "min", "step": 1, "max": mx, "min": 1}
    return out


class Model(unittest.TestCase):
    CFG = {
        "zones": {"zone_2": {"enabled": False}, "zone_3": {"name": "Lawn West", "max_per_run": 30}},
        "slots": [{"id": "m", "anchor": {"mode": "finish", "ref": "sunrise", "offset": -15}, "reverse": True,
                   "days": [0, 2], "zones": [{"zone": "zone_1", "minutes": 20}, {"zone": "zone_3", "minutes": 40}]}],
        "settings": {"merge_window": 30},
    }

    def test_parse(self):
        zones, slots, settings = M.parse(self.CFG, VALVES, valve_overlap=5)
        self.assertEqual([(z.id, z.name, z.enabled, z.max_per_run, z.hard_max) for z in zones],
                         [("zone_1", "Drippers", True, None, 90), ("zone_2", "Field", False, None, 45),
                          ("zone_3", "Lawn West", True, 30, 60)])
        s = slots[0]
        self.assertEqual((s.anchor.mode, s.anchor.ref, s.anchor.offset, s.reverse, s.days),
                         ("finish", "sunrise", -15, True, frozenset({0, 2})))
        self.assertEqual((settings.merge_window, settings.valve_overlap, settings.merge_mode), (30, 5, "window"))

    def test_defaults_parse(self):
        zones, slots, _ = M.parse({"slots": M.DEFAULT_SLOTS}, VALVES)
        self.assertEqual([s.anchor.at for s in slots], [time(5), time(12), time(16), time(20)])

    def test_errors_are_precise(self):
        bad = [
            ({"slots": [{"id": "x", "anchor": {"at": "5h"}}]}, "HH:MM"),
            ({"slots": [{"id": "x", "anchor": {"at": "05:00"}, "zones": [{"zone": "nope", "minutes": 5}]}]}, "does not exist"),
            ({"slots": [{"id": "x", "anchor": {"at": "05:00"}, "days": [7]}]}, "0 (Mon) .. 6 (Sun)"),
            ({"slots": [{"id": "x", "anchor": {"at": "05:00"}}, {"id": "x", "anchor": {"at": "06:00"}}]}, "used twice"),
            ({"settings": {"merge_mode": "magic"}}, "window, overlap, shift"),
            ({"slots": [{"id": "x", "anchor": {"ref": "time"}}]}, "anchor.at is required"),
        ]
        for cfg, text in bad:
            with self.assertRaises(M.ConfigError) as cm:
                M.parse(cfg, VALVES)
            self.assertIn(text, str(cm.exception))

    def test_pump_delay_counts_in_timing_only_with_auto_on(self):
        cfg = {"slots": [{"id": "m", "anchor": {"at": "05:00"}, "zones": [{"zone": "zone_1", "minutes": 10}]}],
               "pump": {"entity": "switch.pump", "auto_on": True, "delay": 30}}
        self.assertEqual(M.parse(cfg, VALVES)[2].pump_delay, 30)
        cfg["pump"]["auto_on"] = False
        self.assertEqual(M.parse(cfg, VALVES)[2].pump_delay, 0)

    def test_pump_validation(self):
        self.assertEqual(M.pump_from_dict(None), {})
        self.assertEqual(M.pump_from_dict({"entity": "input_boolean.p"})["auto_off"], True)
        for bad, text in (({"entity": "sensor.p"}, "pump.entity"), ({"entity": "switch.p", "delay": 900}, "600"),
                          ({"entity": "switch.p", "speed": 1}, "unknown field")):
            with self.assertRaises(M.ConfigError) as cm:
                M.pump_from_dict(bad)
            self.assertIn(text, str(cm.exception))

    def test_run_to_dict(self):
        zones, slots, settings = M.parse(self.CFG, VALVES)
        sun = lambda d: (P.datetime.combine(d, time(6, 0), TZ), P.datetime.combine(d, time(19, 0), TZ))
        plan = P.plan(zones, slots, settings, date(2026, 11, 16), 1, TZ, sun)
        d = M.run_to_dict(plan.runs[0], {z.id: z.name for z in zones})
        self.assertEqual(d["end"], "2026-11-16T05:45:00+01:00")
        self.assertEqual([(z["name"], z["minutes"]) for z in d["zones"]], [("Lawn West", 30), ("Drippers", 20)])
        self.assertTrue(d["reverse"])


class Executor(unittest.TestCase):
    def run_(self, reverse=False, steps=(("zone_3", 22.5), ("zone_1", 20))):
        from datetime import datetime
        t = datetime(2026, 11, 16, 5, 0, tzinfo=TZ)
        return P.Run(date(2026, 11, 16), t, t, [P.Step(z, m, m, "s") for z, m in steps], ["s"], "start", t, [], reverse)

    def test_calls_in_order(self):
        calls = [c.as_text() for c in X.start_calls(self.run_(reverse=True), VALVES, CTRL, states())]
        self.assertEqual(calls, [
            "number.set_value number.mult (value=1)",
            "number.set_value number.rep (value=0)",
            "number.set_value number.d3 (value=23)",        # step 1 -> 22.5 rounded half up
            "number.set_value number.d1 (value=20)",
            "switch.turn_off switch.en2",
            "switch.turn_on switch.en3",
            "switch.turn_on switch.en1",
            "switch.turn_on switch.rev",
            "switch.turn_on switch.main",
        ])

    def test_units_and_clamp(self):
        st = states()
        st["number.d1"]["attributes"] = {"unit_of_measurement": "s", "max": 3600}
        self.assertEqual(X.to_number_value(20, st, "number.d1"), 1200)
        self.assertEqual(X.to_number_value(80, st, "number.d1"), 3600)

    def test_optional_controller_entities(self):
        ctrl = {"main_switch": "switch.main"}
        calls = [c.as_text() for c in X.start_calls(self.run_(), VALVES, ctrl, states())]
        self.assertEqual(calls[0], "number.set_value number.d3 (value=23)")
        self.assertEqual(calls[-1], "switch.turn_on switch.main")
        self.assertFalse(any("rev" in c or "mult" in c for c in calls))

    def test_precheck(self):
        r = self.run_()
        self.assertIsNone(X.precheck(r, VALVES, CTRL, states()))
        self.assertIn("already running", X.precheck(r, VALVES, CTRL, states(**{"switch.main": "on"})))
        self.assertIn("standby", X.precheck(r, VALVES, CTRL, states(**{"switch.standby": "on"})))
        self.assertIn("unavailable: number.d2", X.precheck(r, VALVES, CTRL, states(**{"number.d2": "unavailable"})))
        self.assertIn("no main switch", X.precheck(r, VALVES, {}, states()))

    def test_snapshot_and_restore(self):
        snap = X.take_snapshot(VALVES, CTRL, states())
        self.assertNotIn("switch.main", snap)
        self.assertNotIn("switch.standby", snap)
        calls = [c.as_text() for c in X.restore_calls(snap)]
        self.assertIn("number.set_value number.mult (value=1.5)", calls)
        self.assertIn("number.set_value number.d1 (value=60.0)", calls)
        self.assertIn("switch.turn_off switch.en2", calls)
        self.assertIn("switch.turn_on switch.en3", calls)


if __name__ == "__main__":
    unittest.main()


class HealthTest(unittest.TestCase):
    def test_missing_and_unavailable(self):
        import executor as X
        valves = [{"id": "zone_1", "enable_switch": "switch.en1", "duration": "number.d1"}]
        ctrl = {"main_switch": "switch.main"}
        ok = {"switch.main": {"state": "off"}, "switch.en1": {"state": "on"}, "number.d1": {"state": "5"}}
        self.assertEqual(X.health(valves, ctrl, ok), {"missing": [], "unavailable": []})
        down = dict(ok, **{"switch.main": {"state": "unavailable"}})
        self.assertEqual(X.health(valves, ctrl, down)["unavailable"], ["switch.main"])
        gone = {"switch.main": {"state": "off"}}
        self.assertEqual(X.health(valves, ctrl, gone)["missing"], ["switch.en1", "number.d1"])



class SwitchedOffZoneTest(unittest.TestCase):
    def test_off_entry_kept_but_not_planned(self):
        import model as M
        valves = [{"id": "zone_1", "name": "A", "order": 0}, {"id": "zone_2", "name": "B", "order": 1}]
        cfg = {"slots": [{"id": "m", "anchor": {"mode": "start", "ref": "time", "at": "05:00"},
                          "zones": [{"zone": "zone_1", "minutes": 10},
                                    {"zone": "zone_2", "minutes": 7, "days": [1], "enabled": False},
                                    {"zone": "zone_9", "enabled": False}]}]}   # off entries are not validated
        _z, slots, _s = M.parse(cfg, valves)
        self.assertEqual([e.zone_id for e in slots[0].zones], ["zone_1"])
