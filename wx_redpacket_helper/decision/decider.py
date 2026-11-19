"""决策引擎：将计算出的尾包点数与规则比对，返回是否触发抢包"""

from ..calc_engine.calculator import get_points

MAX_POINTS = 9


def decide(rules: dict, mode: str, tail_amount: float, target_player_points=None):
    if rules.get("rule_four_no_pick"):
        return False, "全不抢模式"
    if rules.get("rule_four_all_pick"):
        return True, "全选模式"

    points = get_points(mode, tail_amount)

    if rules.get("rule_three_enabled"):
        if target_player_points is None:
            return False, "规则三: 未获取到目标玩家点数"
        cmp = rules.get("rule_three_cmp", ">")
        if cmp == ">=":
            hit = points >= target_player_points
        else:
            hit = points > target_player_points
        if hit:
            return True, f"规则三: 尾包{points}点 超过目标{target_player_points}点"
        return False, f"规则三: 尾包{points}点 未超过目标{target_player_points}点"

    if rules.get("rule_two_enabled"):
        if points == MAX_POINTS:
            return True, f"规则二: 尾包{points}点为绝对最大值"
        return False, f"规则二: 尾包{points}点非最大值{MAX_POINTS}"

    if rules.get("rule_one_enabled"):
        th = rules.get("rule_one_threshold", 7)
        if points >= th:
            return True, f"规则一: 尾包{points}点 >= {th}点"
        return False, f"规则一: 尾包{points}点 < {th}点"

    return False, "未启用任何规则"
