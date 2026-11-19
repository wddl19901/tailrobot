import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent.parent / "config.json"

_default_config = {
    "mode": "standard",
    "polling_strategy": "random",
    "main_account_id": "",
    "accounts": [],
    "rules": {
        "rule_one_enabled": False,
        "rule_one_threshold": 7,
        "rule_two_enabled": False,
        "rule_three_enabled": False,
        "rule_three_target_id": "",
        "rule_four_all_pick": False,
        "rule_four_no_pick": False,
    },
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return _default_config.copy()


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
