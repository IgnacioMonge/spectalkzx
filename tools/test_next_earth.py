"""Round-trip every native Earth pixel and reject invalid source assets."""
from io import BytesIO
from pathlib import Path
import tempfile
from zipfile import ZipFile

from PIL import Image

from next_earth import FIRST_BANK, FRAME_COUNT, FRAME_SIZE, LEVELS, PAGE_SIZE, SOURCE, STARFIELD_BANK, FRAME_BUFFER_PAGE, logo_pixels, pack_earth, pack_starfield
from test_earth_packet_bounds import valid_delta
from about_earth_polish import apply_delta


def main():
    packed = pack_earth()
    assert len(packed) % (2 * PAGE_SIZE) == 0
    assert FIRST_BANK * 2 + len(packed) // PAGE_SIZE <= FRAME_BUFFER_PAGE
    decoded = packed[:FRAME_SIZE]
    initial = decoded
    palette = packed[FRAME_SIZE:FRAME_SIZE + 512]
    colors = [(LEVELS[a >> 5], LEVELS[(a >> 2) & 7], LEVELS[((a & 3) << 1) | b])
              for a, b in zip(palette[::2], palette[1::2])]
    with ZipFile(SOURCE) as archive:
        for frame in range(FRAME_COUNT):
            entry = 2 * PAGE_SIZE + frame * 3
            page = packed[entry] - FIRST_BANK * 2
            offset = int.from_bytes(packed[entry + 1:entry + 3], "little")
            assert 0 < page < len(packed) // PAGE_SIZE and offset < FRAME_SIZE
            data = packed[page * PAGE_SIZE + offset:page * PAGE_SIZE + FRAME_SIZE]
            end = 0
            while data[end]:
                command = data[end]
                end += 1 + ((command & 127) + 1 if command & 128 else 0)
            delta = data[:end + 1]
            assert valid_delta(delta, FRAME_SIZE)
            decoded = apply_delta(decoded, delta)
            image = Image.open(BytesIO(archive.read(f"earth_{frame:03}.png")))
            pixels = image.load()
            for y in range(80):
                for x in range(80):
                    offset = ((y // 16) * 5 + x // 16) * 256 + (y % 16) * 16 + x % 16
                    index = decoded[offset]
                    r, g, b, alpha = pixels[x, y]
                    assert (index != 0) == bool(alpha)
                    if alpha:
                        assert colors[index] == (r, g, b), (frame, x, y)
        assert decoded == initial, "delta cycle must return to frame 47"

        with tempfile.TemporaryDirectory(prefix="next-earth-invalid-") as directory:
            bad = Path(directory) / "bad.zip"
            for fault in ("missing", "size", "alpha", "rgb"):
                with ZipFile(bad, "w") as output:
                    for name in archive.namelist():
                        if name == "earth_000.png":
                            if fault == "missing":
                                continue
                            image = Image.new("RGBA", (79, 80) if fault == "size" else (80, 80))
                            if fault == "alpha":
                                image.putpixel((0, 0), (0, 0, 0, 128))
                            if fault == "rgb":
                                image.putpixel((0, 0), (1, 0, 0, 255))
                            stream = BytesIO()
                            image.save(stream, format="PNG")
                            output.writestr(name, stream.getvalue())
                        else:
                            output.writestr(name, archive.read(name))
                try:
                    pack_earth(bad)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"accepted {fault}")

    logo, logo_colors = logo_pixels()
    patterns = packed[6912:8192] + packed[PAGE_SIZE + FRAME_SIZE:PAGE_SIZE + 7936]
    assert len(patterns) == 2816
    for y in range(32):
        for x in range(176):
            offset = ((y // 16) * 11 + x // 16) * 128 + (y % 16) * 8 + x % 16 // 2
            index = (patterns[offset] >> (0 if x % 2 else 4)) & 15
            assert index == logo[y * 176 + x]
            if index:
                assert colors[80 + index] == logo_colors[index - 1]
    assert not any(logo[176 * 24:])
    stars, star_palette = pack_starfield()
    assert len(stars) == 49152 and len(star_palette) == 512
    assert packed[2 * PAGE_SIZE + FRAME_SIZE:2 * PAGE_SIZE + FRAME_SIZE + 512] == star_palette
    for row in range(192):
        start = (3 + row // 7) * PAGE_SIZE + FRAME_SIZE + row % 7 * 256
        assert packed[start:start + 256] == stars[row * 256:(row + 1) * 256]
    assert sum(bool(p) for p in stars) > 1000
    for y in range(192):
        for x in range(256):
            index = stars[y * 256 + x]
            if not (8 <= x < 248 and 24 <= y < 104):
                assert index == 0
            if index:
                assert star_palette[index * 2] != 0
    asm = (SOURCE.parents[2] / "overlay/earth_next.asm").read_text()
    assert f"NEXT_EARTH_FIRST_PAGE = {FIRST_BANK * 2}" in asm
    assert f"NEXT_EARTH_FRAMES = {FRAME_COUNT}" in asm
    assert f"NEXT_STARFIELD_BANK = {STARFIELD_BANK}" in asm
    print("Next Earth: all 307200 pixels round-trip, RGB333/alpha/size/count and page layout OK")


if __name__ == "__main__":
    main()
