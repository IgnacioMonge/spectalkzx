; Classic/native Next staged file replacement, linked only into writer overlays.

SECTION code_user

PUBLIC _esx_replace_write
EXTERN _esx_fopen
EXTERN _esx_fcreate
EXTERN _esx_fwrite
EXTERN _esx_fclose
EXTERN _esx_funlink
EXTERN _esx_frename
EXTERN _esx_handle
EXTERN _esx_count
EXTERN _esx_result

; Tail jump preserves the direct firmware call's stack depth.
storage_rename_to_target:
    ld hl, (storage_path)
    ld de, (storage_target)
    jp _esx_frename

storage_ext_new:
    ld hl, 0x454E       ; "NE"
    ld a, 'W'
    jr storage_set_ext
storage_ext_bak:
    ld hl, 0x4142       ; "BA"
    ld a, 'K'
storage_set_ext:
    ld de, (storage_tail)
    ex de, hl
    ld (hl), e
    inc hl
    ld (hl), d
    inc hl
    ld (hl), a
    ret

; uint8_t esx_replace_write(const char *path) __z88dk_fastcall
; Stage path.NEW, preserve the previous path as path.BAK, then install. This
; narrows the failure window but does not claim FAT power-loss atomicity.
_esx_replace_write:
    push iy
    push ix
    ld (storage_target), hl
    ld hl, -32
    add hl, sp
    ld sp, hl
    ld (storage_path), hl
    ex de, hl
    ld hl, (storage_target)
    ld b, 31
storage_path_copy:
    ld a, (hl)
    inc hl
    ld (de), a
    inc de
    or a
    jr z, storage_path_copied
    djnz storage_path_copy
    jp storage_write_false
storage_path_copied:
    ld hl, -4
    add hl, de
    ld (storage_tail), hl

    call storage_ext_new
    ld hl, (storage_path)
    call _esx_funlink
    ld hl, (storage_path)
    call _esx_fcreate
    ld a, (_esx_handle)
    or a
    jr nz, storage_write_open
    ld hl, (storage_target)
    call _esx_fopen
    ld a, (_esx_handle)
    or a
    jp z, storage_write_unavailable
    call _esx_fclose
    jp storage_write_false

storage_write_open:
    ld hl, (_esx_count)
    ld a, h
    or l
    jr z, storage_write_checked
    call _esx_fwrite
    ld hl, (_esx_result)
    ld de, (_esx_count)
    or a
    sbc hl, de
storage_write_checked:
    push af
    call _esx_fclose
    ld e, l
    pop af
    jr nz, storage_write_cleanup_new
    ld a, e
    or a
    jr nz, storage_write_cleanup_new

    call storage_ext_bak
    ld hl, (storage_target)
    call _esx_fopen
    ld a, (_esx_handle)
    or a
    jr z, storage_try_recover
    call _esx_fclose
    ld a, l
    or a
    jr nz, storage_write_cleanup_new
    jr storage_have_old

storage_try_recover:
    call storage_rename_to_target
    ld a, l
    or a
    jr z, storage_no_old

storage_have_old:
    ld hl, (storage_path)
    call _esx_funlink
    ld hl, (storage_target)
    ld de, (storage_path)
    call _esx_frename
    ld a, l
    or a
    jr z, storage_write_cleanup_new

    call storage_ext_new
    call storage_rename_to_target
    ld a, l
    or a
    jr nz, storage_write_installed

    call storage_ext_bak
    call storage_rename_to_target        ; rollback; .BAK remains if this also fails
    jr storage_write_cleanup_new

storage_no_old:
    call storage_ext_new
    call storage_rename_to_target
    ld a, l
    or a
    jr z, storage_write_cleanup_new
    jr storage_write_true

storage_write_installed:
    call storage_ext_bak
    ld hl, (storage_path)
    call _esx_funlink
storage_write_true:
    ld l, 1
    jr storage_write_ret

storage_write_cleanup_new:
    call storage_ext_new
    ld hl, (storage_path)
    call _esx_funlink
storage_write_false:
    ld l, 0
    jr storage_write_ret
storage_write_unavailable:
    ld l, 2
storage_write_ret:
    ld de, 32
    ex de, hl
    add hl, sp
    ld sp, hl
    ex de, hl
    pop ix
    pop iy
    ret

storage_target: defs 2
storage_tail:   defs 2
storage_path:   defs 2
