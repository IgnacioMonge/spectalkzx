#!/usr/bin/env python3
"""Lock runtime esxDOS transactions and persistent Printer-state boundaries."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_IO_COUNTS = {
    "asm/overlay_loader.asm": 9,
    "asm/spectalk_asm/60_protocol_storage.asm": 20,
    "asm/spectalk_asm/80_ui_runtime.asm": 1,
    "overlay/bookmark_store_ovl.c": 9,
    "overlay/bookmarks_ovl.c": 5,
    "overlay/earth_about_render.asm": 8,
    "overlay/overlay_entry2.asm": 2,
    "overlay/esx_write_ovl.asm": 13,
    "overlay/rtc_seed_ovl.asm": 2,
    "overlay/spxn_page_loader.asm": 3,
    "overlay/spectalk_ovl.c": 5,
    "overlay/spectalk_ovl3.c": 4,
    "overlay/spectalk_ovl4.c": 2,
    "overlay/xfs_write_ovl.asm": 3,
    "src/spectalk.c": 4,
    "src/config_load.c": 3,
}

C_IO = re.compile(r"\b(?:esx_f(?:open|create|read|write|close|seek_set|unlink|rename)|"
                  r"esx_replace_write|dat_open|"
                  r"data_(?:open|fread|close|fseek_set))\s*\(")
ASM_IO = re.compile(r"\b(?:call|jp)\s+(?:_esx_f(?:open|create|read|write|close|seek_set|unlink|rename)|"
                    r"data_f(?:read|seek)|_(?:dat_open|ovl_open|resources_release)|"
                    r"_spxn_xfs_(?:(?:open|use|release)_keep|close_active))\b", re.I)
RST8 = re.compile(r"^\s*rst\s+8\b", re.I | re.M)


def source(path):
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def words(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    code = "\n".join(line.split("//", 1)[0] for line in text.splitlines())
    return " ".join(code.split())


def block(text, start, end=None):
    result = text.split(start, 1)[1]
    return result.split(end, 1)[0] if end else result


def io_inventory():
    observed = {}
    for base in (ROOT / "src", ROOT / "asm", ROOT / "overlay"):
        for path in base.rglob("*"):
            if path.suffix.lower() not in (".c", ".asm"):
                continue
            relative = path.relative_to(ROOT).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() == ".c":
                count = sum(len(C_IO.findall(line)) for line in text.splitlines()
                            if "extern " not in line)
            else:
                count = len(ASM_IO.findall(text)) + len(RST8.findall(text))
            if count:
                observed[relative] = count
    assert observed == EXPECTED_IO_COUNTS, (observed, EXPECTED_IO_COUNTS)


def main():
    io_inventory()

    overlay_api = source("overlay/overlay_api.h")
    whatsnew_data = source("overlay/whatsnew_data.h")
    help_offset = int(re.search(r"#define BPE_HELP_OFFSET (\d+)", overlay_api).group(1))
    logo_offset = int(re.search(r"#define WN_LOGO_OFFSET (\d+)", overlay_api).group(1))
    logo_size = int(re.search(r"#define WN_LOGO_PACKED_SIZE (\d+)", whatsnew_data).group(1))
    assert help_offset == logo_offset + logo_size

    changes = [line.strip() for line in source("release/changes.txt").splitlines()
               if line.strip()]
    assert 2 <= len(changes) <= 12
    # Release wording is data; every current line must fit the renderer.
    assert max(map(len, changes)) <= 40

    persistent = words(block(source("src/spectalk.c"),
                             "char rx_line[RX_LINE_SIZE];", "uint16_t rx_pos;"))
    for declaration in (
        "char notif_buf[64]", "uint8_t names_friend_pos", "char pkt_empty[1]",
        "uint8_t plf_start_byte", "uint8_t plf_pair_count",
    ):
        assert declaration in persistent

    fixed_sources = (source("asm/spectalk_asm/00_preamble.asm") +
                     source("asm/spectalk_asm/80_ui_runtime.asm"))
    for symbol in ("_notif_buf", "_names_friend_pos", "_pkt_empty", "_plf_start_byte"):
        assert not re.search(rf"\bdefc\s+{symbol}\s*=", fixed_sources, re.I)
    renderer = (source("asm/spectalk_asm/30_rendering.asm") +
                source("asm/spectalk_asm/50_main_output.asm"))
    assert not re.search(r"(?<![_A-Za-z0-9])plf_pair_count\b", renderer)

    handlers = source("src/irc_handlers.c")
    assert "static char names_friend_buf[47];" in handlers
    assert "#define names_friend_buf notif_buf" not in handlers
    names = words(block(handlers,
                        "static void h_numeric_353", "static void h_numeric_321"))
    assert names.count("if (names_friend_pos >= sizeof(names_friend_buf)) names_friend_pos = 0") == 2
    assert "if (!overlay_mode && friend_count)" in names
    assert "names_friend_pos < sizeof(names_friend_buf) - 3" in names
    assert "names_friend_pos < sizeof(names_friend_buf) - 1" in names

    help_c = source("overlay/spectalk_ovl.c")
    help_io = words(block(help_c, "static void help_load_segment", "static uint8_t load_next_seg"))
    assert "if (!esx_handle) goto help_io_fail" in help_io
    assert "data_close(); goto help_io_fail" in help_io
    assert "data_close(); input_cache_invalidate()" in help_io
    assert "help_io_fail: input_cache_invalidate(); overlay_slot[0] = 0; overlay_mode = 0" in help_io

    whatsnew = words(block(source("overlay/spectalk_ovl3.c"),
                          "static void blit_logo", "void whatsnew_render"))
    assert "if (!esx_handle) goto finish" in whatsnew
    assert "if (!data_fseek_set(WN_LOGO_OFFSET)) goto finish_close" in whatsnew
    assert "finish_close: data_close(); finish: input_cache_invalidate()" in whatsnew

    whatsnew_render = words(block(source("overlay/spectalk_ovl3.c"),
                                  "void whatsnew_render"))
    assert "blit_logo(r + 1, 1)" in whatsnew_render
    assert "text_col = (WN_LOGO_WB + 3) * 2" in whatsnew_render
    assert "final_attr = 0x43 | (theme_attrs[TATTR_MAIN_BG] & 0x38)" in whatsnew_render
    assert "print_str64(tr, text_col, p, final_attr)" in whatsnew_render

    whatsnew_generator = words(source("tools/gen_whatsnew.py"))
    assert "threshold=160" in whatsnew_generator

    config = words(block(source("overlay/spectalk_ovl4.c"), "void save_config_ovl"))
    assert config.count("input_cache_invalidate()") == 1
    assert "if (saved == 2) saved = esx_replace_write(K_CFG_ALT)" in config
    assert "config_dirty = 0" in config
    assert "done: input_cache_invalidate(); overlay_rx_release()" in config

    store_c = source("overlay/bookmark_store_ovl.c")
    store_line = words(block(store_c, "static const char *bm_line", "static const char *bm_next_field"))
    store_save = words(block(store_c, "void bookmarks_save_ovl"))
    store_delete = words(block(store_c, "void bookmarks_delete_store_ovl"))
    assert "if (!esx_handle) esx_fopen(bm_path_alt(slot))" in store_line
    assert "if (!esx_handle) { input_cache_invalidate(); return 0; }" in store_line
    assert "esx_fclose(); input_cache_invalidate()" in store_line
    assert "if (saved == 2) saved = esx_replace_write(bm_path_alt(bookmark_sel))" in store_save
    assert store_save.find("input_cache_invalidate()", store_save.find("esx_replace_write")) >= 0
    assert "esx_count = 0" in store_delete
    assert "if (saved == 2) saved = esx_replace_write(bm_path_alt(bookmark_sel))" in store_delete
    assert "esx_funlink(bm_path_alt(bookmark_sel))" in store_delete

    bookmarks_c = source("overlay/bookmarks_ovl.c")
    bookmarks_line = words(block(bookmarks_c, "static const char *bm_line", "static uint8_t bm_server_eq"))
    bookmarks_delete = words(block(bookmarks_c, "void bookmarks_delete_ovl"))
    assert "if (!esx_handle) esx_fopen(bm_path_alt(slot))" in bookmarks_line
    assert "if (!esx_handle) { input_cache_invalidate(); return 0; }" in bookmarks_line
    assert "esx_fclose(); input_cache_invalidate()" in bookmarks_line
    assert "esx_funlink(bm_path(bookmark_sel))" in bookmarks_delete
    assert "#ifndef SPECTALK_SPECTRANEXT overlay_slot[0] = 0" in bookmarks_delete
    assert bookmarks_delete.find("input_cache_invalidate()", bookmarks_delete.find("esx_funlink")) >= 0

    user_cmds = words(source("src/user_cmds.c"))
    assert "#define BOOKMARK_DELETE_ENTRY 3" in user_cmds
    assert "overlay_exec(BOOKMARK_STORE_GROUP, BOOKMARK_DELETE_ENTRY)" in user_cmds
    assert "bookmark_render_list()" in user_cmds

    staged = words(source("overlay/esx_write_ovl.asm"))
    assert "ld hl, (_esx_count) ld a, h or l jr z, storage_write_checked" in staged

    rtc = source("overlay/rtc_seed_ovl.asm")
    rtc_top = words(block(rtc, "_rtc_seed_ovl:", "; --- esxDOS"))
    assert "ret" not in rtc_top
    assert "jr nz, rtc_seed_done" in rtc_top
    assert "jr rtc_seed_done" in rtc_top
    assert "rtc_seed_done: jp _input_cache_invalidate" in rtc_top

    earth = words(block(source("overlay/earth_about_render.asm"),
                        "_about_close_ovl:", "_earth_draw_frame:"))
    assert "call _esx_fclose" in earth
    assert "ld (_earth_ready),a jp _input_cache_invalidate" in earth
    assert "_input_cache_invalidate" not in source("overlay/overlay_entry2.asm")

    loader = words(source("asm/overlay_loader.asm"))
    assert "call _esx_fclose call _input_cache_invalidate" in loader
    assert "ovl_fail: ld hl, 0 ld (ovl_loaded_len), hl pop ix" in loader
    assert "call _overlay_exit_full" in loader
    exit_full = words(block(source("asm/spectalk_asm/10_core_helpers.asm"),
                            "_overlay_exit_full:", "; -----------------------------------------------------------------------------"))
    assert "jp _redraw_input_full" in exit_full

    primitive = words(block(source("asm/spectalk_asm/20_rx_ring_uart.asm"),
                            "_input_cache_invalidate:", "; ============================================================================="))
    assert "ld hl, _input_cache_char ld (hl), 0xFF" in primitive
    assert "ld bc, 127 ldir ret" in primitive
    fixed = source("asm/spectalk_asm/80_ui_runtime.asm")
    assert "defc _input_cache_char = 0x5B00" in fixed

    layout = source("tools/check_memory_layout.py")
    assert '"_spxn_xfs_scratch_preserve_size": 128' in layout
    assert '"_spxn_xfs_scratch_preserve_backup": 0x5B00' in layout
    assert 'symbols["_spxn_xfs_scratch_preserve_base"] ==' in layout
    assert 'symbols["_spxn_xfs_scratch_preserve_backup"] ==' in layout
    assert 'fixed["_input_cache_char"]' in layout
    assert '"XFS preserve size must remain 128B"' in layout
    assert '"XFS preserve backup no longer aliases input cache"' in layout

    generator = source("tools/gen_overlay_defs.py")
    optional = block(generator, "OPTIONAL_TARGET_SYMBOLS = [", "]")
    assert "_esx_replace_write" not in optional

    writer = source("overlay/xfs_write_ovl.asm")
    assert "_input_cache_invalidate" not in writer

    print("esxDOS and persistent Printer-state boundary check OK")


if __name__ == "__main__":
    main()
