import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import notify_logic as N  # noqa: E402

RUN = {"start": "2026-11-16T05:00:00+01:00", "end": "2026-11-16T07:54:40+01:00", "day": "2026-11-16",
       "slots": ["morning"], "zones": [{"zone": "zone_5", "name": "Lawn West", "minutes": 15},
                                        {"zone": "zone_1", "name": "Drippers", "minutes": 60}]}


class Config(unittest.TestCase):
    def test_defaults(self):
        f = N.merged(None)
        self.assertEqual(set(f["events"]), set(N.EVENTS))
        self.assertTrue(f["events"]["started"]["enabled"])
        self.assertFalse(f["events"]["planned"]["enabled"])
        self.assertEqual(N.targets_for(f, "started"), [])      # no default targets -> nothing is sent

    def test_targets_global_and_per_event(self):
        f = N.merged({"targets": ["notify.mobile_app_a"],
                      "events": {"finished": {"targets": ["notify.mobile_app_b"]}, "skipped": {"enabled": False}}})
        self.assertEqual(N.targets_for(f, "started"), ["notify.mobile_app_a"])
        self.assertEqual(N.targets_for(f, "finished"), ["notify.mobile_app_b"])
        self.assertEqual(N.targets_for(f, "skipped"), [])

    def test_validation(self):
        bad = [({"targets": ["mobile_app_a"]}, "notify.*"),
               ({"events": {"exploded": {}}}, "unknown event"),
               ({"events": {"started": {"colour": "red"}}}, "unknown field"),
               ({"events": {"started": {"actions": ["selfdestruct"]}}}, "allowed stop"),
               ({"events": {"planned": {"lead": "soon"}}}, "lead")]
        for cfg, text in bad:
            with self.assertRaises(N.NotifyConfigError) as cm:
                N.merged(cfg)
            self.assertIn(text, str(cm.exception))


class Payloads(unittest.TestCase):
    def test_android_keeps_html_icon_and_three_actions(self):
        p = N.payload("android", "Started - <b>x1.5</b>", "a<br>b", ["pump_on", "stop", "skip", "stop"], "E1", tag="run")
        self.assertEqual(p["title"], "Started - <b>x1.5</b>")
        self.assertEqual(p["data"]["notification_icon"], "mdi:sprinkler")
        self.assertEqual(p["data"]["channel"], "Irrigation")
        self.assertEqual(len(p["data"]["actions"]), 3)
        self.assertEqual(p["data"]["actions"][0], {"action": "ESP_SPRINKLER_PUMP_ON_E1", "title": "Turn pump ON"})
        self.assertEqual(p["data"]["tag"], "run")

    def test_ios_plain_text_no_android_fields(self):
        p = N.payload("ios", "Started - <b>x1.5</b>", "a<br>b <i>c</i>", ["stop"], "E1")
        self.assertEqual(p["title"], "Started - x1.5")
        self.assertEqual(p["message"], "a\nb c")
        self.assertNotIn("notification_icon", p["data"])
        self.assertNotIn("channel", p["data"])
        self.assertEqual(p["data"]["actions"], [{"action": "ESP_SPRINKLER_STOP_E1", "title": "Stop"}])

    def test_other_targets_get_title_and_message_only(self):
        self.assertEqual(N.payload("other", "<b>T</b>", "m<br>n", ["stop"], "E1"), {"title": "T", "message": "m\nn"})

    def test_action_round_trip(self):
        for a in N.ACTIONS:
            self.assertEqual(N.parse_action(N.action_id("01ABC", a)), (a, "01ABC"))
        self.assertIsNone(N.parse_action("SOMETHING_ELSE"))


class Variables(unittest.TestCase):
    def test_started(self):
        v = N.variables("started", RUN, {"morning": "Morning"}, "Garden", {"source": "schedule"})
        self.assertEqual(v["zone_list"], "Lawn West, Drippers")
        self.assertEqual((v["start_time"], v["end_time"], v["duration_min"]), ("05:00", "07:54", 175))
        self.assertEqual(v["slots"], "Morning")
        self.assertNotIn("reason", v)

    def test_only_variables_of_the_event(self):
        v = N.variables("skipped", RUN, {}, "Garden", {"reason": "standby", "pump": "x"})
        self.assertEqual(v["reason"], "standby")
        self.assertNotIn("pump", v)


if __name__ == "__main__":
    unittest.main()
