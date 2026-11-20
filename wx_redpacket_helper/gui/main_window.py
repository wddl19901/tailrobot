import platform
import sys
import threading
import time
import webbrowser

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QComboBox, QGroupBox, QCheckBox, QTextBrowser, QMessageBox
)
from PyQt6.QtCore import QTimer, pyqtSignal

from .styles import QSS, LOG_QSS
from ..utils.config import load_config, save_config
from ..utils.autostart import set_enabled as autostart_set
from ..billing.auth_manager import AuthManager, AuthError
from ..billing import gateway
from ..wechat_monitor.launcher import launch_instance, pid_alive
from ..wechat_monitor.robot_worker import RobotWorker
from ..orchestrator import Account

IS_WIN = platform.system() == "Windows"


class AccountItem(QListWidgetItem):
    def __init__(self, name: str, idx: int, handle: int = 0, pid: int = 0):
        super().__init__(name)
        self.idx = idx
        self._handle = handle
        self._pid = pid

    def name(self) -> str:
        return self.text()

    @property
    def handle(self) -> int:
        return getattr(self, "_handle", 0)

    @handle.setter
    def handle(self, value: int):
        self._handle = value

    @property
    def pid(self) -> int:
        return getattr(self, "_pid", 0)

    @pid.setter
    def pid(self, value: int):
        self._pid = value


class MainWindow(QMainWindow):
    log_signal = pyqtSignal(str, bool)
    robot_ready = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.accounts = []
        self._inst_seq = 0
        self._poll_stop = threading.Event()
        self.auth = AuthManager(log_cb=lambda m, p=False: self.log_signal.emit(m, p))
        self.robot = None
        self._init_ui()
        self.log_signal.connect(self._append_log)
        self.robot_ready.connect(lambda m: self.log_signal.emit(m, False))
        self._load_state()
        self._apply_style()
        self._refresh_auth()
        self._auth_timer = QTimer(self)
        self._auth_timer.timeout.connect(self._refresh_auth)
        self._auth_timer.start(30000)
        self._login_check_timer = QTimer(self)
        self._login_check_timer.timeout.connect(self._check_wechat_login)
        self._login_check_timer.start(10000)
        self._last_login_warn = 0.0
        self._logged_pids = set()
        self._main_logged = False

    def _check_wechat_login(self):
        try:
            import win32gui
            import win32process
        except Exception:
            return
        login_titles, main_windows = [], []
        def _cb(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                t = (win32gui.GetWindowText(hwnd) or "").strip()
                cls = win32gui.GetClassName(hwnd)
                if "登录微信" in t or ("登录" in t and "微信" in t):
                    login_titles.append(t)
                if cls in ("Qt51514QWindowIcon", "Qt6514QWindowIcon", "WeChatMainWndForPC") and t == "微信":
                    main_windows.append(hwnd)
            except Exception:
                pass
            return True
        try:
            win32gui.EnumWindows(_cb, None)
        except Exception:
            return
        acc_pid = {a.pid: a.name() for a in self.accounts if a.pid}
        for hwnd in main_windows:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                continue
            name = acc_pid.get(pid)
            if name:
                if pid not in self._logged_pids:
                    self._logged_pids.add(pid)
                    self.log_signal.emit(f"从号登录成功({name}, pid={pid})", True)
            else:
                if not self._main_logged:
                    self._main_logged = True
                    self.log_signal.emit(f"主号登录成功(pid={pid})", True)
        if login_titles:
            import time as _t
            if _t.time() - self._last_login_warn > 60:
                self._last_login_warn = _t.time()
                self.log_signal.emit(f"检测到微信登录窗口({login_titles[0]})：登录态已失效，请快速重新登录(数据已保留，通常免扫码)", True)

    def _apply_style(self):
        self.setStyleSheet(QSS)

    def _init_ui(self):
        self.setWindowTitle("微信尾包助手 · 商业版")
        self.setMinimumSize(460, 720)
        self.resize(480, 760)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        title = QLabel("微信尾包助手")
        title.setStyleSheet("font-size:18px;font-weight:bold;color:#f5d442;background:transparent;border:none;")
        root.addWidget(title)

        root.addWidget(self._build_auth_area())
        root.addWidget(self._build_account_area())
        root.addWidget(self._build_control_area())
        root.addWidget(self._build_log_area(), 1)

    def _build_auth_area(self):
        grp = QGroupBox("授权充值")
        lay = QVBoxLayout()

        row = QHBoxLayout()
        self.auth_state_lbl = QLabel("检测中...")
        self.auth_state_lbl.setStyleSheet("font-weight:bold;font-size:13px;color:#f5d442;background:transparent;border:none;")
        self.auth_time_lbl = QLabel("")
        self.auth_time_lbl.setStyleSheet("color:#888;background:transparent;border:none;font-size:12px;")
        row.addWidget(self.auth_state_lbl)
        row.addWidget(self.auth_time_lbl)
        row.addStretch(1)
        lay.addLayout(row)

        buy_row = QHBoxLayout()
        self.pkg_cb = QComboBox()
        for label, price, _days in gateway.PACKAGES:
            self.pkg_cb.addItem(f"{label}  ({price}U)", label)
        self.buy_btn = QPushButton("获取充值网页")
        self.buy_btn.clicked.connect(self._on_get_pay)
        buy_row.addWidget(self.pkg_cb, 1)
        buy_row.addWidget(self.buy_btn)
        lay.addLayout(buy_row)

        grp.setLayout(lay)
        return grp

    def _build_account_area(self):
        grp = QGroupBox("账号玩法配置")
        lay = QVBoxLayout()

        add_row = QHBoxLayout()
        self.wx_btn = QPushButton("一键添加登录微信")
        self.wx_btn.clicked.connect(self._on_add_wechat)
        self.autostart_cb = QCheckBox("开机自启动")
        self.autostart_cb.toggled.connect(self._on_autostart)
        add_row.addWidget(self.wx_btn, 1)
        add_row.addWidget(self.autostart_cb)
        lay.addLayout(add_row)

        self.acc_list = QListWidget()
        self.acc_list.setFixedHeight(96)
        self.acc_list.itemDoubleClicked.connect(self._remove_selected_account)
        lay.addWidget(self.acc_list)

        self.random_cb = QCheckBox("开启多账号随机轮询抢包")
        lay.addWidget(self.random_cb)

        play_row = QHBoxLayout()
        self.mode_cb = QComboBox()
        self.mode_cb.addItems(["标准相加", "三公", "牛牛"])
        self.point_input = QLineEdit()
        self.point_input.setPlaceholderText("触发点数(>=)")
        self.point_input.setMaxLength(1)
        play_row.addWidget(QLabel("玩法"))
        play_row.addWidget(self.mode_cb, 1)
        play_row.addWidget(QLabel("点数"))
        play_row.addWidget(self.point_input)
        lay.addLayout(play_row)

        price_row = QHBoxLayout()
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("红包单价 元/包(如0.5, 留空则按OCR识别总额)")
        self.price_input.setMaxLength(8)
        price_row.addWidget(QLabel("单价"))
        price_row.addWidget(self.price_input, 1)
        lay.addLayout(price_row)

        remark_row = QHBoxLayout()
        self.remark_input = QLineEdit()
        self.remark_input.setPlaceholderText("锁定备注人(选填，只比对他的点数)")
        remark_row.addWidget(QLabel("锁定"))
        remark_row.addWidget(self.remark_input, 1)
        lay.addLayout(remark_row)

        grp.setLayout(lay)
        return grp

    def _build_control_area(self):
        grp = QGroupBox("控制")
        lay = QHBoxLayout()
        lay.setSpacing(10)
        self.start_btn = QPushButton("启动机器人")
        self.start_btn.setStyleSheet("font-size:15px;font-weight:bold;padding:10px;")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn = QPushButton("停用机器人")
        self.stop_btn.setStyleSheet("font-size:15px;font-weight:bold;padding:10px;")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        lay.addWidget(self.start_btn, 1)
        lay.addWidget(self.stop_btn, 1)
        grp.setLayout(lay)
        return grp

    def _build_log_area(self):
        grp = QGroupBox("运行日志")
        lay = QVBoxLayout()
        self.log_box = QTextBrowser()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(LOG_QSS)
        lay.addWidget(self.log_box)
        clear_btn = QPushButton("清空")
        clear_btn.setFixedHeight(28)
        clear_btn.clicked.connect(self.log_box.clear)
        lay.addWidget(clear_btn)
        grp.setLayout(lay)
        return grp

    def _on_add_wechat(self):
        self._inst_seq += 1
        idx = self._inst_seq
        res = launch_instance(idx)
        if res["success"]:
            item = AccountItem(f"从号-{idx}", idx, pid=res["pid"])
            self.acc_list.addItem(item)
            self.accounts.append(item)
            self._save_to_cfg()
            self.robot_ready.emit(res["note"])
        else:
            QMessageBox.warning(self, "启动失败", res["note"])

    def _remove_selected_account(self, item):
        idx = self.acc_list.row(item)
        if 0 <= idx < len(self.accounts):
            self.accounts.pop(idx)
            self.acc_list.takeItem(idx)

    def _on_get_pay(self):
        label = self.pkg_cb.currentData()
        price = next(p for l, p, _ in gateway.PACKAGES if l == label)
        order_id = f"TAILROBOT_{int(time.time())}_{self._inst_seq}"
        try:
            self.robot_ready.emit(f"创建订单: {label} ({price}U) 订单号 {order_id}")
            data = gateway.create_order(price, order_id)
            pay_url = data.get("payUrl", "")
            pay_id = data.get("payId", "")
            if pay_url:
                webbrowser.open(pay_url)
            if pay_id:
                self._poll_stop = threading.Event()
                self.auth.start_order_polling(
                    pay_id,
                    label,
                    tick_cb=lambda ev: self.robot_ready.emit(self._poll_msg(ev)),
                    stop_event=self._poll_stop,
                )
                self.robot_ready.emit("已打开充值网页，请按页面显示的精准USDT金额支付(TRC20)，后台每4秒检测到账")
        except Exception as e:
            QMessageBox.critical(self, "下单失败", str(e))

    @staticmethod
    def _poll_msg(ev: str) -> str:
        if ev == "paid":
            return "检测到到账，授权已解锁"
        if ev == "expired":
            return "订单已过期，请重新发起支付"
        return f"到账检测: {ev}"

    def _on_autostart(self, checked: bool):
        try:
            autostart_set(checked)
            self.robot_ready.emit("开机自启动已" + ("开启" if checked else "关闭"))
        except Exception as e:
            self.robot_ready.emit(f"开机自启动设置失败: {e}")

    def _on_start(self):
        if not self.auth.is_usable():
            QMessageBox.warning(self, "授权不可用", "授权已过期或试用已结束，请充值或激活后再启动机器人")
            self._refresh_auth()
            return
        if not self.accounts:
            QMessageBox.information(self, "提示", "请先点击【一键添加登录微信】添加至少一个从账号")
            return
        try:
            import traceback
            self._save_to_cfg()
            subs = [Account(name=a.name(), handle=a.handle) for a in self.accounts]
            strategy = "random" if self.random_cb.isChecked() else "order"
            mode_map = ["standard", "sg", "niuniu"]
            mode = mode_map[self.mode_cb.currentIndex()]
            threshold = int(self.point_input.text().strip() or 7)
            price_txt = self.price_input.text().strip()
            try:
                unit_price = round(float(price_txt), 2) if price_txt else 0.0
            except ValueError:
                unit_price = 0.0
            self.robot = RobotWorker(
                accounts=subs, strategy=strategy, mode=mode, threshold=threshold,
                log_cb=lambda m, p=False: self.log_signal.emit(m, p),
                simulate_click=False if IS_WIN else True,
                remark_name=self.remark_input.text().strip(),
                unit_price=unit_price,
            )
            self.robot.start()
            self._set_running(True)
        except Exception:
            err = traceback.format_exc()
            self.log_signal.emit("启动失败:\n" + err, False)
            QMessageBox.critical(self, "启动失败", "启动机器人时发生异常，详情见日志区：\n\n" + err[:800])

    def _on_stop(self):
        if self.robot:
            self.robot.stop()
            self.robot = None
        self._poll_stop.set()
        self._set_running(False)
        self.robot_ready.emit("机器人已停用")

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running and self.auth.is_usable())
        self.stop_btn.setEnabled(running)
        self.start_btn.setText("运行中..." if running else "启动机器人")

    def _refresh_auth(self):
        try:
            state, remain = self.auth.status()
        except AuthError:
            state, remain = "已过期", 0
        self.auth_state_lbl.setText(state)
        if state == "已过期":
            self.auth_state_lbl.setStyleSheet("font-weight:bold;font-size:13px;color:#ff5252;background:transparent;border:none;")
            self.auth_time_lbl.setText("请充值")
        else:
            h = int(remain // 3600)
            m = int((remain % 3600) // 60)
            d = int(remain // 86400)
            if d > 0:
                self.auth_time_lbl.setText(f"剩余 {d}天 {h}小时")
            elif h > 0:
                self.auth_time_lbl.setText(f"剩余 {h}小时 {m}分")
            else:
                self.auth_time_lbl.setText(f"剩余 {m}分")
            color = "#4caf50" if state == "已激活" else "#f5d442"
            self.auth_state_lbl.setStyleSheet(f"font-weight:bold;font-size:13px;color:{color};background:transparent;border:none;")
        self._set_running(self.start_btn.text() == "运行中...")
        if self.start_btn.text() != "运行中...":
            self.start_btn.setEnabled(self.auth.is_usable())

    def _save_to_cfg(self):
        mode_map = ["standard", "sg", "niuniu"]
        cfg = self.cfg.copy()
        cfg["mode"] = mode_map[self.mode_cb.currentIndex()]
        cfg["polling_strategy"] = "random" if self.random_cb.isChecked() else "order"
        cfg["accounts"] = [{"name": a.name(), "idx": a.idx, "handle": a.handle, "pid": a.pid} for a in self.accounts]
        cfg["autostart"] = self.autostart_cb.isChecked()
        cfg["remark_name"] = self.remark_input.text().strip()
        try:
            price_txt = self.price_input.text().strip()
            cfg["unit_price"] = round(float(price_txt), 2) if price_txt else 0.0
        except ValueError:
            cfg["unit_price"] = 0.0
        save_config(cfg)

    def _load_state(self):
        mode_map = {"standard": 0, "sg": 1, "niuniu": 2}
        self.mode_cb.setCurrentIndex(mode_map.get(self.cfg.get("mode", "standard"), 0))
        self.random_cb.setChecked(self.cfg.get("polling_strategy", "random") == "random")
        self.point_input.setText(str(self.cfg.get("rules", {}).get("rule_one_threshold", 7)))
        for acc in self.cfg.get("accounts", []):
            item = AccountItem(
                acc.get("name", ""), acc.get("idx", 0),
                handle=acc.get("handle", 0), pid=acc.get("pid", 0),
            )
            self.acc_list.addItem(item)
            self.accounts.append(item)
            self._inst_seq = max(self._inst_seq, acc.get("idx", 0))
        self.autostart_cb.setChecked(self.cfg.get("autostart", False))
        self.remark_input.setText(self.cfg.get("remark_name", ""))
        price = self.cfg.get("unit_price", 0.0)
        self.price_input.setText(f"{price:.2f}" if price else "")
        QTimer.singleShot(300, self._restore_wechat_instances)

    def _restore_wechat_instances(self):
        threading.Thread(target=self._restore_in_bg, daemon=True).start()

    def _restore_in_bg(self):
        for a in self.accounts:
            if pid_alive(a.pid):
                self.robot_ready.emit(f"检测到微信实例仍存活: {a.name()} (pid={a.pid})")
                continue
            res = launch_instance(a.idx)
            if res["success"]:
                a.pid = res["pid"]
            else:
                self.robot_ready.emit(f"恢复微信失败: {a.name()} {res['note']}")

    def _append_log(self, msg: str, picked: bool):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        color = "#4caf50" if picked else "#f5d442"
        self.log_box.append(f'<span style="color:#666">{ts}</span> <span style="color:{color}">{msg}</span>')

    def closeEvent(self, event):
        self._auth_timer.stop()
        if self.robot:
            self.robot.stop()
        self._poll_stop.set()
        self._save_to_cfg()
        event.accept()


def run_app():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_app()
