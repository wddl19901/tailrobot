"""核心编排器：监控->检测->计算->决策->点击 全链路"""
import threading
from dataclasses import dataclass, field

from .utils.logger import get_logger
from .utils.config import load_config
from .calc_engine.calculator import get_points
from .decision.decider import decide
from .wechat_monitor.account_manager import PollingAllocator, RedPacketState
from .wechat_monitor.monitor import WeChatMonitor
from .executor.auto_clicker import AutoClicker

logger = get_logger("orchestrator")


@dataclass
class Account:
    name: str
    wxid: str = ""
    handle: int = 0
    is_main: bool = False


class Orchestrator:
    def __init__(self, log_cb=None, account_pick_cb=None):
        self.log_cb = log_cb or (lambda msg, picked=False: None)
        self.account_pick_cb = account_pick_cb
        self.cfg = load_config()
        self.strategy = "random"
        self.allocation = PollingAllocator([])
        self.accounts: list[Account] = []
        self.main = None
        self.state = RedPacketState()
        self.clicker = AutoClicker(simulate_only=True)
        self._stop = threading.Event()
        self._thread = None

    def configure(self, main: Account, subs: list, strategy: str):
        self.main = main
        self.accounts = subs
        self.strategy = strategy
        self.allocation = PollingAllocator(subs, strategy)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._log("编排器已启动")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._log("编排器已停止")

    def _run(self):
        self._loop()

    def _loop(self):
        while not self._stop.is_set():
            self._process_pending()
            self._stop.wait(0.1)

    def _process_pending(self):
        pass

    def on_red_packet_seen(self, hwnd: int, title: str):
        logger.info(f"检测到红包: {title} hwnd={hwnd}")
        self._log(f"检测到红包窗口: {title}")
        self.state.is_tail = False
        self.state.tail_candidate = None

    def on_main_claimed(self, total: int, claimed: int, total_amount: float, claimed_sum: float = 0.0):
        self.state.update(total, claimed, total_amount, claimed_sum)
        if not self.state.check_tail():
            return None
        tail = self.state.calc_tail_amount()
        mode = self.cfg.get("mode", "standard")
        points = get_points(mode, tail)
        rules = self.cfg.get("rules", {})
        target_pts = self._resolve_target_points(rules)
        should, reason = decide(rules, mode, tail, target_pts)
        picked_text = "已抢" if should else "不抢"
        self._log(f"尾包{tail:.2f}元 {points}点 - {picked_text}", should)
        if should:
            self._execute_pick(tail, points)
        return tail, points, reason

    def _resolve_target_points(self, rules: dict):
        if not rules.get("rule_three_enabled"):
            return None
        target_id = rules.get("rule_three_target_id", "")
        if not target_id:
            return None
        amount = self._lookup_player_amount(target_id)
        if amount is None:
            return None
        return get_points(self.cfg.get("mode", "standard"), amount)

    def _lookup_player_amount(self, wxid: str):
        return None

    def _execute_pick(self, tail: float, points: int):
        sub = self.allocation.next_account()
        if sub is None:
            logger.warning("无可用从账号，放弃")
            return
        logger.info(f"选中从账号: {sub.name} 策略={self.strategy}")
        if self.account_pick_cb:
            self.account_pick_cb(sub.name)
        target = sub.handle or (self.main.handle if self.main else 0)
        for ratio in self.clicker.pick_candidate(attempts=1):
            if self.clicker.click_red_packet(target, ratio):
                break

    def _log(self, msg: str, picked: bool = False):
        logger.info(msg)
        self.log_cb(msg, picked)
