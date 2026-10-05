#!/usr/bin/env python3
"""Prove the chat-scroll geometry and interrupt/stack source contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASM = ROOT / "asm" / "spectalk_asm" / "40_text_numeric_screen.asm"
MAIN_OUTPUT_ASM = ROOT / "asm" / "spectalk_asm" / "50_main_output.asm"


def words(text):
    code = "\n".join(line.split(";", 1)[0] for line in text.splitlines())
    return " ".join(code.split()).lower()


def screen_addr(row, scanline):
    y = row * 8 + scanline
    return 0x4000 + ((y & 0xC0) << 5) + ((y & 7) << 8) + ((y & 0x38) << 2)


def copy_forward(memory, source, destination, count, touched):
    for offset in range(count):
        memory[destination + offset] = memory[source + offset]
        touched.add(destination + offset)


def prove_geometry():
    original = bytearray(((address * 37) ^ (address >> 8) ^ 0xA5) & 0xFF
                         for address in range(0x10000))
    memory = bytearray(original)
    touched = set()

    for scanline in range(7, -1, -1):
        for source, destination, count in (
            (0x4080 + 0x100 * scanline, 0x4060 + 0x100 * scanline, 128),
            (0x4800 + 0x100 * scanline, 0x40E0 + 0x100 * scanline, 32),
            (0x4820 + 0x100 * scanline, 0x4800 + 0x100 * scanline, 224),
            (0x5000 + 0x100 * scanline, 0x48E0 + 0x100 * scanline, 32),
            (0x5020 + 0x100 * scanline, 0x5000 + 0x100 * scanline, 96),
        ):
            copy_forward(memory, source, destination, count, touched)

    copy_forward(memory, 0x5880, 0x5860, 512, touched)
    for scanline in range(8):
        start = screen_addr(19, scanline)
        memory[start:start + 32] = bytes(32)
        touched.update(range(start, start + 32))
    memory[0x5A60:0x5A80] = bytes((0x5A,)) * 32
    touched.update(range(0x5A60, 0x5A80))

    for row in range(3, 19):
        for scanline in range(8):
            destination = screen_addr(row, scanline)
            source = screen_addr(row + 1, scanline)
            assert memory[destination:destination + 32] == original[source:source + 32]
        attr = 0x5800 + row * 32
        assert memory[attr:attr + 32] == original[attr + 32:attr + 64]

    for scanline in range(8):
        start = screen_addr(19, scanline)
        assert memory[start:start + 32] == bytes(32)
    assert memory[0x5A60:0x5A80] == bytes((0x5A,)) * 32

    for address in range(0x4000, 0x5B00):
        if address not in touched:
            assert memory[address] == original[address]


def prove_source_contract():
    source = ASM.read_text(encoding="utf-8")
    scroll = source.split("_scroll_main_zone:", 1)[1].split("; void main_newline", 1)[0]
    compact = words(scroll)
    helper = scroll.split("smz_copy16n:", 1)[1]

    assert "ld sp" not in compact
    assert "ssb_" not in compact
    assert "scroll_stack_blit" not in compact
    assert words("di ld iy, 0x5C3A ld ixl, 7 ei") in compact
    assert words("ld hl, 0x5060 ld ixl, 8") in compact
    assert words("ld hl, 0x5A60 ld a, (_current_attr) ld bc, 32 di jp _fast_fill_attr") in compact
    assert sum(words(line) == "ldi" for line in helper.splitlines()) == 16
    for setup in (
        "ld a, 0x40 add a, ixl ld h, a ld d, a ld l, 0x80 ld e, 0x60 ld bc, 128 call smz_copy16n",
        "ld a, 0x48 add a, ixl ld h, a ld d, a ld l, 0x20 ld e, 0x00 ld bc, 224 call smz_copy16n",
        "ld a, 0x50 add a, ixl ld h, a ld d, a ld l, 0x20 ld e, 0x00 ld bc, 96 call smz_copy16n",
        "ld de, 0x5860 ld hl, 0x5880 ld bc, 512 call smz_copy16n",
        "add a, ixl ld h, a sub 8 ld d, a ld l, 0x00 ld e, 0xE0 ld bc, 32 jp smz_copy16n",
    ):
        assert words(setup) in compact
    assert compact.count("ld bc, 32") == 3

    preamble = (ROOT / "asm" / "spectalk_asm" / "00_preamble.asm").read_text(encoding="utf-8")
    header = (ROOT / "include" / "spectalk.h").read_text(encoding="utf-8")
    c_source = (ROOT / "src" / "spectalk.c").read_text(encoding="utf-8")
    assert "PUBLIC _scroll_main_zone" not in preamble
    assert "scroll_main_zone(void)" not in header
    assert "scroll_main_zone(void)" not in c_source


def prove_cold_space_contract():
    source = MAIN_OUTPUT_ASM.read_text(encoding="utf-8")
    cold_space = source.split("puts_opt_emit:", 1)[1].split("puts_opt_space_cached:", 1)[0]
    compact = words(cold_space)

    assert words("ld hl, cache_row_y cp (hl) jr z, puts_opt_space_cached") in compact
    assert words("ld h, 32 jr puts_opt_char") in compact


def prove_uart_service_contract():
    screen = ASM.read_text(encoding="utf-8")
    render = (ASM.parent / "30_rendering.asm").read_text(encoding="utf-8")
    output = MAIN_OUTPUT_ASM.read_text(encoding="utf-8")
    # Classic/Spectranext keep their renderer; only Next services its finite FIFO.
    assert "render_poll_rx" not in screen + render + output
    scroll = screen.split("_scroll_main_zone:", 1)[1].split("; void main_newline", 1)[0]
    # Native Next copies each scroll block with the zxnDMA (4 T per byte), so
    # the whole scroll fits the FIFO budget without draining inside it.
    assert "_net_pump_rx" not in words(scroll)
    assert words("""ifdef spectalk_next ld bc, ZXN_DMA_PORT ld a, 0x83 out (c), a
        ld a, 0x54 out (c), a ld a, 0x02 out (c), a ld a, 0x50 out (c), a
        ld a, 0x02 out (c), a ld a, 0x82 out (c), a endif di""") in words(scroll)
    assert words("""zxn_dma_port equ 0x006b smz_copy16n: push bc ld bc, zxn_dma_port
        ld a, 0x7d out (c), a out (c), l out (c), h pop hl out (c), l out (c), h
        ld a, 0xad out (c), a out (c), e out (c), d ld a, 0xcf out (c), a
        ld a, 0x87 out (c), a ret else""") in words(scroll)
    assert "_net_pump_rx" not in render + output
    assert "call _net_pump_rx" in screen.split("_main_newline:", 1)[1]


def main():
    prove_geometry()
    prove_source_contract()
    prove_cold_space_contract()
    prove_uart_service_contract()
    print("Scroll contract check OK")


if __name__ == "__main__":
    main()
