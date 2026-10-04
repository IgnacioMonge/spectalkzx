"""Check the !config screen layout in linked artifacts with z88dk-ticks.

HOSTPYTHON tools/test_config_screen_cpu.py build/classic
The directory must contain SpecTalkZX.map, TAP/resident image, atlas and DAT.
print_str64() is replaced by a recorder; no screen, UART or file I/O occurs.
"""

import argparse
from pathlib import Path
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load, string
from test_autologin_cpu import overlay_entry

CAPTURE = 0x3800  # unused by every target's resident image and overlay window


def recorder(symbols):
    # print_str64(y, col, s, attr) is callee: stack holds y, col, s, attr.
    return f"""
    pop hl
    pop bc
    pop de
    inc sp
    push hl
    ld hl,($4200)
    ld (hl),c
    inc hl
    ld (hl),b
    inc hl
copy:
    ld a,(de)
    ld (hl),a
    inc hl
    inc de
    inc b
    or a
    jr nz,copy
    dec b
    ld ($4200),hl
    ld a,b
    ld ({symbols["_g_ps64_col"]}),a
    ld a,c
    ld ({symbols["_g_ps64_y"]}),a
    ret"""


def render(symbols, memory, folder, directory, cpu, strings, values, friends, ignores):
    sample = bytearray(memory)
    for name, value in strings.items():
        string(sample, symbols[name], value)
    for name, value in values.items():
        sample[symbols[name]] = value & 0xFF
    for i in range(5):
        name = friends[i] if i < len(friends) else ""
        start = symbols["_friend_nicks"] + i * 18
        sample[start : start + 18] = name.encode().ljust(18, b"\0")
    for i, name in enumerate(ignores):
        start = symbols["_ignore_list"] + i * 16
        sample[start : start + 16] = name.encode().ljust(16, b"\0")
    sample[symbols["_ignore_count"]] = len(ignores)
    sample[symbols["_overlay_rx_release"]] = 0xC9
    jump(sample, symbols["_print_str64"], 0x4300)
    entry = overlay_entry(sample, folder, symbols, 4, 0)
    result = execute(
        sample,
        f"ld hl,{CAPTURE}\nld ($4200),hl\ncall {entry}",
        recorder(symbols),
        directory,
        cpu,
        cycles=5000000,
    )
    abi(result)
    end = int.from_bytes(result[0x4200:0x4202], "little")
    calls, pos = [], CAPTURE
    while pos < end:
        stop = result.index(0, pos + 2)
        calls.append((result[pos], result[pos + 1], result[pos + 2 : stop].decode()))
        pos = stop + 1
    return calls


def grid(rows):
    calls = []
    for row, (left, lval, right, rval) in enumerate(rows, 7):
        calls += [(row, 0, left), (row, 14, lval), (row, 32, right), (row, 44, rval)]
    return calls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    symbols, memory = load(args.folder)
    font, end = symbols["font_lut"], symbols["bpe_dict"] + 222
    memory[font:end] = (args.folder / "SPECTALK.DAT").read_bytes()[: end - font]
    cpu = "z80n" if "_next_uart_status" in symbols else "z80"
    flags = (
        "_autoconnect",
        "_autojoin",
        "_nick_color_mode",
        "_show_traffic",
        "_show_channel_separators",
        "_notif_enabled",
        "_beep_enabled",
        "_keyclick_enabled",
        "_count_sync_enabled",
    )
    friends = [
        "FriendNumberOne17",
        "FriendNumberTwo17",
        "FriendNumberThre3",
        "FriendNumberFour4",
        "FriendNumberFive5",
    ]
    ignores = [f"IgnoredNumber0{i}" for i in range(1, 6)]
    with tempfile.TemporaryDirectory(prefix="config-screen-cpu-") as temporary:
        directory = Path(temporary)

        # Worst case: longest host/port/nick, pending /login, five of each list.
        calls = render(
            symbols,
            memory,
            args.folder,
            directory,
            cpu,
            {
                "_irc_server": "irc.very-long-network-name.test",
                "_irc_port": "65535",
                "_irc_nick": "SeventeenCharNick",
                "_irc_pass": "x",
                "_nickserv_nick": "NickServ",
                "_nickserv_pass": "AUTH me secret",
            },
            dict(
                {
                    name: name
                    in (
                        "_autoconnect",
                        "_nick_color_mode",
                        "_show_channel_separators",
                        "_notif_enabled",
                        "_beep_enabled",
                        "_count_sync_enabled",
                    )
                    for name in flags
                },
                _auth_mode=1,
                _bookmark_active_slot=0x83,
                _autoaway_minutes=15,
                _current_theme=1,
                _show_timestamps=2,
                _sntp_tz=-5,
            ),
            friends,
            ignores,
        )
        expected = [
            (6, 0, "server="),
            (6, 14, "irc.very-long-network-name.test"),
            (6, 46, "65535"),
        ]
        expected += grid(
            [
                ("nick=", "SeventeenCharNick", "nickserv=", "NickServ"),
                ("pass=", "set", "authcmd=", "pending"),
                ("autoconnect=", "on", "autojoin=", "off"),
                ("bookmark=", "3+autojoin", "autoaway=", "15m"),
                ("theme=", "1", "timestamps=", "smart"),
                ("nickcolor=", "on", "traffic=", "off"),
                ("divider=", "on", "notif=", "on"),
                ("beep=", "on", "click=", "off"),
                ("countsync=", "on", "tz=", "-05"),
            ]
        )
        expected += [
            (16, 0, "friends="),
            (16, 10, friends[0]),
            (16, 28, friends[1]),
            (16, 46, friends[2]),
            (17, 10, friends[3]),
            (17, 28, friends[4]),
            (18, 0, "ignores="),
            (18, 10, ignores[0]),
            (18, 26, ignores[1]),
            (18, 42, ignores[2]),
            (19, 10, ignores[3]),
            (19, 26, ignores[4]),
        ]
        assert calls == expected, ("worst-case layout", calls)
        print("Config screen: worst case fits rows 6..19 with aligned key labels")

        # Unset values, legacy nickpass, saved bookmark choices and inferred marks.
        base = {
            "_irc_server": "",
            "_irc_port": "6667",
            "_irc_nick": "",
            "_irc_pass": "",
            "_nickserv_nick": "",
            "_nickserv_pass": "",
        }
        cases = (
            (0, "", 0, "nickpass=", "(not set)", "(not set)", "off"),
            (0, "pw", 0x80, "nickpass=", "set", "off", "05m"),
            (2, "AUTH me pw", 0x42, "authcmd=", "set", "(not set)", "off"),
            (3, "AUTH me pw", 2, "authcmd=", "set", "2", "off"),
        )
        for mode, secret, slot, auth_key, auth_value, bookmark, away in cases:
            calls = render(
                symbols,
                memory,
                args.folder,
                directory,
                cpu,
                dict(base, _nickserv_pass=secret),
                dict(
                    {name: 0 for name in flags},
                    _auth_mode=mode,
                    _bookmark_active_slot=slot,
                    _autoaway_minutes=5 if away == "05m" else 0,
                    _current_theme=1,
                    _show_timestamps=0,
                    _sntp_tz=1,
                ),
                [],
                [],
            )
            assert calls[0:2] == [(6, 0, "server="), (6, 14, "(not set)")], calls
            assert calls[8:10] == [(8, 32, auth_key), (8, 44, auth_value)], calls
            assert calls[14:16] == [(10, 0, "bookmark="), (10, 14, bookmark)], calls
            assert calls[16:18] == [(10, 32, "autoaway="), (10, 44, away)], calls
            assert calls[-4:] == [
                (16, 0, "friends="),
                (16, 10, "(not set)"),
                (17, 0, "ignores="),
                (17, 10, "(not set)"),
            ], calls
            assert "autologin=" not in [text for _, _, text in calls]
        print("Config screen: auth modes, bookmark choices and empty lists OK")

        # Short names are packed one space apart instead of using fixed slots.
        calls = render(
            symbols,
            memory,
            args.folder,
            directory,
            cpu,
            base,
            dict({name: 0 for name in flags}, _current_theme=1, _sntp_tz=1),
            ["Friend1", "Friend2", "Friend3", "Friend4"],
            ["NoisyNick", "Spammer"],
        )
        assert calls[-8:] == [
            (16, 0, "friends="),
            (16, 10, "Friend1"),
            (16, 18, "Friend2"),
            (16, 26, "Friend3"),
            (16, 34, "Friend4"),
            (17, 0, "ignores="),
            (17, 10, "NoisyNick"),
            (17, 20, "Spammer"),
        ], calls
        print("Config screen: short list names packed one space apart")


if __name__ == "__main__":
    main()
