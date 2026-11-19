"""颜色检测微信窗口内的红色"领取"按钮，不依赖 OCR"""
import numpy as np


def detect_red_blocks(arr, channel_order="rgb"):
    if arr is None or arr.size == 0:
        return []
    if arr.ndim == 3 and arr.shape[2] >= 3:
        a = arr.astype(np.int16)
        if a.shape[2] == 4:
            b, g, r = a[..., 0], a[..., 1], a[..., 3]
        elif channel_order == "bgr":
            b, g, r = a[..., 0], a[..., 1], a[..., 2]
        else:
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
    else:
        return []
    mask = (r > 150) & ((r - g) > 45) & ((r - b) > 45)
    if not mask.any():
        return []
    H, W = mask.shape
    row_thresh = max(25, int(W * 0.03))
    row_hits = mask.sum(axis=1) > row_thresh
    intervals = []
    start = None
    for i in range(H):
        if row_hits[i] and start is None:
            start = i
        elif not row_hits[i] and start is not None:
            intervals.append((start, i))
            start = None
    if start is not None:
        intervals.append((start, H))
    blocks = []
    for r0, r1 in intervals:
        h = r1 - r0
        if h < 12:
            continue
        sub = mask[r0:r1]
        col_hits = np.where(sub.sum(axis=0) > 0)[0]
        if col_hits.size == 0:
            continue
        c0, c1 = int(col_hits[0]), int(col_hits[-1])
        w = c1 - c0
        if w < 25:
            continue
        area = int(mask[r0:r1, c0:c1 + 1].sum())
        if area < 300:
            continue
        blocks.append({
            "cx": c0 + w // 2, "cy": r0 + h // 2,
            "x0": c0, "y0": r0, "w": w, "h": h, "area": area,
        })
    return blocks


def find_claim_buttons(blocks, img_w, img_h):
    out = []
    for bk in blocks:
        w, h = bk["w"], bk["h"]
        if h < 16 or h > 110:
            continue
        if w < 50:
            continue
        if w / h < 1.8:
            continue
        if w > img_w * 0.95:
            continue
        out.append(bk)
    return out
