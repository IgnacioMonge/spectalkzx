#!/usr/bin/env python3
"""Linked CPU regressions for notification storage/BPE and IRC dispatch."""

import argparse
from pathlib import Path
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load, string


TEXT_COMMANDS = (
    ("PRIVMSG", "_h_privmsg_notice"),
    ("NOTICE", "_h_privmsg_notice"),
    ("PING", "_h_ping"),
    ("PONG", "_h_pong"),
    ("PART", "_h_part"),
    ("NICK", "_h_nick"),
    ("JOIN", "_h_join"),
    ("QUIT", "_h_quit"),
    ("KICK", "_h_kick"),
    ("KILL", "_h_kill"),
    ("MODE", "_h_mode"),
    ("ERROR", "_h_error"),
    ("CAP", "_h_cap"),
    ("privmsg", "_h_privmsg_notice"),
    ("eRrOr", "_h_error"),
    ("kIlL", "_h_kill"),
)


def c_string(memory, address):
    end = memory.index(0, address)
    return bytes(memory[address:end])


def stub_void(sample, symbols, *names):
    for name in names:
        jump(sample, symbols[name], 0x4380)


def numeric_dispatch(symbols, memory, directory, cpu):
    valid = ("000", "006", "099", "199", "249", "267", "399", "600",
             "899", "901", "998", "999")
    invalid = ("0", "00", "0000", "0999", "1000", "9999", "99x", "x99")
    cases = ([(cmd, 0, 1) for cmd in valid] +
             [(cmd, 0, 0) for cmd in invalid] +
             [(cmd, 1, 0) for cmd in ("000", "999")])
    for command, names, expected in cases:
        sample = bytearray(memory)
        sample[symbols["_show_names_list"]] = names
        jump(sample, symbols["_h_numeric_default"], 0x4300)
        jump(sample, symbols["_h_default_cmd"], 0x4310)
        string(sample, 0x5000, f":server {command}")
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         """ld a,1
    ld ($4200),a
    ret
    defs $4310-$,0
    ld a,2
    ld ($4200),a
    ret""", directory, cpu)
        assert result[0x4200] == expected, ("numeric dispatch", command, names)
        if expected:
            address = symbols["_last_cmd_id"]
            assert int.from_bytes(result[address:address + 2], "little") == int(command)
        abi(result)
    print("Numeric dispatcher: 22 fallback/boundary/NAMES cases; SP/IX/IY preserved")


def dispatch(symbols, memory, directory, cpu):
    for command, handler in TEXT_COMMANDS:
        sample = bytearray(memory)
        jump(sample, symbols[handler], 0x4300)
        jump(sample, symbols["_h_default_cmd"], 0x4380)
        string(sample, 0x5000, f":server {command}")
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         """ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4380-$,0
    ret""", directory, cpu)
        assert result[0x4200] == 1, ("valid text command rejected", command)
        abi(result)

    for command, expected in (("ERROR", 1), ("ERRORX", 0), ("ER", 0),
                              ("UNKNOWN", 0), (b"ERR\xcfR", 0)):
        sample = bytearray(memory)
        jump(sample, symbols["_h_error"], 0x4300)
        jump(sample, symbols["_h_default_cmd"], 0x4380)
        if isinstance(command, bytes):
            wire = b":server " + command + b"\0"
            sample[0x5000:0x5000 + len(wire)] = wire
        else:
            string(sample, 0x5000, f":server {command}")
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         """ld a,($4200)
    inc a
    ld ($4200),a
    ret
    defs $4380-$,0
    ret""", directory, cpu)
        assert result[0x4200] == expected, ("partial text dispatch", command)
        abi(result)
    print("Text dispatcher: exact ERROR token, short/extended/unknown rejection and valid commands OK")

    for command, handler, expected in (("PING", "_h_ping", 1),
                                       ("PONG", "_h_pong", 1),
                                       ("PRIVMSG", "_h_privmsg_notice", 0),
                                       ("ERROR", "_h_error", 0),
                                       ("UNKNOWN", "_h_default_cmd", 0)):
        sample = bytearray(memory)
        sample[symbols["_show_names_list"]] = 1
        jump(sample, symbols[handler], 0x4300)
        if handler != "_h_default_cmd":
            jump(sample, symbols["_h_default_cmd"], 0x4300)
        string(sample, 0x5000, f":server {command}")
        result = execute(sample,
                         f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         """ld a,($4200)
    inc a
    ld ($4200),a
    ret""", directory, cpu)
        assert result[0x4200] == expected, ("/names text gate", command)
        abi(result)
    print("Text dispatcher: /names admits exact PING/PONG only")


def disconnected_notification(symbols, memory, directory, cpu):
    sample = bytearray(memory)
    sample[symbols["_notif_enabled"]] = 1
    sample[symbols["_notif_timeout"]] = 0
    string(sample, 0x5000, ":server ERROR")
    stub_void(sample, symbols, "_set_attr_err", "_main_puts", "_main_print", "_force_disconnect")
    result = execute(sample,
                     f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                     "defs $4380-$,0\nret", directory, cpu)
    assert c_string(result, symbols["_notif_buf"]) == b"Disconnected", "BPE leaked into S_DISCONN notification"
    abi(result)
    print("Notification text: S_DISCONN remains raw ASCII")


def names_sample(symbols, memory, directory, cpu, interleaved):
    sample = bytearray(memory)
    sample[symbols["_notif_enabled"]] = 1
    sample[symbols["_friend_count"]] = 1
    sample[symbols["_channel_count"]] = 2
    sample[symbols["_current_channel_idx"]] = 1
    channel = symbols["_channels"] + 32
    string(sample, channel, "#room")
    sample[channel + 30] = 1
    sample[symbols["_cur_chan_ptr"]:symbols["_cur_chan_ptr"] + 2] = channel.to_bytes(2, "little")
    string(sample, symbols["_friend_nicks"], "Alice")
    string(sample, symbols["_names_target_channel"], "#room")
    string(sample, 0x5000, ":server 353 me = #room :Alice Bob")
    string(sample, 0x5100, ":Mallory!u@h PRIVMSG me :hello")
    string(sample, 0x5200, ":server 366 me #room :End of NAMES")
    stub_void(sample, symbols, "_draw_status_bar", "_badge_flash_on", "_mention_beep")
    sample[symbols["_add_query"]:symbols["_add_query"] + 4] = b"\x21\xff\xff\xc9"
    calls = f"ld hl,$5000\ncall {symbols['_parse_irc_message']}\n"
    if interleaved:
        calls += f"ld hl,$5100\ncall {symbols['_parse_irc_message']}\n"
    calls += f"ld hl,$5200\ncall {symbols['_parse_irc_message']}"
    result = execute(sample, calls, "defs $4380-$,0\nret", directory, cpu)
    abi(result)
    return c_string(result, symbols["_notif_buf"])


def names_notifications(symbols, memory, directory, cpu):
    uninterrupted = names_sample(symbols, memory, directory, cpu, False)
    interleaved = names_sample(symbols, memory, directory, cpu, True)
    assert uninterrupted == b"Alice in room", ("NAMES notification", uninterrupted)
    assert interleaved.startswith(b"Mallory: hello [ENTER] -\x01"), ("PM notification lost", interleaved)
    assert interleaved.endswith(uninterrupted), ("NAMES accumulator overwritten by PM", interleaved)
    print("NAMES notifications: 353→366 and 353→PM→366 preserve independent messages")


def names_capacity(symbols, memory, directory, cpu):
    sample = bytearray(memory)
    sample[symbols["_friend_count"]] = 4
    sample[symbols["_channel_count"]] = 2
    sample[symbols["_current_channel_idx"]] = 1
    channel = symbols["_channels"] + 32
    string(sample, channel, "#room")
    sample[channel + 30] = 1
    sample[symbols["_cur_chan_ptr"]:symbols["_cur_chan_ptr"] + 2] = channel.to_bytes(2, "little")
    friends = ("A" * 17, "B" * 17, "C" * 7, "D")
    for index, friend in enumerate(friends):
        string(sample, symbols["_friend_nicks"] + index * 18, friend)
    string(sample, symbols["_names_target_channel"], "#room")
    string(sample, 0x5000, ":server 353 me = #room :" + " ".join(friends))
    buffer = symbols["_names_friend_buf"]
    sample[buffer + 46] = 0xA5
    result = execute(sample,
                     f"ld hl,$5000\ncall {symbols['_parse_irc_message']}",
                     "", directory, cpu)
    expected = (friends[0] + ", " + friends[1] + ", " + friends[2]).encode()
    assert len(expected) == 45 and c_string(result, buffer) == expected
    assert result[buffer + 46] == 0xA5, "NAMES friend accumulator overwrote its canary"
    abi(result)
    print("NAMES capacity: packed 45-byte list rejects an unseparated tail and preserves canary")


def check(folder):
    symbols, memory = load(folder)
    cpu = "z80n" if "_next_uart_status" in symbols else "z80"
    with tempfile.TemporaryDirectory(prefix="notifications-parser-cpu-") as temporary:
        directory = Path(temporary)
        numeric_dispatch(symbols, memory, directory, cpu)
        dispatch(symbols, memory, directory, cpu)
        disconnected_notification(symbols, memory, directory, cpu)
        names_notifications(symbols, memory, directory, cpu)
        names_capacity(symbols, memory, directory, cpu)
    print(f"{folder}: notification/parser CPU regressions OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args()
    for folder in args.folders:
        check(folder)


if __name__ == "__main__":
    main()
