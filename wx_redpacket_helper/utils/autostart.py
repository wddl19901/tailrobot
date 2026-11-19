"""开机自启动：Windows 写注册表 Run / macOS 写 LaunchAgents"""
import json
import platform
import subprocess
import sys
from pathlib import Path

IS_WIN = platform.system() == "Windows"

_APP_NAME = "TailRobot"


def _app_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return f"python3 {Path(__file__).parent.parent.parent / 'main.py'}"


def is_enabled() -> bool:
    if IS_WIN:
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run")
            val, _ = winreg.QueryValueEx(key, _APP_NAME)
            winreg.CloseKey(key)
            return bool(val)
        except OSError:
            return False
    plist = Path.home() / "Library" / "LaunchAgents" / f"com.tailrobot.{_APP_NAME.lower()}.plist"
    return plist.exists()


def set_enabled(enabled: bool) -> bool:
    if IS_WIN:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                             winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, _app_path())
        else:
            try:
                winreg.DeleteValue(key, _APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / f"com.tailrobot.{_APP_NAME.lower()}.plist"
    if enabled:
        content = {
            "Label": f"com.tailrobot.{_APP_NAME.lower()}",
            "ProgramArguments": _app_path().split(),
            "RunAtLoad": True,
        }
        plist.write_text(_plist_xml(content), encoding="utf-8")
        return True
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink()
    return True


def _plist_xml(content: dict) -> str:
    args = "\n".join(f"    <string>{a}</string>" for a in content["ProgramArguments"])
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{content['Label']}</string>
  <key>ProgramArguments</key>
  <array>
{args}
  </array>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
"""
