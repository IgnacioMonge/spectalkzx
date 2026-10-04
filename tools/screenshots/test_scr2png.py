"""Check the gallery geometry: 682x520 canvas, black margin, 2.5x paper."""

from scr2png import pixels, scale_25

scr = bytes([0xFF] * 6144) + bytes([0x45] * 768)  # bright cyan ink everywhere
img = scale_25(pixels(scr))
assert (len(img[0]), len(img)) == (640, 480)
assert img[0][0] == img[479][639] == (0, 0xFF, 0xFF)

half = bytes([0x00] * 6144) + bytes([0x38] * 768)  # white paper, normal
assert scale_25(pixels(half))[10][10] == (0xC0, 0xC0, 0xC0)
print("scr2png geometry OK")
