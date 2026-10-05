"""Execute current rendering kernels with sjasmplus/z88dk-ticks (no hardware I/O).

Run explicitly: HOSTPYTHON tools/test_render_cpu.py [--root CHECKOUT].
Uses actual DAT font, a destructive UART stub, and independent screen geometry.
Temporary binaries are removed automatically. Timings exclude contention/IRQs.
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile


def section(text, start, end):
    first = text.index(start)
    return text[first:text.index(end, first)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--revision', help='Read ASM from this Git revision for comparison')
    parser.add_argument('--spectranext', action='store_true', help='Exclude UART service points')
    parser.add_argument('--next', action='store_true', dest='next_target',
                        help='Exercise native Next scroll UART service points')
    args = parser.parse_args()
    assert not (args.next_target and args.spectranext)
    root = args.root
    def blob(path):
        if args.revision:
            return subprocess.check_output(['git', '-C', str(root), 'show', args.revision+':'+path])
        return (root / path).read_bytes()
    def source(name):
        return blob('asm/spectalk_asm/' + name).decode('utf-8').replace('\r\n', '\n')
    render = source('30_rendering.asm')
    screen = source('40_text_numeric_screen.asm')
    core = source('10_core_helpers.asm')
    polls_uart = 'render_poll_rx:' in screen and not args.spectranext
    font = blob('src/SPECTALK.DAT')[:298]
    # Legacy fonts store LUT indices after a nonzero 10-byte LUT; current fonts
    # store each 4px row pattern directly and leave those 10 bytes zero.
    legacy = any(font[:10])
    assert not legacy or all(n < 10 for b in font[10:] for n in (b >> 4, b & 15))
    glyphs = [bytes(font[n] if legacy else n * 0x11 for b in font[10+i*3:13+i*3]
                    for n in (b >> 4, b & 15)) for i in range(96)]
    kernels = section(render, '_compute_screen_base:', '; ===')
    kernels += section(core, '_l_mul32:', '    ret') + '    ret\n'
    kernels += section(render, 'blank_glyph:', '; =============================================================================\n; GRAPHICS SYSTEM - FUNCTIONS')
    kernels += section(render, '_print_line64_fast:', '; -----------------------------------------------------------------------------\n; void print_status')
    kernels += section(render, 'p64_get_scr_base:', '_draw_big_char:')
    kernels += section(render, 'dbc_add_col:', 'dbc_left_core:')
    kernels += section(screen, '_fast_fill_attr:', '; ===')
    kernels += section(screen, '_scroll_main_zone:', '; =============================================================================\n; void main_newline')
    dma_body = None
    if args.next_target:
        # z88dk-ticks has no zxnDMA: an LDIR stand-in proves the block geometry,
        # and the DMA body itself (OUTs ignored) gives the CPU share of timing.
        start = kernels.index('smz_copy16n:\n    push bc')
        end = kernels.index('ELSE', start)
        dma_body = kernels[start:end]
        kernels = kernels[:start] + 'smz_copy16n:\n    ldir\n    ret\n' + kernels[end:]
    if 'render_poll_rx:' in screen:
        kernels += section(screen, 'render_poll_rx:', 'ENDIF')
    definitions = '''
font_lut equ 0x70f8
font64_packed equ font_lut+10
glyph_buffer equ 0x5bc0
plf_left_buf equ 0x5bc8
plf_attr_val equ 0x5bd0
plf_y_val equ 0x5bd1
_plf_start_byte equ 0x7100+298
_plf_pair_count equ _plf_start_byte+1
_current_attr equ _plf_start_byte+2
_g_ps64_y equ 0x7230
_g_ps64_col equ 0x7231
_g_ps64_attr equ 0x7232
cache_scr_base equ 0x5bba
cache_atr_base equ 0x5bbc
cache_row_y equ 0x5bbe
___sdcc_enter_ix:
    pop hl
    push ix
    ld ix,0
    add ix,sp
    jp (hl)
_net_pump_rx:
    ld a,i
    jp po,poll_di
    ld a,1
    ld (0x7300),a
poll_di:
    ld hl,0x7301
    inc (hl)
    exx
    ld bc,0xdead
    ld de,0xbeef
    ld hl,0xabcd
    exx
    ld bc,0xdead
    ld de,0xbeef
    ld hl,0xabcd
    xor a
    ret
'''
    with tempfile.TemporaryDirectory(prefix='render-cpu-') as temporary:
        tmp = Path(temporary)
        def run(body, setup=None, stop_at_poll=0):
            asm = tmp / 'kernel.asm'
            define = ('    DEFINE SPECTALK_SPECTRANEXT\n' if args.spectranext else
                      '    DEFINE SPECTALK_NEXT\n' if args.next_target else '')
            stub = definitions
            if stop_at_poll:
                stub = stub.replace('    inc (hl)\n    exx',
                                    f'    inc (hl)\n    ld a,(hl)\n    cp {stop_at_poll}\n    jp z,0\n    exx')
            asm.write_text(define + '    org 0x8000\n    di\n    ld sp,0xff00\n'
                           + body + '\n    jp 0\n' + stub + kernels, encoding='utf-8')
            result = subprocess.run(['sjasmplus', '--nologo', '--dirbol', '--raw='+str(tmp/'code.bin'), str(asm)], capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            memory = bytearray(65536)
            memory[0x4000:0x5c00] = bytes((i*37 ^ (i>>8) ^ 165)&255 for i in range(0x1c00))
            memory[0x70f8:0x70f8+298] = font
            code = (tmp/'code.bin').read_bytes()
            memory[0x8000:0x8000+len(code)] = code
            if setup:
                setup(memory)
            before = bytes(memory)
            (tmp/'input.bin').write_bytes(memory)
            result = subprocess.run(['z88dk-ticks', '-pc', '8000', '-start', '8000', '-end', '0000', '-counter', '10000000', '-output', str(tmp/'output.bin'), str(tmp/'input.bin')], capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stdout + result.stderr
            after = (tmp/'output.bin').read_bytes()
            assert len(after) >= 65536
            # ticks appends its CPU state after the 64K RAM image.
            return before, after[:65536], int(re.findall(r'\d+', result.stdout)[-1])

        body = '    ld ix,0x1234\n    ld iy,0x5678\n'
        for i in range(96):
            body += f'''    ld bc,0xabcd
    ld a,{i+32}
    call unpack_glyph
    ld (0x{0x7400+i*2:04x}),bc
    ld de,0x{0x6000+i*6:04x}
    ld bc,6
    ldir
'''
        body += '    ld (0x73f0),ix\n    ld (0x73f2),iy\n    ld (0x73f4),sp\n'
        _, after, cycles = run(body)
        assert after[0x6000:0x6240] == b''.join(glyphs)
        assert after[0x7400:0x74c0] == b'\xcd\xab'*96
        assert after[0x73f0:0x73f6] == b'\x34\x12\x78\x56\x00\xff'
        print(f'96 glyphs + copy/ABI harness: {cycles} T')

        def addr(row, scan):
            return 0x4000 + ((row & 24)<<8) + ((row & 7)<<5) + scan*256

        for row, start, count, data in [(19,0,0,b'A'*64), (3,0,0,b''), (7,3,0,bytes(range(32,128))), (19,31,0,b'AZ'), (19,32,0,b''), (19,0,4,b'A'*8)]:
            def setup(memory):
                memory[0x6000:0x6000+len(data)+1] = data+b'\0'
                memory[0x722a] = start
                memory[0x722b] = count
            body = f'''    ld ix,0x1234
    ld iy,0x5678
    ld bc,0x4760
    push bc
    ld hl,{row}
    push hl
    call _print_line64_fast
    pop bc
    pop bc
    ld (0x73f0),ix
    ld (0x73f2),iy
    ld (0x73f4),sp
'''
            before, after, cycles = run(body, setup)
            expected = bytearray(before[0x4000:0x5b00])
            if start < 32:
                for pair in range(start,min(32,start+count) if count else 32):
                    chars = data[(pair-start)*2:(pair-start)*2+2].ljust(2,b'\0')
                    rows = [glyphs[c-32] if 32 <= c < 128 else bytes(6) for c in chars]
                    for scan in range(8):
                        value = 0 if scan in (0,7) else ((rows[0][scan-1]&240)|(rows[1][scan-1]&15))
                        expected[addr(row,scan)+pair-0x4000] = value
                    expected[0x1800+row*32+pair] = 0x47
            assert after[0x4000:0x5b00] == expected, (row,start)
            assert after[0x73f0:0x73f6] == b'\x34\x12\x78\x56\x00\xff'
            assert after[0x7300] == 0, 'UART called with interrupts enabled'
            pairs = min(32-start, count or 32) if start < 32 else 0
            assert after[0x7301] == (pairs//4 if polls_uart else 0)
            print(f'line row={row} start={start} bytes={len(data)}: {cycles} T, polls={after[0x7301]}')

        for row, start, data in [(7, 1, bytes(range(33, 96))), (19, 0, b'Hi, ~a \x01z\x7f!' + bytes(range(96, 128)))]:
            def setup(memory):
                memory[0x6000:0x6000+len(data)+1] = data+b'\0'
            body = f"""    ld ix,0x1234
    ld iy,0x5678
    ld a,0xff
    ld (cache_row_y),a
    ld a,{row}
    ld (_g_ps64_y),a
    ld a,0x47
    ld (_g_ps64_attr),a
    ld hl,0x6000
    ld a,{start}
pc_loop:
    ld (_g_ps64_col),a
    ld a,(hl)
    or a
    jr z,pc_done
    push hl
    ld l,a
    call _print_str64_char
    pop hl
    inc hl
    ld a,(_g_ps64_col)
    inc a
    jr pc_loop
pc_done:
    ld (0x73f0),ix
    ld (0x73f2),iy
    ld (0x73f4),sp
"""
            before, after, cycles = run(body, setup)
            expected = bytearray(before[0x4000:0x5b00])
            for i, c in enumerate(data):
                col = start + i
                keep, take = (0x0f, 0xf0) if col % 2 == 0 else (0xf0, 0x0f)
                glyph = glyphs[c-32] if 33 <= c < 128 else None
                for scan in range(8):
                    off = addr(row, scan) + col//2 - 0x4000
                    value = expected[off] & keep
                    if glyph and 1 <= scan <= 6:
                        value |= glyph[scan-1] & take
                    expected[off] = value
                expected[0x1800+row*32+col//2] = 0x47
            assert after[0x4000:0x5b00] == expected, ('per-char', row, start)
            assert after[0x73f0:0x73f6] == b'\x34\x12\x78\x56\x00\xff'
            print(f'per-char row={row} start={start} chars={len(data)}: {cycles} T')

        def scroll_setup(memory):
            memory[0x722c] = 0x47
        before, after, cycles = run('    call _scroll_main_zone', scroll_setup)
        expected = bytearray(before[0x4000:0x5b00])
        for row in range(3,20):
            for scan in range(8):
                offset = addr(row,scan)-0x4000
                expected[offset:offset+32] = before[addr(row+1,scan):addr(row+1,scan)+32] if row < 19 else bytes(32)
            offset = 0x1800+row*32
            expected[offset:offset+32] = before[0x4000+offset+32:0x4000+offset+64] if row < 19 else b'\x47'*32
        assert after[0x4000:0x5b00] == expected
        assert after[0x7300] == 0
        assert after[0x7301] == (41 if polls_uart else 0)
        print(f'scroll: {cycles} T, polls={after[0x7301]}')
        if args.next_target:
            # CPU share with the real DMA body, plus 4 T per byte for the 41
            # blocks (8 x 512 bitmap bytes and 512 attribute bytes) the DMA moves.
            kernels = kernels.replace('smz_copy16n:\n    ldir\n    ret\n', dma_body)
            _, _, cpu_part = run('    call _scroll_main_zone', scroll_setup)
            total = cpu_part + 4 * (8 * 512 + 512)
            # 2x margin for contention and IRQs inside the smaller 256-byte FIFO.
            limit = 256 * 10 * 3_500_000 / 115200
            assert 2 * total < limit, total
            print(f'Next DMA scroll: {cpu_part} T CPU + {total - cpu_part} T DMA = {total} T; 2x margin < {limit:.0f} T FIFO budget')
        _, _, cycles = run('    ld hl,0x5880\n    ld de,0x5860\n    ld bc,512\n    call smz_copy16n')
        print(f'largest scroll block (512 bytes), harness included: {cycles} T')
        print('Rendering CPU checks OK; UART stub only, hardware pending')


if __name__ == '__main__':
    main()
