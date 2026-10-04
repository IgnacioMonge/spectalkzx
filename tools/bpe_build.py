#!/usr/bin/env python3
"""
BPE build orchestrator for SpecTalkZX.
Called by Makefile before compilation.

Pipeline:
  1. Copy src/*.c + include/*.h to build/bpe_src/ (working copies)
  2. Apply SB_ renames + structural patches + new SB_ constants
  3. Run BPE compression -> build/bpe_final/*.c
  4. Copy compressed files back to src/ for compilation
  5. Generate SPECTALK.DAT with BPE dict inserted

src/ originals are backed up to build/bpe_originals/ and restored
after compilation by a trap or explicit restore step.
"""

import os
import re
import sys
import shutil
import subprocess
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SCRIPT_DIR)
BUILD_DIR = os.path.join(ROOT, "build")
BPE_STAMP = os.path.join(BUILD_DIR, ".bpe.stamp")
BACKUP_DIR = os.path.join(BUILD_DIR, "bpe_originals")
HELP_TEXT_PATH = os.path.join(ROOT, "src", "SPECTALK_HELP.txt")
EARTH_DIR = os.path.join(ROOT, "release", "about_earth")

SRC_FILES = ["spectalk.c", "irc_handlers.c", "user_cmds.c"]
HDR_FILES = ["spectalk.h"]

BACKUP_FILES = [
    (os.path.join("src", "spectalk.c"), "spectalk.c"),
    (os.path.join("src", "irc_handlers.c"), "irc_handlers.c"),
    (os.path.join("src", "user_cmds.c"), "user_cmds.c"),
    (os.path.join("include", "spectalk.h"), "spectalk.h"),
    (os.path.join("src", "SPECTALK.DAT"), "SPECTALK.DAT"),
    (os.path.join("overlay", "overlay_api.h"), "overlay_api.h"),
    (os.path.join("overlay", "overlay_entry2.asm"), "overlay_entry2.asm"),
    (os.path.join("overlay", "earth_about_render.asm"), "earth_about_render.asm"),
]

# Internal display-only codepoint: UTF-8 ñ/Ñ maps to byte 127.
# The 64-col renderer accepts 32..127, while BPE tokens start at 128.
SPANISH_N_CODE = 127
SPANISH_N_PACKED = bytes((0x6C, 0xAA, 0xAA))
DAT_BASE_SIZE = 373
EARTH_FRAME_COUNT = 24
EARTH_FRAME0_SIZE = 587
EARTH_ATTR0_SIZE = 44
EARTH_LOGO_SIZE = 528
EARTH_PACKET_SIZE_LIMIT = 512
EARTH_PACKET_SIZE_TARGET = 512
EARTH_LOGO_W_BYTES = 22
EARTH_LOGO_H = 24
EARTH_LOGO_ATTR_H = 3

# Constants audited as safe for BPE (screen-only)
SAFE_CONSTANTS = [
    "S_NOTCONN",
    "S_FAIL",
    "S_NOTSET",
    "S_APPNAME",
    "S_COPYRIGHT",
    "S_MAXWIN",
    "S_SWITCHTO",
    "S_TIMEOUT",
    "S_NOWIN",
    "S_RANGE_MINUTES",
    "S_MUST_CHAN",
    "S_ARROW_IN",
    "S_ARROW_OUT",
    "S_EMPTY_PAT",
    "S_ALREADY_IN",
    "S_TOPIC_PFX",
    "S_CONN_REFUSED",
    "S_INIT_DOTS",
    "S_ON",
    "S_OFF",
    "S_CONNECTED",
    "S_DOTS3",
    "S_NICK_INUSE",
    "S_AS_SP",
    "S_MIN",
    "S_DOT_SP",
    "S_USAGE_MSG",
    "S_JOINED_SP",
    "S_SMART",
    "S_SP_LBRACKET",
]

# New SB_ constants for indirect screen-only usage. Each row drives the
# declaration, definition, and source replacement so they cannot drift.
SB_CONSTANTS = (
    ("SB_ABORTED", "Aborted.", 'abort_msg = "Aborted.";'),
    ("SB_INVALID_NICK", "Invalid nick", 'abort_msg = "Invalid nick";'),
    ("SB_AUTH_FAILED", "Auth failed", 'abort_msg = "Auth failed";'),
    ("SB_BANNED", "Banned", 'abort_msg = "Banned";'),
    ("SB_SERVER_ERR", "Server error", 'abort_msg = "Server error";'),
    ("SB_CONN_LOST", "Connection lost", 'abort_msg = "Connection lost";'),
    ("SB_WIFI_OK", "WiFi OK", 'st = "WiFi OK";'),
    ("SB_IRC_READY", "IRC ready", 'st = "IRC ready";'),
    ("SB_UNKNOWN_MODE", "(unknown)", 'mode_text = "(unknown)";'),
)

NEW_SB_CONSTANTS_DECL = "\n" + "\n".join(
    f"extern const char {symbol}[];" for symbol, _, _ in SB_CONSTANTS
)
NEW_SB_CONSTANTS_DEF = "\n".join(
    f'const char {symbol}[] = "{literal}";'
    for symbol, literal, _ in SB_CONSTANTS
)


def read_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def apply_sb_renames(content):
    """Rename S_xxx -> SB_xxx for audited safe constants."""
    for old in SAFE_CONSTANTS:
        new = "SB_" + old[2:]
        content = re.sub(r"\b" + re.escape(old) + r"\b", new, content)
    return content


def patch_spectalk_c(content, bpe_load_size=691):
    """Apply structural patches for BPE support."""
    # esx_count for SPECTALK.DAT with dict (dynamic based on actual dict size)
    content = content.replace("esx_count = 373;", f"esx_count = {bpe_load_size};")
    content = content.replace("esx_result < 373", f"esx_result < {bpe_load_size}")

    # BPE bypass in main_print fast path
    content = content.replace(
        "        while (*p && len < SCREEN_COLS) { p++; len++; }",
        "        while (*p && len < SCREEN_COLS) {\n"
        "            if ((uint8_t)*p >= 0x80) goto slow_path;\n"
        "            p++; len++;\n"
        "        }",
    )
    content = content.replace(
        "        // Texto largo - usar slow path para wrap\n    }",
        "        // Texto largo - usar slow path para wrap\n    }\n    slow_path:",
    )

    # Add new SB_ constant definitions after S_AUTOAWAY
    content = content.replace(
        'const char S_AUTOAWAY[] = "Auto-away";',
        'const char S_AUTOAWAY[] = "Auto-away";\n' + NEW_SB_CONSTANTS_DEF,
    )
    return content


def patch_spectalk_h(content):
    """Add new SB_ extern declarations."""
    content = content.replace(
        "extern const char S_AUTOAWAY[];",
        "extern const char S_AUTOAWAY[];" + NEW_SB_CONSTANTS_DECL,
    )
    return content


def patch_user_cmds_c(content, bpe_load_size=691):
    """Apply help offset and abort_msg/status patches."""
    content = content.replace("ring_buffer + 373", f"ring_buffer + {bpe_load_size}")

    # Replace inline literals with SB_ constants
    for symbol, _, context in SB_CONSTANTS:
        if context.startswith(("abort_msg =", "st =")):
            lhs = context.split("=", 1)[0]
            content = content.replace(context, lhs + "= " + symbol + ";")
    return content


def patch_irc_handlers_c(content):
    """Replace (unknown) mode text."""
    for symbol, _, context in SB_CONSTANTS:
        if context.startswith("mode_text ="):
            lhs = context.split("=", 1)[0]
            content = content.replace(context, lhs + "= " + symbol + ";")
            break
    return content


EXPECTED_DAT_SIZE = 1517  # src/SPECTALK.DAT without BPE dict (font+themes+help)
BPE_POISON_MARKER = "SB_ABORTED"  # only exists after BPE patching


def validate_sources():
    """Abort if src/ files are already BPE-modified or SPECTALK.DAT is wrong size.
    Prevents cascading corruption from a previous failed build."""
    dat_path = os.path.join(ROOT, "src", "SPECTALK.DAT")
    dat_size = os.path.getsize(dat_path)
    if dat_size != EXPECTED_DAT_SIZE:
        print(
            f"  [BPE ABORT] src/SPECTALK.DAT is {dat_size} bytes, "
            f"expected {EXPECTED_DAT_SIZE}. Sources are corrupted.",
            file=sys.stderr,
        )
        print(
            f"  Restore from a Development/ backup: "
            f"cp Development/16_v1.3.7_stable/SPECTALK.DAT src/",
            file=sys.stderr,
        )
        sys.exit(1)

    spectalk_c = read_file(os.path.join(ROOT, "src", "spectalk.c"))
    if BPE_POISON_MARKER in spectalk_c:
        print(
            f"  [BPE ABORT] src/spectalk.c contains '{BPE_POISON_MARKER}' — "
            f"already BPE-patched. Sources are corrupted.",
            file=sys.stderr,
        )
        print(
            f"  Restore from a Development/ backup or bpe_originals/", file=sys.stderr
        )
        sys.exit(1)


def validate_backup(backup_dir):
    """Verify bpe_originals/ backup is clean before we trust it for restore."""
    missing = [name for _, name in BACKUP_FILES if not os.path.isfile(os.path.join(backup_dir, name))]
    if missing:
        raise SystemExit(
            "  [BPE ABORT] Backup is incomplete: " + ", ".join(missing)
        )

    dat_bak = os.path.join(backup_dir, "SPECTALK.DAT")
    sz = os.path.getsize(dat_bak)
    if sz != EXPECTED_DAT_SIZE:
        raise SystemExit(
            f"  [BPE ABORT] Backup SPECTALK.DAT is {sz} bytes, "
            f"expected {EXPECTED_DAT_SIZE}. Backup is corrupted."
        )

    sc_bak = os.path.join(backup_dir, "spectalk.c")
    if BPE_POISON_MARKER in read_file(sc_bak):
        raise SystemExit(
            f"  [BPE ABORT] Backup spectalk.c contains '{BPE_POISON_MARKER}' — "
            f"backup is corrupted."
        )


def files_match(path_a, path_b):
    """Exact comparison for the small BPE source set."""
    if os.path.getsize(path_a) != os.path.getsize(path_b):
        return False
    with open(path_a, "rb") as file_a, open(path_b, "rb") as file_b:
        return file_a.read() == file_b.read()


def atomic_restore_file(src, dst):
    """Replace one live file atomically while retaining the backup source."""
    fd, temp_path = tempfile.mkstemp(prefix=".bpe-restore-", dir=os.path.dirname(dst))
    os.close(fd)
    try:
        shutil.copy2(src, temp_path)
        os.replace(temp_path, dst)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def restore_backup():
    """Restore a validated backup, retaining it until every copy is verified."""
    if os.path.exists(BACKUP_DIR) and not os.path.isdir(BACKUP_DIR):
        raise SystemExit("  [BPE ABORT] bpe_originals exists but is not a directory")
    if not os.path.isdir(BACKUP_DIR):
        if os.path.exists(BPE_STAMP):
            raise SystemExit("  [BPE ABORT] BPE stamp exists without its backup")
        validate_sources()
        return False

    validate_backup(BACKUP_DIR)
    for rel_path, name in BACKUP_FILES:
        atomic_restore_file(
            os.path.join(BACKUP_DIR, name), os.path.join(ROOT, rel_path)
        )

    validate_sources()
    for rel_path, name in BACKUP_FILES:
        live_path = os.path.join(ROOT, rel_path)
        backup_path = os.path.join(BACKUP_DIR, name)
        if not files_match(live_path, backup_path):
            raise SystemExit(f"  [BPE ABORT] Restore verification failed: {rel_path}")

    if os.path.exists(BPE_STAMP):
        os.remove(BPE_STAMP)
    shutil.rmtree(BACKUP_DIR)
    return True


def prepare_backup():
    """Recover stale state, then atomically create one clean backup."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    if os.path.isdir(BACKUP_DIR):
        restore_backup()

    validate_sources()
    staging = tempfile.mkdtemp(prefix="bpe_originals.tmp-", dir=BUILD_DIR)
    try:
        for rel_path, name in BACKUP_FILES:
            shutil.copy2(os.path.join(ROOT, rel_path), os.path.join(staging, name))
        validate_backup(staging)
        os.rename(staging, BACKUP_DIR)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def split_delta_stream(data, target_size, label):
    """Split SKIP/COPY delta stream using command semantics, not raw zero bytes."""
    parts = []
    off = 0
    while off < len(data):
        start = off
        pos = 0
        while True:
            if off >= len(data):
                raise ValueError(f"{label}: truncated delta at {start}")
            cmd = data[off]
            off += 1
            if cmd == 0:
                break
            if cmd < 0x80:
                pos += cmd
            else:
                n = (cmd & 0x7F) + 1
                off += n
                pos += n
            if off > len(data) or pos > target_size:
                raise ValueError(f"{label}: malformed delta at {start}")
        parts.append(data[start:off])
    return parts


def load_earth_assets():
    """Load about Earth assets and build one tick stream with length prefixes."""
    paths = {
        "frame0": os.path.join(EARTH_DIR, "earth_frame0.compact.bin"),
        "frame_deltas": os.path.join(EARTH_DIR, "earth_frame_deltas.bin"),
        "attr0": os.path.join(EARTH_DIR, "earth_attr0.compact4.bin"),
        "attr_deltas": os.path.join(EARTH_DIR, "earth_attr_deltas.compact4.bin"),
        "logo": os.path.join(EARTH_DIR, "earth_logo.bin"),
    }
    try:
        frame0 = open(paths["frame0"], "rb").read()
        attr0 = open(paths["attr0"], "rb").read()
        logo = open(paths["logo"], "rb").read()
        frame_parts = split_delta_stream(
            open(paths["frame_deltas"], "rb").read(), EARTH_FRAME0_SIZE, "frame"
        )
        attr_parts = split_delta_stream(
            open(paths["attr_deltas"], "rb").read(), EARTH_ATTR0_SIZE, "attr"
        )
    except OSError as exc:
        raise SystemExit(f"  [BPE ABORT] missing Earth asset: {exc}") from exc

    if len(frame0) != EARTH_FRAME0_SIZE:
        raise SystemExit(f"  [BPE ABORT] frame0 is {len(frame0)} bytes")
    if len(attr0) != EARTH_ATTR0_SIZE:
        raise SystemExit(f"  [BPE ABORT] attr0 is {len(attr0)} bytes")
    if len(logo) != EARTH_LOGO_SIZE:
        raise SystemExit(f"  [BPE ABORT] logo is {len(logo)} bytes")
    if len(frame_parts) != EARTH_FRAME_COUNT or len(attr_parts) != EARTH_FRAME_COUNT:
        raise SystemExit("  [BPE ABORT] Earth delta frame count mismatch")

    packets = []
    for frame_delta, attr_delta in zip(frame_parts, attr_parts):
        if len(attr_delta) > 255:
            raise SystemExit(f"  [BPE ABORT] attr delta too large: {len(attr_delta)}")
        packet_size = 2 + len(frame_delta) + 1 + len(attr_delta)
        if packet_size > EARTH_PACKET_SIZE_LIMIT:
            raise SystemExit(f"  [BPE ABORT] Earth packet too large: {packet_size}")
        packet = bytearray()
        packet.extend(len(frame_delta).to_bytes(2, "little"))
        packet.extend(frame_delta)
        packet.append(len(attr_delta))
        packet.extend(attr_delta)
        packets.append(packet)

    deltas = bytearray()
    for packet in packets:
        packet.extend(b"\0" * (EARTH_PACKET_SIZE_TARGET - len(packet)))
        deltas.extend(packet)

    return frame0, attr0, logo, bytes(deltas), EARTH_PACKET_SIZE_TARGET


def patch_overlay_api_offsets(path, bpe_help_offset, earth_offsets):
    content = read_file(path)
    replacements = {
        "BPE_HELP_OFFSET": bpe_help_offset,
        **earth_offsets,
        "EARTH_FRAME_COUNT": EARTH_FRAME_COUNT,
        "EARTH_FRAME0_SIZE": EARTH_FRAME0_SIZE,
        "EARTH_ATTR0_SIZE": EARTH_ATTR0_SIZE,
        "EARTH_LOGO_SIZE": EARTH_LOGO_SIZE,
        "EARTH_LOGO_W_BYTES": EARTH_LOGO_W_BYTES,
        "EARTH_LOGO_H": EARTH_LOGO_H,
        "EARTH_LOGO_ATTR_H": EARTH_LOGO_ATTR_H,
    }
    for name, value in replacements.items():
        content = re.sub(rf"#define {name} \d+", f"#define {name} {value}", content)
    write_file(path, content)


def patch_overlay_entry2_consts(path, earth_offsets):
    """Keep the hand-written about tick ASM in sync with generated DAT layout."""
    content = read_file(path)
    replacements = {
        "EARTH_PACKET_SIZE": earth_offsets["EARTH_PACKET_SIZE"],
        "EARTH_FRAME_COUNT": EARTH_FRAME_COUNT,
        "EARTH_DELTA_OFFSET": earth_offsets["EARTH_DELTA_OFFSET"],
    }
    for name, value in replacements.items():
        content, count = re.subn(
            rf"(DEFC\s+{name}\s*=\s*)\d+",
            rf"\g<1>{value}",
            content,
        )
        if count != 1:
            raise SystemExit(f"  [BPE ABORT] could not patch {name} in {path}")
    write_file(path, content)


def patch_earth_render_consts(path, earth_offsets):
    """Keep the about renderer's initial DAT seeks in sync with generated layout."""
    content = read_file(path)
    replacements = {
        "EARTH_FRAME0_OFFSET": earth_offsets["EARTH_FRAME0_OFFSET"],
        "EARTH_FRAME0_SIZE": EARTH_FRAME0_SIZE,
        "EARTH_ATTR0_SIZE": EARTH_ATTR0_SIZE,
        "EARTH_ATTR0_OFFSET": earth_offsets["EARTH_ATTR0_OFFSET"],
        "EARTH_DELTA_OFFSET": earth_offsets["EARTH_DELTA_OFFSET"],
        "EARTH_PACKET_SIZE": earth_offsets["EARTH_PACKET_SIZE"],
    }
    for name, value in replacements.items():
        content, count = re.subn(
            rf"(DEFC\s+{name}\s*=\s*)\d+",
            rf"\g<1>{value}",
            content,
        )
        if count != 1:
            raise SystemExit(f"  [BPE ABORT] could not patch {name} in {path}")
    write_file(path, content)


def build_bpe():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from bpe_compress import (
        extract_string_literals,
        build_corpus,
        bpe_compress,
        generate_compressed_sources,
        generate_dict_binary,
        BPE_DICT_BSS_SIZE,
    )

    bpe_src = os.path.join(BUILD_DIR, "bpe_src")
    bpe_final = os.path.join(BUILD_DIR, "bpe_final")
    os.makedirs(bpe_src, exist_ok=True)
    os.makedirs(bpe_final, exist_ok=True)

    # Step 1: Copy and patch sources with a placeholder BPE load size;
    # offset will be corrected in Step 4b after dict size is known.
    for f in SRC_FILES:
        content = read_file(os.path.join(ROOT, "src", f))
        content = apply_sb_renames(content)
        if f == "spectalk.c":
            content = patch_spectalk_c(content)
        elif f == "user_cmds.c":
            content = patch_user_cmds_c(content)
        elif f == "irc_handlers.c":
            content = patch_irc_handlers_c(content)
        write_file(os.path.join(bpe_src, f), content)

    for f in HDR_FILES:
        content = read_file(os.path.join(ROOT, "include", f))
        content = apply_sb_renames(content)
        content = patch_spectalk_h(content)
        write_file(os.path.join(bpe_src, f), content)

    # Step 2: Run BPE compression
    src_paths = [os.path.join(bpe_src, f) for f in SRC_FILES]
    strings = extract_string_literals(src_paths)
    corpus = build_corpus(strings)
    compressed, dictionary = bpe_compress(corpus, max_tokens=BPE_DICT_BSS_SIZE // 3)

    screen_count = sum(1 for s in strings if s["screen_only"])
    content_bytes = sum(1 for b in corpus if b != 0)
    compressed_bytes = sum(1 for b in compressed if b != 0)

    # Step 3: Generate compressed sources
    generate_compressed_sources(src_paths, strings, dictionary, bpe_final)

    # Step 4: Generate dict binary and compute help offset
    dict_bin = generate_dict_binary(dictionary)
    dict_path = os.path.join(BUILD_DIR, "bpe_dict.bin")
    with open(dict_path, "wb") as f:
        f.write(dict_bin)

    bpe_load_size = DAT_BASE_SIZE + len(
        dict_bin
    )  # font + themes + BPE dict loaded at startup

    (
        earth_frame0,
        earth_attr0,
        earth_logo,
        earth_deltas,
        earth_packet_size,
    ) = load_earth_assets()
    earth_offset = bpe_load_size
    delta_unaligned = (
        earth_offset + len(earth_frame0) + len(earth_attr0) + len(earth_logo)
    )
    earth_delta_pad = (-delta_unaligned) % 512
    earth_delta_offset = delta_unaligned + earth_delta_pad
    earth_offsets = {
        "EARTH_FRAME0_OFFSET": earth_offset,
        "EARTH_ATTR0_OFFSET": earth_offset + len(earth_frame0),
        "EARTH_LOGO_OFFSET": earth_offset + len(earth_frame0) + len(earth_attr0),
        "EARTH_DELTA_OFFSET": earth_delta_offset,
        "EARTH_DELTA_SIZE": len(earth_deltas),
        "EARTH_PACKET_SIZE": earth_packet_size,
    }
    earth_block = (
        earth_frame0
        + earth_attr0
        + earth_logo
        + (b"\0" * earth_delta_pad)
        + earth_deltas
    )
    subprocess.check_call(
        [sys.executable, os.path.join(ROOT, "tools", "gen_whatsnew.py")],
        cwd=ROOT,
    )
    wn_logo_path = os.path.join(BUILD_DIR, "whatsnew_logo.bin")
    with open(wn_logo_path, "rb") as f:
        wn_logo = f.read()
    if not wn_logo:
        raise SystemExit("  [BPE ABORT] build/whatsnew_logo.bin is empty")
    wn_logo_offset = earth_offset + len(earth_block)
    earth_offsets["WN_LOGO_OFFSET"] = wn_logo_offset
    help_offset = wn_logo_offset + len(wn_logo)

    # Step 4b: Fix offsets in compressed sources if dict size differs from default
    DEFAULT_OFFSET = 691  # legacy placeholder patched to the real BPE load size
    if bpe_load_size != DEFAULT_OFFSET:
        for f in ["spectalk.c", "user_cmds.c"]:
            path = os.path.join(bpe_final, f)
            content = read_file(path)
            content = content.replace(
                f"esx_count = {DEFAULT_OFFSET};", f"esx_count = {bpe_load_size};"
            )
            content = content.replace(
                f"esx_result < {DEFAULT_OFFSET}", f"esx_result < {bpe_load_size}"
            )
            content = content.replace(
                f"ring_buffer + {DEFAULT_OFFSET}", f"ring_buffer + {bpe_load_size}"
            )
            write_file(path, content)

    # Step 4c: Patch overlay_api.h with actual help/Earth offsets
    ovl_api = os.path.join(ROOT, "overlay", "overlay_api.h")
    patch_overlay_api_offsets(ovl_api, help_offset, earth_offsets)
    patch_overlay_entry2_consts(
        os.path.join(ROOT, "overlay", "overlay_entry2.asm"), earth_offsets
    )
    patch_earth_render_consts(
        os.path.join(ROOT, "overlay", "earth_about_render.asm"), earth_offsets
    )

    # Step 5: Generate SPECTALK.DAT with dict + help segment padding
    dat_orig = os.path.join(ROOT, "src", "SPECTALK.DAT")
    with open(dat_orig, "rb") as f:
        orig = f.read()

    reserved = orig[:10]  # zero; former LUT slot keeps DAT offsets
    packed = bytearray(orig[10:298])
    # Patch glyph slot 127 (DEL, not typeable by input) as display-only ñ.
    # Row patterns 6,C,A,A,A,A -> tilde row + compact 'n' body.
    n_tilde_off = (SPANISH_N_CODE - 32) * 3
    packed[n_tilde_off : n_tilde_off + 3] = SPANISH_N_PACKED

    header = bytearray(reserved)
    header.extend(packed)
    header.extend(orig[298:373])  # themes
    with open(HELP_TEXT_PATH, "rb") as f:
        help_text = f.read()  # tracked help text source

    # Pad help text so 512-byte segment boundaries never split a line.
    # Split into lines and reassemble with NUL padding at boundaries.
    help_lines = help_text.split(b"\n")
    padded = bytearray()
    for i, line in enumerate(help_lines):
        content = line.rstrip(b"\r")
        line_with_nl = len(content) + (1 if i < len(help_lines) - 1 else 0)
        line_start = len(padded)
        line_end = line_start + line_with_nl
        seg_boundary = ((line_start // 512) + 1) * 512
        if line_start < seg_boundary <= line_end and len(content) > 0:
            # This line would cross a 512B boundary — pad with NUL bytes
            # so segment ends cleanly. skip_partial in overlay treats
            # bytes before first \n as partial (skips them), but NUL bytes
            # terminate the segment string, so no partial to skip.
            while len(padded) < seg_boundary:
                padded.append(0x00)
        padded.extend(content)
        if i < len(help_lines) - 1:
            padded.append(0x0A)

    dat_out = os.path.join(BUILD_DIR, "SPECTALK.DAT")
    with open(dat_out, "wb") as f:
        f.write(bytes(header) + dict_bin + earth_block + wn_logo + bytes(padded))

    # Step 6: Install compressed files for compilation
    for f in SRC_FILES:
        shutil.copy2(os.path.join(bpe_final, f), os.path.join(ROOT, "src", f))
    shutil.copy2(
        os.path.join(bpe_src, "spectalk.h"), os.path.join(ROOT, "include", "spectalk.h")
    )
    shutil.copy2(dat_out, os.path.join(ROOT, "src", "SPECTALK.DAT"))

    # Report
    saved = content_bytes - compressed_bytes
    print(
        f"  BPE: {screen_count} strings, {len(dictionary)} tokens, "
        f"{content_bytes}B -> {compressed_bytes}B (-{saved}B), "
        f"Earth {len(earth_block)}B ({earth_packet_size}B packets), "
        f"whatsnew logo {len(wn_logo)}B @{wn_logo_offset}, help @{help_offset}"
    )


def main():
    prepare_backup()
    try:
        build_bpe()
    except BaseException:
        try:
            restore_backup()
        except BaseException as restore_error:
            print(f"  [BPE ABORT] Automatic restore failed: {restore_error}", file=sys.stderr)
        raise


def cli():
    if sys.argv[1:] == ["--restore"]:
        restore_backup()
        return
    if sys.argv[1:]:
        raise SystemExit("Usage: bpe_build.py [--restore]")

    main()


if __name__ == "__main__":
    cli()
