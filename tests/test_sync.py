import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import discovery as D  # noqa: E402
import sync as S  # noqa: E402


def F(n, order=0):
    return D.ValveProposal(n.title(), f"switch.{n}", f"switch.en_{n}", f"number.{n}_duration", 60, order)


def V(zid, n, order, **kw):
    return {"id": zid, "name": n.title(), "order": order, "enabled": True, "valve_switch": f"switch.{n}",
            "enable_switch": f"switch.en_{n}", "duration": f"number.{n}_duration", "max_minutes": 60, **kw}


SAVED = [V("zone_1", "a", 0), V("zone_2", "b", 1), V("zone_3", "c", 2), V("zone_4", "d", 3), V("zone_5", "e", 4)]


def ents(*names):
    return {f"{p}{n}{s}" for n in names for p, s in (("switch.", ""), ("switch.en_", ""), ("number.", "_duration"))}


class SyncTest(unittest.TestCase):
    def test_new_valve_in_the_middle_gets_its_esp_place(self):
        found = [F("a"), F("b"), F("c"), F("d"), F("new"), F("e")]
        r = S.sync(SAVED, found, ents("a", "b", "c", "d", "new", "e"), S.signature([F(x) for x in "abcde"]))
        self.assertEqual([v["id"] for v in r.added], ["zone_6"])
        self.assertEqual([(v["id"], v["order"]) for v in r.valves],
                         [("zone_1", 0), ("zone_2", 1), ("zone_3", 2), ("zone_4", 3), ("zone_6", 4), ("zone_5", 5)])
        self.assertTrue(r.changed)
        self.assertTrue(r.moved)            # E moved from 4 to 5
        self.assertEqual(r.missing, [])

    def test_nothing_changed(self):
        found = [F(x) for x in "abcde"]
        r = S.sync(SAVED, found, ents(*"abcde"), S.signature(found))
        self.assertFalse(r.changed)
        self.assertEqual(r.added, [])

    def test_manual_position_is_kept_while_the_esp_order_is_the_same(self):
        found = [F(x) for x in "abcde"]
        manual = [V("zone_1", "a", 0), V("zone_2", "b", 2), V("zone_3", "c", 1), V("zone_4", "d", 3), V("zone_5", "e", 4)]
        r = S.sync(manual, found, ents(*"abcde"), S.signature(found))
        self.assertFalse(r.changed)

    def test_first_sync_takes_the_esp_order(self):
        found = [F(x) for x in "abcde"]
        manual = [V("zone_1", "a", 0), V("zone_2", "b", 2), V("zone_3", "c", 1), V("zone_4", "d", 3), V("zone_5", "e", 4)]
        r = S.sync(manual, found, ents(*"abcde"), None)
        self.assertEqual([v["id"] for v in r.valves], ["zone_1", "zone_2", "zone_3", "zone_4", "zone_5"])
        self.assertTrue(r.changed)

    def test_valve_moved_in_the_yaml(self):
        found = [F("a"), F("b"), F("e"), F("c"), F("d")]
        r = S.sync(SAVED, found, ents(*"abcde"), S.signature([F(x) for x in "abcde"]))
        self.assertEqual([v["id"] for v in r.valves], ["zone_1", "zone_2", "zone_5", "zone_3", "zone_4"])
        self.assertTrue(r.moved)
        self.assertEqual(r.added, [])

    def test_gone_valve_is_reported_not_removed(self):
        found = [F(x) for x in "abde"]
        r = S.sync(SAVED, found, ents(*"abde"), S.signature([F(x) for x in "abcde"]))
        self.assertEqual([v["id"] for v in r.missing], ["zone_3"])
        self.assertIn("zone_3", [v["id"] for v in r.valves])
        self.assertEqual(r.valves[-1]["id"], "zone_3")      # after the ones on the ESP

    def test_unavailable_entities_are_not_missing(self):
        # the ESP is offline: nothing found, but the entities still exist -> no change, nothing missing
        r = S.sync(SAVED, [], ents(*"abcde"), S.signature([F(x) for x in "abcde"]))
        self.assertEqual(r.missing, [])
        self.assertEqual(r.added, [])

    def test_renamed_entity_is_taken_over(self):
        f = D.ValveProposal("A", "switch.a", "switch.en_a_new", "number.a_duration", 90, 0)
        r = S.sync(SAVED[:1], [f], {"switch.a", "switch.en_a_new", "number.a_duration"}, None)
        self.assertEqual(r.valves[0]["enable_switch"], "switch.en_a_new")
        self.assertEqual(r.valves[0]["max_minutes"], 90)
        self.assertEqual(r.valves[0]["id"], "zone_1")

    def test_new_id_skips_reserved(self):
        r = S.sync(SAVED[:1], [F("a"), F("x")], ents("a", "x"), None, reserved=["zone_2"])
        self.assertEqual(r.added[0]["id"], "zone_3")

    def test_incomplete_found_valve_is_ignored(self):
        half = D.ValveProposal("Half", "switch.h", None, None, None, 1)
        r = S.sync(SAVED[:1], [F("a"), half], ents("a"), None)
        self.assertEqual(r.added, [])


if __name__ == "__main__":
    unittest.main()


class IgnoredTest(unittest.TestCase):
    def test_ignored_valve_is_not_added_again(self):
        found = [F("a"), F("old"), F("b")]
        r = S.sync(SAVED[:2], found, ents("a", "old", "b"), None, ignored=["number.old_duration"])
        self.assertEqual(r.added, [])
        self.assertEqual([(v["id"], v["order"]) for v in r.valves], [("zone_1", 0), ("zone_2", 1)])
