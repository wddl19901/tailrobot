"""授权管理器：免费试用24h + 卡密激活 + 加密持久化 + 到期拦截"""
import json
import threading
import time
from pathlib import Path

from ..security.crypto import encrypt_json, decrypt_json
from ..security.ntp import get_server_time
from . import gateway

AUTH_FILE = Path(__file__).parent.parent.parent / "auth_config.dat"

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
        """返回 (试用中|已激活|已过期, 剩余秒数)"""
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

    def activate_code(self, code: str) -> float:
        code = code.strip()
        if not code:
            raise AuthError("激活码不能为空")
        data = gateway.activate(code)
        valid_until = data.get("data", {}).get("validUntil")
        if not valid_until:
            raise AuthError("网关未返回有效截止时间")
        self.valid_until = float(valid_until)
        self.activated = True
        self._save()
        self.log_cb(f"激活成功，有效期至 {time.strftime('%Y-%m-%d %H:%M', time.localtime(self.valid_until))}")
        return self.valid_until

    def start_order_polling(self, pay_id: str, tick_cb, stop_event: threading.Event, interval=4):
        """后台线程每 interval 秒轮询 check-order，到账后自动 activate"""
        def worker():
            while not stop_event.is_set():
                try:
                    st = gateway.check_order(pay_id)
                    if st.get("status") == "SUCCESS":
                        code = st.get("activationCode", "")
                        self.activate_code(code)
                        tick_cb("paid")
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
