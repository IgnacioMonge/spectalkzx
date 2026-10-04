"""Render a 6912-byte ZX screen in the README style: 2.5x, 682x520, 20px margin."""

import struct
import sys
import zlib

NORMAL, BRIGHT = 0xC0, 0xFF


def rgb(index, bright):
    level = BRIGHT if bright else NORMAL
    return (
        level if index & 2 else 0,
        level if index & 4 else 0,
        level if index & 1 else 0,
    )


def pixels(scr):
    out = []
    for y in range(192):
        row = []
        for x in range(256):
            addr = ((y & 0xC0) << 5) | ((y & 7) << 8) | ((y & 0x38) << 2) | (x >> 3)
            bit = (scr[addr] >> (7 - (x & 7))) & 1
            attr = scr[6144 + (y >> 3) * 32 + (x >> 3)]
            bright = bool(attr & 0x40)
            row.append(rgb(attr & 7, bright) if bit else rgb((attr >> 3) & 7, bright))
        out.append(row)
    return out


def scale_25(img):
    """Nearest 5x, then 2x2 box average: 2.5x with half-pixel blending."""
    h, w = len(img), len(img[0])
    big = [[img[y // 5][x // 5] for x in range(w * 5)] for y in range(h * 5)]
    out = []
    for y in range(0, h * 5, 2):
        r0, r1 = big[y], big[min(y + 1, h * 5 - 1)]
        line = []
        for x in range(0, w * 5, 2):
            cs = (r0[x], r0[min(x + 1, w * 5 - 1)], r1[x], r1[min(x + 1, w * 5 - 1)])
            line.append(tuple(sum(c[i] for c in cs) // 4 for i in range(3)))
        out.append(line)
    return out


def png(img, path, width=682, height=520, left=21, top=20):
    rows = []
    for y in range(height):
        row = bytearray([0])
        sy = y - top
        for x in range(width):
            sx = x - left
            if 0 <= sy < len(img) and 0 <= sx < len(img[0]):
                row += bytes(img[sy][sx]) + b"\xff"
            else:
                row += b"\x00\x00\x00\xff"
        rows.append(bytes(row))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    data = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )
    open(path, "wb").write(data)


def main():
    scr = open(sys.argv[1], "rb").read()
    png(scale_25(pixels(scr)), sys.argv[2])


if __name__ == "__main__":
    main()
