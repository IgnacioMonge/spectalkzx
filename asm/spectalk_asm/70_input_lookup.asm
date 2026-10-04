; =============================================================================
; UTF-8 to ASCII + IRC control cleanup.
; Cubre Latin-1 Supplement (C2 80-BF, C3 80-BF) = codepoints 0080-00FF
; and falls back for single-byte Latin-1/CP1252 accents from old IRC clients.
; =============================================================================
PUBLIC _utf8_to_ascii

_utf8_to_ascii:
    push hl                 ; Guardar inicio para retornar
    ld d, h
    ld e, l                 ; DE = escritura, HL = lectura

u8a_loop:
    ld a, (hl)
    or a
    jr z, u8a_done
    
    cp 0x80
    jp c, u8a_copy          ; 00-7F: ASCII

    cp 0xC0
    jp c, u8a_skip1         ; 80-BF: orphan continuation/C1 controls

    cp 0xC2
    jr c, u8a_latin1_single ; C0-C1: single-byte Latin-1 fallback

    cp 0xC4
    jp c, u8a_latin1

    cp 0xE0
    jr c, u8a_2byte_ext     ; C4-DF: UTF-8 2-byte or Latin-1 fallback

    cp 0xF0
    jr c, u8a_3byte         ; E0-EF: 3-byte handler (smart quotes)
    
    ; F0+: 4 bytes
u8a_4byte:
    call u8a_first_cont_or_latin1
    inc hl
    ld a, (hl) : or a : jr z, u8a_store_q
    jr u8a_3byte_have_second

u8a_latin1_single:
    ld c, a
    inc hl
    jp u8a_c3

u8a_2byte_ext:
    call u8a_first_cont_or_latin1
    inc hl
    jr u8a_store_q

u8a_first_cont_or_latin1:
    ld c, a                 ; save lead for Latin-1 fallback
    inc hl
    ld a, (hl) : or a : jr z, u8a_first_cont_fallback
    and 0xC0
    cp 0x80
    ret z
u8a_first_cont_fallback:
    pop af                  ; discard helper return before non-local fallback
    jp u8a_c3

u8a_done:
    xor a
    ld (de), a
    pop hl
    ret

u8a_store_q:
    ld a, '?'
    jp u8a_store

; Smart quotes: E2 80 98/99 ? apostrophe (39), E2 80 9C/9D ? double quote (34)
u8a_3byte:
    cp 0xE2
    jr nz, u8a_3byte_generic
    call u8a_first_cont_or_latin1
    ld a, (hl)
    cp 0x80
    jr nz, u8a_3byte_have_second
    inc hl
    ld a, (hl) : or a : jr z, u8a_store_q
    ld b, a
    and 0xC0
    cp 0x80
    jr nz, u8a_store_q
    ld a, b
    inc hl
    or 0x01                  ; pair 98/99?99, 9C/9D?9D
    ld c, a                  ; save OR'd byte3 (fix: A clobbered by ld)
    cp 0x99
    ld a, 39                 ; apostrophe for smart single quotes
    jp z, u8a_store
    ld a, c                  ; restore OR'd byte3
    cp 0x9D
    ld a, 34                 ; double quote for smart double quotes
    jp z, u8a_store
    ld a, '?'                ; audit L11: unknown E2 80 XX ? '?' not '"'
    jp u8a_store

u8a_3byte_generic:
    call u8a_first_cont_or_latin1
u8a_3byte_have_second:
    inc hl
    ld a, (hl) : or a : jr z, u8a_store_q
    inc hl
    jr u8a_store_q

u8a_skip1:
    inc hl
    jr u8a_store_q

u8a_copy:
    cp 0x02                 ; IRC bold
    jr z, u8a_ascii_skip
    cp 0x0F                 ; IRC reset
    jr z, u8a_ascii_skip
    cp 0x16                 ; IRC reverse
    jr z, u8a_ascii_skip
    cp 0x1F                 ; IRC underline
    jr z, u8a_ascii_skip
    cp 0x03                 ; IRC color
    jr z, u8a_color
    ld (de), a
    inc de
u8a_ascii_skip:
    inc hl
    jp u8a_loop

u8a_color:
    inc hl
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, u8a_color_end
    inc hl
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, u8a_check_bg
    inc hl
u8a_check_bg:
    ld a, (hl)
    cp ','
    jr nz, u8a_color_end
    inc hl
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, u8a_color_end
    inc hl
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, u8a_color_end
    inc hl
u8a_color_end:
    jp u8a_loop

u8a_latin1:
    ; A = C2 o C3
    ld b, a                 ; B = primer byte
    inc hl
    ld a, (hl)
    or a
    jp z, u8a_store_q
    ld c, a                 ; C = segundo byte (80-BF)
    inc hl

    ; Verificar que C es continuation (80-BF)
    and 0xC0
    cp 0x80
    jr nz, u8a_invalid_utf8_latin1

    ; B=C2: codepoint = 80 + (C & 3F) = 80-BF
    ; B=C3: codepoint = C0 + (C & 3F) = C0-FF
    ld a, b
    cp 0xC3
    jr z, u8a_c3            ; OPT: jp?jr

    ; C2: codepoints 80-BF (s?mbolos, ?? etc)
    ld a, c
    cp 0xA1                 ; ?
    ld a, '!'
    jr z, u8a_store         ; OPT: jp?jr
    ld a, c
    cp 0xBF                 ; ?
    ld a, '?'
    jr z, u8a_store         ; OPT: jp?jr
    ld a, c
    cp 0xAB                 ; ?
    ld a, '<'
    jr z, u8a_store         ; OPT: jp?jr
    ld a, c
    cp 0xBB                 ; ?
    ld a, '>'
    jr z, u8a_store         ; OPT: jp?jr
    ld a, ' '               ; resto -> espacio
    jr u8a_store            ; OPT: jp?jr

u8a_c3:
    ; C3: codepoints C0-FF (vocales acentuadas, ?, ?, etc)
    ; ?ndice en tabla = C & 3F (0-3F corresponde a C0-FF)
    ld a, c
    and 0x3F
    ld c, a
    ld b, 0
    push hl             ; FIX-C2: guardar puntero de lectura del string
    ld hl, u8a_tbl_c0
    add hl, bc          ; table may cross a page after nearby shrink/layout shifts
    ld a, (hl)
    pop hl              ; FIX-C2: restaurar puntero de lectura
    jr u8a_store            ; OPT: jp?jr (5 bytes)

u8a_invalid_utf8_latin1:
    dec hl                  ; keep the non-continuation byte for next pass
    jp u8a_store_q
    
u8a_store:
    ld (de), a
    inc de
    jp u8a_loop

; Tabla para C3 80-BF -> codepoints C0-FF (64 bytes)
; ???????? ???????? ???????? ???????? ???????? ???????? ???????? ????????
u8a_tbl_c0:
    defb 'A','A','A','A','A','A','A','C'  ; C0-C7: ????????
    defb 'E','E','E','E','I','I','I','I'  ; C8-CF: ????????
    defb 'D',127,'O','O','O','O','O','x'  ; D0-D7: D,Ñ,O...
    defb 'O','U','U','U','U','Y','T','s'  ; D8-DF: ????????
    defb 'a','a','a','a','a','a','a','c'  ; E0-E7: ????????
    defb 'e','e','e','e','i','i','i','i'  ; E8-EF: ????????
    defb 'o',127,'o','o','o','o','o','/'  ; F0-F7: o,ñ,o...
    defb 'o','u','u','u','u','y','t','y'  ; F8-FF: ????????

; =============================================================================
; void sntp_process_response(const char *line) __z88dk_fastcall
; Parses AT+CIPSNTPTIME? response to extract HH:MM:SS
; HL = line pointer
; Response format: +CIPSNTPTIME:Thu Jan 01 00:00:00 1970
; =============================================================================
EXTERN _sntp_waiting
EXTERN _sntp_queried
EXTERN _time_hour
EXTERN _time_minute
EXTERN _time_second
EXTERN _last_frames_lo
EXTERN _tick_accum
EXTERN _draw_status_bar

IFNDEF SPECTALK_SPECTRANEXT
PUBLIC _sntp_process_response
_sntp_process_response:
    ; Validate the complete response prefix before scanning its payload.
    ld a, h
    or l
    ret z
    ld de, spr_prefix
    ld b, 13
spr_prefix_loop:
    ld a, (de)
    cp (hl)
    ret nz
    inc de
    inc hl
    djnz spr_prefix_loop

spr_scan:
    ld a, (hl)
    or a
    jp z, spr_notfound
    cp 33
    jr nc, spr_candidate
    inc hl
    jr spr_scan

spr_candidate:
    push hl             ; candidate start for bounded retry

    call spr_parse2_checked
    jr c, spr_bad
    cp 24
    jr nc, spr_bad
    ld b, a             ; validated hour
    ld a, (hl)
    cp ':'
    jr nz, spr_bad
    inc hl

    call spr_parse2_checked
    jr c, spr_bad
    cp 60
    jr nc, spr_bad
    ld c, a             ; validated minute
    ld a, (hl)
    cp ':'
    jr nz, spr_bad
    inc hl

    call spr_parse2_checked
    jr c, spr_bad
    cp 60
    jr nc, spr_bad
    ld d, a             ; validated second

    ; The complete HH:MM:SS token must end here, not inside a longer token.
    ld a, (hl)
    or a
    jr z, spr_found
    cp 33
    jr nc, spr_bad

    ; Check for ESP placeholder year: "HH:MM:SS 1970"
spr_year_skip:
    inc hl
    ld a, (hl)
    or a
    jr z, spr_found
    cp 33
    jr c, spr_year_skip
    cp '1'
    jr nz, spr_found
    inc hl
    ld a, (hl)
    cp '9'
    jr nz, spr_found
    inc hl
    ld a, (hl)
    cp '7'
    jr nz, spr_found
    inc hl
    ld a, (hl)
    cp '0'
    jr nz, spr_found
    inc hl
    ld a, (hl)
    or a
    jr z, spr_bad
    cp 33
    jr c, spr_bad

    ; === FOUND HH:MM:SS at HL ===
spr_found:
    pop hl                  ; discard candidate pointer
    ld a, b
    ld (_time_hour), a
    ld a, c
    ld (_time_minute), a
    ld a, d
    ld (_time_second), a

    ; Sync frame ticker to current FRAMES, sntp_waiting = 0, sntp_queried = 1
    ld a, (23672)           ; FRAMES low byte
    ld (_last_frames_lo), a
    xor a
    ld (_tick_accum), a     ; Reset frame accumulator
IFDEF SPECTALK_NEXT
    ld (_tick_accum+1), a   ; Native fractional frame units use both bytes
ENDIF
    ld (_sntp_waiting), a
    inc a
    ld (_sntp_queried), a

    jp _draw_status_bar ; tail call

spr_bad:
    pop hl                  ; reject the complete token, not a matching suffix
spr_skip_token:
    ld a, (hl)
    or a
    jr z, spr_notfound
    cp 33
    jp c, spr_scan
    inc hl
    jr spr_skip_token

spr_notfound:
    xor a
    ld (_sntp_waiting), a
    ret

spr_prefix:
    defm "+CIPSNTPTIME:"

; --- subroutine: validate and parse 2-digit decimal at (HL) ---
; Input:  HL = pointer to first digit
; Output: A = parsed value (0..99), HL = pointer past second digit
;         CF = 0 on success, 1 if either byte is not an ASCII digit
; Clobbers: DE
spr_parse2_checked:
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, spr_parse2_bad
    ld e, a
    inc hl
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, spr_parse2_bad
    ld d, a
    ld a, e
    add a, a            ; *2
    add a, a            ; *4
    add a, e            ; *5
    add a, a            ; *10
    add a, d
    inc hl
    or a                ; clear carry
    ret
spr_parse2_bad:
    scf
    ret
ENDIF

; void sntp_udp_fallback(void)
; Calls SPCTLK6 entry 0 only when numeric SNTP was initialized and no valid
; CIPSNTPTIME/UDP response has been accepted. State 3 suppresses automatic
; idle retries, but direct /server calls may try again before opening TCP.
EXTERN _overlay_exec
EXTERN _sntp_init_sent

IFNDEF SPECTALK_SPECTRANEXT
PUBLIC _sntp_udp_fallback
_sntp_udp_fallback:
    ld a, (_sntp_init_sent)
    or a
    ret z
    ld a, (_sntp_queried)
    or a
    ret nz
    ld a, 3
    ld (_sntp_init_sent), a
    ld hl, 5              ; ovl_id=5, entry_id=0
    push hl
    call _overlay_exec
    ret
ENDIF

; =============================================================================
; uint8_t read_key(void)
; Keyboard handler with debounce and auto-repeat.
; Returns key code in L (0 = no key)
; Uses globals: last_k, repeat_timer, debounce_zero
; Calls: in_inkey()
; =============================================================================
PUBLIC _read_key
EXTERN _in_inkey
EXTERN _last_k
EXTERN _repeat_timer
EXTERN _debounce_zero

DEFC RK_KEY_LEFT = 8
DEFC RK_KEY_RIGHT = 9
DEFC RK_KEY_DOWN = 10
DEFC RK_KEY_UP = 11
DEFC RK_KEY_BS = 12

_read_key:
    call _in_inkey      ; L = key (0 if none)
    ld a, l
    or a
    jr nz, rk_got_key

    ; k == 0: clear state
    xor a
    ld (_last_k), a
    ld (_repeat_timer), a
    ; if (debounce_zero) debounce_zero--
    ld hl, _debounce_zero
    ld a, (hl)
    or a
    jr z, rk_ret_zero
    dec (hl)
rk_ret_zero:
    ld l, 0
    ret

rk_got_key:
    ld b, a             ; B = k

    ; if (k == '0' && debounce_zero > 0) ? suppress
    cp '0'
    jr nz, rk_check_new
    ld hl, _debounce_zero
    ld a, (hl)
    or a
    jr z, rk_check_new
    dec (hl)
    jr rk_ret_zero

rk_check_new:
    ; if (k != last_k) ? new key
    ld a, (_last_k)
    cp b
    jr z, rk_repeat

    ; --- Case fold check: ignore Shift release (e.g. 'S' ? 's') ---
    ; If last_k and k differ only by bit 5, then validate folded letter.
    xor b
    cp 32
    jr nz, rk_new_emit
    ld a, b
    or 32
    cp 'a'
    jr c, rk_new_emit
    cp 'z'+1
    jr nc, rk_new_emit
    ; Same letter, just shift change ? update but don't emit
    ld a, b
    ld (_last_k), a
    jr rk_ret_zero

rk_new_emit:
    ; last_k = k
    ld a, b
    ld (_last_k), a

    ; Set repeat_timer based on key type
    cp RK_KEY_BS
    jr z, rk_new_bs
    sub 8
    cp 2
    jr c, rk_new_arrow
    ; Default: repeat_timer = 20
    ld a, 20
    jr rk_new_set_timer

rk_new_bs:
    ld a, 12
    ld (_repeat_timer), a
    ld a, 8
    ld (_debounce_zero), a
    ld l, b
    ret

rk_new_arrow:
    ld a, 15
rk_new_set_timer:
    ld (_repeat_timer), a
    ; debounce_zero = 0 (non-backspace)
    xor a
    ld (_debounce_zero), a
    ld l, b
    ret

rk_repeat:
    ; k == last_k ? auto-repeat handling

    ; if (k == KEY_BACKSPACE) debounce_zero = 8
    ld a, b
    cp RK_KEY_BS
    jr nz, rk_rep_timer
    ld a, 8
    ld (_debounce_zero), a

rk_rep_timer:
    ; if (repeat_timer > 0) { repeat_timer--; return 0; }
    ld hl, _repeat_timer
    ld a, (hl)
    or a
    jr z, rk_rep_fire
    dec (hl)
    jr rk_ret_zero

rk_rep_fire:
    ; Timer expired ? emit based on key type
    ld a, b
    cp RK_KEY_BS
    jr nz, rk_rep_lr
    ld a, 1
    jr rk_rep_emit

rk_rep_lr:
    sub 8
    cp 2
    jr c, rk_rep_lr_emit
    cp 4
    jr c, rk_rep_ud
    ; Other keys: standard repeat
    ld a, 3
    jr rk_rep_emit

rk_rep_lr_emit:
    ld a, 2
    jr rk_rep_emit

rk_rep_ud:
    ld a, 5
rk_rep_emit:
    ld (_repeat_timer), a
    ld l, b
    ret

; =============================================================================
; void print_char64(uint8_t y, uint8_t col, uint8_t c, uint8_t attr) __z88dk_callee
; Stack (byte-packed): [ret_lo][ret_hi][y][col][c][attr]
; OPT: hand-written ASM replaces SDCC version (33 -> 19 bytes)
; =============================================================================
; void nav_push(uint8_t idx) __z88dk_fastcall
; Push idx onto nav_history ring, dedup top, shift if full.
; OPT: hand-written ASM (79 -> 55 bytes, LDIR replaces byte-by-byte loop)
; =============================================================================
EXTERN _nav_history
EXTERN _nav_hist_ptr
DEFC NAV_HIST_SZ = 6

_nav_push:
    ld c, l                     ; C = idx (fastcall param)
    ld a, (_nav_hist_ptr)
    ld b, a                     ; B = ptr
    or a
    jr z, np_no_dup             ; ptr == 0, skip dup check

    ; Dup check: history[ptr-1] == idx?
    dec a
    ld hl, _nav_history
    add a, l                    ; NAV_HIST_SZ=6, _nav_history+$05 cannot carry
    ld l, a                     ; HL = &history[ptr-1]
    ld a, (hl)
    cp c
    ret z                       ; duplicate, return

np_no_dup:
    ld a, b                     ; A = ptr
    cp NAV_HIST_SZ
    jr c, np_append             ; ptr < 6, just append

    ; Shift left: history[0..4] = history[1..5]
    ld a, c                     ; save idx across LDIR (A is preserved)
    ld hl, _nav_history + 1
    ld de, _nav_history
    ld bc, NAV_HIST_SZ - 1
    ldir
    ld (_nav_history + NAV_HIST_SZ - 1), a
    ret

np_append:
    ; history[ptr] = idx; ptr++
    ld a, b
    ld hl, _nav_history
    add a, l                    ; B is clamped to 0..5 by NAV_HIST_SZ
    ld l, a
    ld (hl), c                  ; history[ptr] = idx
    ld hl, _nav_hist_ptr
    inc (hl)                    ; ptr++
    ret

; =============================================================================
_print_char64:
    pop de                      ; DE = return address
    pop hl                      ; L = y, H = col
    ld a, l
    ld (_g_ps64_y), a
    ld a, h
    ld (_g_ps64_col), a
    pop hl                      ; L = c, H = attr
    ld a, h
    ld (_g_ps64_attr), a
    push de                     ; restore return address for tail call
    jp _print_str64_char        ; fastcall: L = char

; =============================================================================
; int8_t find_channel(const char *name) __z88dk_fastcall
; Search active channels[] by IRC case-insensitive name. Returns slot or -1.
; HL = name pointer
; Returns: L = slot index (0..N) or 0xFF (-1)
; =============================================================================
PUBLIC _find_channel
EXTERN _channels
EXTERN _channel_count
EXTERN _st_stricmp

DEFC FC_CH_SIZE = 32
DEFC FC_FLAGS_OFS = 30
DEFC FC_FLAG_ACTIVE = 0x01

_find_channel:
    push iy
    push hl
    pop iy                       ; IY = target name

    ld de, _channels
    ld b, 0                      ; B = slot index

fc_loop:
    ld a, b
    ld hl, _channel_count
    cp (hl)
    jr nc, fc_ret_neg1

    push de
    ld hl, FC_FLAGS_OFS
    add hl, de
    ld a, (hl)
    pop de
    and FC_FLAG_ACTIVE
    jr z, fc_next

    push de
    push bc
    ex de, hl                    ; HL = ch->name
    call fc_check_name
    pop bc
    pop de
    jr z, fc_found

fc_next:
    ld hl, FC_CH_SIZE
    add hl, de
    ex de, hl
    inc b
    jr fc_loop

fc_found:
    ld a, b
    jr fc_ret_a

fc_ret_neg1:
    ld a, 0xFF
fc_ret_a:
    pop iy
    ld l, a
    ret

fc_check_name:
    push iy
    push hl
    call _st_stricmp
    ld a, l
    or h
    ret

; =============================================================================
; uint8_t is_tracked_friend(const char *nick) __z88dk_fastcall
; HL = nick pointer. Returns L = 1 when nick is in friend_nicks[], else 0.
; =============================================================================
PUBLIC _is_tracked_friend
EXTERN _friend_count
EXTERN _friend_nicks

DEFC ITF_MAX_FRIENDS = 5
DEFC ITF_NICK_SIZE = 18

; uint8_t friend_initial_match(char c) __z88dk_fastcall
; HL fastcall low byte holds c. Returns L=1 if any configured friend has same
; folded first byte, else L=0. Used to avoid token mutation/casefold compare
; for almost all NAMES nicks.
PUBLIC _friend_initial_match
_friend_initial_match:
    ld a, (_friend_count)
    or a
    jr z, fim_no
    ld b, a
    ld a, l
    or 0x20
    ld c, a
    ld de, _friend_nicks
fim_loop:
    ld a, (de)
    or a
    jr z, fim_next
    or 0x20
    cp c
    jr z, fim_yes
fim_next:
    ld hl, ITF_NICK_SIZE
    add hl, de
    ex de, hl
    djnz fim_loop
fim_no:
    ld l, 0
    ret
fim_yes:
    ld l, 1
    ret

_is_tracked_friend:
    ld a, (_friend_count)
    or a
    jr z, itf_no
    ld a, h
    or l
    jr z, itf_no
    ld a, (hl)
    or a
    jr z, itf_no

    push iy
    push hl
    pop iy                       ; IY = nick
    or 0x20
    ld c, a                      ; C = nick[0] folded like the C helper

    ld b, ITF_MAX_FRIENDS
    ld de, _friend_nicks
itf_loop:
    ld a, (de)
    or a
    jr z, itf_next
    or 0x20
    cp c
    jr nz, itf_next

    push de
    push bc
    push iy
    push de
    call _st_stricmp
    ld a, l
    or h
    pop bc
    pop de
    jr z, itf_yes

itf_next:
    ld hl, ITF_NICK_SIZE
    add hl, de
    ex de, hl
    djnz itf_loop
    pop iy
itf_no:
    ld l, 0
    ret
itf_yes:
    pop iy
    ld l, 1
    ret

; =============================================================================
; int8_t find_empty_channel_slot(void)
; Returns index of first inactive slot (1..9) or -1 (0xFF) if full.
; Scans channels[1]..channels[9] checking CH_FLAG_ACTIVE.
; OPT: hand-written ASM replaces SDCC version (46 -> 23 bytes)
; =============================================================================
_find_empty_channel_slot:
    ld hl, _channels + 32 + 30  ; &channels[1].flags
    ld de, 32                    ; struct size
    ld b, 9                      ; slots 1..9
    ld c, 1                      ; current index
fecs_loop:
    bit 0, (hl)                  ; CH_FLAG_ACTIVE?
    jr z, fecs_found             ; not active -> empty slot
    add hl, de
    inc c
    djnz fecs_loop
    ld c, 0xFF                   ; return -1
fecs_found:
    ld l, c                      ; return index
    ret

; =============================================================================
; void snapshot_autojoin_channels(void)
; Build search_pattern from active non-query channel slots for !config display.
; If no active channels exist while connected, clear stale search_pattern.
; =============================================================================
EXTERN _search_pattern
EXTERN _connection_state
DEFC SAC_MAX = 63
_snapshot_autojoin_channels:
    xor a
    ex af, af'                  ; shadow A = changed flag (0/1)
    ld hl, _channels + 32        ; &channels[1].name
    ld de, _search_pattern       ; destination CSV buffer
    ld b, 9                      ; slots 1..9
    ld c, SAC_MAX                ; bytes before final NUL
sac_loop:
    push hl
    ld a, l
    add a, 30                    ; flags offset inside ChannelInfo
    ld l, a
    jr nc, sac_flag_addr
    inc h
sac_flag_addr:
    ld a, (hl)
    pop hl
    and 0x03                     ; ACTIVE | QUERY
    cp 0x01                      ; active channel, not query
    jr nz, sac_next
    ld a, (hl)
    cp '#'
    jr z, sac_chan
    cp '&'
    jr nz, sac_next
sac_chan:
    ld a, c
    cp SAC_MAX
    jr z, sac_copy_start
    cp 2                         ; need room for comma + at least 1 char
    jr c, sac_finish_any
    ld a, ','
    call sac_put_a
    dec c
sac_copy_start:
    push hl
sac_copy:
    ld a, c
    or a
    jr z, sac_full
    ld a, (hl)
    or a
    jr z, sac_copied
    call sac_put_a
    inc hl
    dec c
    jr sac_copy
sac_full:
    pop hl
    jr sac_finish_any
sac_copied:
    pop hl
sac_next:
    ld a, l
    add a, 32
    ld l, a
    jr nc, sac_next_ok
    inc h
sac_next_ok:
    djnz sac_loop
    ld a, c
    cp SAC_MAX
    jr nz, sac_finish_any
    ld a, (_connection_state)
    cp 3                         ; STATE_IRC_READY
    jr c, sac_ret_changed
sac_finish_any:
    xor a
    call sac_put_a
sac_ret_changed:
    ex af, af'
    ld l, a
    ret

; A = byte to write, DE = destination, HL = current channel name pointer.
; Increments DE, preserves HL, and updates shadow A when the byte changed.
sac_put_a:
    ex de, hl                    ; HL = dest, DE = source
    cp (hl)
    jr z, sac_put_same
    ex af, af'
    inc a
    ex af, af'
sac_put_same:
    ld (hl), a
    inc hl
    ex de, hl                    ; HL = source, DE = dest + 1
    ret

; =============================================================================
; int8_t find_query(const char *nick) __z88dk_fastcall
; Search for a nick in channels[]. Returns slot index or -1.
; HL = nick pointer
; Returns: L = slot index (0..N) or 0xFF (-1)
; =============================================================================
PUBLIC _find_query
EXTERN _st_stricmp
EXTERN _st_stricmp
EXTERN _channels        ; ChannelInfo[10], 32 bytes each
EXTERN _channel_count
EXTERN _irc_server
EXTERN _S_CHANSERV
EXTERN _S_NICKSERV
EXTERN _S_GLOBAL

DEFC FQ_CH_SIZE = 32
DEFC FQ_FLAGS_OFS = 30
DEFC FQ_FLAG_ACTIVE = 0x01
DEFC FQ_FLAG_QUERY = 0x02

_find_query:
    ; Validate: if (!nick || !*nick) return -1
    ld a, h
    or l
    jr z, fq_bail_neg1
    ld a, (hl)
    or a
    jr nz, fq_valid

fq_bail_neg1:
    ld l, 0xFF
    ret

fq_valid:

    push iy             ; preserve sdcc frame pointer

    ; Save nick in IY for repeated use
    push hl
    pop iy              ; IY = nick

    ; Service filter: check first char (lowercase)
    or 0x20             ; A = nick[0] | 0x20
    cp 'c'
    jr nz, fq_not_c
    ld hl, _S_CHANSERV
    call fq_check_service
    jr z, fq_ret_a_iy
    jr fq_check_server

fq_not_c:
    cp 'n'
    jr nz, fq_not_n
    ld hl, _S_NICKSERV
    call fq_check_service
    jr z, fq_ret_a_iy
    jr fq_check_server

fq_not_n:
    cp 'g'
    jr nz, fq_check_server
    ld hl, _S_GLOBAL
    call fq_check_service
    jr z, fq_ret_a_iy

fq_check_server:
    ; if (st_stricmp(nick, irc_server) == 0) return 0
    ; Empty irc_server cannot match because nick was checked non-empty above.
    ld hl, _irc_server
    call fq_check_service
    jr z, fq_ret_a_iy

fq_loop_init:
    ; Loop: for i=1; i < channel_count; i++
    ; DE = &channels[1] = channels + 32
    ld de, _channels + FQ_CH_SIZE
    ld b, 1             ; B = i

fq_loop:
    ld a, b
    ld hl, _channel_count
    cp (hl)
    jr nc, fq_ret_neg1_iy ; i >= channel_count

    ; Check flags: (ch->flags & (ACTIVE|QUERY)) == (ACTIVE|QUERY)
    ; flags at offset 30 from DE
    push de             ; save ch base
    ld hl, FQ_FLAGS_OFS
    add hl, de          ; HL = &ch->flags
    ld a, (hl)
    pop de              ; restore ch base
    and FQ_FLAG_ACTIVE | FQ_FLAG_QUERY
    cp FQ_FLAG_ACTIVE | FQ_FLAG_QUERY
    jr nz, fq_next

    ; st_stricmp(ch->name, nick) ? name at offset 0, so DE = &ch->name
    push de             ; save ch base
    push bc             ; save i
    ex de, hl           ; HL = ch->name
    call fq_check_service
    pop bc              ; restore i
    pop de              ; restore ch base
    jr z, fq_found      ; match!

fq_next:
    ; DE += 32 (next channel)
    ld hl, FQ_CH_SIZE
    add hl, de
    ex de, hl           ; DE = next ch
    inc b
    jr fq_loop

fq_found:
    ; Return B (= i)
    ld a, b

fq_ret_a_iy:
    pop iy
    ld l, a
    ret

fq_ret_neg1_iy:
    ld a, 0xFF
    jr fq_ret_a_iy

; --- subroutine: compare IY (nick) with HL (service string) ---
; Input:  HL = string to compare, IY = nick
; Output: Z flag set if match (stricmp == 0)
; Clobbers: AF, BC, DE, HL
fq_check_service:
    push iy             ; arg1: nick
    push hl             ; arg2: service string
    call _st_stricmp
    ld a, l
    or h
    ret

; =============================================================================
; Attribute setter helpers - saves 3 bytes per call vs inline assignment
; current_attr = ATTR_X requires 6 bytes inline (ld a,(nn); ld (nn),a)
; call _set_attr_X requires 3 bytes

