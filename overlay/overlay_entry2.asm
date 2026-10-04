;; overlay_entry2.asm — Entry table for SPCTLK2.OVL
SECTION code_user

EXTERN _about_render_ovl
EXTERN _about_close_ovl
EXTERN _about_packet_slot
EXTERN _esx_handle
EXTERN _esx_buf
EXTERN _esx_count
IFDEF SPECTALK_NEXT
EXTERN _dat_fread
EXTERN _dat_fseek_set
DEFC DATA_FREAD = _dat_fread
DEFC DATA_FSEEK = _dat_fseek_set
ELSE
EXTERN _esx_fread
EXTERN _esx_fseek_set
DEFC DATA_FREAD = _esx_fread
DEFC DATA_FSEEK = _esx_fseek_set
ENDIF
EXTERN _esx_result
EXTERN _earth_apply_frame_delta
EXTERN _earth_apply_attr_delta
EXTERN _earth_validate_frame_delta
EXTERN _earth_validate_attr_delta
EXTERN _earth_draw_frame
DEFC EARTH_PACKET_SIZE  = 512

IFDEF SPECTALK_NEXT
; Native overlay pages persist between calls.  Use their zero-filled tail as
; private scratch; $3FFE..$3FFF remains the payload-length trailer.
DEFC EARTH_PACKET_BUFFER = $3DFE
ELSE
IFDEF SPECTALK_SPECTRANEXT
EXTERN _ring_buffer
DEFC EARTH_PACKET_BUFFER = _ring_buffer
ELSE
DEFC EARTH_PACKET_BUFFER = _about_packet_slot
ENDIF
ENDIF

DEFC EARTH_FRAME_COUNT  = 24
DEFC EARTH_DELTA_OFFSET = 2048

PUBLIC _globe_tick_ovl
PUBLIC _earth_ready
PUBLIC _frame_idx

    dw 3                      ; entry_count = 3
    dw _about_render_ovl      ; entry 0 → about
    dw _about_close_ovl       ; entry 1 → close about DAT handle
    dw _globe_tick_ovl        ; entry 2 → globe animation tick

; ==============================================================================
; ENTRY 2 — Fast ASM Tick (transplanted from C)
; ==============================================================================
_globe_tick_ovl:
    ld a, (_earth_ready)
    or a
    ret z

IFDEF SPECTALK_NEXT
    jp next_earth_tick
ELSE
    ; Draw current buffer FIRST. Anchors visible repaint to consistent
    ; timing right after frame_wait. Variable fread latency is absorbed
    ; into the post-draw window of this same tick, so display update no
    ; longer jitters with disk I/O. Buffer was prepared either by
    ; _about_render_ovl (frame 0) or by previous tick.
    call _earth_draw_frame

    ld hl, EARTH_PACKET_BUFFER
    ld (_esx_buf), hl
    ld hl, EARTH_PACKET_SIZE
    ld (_esx_count), hl
    di
    call DATA_FREAD

IFDEF SPECTALK_SPECTRANEXT
    ld hl, (_esx_result)
    ld de, EARTH_PACKET_SIZE
    or a
    sbc hl, de
ELSE
    ld hl, EARTH_PACKET_SIZE
    or a
    sbc hl, bc
ENDIF
    jr nz, _about_close_ovl       ; tail-call if read fails

    ; Packet: u16 frame_len, frame stream, u8 attr_len, attr stream.
    ld bc, (EARTH_PACKET_BUFFER)
    ld a, b
    or c
    jp z, about_tick_fail
    ld hl, EARTH_PACKET_SIZE - 4
    or a
    sbc hl, bc
    jp c, about_tick_fail

    ld hl, EARTH_PACKET_BUFFER + 2
    call _earth_validate_frame_delta
    jp c, about_tick_fail

    ld a, (hl)
    inc hl
    or a
    jp z, about_tick_fail
    ld c, a
    ld b, 0

    push hl
    add hl, bc
    ld de, EARTH_PACKET_BUFFER + EARTH_PACKET_SIZE + 1
    or a
    sbc hl, de
    pop hl
    jp nc, about_tick_fail

    call _earth_validate_attr_delta
    jp c, about_tick_fail
IFNDEF SPECTALK_SPECTRANEXT
IFNDEF SPECTALK_NEXT
    ei
ENDIF
ENDIF

    ld hl, EARTH_PACKET_BUFFER + 2
    call _earth_apply_frame_delta

    ld hl, (EARTH_PACKET_BUFFER)
    ld de, EARTH_PACKET_BUFFER + 3
    add hl, de
    call _earth_apply_attr_delta

    ; Increment frame and reset stream when wrapped
    ld hl, _frame_idx
    inc (hl)
    ld a, (hl)
    cp EARTH_FRAME_COUNT
    ret nz

    ld hl, EARTH_DELTA_OFFSET
    di
    call DATA_FSEEK
    dec l
    jr nz, _about_close_ovl       ; tail-call if seek fails
IFNDEF SPECTALK_SPECTRANEXT
IFNDEF SPECTALK_NEXT
    ei
ENDIF
ENDIF
    ld a, l
    ld (_frame_idx), a
    ret

about_tick_fail:
    jp _about_close_ovl
ENDIF

IFDEF SPECTALK_NEXT
    PUBLIC next_earth_open
    PUBLIC next_earth_close
    EXTERN earth_apply_delta
    INCLUDE "overlay/earth_next.asm"
ENDIF

_earth_ready: db 0
_frame_idx:   db 0
