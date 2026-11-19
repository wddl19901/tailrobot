"""自动点击执行器：拟真防封点击（随机偏移 + 随机反应延迟）
Windows: win32api 物理鼠标事件；其他平台: pyautogui 兜底
"""
import random
import sys
import threading
import time

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import win32api
    import win32gui
else:
    win32api = None
    win32gui = None

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except Exception:
    pyautogui = None

from ..utils.logger import get_logger

logger = get_logger("clicker")

OFFSET_MIN, OFFSET_MAX = 3, 5
DELAY_MIN_MS, DELAY_MAX_MS = 30, 70


class AutoClicker:
    CANDIDATE_RATIOS = [
        (0.5, 0.62), (0.5, 0.55), (0.5, 0.68), (0.5, 0.5),
    ]

    def __init__(self, simulate_only=False):
        self.simulate_only = simulate_only
        self._lock = threading.Lock()

    def click_red_packet(self, hwnd: int, point_ratio: tuple = (0.5, 0.55)):
        with self._lock:
            if self.simulate_only:
                logger.info(f"[SIMULATE] 跳过实际点击 hwnd={hwnd}")
                return True
            delay_s = random.uniform(DELAY_MIN_MS, DELAY_MAX_MS) / 1000
            time.sleep(delay_s)
            x, y = self._resolve_point(hwnd, point_ratio)
            if x is None:
                return False
            x += random.randint(OFFSET_MIN, OFFSET_MAX) * random.choice((-1, 1))
            y += random.randint(OFFSET_MIN, OFFSET_MAX) * random.choice((-1, 1))
            self._raw_click(x, y)
            logger.info(f"拟真点击 ({x},{y}) 延迟{delay_s*1000:.0f}ms")
            return True

    def _resolve_point(self, hwnd: int, ratio: tuple):
        if win32gui and hwnd:
            try:
                win32gui.ShowWindow(hwnd, win32gui.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.03)
                left, top, right, bottom = win32gui.GetWindowRect(hwnd)
                w, h = right - left, bottom - top
                if w <= 0 or h <= 0:
                    return None, None
                return left + int(w * ratio[0]), top + int(h * ratio[1])
            except Exception as e:
                logger.error(f"取窗口坐标失败: {e}")
                return None, None
        if pyautogui:
            sw, sh = pyautogui.size()
            return int(sw * ratio[0]), int(sh * ratio[1])
        logger.warning("无可用点击后端 (win32gui/pyautogui)")
        return None, None

    def _raw_click(self, x: int, y: int):
        if win32api:
            win32api.SetCursorPos((x, y))
            win32api.mouse_event(0x0002, 0, 0, 0, 0)
            win32api.mouse_event(0x0004, 0, 0, 0, 0)
        elif pyautogui:
            pyautogui.click(x, y)
        else:
            logger.error("无点击后端")

    def click_point(self, x: int, y: int, delay_ms: float = 30.0):
        with self._lock:
            if self.simulate_only:
                logger.info(f"[SIMULATE] 跳过实际点击 ({x},{y})")
                return True
            delay_s = random.uniform(DELAY_MIN_MS, DELAY_MAX_MS) / 1000
            time.sleep(min(delay_s, delay_ms / 1000))
            x += random.randint(OFFSET_MIN, OFFSET_MAX) * random.choice((-1, 1))
            y += random.randint(OFFSET_MIN, OFFSET_MAX) * random.choice((-1, 1))
            self._raw_click(x, y)
            logger.info(f"屏幕点击 ({x},{y})")
            return True

    def pick_candidate(self, attempts=2):
        idx = 0
        while idx < attempts and idx < len(self.CANDIDATE_RATIOS):
            yield self.CANDIDATE_RATIOS[idx]
            idx += 1
