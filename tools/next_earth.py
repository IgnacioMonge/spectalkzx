"""Pack native Next SKIP/COPY globe deltas and shared RGB333/static resources."""
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from about_earth_polish import encode_delta


SOURCE = Path(__file__).resolve().parents[1] / "release/about_earth/earth_next_48.zip"
FIRST_BANK = 14  # Pages 28..75, after the two embedded DAT banks.
FRAME_COUNT = 48
PAGE_SIZE = 8192
FRAME_SIZE = 80 * 80
LEVELS = (0, 36, 73, 109, 146, 182, 219, 255)
LOGO_SOURCE = SOURCE.with_name("logo_next.png")
STARFIELD_BANK = FIRST_BANK + FRAME_COUNT // 2
FRAME_BUFFER_PAGE = 75
DELTA_TABLE_PAGE = FIRST_BANK * 2 + 2


def pack_starfield():
    with Image.open(SOURCE.with_name("starfield_oval_v1.png")) as source:
        image = source.resize((240, 80), Image.Resampling.LANCZOS)
    background = Image.new("RGBA", image.size, (0, 0, 0, 255))
    background.alpha_composite(image)
    image = background.convert("RGB").quantize(colors=255).convert("RGB")
    colors = [tuple((c * 7 + 127) // 255 for c in rgb)
              for rgb in image.get_flattened_data()]
    # Global transparency compares RGB332: both darkest blues are transparent.
    visible = sorted({rgb for rgb in colors if rgb[0] or rgb[1] or rgb[2] > 1})
    indices = {rgb: i + 1 for i, rgb in enumerate(visible)}
    palette = bytearray(512)
    for (r, g, b), index in indices.items():
        palette[2 * index:2 * index + 2] = bytes((r << 5 | g << 2 | b >> 1, b & 1))
    screen = bytearray(256 * 192)
    for y in range(80):
        screen[(y + 24) * 256 + 8:(y + 24) * 256 + 248] = bytes(
            indices.get(rgb, 0) for rgb in colors[y * 240:(y + 1) * 240])
    return bytes(screen), bytes(palette)


def logo_pixels():
    with Image.open(LOGO_SOURCE) as source:
        alpha = source.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
        logo = source.crop(alpha.getbbox()).resize((176, 24), Image.Resampling.LANCZOS)
    visible = logo.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    rgb = logo.convert("RGB").quantize(colors=15).convert("RGB")
    pixels = [(tuple(LEVELS[(c * 7 + 127) // 255] for c in p), a)
              for p, a in zip(rgb.get_flattened_data(), visible.get_flattened_data())]
    colors = sorted({p for p, a in pixels if a})
    indices = {p: i + 1 for i, p in enumerate(colors)}
    return bytes(indices[p] if a else 0 for p, a in pixels) + bytes(176 * 8), colors


def earth_assets(path=SOURCE):
    with ZipFile(path) as archive:
        names = [f"earth_{i:03}.png" for i in range(FRAME_COUNT)]
        if sorted(archive.namelist()) != names:
            raise ValueError("Next Earth requires exactly earth_000.png..earth_047.png")
        frames = []
        for name in names:
            with Image.open(BytesIO(archive.read(name))) as image:
                if image.size != (80, 80) or image.mode != "RGBA":
                    raise ValueError(f"{name}: expected 80x80 RGBA")
                pixels = list(image.get_flattened_data())
                if any(p[3] not in (0, 255) for p in pixels):
                    raise ValueError(f"{name}: alpha must be binary")
                frames.append(pixels)
    colors = sorted({p[:3] for frame in frames for p in frame if p[3]})
    if len(colors) > 79 or any(c not in LEVELS for rgb in colors for c in rgb):
        raise ValueError("Next Earth requires at most 79 RGB333 colours; logo reserves 80..95")
    indices = {rgb: i + 1 for i, rgb in enumerate(colors)}  # 0 is transparent.
    palette = bytearray(512)
    logo, logo_colors = logo_pixels()
    entries = list(indices.items()) + [(rgb, 81 + i) for i, rgb in enumerate(logo_colors)]
    for rgb, index in entries:
        r, g, b = (LEVELS.index(c) for c in rgb)
        palette[2 * index:2 * index + 2] = bytes((r << 5 | g << 2 | b >> 1, b & 1))
    sprite_frames = []
    for frame in frames:
        # 25 sequential 16x16 patterns, row-major within each sprite.
        pixels = bytes(indices[p[:3]] if p[3] else 0
                       for sy in range(0, 80, 16) for sx in range(0, 80, 16)
                       for y in range(sy, sy + 16) for x in range(sx, sx + 16)
                       for p in (frame[y * 80 + x],))
        sprite_frames.append(pixels)
    tiles = [logo[y * 176 + x]
             for sy in range(0, 32, 16) for sx in range(0, 176, 16)
             for y in range(sy, sy + 16) for x in range(sx, sx + 16)]
    patterns = bytes(a << 4 | b for a, b in zip(tiles[::2], tiles[1::2]))
    return sprite_frames, bytes(palette), patterns


def pack_earth(path=SOURCE):
    frames, palette, patterns = earth_assets(path)
    # Keep static-resource tail addresses; at least 31 pages hold the starfield.
    pages = bytearray(32 * PAGE_SIZE)
    pages[:FRAME_SIZE] = frames[-1]  # First tick applies the wrap delta to frame 0.
    pages[FRAME_SIZE:FRAME_SIZE + len(palette)] = palette
    page, offset = 1, 0
    for frame in range(FRAME_COUNT):
        delta = encode_delta(frames[(frame - 1) % FRAME_COUNT], frames[frame])
        if len(delta) > FRAME_SIZE:
            raise ValueError("Next Earth delta exceeds one page payload")
        while offset + len(delta) > FRAME_SIZE:
            page += 1
            offset = FRAME_COUNT * 3 if page == 2 else 0
        if (page + 1) * PAGE_SIZE > len(pages):
            pages.extend(bytes(2 * PAGE_SIZE))
        if FIRST_BANK * 2 + page >= FRAME_BUFFER_PAGE:
            raise ValueError("Next Earth deltas overlap the reconstruction buffer")
        entry = 2 * PAGE_SIZE + frame * 3
        pages[entry:entry + 3] = bytes((FIRST_BANK * 2 + page,)) + offset.to_bytes(2, "little")
        start = page * PAGE_SIZE + offset
        pages[start:start + len(delta)] = delta
        offset += len(delta)
    pages[6912:8192] = patterns[:1280]
    pages[PAGE_SIZE + FRAME_SIZE:PAGE_SIZE + FRAME_SIZE + 1536] = patterns[1280:]
    stars, star_palette = pack_starfield()
    pages[2 * PAGE_SIZE + FRAME_SIZE:2 * PAGE_SIZE + FRAME_SIZE + 512] = star_palette
    # Seven complete screen rows per spare page tail; no runtime codec needed.
    for row in range(192):
        start = (3 + row // 7) * PAGE_SIZE + FRAME_SIZE + row % 7 * 256
        pages[start:start + 256] = stars[row * 256:(row + 1) * 256]
    if FIRST_BANK * 2 + len(pages) // PAGE_SIZE > FRAME_BUFFER_PAGE:
        raise ValueError("Next Earth banks overlap the reconstruction buffer")
    return bytes(pages)
