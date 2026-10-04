#!/usr/bin/env python3
"""
Generate overlay_defs.asm from the resident binary's .map file.
Provides PUBLIC+DEFC symbols so the overlay C code (compiled separately)
can link against resident functions and variables.

Usage: python gen_overlay_defs.py SpecTalkZX.map > build/overlay_defs.asm
"""

import re
import sys

# --- Minimal ABI surface for overlay C code ---

REQUIRED_FUNCTIONS = [
    # ABI wrappers
    "_overlay_header",
    # Rendering
    "_print_str64",
    "_print_char64",
    "_print_big_str",
    "_clear_line",
    "_clear_zone",
    "_compute_screen_base",
    "_compute_attr_base",
    "_draw_badge_dither",
    "_notif_center",
    "_input_cache_invalidate",
    # String/number utilities
    "_st_strlen",
    "_st_stricmp",
    "_st_copy_n",
    "_fast_u8_to_str",
    # esxDOS
    "_esx_fopen",
    "_esx_fread",
    "_esx_fwrite",
    "_esx_fcreate",
    "_esx_fclose",
    "_esx_fseek_set",
    # Input / frame sync used by overlays
    "_frame_wait",
    "_draw_status_bar",
    "_print_line64_fast",
    "uartRead",
    # Screen output (for save status messages and cold local commands)
    "_main_putc",
    "_main_puts",
    "_main_newline",
    "_main_print",
    "_set_attr_sys",
    "_set_attr_priv",
    "_sys_puts",
    "_sys_puts_print",
    "_notify",
    "_notify2",
    "_ui_err",
    "_ui_usage",
    "_send_identify",
    "_irc_send_cmd2",
    "_irc_send_privmsg",
    "_last_pm_nick",
    "_irc_is_away",
    "_away_message",
    "_S_AWAY_CMD",
    "_reset_rx_state",
    "_overlay_rx_release",
    "_skip_spaces",
    "_split_at_space",
    "_add_ignore",
    "_remove_ignore",
    "_is_ignored",
    "_str_to_u16",
    "_u16_to_dec",
    "_puts_u8_nolz",
    "_sw_tab_width",
    "_switcher_rebuild_map",
    "_switcher_close",
    # SDCC runtime (called implicitly by compiled C)
    "___sdcc_enter_ix",
    "____sdcc_2_copy_src_mhl_dst_deix",
    "____sdcc_4_push_hlix",
]

REQUIRED_VARIABLES = [
    # esxDOS state
    "_esx_handle",
    "_esx_buf",
    "_esx_count",
    "_esx_result",
    # Overlay state
    "_overlay_mode",
    "_help_page",
    "_config_dirty",
    "_notif_enabled",
    "_status_bar_dirty",
    "_bookmark_sel",
    "_bookmark_active_slot",
    "_bookmark_rows",
    # Buffers
    "_ring_buffer",
    "_overlay_slot",
    "_rx_last_len",
    "_rx_overflow",
    # Theme / print cursor
    "_theme_attrs",
    "_theme_raw",
    "_g_ps64_y",
    "_g_ps64_col",
    "_print_str64_char",
    "_ikkle_packed",
    # Connection state + channels (for status overlay)
    "_connection_state",
    "_channels",
    "_network_name",
    "_ping_latency",
    "_uptime_minutes",
    # Shared strings
    "_K_DAT",
    "_S_APPDESC",
    "_S_AUTOAWAY",
    "_S_SERVER",
    "_SB_MIN",
    "_SB_OFF",
    "_SB_ON",
    "_SB_RANGE_MINUTES",
    "_SB_SMART",
    "_K_NICK",
    "_K_SERVER",
    "_K_PORT",
    "_K_PASS",
    "_K_NKPASS",
    "_K_AUTOCONN",
    "_K_AUTOJOIN",
    "_K_THEME",
    "_K_AUTOAWAY",
    "_K_BEEP",
    "_K_CLICK",
    "_K_NCOLOR",
    "_K_TRAFFIC",
    "_K_TS",
    "_K_DIVIDER",
    "_K_CHANNELS",
    "_K_CFG_PRI",
    "_K_CFG_ALT",
    "_K_TZ",
    "_K_NOTIF",
    "_K_COUNTSYNC",
    "_S_ANYKEY",
    # Config variables (read-only from overlay)
    "_irc_nick",
    "_irc_server",
    "_irc_port",
    "_irc_pass",
    "_nickserv_pass",
    "_nickserv_nick",
    "_autojoin_defer_flags",
    "_auth_mode",
    "_auth_profile",
    "_has_esxdos",
    "_cfg_apply",
    "_K_AUTHCMD",
    "_K_BOOKMARK",
    "_K_NICKSERV",
    "_current_theme",
    "_current_channel_idx",
    "_beep_enabled",
    "_keyclick_enabled",
    "_nick_color_mode",
    "_show_traffic",
    "_show_channel_separators",
    "_count_sync_enabled",
    "_count_sync_idle_frames",
    "_count_sync_quits",
    "_channel_context_next_row",
    "_channel_context_pending",
    "_show_timestamps",
    "_autoconnect",
    "_autojoin",
    "_autoaway_minutes",
    "_autoaway_counter",
    "_autoaway_active",
    "_sntp_tz",
    "_sntp_tz_last",
    "_sntp_init_sent",
    "_sntp_waiting",
    "_sntp_queried",
    "_time_hour",
    "_time_minute",
    "_time_second",
    "_last_ts_hour",
    "_last_ts_minute",
    "_last_frames_lo",
    "_tick_accum",
    "_search_pattern",
    "_sw_sel",
    "_sw_first",
    "_sw_count",
    "_sw_dirty",
    "_autojoin_channels",
    "_friend_nicks",
    "_friend_count",
    "_ignore_list",
    "_ignore_count",
]

OPTIONAL_TARGET_SYMBOLS = [
    "_uart_tx_failed",
    "_next_uart_status",
    "_dat_open",
    "_dat_fread",
    "_dat_fseek_set",
    "_next_rtc_drvapi",
    "_next_rtc_getdate",
    "_spxn_resolve",
    "_spxn_rom_hlcall",
    "_spxn_rom_ixcall",
    "_spxn_rom_detect",
    "_spxn_regs",
    "_esx_funlink",
    "_esx_frename",
    "_esx_freplace",
    "_esx_commit",
    "_spxn_overlay_page",
    "_spxn_page_ready",
    "_spxn_overlay_len",
]


def parse_map(map_path):
    """Extract symbol addresses from .map file."""
    symbols = {}
    with open(map_path, "r", errors="replace") as f:
        for line in f:
            m = re.match(r"(\w+)\s+=\s+\$([0-9A-Fa-f]+)\s+;", line)
            if m:
                symbols[m.group(1)] = int(m.group(2), 16)
    return symbols


def main():
    if len(sys.argv) < 2:
        print("Usage: gen_overlay_defs.py <map_file>", file=sys.stderr)
        sys.exit(1)

    symbols = parse_map(sys.argv[1])

    print(";; AUTO-GENERATED by gen_overlay_defs.py -- DO NOT EDIT")
    print(";; Resident binary symbols for overlay linking (PUBLIC + DEFC)")
    print()

    missing = []
    required = REQUIRED_FUNCTIONS + REQUIRED_VARIABLES
    if "_spxn_overlay_page" in symbols:
        required = [name for name in required if name not in ("_cfg_apply", "uartRead")]
        required += ["_K_TZLAST", "_K_FRIENDS", "_K_IGNORES"]
    for name in required:
        if name in symbols:
            print(f"PUBLIC {name}")
            print(f"DEFC {name} = ${symbols[name]:04X}")
        else:
            missing.append(name)
            print(f";; WARNING: {name} not found in .map!")

    for name in OPTIONAL_TARGET_SYMBOLS:
        if name in symbols:
            print(f"PUBLIC {name}")
            print(f"DEFC {name} = ${symbols[name]:04X}")

    if missing:
        print(f"\n;; MISSING SYMBOLS: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
