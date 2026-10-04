#!/usr/bin/env python3
"""Build a self-contained SpecTalkZX NEX with page-resident overlays."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from next_earth import FIRST_BANK as EARTH_FIRST_BANK, pack_earth


HEADER_SIZE = 512
BANK_SIZE = 16384
PAGE_SIZE = 8192
OVERLAY_SIZE_TRAILER = 2
OVERLAY_SIZE_OFFSET = PAGE_SIZE - OVERLAY_SIZE_TRAILER
OVERLAY_MAX_SIZE = OVERLAY_SIZE_OFFSET
OVERLAY_BASE = 0x2000
ABOUT_OVERLAY_INDEX = 1
ABOUT_PACKET_SIZE = 512
ABOUT_PACKET_OFFSET = OVERLAY_SIZE_OFFSET - ABOUT_PACKET_SIZE
MAIN_BASE = 0x4000
MAIN_BANKS = ((5, 0x4000), (2, 0x8000), (0, 0xC000))
OVERLAY_FIRST_BANK = 8
DAT_FIRST_BANK = 12
DAT_MAX_SIZE = 2 * BANK_SIZE - 2
OVERLAY_COUNT = 8


def parse_map(path: Path) -> dict[str, int]:
    pattern = re.compile(r"^(\w+)\s+=\s+\$([0-9A-Fa-f]+)\s+;")
    return {
        match.group(1): int(match.group(2), 16)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if (match := pattern.match(line))
    }


def parse_atlas(data: bytes) -> list[bytes]:
    if len(data) < 8 or data[:4] != b"STOA" or data[4] != 1:
        raise SystemExit("invalid overlay atlas")
    count = data[5]
    header_len = int.from_bytes(data[6:8], "little")
    if (count != OVERLAY_COUNT or header_len < 8 + count * 4
            or header_len > len(data)):
        raise SystemExit("unexpected overlay atlas layout")
    overlays = []
    previous_end = header_len
    for index in range(count):
        item = 8 + index * 4
        offset = int.from_bytes(data[item : item + 2], "little")
        size = int.from_bytes(data[item + 2 : item + 4], "little")
        if (not size or size > OVERLAY_MAX_SIZE or offset < previous_end
                or offset + size > len(data)):
            raise SystemExit(f"invalid overlay {index + 1} extent")
        overlay = data[offset : offset + size]
        entry_count = overlay[0]
        table_end = 2 + 2 * entry_count
        if not entry_count or table_end > size or overlay[1]:
            raise SystemExit(f"invalid overlay {index + 1} entry table")
        for entry in range(entry_count):
            item = 2 + 2 * entry
            target = int.from_bytes(overlay[item : item + 2], "little")
            if not OVERLAY_BASE + table_end <= target < OVERLAY_BASE + size:
                raise SystemExit(f"invalid overlay {index + 1} entry {entry}")
        overlays.append(overlay)
        previous_end = offset + size
    return overlays


def checked_dat_bank_count(size: int) -> int:
    if not 0 < size <= DAT_MAX_SIZE:
        raise SystemExit(f"DAT size {size} exceeds two NEX banks")
    return (size + 2 + BANK_SIZE - 1) // BANK_SIZE


def build_header(banks: list[int], pc: int, sp: int) -> bytearray:
    header = bytearray(HEADER_SIZE)
    header[:8] = b"NextV1.1"
    header[9] = len(banks)
    header[12:14] = sp.to_bytes(2, "little")
    header[14:16] = pc.to_bytes(2, "little")
    for bank in banks:
        header[18 + bank] = 1
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--resident", type=Path, required=True)
    parser.add_argument("--ovl", type=Path, required=True)
    parser.add_argument("--dat", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--org", type=lambda value: int(value, 0), default=24000)
    args = parser.parse_args()

    symbols = parse_map(args.map)
    pc = symbols.get("__crt_org_code")
    sp = symbols.get("__register_sp")
    data_tail = symbols.get("__data_compiler_tail")
    if None in (pc, sp, data_tail) or pc != args.org:
        raise SystemExit("missing or inconsistent resident map symbols")

    resident = args.resident.read_bytes()
    resident_len = data_tail - args.org
    if len(resident) != resident_len or args.org + resident_len > 0x10000:
        raise SystemExit("resident image does not match the map")

    main_memory = bytearray(3 * BANK_SIZE)
    main_memory[args.org - MAIN_BASE : args.org - MAIN_BASE + resident_len] = resident

    overlay_pages = bytearray(OVERLAY_COUNT * PAGE_SIZE)
    overlays = parse_atlas(args.ovl.read_bytes())
    for index, overlay in enumerate(overlays):
        if index == ABOUT_OVERLAY_INDEX and len(overlay) > ABOUT_PACKET_OFFSET:
            raise SystemExit("SPCTLK2 payload overlaps native About packet scratch")
        start = index * PAGE_SIZE
        overlay_pages[start : start + len(overlay)] = overlay
        overlay_pages[start + OVERLAY_SIZE_OFFSET : start + PAGE_SIZE] = len(overlay).to_bytes(2, "little")

    dat = args.dat.read_bytes()
    dat_bank_count = checked_dat_bank_count(len(dat))
    stored_dat = len(dat).to_bytes(2, "little") + dat
    dat_banks = bytearray(dat_bank_count * BANK_SIZE)
    dat_banks[: len(stored_dat)] = stored_dat

    overlay_banks = list(range(OVERLAY_FIRST_BANK, OVERLAY_FIRST_BANK + 4))
    data_bank_ids = list(range(DAT_FIRST_BANK, DAT_FIRST_BANK + dat_bank_count))
    earth = pack_earth()
    earth_bank_ids = list(range(EARTH_FIRST_BANK, EARTH_FIRST_BANK + len(earth) // BANK_SIZE))
    banks = [bank for bank, _ in MAIN_BANKS] + overlay_banks + data_bank_ids + earth_bank_ids
    image = build_header(banks, pc, sp)
    image.extend(main_memory)
    image.extend(overlay_pages)
    image.extend(dat_banks)
    image.extend(earth)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    sizes = "/".join(str(len(overlay)) for overlay in overlays)
    print(f"[OK] {args.out}: banks {','.join(map(str, banks))}; overlays {sizes}; "
          f"DAT {len(dat)}; NEX {len(image)} bytes")


if __name__ == "__main__":
    main()
