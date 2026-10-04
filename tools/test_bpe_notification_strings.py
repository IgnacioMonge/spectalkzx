#!/usr/bin/env python3
"""Keep raw notification-builder fragments out of the BPE allowlist."""

from pathlib import Path

import bpe_build


ROOT = Path(__file__).resolve().parents[1]
RAW_NOTIFICATION_CONSTANTS = {
    "S_ASTERISK",
    "S_CHANNEL_WORD",
    "S_COLON_SP",
    "S_DISCONN",
    "S_IN_SP",
    "S_MODE_SP_SCR",
    "S_QUIT_SUFFIX",
    "S_SP_PAREN",
}


def main():
    handlers = (ROOT / "src" / "irc_handlers.c").read_text(encoding="utf-8")
    assert RAW_NOTIFICATION_CONSTANTS.isdisjoint(bpe_build.SAFE_CONSTANTS)
    assert all(name in handlers for name in RAW_NOTIFICATION_CONSTANTS)

    sample = " ".join(sorted(RAW_NOTIFICATION_CONSTANTS | {"S_APPNAME", "S_COPYRIGHT"}))
    patched = bpe_build.apply_sb_renames(sample)
    assert all(name in patched for name in RAW_NOTIFICATION_CONSTANTS)
    assert "SB_APPNAME" in patched and "SB_COPYRIGHT" in patched
    consumers = [*ROOT.glob("asm/**/*.asm"), ROOT / "src" / "spectalk_copt.rul"]
    consumer_text = "\n".join(path.read_text(encoding="utf-8") for path in consumers)
    assert all("_SB_" + name[2:] not in consumer_text for name in RAW_NOTIFICATION_CONSTANTS)
    assert "_S_COLON_SP" in consumer_text
    print("BPE notification boundary: raw fragments stay ASCII; render-only constants compress")


if __name__ == "__main__":
    main()
