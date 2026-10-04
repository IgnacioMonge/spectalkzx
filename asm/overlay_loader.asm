;; overlay_loader.asm — Load and execute overlays from esxDOS
;; All overlays packed in SPECTALK.OVL as a variable-length atlas.
;; Classic executes from ring_buffer; Spectranext stages into cartridge Page B.
;; overlay_slot (512B, aliased to rx_line) available as scratch data buffer for overlays.

SECTION code_user

EXTERN _ring_buffer
EXTERN _rb_head
EXTERN _rb_tail
EXTERN _rx_pos
EXTERN _esx_fopen
EXTERN _esx_fread
EXTERN _esx_fclose
EXTERN _esx_fseek_set
EXTERN _esx_handle
EXTERN _esx_buf
EXTERN _esx_count
EXTERN _esx_result
EXTERN _ui_err
EXTERN _net_pump_rx
EXTERN _rx_overflow
EXTERN _overlay_exit_full
EXTERN _input_cache_invalidate
EXTERN ___sdcc_enter_ix

IFDEF SPECTALK_SPECTRANEXT
EXTERN _spxn_rom_held
EXTERN _ovl_open
PUBLIC _spxn_overlay_page
PUBLIC _spxn_page_ready

OVL_CODE_BASE       EQU 0x2000
SPXN_PAGEIN         EQU 0x3FF9
SPXN_PAGEOUT        EQU 0x007C
SPXN_SET_PAGE_B     EQU 0x3E36

SECTION bss_user
_spxn_overlay_page: defs 1
_spxn_page_ready:   defs 1
spxn_call_scratch:  defs 2

SECTION code_user
ELSE
OVL_CODE_BASE       EQU _ring_buffer
SECTION bss_user
PUBLIC _overlay_exec_active
_overlay_exec_active: defs 1
SECTION code_user
ENDIF

OVL_ATLAS_HEADER_LEN EQU 64

; void overlay_exec(uint8_t ovl_id, uint8_t entry_id) __z88dk_callee
; SDCC stack: [IX+4]=ovl_id, [IX+5]=entry_id
PUBLIC _overlay_exec
IFDEF SPECTALK_SPECTRANEXT
SPXN_BOOTSTRAP_OFFSET EQU OVL_ATLAS_HEADER_LEN
SPXN_BOOTSTRAP_SIZE   EQU 256
SPXN_BOOTSTRAP_LOAD_SIZE EQU OVL_ATLAS_HEADER_LEN + SPXN_BOOTSTRAP_SIZE

_overlay_exec:
    call ___sdcc_enter_ix
    call _net_pump_rx

    call _ovl_open
    ld a, (_esx_handle)
    or a
    jr z, ovl_spxn_exec_fail

    ld hl, _ring_buffer
    ld (_esx_buf), hl
    ld hl, SPXN_BOOTSTRAP_LOAD_SIZE
    ld (_esx_count), hl
    call _esx_fread
    ld hl, (_esx_result)
    ld de, SPXN_BOOTSTRAP_LOAD_SIZE
    or a
    sbc hl, de
    jr nz, ovl_spxn_exec_fail_close

    ld a, (ix+4)
    call _ring_buffer + SPXN_BOOTSTRAP_OFFSET
    jr c, ovl_spxn_exec_fail

    ; The bootstrap overwrote ring_buffer. Preserve the existing fragmented
    ; line contract before handing control to Page B.
    ld hl, (_rb_head)
    ld de, (_rb_tail)
    ld (_rb_tail), hl
    or a
    sbc hl, de
    ld a, h
    or l
    ld hl, (_rx_pos)
    or h
    or l
    ld hl, _rx_overflow
    or (hl)
    jr z, ovl_spxn_rx_ready
    ld a, 1
ovl_spxn_rx_ready:
    ld (hl), a

    ld a, (ix+5)
    ld (spxn_call_scratch), a
    pop ix
    pop de
    pop bc
    push de
    ld a, (spxn_call_scratch)
    jp ovl_spxn_call

ovl_spxn_exec_fail_close:
    call _esx_fclose
    call _input_cache_invalidate
ovl_spxn_exec_fail:
    ld hl, 0
    ld (ovl_loaded_len), hl
    pop ix
    pop de
    pop bc
    push de
    call _overlay_exit_full
    ld hl, ovl_err_msg
    jp _ui_err
ELSE
_overlay_exec:
    call ___sdcc_enter_ix

    ; Drain UART before overlay (ring_buffer will be overwritten)
    call _net_pump_rx

    ; Open SPECTALK.OVL
    ld hl, ovl_filename
    call _esx_fopen
    ld a, (_esx_handle)
    or a
    jp z, ovl_fail

    ; Read atlas header into ring_buffer.
    ld hl, _ring_buffer
    ld (_esx_buf), hl
    ld hl, OVL_ATLAS_HEADER_LEN
    ld (_esx_count), hl
    call _esx_fread

    ; Header must be complete before we trust table offsets/sizes.
    ld hl, (_esx_result)
    ld a, h
    or a
    jr nz, ovl_fail_close
    ld a, l
    cp OVL_ATLAS_HEADER_LEN
    jr nz, ovl_fail_close

    ; Resolve ovl_id to payload offset/size, then seek to that payload.
    call ovl_atlas_select
    jr c, ovl_fail_close
    call _esx_fseek_set
    jr c, ovl_fail_close

ovl_read:
    ; Read the exact overlay payload into ring_buffer.
    call _esx_fread
    call _esx_fclose
    call _input_cache_invalidate

    ; Never execute a partial/stale ring load.
    ld hl, (_esx_result)
    ld de, (ovl_loaded_len)
    or a
    sbc hl, de
    jr nz, ovl_fail
ovl_read_ok:

    ; Validate entry_id and use a 16-bit table index (255 entries fit).
    ld a, (ix+5)        ; entry_id
    ld hl, _ring_buffer
    cp (hl)             ; compare entry_id vs entry_count (low byte)
    jr nc, ovl_fail     ; entry_id >= entry_count -> invalid

    ; Look up entry point: ring_buffer[2 + entry_id*2]
    ld e, a
    ld d, 0
    sla e
    rl d
    ld hl, _ring_buffer + 2
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)          ; DE = absolute entry address
    ; Reject corrupted entry pointers outside the loaded overlay body.
    call ovl_entry_in_loaded
    jr c, ovl_fail
    push de             ; preserve entry address while RX cleanup uses DE

    ; The overlay has overwritten ring_buffer. Drop any pre-load UART bytes
    ; that were in the ring, and mark overflow if that discarded a fragment.
    ld hl, (_rb_head)
    ld de, (_rb_tail)
    ld (_rb_tail), hl
    or a
    sbc hl, de
    ld a, h
    or l
    ld hl, (_rx_pos)
    or h
    or l
    ld hl, _rx_overflow
    or (hl)
    jr z, ovl_write_rx_overflow
    ld a, 1
ovl_write_rx_overflow:
    ld (hl), a

    ; Callee cleanup: restore IX, remove params, jump to overlay
    pop hl              ; HL = entry address
    pop ix              ; restore IX
    pop de              ; DE = ret addr (caller's return)
    pop bc              ; remove 2 bytes of params (callee cleanup)
    push de             ; push caller's return address back
    jp ovl_enter

ovl_fail_close:
    call _esx_fclose
    jr ovl_fail

ovl_fail:
    ld hl, 0
    ld (ovl_loaded_len), hl
    pop ix
    pop de              ; ret addr
    pop bc              ; remove 2 bytes of params (callee cleanup)
    push de
    call _overlay_exit_full
    ld hl, ovl_err_msg
    jp _ui_err          ; tail call

; Header format: "STOA", version, count, header_len, then <offset,size> words.
; Output: HL = payload offset, ovl_loaded_len/_esx_count = payload size.
; Carry set means invalid atlas/ovl_id.
ovl_atlas_select:
    ld hl, _ring_buffer
    ld a, (hl)
    cp 'S'
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)
    cp 'T'
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)
    cp 'O'
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)
    cp 'A'
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)
    cp 1
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)          ; overlay_count
    or a
    jr z, ovl_atlas_bad
    cp 15               ; 8 + count*4 must fit the 64-byte header
    jr nc, ovl_atlas_bad
    ld c, a
    inc hl
    ld a, (hl)
    cp OVL_ATLAS_HEADER_LEN
    jr nz, ovl_atlas_bad
    inc hl
    ld a, (hl)
    or a
    jr nz, ovl_atlas_bad
    ld a, (ix+4)        ; ovl_id
    cp c                ; ovl_id < overlay_count?
    jr nc, ovl_atlas_bad

    add a, a
    add a, a            ; table offset = 8 + ovl_id * 4
    add a, 8
    ld l, a             ; H still high(_ring_buffer)
    ld e, (hl)
    inc hl
    ld d, (hl)          ; DE = payload offset
    inc hl
    ld c, (hl)
    ld a, c
    ld (ovl_loaded_len), a
    ld (_esx_count), a
    inc hl
    ld b, (hl)
    ld a, b
    ld (ovl_loaded_len+1), a
    ld (_esx_count+1), a
    or c
    jr z, ovl_atlas_bad
    ld a, b
    cp 8
    jr c, ovl_atlas_size_ok
    jr nz, ovl_atlas_bad
    ld a, c
    or a
    jr nz, ovl_atlas_bad
ovl_atlas_size_ok:
    ex de, hl           ; HL = payload offset
    ld de, OVL_ATLAS_HEADER_LEN
    or a
    sbc hl, de
    jr c, ovl_atlas_bad ; payload must follow the complete header/table
    add hl, de
    or a
    ret

ovl_atlas_bad:
    scf
    ret
ENDIF

; void overlay_call(uint8_t entry_id) __z88dk_fastcall
; Call entry in the already-loaded Classic ring or Spectranext SRAM page.
; No disk I/O.
; Used for per-frame animation ticks while overlay is resident.
PUBLIC _overlay_call
_overlay_call:
IFDEF SPECTALK_SPECTRANEXT
    ld      a, l
    jp      ovl_spxn_call
ELSE
    ld      a, l             ; entry_id (fastcall: param in L)
    ld      hl, _ring_buffer
    cp      (hl)             ; entry_id < entry_count?
    ret     nc               ; invalid/corrupt table -> ignore safely
    ld      e, a
    ld      d, 0
    sla     e
    rl      d
    ld      hl, _ring_buffer + 2
    add     hl, de
    ld      e, (hl)
    inc     hl
    ld      d, (hl)          ; DE = entry function address
    ; Reject corrupt entry pointers outside the resident overlay body.
    call    ovl_entry_in_loaded
    ret     c
    ex      de, hl
    jp      ovl_enter
ENDIF

IFNDEF SPECTALK_SPECTRANEXT
; Keep RX producers away from the code until its final RET.
ovl_enter:
    ld a, 1
    ld (_overlay_exec_active), a
    ld de, ovl_return
    push de
    jp (hl)
ovl_return:
    xor a
    ld (_overlay_exec_active), a
    ret
ENDIF

; DE = candidate entry address. Carry set means outside the loaded body.
; Zero until an atlas load validates and selects a payload.
ovl_entry_in_loaded:
    push    de
    ex      de, hl
    ld      de, OVL_CODE_BASE
    or      a
    sbc     hl, de           ; HL = entry - ring_buffer
    jr      c, ovl_entry_bad
    ld      a, (OVL_CODE_BASE + 1)
    or      a
    jr      nz, ovl_entry_bad ; entry count is a word, limited to 255
    ld      a, (OVL_CODE_BASE)
    ld      e, a
    ld      d, 0
    sla     e
    rl      d
    inc     de
    inc     de               ; DE = complete entry-table length
    or      a
    sbc     hl, de
    jr      c, ovl_entry_bad ; entry points into header/table
    add     hl, de
    ld      de, (ovl_loaded_len)
    or      a
    sbc     hl, de
    jr      nc, ovl_entry_bad ; offset >= loaded_len
    pop     de
    or      a
    ret

ovl_entry_bad:
    pop     de
    scf
    ret

ovl_loaded_len:
    DEFW    0
IFDEF SPECTALK_SPECTRANEXT
PUBLIC _spxn_overlay_len
DEFC _spxn_overlay_len = ovl_loaded_len
ENDIF

; void overlay_call_timed(uint8_t entry_id) __z88dk_fastcall
; Same ABI as overlay_call. Classic enables IM1 during the ABOUT tick;
; Spectranext remains DI and lets frame_wait() page out for the interrupt.
PUBLIC _overlay_call_timed
_overlay_call_timed:
IFDEF SPECTALK_SPECTRANEXT
    ; Page B covers the IM1 vector while an overlay runs. Target overlays stay
    ; DI and use frame_wait(), which briefly pages the cartridge out safely.
    jp      _overlay_call
ELSE
    push    iy
    ld      iy, 0x5C3A        ; ROM ISR expects IY = system variables
    ei
    call    _overlay_call
    di
    pop     iy
    ret
ENDIF

IFDEF SPECTALK_SPECTRANEXT
; A=entry id. Map the reusable page, validate its absolute entry pointer, and
; return through ovl_spxn_return so the cartridge never leaks mapped state.
ovl_spxn_call:
    ld (spxn_call_scratch), a
    ld a, (_spxn_page_ready)
    or a
    ret z
    di
    call SPXN_PAGEIN
    ld a, (_spxn_overlay_page)
    call SPXN_SET_PAGE_B
    ld a, 1
    ld (_spxn_rom_held), a

    ld a, (spxn_call_scratch)
    ld hl, OVL_CODE_BASE
    cp (hl)
    jr nc, ovl_spxn_call_bad
    add a, a
    jr c, ovl_spxn_call_bad
    ld e, a
    ld d, 0
    ld hl, OVL_CODE_BASE + 2
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)
    call ovl_entry_in_loaded
    jr c, ovl_spxn_call_bad
    ld hl, ovl_spxn_return
    push hl
    push de
    ret

ovl_spxn_call_bad:
    call ovl_spxn_pageout
    ret

ovl_spxn_return:
    ld (spxn_call_scratch), hl
    call ovl_spxn_pageout
    ld hl, (spxn_call_scratch)
    ret

ovl_spxn_pageout:
    di
    xor a
    ld (_spxn_rom_held), a
    call SPXN_PAGEOUT
    ret
ENDIF

IFNDEF SPECTALK_SPECTRANEXT
ovl_filename:
    DEFM "SPECTALK.OVL"
    DEFB 0
ENDIF

ovl_err_msg:
    DEFM "Overlay load failed"
    DEFB 0
