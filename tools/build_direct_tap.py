#!/usr/bin/env python3
"""Add the loading screen to the direct SpectraNext TAP.

usage: build_direct_tap.py IN_TAP SCREEN_SCR OUT_TAP

The input must be the exact z88dk loader plus one CODE block. The output keeps
that CODE header/data unchanged, then appends the screen as SCREEN$. The new
loader sets a black border, then shows it for up to two seconds; PAUSE ends
earlier on any key.
"""

import sys
from pathlib import Path

LOADER_IN = b'\xfd\xb0"23999":\xef""\xaf:\xf9\xc0\xb0"24000"\r'
LOADER_OUT = (b'\xfd\xb0"23999":\xe7\xb0"0":\xef""\xaf:\xef""\xaa:'
              b'\xf2\xb0"100":\xf9\xc0\xb0"24000"\r')
SCREEN_NAME = b"SpecTalkZX"


def block(payload):
    checksum = 0
    for byte in payload:
        checksum ^= byte
    data = payload + bytes([checksum])
    return len(data).to_bytes(2, "little") + data


def header(kind, name, length, param1, param2):
    return block(bytes([0, kind]) + name.ljust(10)[:10] + length.to_bytes(2, "little") +
                 param1.to_bytes(2, "little") + param2.to_bytes(2, "little"))


def split_blocks(tap):
    blocks = []
    while tap:
        size = int.from_bytes(tap[:2], "little")
        data, tap = tap[2:2 + size], tap[2 + size:]
        if size < 2 or len(data) != size:
            raise SystemExit("truncated TAP block")
        checksum = 0
        for byte in data:
            checksum ^= byte
        if checksum:
            raise SystemExit("bad TAP checksum")
        blocks.append(size.to_bytes(2, "little") + data)
    return blocks


def program(statement):
    return (10).to_bytes(2, "big") + len(statement).to_bytes(2, "little") + statement


def build(tap, screen):
    if len(screen) != 6912:
        raise SystemExit("loading screen must be 6912 bytes")
    blocks = split_blocks(tap)
    if len(blocks) != 4 or blocks[0][2:4] != b"\0\0" or blocks[2][2:4] != b"\0\3":
        raise SystemExit("unexpected TAP layout")
    if blocks[1][3:-1] != program(LOADER_IN):
        raise SystemExit("unexpected BASIC loader")
    basic = program(LOADER_OUT)
    return (header(0, b"Loader", len(basic), 10, len(basic)) + block(b"\xff" + basic) +
            blocks[2] + blocks[3] +
            header(3, SCREEN_NAME, 6912, 16384, 32768) + block(b"\xff" + screen))


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__.strip().splitlines()[2])
    tap, screen, out = (Path(arg) for arg in sys.argv[1:])
    out.write_bytes(build(tap.read_bytes(), screen.read_bytes()))
    print(f"Direct TAP with loading screen: {out}")


if __name__ == "__main__":
    main()
