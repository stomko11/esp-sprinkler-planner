import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "esp_sprinkler_planner"))

import discovery as D  # noqa: E402

DEV = "Garden8"


def E(eid, name, mx=None, order=0):
    return D.Entity(eid, f"{DEV} {name}", max=mx, order=order)


# entity names in the shape ESPHome's sprinkler component produces (YAML order)
NAMED = [
    E("switch.g_cycle_start", "Irrigation Cycle Start", order=1),
    E("switch.g_auto_advance", "Irrigation Auto Advance", order=2),
    E("switch.g_reverse", "Irrigation Reverse Order", order=3),
    E("switch.g_standby", "Irrigation Standby Switch", order=4),
    E("number.g_multiplier", "Irrigation Multiplier", 10, order=5),
    E("number.g_repeat", "Irrigation Sprinkler Repeat", 10, order=6),
    E("switch.g_house", "Irrigation Drippers House", order=10),
    E("switch.g_en_house", "Enable Irrigation Drippers House", order=11),
    E("number.g_house_dur", "Irrigation Drippers House Duration", 90, order=12),
    E("switch.g_field", "Irrigation Field", order=13),
    E("switch.g_en_field", "Enable Irrigation Field", order=14),
    E("number.g_field_dur", "Irrigation Field Duration", 45, order=15),
    E("switch.g_west", "Irrigation Lawn West", order=16),
    E("switch.g_en_west", "Enable Irrigation Lawn West", order=17),
    E("number.g_west_dur", "Irrigation Lawn West Duration", 60, order=18),
    E("sensor.g_remaining", "Irrigation Zone Remaining Time", order=19),
    E("button.g_next", "Next Valve", order=20),
]


class Named(unittest.TestCase):
    def test_valves_paired_in_esp_order(self):
        p = D.propose(NAMED, DEV)
        self.assertEqual([(v.name, v.valve_switch, v.enable_switch, v.duration, v.max_minutes, v.order) for v in p.valves], [
            ("Drippers House", "switch.g_house", "switch.g_en_house", "number.g_house_dur", 90, 0),
            ("Field", "switch.g_field", "switch.g_en_field", "number.g_field_dur", 45, 1),
            ("Lawn West", "switch.g_west", "switch.g_en_west", "number.g_west_dur", 60, 2),
        ])

    def test_controller_roles(self):
        c = D.propose(NAMED, DEV).controller
        self.assertEqual(c["main_switch"], "switch.g_cycle_start")
        self.assertEqual(c["auto_advance"], "switch.g_auto_advance")
        self.assertEqual(c["reverse"], "switch.g_reverse")
        self.assertEqual(c["standby"], "switch.g_standby")
        self.assertEqual(c["multiplier"], "number.g_multiplier")
        self.assertEqual(c["repeat"], "number.g_repeat")
        self.assertIsNone(c["queue_enable"])

    def test_nothing_left_over(self):
        self.assertEqual(D.propose(NAMED, DEV).unassigned, [])


class ShortNames(unittest.TestCase):
    def test_r1_r2_style(self):
        ents = [
            E("switch.m", "Sprinklers", order=1),
            E("switch.r1", "R1", order=2), E("switch.r1_en", "R1 Enable", order=3), E("number.r1_d", "R1 Duration", 30, order=4),
            E("switch.r2", "R2", order=5), E("switch.r2_en", "R2 Enable", order=6), E("number.r2_d", "R2 Duration", 30, order=7),
        ]
        p = D.propose(ents, DEV)
        self.assertEqual([(v.name, v.valve_switch, v.enable_switch, v.duration) for v in p.valves],
                         [("R1", "switch.r1", "switch.r1_en", "number.r1_d"), ("R2", "switch.r2", "switch.r2_en", "number.r2_d")])
        # a main switch named only "Sprinklers" cannot be recognised -> left for the user
        self.assertIsNone(p.controller["main_switch"])
        self.assertIn("switch.m", p.unassigned)

    def test_names_that_do_not_pair_are_left_for_manual_mapping(self):
        ents = [E("number.a_d", "Valve A Duration", order=1), E("switch.x", "Front lawn", order=2)]
        p = D.propose(ents, DEV)
        self.assertEqual(len(p.valves), 1)
        self.assertIsNone(p.valves[0].valve_switch)
        self.assertIsNone(p.valves[0].enable_switch)
        self.assertEqual(p.unassigned, ["switch.x"])


if __name__ == "__main__":
    unittest.main()


class MoreLanguagesTest(unittest.TestCase):
    def run_names(self, rows, device=""):
        ents = [D.Entity(eid, name, order=i) for i, (eid, name) in enumerate(rows)]
        return D.propose(ents, device)

    def test_slovak_with_accents(self):
        p = self.run_names([
            ("switch.k_zahony", "Záhony"), ("switch.k_povolit_zahony", "Povoliť Záhony"), ("number.k_zahony_trvanie", "Záhony Trvanie"),
            ("switch.k_tuje", "Tuje"), ("switch.k_povolit_tuje", "Povoliť Tuje"), ("number.k_tuje_trvanie", "Tuje Trvanie"),
            ("switch.k_spustit", "Spustiť cyklus"), ("switch.k_opacne", "Opačné poradie"), ("number.k_nasobic", "Násobič"),
        ])
        self.assertEqual([(v.name, bool(v.valve_switch), bool(v.enable_switch)) for v in p.valves],
                         [("Zahony", True, True), ("Tuje", True, True)])
        self.assertEqual(p.controller["main_switch"], "switch.k_spustit")
        self.assertEqual(p.controller["reverse"], "switch.k_opacne")
        self.assertEqual(p.controller["multiplier"], "number.k_nasobic")

    def test_no_known_words_pairs_by_name(self):
        p = self.run_names([
            ("switch.z1", "Vlavo"), ("switch.z1e", "Vlavo Zap"), ("number.z1d", "Vlavo Cislo"),
            ("switch.z2", "Vpravo"), ("switch.z2e", "Vpravo Zap"), ("number.z2d", "Vpravo Cislo"),
        ])
        self.assertEqual([(v.name, v.valve_switch, v.enable_switch, v.duration) for v in p.valves],
                         [("Vlavo", "switch.z1", "switch.z1e", "number.z1d"), ("Vpravo", "switch.z2", "switch.z2e", "number.z2d")])

    def test_english_unchanged(self):
        p = self.run_names([("switch.a", "Irrigation Lawn"), ("switch.b", "Enable Irrigation Lawn"), ("number.c", "Irrigation Lawn Duration"),
                            ("number.m", "Irrigation Multiplier")])
        self.assertEqual(len(p.valves), 1)
        self.assertEqual(p.controller["multiplier"], "number.m")


class NewValvesTest(unittest.TestCase):
    def V(self, n, order):
        return D.ValveProposal(n, f"switch.{n}", f"switch.en_{n}", f"number.{n}_duration", 60, order)

    def test_only_valves_not_in_the_saved_mapping_are_new(self):
        saved = [self.V("a", 0), self.V("b", 1), self.V("west", 4)]
        found = [self.V("a", 0), self.V("b", 1), self.V("south2", 4), self.V("west", 5)]
        self.assertEqual([v.name for v in D.new_valves(saved, found)], ["south2"])

    def test_nothing_new(self):
        saved = [self.V("a", 0)]
        self.assertEqual(D.new_valves(saved, [self.V("a", 0)]), [])

    def test_incomplete_valve_is_not_offered(self):
        half = D.ValveProposal("x", "switch.x", None, None, None, 2)
        self.assertEqual(D.new_valves([self.V("a", 0)], [half]), [])

    def test_matched_by_any_entity(self):
        saved = [D.ValveProposal("a", "switch.a", "switch.en_a", "number.a_duration", 60, 0)]
        renamed = D.ValveProposal("A renamed", "switch.a", "switch.en_a2", "number.a2_duration", 60, 0)
        self.assertEqual(D.new_valves(saved, [renamed]), [])
