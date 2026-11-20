"""授权管理器：免费试用24h + USDT到账本地解锁 + 加密持久化 + 到期拦截
网关(Worker)只负责收款, 不做鉴权; 到账 SUCCESS 后由客户端本地解锁有效期
"""
import threading
import time

from ..security.crypto import encrypt_json, decrypt_json
from ..security.ntp import get_server_time
from ..utils.paths import app_dir
from . import gateway

AUTH_FILE = app_dir() / "auth_config.dat"

TRIAL_HOURS = 24


class AuthError(Exception):
    pass


class AuthManager:
    def __init__(self, log_cb=None):
        self.log_cb = log_cb or (lambda m, p=False: None)
        self._lock = threading.Lock()
        self.first_run_ts = 0.0
        self.valid_until = 0.0
        self.activated = False
        self._load()

    def _load(self):
        if AUTH_FILE.exists():
            try:
                data = decrypt_json(AUTH_FILE.read_bytes())
                self.first_run_ts = data.get("first_run_ts", 0.0)
                self.valid_until = data.get("valid_until", 0.0)
                self.activated = data.get("activated", False)
                return
            except Exception:
                AUTH_FILE.unlink(missing_ok=True)
        now = self._server_now()
        self.first_run_ts = now
        self.valid_until = now + TRIAL_HOURS * 3600
        self._save()

    def _server_now(self) -> float:
        t = get_server_time()
        if t is None:
            raise AuthError("无法获取标准时间（NTP/Cloudflare 全部失败），为防时钟回拨拒绝启动")
        return t

    def _save(self):
        with self._lock:
            AUTH_FILE.write_bytes(encrypt_json({
                "first_run_ts": self.first_run_ts,
                "valid_until": self.valid_until,
                "activated": self.activated,
            }))

    def status(self) -> tuple[str, float]:
        now = self._safe_now()
        remain = self.valid_until - now
        if self.activated:
            return ("已激活", max(remain, 0)) if remain > 0 else ("已过期", 0)
        if remain > 0:
            return ("试用中", remain)
        return ("已过期", 0)

    def is_usable(self) -> bool:
        state, remain = self.status()
        return state != "已过期"

    def poll_trial_left(self) -> float:
        return self.status()[1]

    def unlock_package(self, label: str) -> float:
        """到账后本地解锁: 按套餐天数从当前时间起延长有效期"""
        days = self._days_of(label)
        base = max(self.valid_until, self._server_now())
        self.valid_until = base + days * 86400
        self.activated = True
        self._save()
        self.log_cb(f"解锁成功，有效期至 {time.strftime('%Y-%m-%d %H:%M', time.localtime(self.valid_until))} ({label})")
        return self.valid_until

    @staticmethod
    def _days_of(label: str) -> int:
        for item in gateway.PACKAGES:
            if item[0] == label:
                return item[2]
        return 1

    def start_order_polling(self, pay_id: str, label: str, tick_cb, stop_event: threading.Event, interval=4):
        """后台线程轮询 check-order, status==SUCCESS 时本地解锁, EXPIRED/失败则提示"""
        def worker():
            while not stop_event.is_set():
                try:
                    st = gateway.check_order(pay_id)
                    status = st.get("status", "PENDING")
                    if status == "SUCCESS":
                        self.unlock_package(label)
                        tick_cb("paid")
                        return
                    if status == "EXPIRED":
                        tick_cb("expired")
                        return
                except Exception as e:
                    tick_cb(f"poll_error:{e}")
                stop_event.wait(interval)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return t

    def _safe_now(self) -> float:
        try:
            return self._server_now()
        except AuthError:
            return time.time()
