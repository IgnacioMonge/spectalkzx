"""Run startup/config regressions on a freshly linked TAP or resident image.

HOSTPYTHON tools/test_startup_config_cpu.py build/SpecTalkZX.tap
HOSTPYTHON tools/test_startup_config_cpu.py build/next-resident.img
Requires sjasmplus and z88dk-ticks. No hardware I/O is exercised.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def run(memory, start, end, directory, cpu="z80", cycles=1000000):
    source, output = directory / "input.bin", directory / "output.bin"
    source.write_bytes(memory)
    subprocess.run([
        "z88dk-ticks", "-m" + cpu, "-pc", f"{start:04x}", "-start", f"{start:04x}",
        "-end", f"{end:04x}", "-counter", str(cycles), "-output", str(output),
        str(source),
    ], check=True, capture_output=True, timeout=30)
    return output.read_bytes()


def bookmark_startup_contract(symbols, memory, folder, directory, cpu):
    # Lazy import avoids the shared execute()/run() helpers' import cycle.
    from test_audit_fixes_cpu import abi, execute, jump
    from test_autologin_cpu import (AUTH_LEARNED, UI_STUBS, bookmark_reader,
                                   load_config_fixture, overlay_entry, stub,
                                   target_kind)

    assert "_bookmark_startup" in symbols, "artifact lacks bookmark startup helper"
    kind = target_kind(symbols)
    group, apply_id = (3, 2) if kind == "spectranext" else (2, 1)
    record = "irc.startup.test|6697|startup-pass|#startup|StartupServ|AUTH boot secret|2\n"
    loaded_fields = (("_irc_server", 32), ("_irc_port", 6), ("_irc_pass", 24),
                     ("_autojoin_channels", 64), ("_search_pattern", 64),
                     ("_nickserv_nick", 32), ("_nickserv_pass", 64),
                     ("_auth_mode", 1), ("_auth_profile", 1))

    # These are deliberately live-CFG flags; the bookmark marker overrides
    # them only inside the startup helper, independent of config line order.
    for value in (0, 1, 2, 3, 4, 5, 128, 129, 130, 131, 132, 133,
                  6, 64, 65, 127, 134, 192, 193, 255, 256, 257, 65535, 65536):
        expected = value if value <= 133 and (value & ~0x80) <= 5 else 128
        for marker_first in (False, True):
            lines = (f"bookmark={value}\n", "autoconnect=1\nautojoin=0\n")
            config = ("server=irc.config.test\nport=6667\n"
                      "authcmd=AUTH config secret\nnickserv=ConfigServ\n")
            config += "".join(lines if marker_first else lines[::-1])
            result = load_config_fixture(symbols, memory, folder, directory, cpu, config)
            assert result[symbols["_bookmark_active_slot"]] == expected, (value, marker_first)
            assert result[symbols["_autoconnect"]] == 1
            assert result[symbols["_autojoin"]] == 0

    for text in ("", "nonsense", "-1"):
        config = f"autoconnect=1\nautojoin=1\nbookmark={text}\n"
        result = load_config_fixture(symbols, memory, folder, directory, cpu, config)
        assert result[symbols["_bookmark_active_slot"]] == 128, text

    for marker, content in ((0, record), (0x41, record), (0xC1, record), (128, record), (1, record),
                            (0x83, record), (5, None), (0x85, ""), (0x85, "|6697|||\n"),
                            (0x85, "overlay load failed")):
        config = ("server=irc.config.test\nport=6667\n"
                  "authcmd=AUTH config secret\nnickserv=ConfigServ\n"
                  "autoconnect=1\nautojoin=1\n")
        if marker and not marker & 0x40:
            config += f"bookmark={marker}\n"
        sample = load_config_fixture(symbols, memory, folder, directory, cpu, config)
        if marker & 0x40:
            sample[symbols["_bookmark_active_slot"]] = marker
        sample[symbols["_connection_state"]] = 0
        sample[symbols["_config_dirty"]] = 9
        sample[symbols["_overlay_mode"]] = 0
        sample[symbols["_bookmark_sel"]] = 4
        sample[symbols["_rx_pos"]:symbols["_rx_pos"] + 2] = b"\0\0"
        before = {name: bytes(sample[symbols[name]:symbols[name] + size])
                  for name, size in loaded_fields}
        entry = overlay_entry(sample, folder, symbols, group, apply_id)
        stub(sample, symbols, UI_STUBS, 0x43E0)
        reader = bookmark_reader(sample, symbols, content)
        jump(sample, symbols["_overlay_exec"], 0x4400)
        dispatch = "ret" if content == "overlay load failed" else f"jp {entry}"
        extra = reader + f"""\
    defs $4400-$,0
    pop bc
    pop de
    push bc
    ld a,e
    cp {group}
    jp nz,0
    ld a,d
    cp {apply_id}
    jp nz,0
    ld a,($4200)
    inc a
    ld ($4200),a
    ld a,({symbols['_overlay_slot']})
    ld ($4201),a
    {dispatch}
"""
        result = execute(sample, f"call {symbols['_bookmark_startup']}", extra, directory, cpu)
        assert result[symbols["_config_dirty"]] == 9, marker
        assert result[symbols["_overlay_mode"]] == 0, marker
        assert result[symbols["_connection_state"]] == 0, marker
        if marker == 0 or marker & 0x40:
            assert result[0x4200] == 0, "legacy config unexpectedly read a bookmark"
            assert result[symbols["_autoconnect"]] == result[symbols["_autojoin"]] == 1
            for name, size in loaded_fields:
                assert result[symbols[name]:symbols[name] + size] == before[name], name
        elif marker == 128:
            assert result[0x4200] == 0, "OFF unexpectedly read a bookmark"
            assert result[symbols["_autoconnect"]] == result[symbols["_autojoin"]] == 0
            for name, size in loaded_fields:
                assert result[symbols[name]:symbols[name] + size] == before[name], name
        else:
            assert result[0x4200:0x4202] == b"\1\0", "startup did not call real mode-0 apply"
            assert result[symbols["_bookmark_sel"]] == (marker & 0x7F) - 1
            if content == record:
                assert result[symbols["_bookmark_active_slot"]] == marker
                assert result[symbols["_autoconnect"]] == 1
                assert result[symbols["_autojoin"]] == bool(marker & 0x80)
                assert result[symbols["_auth_mode"]] == AUTH_LEARNED
                assert result[symbols["_auth_profile"]] == (marker & 0x7F)
                for name, text, size in (("_irc_server", "irc.startup.test", 32),
                        ("_irc_pass", "startup-pass", 24),
                        ("_autojoin_channels", "#startup", 64),
                        ("_nickserv_nick", "StartupServ", 32),
                        ("_nickserv_pass", "AUTH boot secret", 64)):
                    actual = result[symbols[name]:symbols[name] + size].split(b"\0", 1)[0]
                    assert actual == text.encode(), (marker, name, actual)
            else:
                assert result[symbols["_bookmark_active_slot"]] == 128
                assert result[symbols["_autoconnect"]] == result[symbols["_autojoin"]] == 0
                for name, size in loaded_fields:
                    assert result[symbols[name]:symbols[name] + size] == before[name], (content, name)
        abi(result)
    print("Bookmark startup: full-width key validation/order; real cold apply, legacy/OFF and failed reads OK on " + kind)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--map", type=Path, default=Path("SpecTalkZX.map"))
    args = parser.parse_args()
    symbols = {match[1]: int(match[2], 16)
               for line in args.map.read_text().splitlines()
               if (match := re.match(r"^(\w+)\s+=\s+\$([0-9A-Fa-f]+)", line))}
    resident = args.image.read_bytes()
    if args.image.suffix.lower() == ".tap":
        offset, blocks = 0, []
        while offset < len(resident):
            size = int.from_bytes(resident[offset:offset + 2], "little")
            block = resident[offset + 2:offset + 2 + size]
            assert len(block) == size and size >= 2
            checksum = 0
            for byte in block:
                checksum ^= byte
            assert checksum == 0
            blocks.append(block)
            offset += size + 2
        assert offset == len(resident) and blocks[-1][0] == 255
        resident = blocks[-1][1:-1]
    origin = symbols["__crt_org_code"]
    assert len(resident) == symbols["__data_compiler_tail"] - origin
    memory = bytearray(65536)
    memory[origin:origin + len(resident)] = resident
    cpu = "z80n" if "_next_uart_status" in symbols else "z80"
    spectranext = "_spxn_overlay_page" in symbols
    if spectranext:
        atlas = (args.image.parent / "SPECTALK.OVL").read_bytes()
        pair = 8 + 4 * 4
        offset = int.from_bytes(atlas[pair:pair + 2], "little")
        size = int.from_bytes(atlas[pair + 2:pair + 4], "little")
        memory[0x2000:0x2000 + size] = atlas[offset:offset + size]
        config_entry = int.from_bytes(memory[0x200A:0x200C], "little")
        for name, address in (("_esx_fopen", 0x4300), ("_esx_fread", 0x4340),
                              ("_esx_fclose", 0x4380), ("_overlay_rx_release", 0x4380)):
            memory[symbols[name]:symbols[name] + 3] = b"\xc3" + address.to_bytes(2, "little")

    with tempfile.TemporaryDirectory(prefix="startup-config-cpu-") as temporary:
        directory = Path(temporary)
        if "_overlay_exec_active" in symbols:  # Classic startup, before main/I/O.
            dirty = bytearray([0xA5]) * 65536
            dirty[origin:origin + len(resident)] = resident
            result = run(dirty, origin, symbols["_main"], directory, cpu)
            for name in ("_uart_tx_failed", "_overlay_exec_active"):
                assert result[symbols[name]] == 0, (name, result[symbols[name]])
            assert result[0xF500] == 0xA5, "startup overwrote the RX ring"
            print("Classic startup: dirty UART/overlay state cleared; ring preserved")

        apply = (f"call {config_entry}" if spectranext else
                 f"ld hl,$5020\npush hl\nld hl,$5000\npush hl\ncall {symbols['_cfg_apply']}")
        apply = apply.replace("\n", "\n    ")
        driver = f"""    org $4000
    di
    ld sp,$FF58
    ld ix,$1234
    ld iy,$5678
    {apply}
    ld ($4100),sp
    ld ($4102),ix
    ld ($4104),iy
    jp 0
"""
        if spectranext:
            driver += f"""
    defs $4300-$,0
    ld a,1
    ld ({symbols['_esx_handle']}),a
    ret
    defs $4340-$,0
    ld hl,$5000
    ld de,({symbols['_esx_buf']})
    ld bc,($5040)
    ldir
    ld hl,($5040)
    ld ({symbols['_esx_result']}),hl
    ret
    defs $4380-$,0
    ret
"""
        assembly, binary = directory / "probe.asm", directory / "probe.bin"
        assembly.write_text(driver)
        subprocess.run(["sjasmplus", "--nologo", "--dirbol",
                        "--raw=" + str(binary), str(assembly)],
                       check=True, capture_output=True, timeout=30)
        code = binary.read_bytes()
        memory[0x4000:0x4000 + len(code)] = code
        cases = (
            ("theme", "_current_theme", 3, 1, 3, 3),
            ("autoaway", "_autoaway_minutes", 10, 0, 60, 10),
            ("timestamps", "_show_timestamps", 2, 0, 2, 1),
        )
        values = (0, 1, 2, 3, 4, 60, 61, 255, 256, 257, 258, 316, 65535,
                  65536, 65537, 65538, 65596, 131072, 99999999999999999999)
        for key, symbol, initial, low, high, fallback in cases:
            for value in values:
                sample = bytearray(memory)
                sample[symbols[symbol]] = initial
                if spectranext:
                    config = f"{key}={value}\n".encode()
                    sample[0x5000:0x5000 + len(config)] = config
                    sample[0x5040:0x5042] = len(config).to_bytes(2, "little")
                    sample[symbols["_has_esxdos"]] = 1
                for address, text in (() if spectranext else ((0x5000, key), (0x5020, str(value)))):
                    sample[address:address + len(text) + 1] = text.encode() + b"\0"
                result = run(sample, 0x4000, 0, directory, cpu)
                expected = value if low <= value <= high else fallback
                assert result[symbols[symbol]] == expected, (key, value, result[symbols[symbol]])
                assert result[0x4100:0x4106] == bytes.fromhex("58ff34127856"), "SP/IX/IY changed"
        print(f"Linked config: {len(cases) * len(values)} boundary/wrap cases passed; SP/IX/IY preserved")
        bookmark_startup_contract(symbols, memory, args.image.parent, directory, cpu)


if __name__ == "__main__":
    main()
