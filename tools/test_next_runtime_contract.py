#!/usr/bin/env python3
"""Lock the minimal native Next paging contract without running an emulator."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8").lower()


def section(source: str, start: str, end: str) -> str:
    first = source.index(start)
    return source[first:source.index(end, first)]


def compact(source: str) -> str:
    return " ".join(source.split())


def asm_lines(source: str) -> list[str]:
    result = []
    for raw in source.splitlines():
        code = raw.split(";", 1)[0].strip()
        if code:
            result.append(" ".join(code.split()))
    return result


def assert_asm_order(source: str, *expected: str) -> None:
    lines = asm_lines(source)
    cursor = 0
    for instruction in expected:
        instruction = " ".join(instruction.lower().split())
        try:
            cursor = lines.index(instruction, cursor) + 1
        except ValueError as exc:
            raise AssertionError(f"missing ordered instruction: {instruction}") from exc


def main() -> None:
    makefile = text("Makefile")
    gitignore = text(".gitignore")
    loader = text("asm/next_overlay_loader.asm")
    packer = text("tools/gen_next_nex.py")
    data = text("asm/next_data.asm")
    storage = text("asm/spectalk_asm/60_protocol_storage.asm")
    preamble = text("asm/spectalk_asm/00_preamble.asm")
    frames = text("asm/spectalk_asm/80_ui_runtime.asm")
    uart_drain = text("asm/spectalk_asm/40_text_numeric_screen.asm")
    next_uart = text("asm/next_uart.asm")
    clock_overlay = text("overlay/overlay_entry6.asm")
    rtc = text("overlay/rtc_seed_ovl.asm")
    rtc_entries = text("overlay/overlay_entry5.asm")
    about_entries = text("overlay/overlay_entry2.asm")
    about_render = text("overlay/earth_about_render.asm")
    source = text("src/spectalk.c")
    user_cmds = text("src/user_cmds.c")
    bookmark_sources = [text("overlay/bookmark_store_ovl.c"), text("overlay/bookmarks_ovl.c")]
    overlay_defs = text("tools/gen_overlay_defs.py")
    sys_init = section(user_cmds, "static void sys_init(", "static void cmd_theme")
    esp_init = section(source, "uint8_t esp_init(", "// time synchronization function")
    next_probe = section(esp_init, "#ifdef spectalk_next", "#else")
    startup_init = section(source, "// --- initialization ---", "// check wifi")
    required_defs = section(overlay_defs, "required_functions = [", "required_variables = [")
    optional_defs = overlay_defs[overlay_defs.index("optional_target_symbols = [") :]
    next_check = section(makefile, "next-check:", "test-spectranext-network:")
    next_all = section(makefile, "next-all:", "next-check:")
    frame_wait_drain = section(frames, "_frame_wait_drain:", "; system ram hijacking")

    assert "asm/next_uart.asm asm/next_clock.asm asm/next_data.asm" in makefile
    assert "overlay_cap = 8190" in makefile
    assert "next_raw_code = $(output)__.bin" in makefile
    assert 'test -f "$(next_raw_code)"' in makefile
    assert "overlay/*.o $(next_raw_code) $(output)_code.bin" in makefile
    assert "/spectalkzx__.bin" in gitignore
    assert "/spectalkzx_code.bin" in gitignore
    for symbol in ("_dat_open", "_dat_fread", "_dat_fseek_set", "_next_rtc_drvapi", "_next_rtc_getdate"):
        assert symbol not in required_defs and symbol in optional_defs
    assert "next_overlay_first_page equ 16" in loader
    assert "ovl_code_base           equ 0x2000" in loader
    assert "ovl_code_end            equ 0x4000" in loader
    assert "ovl_code_size_addr" in loader
    assert "ovl_code_size_addr - ovl_code_base + 1" in loader
    assert "ld de, (ovl_code_size_addr)" in loader
    assert "overlay_size_offset = page_size - overlay_size_trailer" in packer
    assert "size > overlay_max_size" in packer
    assert "len(overlay).to_bytes(2, \"little\")" in packer
    assert_asm_order(
        section(loader, "_overlay_exec:", "next_exec_return:"),
        "call ___sdcc_enter_ix", "xor a", "ld (next_overlay_page), a",
        "call _net_pump_rx", "call next_overlay_begin",
        "call next_overlay_entry", "jr c, next_exec_fail_mapped",
    )
    assert "ld l, (ix+5)" in section(loader, "_overlay_exec:", "next_exec_return:")
    assert_asm_order(
        section(loader, "next_exec_return:", "next_exec_fail_mapped:"),
        "call next_overlay_end_di", "pop ix", "pop de", "pop bc", "push de", "ret",
    )
    assert_asm_order(
        section(loader, "next_call_bad:", ";; timed overlays"),
        "call next_overlay_end_di", "ret",
    )
    assert "next_overlay_ready" not in loader
    assert "next_entry_id" not in loader
    assert_asm_order(
        section(loader, "next_overlay_entry:", ";; a=nextreg number"),
        "ld a, l", "ld c, (hl)", "cp c",
        "sla e", "rl d", "inc de", "inc de",
        "ld hl, (ovl_code_size_addr)",
        "ld bc, ovl_code_size_addr - ovl_code_base + 1",
        "sbc hl, bc", "jr nc, next_overlay_entry_bad",
        "ld hl, (ovl_code_size_addr)", "sbc hl, de",
        "jr c, next_overlay_entry_bad", "push de",
        "pop bc", "push de", "ex de, hl",
        "ld de, ovl_code_base", "sbc hl, de",
        "sbc hl, bc", "jr c, next_overlay_entry_pop_bad",
        "add hl, bc", "ld de, (ovl_code_size_addr)",
        "sbc hl, de", "jr nc, next_overlay_entry_pop_bad",
    )
    assert_asm_order(
        section(loader, "next_overlay_entry_bad:", ";; a=nextreg number"),
        "xor a", "ld (next_overlay_page), a", "scf", "ret",
    )
    overlay_begin = section(loader, "next_overlay_begin:", "_next_overlay_suspend:")
    assert_asm_order(
        overlay_begin, "di", "ld a, nextreg_mmu1", "call nextreg_read",
        "ld (next_saved_mmu1), a", "ld a, 1", "ld (_next_overlay_active), a",
        "jp _next_overlay_restore",
    )
    assert "next_saved_iff" not in loader and "ei" not in asm_lines(loader)
    assert "overlay_exec(4, 4);" not in sys_init
    assert "_esx_" not in loader and "_ring_buffer" not in loader
    assert "call _next_overlay_suspend" in frames
    assert "call _next_overlay_restore" in frames
    next_frame_wait_drain = section(frame_wait_drain, "ifdef spectalk_next", "endif")
    assert_asm_order(next_frame_wait_drain, "ld a, (_next_overlay_active)",
                     "or a", "jr z, fwd_poll", "call _frame_wait", "jp _net_pump_rx")
    assert "ei" not in asm_lines(next_frame_wait_drain)
    assert "extern __bss_user_tail" in preamble
    assert "ld hl, __bss_user_tail" in preamble
    assert "im 1" in asm_lines(section(preamble, "section code_crt_init", "bss_zero_skip:"))
    assert storage.count("call _next_overlay_suspend") >= 8
    assert storage.count("call _next_overlay_restore") >= 7
    esx_detect = storage[storage.index("esx_det_fail:") : storage.index("esx_det_end:")]
    assert "xor a" in esx_detect
    assert "ifdef spectalk_next" in esx_detect
    assert "push af" in esx_detect
    assert "call _next_overlay_restore" in esx_detect
    assert "pop af" in esx_detect
    assert esx_detect.index("xor a") < esx_detect.index("push af")
    assert esx_detect.index("push af") < esx_detect.index("call _next_overlay_restore")
    assert esx_detect.index("call _next_overlay_restore") < esx_detect.index("pop af")
    rtc_driver = storage[storage.index("_next_rtc_drvapi:"):storage.index("next_rtc_restore:")]
    assert rtc_driver.count("call _next_overlay_suspend") == 2
    assert rtc_driver.count("rst 8") == 2
    assert "call _next_rtc_drvapi" in rtc and "call _next_rtc_getdate" in rtc
    assert "public _next_esp_reset_ovl" in rtc
    assert "ld b, 25" in rtc and "ld b, 180" not in rtc
    assert "dw 6" in rtc_entries and "dw _next_esp_reset_ovl" in rtc_entries
    assert "dw _config_load_ovl" in rtc_entries
    assert "#ifdef spectalk_next int8_t sntp_tz = tz_rtc;" in compact(source)
    assert "cfg_ok = config_load();" in source
    assert "sntp_tz = tz_rtc;" not in section(source, "cfg_ok = config_load();", "apply_theme();")
    assert "overlay_exec(4, 4);" not in startup_init
    assert "wait_for_response(null, 4)" in esp_init
    assert "if (!esp_at_cmd(s_at_cipmux0)) {" in esp_init
    assert "uint8_t reset_tries = 2;" in esp_init
    assert "uint8_t wifi_probes = 0;" in esp_init
    assert esp_init.count("overlay_exec(4, 4);") == 1
    assert 'wait_for_response("ready", 251)' in esp_init
    assert "if (!reset_tries) goto esp_init_fail;" in esp_init
    assert "reset_tries--;" in esp_init
    assert "next_wifi_probe:" in esp_init
    assert "wifi_probes = 12;" in esp_init
    assert "wifi_probes--;" in esp_init
    assert "wait_drain(25);" in esp_init
    assert "goto next_wifi_probe;" in esp_init
    assert esp_init.count("in_inkey() == key_break") >= 4
    wifi_result = esp_init[esp_init.index("closed_reported = 0;") :]
    native_wifi = section(wifi_result, "#ifdef spectalk_next", "#else")
    assert "connection_state = state_wifi_ok;" in native_wifi
    assert "at+cwjap?" not in native_wifi
    assert '"0.0.0.0"' in esp_init
    assert "if (connection_state != state_wifi_ok && reset_tries) goto next_esp_reset;" not in esp_init
    assert next_probe.index("wait_for_response(null, 4)") < next_probe.index("goto next_esp_reset")
    assert 'uart_send_string("+++")' not in next_probe
    assert "resetting internal esp" not in source
    assert_asm_order(
        section(about_render, "_about_render_ovl:", "_earth_read_logo:"),
        "call _about_close_ovl",
    )
    assert_asm_order(
        section(about_render, "_about_close_ovl:", "_earth_draw_frame:"),
        "xor a", "ld (_earth_ready),a", "jp _input_cache_invalidate",
    )
    about_lines = asm_lines(about_entries)
    next_di_guard = ["ifndef spectalk_spectranext", "ifndef spectalk_next", "ei", "endif", "endif"]
    assert sum(about_lines[i:i + 5] == next_di_guard for i in range(len(about_lines) - 4)) == 2
    assert_asm_order(
        section(about_entries, "defc earth_packet_size", "defc earth_frame_count"),
        "ifdef spectalk_next", "defc earth_packet_buffer = $3dfe",
    )
    assert "drain_uart_status   equ 0x133b" in uart_drain
    assert "ifdef spectalk_next ld bc, drain_uart_status" in compact(uart_drain)
    assert "udp_uart_tx_status    = $133b" in clock_overlay
    assert "ifdef spectalk_next ld bc, udp_uart_tx_status" in compact(clock_overlay)
    assert 'mkdir -p "$(build_dir)/sys/config"' in makefile
    assert "nextreg_mmu0          equ 0x50" in data
    assert "nextreg_mmu1" not in data
    assert "next_dat_first_page   equ 24" in data
    assert "next_saved_iff" not in data and "ei" not in asm_lines(data)
    assert_asm_order(
        section(data, "next_dat_copy:", "next_dat_copy_done:"),
        "push bc", "call next_dat_window_begin", "pop bc",
    )
    assert "ld hl, (0x0000)" in data and "cp 0x20" in data
    assert_asm_order(
        section(next_uart, "next_uart_init_flush:", ";; fastcall byte"),
        "call uartread", "dec de", "ld a, d", "or e", "jr nz, next_uart_init_flush", "ret",
    )
    assert "ld de, 512" in section(next_uart, "_ay_uart_init:", ";; fastcall byte")
    assert "ret nc" not in section(next_uart, "next_uart_init_flush:", ";; fastcall byte")
    assert "uart_select_esp      equ 0x30" in next_uart
    assert "next-check: check" in next_check
    assert "test_next_runtime_contract.py" in next_check
    assert "test_bpe_transaction.py" not in next_check
    assert "$(make) --no-print-directory next-info" in next_all
    assert '[ "$(skip_check)" != "1" ]' in next_all
    assert "$(bpe_stamp)" not in next_all and "$(next_resident)" not in next_all
    assert "overlay_build nex-build next-info" not in next_all
    assert "$(next_resident): $(next_raw_code)" in compact(makefile)
    assert "$(next_resident): $(next_raw_code) $(map)" not in compact(makefile)
    assert "nex-build: overlay_build" in makefile
    assert "next-info: nex-build" in makefile
    release = makefile[makefile.index("release:\n") :]
    assert "ifeq ($(platform),next)" in release
    assert "build_profile=release max_allocs_per_node=200000 next-all" in release
    assert "scrollback" not in makefile
    assert "c:\\dev\\spectalk-next" not in makefile
    assert 'irc client for zx spectrum next";' in source
    assert 'db "spectalkzx 1.4.1: irc client for zx spectrum next",0' in text("overlay/earth_about_render.asm")
    for bookmark in bookmark_sources:
        path_fn = bookmark[bookmark.index("static const char *bm_path") : bookmark.index("static const char *bm_line")]
        native = path_fn[path_fn.index("#elif defined(spectalk_next)") : path_fn.index("#else")]
        assert "char *path = (char *)overlay_slot + bm_line_max;" in native
        assert "st_copy_n(path, bm_path, sizeof(bm_path));" in native
        assert "return path;" in native
        assert 'bm_path_alt "/sys/sptbm1.cfg"' in bookmark
        assert "esx_fopen(bm_path_alt(slot))" in bookmark
    assert "esx_replace_write(bm_path_alt(bookmark_sel))" in bookmark_sources[0]
    print("Native Next direct-overlay, DAT and ROM trampoline contract OK")


if __name__ == "__main__":
    main()
