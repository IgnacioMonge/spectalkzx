#!/usr/bin/env python3
"""Exercise the learned IRC authentication contract in a linked image.

HOSTPYTHON tools/test_autologin_cpu.py build/classic

The probe uses the real resident parser/config/send paths and the packed login
and /id overlays. UART, UI, and the two MOTD follow-up calls are stubbed; no
network or storage I/O is performed.
"""

import argparse
from pathlib import Path
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load, string


AUTH_LEGACY = 0
AUTH_PENDING = 1
AUTH_LEARNED = 2
AUTH_SAVE = 3

AUTOJOIN_MOTD_DONE = 0x01
AUTOJOIN_IDENT_WAIT = 0x02
AUTOJOIN_IDENT_SENT = 0x04


def target_kind(symbols):
    if ("SPECTALK_SPECTRANEXT" in symbols or
            "_spxn_overlay_page" in symbols or "_spxn_rom_held" in symbols):
        return "spectranext"
    if ("SPECTALK_NEXT" in symbols or
            "_next_overlay_page" in symbols or "_next_uart_status" in symbols):
        return "next"
    return "classic"


def overlay_entry(memory, folder, symbols, atlas_id, entry_id):
    atlas = (folder / "SPECTALK.OVL").read_bytes()
    assert atlas[:4] == b"STOA"
    pair = 8 + atlas_id * 4
    offset = int.from_bytes(atlas[pair:pair + 2], "little")
    size = int.from_bytes(atlas[pair + 2:pair + 4], "little")
    base = 0x2000 if target_kind(symbols) != "classic" else symbols["_ring_buffer"]
    memory[base:base + size] = atlas[offset:offset + size]
    assert memory[base] > entry_id
    return int.from_bytes(memory[base + 2 + entry_id * 2:base + 4 + entry_id * 2], "little")


def stub(memory, symbols, names, target=0x4300):
    for name in names:
        if name in symbols:
            jump(memory, symbols[name], target)


def net_send_block_symbol(symbols):
    for name in symbols:
        if name.endswith("net_send_block"):
            return name
    return None


def install_send_capture(memory, symbols, target=0x4300):
    name = net_send_block_symbol(symbols) or "_ay_uart_send"
    assert name in symbols, "artifact lacks a send backend"
    jump(memory, symbols[name], target)


UI_STUBS = (
    "_badge_flash_on", "_draw_status_bar", "_main_puts", "_main_print",
    "_main_putc", "_main_newline", "_set_attr_sys",
    "_set_attr_err", "_set_attr_priv", "_set_attr_chan", "_set_attr_nick",
    "_set_attr_join", "_ui_err", "_ui_usage",
    "_main_print_time_prefix", "_main_print_wrapped_clean",
    "_overlay_rx_release", "_input_cache_invalidate", "_redraw_input_full",
    "_mention_beep",
)


def auth_fixture(memory, symbols, *, mode=AUTH_PENDING, service="Auth@services.test",
                 payload="AUTH me secret"):
    sample = bytearray(memory)
    sample[symbols["_auth_mode"]] = mode
    sample[symbols["_auth_profile"]] = 0
    sample[symbols["_config_dirty"]] = 0
    sample[symbols["_connection_state"]] = 3
    sample[symbols["_autojoin_defer_flags"]] = 0
    if "_notif_enabled" in symbols:
        sample[symbols["_notif_enabled"]] = 0
    string(sample, symbols["_irc_server"], "irc.test")
    string(sample, symbols["_irc_nick"], "me")
    string(sample, symbols["_nickserv_nick"], service)
    string(sample, symbols["_nickserv_pass"], payload)
    stub(sample, symbols, UI_STUBS)
    return sample


def capture_sender():
    return """\
    push hl
    ld a,l
    ld hl,($4200)
    ld (hl),a
    inc hl
    ld ($4200),hl
    pop hl
    or a
    ret
"""


def capture_block():
    # z88dk cdecl presents net_send_block as (return, data, length).
    return """\
    ld hl,2
    add hl,sp
    ld e,(hl)
    inc hl
    ld d,(hl)
    inc hl
    ld c,(hl)
    inc hl
    ld b,(hl)
    ld hl,($4200)
cap_block_loop:
    ld a,b
    or c
    jr z,cap_block_done
    ld a,(de)
    inc de
    ld (hl),a
    inc hl
    dec bc
    jr cap_block_loop
cap_block_done:
    ld ($4200),hl
    xor a
    ret
"""


def capture_with_nop(symbols):
    capture = capture_block() if net_send_block_symbol(symbols) else capture_sender()
    return capture + "    defs $4320-$,0\n    ret\n"


def captured(result):
    end = int.from_bytes(result[0x4200:0x4202], "little")
    return bytes(result[0x5500:end])


def send_modes(symbols, memory, directory, cpu):
    cases = (
        (AUTH_LEGACY, "", "secret", b"PRIVMSG NickServ :IDENTIFY secret\r\n"),
        (AUTH_LEGACY, "Auth", "secret", b"PRIVMSG Auth :IDENTIFY secret\r\n"),
        (AUTH_LEARNED, "Auth@services.test", "AUTH me secret",
         b"PRIVMSG Auth@services.test :AUTH me secret\r\n"),
        (AUTH_SAVE, "Auth@services.test", "AUTH me secret",
         b"PRIVMSG Auth@services.test :AUTH me secret\r\n"),
        (AUTH_PENDING, "Auth@services.test", "AUTH me secret", b""),
    )
    for mode, service, password, expected in cases:
        sample = auth_fixture(memory, symbols, mode=mode, service=service,
                              payload=password)
        sample[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 64] = b"\0" * 64
        string(sample, symbols["_nickserv_nick"], service)
        string(sample, 0x5000, password)
        stub(sample, symbols, UI_STUBS, 0x4320)
        install_send_capture(sample, symbols)
        result = execute(sample,
                         f"ld hl,$5500\nld ($4200),hl\nld hl,$5000\ncall {symbols['_send_identify']}",
                         capture_with_nop(symbols), directory, cpu)
        assert captured(result) == expected, (mode, service, captured(result))
        abi(result)
    print("Auth send: legacy default, custom service, learned payload, and pending suppression OK")


def login_overlay(symbols, memory, folder, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="old", payload="oldpass")
    entry = overlay_entry(sample, folder, symbols, 0, 4)
    string(sample, symbols["_overlay_slot"], "Auth@services.test AUTH me secret")
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    body = f"ld hl,$5500\nld ($4200),hl\ncall {entry}"
    result = execute(sample, body, capture_with_nop(symbols), directory, cpu)
    assert captured(result) == b"PRIVMSG Auth@services.test :AUTH me secret\r\n"
    assert result[symbols["_auth_mode"]] == AUTH_PENDING
    assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 20].split(b"\0", 1)[0] == b"Auth@services.test"
    assert result[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 64].split(b"\0", 1)[0] == b"AUTH me secret"
    abi(result)
    print("/login: overlay 1 entry 4 preserves qualified destination and exact payload order")


def login_validation(symbols, memory, folder, directory, cpu):
    rejected = (
        ("Auth:foo AUTH me secret", "colon-service"),
        ("Auth|foo AUTH me secret", "pipe-service"),
        ("Auth,Other AUTH me secret", "comma-service"),
        ("#room AUTH me secret", "channel-service"),
        ("Auth AUTH|me secret", "pipe-payload"),
        ("A" * 32 + " AUTH me secret", "oversized-service"),
        ("Auth " + "X" * 64, "oversized-payload"),
    )
    for candidate, label in rejected:
        sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                              service="kept", payload="keptpass")
        entry = overlay_entry(sample, folder, symbols, 0, 4)
        sample[symbols["_config_dirty"]] = 7
        string(sample, symbols["_overlay_slot"], candidate)
        stub(sample, symbols, UI_STUBS, 0x4320)
        install_send_capture(sample, symbols)
        result = execute(sample, f"ld hl,$5500\nld ($4200),hl\ncall {entry}",
                         capture_with_nop(symbols), directory, cpu)
        assert captured(result) == b"", label
        assert result[symbols["_auth_mode"]] == AUTH_LEGACY, label
        assert result[symbols["_config_dirty"]] == 7, label
        assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 32].split(b"\0", 1)[0] == b"kept"
        assert result[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 64].split(b"\0", 1)[0] == b"keptpass"
        abi(result)

    service = "S" * 31
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="kept", payload="keptpass")
    entry = overlay_entry(sample, folder, symbols, 0, 4)
    string(sample, symbols["_overlay_slot"], service + " AUTH me secret")
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    result = execute(sample, f"ld hl,$5500\nld ($4200),hl\ncall {entry}",
                     capture_with_nop(symbols), directory, cpu)
    assert captured(result) == (b"PRIVMSG " + service.encode() +
                                b" :AUTH me secret\r\n")
    assert result[symbols["_auth_mode"]] == AUTH_PENDING
    assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 32].split(b"\0", 1)[0] == service.encode()
    abi(result)
    print("/login: invalid destinations and oversized candidates reject without sending or changing auth; a 31-character service is accepted")


def id_overlay(symbols, memory, folder, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_LEARNED,
                          service="Auth@services.test", payload="AUTH me secret")
    entry = overlay_entry(sample, folder, symbols, 6, 5)
    sample[symbols["_overlay_slot"]:symbols["_overlay_slot"] + 8] = b"secret\0\0"
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    result = execute(sample, f"ld hl,$5500\nld ($4200),hl\ncall {entry}", capture_with_nop(symbols), directory, cpu)
    assert captured(result) == b"PRIVMSG Auth@services.test :IDENTIFY secret\r\n"
    assert result[symbols["_auth_mode"]] == AUTH_LEGACY
    assert result[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 24].split(b"\0", 1)[0] == b"secret"
    abi(result)
    print("/id: overlay 7 entry 5 retains the legacy IDENTIFY shortcut")


def id_overlay_long_payload(symbols, memory, folder, directory, cpu):
    payload = "X" * 127
    sample = auth_fixture(memory, symbols, mode=AUTH_LEARNED,
                          service="Auth@services.test", payload="stored")
    entry = overlay_entry(sample, folder, symbols, 6, 5)
    string(sample, symbols["_overlay_slot"], payload)
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    result = execute(sample, f"ld hl,$5500\nld ($4200),hl\ncall {entry}", capture_with_nop(symbols), directory, cpu)
    expected = b"PRIVMSG Auth@services.test :IDENTIFY " + payload.encode() + b"\r\n"
    assert captured(result) == expected
    abi(result)
    print("/id: a 127-character payload is sent in full without truncation")


def id_resident_wrapper(symbols, memory, directory, cpu):
    payload = "Y" * 127
    sample = auth_fixture(memory, symbols, mode=AUTH_LEARNED,
                          service="Auth@services.test", payload="stored")
    sample[symbols["_connection_state"]] = 3
    sample[symbols["_rx_pos"]:symbols["_rx_pos"] + 2] = b"\0\0"
    string(sample, 0x5000, payload)
    stub(sample, symbols, UI_STUBS, 0x4320)
    jump(sample, symbols["_overlay_exec"], 0x4300)
    if "_net_pump_rx" in symbols:
        jump(sample, symbols["_net_pump_rx"], 0x4320)
    extra = """\
    pop bc
    pop de
    push bc
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
"""
    result = execute(sample,
                     f"xor a\nld ($4200),a\nld hl,$5000\ncall {symbols['_cmd_id']}",
                     extra, directory, cpu)
    assert result[0x4200] == 1, "resident /id wrapper did not dispatch overlay entry"
    assert result[symbols["_overlay_slot"]:symbols["_overlay_slot"] + 127] == payload.encode()
    assert result[symbols["_overlay_slot"] + 127] == 0
    abi(result)
    print("Resident /id wrapper: 127-character input reaches overlay_slot intact")


def notice_gate(symbols, memory, directory, cpu):
    positive = (
        "now identified", "now logged in", "password accepted",
        "authentication successful", "successfully identified",
    )
    for phrase in positive:
        sample = auth_fixture(memory, symbols)
        string(sample, 0x5000, f":Auth!u@host NOTICE me :{phrase}")
        jump(sample, symbols["_send_identify"], 0x4300)
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         "ret", directory, cpu)
        assert result[symbols["_auth_mode"]] == AUTH_SAVE, phrase
        assert result[symbols["_config_dirty"]] == 1, phrase
        assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 20].split(b"\0", 1)[0] == b"Auth@services.test"
        abi(result)

    rejected = (
        (":EvilServ!u@host NOTICE me :now identified", "sender"),
        (":Auth!u@host NOTICE #room :now identified", "target"),
        (":Auth!u@host PRIVMSG me :now identified", "command"),
        (":Auth!u@host NOTICE me :not identified", "negative"),
        (":Auth!u@host NOTICE me :password rejected", "no-success"),
        (":Auth!u@host NOTICE me :unsuccessfully identified", "embedded-success"),
        (":Auth!u@host NOTICE me :authentication successfully failed", "embedded-success-2"),
        (":Auth!u@host NOTICE @#room :now identified", "channel"),
    )
    for line, label in rejected:
        sample = auth_fixture(memory, symbols)
        string(sample, 0x5000, line)
        jump(sample, symbols["_send_identify"], 0x4300)
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         "ret", directory, cpu)
        assert result[symbols["_auth_mode"]] == AUTH_PENDING, label
        assert result[symbols["_config_dirty"]] == 0, label
        abi(result)
    for mode in (AUTH_LEGACY, AUTH_LEARNED, AUTH_PENDING):
        sample = auth_fixture(memory, symbols, mode=mode)
        sample[symbols["_autojoin_defer_flags"]] = AUTOJOIN_IDENT_SENT | AUTOJOIN_IDENT_WAIT
        string(sample, 0x5000, ":Auth!u@host NOTICE me :already identified")
        stub(sample, symbols, UI_STUBS, 0x4320)
        jump(sample, symbols["_send_identify"], 0x4300)
        result = execute(
            sample,
            f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
            """\
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
""",
            directory, cpu)
        assert result[symbols["_auth_mode"]] == mode
        assert result[symbols["_config_dirty"]] == 0
        assert not (result[symbols["_autojoin_defer_flags"]] & AUTOJOIN_IDENT_WAIT), (mode, hex(result[symbols["_autojoin_defer_flags"]]))
        assert result[0x4200] == 0, (
            "already identified sent", mode,
            result[symbols["_auth_mode"]],
            result[symbols["_config_dirty"]],
            hex(result[symbols["_autojoin_defer_flags"]]),
        )
        abi(result)
    print("Auth notice: positive confirmation is private-service gated; already-identified clears autojoin only and never learns/sends")


def numeric_900(symbols, memory, directory, cpu):
    for nick, expected in (("other", AUTH_PENDING), ("me", AUTH_SAVE)):
        sample = auth_fixture(memory, symbols)
        string(sample, 0x5000, f":irc.test 900 {nick} account :You are now logged in")
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         "ret", directory, cpu)
        assert result[symbols["_auth_mode"]] == expected, nick
        abi(result)
    print("RPL_LOGGEDIN 900: only the current nick can confirm the pending login")


def motd_replay(symbols, memory, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_LEARNED,
                          service="Auth@services.test", payload="AUTH me secret")
    sample[symbols["_autojoin_defer_flags"]] = 0
    sample[symbols["_autojoin"]] = 1
    sample[0x4200] = 0
    stub(sample, symbols, ("_send_identify",))
    stub(sample, symbols, ("_session_autojoin_try", "_irc_check_friends_online"), 0x4320)
    result = execute(sample,
                     f"xor a\nld ($4200),a\ncall {symbols['_h_motd_done']}\ncall {symbols['_h_motd_done']}",
                     "ld a,($4200)\ninc a\nld ($4200),a\nret\n    defs $4320-$,0\n    ret",
                     directory, cpu)
    assert result[0x4200] == 1, "learned payload was replayed more than once"
    assert result[symbols["_autojoin_defer_flags"]] & AUTOJOIN_MOTD_DONE
    assert result[symbols["_autojoin_defer_flags"]] & AUTOJOIN_IDENT_WAIT
    assert result[symbols["_autojoin_defer_flags"]] & AUTOJOIN_IDENT_SENT
    abi(result)
    print("MOTD: learned full payload is replayed once and guarded by IDENT_SENT")


def login_confirm_before_motd(symbols, memory, folder, directory, cpu):
    """A confirmed explicit login must not be replayed by the first MOTD."""
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="old", payload="oldpass")
    sample[symbols["_autojoin"]] = 1
    entry = overlay_entry(sample, folder, symbols, 0, 4)
    string(sample, symbols["_overlay_slot"],
           "Auth@services.test AUTH me secret")
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    logged_in = bytearray(execute(sample,
                                  f"ld hl,$5500\nld ($4200),hl\ncall {entry}",
                                  capture_with_nop(symbols), directory, cpu))
    flags = logged_in[symbols["_autojoin_defer_flags"]]
    assert logged_in[symbols["_auth_mode"]] == AUTH_PENDING
    assert flags & AUTOJOIN_IDENT_SENT, hex(flags)
    assert flags & AUTOJOIN_IDENT_WAIT, hex(flags)

    string(logged_in, 0x5000,
           ":Auth!u@host NOTICE me :now identified")
    jump(logged_in, symbols["_send_identify"], 0x4300)
    logged_in[0x4200:0x4202] = b"\0\0"
    confirmed = bytearray(execute(
        logged_in,
        f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
        "ret", directory, cpu))
    assert confirmed[symbols["_auth_mode"]] == AUTH_SAVE
    confirmed_flags = confirmed[symbols["_autojoin_defer_flags"]]
    assert confirmed_flags & AUTOJOIN_IDENT_SENT
    assert not (confirmed_flags & AUTOJOIN_IDENT_WAIT)

    logged_in = confirmed
    stub(logged_in, symbols,
         ("_session_autojoin_try", "_irc_check_friends_online"), 0x4320)
    result = execute(
        logged_in,
        f"call {symbols['_h_motd_done']}",
        """\
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
""",
        directory, cpu)
    assert result[symbols["_auth_mode"]] == AUTH_SAVE
    flags = result[symbols["_autojoin_defer_flags"]]
    assert flags & AUTOJOIN_MOTD_DONE
    assert flags & AUTOJOIN_IDENT_SENT
    assert not (flags & AUTOJOIN_IDENT_WAIT)
    assert result[0x4200] == 0, "pre-MOTD confirmation replayed identify"
    abi(result)
    print("/login: autojoin arms SENT/WAIT; NOTICE confirmation before MOTD prevents replay")


def login_pending_guard(symbols, memory, folder, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="old", payload="oldpass")
    entry = overlay_entry(sample, folder, symbols, 0, 4)
    string(sample, symbols["_overlay_slot"],
           "Auth@services.test AUTH me secret")
    stub(sample, symbols, UI_STUBS, 0x4320)
    install_send_capture(sample, symbols)
    pending = bytearray(execute(
        sample,
        f"ld hl,$5500\nld ($4200),hl\ncall {entry}",
        capture_with_nop(symbols), directory, cpu))
    assert captured(pending) == b"PRIVMSG Auth@services.test :AUTH me secret\r\n"
    assert pending[symbols["_auth_mode"]] == AUTH_PENDING
    saved_service = bytes(pending[symbols["_nickserv_nick"]:
                                  symbols["_nickserv_nick"] + 32])
    saved_payload = bytes(pending[symbols["_nickserv_pass"]:
                                  symbols["_nickserv_pass"] + 64])

    string(pending, symbols["_overlay_slot"],
           "OtherServ OTHER me replacement")
    pending[0x4200:0x4202] = b"\0\0"
    result = execute(
        pending,
        f"call {entry}",
        """\
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
""",
        directory, cpu)
    assert result[symbols["_auth_mode"]] == AUTH_PENDING
    assert result[symbols["_nickserv_nick"]:
                  symbols["_nickserv_nick"] + 32] == saved_service
    assert result[symbols["_nickserv_pass"]:
                  symbols["_nickserv_pass"] + 64] == saved_payload
    assert result[symbols["_config_dirty"]] == 0
    assert result[0x4200] == 0, "pending /login emitted a replacement command"
    abi(result)
    print("/login: a pending candidate cannot be replaced or retransmitted")


def pending_disconnect(symbols, memory, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_PENDING,
                          service="Auth@services.test", payload="AUTH me secret")
    sample[symbols["_config_dirty"]] = 9
    sample[symbols["_disconnecting_in_progress"]] = 0
    close_name = "_net_close" if "_net_close" in symbols else "_classic_net_close"
    jump(sample, symbols[close_name], 0x4320)
    jump(sample, symbols["_notif_cancel_current"], 0x4320)
    result = execute(sample, f"call {symbols['_force_disconnect']}",
                     "ret\n    defs $4320-$,0\n    ret", directory, cpu)
    assert result[symbols["_auth_mode"]] == AUTH_LEGACY
    assert result[symbols["_nickserv_nick"]] == 0
    assert result[symbols["_nickserv_pass"]] == 0
    assert result[symbols["_autojoin_defer_flags"]] == 0
    assert result[symbols["_config_dirty"]] == 9
    abi(result)
    print("Disconnect: pending candidate is cleared in RAM without persistence")


def cfg_roundtrip(symbols, memory, directory, cpu):
    if target_kind(symbols) == "spectranext":
        # cfg_apply is private to SPCTLK5; the config-load probe below executes it.
        return
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="old", payload="oldpass")
    string(sample, 0x5000, "authcmd")
    string(sample, 0x5020, "AUTH me secret")
    body = f"ld hl,$5020\npush hl\nld hl,$5000\npush hl\ncall {symbols['_cfg_apply']}"
    string(sample, 0x5060, "nickserv")
    string(sample, 0x5080, "Auth@services.test")
    body += f"\nld hl,$5080\npush hl\nld hl,$5060\npush hl\ncall {symbols['_cfg_apply']}"
    result = execute(sample, body, "ret", directory, cpu)
    assert result[symbols["_auth_mode"]] == AUTH_LEARNED
    assert result[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 64].split(b"\0", 1)[0] == b"AUTH me secret"
    assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 32].split(b"\0", 1)[0] == b"Auth@services.test"
    abi(result)
    print("Config: authcmd= payload and qualified nickserv= round-trip through cfg_apply")


def load_config_fixture(symbols, memory, folder, directory, cpu, config):
    """Execute the actual cold parser with only filesystem/UI calls stubbed."""
    sample = auth_fixture(memory, symbols, mode=AUTH_LEGACY,
                          service="old", payload="oldpass")
    sample[symbols["_has_esxdos"]] = 1
    string(sample, symbols["_irc_server"], "old.server")
    string(sample, symbols["_irc_port"], "6667")
    string(sample, 0x5000, config)
    stub(sample, symbols, UI_STUBS, 0x4320)
    jump(sample, symbols["_esx_fopen"], 0x4300)
    jump(sample, symbols["_esx_fread"], 0x4380)
    jump(sample, symbols["_esx_fclose"], 0x43E0)
    extra = f"""\
    ld a,1
    ld ({symbols['_esx_handle']}),a
    ret
    defs $4380-$,0
    ld hl,$5000
    ld de,({symbols['_esx_buf']})
    ld bc,{len(config)}
    ldir
    ld hl,{len(config)}
    ld ({symbols['_esx_result']}),hl
    ret
    defs $43E0-$,0
    ret
"""
    kind = target_kind(symbols)
    if kind == "classic":
        body = f"call {symbols['_config_load']}\nld ($4200),hl"
    else:
        entry_id = 5 if kind == "next" else 4
        entry = overlay_entry(sample, folder, symbols, 4, entry_id)
        body = f"call {entry}"
    result = execute(sample, body, extra, directory, cpu)
    if kind == "classic":
        assert result[0x4200] & 0xFF == 1
    else:
        assert result[symbols["_overlay_slot"]] == 1
    abi(result)
    return bytearray(result)


def config_load_roundtrip(symbols, memory, folder, directory, cpu):
    config = ("server=irc.learned.test\n"
              "port=6697\n"
              "authcmd=AUTH LOGIN me secret\n"
              "nickserv=Auth@services.test\n")
    result = load_config_fixture(symbols, memory, folder, directory, cpu, config)
    assert result[symbols["_auth_mode"]] == AUTH_LEARNED
    assert result[symbols["_irc_server"]:symbols["_irc_server"] + 32].split(b"\0", 1)[0] == b"irc.learned.test"
    assert result[symbols["_irc_port"]:symbols["_irc_port"] + 6].split(b"\0", 1)[0] == b"6697"
    assert result[symbols["_nickserv_pass"]:symbols["_nickserv_pass"] + 64].split(b"\0", 1)[0] == b"AUTH LOGIN me secret"
    assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + 32].split(b"\0", 1)[0] == b"Auth@services.test"
    abi(result)
    print("Config load: real esxDOS read parses server/port/authcmd/nickserv on " + target_kind(symbols))


def serializer_roundtrip(symbols, memory, folder, directory, cpu):
    if target_kind(symbols) == "spectranext":
        print("Serializer: SP has no esxDOS writer fixture; storage coverage deferred")
        return
    from test_storage_commit_cpu import run_writer

    service = "Auth@services.test"
    payload = "AUTH LOGIN me secret"
    seeded = bytearray(memory)
    seeded[symbols["_auth_mode"]] = AUTH_LEARNED
    string(seeded, symbols["_nickserv_nick"], service)
    string(seeded, symbols["_nickserv_pass"], payload)
    config_result = run_writer(symbols, seeded, folder, cpu, (3, 1), 0, directory)
    config_count = int.from_bytes(config_result[symbols["_esx_count"]:symbols["_esx_count"] + 2], "little")
    config_data = bytes(config_result[symbols["_overlay_slot"]:symbols["_overlay_slot"] + config_count])
    assert b"authcmd=" + payload.encode() + b"\r\n" in config_data
    assert b"nickserv=" + service.encode() + b"\r\n" in config_data
    assert b"nick pass=" not in config_data
    assert b"bookmark=1\r\n" in config_data

    bookmark_result = run_writer(symbols, seeded, folder, cpu,
                                 (2, 2), 0, directory)
    bookmark_count = int.from_bytes(bookmark_result[symbols["_esx_count"]:symbols["_esx_count"] + 2], "little")
    bookmark_data = bytes(bookmark_result[symbols["_overlay_slot"]:symbols["_overlay_slot"] + bookmark_count])
    assert bookmark_data[0] == 1, "successful bookmark writer marker was lost"
    expected_tail = (service + "|" + payload + "|2\n").encode()
    assert bookmark_data[1:].endswith(expected_tail[1:])
    print("Serializer: learned config and bookmark records retain qualified service, full payload and mode 2")


def bookmark_config_roundtrip(symbols, memory, folder, directory, cpu):
    """Real config serializer/parser with mocked filesystem calls."""
    kind = target_kind(symbols)
    for marker in (0, 1, 129, 128, 0x41, 0xC1):
        sample = auth_fixture(memory, symbols, mode=AUTH_LEARNED)
        sample[symbols["_bookmark_active_slot"]] = marker
        sample[symbols["_autoconnect"]] = 1
        sample[symbols["_autojoin"]] = 0
        sample[symbols["_config_dirty"]] = 1
        sample[symbols["_overlay_mode"]] = 6
        entry = overlay_entry(sample, folder, symbols, 3, 1)
        stub(sample, symbols, UI_STUBS, 0x43E0)
        if kind == "spectranext":
            jump(sample, symbols["_esx_freplace"], 0x4300)
            jump(sample, symbols["_esx_fwrite"], 0x4340)
            jump(sample, symbols["_esx_fclose"], 0x4380)
            extra = f"""\
    ld a,1
    ld ({symbols['_esx_handle']}),a
    ld hl,1
    ld ({symbols['_esx_result']}),hl
    ret
    defs $4340-$,0
    ld hl,({symbols['_esx_count']})
    ld ({symbols['_esx_result']}),hl
    ret
    defs $4380-$,0
    ld l,0
    ret
    defs $43E0-$,0
    ret
"""
        else:
            # The staged writer is private to the overlay. Exercise it using
            # the existing esxDOS firmware fixture, without a resident symbol.
            from test_storage_commit_cpu import (ALT_MARK, ALT_PRESENT,
                BAK_MARK, BAK_PRESENT, FAULT, FIRMWARE, ORIG_MARK,
                ORIG_PRESENT, stub_ui)
            stub_ui(sample, symbols)
            jump(sample, 8, 0x4300)
            for address, value in ((ORIG_PRESENT, 1), (ORIG_MARK, ord("O")),
                    (ALT_PRESENT, 1), (ALT_MARK, ord("A")), (BAK_PRESENT, 0),
                    (BAK_MARK, ord("R")), (FAULT, 0)):
                sample[address] = value
            if kind == "next":
                sample[symbols["_next_overlay_active"]] = 1
                sample[symbols["next_saved_mmu1"]] = 0xFF
                sample[symbols["next_overlay_page"]] = 0xFF
            extra = FIRMWARE
        result = execute(sample, f"call {entry}", extra, directory, cpu)
        count = int.from_bytes(result[symbols["_esx_count"]:symbols["_esx_count"] + 2], "little")
        assert 0 < count <= 512, marker
        data = bytes(result[symbols["_overlay_slot"]:symbols["_overlay_slot"] + count])
        expected_marker = 0 if marker & 0x40 else marker
        if not marker or marker & 0x40:
            assert b"bookmark=" not in data, (marker, "legacy/visual inference persisted")
        else:
            assert f"bookmark={marker}\r\n".encode() in data, (marker, data)
        assert b"autoconnect=1\r\n" in data and b"autojoin=0\r\n" in data, marker
        assert result[symbols["_bookmark_active_slot"]] == marker
        assert result[symbols["_autoconnect"]] == 1
        assert result[symbols["_autojoin"]] == 0
        assert result[symbols["_config_dirty"]] == 0
        abi(result)
        loaded = load_config_fixture(symbols, memory, folder, directory, cpu, data.decode())
        assert loaded[symbols["_bookmark_active_slot"]] == expected_marker, marker
        assert loaded[symbols["_autoconnect"]] == 1 and loaded[symbols["_autojoin"]] == 0
    print("Config bookmark roundtrip: explicit markers persist; inferred UI markers omitted; live flags unchanged on " + kind)


def bookmark_reader(sample, symbols, line):
    if line is None:
        jump(sample, symbols["_esx_fopen"], 0x4300)
        return f"""\
    xor a
    ld ({symbols['_esx_handle']}),a
    ret
    defs $43E0-$,0
    ret
"""
    string(sample, 0x5000, line)
    jump(sample, symbols["_esx_fopen"], 0x4300)
    jump(sample, symbols["_esx_fread"], 0x4380)
    jump(sample, symbols["_esx_fclose"], 0x43E0)
    return f"""\
    ld a,1
    ld ({symbols['_esx_handle']}),a
    ret
    defs $4380-$,0
    ld hl,$5000
    ld de,({symbols['_esx_buf']})
    ld bc,{len(line)}
    ld a,b
    or c
    jr z,bookmark_reader_empty
    ldir
bookmark_reader_empty:
    inc de
    ld a,$A5
    ld (de),a
    inc de
    ld a,$5A
    ld (de),a
    ld hl,{len(line)}
    ld ({symbols['_esx_result']}),hl
    ret
    defs $43E0-$,0
    ret
"""


def bookmark_apply(symbols, memory, folder, directory, cpu, line, *,
                   seed_mode=AUTH_LEARNED):
    atlas_id = 3 if target_kind(symbols) == "spectranext" else 2
    sample = auth_fixture(memory, symbols, mode=seed_mode,
                          service="Auth@services.test", payload="AUTH me secret")
    sample[symbols["_bookmark_sel"]] = 0
    sample[symbols["_overlay_slot"]] = 0
    entry_id = 2 if target_kind(symbols) == "spectranext" else 1
    entry = overlay_entry(sample, folder, symbols, atlas_id, entry_id)
    return execute(sample, f"call {entry}", bookmark_reader(sample, symbols, line),
                   directory, cpu)


def old_bookmark(symbols, memory, folder, directory, cpu):
    line = "irc.other.test|6697|serverpass|#retro\n"
    for mode in (AUTH_LEGACY, AUTH_PENDING, AUTH_LEARNED, AUTH_SAVE):
        result = bookmark_apply(symbols, memory, folder, directory, cpu, line,
                                seed_mode=mode)
        assert result[symbols["_overlay_slot"]] == 1, mode
        assert result[symbols["_auth_mode"]] == AUTH_LEGACY, mode
        assert result[symbols["_auth_profile"]] == 1, mode
        assert result[symbols["_nickserv_nick"]] == 0, (mode, "inherited service")
        assert result[symbols["_nickserv_pass"]] == 0, (mode, "inherited password")
        for name, value, size in (
            ("_irc_server", "irc.other.test", 32), ("_irc_port", "6697", 6),
            ("_irc_pass", "serverpass", 24), ("_autojoin_channels", "#retro", 64),
        ):
            assert result[symbols[name]:symbols[name] + size].split(b"\0", 1)[0] == value.encode(), (mode, name)
        canary = symbols["_overlay_slot"] + len(line)
        assert result[canary:canary + 3] == b"\0\xA5\x5A", mode
        abi(result)
    print("Bookmarks: four-field records clear inherited auth in every mode when changing server")


def bookmark_bounds(symbols, memory, folder, directory, cpu):
    fields = ("S" * 31, "1" * 5, "P" * 23, "C" * 63,
              "N" * 31, "A" * 63)
    line = "|".join(fields) + "|2\n"
    result = bookmark_apply(symbols, memory, folder, directory, cpu, line)
    assert result[symbols["_overlay_slot"]] == 1
    assert result[symbols["_auth_mode"]] == AUTH_LEARNED
    for name, value, size in (
        ("_irc_server", fields[0], 32), ("_irc_port", fields[1], 6),
        ("_irc_pass", fields[2], 24), ("_autojoin_channels", fields[3], 64),
        ("_nickserv_nick", fields[4], 32), ("_nickserv_pass", fields[5], 64),
    ):
        assert result[symbols[name]:symbols[name] + size - 1].split(b"\0", 1)[0] == value.encode()
        assert result[symbols[name] + size - 1] == 0
    assert result[symbols["_search_pattern"]:symbols["_search_pattern"] + 63].split(b"\0", 1)[0] == fields[3].encode()
    canary = symbols["_overlay_slot"] + len(line)
    assert result[canary] == 0
    assert result[canary + 1:canary + 3] == b"\xA5\x5A"
    abi(result)
    print("Bookmarks: max-width fields truncate at max-1, preserve delimiters, and keep the source canary")


def bookmark_activation(symbols, memory, folder, directory, cpu):
    """Drive the resident key handler through the real cold apply entry."""
    kind = target_kind(symbols)
    atlas_id, entry_id = (3, 2) if kind == "spectranext" else (2, 1)
    line = "irc.other.test|6697|serverpass|#retro|OtherServ|AUTH other secret|2\n"
    fields = (
        ("_irc_server", 32), ("_irc_port", 6), ("_irc_pass", 24),
        ("_autojoin_channels", 64), ("_search_pattern", 64),
        ("_nickserv_nick", 32), ("_nickserv_pass", 64),
        ("_auth_mode", 1), ("_auth_profile", 1), ("_bookmark_sel", 1),
        ("_bookmark_active_slot", 1), ("_autoconnect", 1), ("_autojoin", 1),
        ("_config_dirty", 1), ("_connection_state", 1),
        ("_autojoin_defer_flags", 1), ("_irc_nick", 18), ("_overlay_mode", 1),
    )

    def fixture(state, active, mode=AUTH_LEARNED, record=line):
        sample = auth_fixture(memory, symbols, mode=mode)
        sample[symbols["_connection_state"]] = state
        sample[symbols["_overlay_mode"]] = 6  # OVERLAY_BOOKMARKS
        sample[symbols["_rx_pos"]:symbols["_rx_pos"] + 2] = b"\0\0"
        sample[symbols["_bookmark_sel"]] = 0
        sample[symbols["_bookmark_rows"]] = 0x80
        sample[symbols["_bookmark_active_slot"]] = active
        sample[symbols["_auth_profile"]] = 4
        sample[symbols["_autoconnect"]] = 1
        sample[symbols["_autojoin"]] = 1
        sample[symbols["_config_dirty"]] = 9
        sample[symbols["_autojoin_defer_flags"]] = AUTOJOIN_MOTD_DONE | AUTOJOIN_IDENT_WAIT
        string(sample, symbols["_irc_port"], "6667")
        string(sample, symbols["_irc_pass"], "kept-serverpass")
        string(sample, symbols["_autojoin_channels"], "#kept")
        string(sample, symbols["_search_pattern"], "#kept")
        sample[0x4200:0x4204] = b"\0" * 4
        sample[0x5700:0x5740] = b"\0" * 64
        entry = overlay_entry(sample, folder, symbols, atlas_id, entry_id)
        stub(sample, symbols, UI_STUBS, 0x43E0)
        reader = bookmark_reader(sample, symbols, record)
        jump(sample, symbols["_overlay_exec"], 0x4400)
        jump(sample, symbols["_notif_center"], 0x4480)
        extra = reader + f"""\
    defs $4400-$,0
    pop bc
    pop de
    push bc
    ld a,e
    cp {atlas_id}
    jr nz,activation_rows
    ld a,d
    cp {entry_id}
    jp nz,0
    ld a,($4200)
    inc a
    ld ($4200),a
    ld a,({symbols['_overlay_slot']})
    ld ($4201),a
    jp {entry}
activation_rows:
    cp 7
    jp nz,0
    ld a,d
    cp 1
    jp nz,0
    ld a,($4203)
    inc a
    ld ($4203),a
    ret
    defs $4480-$,0
    ld hl,2
    add hl,sp
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    ld de,$5700
activation_feedback:
    ld a,(hl)
    inc hl
    ld (de),a
    inc de
    or a
    jr nz,activation_feedback
    ld a,($4202)
    inc a
    ld ($4202),a
    ret
"""
        return sample, extra

    body = f"ld hl,97\ncall {symbols['_bookmark_selector_key']}"
    preserved = tuple((name, size) for name, size in fields
                      if name not in ("_bookmark_active_slot", "_config_dirty"))
    for state in (0, 2, 3):
        for mode in (AUTH_LEGACY, AUTH_PENDING, AUTH_LEARNED, AUTH_SAVE):
            sample, extra = fixture(state, 0, mode)
            before = {name: bytes(sample[symbols[name]:symbols[name] + size])
                      for name, size in preserved}
            for index, active in enumerate((1, 0x81, 0x80), 1):
                result = execute(sample, body, extra, directory, cpu)
                label = (state, mode, index)
                assert result[symbols["_bookmark_active_slot"]] == active, label
                assert result[symbols["_config_dirty"]] == 1, label
                for name, size in preserved:
                    assert result[symbols[name]:symbols[name] + size] == before[name], (label, name)
                assert result[0x4200] == (1 if index < 3 else 0), label
                assert result[0x4201] == (index if index < 3 else 0), label
                assert result[0x4202] == 0, (label, "unexpected disconnect feedback")
                assert result[0x4203] == 1, (label, "accepted selection did not refresh rows")
                abi(result)
                sample = bytearray(result)

    for inferred, expected, activation_mode in ((0x41, 0x81, 2), (0xC1, 0x80, 0)):
        sample, extra = fixture(3, inferred)
        before = {name: bytes(sample[symbols[name]:symbols[name] + size])
                  for name, size in preserved}
        result = execute(sample, body, extra, directory, cpu)
        assert result[symbols["_bookmark_active_slot"]] == expected, inferred
        assert result[symbols["_config_dirty"]] == 1
        assert result[0x4201] == activation_mode
        for name, size in preserved:
            assert result[symbols[name]:symbols[name] + size] == before[name], (inferred, name)
        abi(result)

    for record in (None, "", "|6697|serverpass|#retro|OtherServ|AUTH other secret|2\n"):
        for state in (0, 2, 3):
            for active in (0, 1):
                sample, extra = fixture(state, active, record=record)
                before = {name: bytes(sample[symbols[name]:symbols[name] + size])
                          for name, size in fields}
                result = execute(sample, body, extra, directory, cpu)
                label = (record, state, active)
                assert result[symbols["_overlay_slot"]] == 0, (label, "invalid bookmark accepted")
                for name, size in fields:
                    assert result[symbols[name]:symbols[name] + size] == before[name], (label, name)
                assert result[0x4203] == 0, (label, "failed selection refreshed rows")
                abi(result)
    print("Bookmark key 'a': 1->129->OFF selects next startup; session/auth/deferred JOIN unchanged on " + kind)


def bookmark_setting_commands(symbols, memory, folder, directory, cpu):
    """Explicit !ac/!aj replace future selection; rejected arguments do not."""
    fields = (("_bookmark_active_slot", 1), ("_config_dirty", 1),
              ("_autoconnect", 1), ("_autojoin", 1), ("_auth_mode", 1),
              ("_auth_profile", 1), ("_connection_state", 1),
              ("_nickserv_nick", 32), ("_nickserv_pass", 64),
              ("_autojoin_channels", 64), ("_search_pattern", 64))
    for setting in (6, 7):
        for args in ("nonsense", "on", "off", ""):
            sample = auth_fixture(memory, symbols)
            sample[symbols["_bookmark_active_slot"]] = 129
            sample[symbols["_config_dirty"]] = 9
            sample[symbols["_autoconnect"]] = 1
            sample[symbols["_autojoin"]] = 1
            string(sample, symbols["_autojoin_channels"], "#kept")
            string(sample, symbols["_search_pattern"], "#kept")
            entry = overlay_entry(sample, folder, symbols, 6, 2)
            sample[symbols["_overlay_slot"]] = setting
            string(sample, symbols["_overlay_slot"] + 1, args)
            stub(sample, symbols, UI_STUBS, 0x4320)
            jump(sample, symbols["_sys_puts_print"], 0x4300)
            before = {name: bytes(sample[symbols[name]:symbols[name] + size])
                      for name, size in fields}
            extra = "pop bc\npop hl\npop hl\npush bc\nret\ndefs $4320-$,0\nret\n"
            result = execute(sample, f"call {entry}", extra, directory, cpu)
            if args == "nonsense":
                for name, size in fields:
                    assert result[symbols[name]:symbols[name] + size] == before[name], (setting, name)
            else:
                assert result[symbols["_bookmark_active_slot"]] == 0, (setting, args)
                assert result[symbols["_config_dirty"]] == 1
                enabled = int(args == "on")
                assert result[symbols["_autoconnect"]] == (enabled if setting == 6 else 1)
                assert result[symbols["_autojoin"]] == enabled
                for name, size in fields:
                    if name in ("_bookmark_active_slot", "_config_dirty", "_autoconnect", "_autojoin"):
                        continue
                    if setting == 6 and not enabled and name in ("_autojoin_channels", "_search_pattern"):
                        assert result[symbols[name]] == 0, (setting, args, name)
                    else:
                        assert result[symbols[name]:symbols[name] + size] == before[name], (setting, args, name)
            abi(result)
    print("Bookmark preference: valid !ac/!aj return to current profile; invalid arguments preserve future selection")


def pending_persistence(symbols, memory, folder, directory, cpu):
    atlas_id = 3 if target_kind(symbols) == "spectranext" else 2
    entry_id = 3 if target_kind(symbols) == "spectranext" else 2
    sample = auth_fixture(memory, symbols, mode=AUTH_PENDING,
                          service="Auth@services.test", payload="AUTH me secret")
    sample[symbols["_config_dirty"]] = 9
    sample[symbols["_bookmark_sel"]] = 0
    sample[symbols["_overlay_slot"]] = 0xA5
    entry = overlay_entry(sample, folder, symbols, atlas_id, entry_id)
    stub(sample, symbols, UI_STUBS, 0x4320)
    for name in ("_esx_fopen", "_esx_fcreate", "_esx_fwrite", "_esx_fclose",
                 "_esx_funlink", "_esx_frename"):
        if name in symbols:
            jump(sample, symbols[name], 0x4300)
    extra = """\
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
"""
    result = execute(sample,
                     f"xor a\nld ($4200),a\ncall {entry}",
                     extra, directory, cpu)
    assert result[0x4200] == 0, "pending login reached the bookmark writer"
    assert result[symbols["_overlay_slot"]] == 0
    assert result[symbols["_auth_mode"]] == AUTH_PENDING
    assert result[symbols["_config_dirty"]] == 9
    abi(result)
    print("Bookmarks: pending auth refuses persistence and leaves auth state dirty")


def pending_cmd_save(symbols, memory, directory, cpu):
    sample = auth_fixture(memory, symbols, mode=AUTH_PENDING,
                          service="Auth@services.test", payload="AUTH me secret")
    sample[symbols["_config_dirty"]] = 9
    sample[0x4200] = 0
    jump(sample, symbols["_ui_err"], 0x4320)
    jump(sample, symbols["_overlay_exec"], 0x4300)
    extra = """\
    pop bc
    pop de
    push bc
    ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4320-$,0
    ret
"""
    result = execute(sample, f"ld hl,0\ncall {symbols['_cmd_save']}", extra, directory, cpu)
    assert result[0x4200] == 0, "pending resident cmd_save reached overlay_exec"
    assert result[symbols["_auth_mode"]] == AUTH_PENDING
    assert result[symbols["_config_dirty"]] == 9
    abi(result)
    print("Resident cmd_save: pending auth refuses persistence before overlay execution")


def cmd_save_success_routing(symbols, memory, directory, cpu):
    """Exercise the learned profile save before the ordinary config save."""
    target = target_kind(symbols)
    expected_group = 3 if target == "spectranext" else 2
    expected_entry = 3 if target == "spectranext" else 2

    def run(fail_first):
        sample = auth_fixture(memory, symbols, mode=AUTH_SAVE,
                              service="Auth@services.test", payload="AUTH me secret")
        sample[symbols["_auth_profile"]] = 3
        sample[symbols["_bookmark_sel"]] = 1
        sample[symbols["_config_dirty"]] = 9
        string(sample, symbols["_autojoin_channels"], "#persist")
        sample[0x4200:0x4211] = b"\0" * 17
        sample[0x4207] = 1 if fail_first else 0
        stub(sample, symbols, UI_STUBS, 0x4400)
        jump(sample, symbols["_overlay_exec"], 0x4300)
        jump(sample, symbols["_net_pump_rx"], 0x4400)
        jump(sample, symbols["_snapshot_autojoin_channels"], 0x4420)
        setup = "ld a,1\nld ($4207),a" if fail_first else "xor a\nld ($4207),a"
        extra = f"""\
    pop bc
    pop de
    push bc
    ld a,($4200)
    inc a
    ld ($4200),a
    cp 1
    jr z,save_first
    ld a,e
    ld ($4204),a
    ld a,d
    ld ($4205),a
    ld a,({symbols['_bookmark_sel']})
    ld ($4206),a
    ld a,1
    ld ({symbols['_overlay_slot']}),a
    ret
save_first:
    ld a,e
    ld ($4201),a
    ld a,d
    ld ($4202),a
    ld a,({symbols['_bookmark_sel']})
    ld ($4203),a
    ld a,($4207)
    or a
    jr nz,save_fail
    ld a,1
    ld ({symbols['_overlay_slot']}),a
    ret
save_fail:
    xor a
    ld ({symbols['_overlay_slot']}),a
    ret
    defs $4400-$,0
    ret
    defs $4420-$,0
    ld a,($4210)
    inc a
    ld ($4210),a
    ret
"""
        return execute(sample, f"{setup}\nld hl,0\ncall {symbols['_cmd_save']}",
                        extra, directory, cpu)

    result = run(False)
    assert result[0x4200] == 2, "cmd_save did not perform bookmark then config save"
    assert (result[0x4201], result[0x4202], result[0x4203]) == (
        expected_group, expected_entry, 2), "associated bookmark was not selected"
    assert (result[0x4204], result[0x4205], result[0x4206]) == (3, 1, 1), (
        "config save did not follow bookmark save or restore selection")
    assert result[symbols["_bookmark_sel"]] == 1
    assert result[symbols["_auth_mode"]] == AUTH_LEARNED
    assert result[symbols["_search_pattern"]:symbols["_search_pattern"] + 9].split(b"\0", 1)[0] == b"#persist"
    assert result[symbols["_overlay_slot"]] == 1
    assert result[0x4210] == 0, "AUTH_SAVE unexpectedly called channel snapshot"
    abi(result)

    result = run(True)
    assert result[0x4200] == 1, "failed bookmark save reached config save"
    assert (result[0x4201], result[0x4202], result[0x4203]) == (
        expected_group, expected_entry, 2)
    assert result[symbols["_bookmark_sel"]] == 1
    assert result[symbols["_auth_mode"]] == AUTH_LEARNED
    assert result[symbols["_config_dirty"]] == 9
    assert result[symbols["_search_pattern"]:symbols["_search_pattern"] + 9].split(b"\0", 1)[0] == b"#persist"
    assert result[symbols["_overlay_slot"]] == 0
    assert result[0x4210] == 0, "AUTH_SAVE unexpectedly called channel snapshot"
    abi(result)
    print("cmd_save: learned profile save selects bookmark 2, restores selection, and gates config persistence on success")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    symbols, memory = load(args.folder)
    required = (
        "_auth_mode", "_auth_profile", "_nickserv_nick", "_nickserv_pass",
        "_parse_irc_message", "_send_identify", "_config_load",
        "_has_esxdos", "_h_motd_done",
        "_ring_buffer", "_bookmark_sel", "_autojoin", "_autojoin_channels",
        "_ui_err", "_overlay_exec", "_cmd_save", "_cmd_id", "_rx_pos",
        "_irc_pass", "_search_pattern", "_bookmark_rows",
        "_bookmark_active_slot", "_autoconnect", "_esx_fopen",
        "_esx_fread", "_esx_fclose", "_esx_buf", "_esx_count", "_esx_result",
        "_force_disconnect", "_disconnecting_in_progress", "_notif_cancel_current",
        "_net_pump_rx", "_snapshot_autojoin_channels",
        "_bookmark_selector_key", "_notif_center", "_overlay_mode",
    )
    if target_kind(symbols) != "spectranext":
        required += ("_cfg_apply",)
    missing = [name for name in required if name not in symbols]
    assert not missing, "artifact lacks learned-auth symbols: " + ", ".join(missing)
    cpu = "z80n" if "_next_uart_status" in symbols else "z80"
    with tempfile.TemporaryDirectory(prefix="autologin-cpu-") as temporary:
        directory = Path(temporary)
        send_modes(symbols, memory, directory, cpu)
        login_overlay(symbols, memory, args.folder, directory, cpu)
        login_pending_guard(symbols, memory, args.folder, directory, cpu)
        login_validation(symbols, memory, args.folder, directory, cpu)
        id_overlay(symbols, memory, args.folder, directory, cpu)
        id_overlay_long_payload(symbols, memory, args.folder, directory, cpu)
        id_resident_wrapper(symbols, memory, directory, cpu)
        notice_gate(symbols, memory, directory, cpu)
        numeric_900(symbols, memory, directory, cpu)
        motd_replay(symbols, memory, directory, cpu)
        login_confirm_before_motd(symbols, memory, args.folder, directory, cpu)
        pending_disconnect(symbols, memory, directory, cpu)
        cfg_roundtrip(symbols, memory, directory, cpu)
        config_load_roundtrip(symbols, memory, args.folder, directory, cpu)
        serializer_roundtrip(symbols, memory, args.folder, directory, cpu)
        bookmark_config_roundtrip(symbols, memory, args.folder, directory, cpu)
        old_bookmark(symbols, memory, args.folder, directory, cpu)
        bookmark_bounds(symbols, memory, args.folder, directory, cpu)
        bookmark_activation(symbols, memory, args.folder, directory, cpu)
        bookmark_setting_commands(symbols, memory, args.folder, directory, cpu)
        pending_persistence(symbols, memory, args.folder, directory, cpu)
        pending_cmd_save(symbols, memory, directory, cpu)
        cmd_save_success_routing(symbols, memory, directory, cpu)


if __name__ == "__main__":
    main()
