"""应用数据目录：PyInstaller 冻结后使用 exe 所在目录，开发时用项目根目录"""
import sys
from pathlib import Path


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent
