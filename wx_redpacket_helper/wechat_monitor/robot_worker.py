"""机器人工作线程：主号秒抢 + 从号尾包点数决策 + 备注人锁定"""
import re
import random
import threading
import time

import numpy as np

from ..utils.logger import get_logger
from ..calc_engine.calculator import get_points
from .ocr_worker import OcrWorker
from .redpack import detect_red_packet_cards, detect_open_button, detect_sidebar_redpack, detect_result_close
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


def find_wechat_windows():
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
    except Exception:
        return []
    out = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, ctypes.c_long)

    def _cb(hwnd, _):
        try:
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                if buf.value == "微信":
                    cls = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, cls, 256)
                    if cls.value in ("Qt51514QWindowIcon", "Qt6514QWindowIcon", "WeChatMainWndForPC"):
                        out.append(hwnd)
        except Exception:
            pass
        return True
    try:
        user32.EnumWindows(WNDENUMPROC(_cb), 0)
    except Exception:
        pass
    single = find_wechat_hwnd()
    if single and single not in out:
        out.append(single)
    return out


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
                 simulate_click=True, remark_name: str = "",
                 unit_price: float = 0.0):
        self.accounts = accounts
        self.mode = mode
        self.threshold = threshold
        self.unit_price = round(float(unit_price or 0), 2)
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
        self._last_fg_ts = 0.0
        self._last_fg_was_min = False
        self._last_side_pos = None
        self._side_streak = 0
        self._last_close_ts = 0.0
        self._last_result_amt = None
        self._last_result_ts = 0.0
        self._state_fresh_ts = 0.0
        self._tail_mark = None
        self._last_card_pos = None
        self._last_card_log_key = None
        self._last_reopen_ts = 0.0
        self._last_result_gone_ts = 0.0
        self._last_pick_ts = 0.0
        self._main_claimed_sum = 0.0
        self._cur_card_key = None
        self._cur_card_pos = None
        self._card_done = False
        self._ob_first_ts = 0.0
        self._no_win_warned = False
        self._win_switched_ts = 0.0
        self._last_reopen_done_ts = 0.0
        self._dbg_dump_ts = 0.0
        self._dbg_arr = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.ocr.start()
        extra = f"，备注锁定: {self.remark.name}" if self.remark.name else ""
        logger.info(f"Robot worker started threshold={self.threshold} mode={self.mode} unit_price={self.unit_price}{extra}")
        price_note = f" 单价={self.unit_price}元/包" if self.unit_price > 0 else ""
        self.log_cb(f"机器人已启动: 玩法={self.mode} 触发点数>={self.threshold}{price_note}{extra}")

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
        wins = find_wechat_windows()
        if wins:
            self._no_win_warned = False
            import ctypes
            user32 = ctypes.windll.user32
            order = [w for w in wins if w == self._hwnd] + [w for w in wins if w != self._hwnd]
            active = None
            for i, h in enumerate(order):
                if now - self._last_fg_ts > 0.5:
                    was_min = ensure_window_foreground(h, user32)
                    if was_min:
                        self.log_cb("检测到微信窗口被最小化，已自动恢复并置前", False)
                    self._last_fg_ts = now
                m = self._wechat_mon2(h, user32)
                if not m:
                    continue
                self._rect = (m["left"], m["top"])
                arr = np.asarray(sct.grab(m))
                if self._process(arr, now, i == 0):
                    active = h
                    break
                time.sleep(0.02)
            if active is None:
                active = order[0]
                self._last_fg_ts = 0.0
            if active != self._hwnd:
                self._hwnd = active
                self._win_switched_ts = now
                self._last_signal_ts = now
                self._clicked = []
                self._cur_card_key = None
                self._cur_card_pos = None
                self._card_done = False
                self._last_card_pos = None
                self._last_card_log_key = None
                self._last_side_pos = None
                self._side_streak = 0
                self._last_close_ts = 0.0
                self._last_result_gone_ts = 0.0
                self._last_result_amt = None
                self._last_result_ts = 0.0
                if now - getattr(self, "_last_switch_log_ts", 0) >= 10:
                    self._last_switch_log_ts = now
                    self.log_cb(f"多窗口: 已锁定含红包的微信窗口(共{len(wins)}个)", False)
            return
        self._hwnd = None
        if not self._no_win_warned:
            self._no_win_warned = True
            self.log_cb("监控中: 未找到微信窗口(请确认微信已登录且窗口未最小化)", False)

    def _wechat_mon2(self, h, user32):
        try:
            rect = get_window_rect(h, user32)
        except Exception:
            return None
        if rect[2] <= rect[0] or rect[3] <= rect[1]:
            return None
        return {"left": max(0, rect[0]), "top": rect[1],
                "width": rect[2] - rect[0], "height": rect[3] - rect[1]}

    def _process(self, arr, now, primary=False):
        rc = detect_result_close(arr)
        if rc:
            self._last_signal_ts = now
            self._last_result_gone_ts = 0.0
            if now - self._dbg_dump_ts >= 3.0:
                self._dbg_dump_ts = now
                self._dump_debug(arr, "result", marker=(self._rect[0] + rc["cx"], self._rect[1] + rc["cy"]))
            if now - self._last_close_ts >= 0.8:
                self._last_close_ts = now
                sx, sy = self._rect[0] + rc["cx"], self._rect[1] + rc["cy"]
                self.clicker.click_point(sx, sy)
                self.clicker.press_escape(self._hwnd)
            return True
        elif self._dbg_dump_ts and now - self._dbg_dump_ts > 5:
            self._dbg_dump_ts = 0.0
        if not rc and self._last_close_ts:
            self._last_result_gone_ts = self._last_result_gone_ts or now
            if now - self._last_result_gone_ts < 1.2:
                if now - self._last_close_ts < 2.5:
                    return True
                self._last_result_gone_ts = 0.0
                self._last_close_ts = 0.0
                if self._cur_card_pos and self.state.remaining >= 1 and self._tail_mark is None:
                    sx, sy = self._cur_card_pos
                    self._record_click(sx, sy)
                    self._last_card_click_ts = time.time()
                    self.log_cb(f"抢完按ESC，再点刚才的红包查剩余包数(剩{self.state.remaining}个)", False)
                    time.sleep(random.uniform(0.05, 0.15))
                    self.clicker.click_point(sx, sy)
            return True
        ob = detect_open_button(arr)
        if ob:
            self._last_signal_ts = now
            if self._ob_first_ts == 0.0:
                self._ob_first_ts = now
                self.log_cb(f"红包详情页已打开(面板{ob['panel']}) 等OCR读剩余包数", False)
                self._dump_debug(arr, "popup")
            stale = now - self._state_fresh_ts > 4
            if stale and now - self._ob_first_ts > 12:
                who = self.accounts[0].name if self.accounts else "主号"
                self.log_cb(f"{who} 详情页{now - self._ob_first_ts:.0f}秒无OCR数据，放弃本包", False)
                self.clicker.press_escape(self._hwnd)
                time.sleep(0.3)
                self._reset_round()
                return True
            if self._tail_hold():
                return True
            if self._tail_mark is not None and now - self._last_close_ts >= 0.5:
                self.clicker.press_escape(self._hwnd)
                self._last_close_ts = now
                return True
            sx, sy = self._rect[0] + ob["cx"], self._rect[1] + ob["cy"]
            if not self._is_clicked(sx, sy) and now - self._last_click_ts >= 0.6:
                delay = random.uniform(0.05, 0.15)
                time.sleep(delay)
                self._last_click_ts = time.time()
                self._picks += 1
                self._record_click(sx, sy)
                self.clicker.click_point(sx, sy)
                who = self.accounts[0].name if self.accounts else "主号"
                self.log_cb(f"{who} 点「开」抢包 @({sx},{sy}) 共抢{self._picks}次", True)
                time.sleep(random.uniform(0.4, 0.6))
                self._close_popup()
            return True
        if not ob:
            if self._card_done:
                if now - self._last_signal_ts > 8:
                    who = self.accounts[0].name if self.accounts else "主号"
                    self.log_cb(f"{who} 本包结束: 共抢{self._picks}个 合计{self._main_claimed_sum:.2f}元，停止点击本包", self._picks > 0)
                    self._card_done = False
                    self._last_card_pos = None
            else:
                self._ob_first_ts = 0.0
        cards = detect_red_packet_cards(arr)
        if cards:
            if ob or rc or self._card_done:
                return True
            if now - self._last_close_ts < 2.5:
                return True
            newest = cards[-1]
            key = (newest["cx"] // 16, newest["cy"] // 16)
            if key != self._cur_card_key:
                self._cur_card_key = key
                self._cur_card_pos = (self._rect[0] + newest["cx"], self._rect[1] + newest["cy"])
                self._reset_round()
                self.log_cb(f"检测到新红包卡片({len(cards)}个)，点击最新 @{self._cur_card_pos[0]},{self._cur_card_pos[1]}", True)
                self._dump_debug(arr, "cards")
            sx, sy = self._cur_card_pos
            if now - self._last_card_click_ts >= 0.8:
                self._last_card_click_ts = now
                delay = random.uniform(0.05, 0.15)
                time.sleep(delay)
                self._record_click(sx, sy)
                self._last_card_pos = (sx, sy)
                self.clicker.click_point(sx, sy)
                self._card_done = True
                self._round_active = True
            return True
        side = detect_sidebar_redpack(arr)
        if side and not self._round_active:
            self._last_side_ts = now
            key = (side["cx"] // 16, side["cy"] // 16)
            if key == self._last_side_pos:
                self._side_streak += 1
            else:
                self._last_side_pos = key
                self._side_streak = 0
            if self._side_streak < 8 and now - self._last_side_click_ts >= 4.0:
                self._last_side_click_ts = now
                sx = self._rect[0] + min(side["cx"] + 30, int(arr.shape[1] * 0.30))
                sy = self._rect[1] + side["cy"]
                self.log_cb(f"会话列表发现红包预览@(窗口坐标 {side['cx']},{side['cy']})，自动打开该群")
                self.clicker.click_point(sx, sy)
            return True
        if primary and not self._round_active and now - self._last_close_ts > 8:
            if now - self._last_scroll_ts > 12:
                self._last_scroll_ts = now
                self._scroll_sidebar(arr)
        if self._round_active and now - self._last_signal_ts > 4:
            self._round_active = False
        return False

    def _reset_round(self):
        self._round_active = True
        self._picks = 0
        self._main_claimed_sum = 0.0
        self._tail_mark = None
        self._ob_first_ts = 0.0
        self._state_fresh_ts = 0.0
        self._clicked = []
        self.state.total_count = 0
        self.state.claimed_count = 0
        self.state.total_amount = 0.0
        self.state.claimed_sum = 0.0

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
        except Exception as e:
            logger.debug(f"scroll sidebar: {e}")

    def _close_popup(self):
        try:
            self._last_close_ts = time.time()
            self.clicker.press_escape(self._hwnd)
        except Exception as e:
            logger.debug(f"close popup: {e}")

    def _tail_hold(self):
        if not self.state.total_count:
            return False
        fresh = time.time() - self._state_fresh_ts < 15
        return fresh and self.state.remaining == 1 and self.state.total_amount > 0

    def _mark_tail_no_grab(self, tail, points):
        self._tail_mark = {"ts": time.time(), "amount": round(tail, 2), "points": points}
        self.log_cb(f"仅剩1包({tail:.2f}元) 不抢, 永久标记跳过", False)

    def _dump_debug(self, arr, tag, marker=None):
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
            if marker:
                lx, ly = marker[0] - self._rect[0], marker[1] - self._rect[1]
                dr.rectangle([lx - 25, ly - 25, lx + 25, ly + 25], outline="lime", width=4)
            img.save(ddir / f"debug_{tag}_{time.strftime('%H%M%S')}.png")
        except Exception as e:
            logger.debug(f"debug dump failed: {e}")

    def _on_ocr_text(self, text: str):
        self.remark.on_text(text)
        m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})", text)
        claimed = int(m.group(1)) if m else None
        if "存入零钱" in text or "已存入" in text:
            dec = [float(n) for n in re.findall(r"\d+\.\d+", text) if 0.005 <= float(n) <= 100000]
            amt = max(dec) if dec else 0.0
            if amt and time.time() - self._last_pick_ts >= 2:
                self._last_pick_ts = time.time()
                self._main_claimed_sum = round(self._main_claimed_sum + amt, 2)
                self.state.claimed_sum = self._main_claimed_sum
                who = self.accounts[0].name if self.accounts else "主号"
                rem = self.state.remaining if self.state.total_count else 0
                extra = f" 还剩{rem}个包未抢(等待中)" if rem > 1 else ("" if rem == 0 else f" 剩尾包")
                self.log_cb(f"{who}抢了红包({amt:.2f}元){extra}", True)
        if m:
            total = int(m.group(2))
            if not (0 < claimed <= total <= 99):
                return
            if self.unit_price > 0:
                amount = round(self.unit_price * total, 2)
            else:
                dec = [float(n) for n in re.findall(r"\d+\.\d+", text) if 0.01 <= float(n) <= 100000]
                amount = max(dec) if dec else 0.0
            if (claimed, total, amount) != (self.state.claimed_count, self.state.total_count, self.state.total_amount):
                self.state.update(total, claimed, amount, self._main_claimed_sum)
                self._state_fresh_ts = time.time()
                if self.state.remaining == 1 and amount > 0 and self._tail_mark is None:
                    self._decide_tail()

    def _on_tail(self, total: int, claimed: int, total_amount: float, claimed_sum: float):
        if self._stop.is_set() or not self._round_active:
            return
        if self.unit_price > 0:
            total_amount = round(self.unit_price * total, 2)
        cs = self._main_claimed_sum if self._main_claimed_sum > 0 else claimed_sum
        self.state.update(total, claimed, total_amount, cs)
        self._state_fresh_ts = time.time()
        if not self.state.check_tail():
            return
        self._decide_tail()

    def _decide_tail(self):
        if self._tail_mark is not None:
            return
        tail = self.state.calc_tail_amount()
        tail_points = get_points(self.mode, tail)
        if self.remark.name and self.remark.active():
            rp = get_points(self.mode, self.remark.last_amount)
            if tail_points > rp:
                self._pick(tail, tail_points)
            else:
                self._mark_tail_no_grab(tail, tail_points)
                return
        else:
            if tail_points >= self.threshold:
                self._pick(tail, tail_points)
            else:
                self._mark_tail_no_grab(tail, tail_points)
                return

    def _pick(self, tail, tail_points):
        if time.time() - self._last_click_ts < 0.6:
            return
        sub = self.allocation.next_account()
        if not sub:
            self.log_cb(f"仅剩1包({tail:.2f}元) 无可用从号，放弃", False)
            return
        self._last_click_ts = time.time()
        self._picks += 1
        self.log_cb(f"从号[{sub.name}]尾包{tail:.2f}元({tail_points}点) 秒抢 (共抢{self._picks}次)", True)
        self._click_open_button()

    def _click_open_button(self):
        try:
            import mss as _mss
            import ctypes
            user32 = ctypes.windll.user32
            sct = _mss.mss()
            h = self._hwnd or find_wechat_hwnd()
            m = self._wechat_mon2(h, user32) if h else None
            if not m:
                mon = sct.monitors[0]
                m = {"left": 0, "top": 0,
                     "width": mon["right"] - mon["left"],
                     "height": mon["bottom"] - mon["top"]}
            self._rect = (m["left"], m["top"])
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
