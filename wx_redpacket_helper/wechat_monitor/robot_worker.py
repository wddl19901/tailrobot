"""机器人工作线程：主号秒抢 + 从号尾包点数决策 + 备注人锁定"""
import re
import threading
import time

import numpy as np

from ..utils.logger import get_logger
from ..calc_engine.calculator import get_points
from .ocr_worker import OcrWorker
from .button_finder import detect_red_blocks, find_claim_buttons
from ..executor.auto_clicker import AutoClicker
from .account_manager import PollingAllocator, RedPacketState
from ..orchestrator import Account

logger = get_logger("robot")

MAX_POINTS_FALLBACK = 9

try:
    import mss
except Exception:
    mss = None


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
        self._round_active = False
        self._last_button_ts = 0.0
        self._last_click_ts = 0.0
        self._click_cooldown_s = 1.0
        self._picks = 0
        self._last_progress_log_ts = 0.0
        self._last_heartbeat_ts = 0.0

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
            self.log_cb("未检测到 mss 截图库，无法监控红包按钮")
            return
        sct = mss.mss()
        while not self._stop.is_set():
            try:
                self._tick_screen(sct)
            except Exception as e:
                logger.error(f"watchdog tick error: {e}")
            time.sleep(0.12)

    def _tick_screen(self, sct):
        mon = sct.monitors[0]
        if mon.get("left"):
            mon = {"left": 0, "top": 0,
                   "width": mon["left"] + mon["right"],
                   "height": mon["top"] + mon["bottom"]}
        arr = np.asarray(sct.grab(mon))
        buttons = find_claim_buttons(detect_red_blocks(arr), arr.shape[1], arr.shape[0])
        now = time.time()
        if buttons:
            self._last_button_ts = now
            target = sorted(buttons, key=lambda b: b["cy"])[-1]
            if not self._round_active:
                self._round_active = True
                self.state.__init__()
                self.log_cb(f"红包轮次开始，检测到{len(buttons)}个领取按钮(目标坐标 {target['cx']},{target['cy']})，主号秒抢第1个包")
                if now - self._last_click_ts >= self._click_cooldown_s:
                    main = self.accounts[0] if self.accounts else None
                    self._last_click_ts = now
                    self._picks += 1
                    self.clicker.click_point(target["cx"], target["cy"])
                    self.state.total_count = 1
                    self.state.claimed_count = 1
                    self.log_cb(f"主号 {main.name if main else '-'} 已秒抢第1个包 (共抢{self._picks}次)", True)
                self._dump_debug(arr, buttons, "round_start")
            else:
                if now - self._last_progress_log_ts > 3:
                    self._last_progress_log_ts = now
                    self.log_cb(f"红包进行中，从号已就位等待尾包... 累计抢{self._picks}次", False)
        elif not self._round_active:
            if now - self._last_heartbeat_ts > 5:
                self._last_heartbeat_ts = now
                self.log_cb("监控中: 未发现红包领取按钮(请确认微信红包群窗口已打开且红包可见)", False)
        elif self._round_active and now - self._last_button_ts > 4:
            self._round_active = False
            self.state.__init__()
            self.log_cb(f"红包轮次结束，本轮共抢{self._picks}次", self._picks > 0)

    def _dump_debug(self, arr, buttons, tag):
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
            for b in buttons:
                dr.rectangle([b["x0"], b["y0"], b["x0"] + b["w"], b["y0"] + b["h"]], outline="yellow", width=3)
            img.save(ddir / f"debug_{tag}_{time.strftime('%H%M%S')}.png")
        except Exception as e:
            logger.debug(f"debug dump failed: {e}")

    def _on_ocr_text(self, text: str):
        self.remark.on_text(text)
        m = re.search(r"已领?取?\s*(\d+)\s*/\s*(\d+)", text)
        if m:
            claimed, total = int(m.group(1)), int(m.group(2))
            nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)]
            amount = max(nums) if nums else 0.0
            if total > 0 and (claimed, total, amount) != (self.state.claimed_count, self.state.total_count, self.state.total_amount):
                self.state.update(total, claimed, amount)
                if total - claimed == 1:
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
        if time.time() - self._last_click_ts < self._click_cooldown_s:
            return
        sub = self.allocation.next_account()
        if not sub:
            self.log_cb(" ".join(lines + ["无可用从账号，放弃"]), False)
            return
        self._last_click_ts = time.time()
        self._picks += 1
        self.log_cb(" ".join(lines + [f"从号[{sub.name}] 尾包{tail_points}点秒抢执行 (共抢{self._picks}次)"]), True)
        self._click_last_button()

    def _click_last_button(self):
        try:
            import mss as _mss
            sct = _mss.mss()
            mon = sct.monitors[0]
            arr = np.asarray(sct.grab(mon))
            buttons = find_claim_buttons(detect_red_blocks(arr), arr.shape[1], arr.shape[0])
            if buttons:
                b = sorted(buttons, key=lambda x: x["cy"])[-1]
                self.clicker.click_point(b["cx"], b["cy"])
                return
        except Exception:
            pass
        self.clicker.click_red_packet(0, (0.5, 0.55))
