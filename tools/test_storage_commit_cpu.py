#!/usr/bin/env python3
"""Exercise linked config/bookmark writers with simulated esxDOS faults.

HOSTPYTHON tools/test_storage_commit_cpu.py build/classic
HOSTPYTHON tools/test_storage_commit_cpu.py build/next
"""

import argparse
from pathlib import Path
import tempfile

from test_audit_fixes_cpu import abi, execute, jump, load, string


ORIG_PRESENT = 0x5800
NEW_PRESENT = 0x5801
BAK_PRESENT = 0x5802
ORIG_MARK = 0x5803
NEW_MARK = 0x5804
BAK_MARK = 0x5805
FAULT = 0x5806
MODE = 0x5807
SOURCE_KIND = 0x5808
ERROR_SEEN = 0x5809
INPUT_A = 0x580A
PRIMARY_PATH = 0x580B
ALT_PRESENT = 0x580C
ALT_MARK = 0x580D
SOURCE_PRIMARY = 0x580E
WRITE_CALLED = 0x580F
IFF_ENABLED = 0x5810


def overlay_entry(memory, folder, symbols, atlas_id, entry_id):
    atlas = (folder / "SPECTALK.OVL").read_bytes()
    assert atlas[:4] == b"STOA"
    pair = 8 + atlas_id * 4
    offset = int.from_bytes(atlas[pair:pair + 2], "little")
    size = int.from_bytes(atlas[pair + 2:pair + 4], "little")
    base = 0x2000 if "SPECTALK_NEXT" in symbols else symbols["_ring_buffer"]
    memory[base:base + size] = atlas[offset:offset + size]
    assert memory[base] > entry_id
    return int.from_bytes(memory[base + 2 + entry_id * 2:base + 4 + entry_id * 2], "little")


def stub_ui(memory, symbols):
    for name in ("_main_puts", "_main_print", "_set_attr_sys",
                 "_input_cache_invalidate", "_overlay_rx_release"):
        memory[symbols[name]] = 0xC9
    memory[symbols["_ui_err"]:symbols["_ui_err"] + 6] = bytes(
        (0x3E, 1, 0x32, ERROR_SEEN & 0xFF, ERROR_SEEN >> 8, 0xC9)
    )


FIRMWARE = r"""
rst8:
    ld ($580A),a
    pop hl
    ld a,(hl)
    inc hl
    push hl
    cp $9A
    jp z,fw_open
    cp $9B
    jp z,fw_close
    cp $9E
    jp z,fw_write
    cp $AD
    jp z,fw_unlink
    cp $B0
    jp z,fw_rename
    scf
    ret

path_kind_ix:
    push ix
    pop hl
    jr path_kind
path_kind_de:
    ex de,hl
path_kind:
    ld c,0
path_kind_scan:
    ld a,(hl)
    inc hl
    or a
    jr z,path_kind_end
    inc c
    jr path_kind_scan
path_kind_end:
    xor a
    ld ($580B),a
    ld a,c
    cp 20
    jr c,path_kind_suffix
    ld a,1
    ld ($580B),a
path_kind_suffix:
    dec hl
    dec hl
    ld a,(hl)
    cp 'W'
    ld a,2
    ret z
    ld a,(hl)
    cp 'K'
    ld a,3
    ret z
    ld a,1
    ret

fw_open:
    push ix
    pop hl
    ld a,h
    cp $40
    jp c,fw_fail
    ld a,b
    ld ($5807),a
    call path_kind_ix
    cp 2
    jr z,open_new
    cp 1
    jp nz,fw_fail
    ld hl,$5800
    ld a,($580B)
    or a
    jr nz,open_target_selected
    ld hl,$580C
open_target_selected:
    ld a,(hl)
    or a
    jp z,fw_fail
    ld a,2
    or a
    ret
open_new:
    ld a,($5807)
    cp $0E
    jp nz,fw_fail
    ld a,($5806)
    cp 1
    jp z,fw_fail
    cp 7
    jr nz,open_new_ok
    ld a,($580B)
    or a
    jp nz,fw_fail
open_new_ok:
    ld a,1
    ld ($5801),a
    xor a
    ld ($5804),a
    inc a
    ret

fw_write:
    push ix
    pop hl
    ld a,h
    cp $40
    jp c,fw_fail
    ld a,1
    ld ($580F),a
    ld a,($5806)
    cp 2
    jr nz,write_full
    dec bc
write_full:
    push ix
    pop hl
    ld a,(hl)
    ld ($5804),a
    or a
    ret

fw_close:
    ld a,($580A)
    cp 1
    jp nz,fw_ok
    ld a,($5806)
    cp 3
    jp z,fw_fail
fw_ok:
    or a
    ret
fw_fail:
    scf
    ret

fw_unlink:
    push ix
    pop hl
    ld a,h
    cp $40
    jp c,fw_fail
    call path_kind_ix
    cp 1
    jr z,unlink_target
    cp 2
    jr z,unlink_new
    ld hl,$5802
    jr unlink_one
unlink_target:
    ld hl,$5800
    ld a,($580B)
    or a
    jr nz,unlink_one
    ld hl,$580C
    jr unlink_one
unlink_new:
    ld hl,$5801
unlink_one:
    ld a,(hl)
    or a
    jp z,fw_fail
    ld (hl),0
    jp fw_ok

fw_rename:
    push ix
    pop hl
    ld a,h
    cp $40
    jp c,fw_fail
    ld a,d
    cp $40
    jp c,fw_fail
    call path_kind_ix
    ld ($5808),a
    ld a,($580B)
    ld ($580E),a
    call path_kind_de
    ld b,a
    ld a,($5808)
    cp 1
    jr z,rename_orig
    cp 2
    jr z,rename_new
    cp 3
    jr z,rename_bak
    jp fw_fail
rename_orig:
    ld a,b
    cp 3
    jp nz,fw_fail
    ld a,($5806)
    cp 4
    jp z,fw_fail
    ld hl,$5800
    ld de,$5803
    ld a,($580E)
    or a
    jr nz,rename_orig_selected
    ld hl,$580C
    ld de,$580D
rename_orig_selected:
    ld a,(hl)
    or a
    jp z,fw_fail
    ld a,($5802)
    or a
    jp nz,fw_fail
    ld a,1
    ld ($5802),a
    ld a,(de)
    ld ($5805),a
    xor a
    ld (hl),a
    ret
rename_new:
    ld a,b
    cp 1
    jp nz,fw_fail
    ld a,($5806)
    cp 5
    jp z,fw_fail
    cp 6
    jp z,fw_fail
    ld a,($5801)
    or a
    jp z,fw_fail
    ld hl,$5800
    ld de,$5803
    ld a,($580B)
    or a
    jr nz,rename_new_selected
    ld hl,$580C
    ld de,$580D
rename_new_selected:
    ld a,(hl)
    or a
    jp nz,fw_fail
    ld a,1
    ld (hl),a
    ld a,($5804)
    ld (de),a
    xor a
    ld ($5801),a
    ret
rename_bak:
    ld a,b
    cp 1
    jp nz,fw_fail
    ld a,($5806)
    cp 6
    jp z,fw_fail
    ld a,($5802)
    or a
    jp z,fw_fail
    ld hl,$5800
    ld de,$5803
    ld a,($580B)
    or a
    jr nz,rename_bak_selected
    ld hl,$580C
    ld de,$580D
rename_bak_selected:
    ld a,(hl)
    or a
    jp nz,fw_fail
    ld a,1
    ld (hl),a
    ld a,($5805)
    ld (de),a
    xor a
    ld ($5802),a
    ret

"""


def run_writer(symbols, memory, folder, cpu, writer, fault, directory, deleting=False):
    sample = bytearray(memory)
    entry = overlay_entry(sample, folder, symbols, *writer)
    stub_ui(sample, symbols)
    jump(sample, 8, 0x4300)
    sample[ORIG_PRESENT] = (fault not in (7, 8))
    sample[ORIG_MARK] = ord("O")
    sample[ALT_PRESENT] = 1
    sample[ALT_MARK] = ord("A")
    sample[BAK_PRESENT] = (fault == 8)
    sample[BAK_MARK] = ord("R")
    sample[FAULT] = fault
    sample[symbols["_config_dirty"]] = 0 if deleting else 1
    sample[symbols["_bookmark_sel"]] = 0
    sample[symbols["_bookmark_rows"]] = 0x80
    sample[symbols["_bookmark_active_slot"]] = 1
    sample[symbols["_autoconnect"]] = 1
    sample[symbols["_autojoin"]] = 1
    native_next = "SPECTALK_NEXT" in symbols
    if native_next:
        sample[symbols["_next_overlay_active"]] = 1
        # z88dk-ticks starts raw images with MMU1=$FF. Keep both simulated
        # mappings there so the real NEXTREG branches execute without hiding
        # the linked overlay bytes from the flat fixture.
        sample[symbols["next_saved_mmu1"]] = 0xFF
        sample[symbols["next_overlay_page"]] = 0xFF
    string(sample, symbols["_irc_server"], "irc.test")
    string(sample, symbols["_irc_port"], "6667")
    string(sample, symbols["_irc_pass"], "secret")
    string(sample, symbols["_search_pattern"], "#retro")
    enable_interrupts = bool(fault & 1)
    body = ("ei\nnop\n" if enable_interrupts else "di\n") + f"""call {entry}
ld a,i
jp po,storage_iff_clear
ld a,1
jr storage_iff_store
storage_iff_clear:
xor a
storage_iff_store:
ld (${IFF_ENABLED:04X}),a"""
    result = execute(sample, body, FIRMWARE, directory, cpu, cycles=3000000)
    abi(result)
    assert result[IFF_ENABLED] == enable_interrupts, ("IFF changed", fault)
    if native_next:
        assert result[symbols["_next_overlay_active"]] == 1
        assert result[symbols["next_saved_mmu1"]] == 0xFF
        assert result[symbols["next_overlay_page"]] == 0xFF
    return result


def check_writer(symbols, memory, folder, cpu, name, writer, success_mark, directory):
    for fault in range(9):
        result = run_writer(symbols, memory, folder, cpu, writer, fault, directory)
        state = tuple(result[address] for address in
                      (ORIG_PRESENT, ALT_PRESENT, NEW_PRESENT, BAK_PRESENT,
                       ORIG_MARK, ALT_MARK, BAK_MARK))
        if fault in (0, 7, 8):
            expected = ((1, 1, 0, 0, success_mark, ord("A"), ord("O")) if fault == 0
                        else ((0, 1, 0, 0, ord("O"), success_mark, ord("A")) if fault == 7
                              else (1, 1, 0, 0, success_mark, ord("A"), ord("R"))))
            assert state == expected, (name, fault, state)
            assert result[symbols["_config_dirty"]] == (0 if name == "config" else 1)
            assert result[ERROR_SEEN] == 0
        elif fault == 6:
            assert state == (0, 1, 0, 1, ord("O"), ord("A"), ord("O")), (name, fault, state)
            assert result[ERROR_SEEN] == 1
        else:
            assert state[:6] == (1, 1, 0, 0, ord("O"), ord("A")), (name, fault, state)
            assert result[ERROR_SEEN] == 1
        if name == "bookmark":
            assert result[symbols["_overlay_slot"]] == (1 if fault in (0, 7, 8) else 0)
    print(f"{name}: staged success, primary fallback, backup recovery and faults OK")


def check_delete(symbols, memory, folder, cpu, directory):
    for fault in range(9):
        result = run_writer(symbols, memory, folder, cpu, (2, 3), fault, directory, deleting=True)
        state = tuple(result[address] for address in
                      (ORIG_PRESENT, ALT_PRESENT, NEW_PRESENT, BAK_PRESENT,
                       ORIG_MARK, ALT_MARK, BAK_MARK))
        if fault in (0, 2):
            assert state[:4] == (1, 0, 0, 0), (fault, state)
            assert state[4] == 0, (fault, state)
        elif fault == 7:
            assert state[:4] == (0, 1, 0, 0), (fault, state)
            assert state[5] == 0, (fault, state)
        elif fault == 8:
            assert state[:4] == (1, 0, 0, 0), (fault, state)
            assert state[4] == 0, (fault, state)
        elif fault == 6:
            assert state == (0, 1, 0, 1, ord("O"), ord("A"), ord("O")), (fault, state)
        else:
            assert state[:6] == (1, 1, 0, 0, ord("O"), ord("A")), (fault, state)
        success = fault in (0, 2, 7, 8)
        assert result[symbols["_overlay_slot"]] == success
        assert result[ERROR_SEEN] == (not success)
        assert result[WRITE_CALLED] == 0
        assert result[symbols["_bookmark_active_slot"]] == (0 if success else 1)
        assert result[symbols["_config_dirty"]] == (1 if success else 0)
    print("delete: empty staged tombstone, alternate cleanup and all faults OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    symbols, memory = load(args.folder)
    assert "SPECTALK_SPECTRANEXT" not in symbols, \
        "Spectranext uses ROM/XFS storage; this esxDOS harness supports Classic/native Next"
    assert "_esx_frename" in symbols, "artifact predates staged storage transaction"
    cpu = "z80n" if "SPECTALK_NEXT" in symbols else "z80"
    with tempfile.TemporaryDirectory(prefix="storage-commit-cpu-") as temporary:
        directory = Path(temporary)
        check_writer(symbols, memory, args.folder, cpu, "config", (3, 1), ord("s"), directory)
        check_writer(symbols, memory, args.folder, cpu, "bookmark", (2, 2), ord("i"), directory)
        check_delete(symbols, memory, args.folder, cpu, directory)


if __name__ == "__main__":
    main()
