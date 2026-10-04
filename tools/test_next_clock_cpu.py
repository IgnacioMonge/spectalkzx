"""Check native video cadence and the linked main-loop clock (no hardware I/O).

Usage: python tools/test_next_clock_cpu.py build/next
Timing reference: core 3.x src/video/zxula_timing.vhd, including 264-line VGA
60Hz modes; https://wiki.specnext.dev/Video_Timing_Register supplies clocks.
"""
from fractions import Fraction
from pathlib import Path
import sys
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load, string


CLOCKS = (28000000, Fraction(200000000, 7), Fraction(206250000, 7),
          30000000, 31000000, 32000000, 33000000, 27000000)


def cadence(video, machine, hz60):
    if video == 7:
        width, lines = (429, 262) if hz60 else (432, 312)
    elif machine >= 4:
        width, lines = 448, 320
    elif machine >= 2:
        width, lines = 456, 264 if hz60 else 311
    else:
        width, lines = 448, 264 if hz60 else 312
    return Fraction(CLOCKS[video], 4 * width * lines)


def main():
    folder = Path(sys.argv[1])
    symbols, baseline = load(folder)
    # Only the register bus is simulated; execute the linked lookup and table.
    jump(baseline, symbols['next_clock_read'], 0x4300)
    read_register = 'push hl\nld l,a\nld h,$50\nld a,(hl)\npop hl\nret'

    def registers(memory, video, machine, hz60):
        memory[0x5011] = video
        memory[0x5003] = 0x83 | (machine << 4)
        memory[0x5005] = 0xf3 | (4 if hz60 else 0)

    with tempfile.TemporaryDirectory(prefix='next-clock-cpu-') as temporary:
        directory = Path(temporary)
        cases = 0
        for video in range(8):
            for machine in (1, 2, 3, 4):
                for hz60 in (False, True):
                    sample = bytearray(baseline)
                    registers(sample, video, machine, hz60)
                    result = execute(sample,
                                     f"call {symbols['_next_clock_second']}\nld ($4200),hl",
                                     read_register, directory, 'z80n')
                    abi(result)
                    rate = int.from_bytes(result[0x4200:0x4202], 'little')
                    exact = cadence(video, machine, hz60) * 64
                    assert rate == round(exact), (video, machine, hz60, rate, exact)
                    assert abs(rate / exact - 1) < Fraction(1, 5000)
                    cases += 1

        def call_bytes(name):
            return b'\xcd' + symbols[name].to_bytes(2, 'little')

        # Run the real FRAMES conversion and second side effects, ending before
        # clock I/O. Advancing the byte counter also exercises its wraparound.
        threshold = baseline.find(call_bytes('_next_clock_second'), symbols['_main'])
        assert threshold >= 0
        start = baseline.rfind(b'\x3a\x78\x5c', symbols['_main'], threshold)
        assert start >= symbols['_main'], 'linked FRAMES read not found'
        end = baseline.find(call_bytes('_classic_clock_init'), threshold)
        assert end > threshold
        baseline[end] = 0xc9
        baseline[symbols['_has_other_mention']:symbols['_has_other_mention'] + 4] = b'\x21\0\0\xc9'
        baseline[symbols['_draw_clock']] = 0xc9
        baseline[symbols['_draw_status_bar']] = 0xc9
        sample = bytearray(baseline)
        ticks = symbols['_tick_accum']
        sample[ticks:ticks + 2] = b'\xef\xbe'
        string(sample, 0x5100, '+CIPSNTPTIME:Tue Sep 29 12:34:56 2026')
        result = execute(sample, f"ld hl,$5100\ncall {symbols['_sntp_process_response']}",
                         read_register, directory, 'z80n')
        abi(result)
        assert result[ticks:ticks + 2] == b'\0\0'
        assert result[symbols['_time_second']] == 56
        for video, machine, hz60 in ((7, 3, False), (7, 3, True),
                                     (6, 3, False), (6, 3, True), (0, 4, True)):
            sample = bytearray(baseline)
            registers(sample, video, machine, hz60)
            ticks = symbols['_tick_accum']
            body = f'''ld b,10
again:
push bc
ld a,($5c78)
add a,60
ld ($5c78),a
call {start}
pop bc
djnz again'''
            result = execute(sample, body, read_register, directory, 'z80n')
            abi(result)
            seconds, remaining = divmod(600 * 64, round(cadence(video, machine, hz60) * 64))
            assert result[symbols['_time_second']] == seconds
            assert int.from_bytes(result[ticks:ticks + 2], 'little') == remaining

    print(f'Next clock: {cases} VGA/HDMI/machine/50-60 selections, linked FRAMES wrap/seconds and SNTP reset; SP/IX/IY OK')


if __name__ == '__main__':
    main()
