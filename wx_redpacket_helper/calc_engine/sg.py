"""三公玩法模式：金额各位数字相加，10点=0点，最高9点"""


def calc_sg(amount: float) -> int:
    fen = round(amount * 100)
    digits = [int(d) for d in str(fen).zfill(3)]
    total = sum(digits)
    return total % 10
