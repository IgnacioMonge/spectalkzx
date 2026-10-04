#!/usr/bin/env python3
"""Check the generated direct resource: matching assets and remote launch."""

import hashlib
import json
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "build/spectranext-direct"
    package = json.loads((output / "package.json").read_text())
    entries = {item["name"]: item for item in package["files"]}
    assert set(entries) == {"boot.zx", "SPECTALK.TAP", "SPECTALK.DAT", "SPECTALK.OVL"}
    for name, item in entries.items():
        data = (output / name).read_bytes()
        assert len(data) == item["size"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        if name != "boot.zx":
            source = "SpecTalkZX-direct.tap" if name == "SPECTALK.TAP" else name
            assert data == (root / "build" / source).read_bytes(), name

    # Direct TAP: original CODE blocks, then the installer screen as SCREEN$.
    sys.path.insert(0, str(root / "tools"))
    from build_direct_tap import LOADER_OUT, split_blocks
    plain = split_blocks((root / "build/SpecTalkZX.tap").read_bytes())
    direct = split_blocks((output / "SPECTALK.TAP").read_bytes())
    screen = (root / "packaging/spectranext/loading.scr").read_bytes()
    assert len(direct) == 6 and direct[2:4] == plain[2:4]
    assert direct[1][3:-1] == b"\0\n" + len(LOADER_OUT).to_bytes(2, "little") + LOADER_OUT
    assert direct[4][2:4] == b"\0\3" and direct[4][14:20] == bytes.fromhex("001b00400080")
    assert direct[5][2] == 0xFF and direct[5][3:-1] == screen

    image = (output / "boot.zx").read_bytes()
    blocks = []
    while image:
        size = int.from_bytes(image[:2], "little")
        block, image = image[2:2 + size], image[2 + size:]
        assert size >= 2 and len(block) == size
        checksum = 0
        for byte in block:
            checksum ^= byte
        assert checksum == 0
        blocks.append(block)
    assert len(blocks) == 2 and blocks[0][:2] == b"\0\0"
    assert int.from_bytes(blocks[0][14:16], "little") == 10  # BASIC autostart
    program = blocks[1][1:-1]
    statement = program[4:]
    assert int.from_bytes(program[:2], "big") == 10
    assert int.from_bytes(program[2:4], "little") == len(statement)
    # %tapein on the inherited mount, then tokenized LOAD ""; no install/%fs.
    assert statement == b'%tapein"SPECTALK.TAP":\xef""\r'
    assert 'name=boot.zx ' in (output / "index.txt").read_text()
    print("Direct HTTPS package: matching assets, loading screen and inherited-mount launcher PASS")


if __name__ == "__main__":
    main()
