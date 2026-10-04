#!/usr/bin/env python3
"""Verify the native NEX resident, overlay pages and DAT bytes."""

from __future__ import annotations

import argparse
from pathlib import Path

from next_earth import FIRST_BANK as EARTH_FIRST_BANK, STARFIELD_BANK, pack_earth

from gen_next_nex import (
    ABOUT_OVERLAY_INDEX,
    ABOUT_PACKET_OFFSET,
    BANK_SIZE,
    DAT_FIRST_BANK,
    HEADER_SIZE,
    MAIN_BASE,
    MAIN_BANKS,
    OVERLAY_BASE,
    OVERLAY_FIRST_BANK,
    OVERLAY_SIZE_OFFSET,
    PAGE_SIZE,
    parse_atlas,
    parse_map,
)


def entry_is_valid(page: bytes, entry_id: int) -> bool:
    """Mirror next_overlay_entry() for a deterministic padding-bound test."""
    count = page[0]
    size = int.from_bytes(page[OVERLAY_SIZE_OFFSET : PAGE_SIZE], "little")
    table_end = 2 + 2 * count
    if (size > OVERLAY_SIZE_OFFSET or table_end > size
            or not 0 <= entry_id < count or page[1]):
        return False
    item = 2 + 2 * entry_id
    target = int.from_bytes(page[item : item + 2], "little")
    return OVERLAY_BASE + table_end <= target < OVERLAY_BASE + size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nex", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--resident", type=Path, required=True)
    parser.add_argument("--ovl", type=Path, required=True)
    parser.add_argument("--dat", type=Path, required=True)
    parser.add_argument("--org", type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()

    symbols = parse_map(args.map)
    cleared_head = symbols["__data_compiler_tail"]
    cleared_tail = symbols["__bss_user_tail"]
    for symbol in (
        "next_dat_position", "next_dat_size", "next_dat_saved_mmu", "next_dat_page",
        "_next_overlay_active", "next_overlay_page", "next_saved_mmu1",
    ):
        assert cleared_head <= symbols[symbol] < cleared_tail, symbol

    image = args.nex.read_bytes()
    header = image[:HEADER_SIZE]
    assert header[:8] == b"NextV1.1"
    dat = args.dat.read_bytes()
    stored_source = len(dat).to_bytes(2, "little") + dat
    dat_bank_count = (len(stored_source) + BANK_SIZE - 1) // BANK_SIZE
    earth = pack_earth()
    earth_bank_ids = list(range(EARTH_FIRST_BANK, EARTH_FIRST_BANK + len(earth) // BANK_SIZE))
    bank_ids = ([bank for bank, _ in MAIN_BANKS]
                + list(range(OVERLAY_FIRST_BANK, OVERLAY_FIRST_BANK + 4))
                + list(range(DAT_FIRST_BANK, DAT_FIRST_BANK + dat_bank_count))
                + earth_bank_ids)
    assert len(set(bank_ids)) == len(bank_ids)
    assert header[9] == len(bank_ids)
    assert {bank for bank in range(112) if header[18 + bank]} == set(bank_ids)
    assert int.from_bytes(header[14:16], "little") == args.org

    payload = image[HEADER_SIZE:]
    assert len(payload) == len(bank_ids) * BANK_SIZE
    banks = {
        bank: payload[index * BANK_SIZE : (index + 1) * BANK_SIZE]
        for index, bank in enumerate(bank_ids)
    }

    main_memory = b"".join(banks[bank] for bank, _ in MAIN_BANKS)
    resident = args.resident.read_bytes()
    resident_at = args.org - MAIN_BASE
    assert main_memory[resident_at : resident_at + len(resident)] == resident

    atlas = args.ovl.read_bytes()
    overlapping = bytearray(atlas)
    overlapping[12:14] = overlapping[8:10]
    try:
        parse_atlas(overlapping)
    except SystemExit:
        pass
    else:
        raise AssertionError("overlapping overlay extents were accepted")

    overlay_bytes = b"".join(banks[bank] for bank in range(OVERLAY_FIRST_BANK, OVERLAY_FIRST_BANK + 4))
    for index, overlay in enumerate(parse_atlas(atlas)):
        page = overlay_bytes[index * PAGE_SIZE : (index + 1) * PAGE_SIZE]
        if index == ABOUT_OVERLAY_INDEX:
            assert len(overlay) <= ABOUT_PACKET_OFFSET
        assert page[: len(overlay)] == overlay
        assert int.from_bytes(page[OVERLAY_SIZE_OFFSET : PAGE_SIZE], "little") == len(overlay)
        assert not any(page[len(overlay) : OVERLAY_SIZE_OFFSET])
        assert all(entry_is_valid(page, entry_id) for entry_id in range(page[0]))

        corrupt = bytearray(page)
        corrupt[2:4] = OVERLAY_BASE.to_bytes(2, "little")
        assert not entry_is_valid(corrupt, 0)
        corrupt[2:4] = (0x2000 + len(overlay)).to_bytes(2, "little")
        assert not entry_is_valid(corrupt, 0)
        corrupt[OVERLAY_SIZE_OFFSET:PAGE_SIZE] = (0xFFFF).to_bytes(2, "little")
        for target in (0x2000 + OVERLAY_SIZE_OFFSET, 0x4000):
            corrupt[2:4] = target.to_bytes(2, "little")
            assert not entry_is_valid(corrupt, 0)

    stored_dat = b"".join(banks[bank] for bank in range(DAT_FIRST_BANK, DAT_FIRST_BANK + dat_bank_count))
    assert stored_dat[: len(stored_source)] == stored_source
    assert not any(stored_dat[len(stored_source) :])
    assert b"".join(banks[bank] for bank in earth_bank_ids) == earth
    assert all(bank not in banks for bank in range(STARFIELD_BANK, STARFIELD_BANK + 3))
    assert int.from_bytes(header[12:14], "little") == symbols["__register_sp"]
    print("NEX resident, eight overlay pages, DAT and 48 colour Earth frames verified byte for byte")


if __name__ == "__main__":
    main()
