#!/usr/bin/env python3
"""Source contracts for the Spectranext 1.3.9 consumer blockers."""

from pathlib import Path
import re


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


def branch(source: str, marker: str, end: str) -> str:
    start = source.index(marker) + len(marker)
    return source[start : source.index(end, start)]


def target_and_classic(source: str, anchor: str) -> tuple[str, str]:
    anchor_pos = source.index(anchor)
    if_pos = source.rfind("#ifdef SPECTALK_SPECTRANEXT", 0, anchor_pos)
    else_pos = source.index("#else", if_pos)
    end_pos = source.index("#endif", else_pos)
    return source[if_pos:else_pos], source[else_pos:end_pos]


def init_contract() -> None:
    user_source = text("src/user_cmds.c")
    source = function_body(user_source, "static void sys_init(")
    target_socket, classic_socket = target_and_classic(source, "net_disconnect();")
    target_start, classic_start = target_and_classic(source, "main_puts(S_INIT_DOTS);")
    target_fail, classic_fail = target_and_classic(source, "ui_err(S_FAIL);")
    net_header = text("include/spectalk_net.h")
    disconnect = function_body(text("src/spectalk.c"), "void force_disconnect(void)")

    assert "net_disconnect();" in target_socket
    assert "reset_rx_state();" not in target_socket
    assert "overlay_exec" not in target_socket
    assert source.index("net_disconnect();") < source.index("result = net_init();")
    assert not re.search(r"\b(?:uart_send_line|uart_send_string|wait_for_response)\s*\(", target_socket)
    assert "S_AT_" not in target_socket
    assert "#define net_disconnect force_disconnect" in net_header
    assert "net_close();" in disconnect
    assert "reset_rx_state();" in disconnect
    assert disconnect.index("net_close();") < disconnect.index("reset_rx_state();")
    assert "uart_send_line(S_AT_CMD);" in classic_socket
    assert "uart_send_line(S_AT_CIPCLOSE);" in classic_socket
    assert "wait_for_response(S_OK, 25)" in classic_socket
    assert 'main_puts("Re-initializing ESP... ");' in classic_start
    assert 'ui_err("FAILED: no ESP response");' in classic_fail
    assert "main_puts(S_INIT_DOTS);" in target_start
    assert "main_putc(' ');" in target_start
    assert "ui_err(S_FAIL);" in target_fail
    assert "S_INIT_NETWORK" not in user_source
    assert "S_NO_NETWORK" not in user_source
    assert "connection_state = STATE_DISCONNECTED;" in source
    target_clock, classic_clock = target_and_classic(source, "clock_sync_fallback();")
    assert "clock_sync_fallback();" in target_clock
    assert "clock_init();" in classic_clock
    assert source.index("connection_state == STATE_WIFI_OK") < source.index("clock_sync_fallback();")
    assert "clock_synced = 0;" in disconnect
    assert "config_load(" not in source  # Keep the loaded/current timezone and other settings.
    retry = function_body(text("src/clock_spectranext.c"), "void clock_sync_fallback(void)")
    assert retry.index("clock_retry_frames = 0;") < retry.index("clock_fetch();")


def clock_contract() -> None:
    source = function_body(text("src/clock_spectranext.c"), "static void clock_fetch(void)")
    guard = "if (overlay_mode != OVERLAY_NONE) return;"

    assert guard in source
    assert source.index(guard) < source.index("overlay_exec(5, 0);")


def storage_message_contract() -> None:
    source = function_body(text("src/spectalk.c"), "void main(void)")
    target = branch(source, "#ifdef SPECTALK_SPECTRANEXT", "#else")
    classic = branch(source, "#else", "#endif")

    assert 'fatal_msg("REQUIRES SPECTRANEXT!")' in target
    assert "REQUIRES DIVMMC" not in target
    assert 'fatal_msg("REQUIRES DIVMMC!")' in classic


def main() -> None:
    init_contract()
    clock_contract()
    storage_message_contract()
    print("Spectranext release blockers contract OK")


if __name__ == "__main__":
    main()
