"""Measure native Next MOTD consumption in T-states with the linked image.

Usage: HOSTPYTHON tools/next_rx_throughput.py build/next [--lines N] [--stub SYMBOL]
The UART reports no data, keys are idle, the chat area is full so every line
scrolls; a 50 Hz IM1 stub advances FRAMES. Excludes contention, wait states
and the zxnDMA transfer itself (add 18,432 T per scrolled line). --stub turns
a routine into RET to measure its share. Budget at 115200 baud and
3.5 MHz: 3_500_000 / 11_520 = 304 T per byte.
"""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_audit_fixes_cpu import load, string  # noqa: E402

SRV = "irc.example.net"


def motd(lines):
    out = b""
    for i in range(lines):
        out += f":{SRV} 372 spectalk :- MOTD line {i:03d} abcdefghijklmnopqrstuvwxyz0123456789\r\n".encode()
        if i % 5 == 4:
            out += f"PING :M{i // 5:03d}-00\r\n".encode()
    return out


def patch(memory, address, code):
    memory[address : address + len(code)] = code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--lines", type=int, default=20)
    ap.add_argument("--stub", action="append", default=[])
    args = ap.parse_args()
    s, memory = load(args.folder)
    patch(memory, s["_next_uart_status"], b"\xaf\xc9")  # xor a; ret: idle UART
    patch(memory, s["_ay_uart_send"], b"\xb7\xc9")  # or a; ret: TX accepted
    for name in args.stub:
        patch(memory, s[name], bytes([0xC9]))  # ablation: ret
    patch(memory, s["_in_inkey"], b"\x2e\x00\xc9")  # ld l,0; ret: no key
    if "_clock_poll_rx" in s:
        patch(memory, s["_clock_poll_rx"], b"\x2e\x00\xc9")
    memory[s["_connection_state"]] = 3
    memory[s["_overlay_mode"]] = 0
    memory[s["_main_line"]] = 3 + 17 - 1
    memory[s["_main_col"]] = 0
    if "_notif_enabled" in s:
        memory[s["_notif_enabled"]] = 0
    string(memory, s["_irc_nick"], "spectalk")
    string(memory, s["_irc_server"], SRV)
    data = motd(args.lines)
    assert len(data) < 2048
    patch(memory, s["_ring_buffer"], data)
    memory[s["_rb_tail"] : s["_rb_tail"] + 2] = (0).to_bytes(2, "little")
    memory[s["_rb_head"] : s["_rb_head"] + 2] = len(data).to_bytes(2, "little")
    memory[s["_rx_pos"] : s["_rx_pos"] + 2] = b"\0\0"
    head, tail, proc = s["_rb_head"], s["_rb_tail"], s["_process_irc_data"]
    driver = bytes(
        [0xF3, 0x31, 0x58, 0xFF, 0xED, 0x56, 0xFB]  # di; ld sp,$FF58; im 1; ei
        + [0xFD, 0x21, 0x3A, 0x5C]  # ld iy,$5C3A
        + [0xCD, proc & 255, proc >> 8]  # loop: call process_irc_data
        + [0x2A, head & 255, head >> 8]  # ld hl,(rb_head)
        + [0xED, 0x5B, tail & 255, tail >> 8]  # ld de,(rb_tail)
        + [0xB7, 0xED, 0x52]  # or a; sbc hl,de
        + [0x20, 0xF1]  # jr nz,loop (-15)
        + [0xF3]  # di
        + [0x76]  # halt (end marker)
    )
    isr = bytes(
        [0xE5, 0x2A, 0x78, 0x5C, 0x23, 0x22, 0x78, 0x5C, 0xE1, 0xFB, 0xED, 0x4D]
    )  # FRAMES++
    patch(memory, 0x0038, isr)
    start = 0xFD60  # bottom of the 512-byte stack reserve, far below SP
    patch(memory, start, driver)
    end = start + len(driver) - 1
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.bin"
        src.write_bytes(memory)
        r = subprocess.run(
            [
                "z88dk-ticks",
                "-mz80n",
                "-pc",
                f"{start:04x}",
                "-start",
                f"{start:04x}",
                "-end",
                f"{end:04x}",
                "-int",
                "70000",
                "-counter",
                "400000000",
                "-output",
                str(Path(tmp) / "out.bin"),
                str(src),
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        out = (Path(tmp) / "out.bin").read_bytes()
    ticks = int(re.findall(r"\d+", r.stdout)[-1])
    left = (
        int.from_bytes(out[head : head + 2], "little")
        - int.from_bytes(out[tail : tail + 2], "little")
    ) & 2047
    per_byte = ticks / len(data)
    print(
        f"{len(data)} B, {args.lines} lines: {ticks} T = {per_byte:.0f} T/B "
        f"({ticks / args.lines:.0f} T/line); ring left {left}; "
        f"3.5 MHz capacity {3_500_000 / per_byte:.0f} B/s vs 11520 B/s arrival"
    )


if __name__ == "__main__":
    main()
