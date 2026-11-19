"""跨平台启动入口（仅 GUI，无命令行参数）"""
import sys

from wx_redpacket_helper.gui.main_window import run_app


def main():
    run_app()


if __name__ == "__main__":
    main()
