#!/usr/bin/env python3
"""Fail-closed source contracts for the Spectranext product adapters."""

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="strict")


def ordered(source: str, *needles: str) -> None:
    position = -1
    for needle in needles:
        position = source.find(needle, position + 1)
        assert position >= 0, needle


def network() -> None:
    source = text("src/net_spectranext.c")
    app_source = text("src/spectalk.c")
    makefile = text("Makefile")
    header = text("include/spectalk_net.h")

    assert "ROM_SEND" in source
    assert "NET_SEND_ZERO_BUDGET" in source and "frame_wait();" in source
    ordered(source, "flags = net_poll()", "net_recv(ring_buffer + rb_head")
    assert "SPXN_POLLHUP | SPXN_POLLNVAL" in source
    assert "uint8_t budget = 4;" in source
    assert "uint8_t budget = 64;" not in source
    assert "net_recv(&byte, 1)" in source
    ordered(source, "uint8_t budget = 4;", "net_recv(&byte, 1)")
    ordered(
        app_source,
        "#ifdef SPECTALK_SPECTRANEXT",
        'const char S_APPDESC[] = "IRC Client for Spectranext";',
        "#else",
        'const char S_APPDESC[] = "IRC Client for ZX Spectrum";',
        "#endif",
    )
    assert 'db "SPECTALKZX 1.4.1: IRC CLIENT FOR SPECTRANEXT",0' in text(
        "overlay/earth_about_render.asm"
    )
    assert "AT+" not in source and "uart_" not in source.lower()
    assert "#ifdef SPECTALK_SPECTRANEXT" in header
    assert "asm/divmmc_uart.asm" in makefile
    target = makefile.split("ifeq ($(PLATFORM),spectranext)", 1)[1].split("else", 1)[0]
    assert "asm/divmmc_uart.asm" not in target
    for driver in ("spxresolve.c", "spxn_rom.asm"):
        assert driver in target
    assert "spxn.c" not in target and "spxn_stream.c" not in target


def storage() -> None:
    source = text("asm/spectalk_asm/60_protocol_storage.asm")
    policy = source.split("; SPECTRANEXT XFS PRODUCT POLICY", 1)[1]
    makefile = text("Makefile")
    target = makefile.split("ifeq ($(PLATFORM),spectranext)", 1)[1].split("else", 1)[0]

    assert "adapters/xfs_compat.asm" in target
    assert "SPXN_XFS_STATE_BASE=0x5B80" in target
    assert "SPXN_XFS_DIR_SCRATCH=0x5CB6" in target
    assert "SPXN_XFS_SCRATCH_PRESERVE_BASE=0x5CB6" in target
    assert "SPXN_XFS_SCRATCH_PRESERVE_SIZE=128" in target
    assert "SPXN_XFS_SCRATCH_PRESERVE_BACKUP=0x5B00" in target
    crt = text("asm/spectalk_asm/00_preamble.asm")
    crt_init = crt.split("SECTION code_crt_init", 1)[1].split("SECTION code_user", 1)[0]
    assert "ld hl, _spxn_rom_held + 1" in crt_init
    assert "ld (_spxn_rom_held), a" not in crt_init
    assert "spxf.c" not in target
    assert not (ROOT / "src/storage_spectranext.c").exists()
    assert '#include "storage_spectranext.c"' not in text("src/main_build.c")
    assert 'defm "/CFG", 0' in policy
    ordered(policy, "call _spxn_rom_detect", "call _spxn_xfs_open_keep",
            "call _spxn_xfs_open_keep", "call _esx_opendir",
            "call _esx_mkdir", "call _esx_opendir", "call _esx_fclose")
    transaction = text("overlay/xfs_write_ovl.asm")
    ordered(transaction, "call _esx_freplace", "ld (xfs_write_created), a",
            "call _esx_fwrite", "call _esx_fclose", "call _esx_commit",
            "call _esx_funlink")
    assert "overlay/xfs_write_ovl.o" in makefile


def configuration() -> None:
    paths = text("src/user_cmds.c")
    assert '"/CFG/SPECTALK.CFG"' in paths
    assert '"/SYS/CONFIG/SPECTALK.CFG"' in paths
    save = text("overlay/spectalk_ovl4.c")
    assert "esx_replace_write(K_CFG_PRI)" in save
    assert "if (saved == 2) saved = esx_replace_write(K_CFG_ALT)" in save

    bookmark_store = text("overlay/bookmark_store_ovl.c")
    bookmarks = text("overlay/bookmarks_ovl.c")
    for source in (bookmark_store, bookmarks):
        assert '"/CFG/SPTBM1.CFG"' in source
        assert "#define BM_PATH_SLOT 10" in source
        assert '"/SYS/CONFIG/SPTBM1.CFG"' in source
        assert '"/SYS/SPTBM1.CFG"' in source
    assert "esx_replace_write(bm_path(bookmark_sel))" in bookmark_store
    assert "esx_funlink(bm_path(bookmark_sel))" in bookmarks


def clock() -> None:
    source = text("src/clock_spectranext.c")
    overlay = text("overlay/spectranext_clock_ovl.c")
    assert "overlay_exec(5, 0)" in source
    assert "connection_state != STATE_WIFI_OK" in source
    assert "ROM_SENDTO" in overlay and "ROM_RECVFROM" in overlay
    assert "same_host(&source, &destination)" in overlay
    assert "sntp_tz == TZ_RTC ? sntp_tz_last : sntp_tz" in overlay
    assert "frame_wait();" in overlay
    makefile = text("Makefile")
    assert "spectranext_clock_ovl.o" in makefile
    assert "ge24(remainder, 0x01u, 0x51u, 0x80u)" in overlay
    assert "ge24(remainder, 0u, 0x0Eu, 0x10u)" in overlay
    assert "ge24(remainder, 0u, 0u, 60u)" in overlay
    for stamp in (0, 59, 60, 3599, 3600, 86399, 86400,
                  0x7FFFFFFF, 0xFFFFFFFF):
        remainder = 0
        for bit in range(31, -1, -1):
            remainder = (remainder << 1) | ((stamp >> bit) & 1)
            if remainder >= 86400:
                remainder -= 86400
        assert remainder == stamp % 86400
    rtc = text("overlay/rtc_seed_ovl.asm")
    udp = text("overlay/overlay_entry6.asm")
    assert "IFDEF SPECTALK_SPECTRANEXT" in rtc
    assert "IFDEF SPECTALK_SPECTRANEXT" in udp
    assert "Z80ASM_EVIDENCE_FLAGS += $(TARGET_ASM_FLAGS)" in makefile


CHECKS = {
    "network": network,
    "storage": storage,
    "configuration": configuration,
    "clock": clock,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capability", choices=CHECKS)
    args = parser.parse_args()
    CHECKS[args.capability]()
    print(f"Spectranext {args.capability} contract OK")


if __name__ == "__main__":
    main()
