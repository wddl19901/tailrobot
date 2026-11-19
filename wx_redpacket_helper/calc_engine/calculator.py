from .standard import calc_standard
from .sg import calc_sg
from .niuniu import calc_niuniu

MODE_FUNCS = {
    "standard": calc_standard,
    "sg": calc_sg,
    "niuniu": calc_niuniu,
}


def get_points(mode: str, amount: float) -> int:
    fn = MODE_FUNCS.get(mode, calc_standard)
    res = fn(amount)
    if isinstance(res, tuple):
        res = res[1]
    return int(res)


def get_points_label(mode: str, amount: float):
    fn = MODE_FUNCS.get(mode, calc_standard)
    res = fn(amount)
    if isinstance(res, tuple):
        return res[0], int(res[1])
    return None, int(res)
