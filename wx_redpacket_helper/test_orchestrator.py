"""编排器单元测试"""
import unittest
from .orchestrator import Orchestrator, Account


class TestOrchestrator(unittest.TestCase):

    def setUp(self):
        self.o = Orchestrator()
        self.o.cfg = {
            "mode": "standard",
            "rules": {
                "rule_one_enabled": True, "rule_one_threshold": 7,
                "rule_two_enabled": False,
                "rule_three_enabled": False, "rule_three_target_id": "", "rule_three_cmp": ">",
                "rule_four_all_pick": False, "rule_four_no_pick": False,
            },
        }
        from .orchestrator import Account
        main = Account(name="主号", is_main=True, handle=1001)
        subs = [Account(name="从1", handle=2001), Account(name="从2", handle=2002)]
        self.o.configure(main, subs, strategy="random")

    def test_tail_detection_triggers(self):
        self.o.state.update(total=3, claimed=1, total_amount=3.00, claimed_sum=1.50)
        self.assertIsNone(self.o.on_main_claimed(3, 1, 3.00, 1.50))
        self.o.state.update(total=3, claimed=2, total_amount=3.00, claimed_sum=2.00)
        res = self.o.on_main_claimed(3, 2, 3.00, 2.00)
        self.assertIsNotNone(res)
        tail, pts, reason = res
        self.assertAlmostEqual(tail, 1.00, places=2)
        self.assertEqual(pts, 1)  # 1+0+0=1
        self.assertIn("规则一", reason)

    def test_no_pick_when_below(self):
        self.o.state.update(total=2, claimed=1, total_amount=2.00, claimed_sum=1.00)
        res = self.o.on_main_claimed(2, 1, 2.00, 1.00)
        tail, pts, reason = res
        self.assertAlmostEqual(tail, 1.00, places=2)
        self.assertIn("规则一", reason)


if __name__ == "__main__":
    unittest.main()
