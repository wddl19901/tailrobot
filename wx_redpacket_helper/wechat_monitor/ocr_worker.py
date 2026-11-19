"""高频 OCR 监控线程：截取主号红包详情页固定区域，识别 总金额/已领取数
依赖: mss + Pillow + 本地 OCR (PaddleOCR 或 pytesseract，任一可用即可)
"""
import re
import threading
import time

from ..utils.logger import get_logger

logger = get_logger("ocr_worker")

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _pick_ocr():
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)
        return ("paddle", ocr)
    except Exception:
        pass
    try:
        import pytesseract
        from PIL import Image
        return ("tesseract", pytesseract)
    except Exception:
        return (None, None)


class OcrWorker:
    """
    针对微信红包详情页固定区域做高频局部截图识别。
    region: (x, y, w, h) 屏幕坐标；None 时自动截主号窗口客户区。
    on_tail 回调: (total_count, claimed_count, total_amount, claimed_sum)
    """

    INTERVAL = 0.12

    def __init__(self, region=None, hwnd=0, on_tail=None, log_cb=None):
        self.region = region
        self.hwnd = hwnd
        self.on_tail = on_tail
        self.log_cb = log_cb or (lambda m: None)
        self._stop = threading.Event()
        self._thread = None
        self._engine = None
        self._ocr = None
        self._engine_ready = threading.Event()
        self._screenshotter = self._make_screenshot()

    def _init_engine(self):
        self._engine, self._ocr = _pick_ocr()
        if self._engine is None:
            logger.warning("未检测到 PaddleOCR 或 pytesseract，监控将降级为窗口检测")
        self._engine_ready.set()

    def _make_screenshot(self):
        try:
            import mss
            return mss.mss()
        except Exception:
            return None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"OCR worker started, engine will load in background, region={self.region}")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        self._init_engine()
        while not self._stop.is_set():
            try:
                if self._engine is None:
                    time.sleep(1.0)
                    continue
                self._tick()
            except Exception as e:
                logger.error(f"ocr tick error: {e}")
            time.sleep(self.INTERVAL)

    def _capture_region(self):
        if self._screenshotter is None:
            return None
        if self.region:
            x, y, w, h = self.region
            shot = self._screenshotter.grab({"left": x, "top": y, "width": w, "height": h})
        else:
            mon = self._screenshotter.monitors[0]
            shot = self._screenshotter.grab(mon)
        import numpy as np
        return np.asarray(shot)

    def _ocr_text(self, arr):
        if self._engine == "paddle":
            result = self._ocr.ocr(arr, cls=False)
            parts = []
            for page in result or []:
                for line in page or []:
                    parts.append(str(line[1]))
            return " ".join(parts)
        if self._engine == "tesseract":
            from PIL import Image
            img = Image.fromarray(arr)
            return self._ocr.image_to_string(img, lang="chi_sim") or ""
        return ""

    def _tick(self):
        arr = self._capture_region()
        if arr is None:
            return
        text = self._ocr_text(arr)
        if not text:
            return
        self._parse(text)

    def _parse(self, text: str):
        nums = _NUM_RE.findall(text)
        if not nums:
            return
        m = re.search(r"已领?取?\s*(\d+)\s*/\s*(\d+)", text)
        claimed = total = None
        if m:
            claimed, total = int(m.group(1)), int(m.group(2))
        amounts = [float(n) for n in nums]
        total_amount = max(amounts) if amounts else None
        claimed_sum = 0.0
        if total is not None and claimed is not None and claimed == total - 1:
            self.log_cb(f"锁定尾包: 已领取{claimed}/{total} 总额{total_amount}")
            if self.on_tail:
                self.on_tail(total, claimed, total_amount or 0.0, claimed_sum)
