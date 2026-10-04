;; Read-only SPECTALK.DAT stream embedded in NEX physical pages 24..27.

SECTION code_user

PUBLIC _dat_open
PUBLIC _dat_fread
PUBLIC _dat_fseek_set

EXTERN _esx_buf
EXTERN _esx_count
EXTERN _esx_result

NEXTREG_SELECT        EQU 0x243B
NEXTREG_MMU0          EQU 0x50
NEXT_DAT_FIRST_PAGE   EQU 24

SECTION bss_user

next_dat_position:  defs 2
next_dat_size:      defs 2
next_dat_saved_mmu: defs 1
next_dat_page:      defs 1

SECTION code_user

;; Reset stream and read its generated two-byte logical length.
_dat_open:
    ld hl, 0
    ld (next_dat_position), hl
    call next_dat_window_begin
    ld a, NEXT_DAT_FIRST_PAGE
    call next_dat_map
    ld hl, (0x0000)
    ld de, 32767
    or a
    sbc hl, de
    jr c, next_dat_size_ok
    ld hl, 0
    jr next_dat_size_store
next_dat_size_ok:
    add hl, de
next_dat_size_store:
    ld (next_dat_size), hl
    jp next_dat_window_end

;; uint8_t dat_fseek_set(uint16_t offset) __z88dk_fastcall
_dat_fseek_set:
    push hl
    ld de, (next_dat_size)
    or a
    sbc hl, de
    pop hl
    jr c, next_dat_seek_ok
    jr z, next_dat_seek_ok
    ld l, 0
    ret
next_dat_seek_ok:
    ld (next_dat_position), hl
    ld l, 1
    ret

;; Uses the established esx_* globals and returns BC=bytes copied.
_dat_fread:
    ld hl, 0
    ld (_esx_result), hl

    ld hl, (next_dat_position)
    ld de, (next_dat_size)
    or a
    sbc hl, de
    jr nc, next_dat_read_zero

    ld hl, (next_dat_size)
    ld de, (next_dat_position)
    or a
    sbc hl, de
    ld bc, (_esx_count)
    push hl
    or a
    sbc hl, bc
    pop hl
    jr nc, next_dat_count_ready
    ld b, h
    ld c, l
next_dat_count_ready:
    ld h, b
    ld l, c
    ld (_esx_result), hl

    ld hl, (next_dat_position)
    inc hl
    inc hl
    ld de, (_esx_buf)
    call next_dat_copy

    ld bc, (_esx_result)
    ld hl, (next_dat_position)
    add hl, bc
    ld (next_dat_position), hl
    ret

next_dat_read_zero:
    ld bc, 0
    ret

;; HL=physical stream offset, DE=destination, BC=count.
next_dat_copy:
    ld a, b
    or c
    ret z
    push bc
    call next_dat_window_begin
    pop bc

    ld a, h
    rlca
    rlca
    rlca
    and 3
    add a, NEXT_DAT_FIRST_PAGE
    ld (next_dat_page), a
    call next_dat_map

    ld a, h
    and 0x1F
    ld h, a
next_dat_copy_loop:
    ldi
    jp po, next_dat_copy_done
    ld a, h
    cp 0x20
    jr nz, next_dat_copy_loop
    ld a, (next_dat_page)
    inc a
    ld (next_dat_page), a
    call next_dat_map
    ld h, 0x00
    jr next_dat_copy_loop
next_dat_copy_done:
    jp next_dat_window_end

next_dat_window_begin:
    di
    ld bc, NEXTREG_SELECT
    ld a, NEXTREG_MMU0
    out (c), a
    inc b
    in a, (c)
    ld (next_dat_saved_mmu), a
    ret

next_dat_window_end:
    ld a, (next_dat_saved_mmu)
    jp next_dat_map

next_dat_map:
    DEFB 0xED, 0x92, NEXTREG_MMU0
    ret
