"""机器人工作线程：主号秒抢 + 从号尾包点数决策 + 备注人锁定"""
import re
import random
import threading
import time

import numpy as np

from ..utils.logger import get_logger
from ..calc_engine.calculator import get_points
from .ocr_worker import OcrWorker
from .redpack import detect_red_packet_cards, detect_open_button, detect_sidebar_redpack
from ..executor.auto_clicker import AutoClicker
from .account_manager import PollingAllocator, RedPacketState
from ..orchestrator import Account

logger = get_logger("robot")

try:
    import mss
except Exception:
    mss = None


def find_wechat_hwnd():
    try:
        import ctypes
        user32 = ctypes.windll.user32
    except Exception:
        return None
    for cls, title in (("Qt51514QWindowIcon", "微信"),
                       ("Qt6514QWindowIcon", "微信"),
                       ("WeChatMainWndForPC", "微信")):
        try:
            h = user32.FindWindowW(cls, title)
            if h:
                return h
        except Exception:
            pass
    try:
        return user32.FindWindowW(None, "微信") or None
    except Exception:
        return None


def get_window_rect(hwnd, user32):
    import ctypes
    from ctypes import wintypes
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def ensure_window_foreground(hwnd, user32):
    """恢复最小化 + 切到前台，返回是否发生最小化恢复"""
    if not hwnd:
        return False
    import ctypes
    SW_SHOWNORMAL = 1
    SW_RESTORE = 9
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_SHOWWINDOW = 0x0040
    was_min = False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.06)
        was_min = True
    else:
        user32.ShowWindow(hwnd, SW_SHOWNORMAL)
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
    time.sleep(0.02)
    return was_min


class RemarkTracker:
    """跟踪指定备注人的领取金额，用于尾包比较"""

    def __init__(self, name: str):
        self.name = name
        self.last_amount: float | None = None
        self.last_seen: float = 0.0

    def on_text(self, text: str):
        if not text or not self.name:
            return
        pats = [
            re.escape(self.name) + r"[^\d]{0,12}(\d+(?:\.\d+)?)\s*元?",
            r"(?:领取|抢到|领到)[^\d]{0,10}" + re.escape(self.name) + r"[^\d]{0,12}(\d+(?:\.\d+)?)",
            re.escape(self.name) + r"[^\d]{0,20}(\d+(?:\.\d+)?)\s*元",
        ]
        for p in pats:
            m = re.search(p, text)
            if m:
                amt = float(m.group(1))
                if 0.01 <= amt <= 10000:
                    if self.last_amount is None or abs(amt - self.last_amount) > 0.001:
                        self.last_seen = time.time()
                        self.last_amount = amt
                    return

    def active(self, within_s: float = 30.0) -> bool:
        return self.last_amount is not None and (time.time() - self.last_seen) <= within_s


class RobotWorker:
    def __init__(self, accounts: list[Account], strategy: str, mode: str,
                 threshold: int, log_cb=None, ocr_region=None,
                 simulate_click=True, remark_name: str = ""):
        self.accounts = accounts
        self.mode = mode
        self.threshold = threshold
        self.log_cb = log_cb or (lambda m, p=False: None)
        self.state = RedPacketState()
        self.allocation = PollingAllocator(accounts[1:] or accounts, strategy)
        self.clicker = AutoClicker(simulate_only=simulate_click)
        self.remark = RemarkTracker(remark_name)
        self.ocr = OcrWorker(region=ocr_region, on_tail=self._on_tail,
                             log_cb=lambda m: self.log_cb(m),
                             on_text=self._on_ocr_text)
        self._stop = threading.Event()
        self._thread = None
        self._hwnd = None
        self._rect = None
        self._picks = 0
        self._last_click_ts = 0.0
        self._last_card_click_ts = 0.0
        self._last_side_ts = 0.0
        self._last_side_click_ts = 0.0
        self._last_scroll_ts = 0.0
        self._last_heartbeat_ts = 0.0
        self._round_active = False
        self._last_signal_ts = 0.0
        self._clicked = []
        self._cur_panel = None
        self._last_fg_ts = 0.0
        self._last_fg_was_min = False
        self._last_side_pos = None
        self._side_streak = 0

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.ocr.start()
        extra = f"，备注锁定: {self.remark.name}" if self.remark.name else ""
        logger.info(f"Robot worker started threshold={self.threshold} mode={self.mode}{extra}")
        self.log_cb(f"机器人已启动: 玩法={self.mode} 触发点数>={self.threshold}{extra}")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.ocr.stop()
        logger.info("Robot worker stopped")

    def _run(self):
        if mss is None:
            self.log_cb("未检测到 mss 截图库，无法监控红包")
            return
        sct = mss.mss()
        while not self._stop.is_set():
            try:
                self._tick(sct)
            except Exception as e:
                logger.error(f"watchdog tick error: {e}")
            time.sleep(0.1 + random.uniform(0, 0.05))

    def _wechat_mon(self, sct):
        h = find_wechat_hwnd()
        if not h:
            return None
        try:
            import ctypes
            user32 = ctypes.windll.user32
            rect = get_window_rect(h, user32)
        except Exception:
            return None
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        m = {"left": rect[0], "top": rect[1],
             "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
        if m["left"] < 0:
            m["left"] = 0
        return m

    def _is_clicked(self, sx, sy, threshold=30):
        for cx, cy in self._clicked:
            if abs(sx - cx) < threshold and abs(sy - cy) < threshold:
                return True
        return False

    def _record_click(self, sx, sy):
        self._clicked.append((sx, sy))
        if len(self._clicked) > 200:
            self._clicked = self._clicked[-100:]

    def _tick(self, sct):
        now = time.time()
        h = find_wechat_hwnd()
        if h:
            import ctypes
            user32 = ctypes.windll.user32
            if now - self._last_fg_ts > 0.5:
                was_min = ensure_window_foreground(h, user32)
                if was_min:
                    self.log_cb("检测到微信窗口被最小化，已自动恢复并置前", False)
                self._last_fg_ts = now
            m = self._wechat_mon(sct)
            if m:
                self._rect = (m["left"], m["top"])
                arr = np.asarray(sct.grab(m))
                self._process(arr, now)
                return
        if now - self._last_heartbeat_ts > 5:
            self._last_heartbeat_ts = now
            self.log_cb("监控中: 未找到微信窗口(请确认微信已登录且窗口未最小化)", False)

    def _process(self, arr, now):
        ob = detect_open_button(arr)
        if ob:
            self._last_signal_ts = now
            panel = ob["panel"]
            if self._cur_panel is None:
                self._cur_panel = panel
                self._picks = 0
                self._clicked = []
            elif panel != self._cur_panel:
                self._cur_panel = panel
                self._picks = 0
                self._clicked = []
                self._last_click_ts = 0.0
            sx, sy = self._rect[0] + ob["cx"], self._rect[1] + ob["cy"]
            if not self._round_active:
                self._round_active = True
                self.log_cb(f"红包弹窗已打开(面板{panel}) 开钮@{sx},{sy}", False)
                self._dump_debug(arr, "popup")
            if not self._is_clicked(sx, sy) and now - self._last_click_ts >= 0.6:
                delay = random.uniform(0.05, 0.15)
                time.sleep(delay)
                self._last_click_ts = time.time()
                self._picks += 1
                self._record_click(sx, sy)
                self.clicker.click_point(sx, sy)
                who = self.accounts[0].name if self.accounts else "主号"
                self.state.claimed_count += 1
                self.log_cb(f"{who} 点开抢包执行 @({sx},{sy}) (共抢{self._picks}次)", True)
                time.sleep(random.uniform(0.4, 0.6))
                self._close_popup()
            return
        cards = detect_red_packet_cards(arr)
        if cards:
            self._last_signal_ts = now
            newest = cards[-1]
            sx, sy = self._rect[0] + newest["cx"], self._rect[1] + newest["cy"]
            if now - self._last_card_click_ts >= 0.8:
                self._last_card_click_ts = now
                self.log_cb(f"检测到红包卡片{len(cards)}个，点击最新@{sx},{sy} (尺寸{newest['w']}x{newest['h']})")
                self._dump_debug(arr, "cards")
                delay = random.uniform(0.05, 0.15)
                time.sleep(delay)
                self._record_click(sx, sy)
                self.clicker.click_point(sx, sy)
            return
        side = detect_sidebar_redpack(arr)
        if side:
            self._last_side_ts = now
            key = (side["cx"] // 16, side["cy"] // 16)
            if key == self._last_side_pos:
                self._side_streak += 1
            else:
                self._last_side_pos = key
                self._side_streak = 0
            if self._side_streak < 8 and now - self._last_side_click_ts >= 2.0:
                self._last_side_click_ts = now
                sx = self._rect[0] + min(side["cx"] + 30, int(arr.shape[1] * 0.30))
                sy = self._rect[1] + side["cy"]
                self.log_cb(f"会话列表发现红包预览@(窗口坐标 {side['cx']},{side['cy']})，自动打开该群")
                self.clicker.click_point(sx, sy)
            return
        if now - self._last_scroll_ts > 12:
            self._last_scroll_ts = now
            self._scroll_sidebar(arr)
        if self._round_active and now - self._last_signal_ts > 4:
            self._round_active = False
            self.log_cb(f"红包轮次结束，本轮共抢{self._picks}次", self._picks > 0)
            self._clicked = []
            self._cur_panel = None
            self._picks = 0
        elif now - self._last_heartbeat_ts > 5:
            self._last_heartbeat_ts = now
            self.log_cb("监控中: 等待红包(卡片->弹窗->开钮 全自动)", False)

    def _scroll_sidebar(self, arr):
        try:
            import ctypes
            user32 = ctypes.windll.user32
            W, H = arr.shape[1], arr.shape[0]
            strip = arr[60:130, :int(W * 0.30)]
            key = strip[::4, ::4].tobytes()
            if key == getattr(self, "_top_strip_key", None):
                self._top_streak = getattr(self, "_top_streak", 0) + 1
            else:
                self._top_streak = 0
                self._top_strip_key = key
            if self._top_streak >= 2:
                return
            x, y = self._rect[0] + int(W * 0.15), self._rect[1] + int(H * 0.5)
            user32.SetCursorPos(x, y)
            time.sleep(0.03)
            user32.mouse_event(0x0800, 0, -120, 0)
            self.log_cb("已滚动会话列表(检查其他群红包)", False)
        except Exception as e:
            logger.debug(f"scroll sidebar: {e}")

    def _close_popup(self):
        try:
            time.sleep(random.uniform(0.10, 0.20))
            self.clicker.press_escape()
            time.sleep(random.uniform(0.08, 0.18))
            self.clicker.press_escape()
            time.sleep(random.uniform(0.08, 0.15))
            self.log_cb("红包结果页已关闭(ESC)，继续监控下一个红包", False)
        except Exception as e:
            logger.debug(f"close popup: {e}")

    def _dump_debug(self, arr, tag):
        try:
            from PIL import Image, ImageDraw
            from ..utils.paths import app_dir
            ddir = app_dir() / "logs" / "debug"
            ddir.mkdir(parents=True, exist_ok=True)
            a = arr.copy()
            if a.shape[2] == 4:
                a = a[:, :, [2, 1, 0]]
            img = Image.fromarray(a.astype("uint8"))
            dr = ImageDraw.Draw(img)
            for cx, cy in self._clicked[-20:]:
                try:
                    lx, ly = cx - self._rect[0], cy - self._rect[1]
                    dr.ellipse([lx - 20, ly - 20, lx + 20, ly + 20], outline="cyan", width=3)
                except Exception:
                    pass
            img.save(ddir / f"debug_{tag}_{time.strftime('%H%M%S')}.png")
        except Exception as e:
            logger.debug(f"debug dump failed: {e}")

    def _on_ocr_text(self, text: str):
        self.remark.on_text(text)
        if "存入零钱" in text or "已存入" in text:
            dec = [float(n) for n in re.findall(r"\d+\.\d+", text) if 0.005 <= float(n) <= 100000]
            amt = max(dec) if dec else 0.0
            if amt and amt != getattr(self, "_last_grab_amt", None):
                self._last_grab_amt = amt
                who = self.accounts[0].name if self.accounts else "主号"
                self.log_cb(f"查询到账: {who} 本次抢到 {amt:.2f}元 已存入零钱", True)
        m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text)
        if m:
            claimed, total = int(m.group(1)), int(m.group(2))
            if not (0 < claimed <= total <= 99):
                return
            dec = [float(n) for n in re.findall(r"\d+\.\d+", text) if 0.01 <= float(n) <= 100000]
            amount = max(dec) if dec else 0.0
            if (claimed, total, amount) != (self.state.claimed_count, self.state.total_count, self.state.total_amount):
                self.state.update(total, claimed, amount)
                if total - claimed == 1 and amount > 0:
                    tail = amount - self.state.claimed_sum
                    self.log_cb(f"等待尾包: 已领{claimed}/{total} 总额{amount:.2f} 尾包金额≈{max(tail,0.01):.2f}元")

    def _on_tail(self, total: int, claimed: int, total_amount: float, claimed_sum: float):
        if self._stop.is_set() or not self._round_active:
            return
        self.state.update(total, claimed, total_amount, claimed_sum)
        if not self.state.check_tail():
            return
        self._decide_tail()

    def _decide_tail(self):
        tail = self.state.calc_tail_amount()
        tail_points = get_points(self.mode, tail)
        digits = sum(int(c) for c in f"{round(tail, 2):.2f}".replace(".", ""))
        lines = [f"等待尾包: 尾包金额={tail:.2f}元 各位相加={digits} 尾包点数={tail_points}"]
        if self.remark.name and self.remark.active():
            rp = get_points(self.mode, self.remark.last_amount)
            lines.append(f"备注人[{self.remark.name}]抢了{self.remark.last_amount:.2f}元 点数={rp}")
            if tail_points > rp:
                lines.append(f"尾包{tail_points}点 > 备注人{rp}点，秒抢!")
                self._pick(lines, tail_points)
            else:
                lines.append(f"尾包{tail_points}点 <= 备注人{rp}点，不抢！")
                self.log_cb(" ".join(lines), False)
        else:
            if tail_points >= self.threshold:
                lines.append(f"达到预期标准(>={self.threshold}点)，秒抢!")
                self._pick(lines, tail_points)
            else:
                lines.append(f"相加={digits} 点数={tail_points} < {self.threshold}，没达到预期标准，不抢！")
                self.log_cb(" ".join(lines), False)

    def _pick(self, lines, tail_points):
        if time.time() - self._last_click_ts < 0.6:
            return
        sub = self.allocation.next_account()
        if not sub:
            self.log_cb(" ".join(lines + ["无可用从账号，放弃"]), False)
            return
        self._last_click_ts = time.time()
        self._picks += 1
        self.log_cb(" ".join(lines + [f"从号[{sub.name}] 尾包{tail_points}点秒抢执行 (共抢{self._picks}次)"]), True)
        self._click_open_button()

    def _click_open_button(self):
        try:
            import mss as _mss
            sct = _mss.mss()
            m = self._wechat_mon(sct) or {"left": 0, "top": 0,
                                          "width": sct.monitors[0]["left"] + sct.monitors[0]["right"],
                                          "height": sct.monitors[0]["top"] + sct.monitors[0]["bottom"]}
            arr = np.asarray(sct.grab(m))
            ob = detect_open_button(arr)
            if ob:
                sx, sy = m["left"] + ob["cx"], m["top"] + ob["cy"]
                self._record_click(sx, sy)
                self.clicker.click_point(sx, sy)
                return
        except Exception:
            pass
        self.clicker.click_red_packet(0, (0.5, 0.55))
