"""
WeChat window monitor - monitor red packet popup via window class/name detection
Uses pywin32 to watch for WeChat red packet dialog windows.
"""
import sys
import threading
import time
from ..utils.logger import get_logger

logger = get_logger("monitor")

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import win32gui


class WeChatMonitor:
    MONITOR_INTERVAL_MS = 50

    def __init__(self, on_tail_detected=None, on_red_packet_found=None):
        self.on_tail = on_tail_detected
        self.on_redpacket = on_red_packet_found
        self._running = False
        self._thread = None
        self._watching = False

    def start_watching(self):
        if self._running:
            return
        if not IS_WIN:
            logger.warning("非Windows平台，窗口监控不可用")
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("WeChat monitor started")

    def stop_watching(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("WeChat monitor stopped")

    def _monitor_loop(self):
        while self._running:
            self._check_windows()
            time.sleep(self.MONITOR_INTERVAL_MS / 1000)

    def _check_windows(self):
        try:
            def enum_cb(hwnd, ctx):
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd)
                cls = win32gui.GetClassName(hwnd)
                if "红包" in title or "RedPacket" in cls or "hongbao" in title.lower():
                    ctx["found"].append((hwnd, title))
                elif "微信支付" in title or "WeChatPay" in cls:
                    ctx["pay"].append((hwnd, title))

            found = {"found": [], "pay": []}
            win32gui.EnumWindows(enum_cb, found)

            if found["found"]:
                if self.on_redpacket:
                    for hwnd, title in found["found"]:
                        logger.info(f"红包窗口检测到: {title} (hwnd={hwnd})")
                        self.on_redpacket(hwnd, title)

            if found["pay"]:
                for hwnd, title in found["pay"]:
                    logger.info(f"支付窗口: {title} (hwnd={hwnd})")

        except Exception as e:
            logger.error(f"Monitor error: {e}")
