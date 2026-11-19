"""计算引擎单元测试"""
import unittest
from .calculator import get_points, get_points_label


class TestCalcEngine(unittest.TestCase):

    def test_standard(self):
        self.assertEqual(get_points("standard", 6.52), 3)   # 6+5+2=13->3
        self.assertEqual(get_points("standard", 8.88), 4)   # 8+8+8=24->4
        self.assertEqual(get_points("standard", 1.00), 1)
        self.assertEqual(get_points("standard", 0.01), 1)
        self.assertEqual(get_points("standard", 10.00), 1)  # 1+0+0=1
        self.assertEqual(get_points("standard", 9.99), 7)   # 9+9+9=27->7

    def test_standard_999(self):
        val = get_points("standard", 9.99)
        self.assertEqual(val, 7)  # 9+9+9=27 -> 7

    def test_standard_various(self):
        cases = [
            (6.52, 3),
            (1.00, 1),
            (0.01, 1),
            (10.00, 1),
            (5.00, 5),
            (0.50, 5),
            (99.99, 6),  # fen=9999 -> 9+9+9+9=36->6
            (8.88, 4),   # 8+8+8=24->4
        ]
        for amt, expected in cases:
            with self.subTest(amt=amt):
                self.assertEqual(get_points("standard", amt), expected)

    def test_sg(self):
        self.assertEqual(get_points("sg", 6.52), 3)   # 6+5+2=13 -> 3
        self.assertEqual(get_points("sg", 9.99), 7)   # 9+9+9=27 -> 7
        self.assertEqual(get_points("sg", 5.50), 0)   # 5+5+0=10 -> 0
        self.assertEqual(get_points("sg", 1.00), 1)

    def test_niuniu_not_niu(self):
        self.assertEqual(get_points("niuniu", 1.23), 6)
        label, pts = get_points_label("niuniu", 1.23)
        self.assertEqual(label, "not_niu")
        self.assertEqual(pts, 6)

    def test_niuniu_with_combo(self):
        self.assertEqual(get_points("niuniu", 2.80), 0)
        label, pts = get_points_label("niuniu", 2.80)
        self.assertEqual(label, "niu")
        self.assertEqual(pts, 0)

    def test_edge_zero(self):
        self.assertEqual(get_points("standard", 0.00), 0)
        self.assertEqual(get_points("sg", 0.00), 0)


if __name__ == "__main__":
    unittest.main()
