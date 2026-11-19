import sys
import threading
import random
from collections import deque

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import win32gui


class PollingAllocator:
    """一拖N轮询分配器：支持随机和顺序两种策略"""

    def __init__(self, accounts, strategy="random"):
        self.accounts = accounts
        self.strategy = strategy
        self._index = 0
        self._lock = threading.Lock()

    def next_account(self):
        with self._lock:
            if not self.accounts:
                return None
            if self.strategy == "random":
                idx = random.randint(0, len(self.accounts) - 1)
            else:
                idx = self._index % len(self.accounts)
                self._index += 1
            return self.accounts[idx]

    def reset(self):
        with self._lock:
            self._index = 0

    @staticmethod
    def find_wechat_windows(title_keyword="微信"):
        handles = []
        if not IS_WIN:
            return handles
        def enum_cb(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title_keyword.lower() in title.lower():
                    results.append((hwnd, title))
        win32gui.EnumWindows(enum_cb, handles)
        return handles

    @staticmethod
    def get_active_window_handle():
        if not IS_WIN:
            return 0
        return win32gui.GetForegroundWindow()


class RedPacketState:
    """红包状态追踪"""

    def __init__(self):
        self.total_count = 0
        self.total_amount = 0.0
        self.claimed_count = 0
        self.claimed_sum = 0.0
        self.is_tail = False
        self.tail_candidate = None

    def update(self, total: int, claimed: int, total_amount: float, claimed_sum: float = 0.0):
        self.total_count = total
        self.total_amount = total_amount
        self.claimed_count = claimed
        self.claimed_sum = claimed_sum

    @property
    def remaining(self) -> int:
        return self.total_count - self.claimed_count

    def check_tail(self):
        self.is_tail = (self.remaining == 1)
        return self.is_tail

    def calc_tail_amount(self) -> float:
        tail = self.total_amount - self.claimed_sum
        return max(tail, 0.01)
