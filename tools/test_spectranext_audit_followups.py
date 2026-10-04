#!/usr/bin/env python3
"""Source contracts for the Spectranext 1.3.9 audit follow-ups."""

import json
from pathlib import Path
import re

from overlay_atlas_probe import build_atlas


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="strict")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : pos + 1]
    raise AssertionError(f"unterminated function: {signature}")


def compact(source: str) -> str:
    return re.sub(r"\s+", " ", source)


def section(source: str, start: str, end: str) -> str:
    begin = source.index(start) + len(start)
    return source[begin : source.index(end, begin)]


def response_path_contract(fetch: str) -> None:
    recv_success = "if (spxn_rom_ixcall(ROM_RECVFROM) & ROM_CARRY) break;"
    length_assignment = "length = spxn_regs.bc;"
    close_call = "close_socket(fd);"
    validation = "if (length < NTP_PACKET_SIZE"
    decode = "decode_time"

    recv = fetch.index(recv_success)
    length = fetch.index(length_assignment, recv)
    close = fetch.index(close_call, length)
    validation_start = fetch.index(validation, length)
    decode_start = fetch.index(decode, validation_start)
    length_end = length + len(length_assignment)
    close_end = close + len(close_call)

    assert length_end < close < validation_start < decode_start, (
        "response receive must close before validation"
    )
    assert not fetch[length_end:close].strip(), "response close is not immediate"
    assert not fetch[close_end:validation_start].strip(), (
        "response validation must follow close"
    )


def ntp_contract() -> None:
    source = text("overlay/spectranext_clock_ovl.c")
    fetch = function_body(source, "static uint8_t fetch_utc(")
    validation_start = fetch.index("if (length < NTP_PACKET_SIZE")
    decode_start = fetch.index("decode_time", validation_start)
    validation = fetch[validation_start:decode_start]
    normalized = compact(validation)

    for check in (
        "length < NTP_PACKET_SIZE",
        "!same_host(&source, &destination)",
        "(overlay_slot[0] & 0xC0u) == 0xC0u",
        "((overlay_slot[0] & 7u) != 4u && (overlay_slot[0] & 7u) != 5u)",
        "!overlay_slot[1]",
        "overlay_slot[1] > 15u",
    ):
        assert check in normalized, f"NTP validation lost check: {check}"

    zero_field = (
        "!(overlay_slot[NTP_TX_SECONDS] | "
        "overlay_slot[NTP_TX_SECONDS + 1u] | "
        "overlay_slot[NTP_TX_SECONDS + 2u] | "
        "overlay_slot[NTP_TX_SECONDS + 3u])"
    )
    assert zero_field in normalized, "NTP zero transmit-seconds field is not rejected"
    assert validation_start < decode_start

    response_path_contract(fetch)
    recv = fetch.index("if (spxn_rom_ixcall(ROM_RECVFROM) & ROM_CARRY) break;")
    length = fetch.index("length = spxn_regs.bc;", recv)
    close = fetch.index("close_socket(fd);", length)
    mutated = fetch[:close] + fetch[close + len("close_socket(fd);") :]
    try:
        response_path_contract(mutated)
    except AssertionError as error:
        assert str(error) == "response receive must close before validation"
    else:
        raise AssertionError("deleting the response-path close was not detected")


def copt_contract() -> None:
    rules = text("src/spectalk_copt.rul")
    classic_rules = (
        (
            "_S_SP_COLON",
            "_net_sp_colon",
        ),
        (
            "_S_PRIVMSG",
            "_net_privmsg",
        ),
    )
    for payload, helper in classic_rules:
        classic = (
            f"%0ld%1hl,{payload}\n"
            "%0call%1_uart_send_string\n"
            "=\n"
            f"\tEXTERN {helper}\n"
            f"%0call%1{helper}"
        )
        assert rules.count(classic) == 1, f"Classic copt rule changed or duplicated: {payload}"

        target = (
            f"%0ld%1hl,{payload}\n"
            "%0call%1_net_send_string\n"
            "=\n"
            f"\tEXTERN {helper}\n"
            f"%0call%1{helper}"
        )
        assert rules.count(target) == 1, f"missing Spectranext copt rule: {payload}"

    asm = text("asm/spectalk_asm/80_ui_runtime.asm")
    assert "_net_sp_colon:\n    ld hl, _S_SP_COLON\n    jp _net_send_string" in asm
    assert "_net_privmsg:\n    ld hl, _S_PRIVMSG\n    jp _net_send_string" in asm

    header = text("include/spectalk_net.h")
    target, classic = section(header, "#ifdef SPECTALK_SPECTRANEXT", "#endif") .split("#else", 1)
    assert "void net_send_string(const char *text)" in target
    assert "#define net_send_string uart_send_string" in classic


def frame_wait_contract() -> None:
    net = text("src/net_spectranext.c")
    frame_wait = function_body(net, "void net_frame_wait(void)")
    assert frame_wait.index("frame_wait();") < frame_wait.index("net_pump_rx();")

    asm = text("asm/spectalk_asm/80_ui_runtime.asm")
    assert "PUBLIC _frame_wait_drain" in asm
    frame = asm.split("_frame_wait_drain:", 1)[1]
    target = section(frame, "IFDEF SPECTALK_SPECTRANEXT", "ELSE")
    assert target.index("call _frame_wait") < target.index("jp _net_pump_rx")
    classic = section(frame, "fwd_poll:", "ENDIF")
    assert "call uartRead" in classic
    assert "call _rb_push" in classic

    common = text("src/spectalk.c")
    for signature in ("uint8_t wait_for_response(", "uint8_t wait_for_prompt_char("):
        assert "frame_wait_drain();" in function_body(common, signature)
    assert "extern void frame_wait_drain(void);" in text("include/spectalk.h")

    header = text("include/spectalk_net.h")
    assert "#define net_frame_wait   frame_wait_drain" in header
    for path in ("src/user_cmds.c", "src/spectalk.c"):
        assert re.search(r"\bnet_frame_wait\s*\(", text(path)), path


def about_pump_contract() -> None:
    pump = function_body(text("src/net_spectranext.c"), "void spectranext_about_pump(void)")
    newline = pump.index("if (byte == '\\n')")
    line_end = pump.index("rx_pos = 0;", newline)
    after_reset = pump[line_end + len("rx_pos = 0;"):]
    assert after_reset.lstrip().startswith("return;"), (
        "ABOUT pump must yield after one complete LF-terminated line"
    )
    line = pump[newline:]
    assert "if (rx_overflow)" in line
    assert "parse_irc_message(rx_line);" in line


def memory_layout_contract() -> None:
    layout = text("tools/check_memory_layout.py")
    assert 'platform="classic"' in layout
    assert 'if platform == "spectranext":' in layout
    platform_arg = re.search(
        r'parser\.add_argument\(\s*"--platform".*?choices=\(([^)]*)\)',
        layout,
        re.DOTALL,
    )
    assert platform_arg
    assert set(re.findall(r'"([^"]+)"', platform_arg.group(1))) == {
        "classic", "next", "spectranext"
    }
    assert "missing all Spectranext map symbols was accepted" in layout

    makefile = text("Makefile")
    trim = section(makefile, "trim: $(TAP) $(MAP)", "# ------------------------------------------------------------\n# OVERLAY")
    assert 'check_memory_layout.py "$(MAP)" --platform "$(PLATFORM)"' in trim


def inventory_contract() -> None:
    cache = text("tools/test_esxdos_cache_contract.py")
    assert "src/storage_spectranext.c" not in cache


def save_args_contract() -> None:
    architecture = text("ARCHITECTURE.md")
    assert "A command handler must not read parser arguments in `temp_input` after starting an XFS directory transaction" in architecture
    assert "`READDIR` may overwrite that half of the scratch" in architecture

    save = function_body(text("src/user_cmds.c"), "void cmd_save(")
    marker = "(void)args;"
    marker_end = save.index(marker) + len(marker)
    assert "args" not in save[marker_end:], "cmd_save reads args after discarding them"


def overlay_paging_contract() -> None:
    makefile = text("Makefile")
    target = section(makefile, "ifeq ($(PLATFORM),spectranext)", "else")
    loader = text("asm/overlay_loader.asm")
    frame = text("asm/spectalk_asm/80_ui_runtime.asm")

    for token in ("SPXN_ROM_HELD", "OVERLAY_LOAD_ADDR = 2000",
                  "OVERLAY_CAP = 4096", "--block-size $(OVERLAY_CAP)",
                  "SPXN_BOOTSTRAP_SIZE = 256",
                  "--prefix $(BUILD_DIR)/SPXLOAD.OVL --prefix-size $(SPXN_BOOTSTRAP_SIZE)"):
        assert token in makefile
    for token in ("SPXN_BOOTSTRAP_OFFSET EQU OVL_ATLAS_HEADER_LEN",
                  "SPXN_BOOTSTRAP_LOAD_SIZE EQU OVL_ATLAS_HEADER_LEN + SPXN_BOOTSTRAP_SIZE",
                  "call _ring_buffer + SPXN_BOOTSTRAP_OFFSET",
                  "jr c, ovl_spxn_exec_fail",
                  "SPXN_SET_PAGE_B", "call ovl_spxn_pageout"):
        assert token in loader
    bootstrap = text("overlay/spxn_page_loader.asm")
    for token in ("SPXN_RESERVE_PAGE", "SPXN_STAGE_SIZE      EQU 512",
                  "SPXN_STAGE_BASE      EQU _ring_buffer + SPXN_STAGE_SIZE",
                  "ld hl, SPXN_STAGE_BASE", "call _esx_fread",
                  "ld hl, OVL_CODE_BASE"):
        assert token in bootstrap
    assert "call _esx_fopen" not in bootstrap
    assert "ld hl, _ring_buffer" in bootstrap
    assert "push af\n    call _esx_fclose\n    call _input_cache_invalidate\n    pop af" in bootstrap
    assert "_overlay_slot" not in bootstrap
    atlas = build_atlas(b"A" * 8 + b"B" * 8, [3, 4], 8, 64, b"BOOT", 8)
    assert atlas[8:16] == b"H\0\3\0K\0\4\0"
    assert atlas[64:72] == b"BOOT\0\0\0\0"
    assert atlas[72:79] == b"AAA" + b"BBBB"
    assert "-DSPXN_ROM_HELD" in target
    position = -1
    for token in ("ld (_spxn_rom_held), a", "call SPXN_PAGEOUT", "ei", "halt",
                  "di", "call SPXN_PAGEIN", "call SPXN_SET_PAGE_B",
                  "ld (_spxn_rom_held), a"):
        position = frame.index(token, position + 1)

    earth = text("overlay/overlay_entry2.asm")
    assert "DEFC EARTH_PACKET_BUFFER = _ring_buffer" in earth
    assert len(re.findall(
        r"IFNDEF SPECTALK_SPECTRANEXT\s+IFNDEF SPECTALK_NEXT\s+ei\s+ENDIF\s+ENDIF",
        earth,
    )) == 2
    read_check = section(earth, "call DATA_FREAD", "; Packet:")
    for token in ("IFDEF SPECTALK_SPECTRANEXT", "ld hl, (_esx_result)",
                  "ld de, EARTH_PACKET_SIZE", "sbc hl, de", "ELSE",
                  "ld hl, EARTH_PACKET_SIZE", "sbc hl, bc", "ENDIF"):
        assert token in read_check
    for path in ("overlay/bookmark_store_ovl.c", "overlay/bookmarks_ovl.c"):
        source = text(path)
        assert "st_copy_n((char *)ring_buffer, BM_PATH, sizeof(BM_PATH));" in source
    clock = text("overlay/spectranext_clock_ovl.c")
    staged = clock.index('st_copy_n((char *)ring_buffer, "pool.ntp.org", 16u);')
    assert staged < clock.index("spxn_resolve((const char *)ring_buffer", staged)


def overlay_storage_layout_contract() -> None:
    makefile = text("Makefile")
    ovl3 = section(makefile, 'echo "  Building SPCTLK3.OVL..."; \\', 'echo "  Building SPCTLK4.OVL..."; \\')
    ovl4 = section(makefile, 'echo "  Building SPCTLK4.OVL..."; \\', 'echo "  Building SPCTLK5.OVL..."; \\')
    assert "overlay/xfs_write_ovl.o" not in ovl3
    assert "$(filter-out spectranext,$(PLATFORM))" in ovl3
    assert ovl4.count("overlay/xfs_write_ovl.o") == 1
    assert "$(filter spectranext,$(PLATFORM)),$(BUILD_DIR)/bookmark_store_ovl.o" in ovl4

    commands = text("src/user_cmds.c")
    for token in ("#define BOOKMARK_STORE_GROUP 3", "#define BOOKMARK_APPLY_ENTRY 2",
                  "#define BOOKMARK_SAVE_ENTRY 3"):
        assert token in commands
    entry3 = text("overlay/overlay_entry3.asm")
    entry4 = text("overlay/overlay_entry4.asm")
    assert "IFDEF SPECTALK_SPECTRANEXT\n    dw 1" in entry3
    assert "IFDEF SPECTALK_SPECTRANEXT\n    dw 4" in entry4
    activate = function_body(commands, "static void bookmark_activate_current(")
    assert "overlay_exec_rx(BOOKMARK_STORE_GROUP, BOOKMARK_APPLY_ENTRY);" in activate
    assert "overlay_exec_rx(2, 1);" not in activate


def overlay_build_recipe_contract() -> None:
    makefile = text("Makefile")
    recipe = section(makefile, "_overlay_build:", "nex-build:")
    assert "overlay_build: overlay" in makefile
    assert "$(MAKE) --no-print-directory _overlay_build" in makefile
    assert "OVL_ZCC='zcc +z80" in recipe
    assert "OVL_ASM='z80asm" in recipe
    assert recipe.count("$(ZCC_EVIDENCE_FLAGS)") == 1
    assert recipe.count("$(Z80ASM_EVIDENCE_FLAGS)") == 1
    assert '@test -s "$(BUILD_DIR)/SPECTALK.OVL"' in recipe
    release = makefile[makefile.index("release:\n") :]
    assert "else ifeq ($(PLATFORM),spectranext)" in release
    assert 'test_spectranext_driver_contract.py "$(SPXN_DIR)"' in release


def port_pipeline_dedup_contract() -> None:
    makefile = text("Makefile")
    all_target = section(makefile, "all:\n", "\nhelp:")
    assert "SKIP_CHECK ?= 0" in makefile
    assert 'if [ "$(SKIP_CHECK)" != "1" ]; then $(MAKE) --no-print-directory check' in all_target

    checks = json.loads(text("packaging/spectranext/port.json"))["checks"]
    assert checks["host"] == [["make", "NO_COLOR=1", "check"]]
    assert "SKIP_CHECK=1" in checks["classic"][0]
    assert "SKIP_CHECK=1" in checks["spectranext"][0]

    port_test = text("tools/test_spectranext_port.py")
    configuration = section(port_test, "def configuration() -> None:\n", "\ndef clock() -> None:")
    assert "storage()" not in configuration
    assert "test-spectranext-configuration" in checks["configuration"][0]
    assert "test-spectranext-storage" in checks["mutable_storage"][0]


def main() -> None:
    ntp_contract()
    copt_contract()
    frame_wait_contract()
    about_pump_contract()
    memory_layout_contract()
    inventory_contract()
    save_args_contract()
    overlay_paging_contract()
    overlay_storage_layout_contract()
    overlay_build_recipe_contract()
    port_pipeline_dedup_contract()
    print("Spectranext audit follow-up contracts OK")


if __name__ == "__main__":
    main()
