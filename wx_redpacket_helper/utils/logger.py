import logging
import sys
from pathlib import Path

from .paths import app_dir

LOG_DIR = app_dir() / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_initialized = set()


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _initialized:
        return logger
    _initialized.add(name)

    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8", errors="replace")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    if sys.stdout is not None:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        try:
            sh.stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        logger.addHandler(sh)

    return logger


logger = get_logger("wx_redpacket_helper")
