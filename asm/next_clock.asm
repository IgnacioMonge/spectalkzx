; Native Next frame rate in units of 1/64 frame per second.
; Core 3.x zxula_timing.vhd: VGA 448/456 ULA clocks per line,
; 312/311 PAL lines, 264 NTSC lines; Pentagon 448*320; HDMI overrides.
; Frequencies follow NextReg $11, including its accelerated VGA modes.
; No video setting, interrupt state, IX or IY is changed.

SECTION code_user
PUBLIC _next_clock_second

_next_clock_second:
    ld a, $11
    call next_clock_read
    and 7
    ld e, a
    ld d, 0
    push de
    ld a, $05
    call next_clock_read
    and 4
    ld e, a                 ; 0=50Hz selection, 4=60Hz selection
    ld a, $03
    call next_clock_read
    and $70
    ld hl, next_clock_48
    cp $20
    jr c, next_clock_mode
    ld hl, next_clock_128
    cp $40
    jr c, next_clock_mode
    ld hl, next_clock_pentagon
    ld e, 0                 ; VGA Pentagon has no 60Hz mode
next_clock_mode:
    pop bc                  ; video timing index, 0..7
    ld a, c
    cp 7
    jr z, next_clock_hdmi
    ld a, e
    or a
    ld de, 14
    jr z, next_clock_index
    add hl, de
next_clock_index:
    ld b, 0
    add hl, bc
    add hl, bc
    ld e, (hl)
    inc hl
    ld d, (hl)
    ex de, hl
    ret
next_clock_hdmi:
    ld a, $05               ; HDMI can run at 60Hz even in Pentagon mode
    call next_clock_read
    and 4
    rrca
    ld c, a
    ld b, 0
    ld hl, next_clock_hdmi_rates
    add hl, bc
    ld e, (hl)
    inc hl
    ld d, (hl)
    ex de, hl
    ret

next_clock_read:
    ld bc, $243B
    out (c), a
    inc b
    in a, (c)
    ret

; round(64 * clock28 / (4 * horizontal_clocks * vertical_lines)).
; VGA0..6: 28MHz, 200/7MHz, 206.25/7MHz, 30,31,32,33MHz.
next_clock_48:
    defw 3205,3271,3373,3434,3549,3663,3777
    defw 3788,3865,3986,4058,4194,4329,4464
next_clock_128:
    defw 3159,3223,3324,3385,3497,3610,3723
    defw 3721,3797,3916,3987,4120,4253,4386
next_clock_pentagon:
    defw 3125,3189,3288,3348,3460,3571,3683
next_clock_hdmi_rates:
    defw 3205,3843           ; 27MHz / (4*432*312), 27MHz / (4*429*262)
