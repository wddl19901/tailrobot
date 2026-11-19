"""机器人工作线程：编排 OCR 监控 + 决策 + 拟真点击"""
import threading

from ..utils.logger import get_logger
from ..calc_engine.calculator import get_points
from ..decision.decider import decide
from .ocr_worker import OcrWorker
from ..executor.auto_clicker import AutoClicker
from .account_manager import PollingAllocator, RedPacketState
from ..orchestrator import Account

logger = get_logger("robot")


class RobotWorker:
    def __init__(self, accounts: list[Account], strategy: str, mode: str,
                 threshold: int, log_cb=None, ocr_region=None,
                 simulate_click=True):
        self.accounts = accounts
        self.mode = mode
        self.threshold = threshold
        self.log_cb = log_cb or (lambda m, p=False: None)
        self.state = RedPacketState()
        self.allocation = PollingAllocator(accounts, strategy)
        self.clicker = AutoClicker(simulate_only=simulate_click)
        self.ocr = OcrWorker(region=ocr_region, on_tail=self._on_tail,
                             log_cb=lambda m: self.log_cb(m))
        self._stop = threading.Event()

    def start(self):
        self._stop.clear()
        self.ocr.start()
        logger.info("Robot worker started")

    def stop(self):
        self._stop.set()
        self.ocr.stop()
        logger.info("Robot worker stopped")

    def _on_tail(self, total: int, claimed: int, total_amount: float, claimed_sum: float):
        if self._stop.is_set():
            return
        self.state.update(total, claimed, total_amount, claimed_sum)
        if not self.state.check_tail():
            return
        tail = self.state.calc_tail_amount()
        points = get_points(self.mode, tail)
        rules = {
            "rule_one_enabled": True,
            "rule_one_threshold": self.threshold,
            "rule_two_enabled": False,
            "rule_three_enabled": False,
            "rule_four_all_pick": False,
            "rule_four_no_pick": False,
        }
        should, _ = decide(rules, self.mode, tail, None)
        picked_text = "已抢" if should else "不抢"
        self.log_cb(f"尾包{tail:.2f}元 {points}点 - {picked_text}", should)
        if should:
            sub = self.allocation.next_account()
            if sub:
                target = sub.handle or 0
                for ratio in self.clicker.pick_candidate(attempts=1):
                    if self.clicker.click_red_packet(target, ratio):
                        break
