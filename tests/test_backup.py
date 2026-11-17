import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import backup as B  # noqa: E402

VALVES = [
    {"id": "zone_1", "name": "House", "order": 0, "enabled": True, "duration": "number.a_duration",
     "enable_switch": "switch.a_en", "valve_switch": "switch.a", "max_minutes": 90},
    {"id": "zone_2", "name": "Lawn South 1", "order": 1, "enabled": False, "duration": "number.b_duration",
     "enable_switch": "switch.b_en", "valve_switch": None, "max_minutes": 60},
    {"id": "zone_3", "name": "Lawn West", "order": 2, "enabled": True, "duration": "number.c_duration",
     "enable_switch": "switch.c_en", "valve_switch": "switch.c", "max_minutes": 60},
]
CONFIG = {
    "zones": {"zone_1": {"icon": "mdi:water"}, "zone_3": {"color": "#7cb342", "max_per_run": 20}},
    "slots": [{"id": "morning", "name": "Morning", "zones": [{"zone": "zone_1", "minutes": 10}, {"zone": "zone_3", "minutes": 15}]}],
    "settings": {"merge_mode": "shift"},
    "blockers": [{"id": "b1", "scope": "zones", "zones": ["zone_3", "zone_1"]}],
    "weather": {"mode": "auto"},
    "extra_unknown_key": 1,
}


def make():
    return B.build("Garden", "0.10.1", {"main_switch": "switch.start", "reverse": None}, VALVES, CONFIG)


class BackupTest(unittest.TestCase):
    def test_roundtrip(self):
        b = B.parse(json.dumps(make()))
        self.assertEqual(b["kind"], B.KIND)
        self.assertEqual(b["config"]["settings"], {"merge_mode": "shift"})
        self.assertNotIn("extra_unknown_key", b["config"])          # only known settings are exported
        self.assertEqual(b["controller"], {"main_switch": "switch.start"})
        self.assertNotIn("valve_switch", b["valves"][1])             # empty values are left out

    def test_parse_rejects(self):
        for text, why in (("not json", "JSON"), ("[]", "backup"), (json.dumps({"kind": "other"}), "backup"),
                          (json.dumps({"kind": B.KIND, "version": 99, "config": {}, "valves": []}), "newer"),
                          (json.dumps({"kind": B.KIND, "version": 1, "valves": []}), "settings"),
                          (json.dumps({"kind": B.KIND, "version": 1, "config": {}, "valves": [{"name": "x"}]}), "zones"),
                          ("x" * (B.MAX_BYTES + 1), "large")):
            with self.assertRaises(B.BackupError) as cm:
                B.parse(text)
            self.assertIn(why, str(cm.exception))

    def test_match_by_entity_even_when_renamed(self):
        v = B.match_valve({"name": "Totally new name", "duration": "number.c_duration"}, VALVES)
        self.assertEqual(v["id"], "zone_3")

    def test_match_by_name_when_entities_changed(self):
        v = B.match_valve({"name": " lawn west ", "duration": "number.zzz"}, VALVES)
        self.assertEqual(v["id"], "zone_3")

    def test_match_does_not_reuse_an_id(self):
        self.assertIsNone(B.match_valve({"name": "Lawn West"}, VALVES, used=["zone_3"]))

    def test_no_match(self):
        self.assertIsNone(B.match_valve({"name": "Garage", "duration": "number.new"}, VALVES))

    def test_next_free_id_skips_taken(self):
        self.assertEqual(B.next_free_id(["zone_1", "zone_3"]), "zone_2")
        self.assertEqual(B.next_free_id([]), "zone_1")

    def test_prepare_keeps_everything_when_all_zones_exist(self):
        cfg, notes = B.prepare(make(), ["zone_1", "zone_2", "zone_3"])
        self.assertEqual(notes, [])
        self.assertEqual(cfg["slots"][0]["zones"][1], {"zone": "zone_3", "minutes": 15})
        self.assertEqual(cfg["blockers"][0]["zones"], ["zone_3", "zone_1"])

    def test_prepare_drops_what_points_at_a_missing_zone(self):
        cfg, notes = B.prepare(make(), ["zone_1"])
        self.assertEqual(list(cfg["zones"]), ["zone_1"])
        self.assertEqual(cfg["slots"][0]["zones"], [{"zone": "zone_1", "minutes": 10}])
        self.assertEqual(cfg["blockers"][0]["zones"], ["zone_1"])
        self.assertEqual(len(notes), 1)
        self.assertIn("Lawn West", notes[0])
        self.assertEqual(cfg["settings"], {"merge_mode": "shift"})   # the rest stays

    def test_prepare_does_not_change_the_backup(self):
        b = make()
        B.prepare(b, [])
        self.assertIn("zone_3", b["config"]["zones"])


if __name__ == "__main__":
    unittest.main()


class EntryTest(unittest.TestCase):
    def test_entry_options_are_exported_when_numbers(self):
        b = B.build("G", "1", {}, VALVES, CONFIG, entry={"valve_overlap": 5, "watchdog_margin": None})
        self.assertEqual(b["entry"], {"valve_overlap": 5})
        self.assertEqual(B.build("G", "1", {}, VALVES, CONFIG)["entry"], {})
