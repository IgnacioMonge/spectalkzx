#!/usr/bin/env python3
"""Build-only probe for a variable-length SpecTalkZX overlay atlas."""

from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path


MAGIC = b"STOA"
VERSION = 1
DEFAULT_HEADER_LEN = 64
DEFAULT_BLOCK_SIZE = 2048


def parse_sizes(text: str) -> list[int]:
    sizes = [0] * 8
    found = False
    for match in re.finditer(r"SPCTLK([1-8])\.OVL:\s+(\d+)\s+bytes", text):
        idx = int(match.group(1)) - 1
        sizes[idx] = int(match.group(2))
        found = True
    if not found:
        raise ValueError("no SPCTLK*.OVL size lines found")
    missing = [str(i + 1) for i, size in enumerate(sizes) if size == 0]
    if missing:
        raise ValueError("missing overlay sizes: " + ", ".join(missing))
    return sizes


def parse_size_list(text: str) -> list[int]:
    sizes = [int(part.strip()) for part in text.split(",") if part.strip()]
    if not sizes:
        raise ValueError("empty size list")
    return sizes


def build_atlas(
    packed: bytes, sizes: list[int], block_size: int, header_len: int,
    prefix: bytes = b"", prefix_size: int = 0,
) -> bytes:
    if not 0 < len(sizes) <= 0xFF:
        raise ValueError("overlay count must fit one byte")
    if not 8 <= header_len <= 0xFFFF:
        raise ValueError("header length must fit one word")
    if not 0 < block_size <= 0xFFFF or prefix_size < 0:
        raise ValueError("block and prefix sizes must fit the atlas format")
    if len(packed) < block_size * len(sizes):
        raise ValueError("packed overlay is smaller than size list requires")
    if header_len < 8 + 4 * len(sizes):
        raise ValueError("header is too small for overlay table")
    if len(prefix) > prefix_size:
        raise ValueError(f"prefix size {len(prefix)} exceeds {prefix_size}")

    chunks = []
    offset = header_len + prefix_size
    table = bytearray()

    for idx, size in enumerate(sizes):
        if size < 1 or size > block_size:
            raise ValueError(f"overlay {idx + 1} size {size} outside 1..{block_size}")
        if offset + size > 0xFFFF:
            raise ValueError("atlas offsets exceed the 16-bit format")
        start = idx * block_size
        chunks.append(packed[start : start + size])
        table += struct.pack("<HH", offset, size)
        offset += size

    header = bytearray()
    header += MAGIC
    header += bytes((VERSION, len(sizes)))
    header += struct.pack("<H", header_len)
    header += table
    header += bytes(header_len - len(header))
    return bytes(header) + prefix.ljust(prefix_size, b"\0") + b"".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pack fixed overlay blocks into a build-only variable atlas."
    )
    parser.add_argument(
        "--packed", default="build/SPECTALK.OVL", help="fixed packed overlay file"
    )
    parser.add_argument(
        "--out", default="build/SPECTALK.OVA", help="prototype atlas output"
    )
    parser.add_argument("--sizes", help="comma-separated exact overlay sizes")
    parser.add_argument(
        "--sizes-from-log", help="file containing SPCTLK*.OVL build lines"
    )
    parser.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE)
    parser.add_argument("--header-len", type=int, default=DEFAULT_HEADER_LEN)
    parser.add_argument("--prefix", help="binary payload placed after the header")
    parser.add_argument("--prefix-size", type=int, default=0)
    parser.add_argument("--no-write", action="store_true", help="measure only")
    args = parser.parse_args()

    if args.sizes:
        sizes = parse_size_list(args.sizes)
    elif args.sizes_from_log:
        sizes = parse_sizes(
            Path(args.sizes_from_log).read_text(encoding="utf-8", errors="replace")
        )
    else:
        raise SystemExit("provide --sizes or --sizes-from-log")

    packed_path = Path(args.packed)
    packed = packed_path.read_bytes()
    prefix = Path(args.prefix).read_bytes() if args.prefix else b""
    atlas = build_atlas(
        packed, sizes, args.block_size, args.header_len, prefix, args.prefix_size
    )

    payload = sum(sizes)
    fixed = args.prefix_size + args.block_size * len(sizes)
    saving = fixed - len(atlas)
    slack = fixed - payload

    print("overlay_sizes=" + "/".join(str(size) for size in sizes))
    print(f"fixed_size={fixed}")
    print(f"payload_size={payload}")
    print(f"fixed_slack={slack}")
    print(f"atlas_header={args.header_len}")
    if args.prefix_size:
        print(f"atlas_prefix={args.prefix_size}")
    print(f"atlas_size={len(atlas)}")
    print(f"atlas_saving={saving}")

    if not args.no_write:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(atlas)
        print(f"wrote={out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
