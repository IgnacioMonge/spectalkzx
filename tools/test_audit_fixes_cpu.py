"""Exercise the audit fixes in linked artifacts with sjasmplus/z88dk-ticks.

HOSTPYTHON tools/test_audit_fixes_cpu.py build/classic
The directory must contain SpecTalkZX.map, TAP/resident image, atlas and DAT.
Only firmware/UART I/O and unrelated UI effects are stubbed; no real I/O occurs.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

from test_startup_config_cpu import run


def load(folder):
    symbols = {m[1]: int(m[2], 16) for line in (folder / "SpecTalkZX.map").read_text().splitlines()
               if (m := re.match(r"^(\w+)\s+=\s+\$([0-9a-fA-F]+)", line))}
    image = folder / "next-resident.img"
    if image.exists():
        resident = image.read_bytes()
    else:
        raw = (folder / "SpecTalkZX.tap").read_bytes()
        pos = 0
        while pos < len(raw):
            length = int.from_bytes(raw[pos:pos + 2], "little")
            block = raw[pos + 2:pos + 2 + length]
            assert len(block) == length and length >= 2
            checksum = 0
            for byte in block:
                checksum ^= byte
            assert checksum == 0
            pos += length + 2
        assert pos == len(raw) and block[0] == 255
        resident = block[1:-1]
    origin, end = symbols["__crt_org_code"], symbols["__data_compiler_tail"]
    assert len(resident) == end - origin
    memory = bytearray(65536)
    memory[origin:end] = resident
    return symbols, memory


def string(memory, address, value):
    memory[address:address + len(value) + 1] = value.encode() + b"\0"


def jump(memory, address, target):
    memory[address:address + 3] = b"\xc3" + target.to_bytes(2, "little")


def execute(memory, body, extra, directory, cpu, cycles=1000000):
    source, binary = directory / "probe.asm", directory / "probe.bin"
    assembly = f"""    org $4000
    di
    ld sp,$FF58
    ld ix,$1234
    ld iy,$5678
{body}
    ld ($4100),sp
    ld ($4102),ix
    ld ($4104),iy
    jp 0
    defs $4300-$,0
{extra}
"""
    source.write_text("\n".join(line if line.endswith(":") else "    " + line.lstrip()
                                for line in assembly.splitlines()))
    result = subprocess.run(["sjasmplus", "--nologo", "--dirbol", "--raw=" + str(binary), str(source)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    code = binary.read_bytes()
    memory[0x4000:0x4000 + len(code)] = code
    return run(memory, 0x4000, 0, directory, cpu, cycles)


def abi(result):
    assert result[0x4100:0x4106] == bytes.fromhex("58ff34127856"), "SP/IX/IY changed"


def numeric(symbols, memory, directory, cpu):
    cases = ("", "x", "12x", "00000000000000060", "65535", "65536", "65537",
             "131072", "262144", "524288", "999999999999999999999999")
    for value in cases:
        sample = bytearray(memory)
        string(sample, 0x5000, value)
        result = execute(sample, f"ld hl,$5000\ncall {symbols['_str_to_u16']}\nld ($4200),hl", "", directory, cpu)
        prefix = re.match(r"[0-9]+", value)
        expected = min(int(prefix[0]), 65535) if prefix else 0
        assert int.from_bytes(result[0x4200:0x4202], "little") == expected, ("decimal overflow", value)
        abi(result)
    print("Decimal prefix: valid limits, saturation and ABI OK")


def auth(symbols, memory, directory, cpu):
    cases = (("", "EvilServ", "NOTICE", "victim", False),
             ("", "NickServ", "NOTICE", "victim", True),
             ("", "NiCkSeRv", "NOTICE", "victim", True),
             ("Auth", "NickServ", "NOTICE", "victim", False),
             ("Auth", "AuTh", "NOTICE", "victim", True),
             ("Auth", "EvilServ", "NOTICE", "victim", False),
             ("", "NickServ", "NOTICE", "#room", False),
             ("", "NickServ", "PRIVMSG", "victim", False))
    for service, sender, command, target, allowed in cases:
        sample = bytearray(memory)
        sample[symbols["_connection_state"]] = 3
        for name in ("_badge_flash_on", "_main_print", "_main_puts"):
            sample[symbols[name]:symbols[name] + 2] = b"\xaf\xc9"
        jump(sample, symbols["_notify"], 0)
        jump(sample, symbols["_ay_uart_send"], 0x4300)
        for name, value in (("_irc_server", "irc.test"), ("_irc_nick", "victim"),
                            ("_nickserv_pass", "TEST_ONLY"), ("_nickserv_nick", service)):
            string(sample, symbols[name], value)
        string(sample, 0x5000, f":{sender}!user@host {command} {target} :please identify")
        result = execute(sample, f"ld hl,$5500\nld ($4200),hl\nld hl,$5000\ncall {symbols['_parse_irc_message']}",
                         """push hl
    ld a,l
    ld hl,($4200)
    ld (hl),a
    inc hl
    ld ($4200),hl
    pop hl
    or a
    ret""", directory, cpu)
        end = int.from_bytes(result[0x4200:0x4202], "little")
        # The stored login is sent at end of MOTD; no NOTICE, trusted or not,
        # makes SpecTalkZX send the password.
        assert result[0x5500:end] == b"", ("NOTICE triggered identify", service, sender, command, target, result[0x5500:end])
        assert result[symbols["_nickserv_nick"]:symbols["_nickserv_nick"] + len(service) + 1] == service.encode() + b"\0"
        abi(result)
    print("Auto-identify: no NOTICE from any sender sends the password")


def timeout(symbols, memory, directory, cpu):
    for mode, expected_waits, expected_code in (("empty", 3, 6), ("short", 3, 6),
                                               ("last-success", 3, 1), ("error", 1, 5), ("cancel", 1, 2)):
        sample = bytearray(memory)
        jump(sample, symbols["_frame_wait_drain"], 0x4300)
        sample[symbols["_in_inkey"]:symbols["_in_inkey"] + 4] = bytes((0x21, 3 if mode == "cancel" else 0, 0, 0xC9))
        jump(sample, symbols["_try_read_line_nodrain"], 0x4400)
        string(sample, symbols["_rx_line"], "ERROR" if mode == "error" else "CONNECT")
        sample[symbols["_rx_last_len"]:symbols["_rx_last_len"] + 2] = (1 if mode == "short" else 7).to_bytes(2, "little")
        read = "ld hl,0\nret" if mode == "empty" else "ld hl,1\nret"
        if mode == "last-success":
            read = "ld a,($4200)\ncp 3\nld hl,0\nret nz\ninc l\nret"
        result = execute(sample, f"ld hl,3\ncall {symbols['_classic_wait_connect']}\nld ($4201),hl", f"""
    ld a,($4200)
    inc a
    ld ($4200),a
    cp 8
    jp z,0
    ret
    defs $4400-$,0
{read}""", directory, cpu)
        assert result[0x4200] == expected_waits and result[0x4201] == expected_code, ("connect timeout", mode, result[0x4200:0x4203])
        abi(result)
    print("Connection wait: short-line deadline, final-frame success, error and cancellation OK")


def bookmarks(symbols, memory, directory, cpu, folder):
    atlas = (folder / "SPECTALK.OVL").read_bytes()
    assert atlas[:4] == b"STOA"
    offset = int.from_bytes(atlas[36:38], "little")  # <offset,size> for atlas id 7
    size = int.from_bytes(atlas[38:40], "little")
    sample = bytearray(memory)
    sample[0xF500:0xF500 + size] = atlas[offset:offset + size]
    sample[symbols["_autoconnect"]] = 0
    font, end = symbols["font_lut"], symbols["bpe_dict"] + 222
    sample[font:end] = (folder / "SPECTALK.DAT").read_bytes()[:end - font]
    for name, target in (("_esx_fopen", 0x4300), ("_esx_fread", 0x4400), ("_esx_fclose", 0x4420)):
        jump(sample, symbols[name], target)
    sample[symbols["_overlay_rx_release"]] = 0xC9
    assert int.from_bytes(sample[0xF500:0xF502], "little") == 5
    entry = int.from_bytes(sample[0xF506:0xF508], "little")  # count word, then entry 2
    result = execute(sample, f"ld hl,$5700\nld ($4200),hl\ncall {entry}", f"""
    ld de,($4200)
copy_path:
    ld a,(hl)
    inc hl
    ld (de),a
    inc de
    or a
    jr nz,copy_path
    ld ($4200),de
    ld a,($4202)
    inc a
    ld ($4202),a
    cp 1
    ld a,1
    jr nz,open_done
    xor a
open_done:
    ld ({symbols['_esx_handle']}),a
    ret
    defs $4400-$,0
    ld hl,0
    ld ({symbols['_esx_result']}),hl
    ret
    defs $4420-$,0
    ret""", directory, cpu)
    end = int.from_bytes(result[0x4200:0x4202], "little")
    paths = result[0x5700:end].rstrip(b"\0").split(b"\0")
    expected = [b"/SYS/CONFIG/SPTBM1.CFG", b"/SYS/SPTBM1.CFG"]
    expected += [f"/SYS/CONFIG/SPTBM{slot}.CFG".encode() for slot in range(2, 6)]
    assert paths == expected, ("bookmark fallback", paths)
    abi(result)
    print("Classic SPCTLK8: fallback does not poison later primary paths; ABI OK")


def registration(symbols, memory, directory, cpu):
    lines = ("PING :keepalive", ":server CAP * LS :cap", ":server 433 victim :busy", "@badtag")
    for line in lines:
        sample = bytearray(memory)
        sample[symbols["_connection_state"]] = 1
        for name in ("_force_disconnect", "_classic_clock_init", "_sntp_udp_fallback",
                     "_classic_net_prepare", "_draw_status_bar", "_redraw_input_full",
                     "_main_print", "_main_puts", "_main_putc", "_uart_send_string", "_ay_uart_send"):
            sample[symbols[name]:symbols[name] + 2] = b"\xaf\xc9"
        sample[symbols["_in_inkey"]:symbols["_in_inkey"] + 4] = b"\x21\x00\x00\xc9"
        sample[symbols["_classic_net_start_stream"]:symbols["_classic_net_start_stream"] + 4] = b"\x21\x01\x00\xc9"
        for name, target in (("_frame_wait_drain", 0x4300), ("_try_read_line_nodrain", 0x4400),
                             ("_classic_net_connect", 0x4480), ("_ui_err", 0x44A0)):
            jump(sample, symbols[name], target)
        for name, value in (("_irc_server", "irc.test"), ("_irc_port", "6667"), ("_irc_nick", "victim")):
            string(sample, symbols[name], value)
        string(sample, 0x5000, line)
        result = execute(sample, f"ld hl,0\ncall {symbols['_cmd_connect']}", f"""
    ld hl,($4200)
    inc hl
    ld ($4200),hl
    ld de,3008
    or a
    sbc hl,de
    jp z,0
    ret
    defs $4400-$,0
    ld hl,$5000
    ld de,{symbols['_rx_line']}
    ld bc,{len(line) + 1}
    ldir
    ld hl,{len(line)}
    ld ({symbols['_rx_last_len']}),hl
    ld hl,1
    ret
    defs $4480-$,0
    pop bc
    pop hl
    pop hl
    inc sp
    push bc
    ld hl,1
    ret
    defs $44A0-$,0
    ld ($4202),hl
    ret""", directory, cpu, cycles=20000000)
        assert int.from_bytes(result[0x4200:0x4202], "little") == 3001, ("registration deadline", line)
        assert result[0x4202:0x4204] != b"\0\0", "registration timeout was not reported"
        abi(result)
    print("Registration: PING/CAP/433/malformed-tag streams all reach the absolute deadline")


def tx(symbols, memory, directory, cpu):
    regs = symbols["_spxn_regs"]
    faults = {"carry": "ld l,1\nret", "excess": f"ld hl,({regs + 1})\ninc hl\nld ({regs + 1}),hl\nld l,0\nret",
              "stalled": f"ld hl,0\nld ({regs + 1}),hl\nret",
              "partial": "ld a,($4202)\ncp 2\nld l,1\nret z\nld bc,2\njr write_count",
              "short": "ld bc,1\njr write_count",
              "zero-once": f"ld a,($4202)\ncp 1\njr nz,success\nld hl,0\nld ({regs + 1}),hl\nret",
              "normal": "jr success"}
    for mode, fault in faults.items():
        failed = mode in ("carry", "excess", "stalled", "partial")
        sample = bytearray(memory)
        sample[symbols["_connection_state"]] = 2
        sample[symbols["_net_open"]] = 1
        jump(sample, symbols["_spxn_rom_hlcall"], 0x4300)
        jump(sample, symbols["_spxn_resolve"], 0x4500)
        sample[symbols["_frame_wait"]] = 0xC9
        for address, value in ((0x5000, "PRIVMSG test :first"), (0x5050, "PING :ok"), (0x5080, "irc.test"), (0x50A0, "6667")):
            string(sample, address, value)
        body = f"ld hl,$5500\nld ($4200),hl\nld hl,$5000\ncall {symbols['_net_send_line']}\nld a,($4202)\nld ($4208),a"
        if failed:
            body += f"""
    call {symbols['_net_publish_closed']}
    ld hl,$5050
    call {symbols['_net_send_line']}
    ld a,($4202)
    ld ($4209),a
    call {symbols['_net_close']}
    ld a,1
    ld ($4207),a
    ld hl,0
    push hl
    inc sp
    ld hl,$50A0
    push hl
    ld hl,$5080
    push hl
    call {symbols['_net_connect']}
    ld a,l
    ld ($420A),a
    ld hl,$5050
    call {symbols['_net_send_line']}"""
        result = execute(sample, body, f"""
    ld a,l
    cp $12
    jr z,send
    cp $03
    jr nz,rom_ok
    ld a,($4203)
    inc a
    ld ($4203),a
rom_ok:
    ld l,0
    ret
send:
    ld a,($4202)
    inc a
    ld ($4202),a
    ld a,($4207)
    or a
    jr nz,success
{fault}
success:
    ld bc,({regs + 1})
write_count:
    ld ({regs + 1}),bc
    ld hl,({regs + 3})
    ld de,($4200)
    ldir
    ld ($4200),de
    ld l,0
    ret
    defs $4500-$,0
    pop bc
    pop hl
    pop hl
    push bc
    ld hl,0
    ret""", directory, cpu)
        end = int.from_bytes(result[0x4200:0x4202], "little")
        if failed:
            calls = {"carry": 1, "excess": 1, "stalled": 50, "partial": 2}[mode]
            assert result[0x4208] == calls and result[0x4209] == calls, ("TX after failure", mode, result[0x4208:0x420B])
            assert result[0x4203] == 1 and result[0x420A] == 1, "descriptor close/reconnect failed"
            assert result[symbols["_net_open"]] == 1 and result[symbols["_net_hup_pending"]] == 0
            assert result[0xF500:0xF508] == b"CLOSED\r\n", "deferred close not published"
            expected = (b"PR" if mode == "partial" else b"") + b"PING :ok\r\n"
        else:
            expected = b"PRIVMSG test :first\r\n"
            assert result[symbols["_net_open"]] == 1 and result[symbols["_net_hup_pending"]] == 0
        assert result[0x5500:end] == expected, ("TX payload", mode, result[0x5500:end])
        abi(result)
    print("Spectranext TX: carry/short/zero/excess, sticky failure, CLOSED and reconnect OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--only", choices=("numeric", "auth", "timeout", "registration", "bookmarks", "tx"))
    args = parser.parse_args()
    symbols, memory = load(args.folder)
    cpu = "z80n" if "_next_uart_status" in symbols else "z80"
    checks = {"numeric": numeric}
    if "_classic_wait_connect" in symbols:
        checks.update(auth=auth, timeout=timeout, registration=registration)
    if "_overlay_exec_active" in symbols:
        checks["bookmarks"] = lambda s, m, d, c: bookmarks(s, m, d, c, args.folder)
    if "_net_open" in symbols:
        checks["tx"] = tx
    if args.only:
        checks = {args.only: checks[args.only]}
    with tempfile.TemporaryDirectory(prefix="audit-fixes-cpu-") as temporary:
        for check in checks.values():
            check(symbols, memory, Path(temporary), cpu)


if __name__ == "__main__":
    main()
