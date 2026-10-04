"""Focused host regressions for UI/protocol assembly safety contracts."""

from pathlib import Path
from bpe_compress import generate_dict_binary
from bpe_build import patch_spectalk_c


ROOT = Path(__file__).resolve().parents[1]
PREFIX = b"+CIPSNTPTIME:"


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def between(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    return source[begin : source.index(end, begin)]


def main_print_uses_slow_path(data: bytes) -> bool:
    return len(data) > 64 or 10 in data or any(byte >= 0x80 for byte in data)


def names_tokens(data: bytes) -> list[bytes]:
    tokens = []
    pos = 0
    while pos < len(data):
        while pos < len(data) and data[pos] < 33:
            pos += 1
        start = pos
        while pos < len(data) and data[pos] >= 33:
            pos += 1
        if start != pos:
            tokens.append(data[start:pos])
    return tokens


def wrap_cut(data: bytes, column: int) -> int:
    available = 64 - column
    if len(data) <= available:
        return len(data)
    last_space = data.rfind(b" ", 0, available)
    return last_space if last_space > 0 else available


def parse_sntp(line: bytes) -> tuple[int, int, int] | None:
    if not line.startswith(PREFIX):
        return None
    payload = line[len(PREFIX) :]
    fields = payload.split()
    for pos, value in enumerate(fields):
        if len(value) != 8 or value[2:3] != b":" or value[5:6] != b":":
            continue
        digits = value[0:2] + value[3:5] + value[6:8]
        if any(byte < ord("0") or byte > ord("9") for byte in digits):
            continue
        hour, minute, second = (int(value[0:2]), int(value[3:5]), int(value[6:8]))
        if hour >= 24 or minute >= 60 or second >= 60:
            continue
        if pos + 1 < len(fields) and fields[pos + 1] == b"1970":
            continue
        return hour, minute, second
    return None


def irc_command(cmd: str, p1: str | None, p2: str | None) -> str:
    wire = cmd
    if p1:
        wire += " " + p1
    if p2 is not None:
        wire += " :" + p2
    return wire + "\r\n"


def valid_bpe_dictionary(dictionary: bytes) -> bool:
    if len(dictionary) != 74 * 3:
        return False
    token = 0x80
    for pos in range(0, len(dictionary), 3):
        left, right, terminator = dictionary[pos : pos + 3]
        if not left or not right or left >= token or right >= token or terminator:
            return False
        token += 1
    return True


def expand_bpe(data: bytes, dictionary: bytes) -> bytes:
    output = bytearray()
    stack = list(reversed(data))
    while stack:
        byte = stack.pop()
        if byte < 0x80:
            output.append(byte)
        elif byte <= 0xC9:
            pos = (byte - 0x80) * 3
            stack.extend((dictionary[pos + 1], dictionary[pos]))
        # Invalid high tokens are dropped, matching the display decoder.
    return bytes(output)


def behavior_regressions() -> None:
    for column in (0, 6):
        width = 64 - column
        exact = b"A " + b"B" * (width - 2)
        assert wrap_cut(exact, column) == width
        assert wrap_cut(exact[:-1], column) == width - 1
        assert wrap_cut(exact + b"C", column) == 1
        assert wrap_cut(b"A" * (width + 1), column) == width

    # The former fast scan accepted LF, so print_line64_fast blanked it and the
    # following text instead of letting main_puts perform an embedded newline.
    assert main_print_uses_slow_path(b"left\nright")
    assert not main_print_uses_slow_path(b"plain")

    # The former NAMES skip loop consumed only spaces; TAB repeatedly created
    # empty cells without advancing its input pointer.
    assert names_tokens(b"\t alice\x1fbob\r\n") == [b"alice", b"bob"]

    valid = PREFIX + b"Mon Sep 07 23:59:58 2026"
    assert parse_sntp(valid) == (23, 59, 58)
    clock_end = valid.index(b"23:59:58") + 8
    for end in range(clock_end):
        assert parse_sntp(valid[:end]) is None
    assert parse_sntp(valid[:clock_end]) == (23, 59, 58)
    for digit_pos in (0, 1, 3, 4, 6, 7):
        clock = bytearray(b"23:59:58")
        clock[digit_pos] = ord("X")
        assert parse_sntp(PREFIX + bytes(clock)) is None
    assert parse_sntp(PREFIX + b"24:00:00") is None
    assert parse_sntp(PREFIX + b"23:60:00") is None
    assert parse_sntp(PREFIX + b"23:59:60") is None
    assert parse_sntp(PREFIX + b"112:00:00") is None
    assert parse_sntp(PREFIX + b"12:00:00X") is None
    assert parse_sntp(PREFIX + b"Thu Jan 01 00:00:00 1970") is None
    assert parse_sntp(b"+CIPSNTXTIME:Mon Sep 07 23:59:58 2026") is None

    original = (7, 8, 9)
    parsed = parse_sntp(PREFIX + b"12:99:00")
    state = original
    if parsed is not None:
        state = parsed
    assert state == original

    assert irc_command("AWAY", None, None) == "AWAY\r\n"
    assert irc_command("TOPIC", "#zx", "") == "TOPIC #zx :\r\n"

    dictionary = b"AB\0" * 74
    assert valid_bpe_dictionary(dictionary)
    generated = generate_dict_binary([(65, 66), (0x80, 67)])
    assert len(generated) == 222 and valid_bpe_dictionary(generated)
    assert expand_bpe(b"\x81", generated) == b"ABC"
    patched = patch_spectalk_c("esx_count = 373; if (esx_result < 373)", 595)
    assert "esx_count = 595; if (esx_result < 595)" in patched
    missing_nul = bytearray(dictionary)
    missing_nul[2] = 1
    assert not valid_bpe_dictionary(missing_nul)
    cycle = bytearray(dictionary)
    cycle[0] = 0x80
    assert not valid_bpe_dictionary(cycle)
    future_reference = bytearray(dictionary)
    future_reference[3] = 0x81
    assert not valid_bpe_dictionary(future_reference)
    assert expand_bpe(b"X\x80\xCAZ", dictionary) == b"XABZ"


def source_contracts() -> None:
    output = text("asm/spectalk_asm/50_main_output.asm")
    slow = between(output, "mp_slow:", "mp_fast:")
    assert "call _main_puts" in slow and "ld a, 0" in slow
    assert slow.index("ld (_wrap_indent), a") < slow.index("ret nz") < slow.index("jp _main_newline")
    assert "xor a" not in slow
    # main_col=64 alone also describes a successfully completed full row.
    # Preserve the existing Z completion contract instead of treating it as cancel.
    done = between(output, "puts_opt_done:", "; uint8_t is_ignored")
    instructions = [line.split(";", 1)[0].strip() for line in done.splitlines()[1:]]
    assert [line for line in instructions if line] == ["ld a, b", "ld (_main_col), a", "ret"]
    pop = between(output, "puts_bpe_pop:", "puts_opt_done:")
    assert "cp 0xD3" in pop and "jr z, puts_opt_done" in pop
    exact = between(output, "mpwr_scan_next:", "mpwr_use_space:")
    assert exact.index("ld a, (hl)") < exact.index("jr z, mpwr_cut_end") < exact.index("ld hl, (mpwr_last_space)")
    reload = between(output, "puts_reload_nl:", "; --- BPE expansion")
    assert "ld c, a\n    ld (_g_ps64_attr), a" in reload
    screen = text("asm/spectalk_asm/40_text_numeric_screen.asm")
    hline = between(screen, "_main_hline:", "; void uart_drain_to_buffer")
    assert hline.index("call nz, _main_newline") < hline.index("cp 64") < hline.index("ret z") < hline.index("call _compute_screen_base")
    scan = between(output, "mp_scan:", "mp_bpe_slow:")
    assert scan.index("cp 10") < scan.index("jr z, mp_bpe_slow") < scan.index("add a, a")
    names = between(output, "nrg_skip_spaces:", "nrg_token:")
    assert "cp 33" in names and "jr nc, nrg_token" in names and "inc hl" in names
    bpe = between(output, "puts_bpe_expand:", "puts_bpe_overflow:")
    assert bpe.index("inc de") < bpe.index("cp 0xCA") < bpe.index("jp nc, puts_opt_loop")

    rendering = text("asm/spectalk_asm/30_rendering.asm")
    fast = between(rendering, "_print_line64_fast:", "plf_pair_loop:")
    assert "ld a, (_plf_start_byte)\n    cp 32\n    jp nc, plf_no_ldir" in fast
    validator = between(rendering, "_bpe_validate:", "; GLYPH DECOMPRESSOR")
    for contract in ("ld b, 74", "ld c, 0x80", "cp c", "or a", "djnz bv_entry"):
        assert contract in validator
    assert rendering.count("PUBLIC _bpe_validate") == 1

    protocol = text("asm/spectalk_asm/60_protocol_storage.asm")
    assert "call _main_puts\n    pop hl\n    ret nz" in protocol
    p2 = between(protocol, "isci_check_p2:", "isci_crlf:")
    assert "or l" in p2 and "jr z, isci_crlf" in p2
    assert "ld a, (hl)" not in p2
    about = between(protocol, "DEFC ABOUT_PUMP_LINE_MAX", "ap_overflow:")
    assert "DEFC ABOUT_PUMP_LINE_MAX    = 510" in about
    assert "jr c, ap_overflow" in about and "jr z, ap_overflow" in about

    lookup = text("asm/spectalk_asm/70_input_lookup.asm")
    sntp = between(lookup, "_sntp_process_response:", "; void sntp_udp_fallback")
    assert "IFNDEF SPECTALK_SPECTRANEXT\nPUBLIC _sntp_process_response" in lookup
    assert "IFNDEF SPECTALK_SPECTRANEXT\nPUBLIC _sntp_udp_fallback" in lookup
    assert 'defm "+CIPSNTPTIME:"' in sntp
    assert "ld b, 13" in sntp and sntp.count("call spr_parse2_checked") == 3
    assert "cp 24" in sntp and sntp.count("cp 60") == 2
    assert "spr_skip_token:" in sntp and "cp 33" in sntp
    first_store = sntp.index("ld (_time_hour), a")
    assert sntp.index("spr_found:") < first_store
    assert "ld (_time_minute), a" in sntp[first_store:]
    assert "ld (_time_second), a" in sntp[first_store:]
    parser = sntp[sntp.index("spr_parse2_checked:") :]
    assert parser.count("cp 10") == 2 and "scf" in parser

    # puts_u8_nolz is intentionally two-digit: all reachable callers validate
    # autoaway <=60 or timezone absolute value <=12.
    local = text("overlay/local_cmds_ovl.c")
    timezone = text("overlay/overlay_entry5.asm")
    assert "raw > 60" in local and local.count("puts_u8_nolz(") == 2
    assert "cp 13" in timezone and timezone.count("_puts_u8_nolz") == 2

    app = text("src/spectalk.c")
    redraw = between(app, "void redraw_input_full(void)", "static void input_clear")
    assert redraw.index("input_cache_invalidate();") < redraw.index("redraw_input_asm();")
    cursor = between(app, "void refresh_cursor_char(", "// Wrappers to avoid")
    assert "print_char64(row, col, c, ATTR_INPUT);" in cursor
    assert "input_cache_char[r][col] = (uint8_t)c;" in cursor


def main() -> None:
    behavior_regressions()
    source_contracts()
    print("UI/protocol validation contracts: OK")


if __name__ == "__main__":
    main()
