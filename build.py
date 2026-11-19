"""一键打包脚本：PyInstaller 单文件输出
Windows -> dist/TailRobot.exe
macOS   -> dist/TailRobot.app
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(__file__).parent
ENTRY = ROOT / "main.py"
DIST = ROOT / "dist"

EXTRA_PKGS = [
    "wx_redpacket_helper",
    "wx_redpacket_helper.gui",
    "wx_redpacket_helper.utils",
    "wx_redpacket_helper.security",
    "wx_redpacket_helper.billing",
    "wx_redpacket_helper.calc_engine",
    "wx_redpacket_helper.decision",
    "wx_redpacket_helper.wechat_monitor",
    "wx_redpacket_helper.executor",
]


def _pyinstaller(args):
    cmd = [sys.executable, "-m", "PyInstaller", *args]
    print("$", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


def build():
    system = platform.system()
    DIST.mkdir(exist_ok=True)
    old_exe = DIST / "TailRobot"
    if old_exe.exists():
        if old_exe.is_dir():
            shutil.rmtree(old_exe)
        else:
            old_exe.unlink()

    common = [
        "--onefile",
        "--name", "TailRobot",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--collect-submodules", "wx_redpacket_helper",
        "--hidden-import", "Crypto.Cipher",
        "--hidden-import", "Crypto.Util.Padding",
        "--hidden-import", "requests",
        "--hidden-import", "numpy",
        "--hidden-import", "mss",
        "--hidden-import", "PIL",
    ]

    if system == "Windows":
        common += [
            "--hidden-import", "win32api",
            "--hidden-import", "win32gui",
            "--hidden-import", "win32con",
            "--icon", "resources/icon.ico" if (ROOT / "resources/icon.ico").exists() else "--add-data",
        ]
        if not (ROOT / "resources/icon.ico").exists():
            common = [c for c in common if c not in ("--icon", "--add-data")]
        ret = _pyinstaller(["--icon=resources/icon.ico"] if (ROOT / "resources/icon.ico").exists() else common + [str(ENTRY)])
        _copy_ocr_models()

    elif system == "Darwin":
        ret = _pyinstaller(common + [str(ENTRY)])
        _copy_ocr_models()
    else:
        print("暂不支持在", system, "上打包")
        return 1

    if ret == 0:
        out = DIST / ("TailRobot.exe" if system == "Windows" else "TailRobot.app")
        print(f"\n打包完成: {out}")
    return ret


def _copy_ocr_models():
    """PyInstaller onefile 不会自动带 PaddleOCR 模型，需手动 copy 到 dist"""
    paddle_dir = Path.home() / ".paddocr"
    if paddle_dir.exists():
        shutil.copytree(paddle_dir, DIST / "paddleocr_models", dirs_exist_ok=True)
        print("已复制 PaddleOCR 模型到 dist/paddleocr_models")


if __name__ == "__main__":
    sys.exit(build())
