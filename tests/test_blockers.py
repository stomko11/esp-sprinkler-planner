import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))
import blockers as BL  # noqa: E402


def mk(**k):
    return BL.from_list([{"entity": "lawn_mower.robot", **k}])


class BlockerTest(unittest.TestCase):
    def test_conditions(self):
        self.assertTrue(BL.active(mk(op="is", value="mowing")[0], "mowing"))
        self.assertFalse(BL.active(mk(op="is", value="mowing")[0], "docked"))
        self.assertTrue(BL.active(mk(op="on")[0], "on"))
        self.assertTrue(BL.active(mk(op="off")[0], "off"))
        self.assertTrue(BL.active(mk(op="above", value=5)[0], "7.2"))
        self.assertFalse(BL.active(mk(op="below", value=5)[0], "7.2"))
        self.assertFalse(BL.active(mk(op="on")[0], "unavailable"))       # unknown never blocks

    def test_scope_and_precedence(self):
        bl = BL.from_list([
            {"id": "a", "entity": "switch.party", "op": "on", "action": "wait"},
            {"id": "b", "entity": "lawn_mower.robot", "op": "is", "value": "mowing", "scope": "slots", "slots": ["evening"], "action": "ask"},
        ])
        st = {"switch.party": "on", "lawn_mower.robot": "mowing"}
        self.assertEqual(BL.check(bl, st, ["morning"], ["z1"]).action, "wait")
        self.assertEqual(BL.check(bl, st, ["evening"], ["z1"]).action, "ask")
        self.assertEqual(BL.check(bl, {"switch.party": "off"}, ["evening"], ["z1"]).action, "run")
        bl.append(BL.from_list([{"id": "c", "entity": "binary_sensor.pool", "op": "on", "action": "skip"}])[0])
        self.assertEqual(BL.check(bl, {**st, "binary_sensor.pool": "on"}, ["evening"], ["z1"]).action, "skip")

    def test_zone_scope_drops_zones(self):
        bl = BL.from_list([{"entity": "lawn_mower.robot", "op": "is", "value": "mowing", "scope": "zones",
                            "zones": ["lawn"], "action": "wait"}])
        self.assertEqual(bl[0]["action"], "skip")                       # zone blockers only drop zones
        v = BL.check(bl, {"lawn_mower.robot": "mowing"}, ["m"], ["drip", "lawn"], {"lawn": "Lawn"})
        self.assertEqual((v.action, v.drop_zones), ("run", ["lawn"]))
        self.assertEqual(BL.check(bl, {"lawn_mower.robot": "mowing"}, ["m"], ["lawn"]).action, "skip")

    def test_disabled_and_validation(self):
        self.assertEqual(BL.check(mk(op="on", enabled=False), {"lawn_mower.robot": "on"}, ["m"], ["z"]).action, "run")
        for bad in ([{"entity": "x"}], [{"entity": "a.b", "op": "nope"}], [{"entity": "a.b", "op": "above", "value": "x"}],
                    [{"entity": "a.b", "op": "is"}], [{"id": "a", "entity": "a.b"}, {"id": "a", "entity": "a.c"}]):
            with self.assertRaises(BL.BlockerConfigError):
                BL.from_list(bad)
