"""标准点数模式：百+十+个+角+分各位直接相加，取个位"""


def calc_standard(amount: float) -> int:
    fen = round(amount * 100)
    total = sum(int(d) for d in str(fen).zfill(3))
    return total % 10
