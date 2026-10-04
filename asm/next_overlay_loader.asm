;; Native Spectrum Next overlay dispatcher.
;; Eight overlays live in dedicated 8 KiB pages and execute at MMU1/$2000.

SECTION code_user

EXTERN _net_pump_rx
EXTERN _overlay_exit_full
EXTERN _ui_err
EXTERN ___sdcc_enter_ix

PUBLIC _overlay_exec
PUBLIC _overlay_call
PUBLIC _overlay_call_timed
PUBLIC _next_overlay_suspend
PUBLIC _next_overlay_restore
PUBLIC _next_overlay_active

NEXTREG_SELECT          EQU 0x243B
NEXTREG_ACCESS          EQU 0x253B
NEXTREG_MMU1            EQU 0x51
NEXT_OVERLAY_FIRST_PAGE EQU 16
NEXT_OVERLAY_COUNT      EQU 8
OVL_CODE_BASE           EQU 0x2000
OVL_CODE_END            EQU 0x4000
OVL_CODE_SIZE_ADDR      EQU OVL_CODE_END - 2

SECTION bss_user

_next_overlay_active: defs 1
next_overlay_page:    defs 1
next_saved_mmu1:      defs 1

SECTION code_user

;; void overlay_exec(uint8_t ovl_id, uint8_t entry_id) __z88dk_callee
_overlay_exec:
    call ___sdcc_enter_ix
    xor a
    ld (next_overlay_page), a
    call _net_pump_rx

    ld a, (ix+4)
    cp NEXT_OVERLAY_COUNT
    jr nc, next_exec_fail
    add a, NEXT_OVERLAY_FIRST_PAGE
    ld (next_overlay_page), a
    ld l, (ix+5)

    call next_overlay_begin
    call next_overlay_entry
    jr c, next_exec_fail_mapped

    ld hl, next_exec_return
    push hl
    push de
    ret

next_exec_return:
    call next_overlay_end_di
    pop ix
    pop de
    pop bc
    push de
    ret

next_exec_fail_mapped:
    call next_overlay_end_di
next_exec_fail:
    pop ix
    pop de
    pop bc
    push de
    call _overlay_exit_full
    ld hl, next_overlay_error
    jp _ui_err

;; void overlay_call(uint8_t entry_id) __z88dk_fastcall
;; Calls an entry in the last overlay selected by overlay_exec().
_overlay_call:
    ld a, (next_overlay_page)
    or a
    ret z
    call next_overlay_begin
    call next_overlay_entry
    jr c, next_call_bad
    ld hl, next_call_return
    push hl
    push de
    ret
next_call_return:
    jp next_overlay_end_di
next_call_bad:
    call next_overlay_end_di
    ret

;; Timed overlays use frame_wait(), which temporarily suspends MMU1 itself.
_overlay_call_timed:
    jp _overlay_call

;; Save the caller's MMU1 mapping, then select the active overlay page.
;; The native mainline contract is DI; frame_wait owns every EI window.
next_overlay_begin:
    di
    ld a, NEXTREG_MMU1
    call nextreg_read
    ld (next_saved_mmu1), a
    ld a, 1
    ld (_next_overlay_active), a
    jp _next_overlay_restore

;; Restore the page hidden by the overlay without changing active state.
_next_overlay_suspend:
    ld a, (_next_overlay_active)
    or a
    ret z
    ld a, (next_saved_mmu1)
    jp next_mmu1_write

;; Remap the active overlay after ROM/NextZXOS temporarily owned low memory.
_next_overlay_restore:
    ld a, (_next_overlay_active)
    or a
    ret z
    ld a, (next_overlay_page)
    jp next_mmu1_write

next_overlay_end_di:
    call _next_overlay_suspend
    xor a
    ld (_next_overlay_active), a
    ret

;; Return DE=validated entry address, carry set on malformed page/entry.
next_overlay_entry:
    ld a, l
    ld hl, OVL_CODE_BASE
    ld c, (hl)
    cp c
    jr nc, next_overlay_entry_bad
    ld b, a
    inc hl
    ld a, (hl)
    or a
    jr nz, next_overlay_entry_bad
    ld a, b
    ld e, c
    ld d, 0
    sla e
    rl d
    inc de
    inc de                   ; DE = complete entry-table length
    ld hl, (OVL_CODE_SIZE_ADDR)
    ld bc, OVL_CODE_SIZE_ADDR - OVL_CODE_BASE + 1
    or a
    sbc hl, bc
    jr nc, next_overlay_entry_bad ; stored length exceeds 8190
    ld hl, (OVL_CODE_SIZE_ADDR)
    or a
    sbc hl, de
    jr c, next_overlay_entry_bad  ; truncated entry table
    push de
    ld e, a
    ld d, 0
    sla e
    rl d
    ld hl, OVL_CODE_BASE + 2
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)
    pop bc

    push de
    ex de, hl
    ld de, OVL_CODE_BASE
    or a
    sbc hl, de
    jr c, next_overlay_entry_pop_bad
    or a
    sbc hl, bc
    jr c, next_overlay_entry_pop_bad
    add hl, bc
    ld de, (OVL_CODE_SIZE_ADDR)
    or a
    sbc hl, de
    jr nc, next_overlay_entry_pop_bad
    pop de
    or a
    ret
next_overlay_entry_pop_bad:
    pop de
next_overlay_entry_bad:
    xor a
    ld (next_overlay_page), a
    scf
    ret

;; A=NextReg number -> A=value.
nextreg_read:
    ld bc, NEXTREG_SELECT
    out (c), a
    inc b
    in a, (c)
    ret

;; A=physical 8 KiB page. Z80N NEXTREG preserves registers, flags and IFF.
next_mmu1_write:
    DEFB 0xED, 0x92, NEXTREG_MMU1
    ret

next_overlay_error:
    DEFM "Embedded overlay corrupt"
    DEFB 0
