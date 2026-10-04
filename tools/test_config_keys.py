#!/usr/bin/env python3
"""Keep the config-key enum, pointer table, and exact spellings aligned."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED = [
    ("CFGK_NICK", "K_NICK"),
    ("CFGK_NKPASS", "K_NKPASS"),
    ("CFGK_NCOLOR", "K_NCOLOR"),
    ("CFGK_NICKSERV", "K_NICKSERV"),
    ("CFGK_SERVER", "K_SERVER"),
    ("CFGK_PORT", "K_PORT"),
    ("CFGK_PASS", "K_PASS"),
    ("CFGK_THEME", "K_THEME"),
    ("CFGK_AUTOJOIN", "K_AUTOJOIN"),
    ("CFGK_AUTOCONN", "K_AUTOCONN"),
    ("CFGK_AUTOAWAY", "K_AUTOAWAY"),
    ("CFGK_FRIENDS", "K_FRIENDS"),
    ("CFGK_IGNORES", "K_IGNORES"),
    ("CFGK_CHANNELS", "K_CHANNELS"),
    ("CFGK_COUNTSYNC", "K_COUNTSYNC"),
    ("CFGK_BEEP", "K_BEEP"),
    ("CFGK_CLICK", "K_CLICK"),
    ("CFGK_TRAFFIC", "K_TRAFFIC"),
    ("CFGK_TS", "K_TS"),
    ("CFGK_TZ", "K_TZ"),
    ("CFGK_TZLAST", "K_TZLAST"),
    ("CFGK_DIVIDER", "K_DIVIDER"),
    ("CFGK_NOTIF", "K_NOTIF"),
    ("CFGK_AUTHCMD", "K_AUTHCMD"),
    ("CFGK_BOOKMARK", "K_BOOKMARK"),
]


def main():
    source = (ROOT / "src" / "config_apply.c").read_text(encoding="utf-8")
    constants_source = (ROOT / "src" / "user_cmds.c").read_text(encoding="utf-8")

    enum_block = re.search(r"enum\s*\{([^}]*(?:CFGK_NICK)[^}]*)\};", source, re.S).group(1)
    enum_names = re.findall(r"\bCFGK_[A-Z]+\b", enum_block)
    table_block = re.search(r"cfg_key_table:(.*?)__endasm", source, re.S).group(1)
    table_names = re.findall(r"\b_K_[A-Z]+\b", table_block)

    assert enum_names == [enum for enum, _ in EXPECTED]
    assert table_names == ["_" + symbol for _, symbol in EXPECTED]

    constants = dict(re.findall(r'static const char (K_[A-Z]+)\[\]\s*=\s*"([^"]+)";', constants_source))
    keys = [constants[symbol] for _, symbol in EXPECTED]
    assert len(keys) == len(EXPECTED) and len(set(keys)) == len(EXPECTED)
    assert all(key.endswith("=") for key in keys)

    def key_id(candidate):
        try:
            return [key[:-1] for key in keys].index(candidate)
        except ValueError:
            return 255

    assert [key_id(key[:-1]) for key in keys] == list(range(len(EXPECTED)))
    for collision in ("nifty", "nickpassx", "server_backup", "portal",
                      "autoconnected", "friends2", "ignores2", "tzx", "notify", "bookmarks"):
        assert key_id(collision) == 255

    print("Config key table check OK")


if __name__ == "__main__":
    main()
