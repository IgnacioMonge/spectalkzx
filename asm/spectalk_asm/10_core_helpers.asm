; =============================================================================
; UTILIDADES B?SICAS
; =============================================================================

; -----------------------------------------------------------------------------
; channel_flags_ptr: HL = &channels[L].flags
; copt replaces: 5x add hl,hl + ld de,_channels + add hl,de + ld de,0x001e + add hl,de
; Saves 8 bytes per site (11 -> 3 bytes call)
; -----------------------------------------------------------------------------
EXTERN _channels
_channel_flags_ptr:
    call _channel_name_ptr
    ld de, 0x001e
    add hl, de
    ret

; -----------------------------------------------------------------------------
; channel_name_ptr: HL = &channels[HL].name, same as channel slot base.
; copt replaces: call _hl_mul32 + ld de,_channels + add hl,de
; -----------------------------------------------------------------------------
_channel_name_ptr:
    call _hl_mul32
    ld de, _channels
    add hl, de
    ret

; -----------------------------------------------------------------------------
; irc_param_N: fixed-index wrappers for hot irc_param(0..2) call sites.
; COPT replaces ld l,N / call _irc_param with one call.
; -----------------------------------------------------------------------------
EXTERN _irc_param
_irc_param_0:
    ld l, 0x00
    jp _irc_param

_irc_param_1:
    ld l, 0x01
    jp _irc_param

_irc_param_2:
    ld l, 0x02
    jp _irc_param

; -----------------------------------------------------------------------------
; a_sext_mul32: sign-extend A to HL, then HL *= 32
; copt replaces: ld l,a / rlca / sbc a,a / ld h,a / 5x add hl,hl (9 bytes -> 3)
; -----------------------------------------------------------------------------
_a_sext_mul32:
    ld l, a
    rlca
    sbc a, a
    ld h, a
    jr _hl_mul32

; -----------------------------------------------------------------------------
; l_mul32: zero-extend L to HL, then HL *= 32 ? falls through to hl_mul32
; copt replaces: ld h,0x00 / 5x add hl,hl (7 bytes -> 3)
; -----------------------------------------------------------------------------
_l_mul32:
    ld h, 0x00
    ; fall through to _hl_mul32

; -----------------------------------------------------------------------------
; hl_mul32: HL = HL * 32 (used by peephole rule for channels[] indexing)
; Replaces 5x add hl,hl (5 bytes) with call (3 bytes) saving 2 bytes/site
; -----------------------------------------------------------------------------
_hl_mul32:
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    ret

; -----------------------------------------------------------------------------
; leave_ix: IX epilogue ? ld sp,ix / pop ix / ret
; copt replaces the 3-instruction epilogue (5 bytes) with jp (3 bytes)
; -----------------------------------------------------------------------------
_leave_ix:
    ld sp, ix
    pop ix
    ret

; -----------------------------------------------------------------------------
; l_channel_flags_ptr: HL = &channels[L].flags (L variant of channel_flags_ptr)
; copt replaces: call _l_mul32 + ld de,_channels + add hl,de + ld de,0x001e + add hl,de
; -----------------------------------------------------------------------------
_l_channel_flags_ptr:
    ld h, 0x00
    jr _channel_flags_ptr      ; shares body with _channel_flags_ptr (-9 bytes)

; -----------------------------------------------------------------------------
; channel_dec_users: decrement channels[L].user_count if non-zero.
; -----------------------------------------------------------------------------
_channel_dec_users:
    call _l_channel_flags_ptr
    dec hl
    dec hl
    ld e, (hl)
    inc hl
    ld d, (hl)
    ld a, d
    or e
    ret z
    dec de
    ld (hl), d
    dec hl
    ld (hl), e
    ret

; -----------------------------------------------------------------------------
; IX load helpers: HL = (ix+N/ix+N+1) ? 7 bytes each, saves 3 bytes per site
; Safe: callers using (ix+N) explicitly set IX via ___sdcc_enter_ix.
; -----------------------------------------------------------------------------
_ld_hl_ix4:
    ld l,(ix+4)
    ld h,(ix+5)
    ret

_ld_hl_ixm2:
    ld l,(ix-2)
    ld h,(ix-1)
    ret

_ld_hl_ix6:
    ld l,(ix+6)
    ld h,(ix+7)
    ret

_ld_hl_ixm4:
    ld l,(ix-4)
    ld h,(ix-3)
    ret
PUBLIC _ld_de_ixm2
_ld_de_ixm2:
    ld e,(ix-2)
    ld d,(ix-1)
    ret
PUBLIC _ld_hl_ixm5
_ld_hl_ixm5:
    ld l,(ix-5)
    ld h,(ix-4)
    ret
PUBLIC _ld_hl_ixm7
_ld_hl_ixm7:
    ld l,(ix-7)
    ld h,(ix-6)
    ret
PUBLIC _ld_hl_ixm3
_ld_hl_ixm3:
    ld l,(ix-3)
    ld h,(ix-2)
    ret

; -----------------------------------------------------------------------------
; IX store helpers: (ix+N/ix+N+1) = HL ? 7 bytes each, saves 3 bytes per site
; -----------------------------------------------------------------------------
_st_hl_ix4:
    ld (ix+4),l
    ld (ix+5),h
    ret

_st_hl_ixm2:
    ld (ix-2),l
    ld (ix-1),h
    ret

; -----------------------------------------------------------------------------
; rx_pos_reset: rx_pos = 0 (copt replaces ld hl,0/ld (_rx_pos),hl)
; Saves 3-6 bytes per site (25+ sites)
; -----------------------------------------------------------------------------
_rx_pos_reset:
    ld hl, 0
    ld (_rx_pos), hl
    ret

; -----------------------------------------------------------------------------
; reset_rx_state: rb_head = rb_tail = rx_pos = rx_overflow = 0
; 3 call sites in C -> saves ~3 bytes per site vs inline stores
; -----------------------------------------------------------------------------
_reset_rx_state:
    xor a
    ld (_rx_overflow), a
    call _rx_pos_reset        ; HL = 0 after return
    ld (_rb_head), hl
    ld (_rb_tail), hl
    ret

; A transport gap invalidates every queued byte, not the oldest queued line.
; Clobbers AF/HL only. The next accepted line must start after a later LF.
PUBLIC _rx_discard_pending
_rx_discard_pending:
    ld hl, (_rb_head)
    ld (_rb_tail), hl
    ld a, 1
    ld (_rx_overflow), a
    jp _rx_pos_reset

; Release overlay scratch without forgetting an interrupted receive line.
; Native Next overlays never overwrite the ring; retain its queued bytes.
PUBLIC _overlay_rx_release
_overlay_rx_release:
    ld hl, (_rx_pos)
    ld a, h
    or l
    ld hl, _rx_overflow
    or (hl)
IFNDEF SPECTALK_NEXT
    ld hl, (_rb_head)
    ld de, (_rb_tail)
    ld (_rb_tail), hl
    or a
    sbc hl, de
    or h
    or l
ENDIF
    ret z
    ld a, 1
    ld (_rx_overflow), a
    jp _rx_pos_reset

; -----------------------------------------------------------------------------
; check_status_irc: check_status(LVL_IRC=2) ? copt fuses ld l,2 / call
; Saves 2 bytes per site (13 sites)
; -----------------------------------------------------------------------------
EXTERN _check_status
PUBLIC _check_status_irc
_check_status_irc:
    ld l, 2
    jp _check_status

; -----------------------------------------------------------------------------
; set_sbd: status_bar_dirty = 1 ? copt fuses ld hl,_sbd / ld (hl),1
; Saves 2 bytes per site (9 sites)
; -----------------------------------------------------------------------------
EXTERN _status_bar_dirty
PUBLIC _set_sbd
_set_sbd:
    ld hl, _status_bar_dirty
    ld (hl), 0x01
    ret

; -----------------------------------------------------------------------------
; restore_input: cursor_visible = 1 + redraw_input_full ? copt fuses 3-line
; Saves 5 bytes per site (4 sites)
; -----------------------------------------------------------------------------
EXTERN _cursor_visible
EXTERN _redraw_input_full
PUBLIC _restore_input
_restore_input:
    ld hl, _cursor_visible
    ld (hl), 0x01
    jp _redraw_input_full

; -----------------------------------------------------------------------------
; overlay_exit_full: common overlay exit sequence
; Sets overlay_mode=0, cursor_visible=1, notif_timeout=0,
; then calls clear_main, notif_clear, redraw_input_full (tail call).
; OPT-SHRINK-R01: Saves ~50-65 bytes (4 call sites ? ~22B ? 4 ? 3B + 22B)
; -----------------------------------------------------------------------------
EXTERN _overlay_mode
EXTERN _notif_timeout
EXTERN _clear_main
EXTERN _notif_clear
PUBLIC _overlay_exit_full
_overlay_exit_full:
    call _overlay_rx_release
    xor a
    ld (_overlay_mode), a
    ld l, a
    ld h, a
    ld (_notif_timeout), hl
    inc a                       ; a = 1
    ld (_cursor_visible), a
    call _clear_main
    call _notif_clear
    jp _redraw_input_full       ; tail call

; -----------------------------------------------------------------------------
; void set_border(uint8_t color) __z88dk_fastcall
; input: L = color
; -----------------------------------------------------------------------------
_set_border:
    ld a, l
    out (0xfe), a
    ret

; -----------------------------------------------------------------------------
; char *skip_spaces(char *p) __z88dk_fastcall
; Advances HL past ASCII spaces (0x20). Returns pointer to first non-space.
; 7 bytes. Replaces 16? inline `while (*p == ' ') p++;` (~8 bytes each)
; -----------------------------------------------------------------------------
PUBLIC _skip_spaces
_skip_spaces:
    ld a, ' '
ss_loop:
    cp (hl)
    ret nz
    inc hl
    jr ss_loop

; -----------------------------------------------------------------------------
; cdecl cleanup wrappers: EXX saves ret addr in HL' (alt register set).
; Safe: targets are leaf functions, SDCC never uses EXX, EXX runs between frames,
; and glyph decompressor's EXX usage doesn't overlap with wrapper call sites.
; For copy_n (void): jp (hl) returns directly ? no push/ret needed.
; For stricmp/stristr: exx/push/exx/ret swaps return value and ret addr.
; -----------------------------------------------------------------------------

; COPT-32: st_copy_n (void return ? 24 sites, saves 4B each)
EXTERN _st_copy_n
PUBLIC _st_copy_n_cleanup
_st_copy_n_cleanup:
    pop hl              ; HL = return address
    exx                 ; save in HL'. Main regs = former alt set.
    call _st_copy_n     ; params at correct stack positions
    pop af              ; cleanup param 1 (2 bytes)
    pop af              ; cleanup param 2 (2 bytes)
    inc sp              ; cleanup param 3 (1 byte)
    exx                 ; restore: HL = return address
    jp (hl)             ; return without push/ret

; -----------------------------------------------------------------------------
; Common beep core:
;   IN:  HL = duration loop count
;        C  = tone mask (e.g. 0x10 or 0x20)
; Uses: A,B,HL (IY not touched ? no push/pop needed)
; -----------------------------------------------------------------------------
_beep_core:

beep_loop:
    ld a, l
    and c               ; tone mask from C (was hardcoded 0x10)
    or 0x08
    ld b, a

    ld a, (_theme_attrs + TA_BORDER)
    and 0x07
    or b

    out (0xFE), a

    dec hl
    ld a, h
    or l
    jr nz, beep_loop

    ret


; -----------------------------------------------------------------------------
; void mention_beep(void)  -- menci?n en canal (beep simple m?s grave)
; -----------------------------------------------------------------------------
PUBLIC _mention_beep
_mention_beep:
    ld a, (_beep_enabled)
    or a
    ret z                   ; Si beep_enabled == 0, salir
IFDEF SPECTALK_NEXT
    call sound_speed_35
    push de
    ld hl, 2500
    ld c, 0x18
    call _beep_core
    pop de
    jr sound_speed_restore
ELSE
    ld hl, 2500             ; M?s largo
    ld c, 0x18              ; Tono m?s grave
    jr _beep_core
ENDIF

; -----------------------------------------------------------------------------
; void key_click(void)  -- micro-pulse keyclick (short blocking pulse)
; -----------------------------------------------------------------------------
PUBLIC _key_click
EXTERN _keyclick_enabled
_key_click:
    ld a, (_keyclick_enabled)
    or a
    ret z
IFDEF SPECTALK_NEXT
    ; NextZXOS click: the ROM BEEPER with HL=$00C8 and PIP=0 plays one cycle,
    ; about 876 T per half at 3.5 MHz. Played here without the ROM, whose
    ; BEEPER re-enables interrupts and takes the border from BORDCR.
    call sound_speed_35
    ld b, 67
ELSE
    ld b, 30
ENDIF
    ld a, (_theme_attrs + TA_BORDER)
    and 0x07                ; preserve theme border colour
    or 0x18                 ; MIC + EAR on
    out (0xFE), a
kclick_w:
    djnz kclick_w
    xor 0x10                ; EAR off, keep MIC + border
    out (0xFE), a
IFDEF SPECTALK_NEXT
    jr sound_speed_restore

; Beeper sounds are timed in T-states, so they are played at 3.5 MHz on any
; Next CPU speed and the selected speed is restored afterwards.
; sound_speed_35: E = previous NextReg $07 speed. Uses A, BC.
sound_speed_35:
    ld bc, 0x243B
    ld a, 0x07
    out (c), a
    inc b
    in a, (c)
    and 0x03
    ld e, a
    xor a
    out (c), a              ; 3.5 MHz
    ret

; In: E = speed saved by sound_speed_35. Uses A, BC.
sound_speed_restore:
    ld bc, 0x243B
    ld a, 0x07
    out (c), a
    inc b
    out (c), e
    ret
ELSE
    ret
ENDIF

; -----------------------------------------------------------------------------
; void check_caps_toggle(void)
; Verifica Caps Shift + 2 y actualiza _caps_lock_mode
; -----------------------------------------------------------------------------
_check_caps_toggle:
    ld bc, 0xFEFE
    in a, (c)
    rra
    jr c, caps_no_combo

    ld bc, 0xF7FE
    in a, (c)
    bit 1, a
    jr nz, caps_no_combo

    ld a, (_caps_latch)
    or a
    ret nz

    ld hl, _caps_lock_mode
    ld a, (hl)
    xor 1
    ld (hl), a
    
    ld hl, _caps_latch
    ld (hl), 1
    ret

caps_no_combo:
    xor a
    ld (_caps_latch), a
    ret

; -----------------------------------------------------------------------------
; uint8_t key_shift_held(void)
; Retorna 1 (en HL) si Caps Shift est? pulsado limpiamente
; -----------------------------------------------------------------------------
_key_shift_held:
    ld bc, 0xFEFE
    in a, (c)
    rra
    jr c, shift_not_held

    ld bc, 0xF7FE
    in a, (c)
    cpl
    and 0x1F
    jr nz, shift_not_held

    ld bc, 0xEFFE
    in a, (c)
    cpl
    and 0x1F
    jr nz, shift_not_held

    ; BREAK is CAPS SHIFT+SPACE and word navigation is CAPS SHIFT+SYMBOL SHIFT.
    ; Neither should count as a clean typing shift for cursor/case state.
    ld bc, 0x7FFE
    in a, (c)
    cpl
    and 0x03
    jr nz, shift_not_held

    ld hl, 1
    ret

shift_not_held:
    ld hl, 0
    ret


