"""牛牛玩法模式：元、角、分三位任意组合凑10的倍数，剩下两位相加取个位"""


def _sum_mod10(nums):
    s = sum(int(n) for n in nums)
    return s % 10


def calc_niuniu(amount: float):
    fen = round(amount * 100)
    s = str(fen).zfill(3)
    digits = [int(c) for c in s]
    hundreds, tens, ones = digits[0], digits[1], digits[2] if len(digits) == 3 else (digits[0], digits[1] if len(digits) > 1 else 0, 0)

    combos = [
        (hundreds, tens, ones),
    ]

    for a, b, c in combos:
        triplet_sum = a + b + c
        if triplet_sum % 10 == 0:
            rest_sum = sum(digits) - a - b - c
            return ("niu" + str(rest_sum % 10) if rest_sum % 10 != 0 else "niu"), rest_sum % 10

    all_sum = sum(digits)
    last_digit = all_sum % 10
    return "not_niu", last_digit
