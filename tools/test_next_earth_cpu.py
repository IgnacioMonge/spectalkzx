"""Execute the actual Earth sprite kernel in ZEsarUX via an existing ZRCP port.

Run on a disposable TBBlue instance: HOSTPYTHON tools/test_next_earth_cpu.py PORT.
Replaces the emulated machine's RAM/state; never point at an interactive session.
Requires sjasmplus. Verifies all 48 uploads, palette, flip, wrap, close and reopen.
"""
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

from next_earth import FIRST_BANK, FRAME_COUNT, FRAME_SIZE, PAGE_SIZE, STARFIELD_BANK, FRAME_BUFFER_PAGE, earth_assets, pack_earth, pack_starfield


def main():
    root = Path(__file__).resolve().parents[1]
    packed = pack_earth()
    frames = earth_assets()[0]
    source = (root / "overlay/earth_next.asm").read_text()
    common = (root / "overlay/earth_about_render.asm").read_text()
    source += "\n" + common[common.index("\nearth_apply_delta:"):common.index(";; Validate one exact-length")]
    source = re.sub(r"DEFC (\w+) =", r"\1 equ", source)
    program = '''    org 0x8000
open_entry:
    call next_earth_open
    ld a,1
    ld (_earth_ready),a
    jp stopped
tick_entry:
    call next_earth_tick
    jp stopped
close_entry:
    call next_earth_close
    xor a
    ld (_earth_ready),a
stopped:
    jr stopped
_frame_idx equ 0x7000
_earth_ready equ 0x7001
''' + source
    with tempfile.TemporaryDirectory(prefix="earth-cpu-") as directory, socket.create_connection(
        ("127.0.0.1", int(sys.argv[1])), timeout=30
    ) as connection:
        tmp = Path(directory)

        def response():
            result = b""
            while not result.endswith(b"> "):
                chunk = connection.recv(65536)
                if not chunk:
                    raise ConnectionError("ZRCP closed")
                result += chunk
            return result.decode()

        def command(text):
            connection.sendall((text + "\n").encode())
            result = response()
            assert "ERROR" not in result, (text, result)
            return result

        def values(text):
            return [int(n.rstrip("H"), 16) for n in text.rsplit("\n", 1)[0].split()]

        response()
        (tmp / "test.asm").write_text(program)
        subprocess.run(["sjasmplus", "--nologo", "--dirbol", "--raw=" + str(tmp / "test.bin"),
                        "--sym=" + str(tmp / "test.sym"), str(tmp / "test.asm")], check=True,
                       capture_output=True)
        symbols = {name: int(value, 16) for name, value in
                   re.findall(r"(\w+): EQU 0x([0-9A-Fa-f]+)", (tmp / "test.sym").read_text())}
        command("enter-cpu-step")
        command("tbblue-set-register 3 3")  # Leave boot ROM/config mode, as NEX loading does.
        command("set-memory-zone -1")
        saved_mmu = values(command("tbblue-get-register 80"))[0]
        saved_mmu2 = values(command("tbblue-get-register 82"))[0]
        for frame in range(len(packed) // PAGE_SIZE):
            (tmp / "frame.bin").write_bytes(packed[frame * PAGE_SIZE:(frame + 1) * PAGE_SIZE])
            command(f"tbblue-set-register 80 {FIRST_BANK * 2 + frame}")
            command(f'load-binary "{tmp / "frame.bin"}" 0 0')
        (tmp / "frame.bin").write_bytes(bytes([0xA5]) * PAGE_SIZE)
        for page in [FRAME_BUFFER_PAGE, *range(STARFIELD_BANK * 2, STARFIELD_BANK * 2 + 6)]:
            command(f"tbblue-set-register 80 {page}")
            command(f'load-binary "{tmp / "frame.bin"}" 0 0')
        command(f"tbblue-set-register 80 {saved_mmu}")
        command(f'load-binary "{tmp / "test.bin"}" 32768 0')
        command("write-memory 28672 0 0")
        command("set-register SP=FF00H")
        command("set-register IX=1234H")
        command("set-register IY=5678H")
        for register, value in ((7, 0), (0x15, 0), (0x43, 0), (0x4B, 0xE3)):
            command(f"tbblue-set-register {register} {value}")
        star_registers = {0x12: 9, 0x14: 0xE3, 0x16: 7, 0x17: 5, 0x70: 0x10, 0x71: 1}
        for register, value in star_registers.items():
            command(f"tbblue-set-register {register} {value}")
        command("tbblue-set-register 105 0")
        command("tbblue-set-register 28 1")
        for value in (10, 200, 3, 150, 10, 200):
            command(f"tbblue-set-register 24 {value}")
        command(f'set-breakpoint 1 PC={symbols["stopped"]}')
        command("enable-breakpoints")
        command("enable-breakpoint 1")

        def run(entry):
            command(f"set-register PC={symbols[entry]}")
            command("run 200000")
            registers = command("get-registers").upper()
            for field in ("SP=FF00", "IX=1234", "IY=5678", f'PC={symbols["stopped"]:04X}'):
                assert field in registers, registers
            assert "IFF--" in registers, registers
            assert values(command("tbblue-get-register 80")) == [saved_mmu]
            assert values(command("tbblue-get-register 82")) == [saved_mmu2]
            assert values(command("tbblue-get-register 7"))[0] & 3 == 0

        for frame in range(FRAME_COUNT + 1):
            run("open_entry" if frame == 0 else "tick_entry")
            base = (frame % 2) * 25
            actual = bytes(values(command(f"tbblue-get-pattern {base} 8 25")))
            assert actual == frames[frame % FRAME_COUNT], frame
            attributes = values(command("tbblue-get-sprite 0 25"))
            assert len(attributes) == 100, len(attributes)
            for sprite in range(25):
                assert attributes[sprite * 4:sprite * 4 + 4] == [
                    120 + sprite % 5 * 16, 56 + sprite // 5 * 16, 0, 128 + base + sprite]
            assert values(command("read-memory 28672 1")) == [(frame + 1) % FRAME_COUNT]
            logo = packed[6912:8192] + packed[PAGE_SIZE + FRAME_SIZE:PAGE_SIZE + 7936]
            actual_logo = bytes(values(command("tbblue-get-pattern 50 8 11")))
            assert actual_logo == logo, (frame, [(i, a, b) for i, (a, b) in enumerate(zip(actual_logo, logo)) if a != b][:10])
            attributes = values(command("tbblue-get-sprite 25 22"))
            assert len(attributes) == 110
            for sprite in range(22):
                assert attributes[sprite * 5:sprite * 5 + 5] == [
                    72 + sprite % 11 * 16, 136 + sprite // 11 * 16, 0x50,
                    0xC0 | ((100 + sprite) >> 1), 0x80 | ((sprite & 1) << 6)]
        palette = values(command("tbblue-get-palette sprite second 0 256"))
        expected = packed[FRAME_SIZE:FRAME_SIZE + 512]
        assert palette == [(a << 1) | b for a, b in zip(expected[::2], expected[1::2])]
        for register in star_registers:
            assert values(command(f"tbblue-get-register {register}")) == [STARFIELD_BANK if register == 0x12 else 0]
        assert values(command("tbblue-get-register 105"))[0] & 128
        palette = values(command("tbblue-get-palette layer2 second 0 256"))
        expected = pack_starfield()[1]
        assert palette == [(a << 1) | b for a, b in zip(expected[::2], expected[1::2])]
        background = bytearray()
        for page in range(STARFIELD_BANK * 2, STARFIELD_BANK * 2 + 6):
            command(f"tbblue-set-register 80 {page}")
            background.extend(bytes.fromhex(command(f"read-memory 0 {PAGE_SIZE}").rsplit("\n", 1)[0]))
        command(f"tbblue-set-register 80 {saved_mmu}")
        assert background == pack_starfield()[0], "Layer 2 reconstruction from dirty RAM"
        run("close_entry")
        for register, value in star_registers.items():
            assert values(command(f"tbblue-get-register {register}")) == [value]
        assert not values(command("tbblue-get-register 105"))[0] & 128
        assert values(command("tbblue-get-register 28"))[0] & 3 == 2
        for value in (3, 150, 10, 200):
            assert values(command("tbblue-get-register 24")) == [value]
            command(f"tbblue-set-register 24 {value}")
        for register, value in ((0x15, 0), (0x43, 0), (0x4B, 0xE3)):
            assert values(command(f"tbblue-get-register {register}")) == [value]
        command("tbblue-set-register 21 1")  # NEX loaders may leave global sprites enabled.
        run("open_entry")
        assert values(command("read-memory 28672 1")) == [1]
        run("close_entry")
        assert values(command("tbblue-get-register 21")) == [1]
        assert values(command("tbblue-get-sprite 0 47")) == [0] * 188
        print("Earth Z80N: 48 uploads + wrap, double buffer, sprite geometry, RGB333 palette, "
              "MMU0/CPU/IY/IX/SP/DI, close and reopen OK")


if __name__ == "__main__":
    main()
