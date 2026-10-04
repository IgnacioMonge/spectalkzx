"""Convert a ZEsarUX Next BMP to the README style.

usage: bmp2png.py IN.bmp OUT.png [raw]
Crops the 512x384 paper area, scales 5/4 with box filtering to 640x480 and
centres it on the 682x520 black canvas used by the other screenshots.
"""

import struct
import sys

from scr2png import png


def load_bmp(path):
    d = open(path, "rb").read()
    off = struct.unpack("<I", d[10:14])[0]
    w, h = struct.unpack("<ii", d[18:26])
    bpp = struct.unpack("<H", d[28:30])[0]
    assert bpp == 24
    stride = (w * 3 + 3) & ~3
    rows = []
    for y in range(abs(h)):
        src = (abs(h) - 1 - y) if h > 0 else y
        base = off + src * stride
        rows.append(
            [
                (d[base + x * 3 + 2], d[base + x * 3 + 1], d[base + x * 3])
                for x in range(w)
            ]
        )
    return rows


def find_paper(img):
    """Return the 512x384 paper area: border colour surrounds it."""
    h, w = len(img), len(img[0])
    left, top = (w - 512) // 2, (h - 384) // 2
    return [row[left : left + 512] for row in img[top : top + 384]]


def scale_54(img):
    h, w = len(img), len(img[0])
    out = []
    for oy in range(h * 5 // 4):
        line = []
        for ox in range(w * 5 // 4):
            acc = [0, 0, 0]
            for dy in range(4):
                for dx in range(4):
                    c = img[(oy * 4 + dy) // 5][(ox * 4 + dx) // 5]
                    acc[0] += c[0]
                    acc[1] += c[1]
                    acc[2] += c[2]
            line.append(tuple(v // 16 for v in acc))
        out.append(line)
    return out


def main():
    img = load_bmp(sys.argv[1])
    if len(sys.argv) > 3:
        png(img, sys.argv[2], len(img[0]), len(img), 0, 0)
        return
    png(scale_54(find_paper(img)), sys.argv[2])


if __name__ == "__main__":
    main()
