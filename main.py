"""跨平台启动入口（仅 GUI，无命令行参数）"""
import sys
import traceback


def _global_exception_hook(exc_type, value, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, value, tb)
        return
    try:
        from wx_redpacket_helper.utils.paths import app_dir
        log_file = app_dir() / "logs" / "crash.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(traceback.format_exception(exc_type, value, tb))
            f.write("\n---\n")
    except Exception:
        pass
    sys.__excepthook__(exc_type, value, tb)


sys.excepthook = _global_exception_hook

from wx_redpacket_helper.gui.main_window import run_app


def main():
    try:
        run_app()
    except Exception:
        _global_exception_hook(*sys.exc_info())
        raise


if __name__ == "__main__":
    main()
