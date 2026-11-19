"""红包检测：实测颜色参数
卡片金橙 RGB(250,157,59) / 红信封 RGB(225,73,73)
弹窗红 RGB(231,81,64) / 金色"开"按钮 RGB(220-250, 180-220, 130-175)
输入 arr 支持 mss BGRA 4通道或 RGB 3通道
"""
import numpy as np


def _channels(arr):
    a = np.ascontiguousarray(arr).astype(np.int16)
    if a.shape[2] == 4:
        return a[..., 2], a[..., 1], a[..., 0]
    return a[..., 0], a[..., 1], a[..., 2]


def _regions(mask, min_h, min_w):
    H, W = mask.shape
    row_hits = mask.sum(axis=1)
    out = []
    start = None
    for i in range(H):
        if row_hits[i] > 15 and start is None:
            start = i
        elif row_hits[i] <= 15 and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, H))
    res = []
    for r0, r1 in out:
        rh = r1 - r0
        if rh < min_h:
            continue
        cols = np.where(mask[r0:r1].sum(axis=0) > 2)[0]
        if cols.size == 0:
            continue
        c0, c1 = int(cols[0]), int(cols[-1])
        rw = c1 - c0
        if rw < min_w:
            continue
        res.append({"cx": c0 + rw // 2, "cy": r0 + rh // 2,
                    "x": c0, "y": r0, "w": rw, "h": rh})
    return res


def detect_red_packet_cards(arr):
    """聊天区里的红包卡片(金橙+红信封)，返回所有卡片，越靠下越新"""
    if arr is None or arr.size == 0 or arr.ndim != 3 or arr.shape[2] < 3:
        return []
    r, g, b = _channels(arr)
    card = (r >= 240) & (r <= 255) & (g >= 140) & (g <= 175) & (b >= 40) & (b <= 80)
    icon = (r >= 200) & (r <= 255) & (g >= 55) & (g <= 120) & (b >= 30) & (b <= 95)
    combined = card | icon
    H, W = combined.shape
    start_x = int(W * 0.28)
    combined[:, :start_x] = False
    regions = _regions(combined, min_h=20, min_w=40)
    out = []
    for pkt in regions:
        sub = combined[pkt["y"]:pkt["y"] + pkt["h"], pkt["x"]:pkt["x"] + pkt["w"]]
        px = int(sub.sum())
        if px < 2000:
            continue
        if px / max(pkt["w"] * pkt["h"], 1) < 0.5:
            continue
        if int(icon[pkt["y"]:pkt["y"] + pkt["h"], pkt["x"]:pkt["x"] + pkt["w"]].sum()) < 200:
            continue
        out.append(pkt)
    out.sort(key=lambda p: p["cy"])
    return out


def detect_open_button(arr):
    """全屏/窗口截图中的红包弹窗 + 金色'开'按钮，返回点击坐标(截图内)"""
    if arr is None or arr.size == 0 or arr.ndim != 3 or arr.shape[2] < 3:
        return None
    r, g, b = _channels(arr)
    red_mask = (r >= 215) & (r <= 250) & (g >= 65) & (g <= 100) & (b >= 50) & (b <= 85)
    if int(red_mask.sum()) < 5000:
        return None
    H, W = red_mask.shape
    col_counts = red_mask.sum(axis=0)
    dense = np.where(col_counts > H * 0.3)[0]
    if dense.size == 0:
        dense = np.where(col_counts > H * 0.15)[0]
    if dense.size == 0:
        return None
    gaps = np.where(np.diff(dense) > 5)[0]
    segments = np.split(dense, gaps + 1)
    seg = max(segments, key=lambda s: len(s))
    x_min, x_max = int(seg[0]), int(seg[-1])
    panel = red_mask[:, x_min:x_max + 1]
    rows = np.where(panel.any(axis=1))[0]
    if rows.size == 0:
        return None
    y_min, y_max = int(rows[0]), int(rows[-1])
    gold = (r >= 220) & (r <= 250) & (g >= 180) & (g <= 220) & (b >= 130) & (b <= 175) & (~red_mask)
    zone = np.zeros_like(gold)
    zone[y_min:y_max + 1, x_min:x_max + 1] = True
    gold_zone = gold & zone
    if int(gold_zone.sum()) > 50:
        ys, xs = np.where(gold_zone)
        idx = np.argsort(ys)
        ys, xs = ys[idx], xs[idx]
        clusters = []
        cs = 0
        for i in range(1, len(ys)):
            if ys[i] - ys[i - 1] > 20:
                clusters.append((ys[cs:i], xs[cs:i]))
                cs = i
        clusters.append((ys[cs:], xs[cs:]))
        by, bx = max(clusters, key=lambda c: len(c[0]))
        if len(by) > 30:
            return {"cx": int(bx.mean()), "cy": int(by.mean()),
                    "panel": (x_min, y_min, x_max, y_max)}
    pw = x_max - x_min
    ph = y_max - y_min
    return {"cx": x_min + pw // 2, "cy": y_min + int(ph * 0.75),
            "panel": (x_min, y_min, x_max, y_max), "estimated": True}
