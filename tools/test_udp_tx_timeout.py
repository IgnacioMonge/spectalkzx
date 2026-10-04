#!/usr/bin/env python3
"""Lock the bounded SPCTLK6 raw-UDP TX contract."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASM = ROOT / "overlay" / "overlay_entry6.asm"
USER_CMDS = ROOT / "src" / "user_cmds.c"


def words(text):
    code = "\n".join(line.split(";", 1)[0] for line in text.splitlines())
    return " ".join(code.split())


def block(source, start, end):
    return words(source.split(start, 1)[1].split(end, 1)[0])


def model_send(busy_polls):
    for poll in range(1, 193):
        if poll > busy_polls:
            return True, poll
    return False, 192


def main():
    source = ASM.read_text(encoding="utf-8")
    sender = block(source, "udp_uart_send:", "udp_send_string:")
    strings = block(source, "udp_send_string:", "_sntp_udp_ovl:")
    flow = block(source, "_sntp_udp_ovl:", "wait_domain:")
    close = block(source, "udp_close:", "udp_fail_dns:")
    fatal = block(source, "udp_tx_fatal:", "wait_domain:")

    assert "DEFC UDP_TX_POLL_BUDGET = $C0" in source
    assert sender.startswith("ld d, UDP_TX_POLL_BUDGET ")
    assert words("""udp_uart_wait:
        in a, (c)
        add a, a
        jp p, udp_uart_ready
        dec d
        jr nz, udp_uart_wait
        scf
        ret""") in sender
    assert words("out (c), l or a ret") in sender
    assert words("call udp_uart_send pop hl ret c inc hl") in strings

    for snippet in (
        "ld hl, cmd_cipdomain call udp_send_string jp c, udp_tx_fatal",
        "ld hl, cmd_cipstart_pfx call udp_send_string jp c, udp_tx_fatal",
        "ld hl, ip_buf call udp_send_string jp c, udp_tx_fatal",
        "ld hl, cmd_cipstart_tail call udp_send_string jp c, udp_tx_fatal",
        "ld hl, cmd_cipsend call udp_send_string jp c, udp_tx_fatal",
        "ld a, '>' call wait_char jp c, udp_tx_fatal",
        "ld l, $0B call udp_uart_send jp c, udp_tx_fatal",
        "call udp_uart_send pop de jp c, udp_tx_fatal dec d",
    ):
        assert words(snippet) in flow

    assert close.count("call udp_send_string") == 1
    assert "call udp_send_string jp c, udp_tx_fatal" in close
    assert len(re.findall(r"\b(?:jr|jp) c, udp_tx_fatal\b", words(source))) == 9
    assert "udp_fail_send" not in source

    for snippet in (
        "xor a ld (_connection_state), a",
        "ld (_sntp_init_sent), a",
        "ld (_sntp_waiting), a inc a ld (_uart_tx_failed), a ld (_status_bar_dirty), a",
        "jp _reset_rx_state",
    ):
        assert words(snippet) in fatal
    assert not re.search(r"\b(?:call udp_|out\b|cmd_)", fatal)

    connect = words(USER_CMDS.read_text(encoding="utf-8"))
    guard = "clock_sync_fallback(); if (connection_state < STATE_WIFI_OK) { ui_err(S_FAIL); goto connect_cleanup; }"
    assert words(guard) in connect
    assert source.count("call udp_uart_send") == 3
    assert source.count("call udp_send_string") == 6

    assert model_send(0) == (True, 1)
    assert model_send(191) == (True, 192)
    assert model_send(192) == (False, 192)
    print("UDP TX timeout check OK")


if __name__ == "__main__":
    main()
