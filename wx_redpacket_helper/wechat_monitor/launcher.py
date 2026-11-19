"""微信原生多开启动器：数据隔离目录 + 独立实例，不修改内存
Windows: 启动 WeChat.exe 并指定独立数据路径
macOS:   open -n 启动独立新实例
"""
import platform
import re
import string
import subprocess
from pathlib import Path

from ..utils.logger import get_logger
from ..utils.paths import app_dir

logger = get_logger("launcher")

IS_WIN = platform.system() == "Windows"

_WIN_WECHAT_EXE = [
    r"C:\Program Files\Tencent\WeChat\WeChat.exe",
    r"C:\Program Files (x86)\Tencent\WeChat\WeChat.exe",
    r"C:\Program Files\Tencent\Weixin\Weixin.exe",
    r"C:\Program Files (x86)\Tencent\Weixin\Weixin.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Tencent" / "WeChat" / "WeChat.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Tencent" / "Weixin" / "Weixin.exe",
]

_EXE_NAMES = ("WeChat.exe", "WeChatApp.exe", "Weixin.exe")

_DATA_ROOT = app_dir() / "TailRobotData"


def _find_in_registry() -> list[str]:
    found: list[str] = []
    try:
        import winreg
        for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                                     0, winreg.KEY_READ | view)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                try:
                    skey = winreg.OpenKey(key, sub)
                    try:
                        display, _ = winreg.QueryValueEx(skey, "DisplayName")
                        if not any(k in str(display).lower() for k in ("wechat", "weixin")):
                            continue
                        loc, _ = winreg.QueryValueEx(skey, "InstallLocation")
                    except OSError:
                        continue
                    winreg.CloseKey(skey)
                    base = Path(str(loc)).expandvars()
                    for name in _EXE_NAMES:
                        exe = base / name
                        if exe.exists():
                            found.append(str(exe))
                    for sub in ("x64", "x86"):
                        x64 = base / sub / "WeChatApp.exe"
                        if x64.exists():
                            found.append(str(x64))
                except OSError:
                    continue
            winreg.CloseKey(key)
    except Exception:
        pass
    return found


def _scan_drives() -> list[str]:
    found: list[str] = []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drives = [c for c, bit in zip(string.ascii_uppercase, range(26)) if mask & (1 << bit)]
    except Exception:
        drives = ["C"]
    for drive in drives:
        root = Path(f"{drive}:\\")
        if not root.exists():
            continue
        for sub in root.glob("*"):
            name = sub.name.lower()
            if not re.search(r"tencent|wechat|weixin|wx", name):
                continue
            for exe_name in _EXE_NAMES:
                for exe in sub.glob(f"**/{exe_name}"):
                    found.append(str(exe))
    return found


def _find_with_where() -> list[str]:
    found: list[str] = []
    for exe_name in _EXE_NAMES:
        try:
            out = subprocess.run(["where", exe_name], capture_output=True,
                                 text=True, timeout=5)
            if out.returncode == 0:
                found += [line.strip() for line in out.stdout.splitlines() if line.strip()]
        except Exception:
            pass
    return found


def _find_wechat_exe() -> str | None:
    candidates: list[str] = []
    candidates += [str(p) for p in _WIN_WECHAT_EXE]
    candidates += _find_in_registry()
    candidates += _scan_drives()
    candidates += _find_with_where()
    for c in candidates:
        try:
            if Path(c).exists():
                return c
        except OSError:
            continue
    return None


def launch_instance(index: int) -> dict:
    """
    启动第 index 个隔离微信实例，返回 {success, pid, data_dir, note}
    每个实例使用独立数据目录 TailRobotData/User_{index}，
    首次登录该目录时弹出全新官方微信登录框。
    """
    data_dir = _DATA_ROOT / f"User_{index}"
    data_dir.mkdir(parents=True, exist_ok=True)

    if IS_WIN:
        exe = _find_wechat_exe()
        if not exe:
            return {"success": False, "pid": 0, "data_dir": str(data_dir),
                    "note": "未找到 WeChat.exe，请手动指定安装路径"}
        # 微信数据隔离：通过启动参数+独立用户数据目录实现多开
        # --data-path 为隔离参数；若目标版本不识别该参数，微信仍会因
        # 独立数据目录（首次登录态）而弹出独立登录框
        cmd = [exe, f"--data-path={data_dir}"]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(data_dir),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            logger.info(f"启动微信实例 #{index} pid={proc.pid} data_dir={data_dir}")
            return {"success": True, "pid": proc.pid, "data_dir": str(data_dir),
                    "note": f"实例#{index} 已启动，独立数据目录 {data_dir.name}"}
        except Exception as e:
            logger.error(f"启动失败: {e}")
            return {"success": False, "pid": 0, "data_dir": str(data_dir), "note": str(e)}

    # macOS: -n 强制开新实例
    app = "/Applications/WeChat.app"
    if not Path(app).exists():
        return {"success": False, "pid": 0, "data_dir": str(data_dir),
                "note": "未找到 /Applications/WeChat.app"}
    try:
        proc = subprocess.Popen(["open", "-n", app],
                                env={"__WECHAT_DATA_DIR": str(data_dir)})
        logger.info(f"启动 macOS 微信新实例 pid={proc.pid}")
        return {"success": True, "pid": proc.pid, "data_dir": str(data_dir),
                "note": f"已用 open -n 启动新实例（建议将 {data_dir.name} 作为该实例数据目录）"}
    except Exception as e:
        return {"success": False, "pid": 0, "data_dir": str(data_dir), "note": str(e)}
