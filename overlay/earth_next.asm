;; ABOUT: globe sprites 0..24 / 8-bit patterns 0..49; logo sprites 25..46,
;; 4-bit patterns 100..121, palette offset 5. Logo lives in frame-page padding.
;; Page 28 holds the initial frame; page 30 holds 48 (page,u16 offset) deltas.
;; Classic SKIP/COPY decoder reconstructs frames in page 75 at MMU2.
;; Two pattern sets avoid modifying the visible frame during the 6400-byte upload.
;; Entry/exit DI; MMU0 and CPU speed restored, IX/IY and shadow registers untouched.
DEFC NEXT_EARTH_FIRST_PAGE = 28
DEFC NEXT_EARTH_FRAMES = 48
DEFC NEXT_STARFIELD_BANK = 38
DEFC NEXT_EARTH_BUFFER_PAGE = 75
DEFC NEXT_EARTH_TABLE_PAGE = 30

next_earth_open:
    ld a,$15
    call next_earth_read_reg
    ld (next_earth_layers),a
    and $FE
    defb $ED,$92,$15
    ld a,$43
    call next_earth_read_reg
    ld (next_earth_palette),a
    and 7
    or $68                     ; write/display second sprite palette; preserve ULA
    defb $ED,$92,$43
    ld a,$4B
    call next_earth_read_reg
    ld (next_earth_transparent),a
    defb $ED,$91,$4B,0

    call next_earth_hide_sprites
    call next_starfield_open

    call next_earth_window_begin
    ld a,NEXT_EARTH_FIRST_PAGE
    defb $ED,$92,$50
    defb $ED,$91,$40,0
    ld hl,$1900
    call next_earth_load_palette
    ld bc,$303B
    ld a,50                    ; 4-bit patterns 100..121
    out (c),a
    ld c,$5B
    ld d,5                     ; page 28+$1B00: first 1280 bytes
    call next_earth_upload
    ld a,NEXT_EARTH_FIRST_PAGE+1
    defb $ED,$92,$50
    ld hl,$1900
    ld d,6                     ; page 29+$1900: remaining 1536 bytes
    call next_earth_upload
    ld a,$52
    call next_earth_read_reg
    push af
    ld a,NEXT_EARTH_BUFFER_PAGE
    defb $ED,$92,$52
    ld a,NEXT_EARTH_FIRST_PAGE
    defb $ED,$92,$50
    ld hl,0
    ld de,$4000
    ld bc,6400
    ldir                       ; start from frame 47; first tick wraps to frame 0
    pop af
    defb $ED,$92,$52
    call next_earth_window_end
    xor a
    ld (_frame_idx),a
    ld (next_earth_patterns),a
    call next_earth_tick
    call next_earth_logo
    ld a,(next_earth_layers)
    and $C0
    or 3                       ; sprites above ULA, over-border ignores clip window
    defb $ED,$92,$15
    ld bc,$123B
    ld a,2                     ; visible Layer 2, no read/write mapping
    out (c),a
    ret

next_earth_close:
    ld a,(_earth_ready)
    or a
    ret z
    call next_earth_hide_sprites ; loader may have left global sprite visibility ON
    call next_starfield_close
    ld a,(next_earth_layers)
    defb $ED,$92,$15
    ld a,(next_earth_palette)
    defb $ED,$92,$43
    ld a,(next_earth_transparent)
    defb $ED,$92,$4B
    ret

next_earth_hide_sprites:
    ; Clear attributes including sprites left by the loader before enabling them.
    ld bc,$303B
    xor a
    out (c),a
    ld bc,$8057
next_earth_hide:
    out (c),a
    out (c),a
    out (c),a
    out (c),a
    djnz next_earth_hide
    ret

next_earth_tick:
    call next_earth_window_begin
    ld a,$52
    call next_earth_read_reg
    push af
    ld a,NEXT_EARTH_BUFFER_PAGE
    defb $ED,$92,$52
    ld a,NEXT_EARTH_TABLE_PAGE
    defb $ED,$92,$50
    ld a,(_frame_idx)
    ld l,a
    ld h,0
    ld e,a
    ld d,0
    add hl,hl
    add hl,de
    ld a,(hl)
    inc hl
    ld e,(hl)
    inc hl
    ld d,(hl)
    ex de,hl
    defb $ED,$92,$50
    ld de,$4000
    call earth_apply_delta
    ld a,(next_earth_patterns)
    ld bc,$303B
    out (c),a
    ld hl,$4000
    ld c,$5B
    ld d,25
    call next_earth_upload
    pop af
    defb $ED,$92,$52
    call next_earth_window_end

    ; Commit the new pattern set after all 25 patterns have been uploaded.
    ld bc,$303B
    xor a
    out (c),a
    ld c,$57
    ld a,(next_earth_patterns)
    or $80
    ld l,a                     ; visible flag and first pattern
    ld e,56                    ; ULA y=24 plus 32-pixel sprite border
    ld h,5
next_earth_row:
    ld d,120                   ; ULA x=88 plus 32-pixel sprite border
    ld b,5
next_earth_sprite:
    out (c),d
    out (c),e
    xor a
    out (c),a
    out (c),l
    inc l
    ld a,d
    add a,16
    ld d,a
    djnz next_earth_sprite
    ld a,e
    add a,16
    ld e,a
    dec h
    jr nz,next_earth_row

    ld a,(next_earth_patterns)
    xor 25
    ld (next_earth_patterns),a
    ld a,(_frame_idx)
    inc a
    cp NEXT_EARTH_FRAMES
    jr c,next_earth_frame_ready
    xor a
next_earth_frame_ready:
    ld (_frame_idx),a
    ret

next_earth_upload:
    ld b,0
    otir
    dec d
    jr nz,next_earth_upload
    ret

next_earth_load_palette:
    ld de,512
next_earth_palette_byte:
    ld a,(hl)
    defb $ED,$92,$44
    inc hl
    dec de
    ld a,d
    or e
    jr nz,next_earth_palette_byte
    ret

next_starfield_open:
    ld bc,$123B
    in a,(c)
    ld (next_starfield_access),a
    xor a
    out (c),a
    call next_starfield_swap_regs
    ld a,$1C
    call next_earth_read_reg
    and 3
    ld (next_starfield_clip_index),a
    call next_starfield_swap_clip
    call next_earth_window_begin
    call next_starfield_unpack
    ld a,NEXT_EARTH_FIRST_PAGE+2
    defb $ED,$92,$50
    ld a,(next_earth_palette)
    and 3
    or $5C                     ; second Layer 2 palette; both second palettes visible
    defb $ED,$92,$43
    defb $ED,$91,$40,0
    ld hl,$1900
    call next_earth_load_palette
    ld a,(next_earth_palette)
    and 3
    or $6C                     ; subsequent upload writes second sprite palette
    defb $ED,$92,$43
    jp next_earth_window_end

next_starfield_unpack:
    ; Reconstruct all 48K from seven scanlines per globe-page tail.
    ; DI, code in MMU1; restore MMU2 before returning to the resident.
    ld a,$52
    call next_earth_read_reg
    push af
    ld a,NEXT_STARFIELD_BANK*2
    ld (next_starfield_dest_page),a
    defb $ED,$92,$52
    ld a,NEXT_EARTH_FIRST_PAGE+3
    ld (next_starfield_source_page),a
    defb $ED,$92,$50
    ld hl,$1900
    ld de,$4000
next_starfield_copy_row:
    ld bc,256
    ldir
    ld a,h
    cp $20
    jr nz,next_starfield_source_ready
    ld h,$19
    ld a,(next_starfield_source_page)
    inc a
    ld (next_starfield_source_page),a
    defb $ED,$92,$50
next_starfield_source_ready:
    ld a,d
    cp $60
    jr nz,next_starfield_copy_row
    ld d,$40
    ld a,(next_starfield_dest_page)
    inc a
    cp NEXT_STARFIELD_BANK*2+6
    jr z,next_starfield_copied
    ld (next_starfield_dest_page),a
    defb $ED,$92,$52
    jr next_starfield_copy_row
next_starfield_copied:
    pop af
    defb $ED,$92,$52
    ret

next_starfield_source_page: db 0
next_starfield_dest_page: db 0

next_starfield_close:
    ld bc,$123B
    xor a
    out (c),a
    call next_starfield_swap_regs
    call next_starfield_swap_clip
    ld a,(next_starfield_clip_index)
    or a
    jr z,next_starfield_clip_restored
    ld d,a
next_starfield_clip_advance:
    ld a,$18
    call next_earth_read_reg
    out (c),a                  ; rewrite unchanged coordinate to advance index
    dec d
    jr nz,next_starfield_clip_advance
next_starfield_clip_restored:
    ld bc,$123B
    ld a,(next_starfield_access)
    out (c),a
    ret

next_starfield_swap_regs:
    ; Exchange desired/saved state. Closing restores both registers and table.
    ld hl,next_starfield_regs
    ld d,6
next_starfield_swap_reg:
    ld a,(hl)
    inc hl
    call next_earth_read_reg
    ld e,(hl)
    ld (hl),a
    out (c),e
    inc hl
    dec d
    jr nz,next_starfield_swap_reg
    ret

next_starfield_swap_clip:
    defb $ED,$91,$1C,1          ; reset only Layer 2 clip index
    ld hl,next_starfield_clip
    ld d,4
next_starfield_clip_coord:
    ld a,$18
    call next_earth_read_reg
    ld e,(hl)
    ld (hl),a
    out (c),e
    inc hl
    dec d
    jr nz,next_starfield_clip_coord
    ret

next_starfield_regs:
    db $12,NEXT_STARFIELD_BANK, $14,0, $16,0, $17,0, $70,0, $71,0
next_starfield_clip: db 0,255,0,191
next_starfield_access: db 0
next_starfield_clip_index: db 0

next_earth_logo:
    ld bc,$303B
    ld a,25
    out (c),a
    ld c,$57
    ld l,100
    ld e,136                   ; ULA y=104
    ld h,2
next_earth_logo_row:
    ld d,72                    ; ULA x=40
    ld b,11
next_earth_logo_sprite:
    out (c),d
    out (c),e
    ld a,$50                   ; palette entries 80..95
    out (c),a
    ld a,l
    srl a
    or $C0                     ; visible, extended, pattern N5..0
    out (c),a
    ld a,l
    rrca
    rrca
    and $40
    or $80                     ; 4-bit, pattern N6 selects half-pattern
    out (c),a
    inc l
    ld a,d
    add a,16
    ld d,a
    djnz next_earth_logo_sprite
    ld a,e
    add a,16
    ld e,a
    dec h
    jr nz,next_earth_logo_row
    ret

next_earth_window_begin:
    di
    ld a,$07
    call next_earth_read_reg
    and 3
    ld (next_earth_cpu),a
    defb $ED,$91,$07,3          ; bounded upload at 28MHz, then restore caller speed
    ld a,$50
    call next_earth_read_reg
    ld (next_earth_mmu),a
    ret
next_earth_window_end:
    ld a,(next_earth_mmu)
    defb $ED,$92,$50
    ld a,(next_earth_cpu)
    defb $ED,$92,$07
    ret
next_earth_read_reg:
    ld bc,$243B
    out (c),a
    inc b
    in a,(c)
    ret

next_earth_layers: db 0
next_earth_palette: db 0
next_earth_transparent: db 0
next_earth_patterns: db 0
next_earth_mmu: db 0
next_earth_cpu: db 0
