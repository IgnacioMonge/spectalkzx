"""Next frame-wait RX regression: burst model plus actual Z80 wait kernel.

Requires sjasmplus and z88dk-ticks. UART/frame events are simulated; no real I/O.
"""
from collections import deque
from pathlib import Path
import subprocess
import sys
import tempfile


def burst(budget, discard_errors, welcome):
    packet = welcome + b':server NOTICE nick :' + b'x'*450 + b'\r\n' + b':server 005 nick :' + b'y'*450 + b'\r\n'
    fifo, line = deque(), bytearray()
    accepted = False
    for frame in range(100):
        overflow = False
        for byte in packet[frame*230:(frame+1)*230]:
            if len(fifo) < 512:
                fifo.append(byte)
            else:
                overflow = True
        if overflow and discard_errors:
            fifo.clear()
            line.clear()
        for _ in range(min(budget, len(fifo))):
            byte = fifo.popleft()
            if byte == 10:
                accepted |= b' 001 ' in line
                line.clear()
            else:
                line.append(byte)
    return accepted


def main():
    long = b':irc.example.net 001 testnick :Welcome to the Example Internet Relay Chat Network testnick\r\n'
    short = b':server 001 nick :Welcome\r\n'
    assert burst(32, False, long)
    assert not burst(32, True, long)
    assert burst(230, True, long)
    assert burst(32, True, short)  # A short welcome can precede the overflow.
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
    name = 'asm/spectalk_asm/80_ui_runtime.asm'
    current = (root/name).read_text(encoding='utf-8')
    baseline = subprocess.check_output(['git', '-C', str(root), 'show', '1bda5d3:'+name]).decode().replace('\r\n','\n')
    def kernel(source):
        start = source.index('_frame_wait_drain:')
        return source[start:source.index('; =============================================================================',start)]
    stub = '''
_next_overlay_active equ 0x7000
_rb_head equ 0x7020
_rb_tail equ 0x7022
_frame_wait:
    ld hl,0x5c78
    inc (hl)
    ret
_net_pump_rx:
    ld a,32
    ld (0x7001),a
    ret
uartRead:
    ld hl,0x7002
    inc (hl)
    ld a,(hl)
    cp 230
    jr nz,ready
    ld hl,0x5c78
    inc (hl)
ready:
    ld a,42
    scf
    ret
_rb_push:
    ld hl,0x7001
    inc (hl)
    ret
'''
    with tempfile.TemporaryDirectory(prefix='next-wait-cpu-') as temporary:
        tmp = Path(temporary)
        def run(source, target, active):
            define = '' if target == 'classic' else '    DEFINE SPECTALK_'+target.upper()+'\n'
            program = define + '''    org 0x8000
    di
    ld sp,0xff00
    ld iy,0x1234
    call _frame_wait_drain
    ld (0x7010),iy
    ld (0x7012),sp
    ld a,i
    push af
    pop bc
    ld (0x7014),bc
    jp 0
''' + kernel(source) + stub
            (tmp/'test.asm').write_text(program,encoding='utf-8')
            result = subprocess.run(['sjasmplus','--nologo','--dirbol','--raw='+str(tmp/'test.bin'),str(tmp/'test.asm')],capture_output=True,text=True,timeout=30)
            assert result.returncode == 0, result.stdout+result.stderr
            code = (tmp/'test.bin').read_bytes()
            memory = bytearray(65536)
            memory[0x8000:0x8000+len(code)] = code
            memory[0x7000] = active
            (tmp/'input.bin').write_bytes(memory)
            subprocess.run(['z88dk-ticks','-pc','8000','-start','8000','-end','0','-counter','1000000','-output',str(tmp/'out.bin'),str(tmp/'input.bin')],check=True,capture_output=True,timeout=30)
            memory = (tmp/'out.bin').read_bytes()
            assert memory[0x7010:0x7014] == b'\x34\x12\x00\xff'
            assert not memory[0x7014] & 4, 'IFF2 must be clear on return'
            return memory[0x7001], code
        assert run(baseline,'next',0)[0] == 32
        assert run(current,'next',0)[0] == 230
        assert run(current,'next',1)[0] == 32
        # Classic gains only the ring-room gate before uartRead; same 230 pushes.
        assert run(current,'classic',0)[0] == run(baseline,'classic',0)[0]
        assert run(current,'spectranext',0) == run(baseline,'spectranext',0)
    print('Next wait RX: burst regression, 230-byte frame, overlay fallback, IY/SP/DI and unchanged other targets OK; hardware pending')


if __name__ == '__main__':
    main()
