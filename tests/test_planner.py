"""Unit tests for the planner core (stdlib unittest; pytest runs them as well).

Run:  python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import planner as P  # noqa: E402

TZ = ZoneInfo("Europe/Bratislava")
MON = date(2026, 11, 16)  # a Monday


def z(id_, order=0, **kw):
    return P.Zone(id_, id_, order, **kw)


def slot(id_, at, zones, mode="start", ref="time", offset=0, **kw):
    return P.Slot(id_, id_, P.Anchor(mode, ref, at, offset), tuple(P.SlotZone(zid, m) for zid, m in zones), **kw)


def hm(dt):
    return dt.strftime("%H:%M:%S")


ZONES = [z("z1", 0), z("z2", 1), z("z3", 2)]
PLAIN = P.Settings()


def one_day(slots, zones=ZONES, settings=PLAIN, **kw):
    return P.plan(zones, slots, settings, MON, 1, TZ, **kw)


class BasicRuns(unittest.TestCase):
    def test_start_at_esp_order(self):
        p = one_day([slot("m", time(5, 0), [("z2", 10), ("z1", 20)])])
        self.assertEqual(len(p.runs), 1)
        r = p.runs[0]
        self.assertEqual(r.zone_ids(), ["z1", "z2"])          # ESP order, not the order in the slot
        self.assertEqual((hm(r.start), hm(r.end)), ("05:00:00", "05:30:00"))
        self.assertEqual(r.start.tzinfo, TZ)

    def test_reverse(self):
        rev = one_day([slot("m", time(5, 0), [("z1", 1), ("z2", 1), ("z3", 1)], reverse=True)])
        self.assertEqual(rev.runs[0].zone_ids(), ["z3", "z2", "z1"])
        self.assertTrue(rev.runs[0].reverse)

    def test_finish_by_with_pump_delay_and_overlap(self):
        s = P.Settings(pump_delay=30, valve_overlap=5)
        p = one_day([slot("e", time(21, 0), [("z1", 10), ("z2", 10)], mode="finish")], settings=s)
        r = p.runs[0]
        # 20 min + 30 s pump - 5 s overlap = 20:25
        self.assertEqual(hm(r.end), "21:00:00")
        self.assertEqual(hm(r.start), "20:39:35")
        self.assertEqual(r.duration, timedelta(minutes=20, seconds=25))

    def test_valve_gap(self):
        p = one_day([slot("m", time(5, 0), [("z1", 10), ("z2", 10), ("z3", 10)])], settings=P.Settings(valve_gap=10))
        self.assertEqual(p.runs[0].duration, timedelta(minutes=30, seconds=20))

    def test_sunrise_anchor(self):
        sun = lambda d: (datetime.combine(d, time(6, 10), TZ), datetime.combine(d, time(19, 45), TZ))
        p = one_day([slot("m", None, [("z1", 20)], mode="finish", ref="sunrise", offset=-15)], sun=sun)
        self.assertEqual((hm(p.runs[0].start), hm(p.runs[0].end)), ("05:35:00", "05:55:00"))
        p2 = one_day([slot("e", None, [("z1", 20)], ref="sunset", offset=30)], sun=sun)
        self.assertEqual(hm(p2.runs[0].start), "20:15:00")

    def test_missing_sun_data_is_a_conflict(self):
        p = one_day([slot("m", None, [("z1", 20)], ref="sunrise")], sun=lambda d: None)
        self.assertEqual(p.runs, [])
        self.assertEqual([c.kind for c in p.conflicts], ["no_sun"])

    def test_dst_change_keeps_real_length(self):
        # 2027-03-28 02:00 -> 03:00 in Central Europe
        p = P.plan(ZONES, [slot("n", time(1, 30), [("z1", 120)])], PLAIN, date(2027, 3, 28), 1, TZ)
        r = p.runs[0]
        self.assertEqual(r.duration, timedelta(hours=2))
        self.assertEqual(hm(r.end), "04:30:00")


class Days(unittest.TestCase):
    def test_weekdays(self):
        p = P.plan(ZONES, [slot("m", time(5, 0), [("z1", 5)], days=frozenset({0, 2}))], PLAIN, MON, 7, TZ)
        self.assertEqual([r.day.weekday() for r in p.runs], [0, 2])

    def test_every_n_days(self):
        p = P.plan(ZONES, [slot("m", time(5, 0), [("z1", 5)], every_n_days=3, every_n_from=MON)], PLAIN, MON, 7, TZ)
        self.assertEqual([r.day.day for r in p.runs], [16, 19, 22])

    def test_zone_days_inside_slot(self):
        s = P.Slot("m", "m", P.Anchor(at=time(5, 0)),
                   (P.SlotZone("z1", 5), P.SlotZone("z2", 5, days=frozenset({0}))))
        p = P.plan(ZONES, [s], PLAIN, MON, 2, TZ)
        self.assertEqual([r.zone_ids() for r in p.runs], [["z1", "z2"], ["z1"]])


class Skips(unittest.TestCase):
    def test_disabled_zone_and_slot(self):
        zones = [z("z1", 0, enabled=False), z("z2", 1)]
        p = one_day([slot("m", time(5, 0), [("z1", 5), ("z2", 5)]),
                     slot("e", time(20, 0), [("z2", 5)], enabled=False)], zones=zones)
        self.assertEqual([r.zone_ids() for r in p.runs], [["z2"]])

    def test_slot_with_only_disabled_zones_makes_no_run(self):
        p = one_day([slot("m", time(5, 0), [("z1", 5)])], zones=[z("z1", enabled=False)])
        self.assertEqual(p.runs, [])

    def test_unknown_zone(self):
        p = one_day([slot("m", time(5, 0), [("nope", 5), ("z1", 5)])])
        self.assertEqual(p.runs[0].zone_ids(), ["z1"])
        self.assertEqual([c.kind for c in p.conflicts], ["unknown_zone"])


class MultiplierAndLimits(unittest.TestCase):
    def test_multiplier_and_opt_out(self):
        p = one_day([slot("m", time(5, 0), [("z1", 10)]),
                     slot("e", time(20, 0), [("z1", 10)], use_multiplier=False)], multiplier=1.5)
        self.assertEqual([r.steps[0].minutes for r in p.runs], [15, 10])
        self.assertEqual(p.runs[0].steps[0].base_minutes, 10)

    def test_weather_opt_out_and_drop(self):
        zones = [P.Zone("z1", "Lawn", 0), P.Zone("z2", "Greenhouse", 1, weather=False)]
        p = one_day([slot("m", time(5, 0), [("z1", 10), ("z2", 10)])], zones=zones,
                    multiplier=lambda d, sid: 1.5)
        self.assertEqual([s.minutes for s in p.runs[0].steps], [15, 10])
        p = one_day([slot("m", time(5, 0), [("z1", 10), ("z2", 10)])], zones=zones,
                    multiplier=lambda d, sid: 0.0)
        self.assertEqual([s.zone_id for s in p.runs[0].steps], ["z2"])
        self.assertIn("weather: Lawn skipped", p.runs[0].notes)
        p = one_day([slot("m", time(5, 0), [("z1", 10)])], zones=zones, multiplier=lambda d, sid: 0.0)
        self.assertEqual(p.runs, [])

    def test_multiplier_per_day(self):
        p = P.plan(ZONES, [slot("m", time(5, 0), [("z1", 10)])], PLAIN, MON, 2, TZ,
                   multiplier=lambda d: 2.0 if d.weekday() == 0 else 1.0)
        self.assertEqual([r.steps[0].minutes for r in p.runs], [20, 10])

    def test_per_run_and_hard_cap(self):
        zones = [z("z1", 0, max_per_run=45, hard_max=90), z("z2", 1, hard_max=30)]
        p = one_day([slot("m", time(5, 0), [("z1", 40), ("z2", 25)])], zones=zones, multiplier=1.5)
        self.assertEqual([s.minutes for s in p.runs[0].steps], [45, 30])
        self.assertEqual([c.kind for c in p.conflicts], ["limit", "limit"])
        self.assertEqual(len(p.runs[0].notes), 2)

    def test_daily_limit_caps_then_leaves_out(self):
        zones = [z("z1", 0, max_per_day=30), z("z2", 1)]
        p = P.plan(zones, [slot("m", time(5, 0), [("z1", 20)]),
                           slot("a", time(12, 0), [("z1", 20), ("z2", 5)]),
                           slot("e", time(20, 0), [("z1", 20)])], PLAIN, MON, 1, TZ)
        self.assertEqual([[(s.zone_id, s.minutes) for s in r.steps] for r in p.runs],
                         [[("z1", 20)], [("z1", 10), ("z2", 5)]])      # evening dropped entirely
        kinds = [c.kind for c in p.conflicts]
        self.assertIn("limit", kinds)
        self.assertIn("dropped", kinds)
        self.assertEqual(hm(p.runs[1].end), "12:15:00")                # re-timed after the cap


class Merging(unittest.TestCase):
    def test_smaller_later_run_is_appended(self):
        p = one_day([slot("a", time(5, 0), [("z1", 10), ("z2", 10)]),
                     slot("b", time(5, 40), [("z3", 10)])])
        self.assertEqual(len(p.runs), 1)
        r = p.runs[0]
        self.assertTrue(r.merged)
        self.assertEqual(r.slot_ids, ["a", "b"])
        self.assertEqual(r.zone_ids(), ["z1", "z2", "z3"])
        self.assertEqual((hm(r.start), hm(r.end)), ("05:00:00", "05:30:00"))

    def test_merged_run_follows_esp_order_and_starts_at_the_earlier_start(self):
        p = one_day([slot("a", time(5, 0), [("z3", 10)]),
                     slot("b", time(5, 20), [("z1", 10), ("z2", 10)])])
        r = p.runs[0]
        self.assertEqual(r.zone_ids(), ["z1", "z2", "z3"])                     # one ESP cycle
        self.assertEqual((hm(r.start), hm(r.end)), ("05:00:00", "05:30:00"))

    def test_merge_with_finish_by_finishes_by_the_earliest_finish(self):
        p = one_day([slot("a", time(5, 0), [("z1", 10)]),
                     slot("b", time(5, 40), [("z2", 10), ("z3", 10)], mode="finish")])
        r = p.runs[0]
        self.assertEqual((hm(r.start), hm(r.end)), ("05:10:00", "05:40:00"))

    def test_merge_mixed_directions_takes_the_bigger_parts_direction(self):
        p = one_day([slot("a", time(5, 0), [("z1", 10), ("z2", 10)], reverse=True),
                     slot("b", time(5, 30), [("z3", 10)])])
        r = p.runs[0]
        self.assertTrue(r.reverse)
        self.assertEqual(r.zone_ids(), ["z3", "z2", "z1"])
        self.assertTrue(any("reversed" in n for n in r.notes))

    def test_finish_anchored_bigger_keeps_its_finish(self):
        p = one_day([slot("a", time(8, 0), [("z1", 10), ("z2", 10)], mode="finish"),
                     slot("b", time(8, 30), [("z3", 10)])])
        r = p.runs[0]
        self.assertEqual(r.zone_ids(), ["z1", "z2", "z3"])
        self.assertEqual((hm(r.start), hm(r.end)), ("07:30:00", "08:00:00"))

    def test_outside_window_stays_separate(self):
        p = one_day([slot("a", time(5, 0), [("z1", 10)]), slot("b", time(6, 30), [("z2", 10)])],
                    settings=P.Settings(merge_window=60))
        self.assertEqual(len(p.runs), 2)

    def test_chain_is_judged_on_the_merged_run(self):
        # the gap is measured from the END of the (already merged) run to the next start
        s = P.Settings(merge_window=30)
        chain = one_day([slot("a", time(5, 0), [("z1", 10)]), slot("b", time(5, 25), [("z2", 10)]),
                         slot("c", time(5, 45), [("z3", 10)])], settings=s)
        self.assertEqual(len(chain.runs), 1)
        self.assertEqual(chain.runs[0].zone_ids(), ["z1", "z2", "z3"])
        # a+b becomes 05:00-05:20, so c at 06:00 is 40 min away: separate
        stop = one_day([slot("a", time(5, 0), [("z1", 10)]), slot("b", time(5, 30), [("z2", 10)]),
                        slot("c", time(6, 0), [("z3", 10)])], settings=s)
        self.assertEqual([r.zone_ids() for r in stop.runs], [["z1", "z2"], ["z3"]])

    def test_overlap_mode(self):
        apart = one_day([slot("a", time(5, 0), [("z1", 30)]), slot("b", time(5, 40), [("z2", 10)])],
                        settings=P.Settings(merge_mode="overlap"))
        self.assertEqual(len(apart.runs), 2)
        over = one_day([slot("a", time(5, 0), [("z1", 30)]), slot("b", time(5, 20), [("z2", 10)])],
                       settings=P.Settings(merge_mode="overlap"))
        self.assertEqual(len(over.runs), 1)
        self.assertEqual((hm(over.runs[0].start), hm(over.runs[0].end)), ("05:00:00", "05:40:00"))

    def test_shift_mode(self):
        p = one_day([slot("a", time(5, 0), [("z1", 30)]), slot("b", time(5, 15), [("z2", 10)])],
                    settings=P.Settings(merge_mode="shift"))
        self.assertEqual([(hm(r.start), hm(r.end)) for r in p.runs],
                         [("05:00:00", "05:30:00"), ("05:30:00", "05:40:00")])
        self.assertTrue(any("shifted" in n for n in p.runs[1].notes))
        self.assertEqual(p.conflicts, [])

    def test_shift_that_misses_finish_by_is_a_conflict(self):
        p = one_day([slot("a", time(5, 0), [("z1", 30)]), slot("b", time(5, 25), [("z2", 10)], mode="finish")],
                    settings=P.Settings(merge_mode="shift"))
        self.assertEqual(hm(p.runs[1].end), "05:40:00")
        self.assertEqual([c.kind for c in p.conflicts], ["finish_missed"])


class SameZone(unittest.TestCase):
    SLOTS = [slot("a", time(5, 0), [("z1", 10), ("z2", 10)]), slot("b", time(5, 30), [("z1", 20)])]

    def test_longer(self):
        r = one_day(self.SLOTS).runs
        self.assertEqual(len(r), 1)
        self.assertEqual([(s.zone_id, s.minutes) for s in r[0].steps], [("z1", 20), ("z2", 10)])

    def test_sum_respects_per_run_limit(self):
        zones = [z("z1", 0, max_per_run=25), z("z2", 1)]
        p = one_day(self.SLOTS, zones=zones, settings=P.Settings(same_zone="sum"))
        self.assertEqual([(s.zone_id, s.minutes) for s in p.runs[0].steps], [("z1", 25), ("z2", 10)])
        self.assertEqual([c.kind for c in p.conflicts], ["limit"])

    def test_separate_keeps_two_runs_and_shifts_on_overlap(self):
        apart = one_day(self.SLOTS, settings=P.Settings(same_zone="separate"))
        self.assertEqual(len(apart.runs), 2)
        over = one_day([slot("a", time(5, 0), [("z1", 10), ("z2", 10)]), slot("b", time(5, 10), [("z1", 20)])],
                       settings=P.Settings(same_zone="separate"))
        self.assertEqual([hm(r.start) for r in over.runs], ["05:00:00", "05:20:00"])


class CurrentSetupScenario(unittest.TestCase):
    """Modelled on a real installation: five zones, drippers 60 min, field 25, two lawns 15,
    5 s valve overlap. Morning in reverse order (lawns first, done quickly), evening in the
    default order (lawns last)."""

    ZONES = [z("drippers_a", 0, hard_max=90), z("drippers_b", 1, hard_max=90), z("field", 2, hard_max=45),
             z("lawn_s", 3, hard_max=60), z("lawn_w", 4, hard_max=60)]
    ALL = [("drippers_a", 60), ("drippers_b", 60), ("field", 25), ("lawn_s", 15), ("lawn_w", 15)]

    def test_morning_and_evening(self):
        s = P.Settings(valve_overlap=5)
        p = one_day([slot("morning", time(5, 0), self.ALL, reverse=True),
                     slot("evening", time(19, 0), self.ALL)], zones=self.ZONES, settings=s)
        morning, evening = p.runs
        self.assertEqual(morning.zone_ids(), ["lawn_w", "lawn_s", "field", "drippers_b", "drippers_a"])
        self.assertEqual(evening.zone_ids(), ["drippers_a", "drippers_b", "field", "lawn_s", "lawn_w"])
        self.assertEqual(hm(morning.end), "07:54:40")   # 175 min - 4 x 5 s
        self.assertEqual(p.conflicts, [])

    def test_heat_multiplier_hits_hard_max(self):
        p = one_day([slot("morning", time(5, 0), self.ALL)], zones=self.ZONES, multiplier=1.6)
        mins = {s.zone_id: s.minutes for s in p.runs[0].steps}
        self.assertEqual(mins, {"drippers_a": 90, "drippers_b": 90, "field": 40, "lawn_s": 24, "lawn_w": 24})
        self.assertEqual(len(p.conflicts), 2)   # both drippers capped at the ESP max


if __name__ == "__main__":
    unittest.main()
