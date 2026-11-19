"""决策引擎单元测试"""
import unittest
from .decider import decide


class TestDecide(unittest.TestCase):

    def rules(self, **kw):
        base = {
            "rule_one_enabled": False, "rule_one_threshold": 7,
            "rule_two_enabled": False,
            "rule_three_enabled": False, "rule_three_cmp": ">",
            "rule_four_all_pick": False, "rule_four_no_pick": False,
        }
        base.update(kw)
        return base

    def test_all_pick(self):
        ok, _ = decide(self.rules(rule_four_all_pick=True), "standard", 0.01)
        self.assertTrue(ok)

    def test_no_pick(self):
        ok, _ = decide(self.rules(rule_four_no_pick=True, rule_four_all_pick=True), "standard", 9.99)
        self.assertFalse(ok)

    def test_rule_one(self):
        ok, _ = decide(self.rules(rule_one_enabled=True, rule_one_threshold=7), "standard", 9.99)
        self.assertTrue(ok)
        ok, _ = decide(self.rules(rule_one_enabled=True, rule_one_threshold=8), "standard", 9.99)
        self.assertFalse(ok)

    def test_rule_two_max(self):
        ok, _ = decide(self.rules(rule_two_enabled=True), "standard", 9.99)
        self.assertFalse(ok)
        ok, _ = decide(self.rules(rule_two_enabled=True), "standard", 6.94)
        self.assertTrue(ok)

    def test_rule_three(self):
        rules = self.rules(rule_three_enabled=True, rule_three_cmp=">")
        ok, _ = decide(rules, "standard", 9.99, target_player_points=3)
        self.assertTrue(ok)
        ok, _ = decide(rules, "standard", 9.99, target_player_points=7)
        self.assertFalse(ok)
        rules2 = self.rules(rule_three_enabled=True, rule_three_cmp=">=")
        ok, _ = decide(rules2, "standard", 9.99, target_player_points=7)
        self.assertTrue(ok)

    def test_rule_three_no_target(self):
        ok, _ = decide(self.rules(rule_three_enabled=True), "standard", 9.99)
        self.assertFalse(ok)

    def test_no_rule(self):
        ok, reason = decide(self.rules(), "standard", 9.99)
        self.assertFalse(ok)
        self.assertIn("未启用", reason)


if __name__ == "__main__":
    unittest.main()
