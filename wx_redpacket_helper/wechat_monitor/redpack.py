"""红包弹窗检测：全屏大红背景 + 金色"开"按钮，避免误检聊天记录中的橙色气泡"""
import numpy as np


def detect_redpack(arr):
    if arr is None or arr.size == 0:
        return None
    if arr.ndim != 3 or arr.shape[2] < 3:
        return None
    a = arr.astype(np.int16)
    if a.shape[2] == 4:
        b, g, r = a[..., 0], a[..., 1], a[..., 3]
    else:
        b, g, r = a[..., 0], a[..., 1], a[..., 2]
    red_mask = (r > 150) & ((r - g) > 40) & ((r - b) > 40)
    total = red_mask.size
    ratio = red_mask.sum() / total
    if ratio < 0.30:
        return None
    H, W = red_mask.shape
    row_hits = red_mask.sum(axis=1)
    intervals = []
    start = None
    for i in range(H):
        if row_hits[i] > W * 0.3 and start is None:
            start = i
        elif row_hits[i] <= W * 0.3 and start is not None:
            intervals.append((start, i))
            start = None
    if start is not None:
        intervals.append((start, H))
    if not intervals:
        return {"ratio": float(ratio), "red_cx": W // 2, "red_cy": H // 2,
                "gold_cx": None, "gold_cy": None, "W": W, "H": H}
    r0, r1 = max(intervals, key=lambda x: x[1] - x[0])
    sub = red_mask[r0:r1]
    cols = np.where(sub.sum(axis=0) > 0)[0]
    c0, c1 = int(cols[0]), int(cols[-1])
    result = {
        "ratio": float(ratio),
        "red_cx": (c0 + c1) // 2,
        "red_cy": (r0 + r1) // 2,
        "gold_cx": None,
        "gold_cy": None,
        "W": W,
        "H": H,
    }
    gold_mask = (r > 190) & (g >= 150) & (g < 225) & (b < 165)
    if gold_mask[r0:r1, c0:c1 + 1].any():
        ys, xs = np.where(gold_mask[r0:r1, c0:c1 + 1])
        if xs.size > 80:
            result["gold_cx"] = int(xs.mean()) + c0
            result["gold_cy"] = int(ys.mean()) + r0
    return result
