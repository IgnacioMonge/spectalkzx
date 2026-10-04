#!/usr/bin/env python3
"""Regression checks for malformed STOA and embedded Next resources."""

from gen_next_nex import (
    DAT_MAX_SIZE,
    OVERLAY_BASE,
    checked_dat_bank_count,
    parse_atlas,
)
from overlay_atlas_probe import build_atlas
from test_next_nex_image import entry_is_valid


def rejected(data: bytes) -> None:
    try:
        parse_atlas(data)
    except SystemExit:
        return
    raise AssertionError("malformed atlas was accepted")


def main() -> None:
    overlays = []
    for _ in range(8):
        overlay = bytearray((1, 0, 0, 0, 0xC9))
        overlay[2:4] = (OVERLAY_BASE + 4).to_bytes(2, "little")
        overlays.append(bytes(overlay))
    packed = b"".join(item.ljust(8190, b"\0") for item in overlays)
    atlas = build_atlas(packed, [len(item) for item in overlays], 8190, 64)
    assert parse_atlas(atlas) == overlays

    malformed = bytearray(atlas)
    malformed[6:8] = (0xFFFF).to_bytes(2, "little")
    rejected(malformed)
    malformed = bytearray(atlas)
    malformed[8:10] = (0).to_bytes(2, "little")
    rejected(malformed)
    malformed = bytearray(atlas)
    malformed[10:12] = (8191).to_bytes(2, "little")
    rejected(malformed)
    malformed = bytearray(atlas)
    first = int.from_bytes(malformed[8:10], "little")
    malformed[first + 2:first + 4] = OVERLAY_BASE.to_bytes(2, "little")
    rejected(malformed)
    malformed = bytearray(atlas)
    malformed[first] = 255
    rejected(malformed)
    malformed = bytearray(atlas)
    malformed[first + 1] = 1
    rejected(malformed)

    # Full-width indexing must not wrap at entry 127 (offset 256).
    page = bytearray(8192)
    page[0] = 255
    page[-2:] = (513).to_bytes(2, "little")
    for entry in range(255):
        page[2 + 2 * entry:4 + 2 * entry] = (OVERLAY_BASE + 512).to_bytes(2, "little")
    for entry in (0, 126, 127, 128, 254):
        assert entry_is_valid(page, entry)
    assert not entry_is_valid(page, 255)
    page[1] = 1
    assert not entry_is_valid(page, 0)
    page[1] = 0
    page[-2:] = (8191).to_bytes(2, "little")
    assert not entry_is_valid(page, 0)

    assert DAT_MAX_SIZE == 32766
    assert checked_dat_bank_count(DAT_MAX_SIZE) == 2
    for size in (0, DAT_MAX_SIZE + 1):
        try:
            checked_dat_bank_count(size)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"invalid DAT size accepted: {size}")
    for kwargs in ({"sizes": []}, {"sizes": [0]}, {"sizes": [1] * 256}):
        try:
            build_atlas(b"", block_size=1, header_len=64, **kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid atlas build accepted: {kwargs}")
    print("overlay atlas and native resource validation passed")


if __name__ == "__main__":
    main()
