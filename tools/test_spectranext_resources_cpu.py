#!/usr/bin/env python3
"""Run linked Spectranext resource ownership paths with mocked ROM/VFS I/O."""
import argparse
from pathlib import Path
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    symbols, memory = load(args.folder)
    callbacks = {
        "_spxn_rom_detect": 0x4300, "_spxn_xfs_open_keep": 0x4600,
        "_esx_opendir": 0x4380, "_esx_mkdir": 0x43A0,
        "_esx_fclose": 0x43C0, "_spxn_xfs_use_keep": 0x4400,
        "_spxn_xfs_fseek": 0x4440, "_spxn_xfs_release_keep": 0x4480,
        "fm_resources_closed": 0x44E0, "_spxn_xfs_close_active": 0x4500,
    }
    for name, address in callbacks.items():
        jump(memory, symbols[name], address)
    extra = f"""
    ld a,($5100)
    ld l,a
    ld h,0
    ret
    defs $4380-$,0
    xor a
    ld ($5102),a
    ld a,($5106)
    inc a
    ld ($5106),a
    ld a,($5107)
    or a
    ld a,0
    jr nz,dir_result
    ld a,1
    ld ($510B),a
    ld a,3
dir_result:
    ld ({symbols['_esx_handle']}),a
    ret
    defs $43A0-$,0
    ld a,($5108)
    inc a
    ld ($5108),a
    ret
    defs $43C0-$,0
    ld a,($5109)
    inc a
    ld ($5109),a
    ld a,($510A)
    or a
    ld l,$FF
    ret nz
    xor a
    ld ({symbols['_esx_handle']}),a
    ld ($510B),a
    ld l,a
    ret
    defs $4400-$,0
    ld a,l
    ld ($5114),a
    ld a,($5115)
    inc a
    ld ($5115),a
    ld a,($5116)
    or a
    ld a,l
    ld l,0
    ret nz
    ld ({symbols['_esx_handle']}),a
    ld a,2
    ld ($510B),a
    ld l,1
    ret
    defs $4440-$,0
    ld ($5118),hl
    ld a,($511A)
    inc a
    ld ($511A),a
    ld a,($511B)
    or a
    ld l,0
    ret nz
    inc l
    ret
    defs $4480-$,0
    ld a,l
    push af
    cp 7
    ld hl,$511E
    jr z,release_count
    inc hl
release_count:
    inc (hl)
    ld hl,$511D
    inc (hl)
    pop af
    ld hl,$511C
    cp (hl)
    ld l,$FF
    ret z
    ld l,0
    ret
    defs $44E0-$,0
    ld ($5120),hl
    ret
    defs $4500-$,0
    ld a,($510B)
    or a
    ld hl,0
    ret z
    jp $43C0
    defs $4600-$,0
    push hl
    xor a
    ld ($510B),a
    ld ({symbols['_esx_handle']}),a
    ld a,($5101)
    inc a
    ld ($5101),a
    cp 1
    jr nz,open_second
    pop hl
    ld ($5110),hl
    ld a,($5102)
    ld ($5104),a
    jr open_result
open_second:
    pop hl
    ld ($5112),hl
    ld a,($5102)
    ld ($5105),a
open_result:
    ld a,($5101)
    ld hl,$5103
    cp (hl)
    ld hl,0
    ret z
    add a,6
    ld l,a
    ld ({symbols['_esx_handle']}),a
    ld a,2
    ld ($510B),a
    ret
"""
    def fixture():
        sample = bytearray(memory)
        sample[0x5100] = 1
        sample[0x5102] = 3
        return sample

    with tempfile.TemporaryDirectory(prefix="spectranext-resources-") as temporary:
        directory = Path(temporary)
        def probe(sample, body):
            result = execute(bytearray(sample), body, extra, directory, "z80")
            abi(result)
            return result
        detect = f"call {symbols['_esx_detect']}\nld ($5122),hl"
        result = probe(fixture(), detect)
        assert result[0x5122] == 1
        assert result[0x5101] == 2 and result[0x5104:0x5106] == b"\x03\x03"
        assert result[0x5102] == 0 and result[0x5106] == 1
        assert int.from_bytes(result[0x5110:0x5112], "little") == symbols["_K_DAT"]
        assert int.from_bytes(result[0x5112:0x5114], "little") == symbols["storage_ovl_path"]
        assert result[symbols['_dat_keep']] == 7 and result[symbols['_ovl_keep']] == 8
        body = "\n".join(f"call {symbols[name]}\nld a,({symbols['_esx_handle']})"
                          f"\nld (${0x5124 + index:04X}),a\ncall {symbols['_esx_fclose']}"
                          for index, name in enumerate(("_dat_open", "_ovl_open") * 3))
        repeated = probe(result, body)
        assert repeated[0x5101] == 2, "runtime reopened an immutable resource"
        assert repeated[0x5115] == 6 and repeated[0x511A] == 6
        assert repeated[0x5124:0x512A] == bytes((7, 8)) * 3, "logical open detached early"
        assert repeated[0x5118:0x511A] == b"\0\0", "logical open did not rewind"
        assert repeated[symbols['_dat_keep']] == 7 and repeated[symbols['_ovl_keep']] == 8

        for failure, released, directories in (("detect", 0, 0), ("DAT", 0, 0),
                                               ("OVL", 1, 0), ("CFG", 2, 2)):
            sample = fixture()
            if failure == "detect": sample[0x5100] = 0
            elif failure == "DAT": sample[0x5103] = 1
            elif failure == "OVL": sample[0x5103] = 2
            else: sample[0x5107] = 1
            failed = probe(sample, detect)
            if failure in ("DAT", "OVL"):
                message = symbols['storage_dat_error' if failure == "DAT" else 'storage_ovl_error']
                assert int.from_bytes(failed[0x5120:0x5122], "little") == message, failure
            else:
                assert failed[0x5122] == 0, failure
            assert failed[symbols['_dat_keep']] == failed[symbols['_ovl_keep']] == 0
            assert failed[0x511D] == released and failed[0x5106] == directories, failure

        for flag in (0x5116, 0x511B):
            sample = bytearray(result)
            sample[flag] = 1
            failed = probe(sample, f"call {symbols['_dat_open']}")
            assert failed[symbols['_esx_handle']] == 0, "failed bind/seek exposed stale cursor"
            assert failed[symbols['_dat_keep']] == 7, "seek failure lost retained ownership"
            assert failed[0x5109] == result[0x5109] + (flag == 0x511B)
            assert failed[0x511A] == (flag == 0x511B)

        sample = bytearray(result)
        sample[0x511C] = 7
        failed = probe(sample, f"call {symbols['_resources_release']}\nld ($5122),hl")
        assert failed[0x5122] == 0xFF and failed[symbols['_dat_keep']] == 7
        assert failed[symbols['_ovl_keep']] == 0 and failed[0x511D] == 2
        retry = bytearray(failed)
        retry[0x511C] = 0
        retried = probe(retry, f"call {symbols['_resources_release']}\nld ($5122),hl")
        assert retried[0x5122] == 0 and retried[symbols['_dat_keep']] == 0
        assert retried[0x511E:0x5120] == b"\x02\x01"

        sample = bytearray(result)
        sample[symbols['_esx_handle']] = 3
        sample[0x510B] = 1
        sample[0x510A] = 1
        failed = probe(sample, f"call {symbols['_resources_release']}\nld ($5122),hl")
        assert failed[0x5122] == 0xFF and failed[0x511D] == 2
        assert failed[symbols['_esx_handle']] == 3, "failed transient close was hidden"

        # Compatibility zero may hide ownership after failed OPEN/predecessor CLOSE.
        for failed_close in (False, True):
            sample = fixture()
            sample[0x510B] = 1
            sample[0x510A] = int(failed_close)
            hidden = probe(sample, f"call {symbols['_resources_release']}\nld ($5122),hl")
            assert hidden[0x5109] == 1 and hidden[0x511D] == 0
            assert hidden[0x5122] == (0xFF if failed_close else 0)
            assert hidden[0x510B] == int(failed_close)
        empty = probe(fixture(), f"call {symbols['_resources_release']}")
        assert empty[0x5109] == empty[0x511D] == 0

        for failure in (False, True):
            sample = bytearray(result)
            if failure: sample[0x511C] = 7
            failed = probe(sample, f"ld hl,$5000\ncall {symbols['_fatal_msg']}")
            expected = symbols['resources_close_error'] if failure else 0x5000
            assert int.from_bytes(failed[0x5120:0x5122], "little") == expected
            assert failed[0x511D] == 2
            assert failed[symbols['_dat_keep']] == (7 if failure else 0)
        print("Spectranext resources: inherited opens, local CFG, repeated rewinds, failure ownership and fatal cleanup PASS")


if __name__ == "__main__":
    main()
