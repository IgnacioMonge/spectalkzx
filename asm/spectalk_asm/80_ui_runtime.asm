; =============================================================================
PUBLIC _set_attr_sys
PUBLIC _set_attr_err
PUBLIC _set_attr_priv
PUBLIC _set_attr_chan
PUBLIC _set_attr_nick
PUBLIC _set_attr_join
; Fused set_attr + main_puts/main_print (copt targets)
PUBLIC _sys_puts
PUBLIC _err_puts
PUBLIC _priv_puts
PUBLIC _nick_puts
PUBLIC _join_puts
PUBLIC _sys_print
PUBLIC _err_print
PUBLIC _priv_print
PUBLIC _ui_sys
PUBLIC _ui_err
EXTERN _current_attr
; theme_attrs offsets: 9=SERVER/SYS 15=ERROR 4=PRIV 2=CHAN 11=NICK 10=JOIN

_set_attr_sys:
    ld a, (_theme_attrs + 9)  ; ATTR_MSG_SERVER
    jr set_attr_common

_set_attr_err:
    ld a, (_theme_attrs + 15) ; ATTR_ERROR
    jr set_attr_common

_set_attr_priv:
    ld a, (_theme_attrs + 4)  ; ATTR_MSG_PRIV
    jr set_attr_common

_set_attr_chan:
    ld a, (_theme_attrs + TA_MSG_CHAN)
    jr set_attr_common

_set_attr_nick:
    ld a, (_theme_attrs + 11) ; ATTR_MSG_NICK
    jr set_attr_common

_set_attr_join:
    ld a, (_theme_attrs + 10) ; ATTR_MSG_JOIN
    ; fall through to set_attr_common

set_attr_common:
    ld (_current_attr), a
    ret

; -----------------------------------------------------------------------------
; set_nick_color: per-nick deterministic color from hash
; Input: HL = nick string pointer (__z88dk_fastcall)
; If nick_color_mode == 0, falls back to set_attr_nick (mono theme)
; Hash: add+rlc3 (best distribution across 6 colors)
; -----------------------------------------------------------------------------
PUBLIC _set_nick_color
EXTERN _nick_color_mode
_set_nick_color:
    ld a, (_nick_color_mode)
    or a
    jr nz, snc_hash
    jr _set_attr_nick
snc_hash:
    ld d, 0
snc_loop:
    ld a, (hl)
    or a
    jr z, snc_done
    add a, d
    rlca
    rlca
    rlca
    ld d, a
    inc hl
    jr snc_loop
snc_done:
    ld a, d
snc_mod6:
    sub 6
    jr nc, snc_mod6
    add a, 7                    ; restore underflowed remainder and add ink +1
snc_ink:
    ld d, a
    ld a, (_theme_attrs + 11)
    ld e, a
    and 0x38
    rrca
    rrca
    rrca
    cp d
    jr nz, snc_ok
    inc d
snc_ok:
    ld a, e
    and 0xF8
    or d
    ld (_current_attr), a
    ret

; -----------------------------------------------------------------------------
; Fused set_attr + main_puts (copt targets, HL = string)
; Each entry: ld a, theme offset ? fall through to attr_puts
; -----------------------------------------------------------------------------
_sys_puts:
    ld a, (_theme_attrs + 9)
    jr attr_puts
_err_puts:
    ld a, (_theme_attrs + 15)
    jr attr_puts
_priv_puts:
    ld a, (_theme_attrs + 4)
    jr attr_puts
_nick_puts:
    ld a, (_theme_attrs + 11)
    jr attr_puts
_join_puts:
    ld a, (_theme_attrs + 10)
attr_puts:
    ld (_current_attr), a
    jp _main_puts

; Fused set_attr + main_print (copt targets, HL = string)
_sys_print:
_ui_sys:
    ld a, (_theme_attrs + 9)
    jr attr_print
_err_print:
_ui_err:
    ld a, (_theme_attrs + 15)
    jr attr_print
_priv_print:
    ld a, (_theme_attrs + 4)
attr_print:
    ld (_current_attr), a
    jp _main_print

; -----------------------------------------------------------------------------
; copt fused call targets for frequent ld hl,const / call fn patterns
; -----------------------------------------------------------------------------
EXTERN _net_send_string
PUBLIC _puts_colon_sp
PUBLIC _net_sp_colon
PUBLIC _net_privmsg
EXTERN _S_COLON_SP
EXTERN _S_SP_COLON
EXTERN _S_PRIVMSG

_puts_colon_sp:
    ld hl, _S_COLON_SP
    jp _main_puts
_net_sp_colon:
    ld hl, _S_SP_COLON
    jp _net_send_string
_net_privmsg:
    ld hl, _S_PRIVMSG
    jp _net_send_string

; =============================================================================
; COMPACT KEYBOARD READER (replaces z88dk in_inkey)
; Saves ~80 bytes: no rowtable (bit-scan instead), no CAPS+SYM table section,
; no ghost-key detection (unnecessary for single-user IRC client).
; Returns: HL = ASCII code (0 if no key)
; =============================================================================
_in_inkey:
asm_in_inkey:
    ld bc, 0xFEFE          ; B = row $FE, C = port $FE
    ld de, 0               ; E = table offset accumulator, D = 0 for table add

    ; --- Row 0: CAPS SHIFT row (port $FEFE) ---
    in a,(c)
    or 0xE1                ; mask CS (bit0) + bits 5-7
    inc a
    jr nz, ik_found

    ; --- Rows 1-6: main keyboard rows ---
    ld b, 0xFD
ik_row_loop:
    ld a, e
    add a, 5
    ld e, a                ; E += 5 (next row base)
    in a,(c)
    or 0xE0                ; mask bits 5-7
    inc a
    jr nz, ik_found
    rlc b
    jp m, ik_row_loop      ; loop while bit 7 set ($FD..$BF)

    ; --- Row 7: SYM SHIFT row (port $7FFE, B=$7F after loop) ---
    ld e, 35               ; row 7 base after rows 1-6
    in a,(c)
    or 0xE2                ; mask SS (bit1) + bits 5-7
    inc a
    jr nz, ik_found

    ; No key pressed
ik_nokey:
    ld hl, 0
    ret

ik_found:
    dec a                  ; restore row byte after compact no-key test
    ; A = row reading (one of bits 0-4 is 0 = pressed key)
    ; Bit-scan from bit 0 to find key position
ik_bitscan:
    rra
    jr nc, ik_gotkey
    inc e
    jr ik_bitscan

ik_gotkey:
    ; E = table index (row base + key position), D = 0
    ld hl, ik_keytable
    add hl, de             ; HL -> unshifted table entry

    ; --- Shift detection ---
    ld a, 0xFE
    in a,(0xFE)            ; read CAPS SHIFT row
    ld c, a                ; C bit0: 0=CS pressed, 1=not
    ld a, 0x7F
    in a,(0xFE)            ; read SYM SHIFT row

    bit 0, c
    jr nz, ik_nocaps
    ; CAPS is pressed ? check if SYM also pressed
    bit 1, a
    jr z, ik_nokey         ; both shifts = ignore (no CTRL codes needed)
    ld e, 40
    jr ik_add_hl           ; -> CAPS section

ik_nocaps:
    bit 1, a
    jr nz, ik_lookup       ; no shift
    ld e, 80
ik_add_hl:
    add hl, de             ; -> shifted table section

ik_lookup:
    ld l, (hl)
    ld h, 0
    ret

; --- Translation table: 120 bytes (unshifted + CAPS + SYM) ---
; Row order: 0=$FEFE(CS,Z,X,C,V) 1=$FDFE(A,S,D,F,G) 2=$FBFE(Q,W,E,R,T)
;            3=$F7FE(1,2,3,4,5) 4=$EFFE(0,9,8,7,6) 5=$DFFE(P,O,I,U,Y)
;            6=$BFFE(EN,L,K,J,H) 7=$7FFE(SP,SS,M,N,B)
ik_keytable:
    ; Unshifted (offset 0-39)
    defb 0xFF, 'z','x','c','v'     ; row 0
    defb 'a','s','d','f','g'       ; row 1
    defb 'q','w','e','r','t'       ; row 2
    defb '1','2','3','4','5'       ; row 3
    defb '0','9','8','7','6'       ; row 4
    defb 'p','o','i','u','y'       ; row 5
    defb  13,'l','k','j','h'       ; row 6 (13=ENTER)
    defb  32,0xFF,'m','n','b'      ; row 7 (32=SPACE, 0xFF=SS)

    ; CAPS shifted (offset 40-79)
    defb 0xFF, 'Z','X','C','V'     ; row 0
    defb 'A','S','D','F','G'       ; row 1
    defb 'Q','W','E','R','T'       ; row 2
    defb   7,  6,128,129,  8       ; row 3 (EDIT,CAPSLOCK,TRUEVID,INVVID,LEFT)
    defb  12,  8,  9, 11, 10       ; row 4 (DELETE,RIGHT,TAB,UP,DOWN)
    defb 'P','O','I','U','Y'       ; row 5
    defb  13, 'L','K','J','H'      ; row 6
    defb   3,0xFF,'M','N','B'      ; row 7 (3=BREAK=CS+SPACE)

    ; SYM shifted (offset 80-119)
    defb 0xFF, ':','`','?','/'      ; row 0
    defb '~','|','\\','{','}'      ; row 1
    defb 131,132,133, '<','>'       ; row 2 (131-133=gfx chars)
    defb '!','@','#','$','%'       ; row 3
    defb '_',')','(', 39,'&'       ; row 4 (39=apostrophe)
    defb  34, ';',130,']','['       ; row 5 (34=quote, 130=gfx)
    defb  13, '=','+','-','^'      ; row 6
    defb  32,0xFF,'.',',','*'      ; row 7

; =============================================================================
; WORD NAVIGATION ? SS+LEFT/RIGHT/UP/DOWN/BACKSPACE
; =============================================================================

EXTERN _cursor_pos
EXTERN _line_len
EXTERN _cursor_hide
EXTERN _cursor_show
EXTERN _redraw_input_from
EXTERN _text_shift_left

; uint8_t key_ss_arrow(void)
; Reads raw keyboard ports for SS + CS + key combos.
; Returns: 0=none, 1=SS+LEFT, 2=SS+RIGHT, 3=SS+BACKSPACE,
;          4=SS+UP, 5=SS+DOWN
PUBLIC _key_ss_arrow
_key_ss_arrow:
    ; Check Symbol Shift (0x7FFE bit 1)
    ld a, 0x7F
    in a, (0xFE)
    bit 1, a
    ld l, 0
    ret nz              ; SS not pressed ? 0
    ; Check Caps Shift (0xFEFE bit 0) ? needed for arrow keys
    ld a, 0xFE
    in a, (0xFE)
    rrca
    ret c               ; CS not pressed ? 0
    ; Check key 5 = LEFT (0xF7FE bit 4)
    ld a, 0xF7
    in a, (0xFE)
    ld l, 1             ; SS+LEFT ? 1
    bit 4, a
    ret z
    ; Check key 8 = RIGHT (0xEFFE bit 2)
    inc l               ; SS+RIGHT ? 2
    ld a, 0xEF
    in a, (0xFE)
    bit 2, a
    ret z
    ; Check key 0 = BACKSPACE (0xEFFE bit 0)
    ; A still has 0xEFFE result from above
    inc l               ; SS+BACKSPACE ? 3
    bit 0, a
    ret z
    ; Check key 7 = UP (0xEFFE bit 3)
    inc l               ; SS+UP ? 4
    bit 3, a
    ret z
    ; Check key 6 = DOWN (0xEFFE bit 4)
    inc l               ; SS+DOWN ? 5
    bit 4, a
    ret z
    ld l, 0
    ret

; wb_left_clean: A = pos ? A = new pos (word boundary left, pointer walking)
wb_left_clean:
    or a
    ret z
    ld c, a
    ld b, 0
    ld hl, _line_buffer
    add hl, bc
    ; Phase 1: skip spaces backward
wbl_sp:
    dec hl
    ld a, (hl)
    cp ' '
    jr nz, wbl_wd
    dec c
    jr nz, wbl_sp
    xor a
    ret
    ; Phase 2: skip non-spaces backward
wbl_wd:
    ld a, ' '
    cpdr
    jr nz, wbl_ret0
    inc c               ; CPDR leaves C at space index; return one past it
    ld a, c
    ret
wbl_ret0:
    xor a               ; no previous space: start of line
    ret

; wb_right: A = pos ? A = new pos (word boundary right, pointer walking)
wb_right:
    ld c, a
    ld b, 0
    ld hl, _line_buffer
    add hl, bc
wbr_wd:
    ld a, (hl)
    cp 33
    jr c, wbr_sp
    inc hl
    inc c
    jr wbr_wd
wbr_sp:
    ld a, (hl)
    cp ' '
    jr nz, wbr_done
    inc hl
    inc c
    jr wbr_sp
wbr_done:
    ld a, c
    ret

; void input_word_left(void)
_input_word_left:
    ld a, (_cursor_pos)
    call wb_left_clean
    jr wm_apply

; void input_word_right(void)
_input_word_right:
    ld a, (_cursor_pos)
    call wb_right
    jr wm_apply

; void input_line_start(void)
_input_line_start:
    xor a
    jr wm_apply

; void input_line_end(void)
_input_line_end:
    ld a, (_line_len)
    jr wm_apply

; Common tail: A = new_pos, apply cursor move
wm_apply:
    ld c, a
    ld a, (_cursor_pos)
    cp c
    ret z
    push bc
    call _cursor_hide
    pop bc
    ld a, c
    ld (_cursor_pos), a
    jp _cursor_show

; void input_delete_word(void)
_input_delete_word:
    ld a, (_cursor_pos)
    ld e, a                 ; old cursor_pos survives wb_left_clean
    call wb_left_clean      ; A = new_pos (word boundary)
    cp e
    ret z
    ld c, a                 ; C = new_pos
    ld a, e                 ; A = old cursor_pos
    sub c
    ld b, a                 ; B = del_count = cursor_pos - new_pos
    push bc
    call _cursor_hide
    pop bc                  ; B = del_count, C = new_pos
    ; LDIR: copy line_buffer[cursor_pos..line_len] to line_buffer[new_pos..]
    push bc
    ld e, c
    ld d, 0
    ld hl, _line_buffer
    add hl, de              ; HL = dest = &line_buffer[new_pos]
    push hl
    ld e, b                 ; E = del_count
    add hl, de              ; HL = source = dest + del_count
    pop de                  ; DE = dest
    ld a, (_line_len)
    sub c
    sub b                   ; A = line_len - cursor_pos
    inc a                   ; +1 for NUL terminator
    ld c, a
    ld b, 0                 ; BC = byte count
    ldir
    pop bc                  ; B = del_count, C = new_pos
    ld a, (_line_len)
    sub b
    ld (_line_len), a
    ld a, c
    ld (_cursor_pos), a
    ld l, c
    jp _redraw_input_from

; =============================================================================
; FATAL MESSAGE ? prints to screen using ROM font, then loops forever
; void fatal_msg(const char *msg) __z88dk_fastcall  ? never returns
; Writes directly to VRAM (0x4000) + attrs (0x5800). No ROM calls needed.
; Uses Spectrum ROM font at 0x3D00 (hardcoded, no sysvar dependency).
; =============================================================================
PUBLIC _fatal_msg
_fatal_msg:
    ; HL = message string (fastcall). Never returns.
IFDEF SPECTALK_SPECTRANEXT
    push hl
    call _resources_release
    ld a, l
    or a
    pop hl
    jr z, fm_resources_closed
    ld hl, resources_close_error
fm_resources_closed:
ENDIF
    ; Set border red
    ld a, 2
    out (254), a
    ; Clear entire screen: pixels (6144B) + attrs (768B) = 6912 bytes at 0x4000
    push hl
    ld hl, 0x4000
    ld (hl), 0
    ld d, h
    ld e, l
    inc de
    ld bc, 6911
    ldir
    ; Set attrs for row 11 (32 cells at 0x5960): BRIGHT + RED paper + WHITE ink
    ld hl, 0x5960
    ld a, 0x57
    ld b, 32
fm_attr:
    ld (hl), a
    inc hl
    djnz fm_attr
    pop hl               ; HL = message
    ; Count string length
    push hl
    ld b, 0
fm_len:
    ld a, (hl)
    or a
    jr z, fm_ctr
    inc b
    inc hl
    jr fm_len
fm_ctr:
    pop hl               ; HL = message start
    ; Center: start col = (32 - len) / 2
    ld a, 32
    sub b
    srl a
    ; Row 11 scanline 0: H=0x48|(11&0x18>>3)<<3=0x48, L=(11&7)<<5=0x60
    ; Actually: row 11 ? third=1 (8-15), row_in_third=3
    ; H = 0x40 | (third << 3) | scanline = 0x48 | 0 = 0x48
    ; L = (row_in_third << 5) | col = (3 << 5) | col = 0x60 | col
    or 0x60              ; A = 0x60 | start_col (row 11, scanline 0 base)
    ld e, a              ; E = low byte base for row 11
fm_char:
    ld a, (hl)
    or a
    jr z, fm_done
    push hl
    sub 32
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl           ; HL = (char-32) * 8
    ld bc, 0x3D00
    add hl, bc            ; HL = glyph address
    ; Write 8 scanlines: D=0x48+S, E=column.
    ld d, 0x48            ; D = high byte base for row 11
    ld b, 8
fm_scan:
    ld a, (hl)
    ld (de), a
    inc hl
    inc d                 ; next scanline
    djnz fm_scan
    inc e                 ; next column
    pop hl
    inc hl
    jr fm_char
fm_done:
    jr fm_done

; =============================================================================
; FRAMELESS ASM CALLEE FUNCTIONS (dev43 optimization)
; =============================================================================

; void sys_puts_print(const char *label, const char *value) __z88dk_callee
; set_attr_sys(); main_puts(label); main_print(value);
_sys_puts_print:
    pop bc              ; return address
    pop hl              ; label
    pop de              ; value
    push bc             ; save return address FIRST (bottom)
    push de             ; save value SECOND (top)
    call _sys_puts      ; sets ATTR_SYS + prints label
    pop hl              ; value (top of stack)
    jp _main_print      ; tail call ? ret pops saved return address

; void irc_send_cmd1(const char *cmd, const char *p1) __z88dk_callee
; Calls cdecl irc_send_cmd_internal(cmd, p1, NULL)
_irc_send_cmd1:
    pop hl              ; ret addr
    pop de              ; cmd
    pop bc              ; p1
    push hl             ; save ret addr
    push ix             ; save IX (irc_send_cmd_internal clobbers it via pop ix)
    ld hl, 0
    push hl             ; p2 = NULL
    push bc             ; p1
    push de             ; cmd
    jr isc_do_call      ; OPT-SHRINK: shared tail saves 3B

; void irc_send_cmd2(const char *cmd, const char *p1, const char *p2) __z88dk_callee
; Calls cdecl irc_send_cmd_internal(cmd, p1, p2)
_irc_send_cmd2:
    pop hl              ; ret addr
    pop de              ; cmd
    pop bc              ; p1
    ex (sp), hl         ; HL = p2, (SP) = ret addr
    push ix             ; save IX
    push hl             ; p2
    push bc             ; p1
    push de             ; cmd
isc_do_call:
    call _irc_send_cmd_internal
    pop af              ; cleanup cmd
    pop af              ; cleanup p1
    pop af              ; cleanup p2
    pop ix              ; restore IX
    ret                 ; return via saved addr

; uint8_t ensure_args(const char *args, const char *usage) __z88dk_callee
; Returns 1 if args non-empty, else calls ui_usage(usage) and returns 0.
_ensure_args:
    pop bc              ; return address
    pop hl              ; args
    pop de              ; usage
    push bc             ; restore return addr
    ld a, h
    or l
    jr z, ea_fail       ; args == NULL
    ld a, (hl)
    or a
    jr z, ea_fail       ; *args == '\0'
    ld l, 1             ; return 1
    ret
ea_fail:
    ex de, hl           ; HL = usage (fastcall arg for ui_usage)
    call _ui_usage
    ld l, 0             ; return 0
    ret

; void fast_u8_to_str(char *buf, uint8_t val) __z88dk_callee
; Writes 2 ASCII digits (tens, units) to buf. No null terminator.
u8_div10:
    ld b, '0'
u8_div10_loop:
    ld a, c
    sub 10
    ret c               ; C remains remainder
    ld c, a
    inc b
    jr u8_div10_loop

_fast_u8_to_str:
    pop hl              ; return address
    pop de              ; DE = buf
    pop bc              ; C = val (1B param, reads 1B extra from caller)
    dec sp              ; FIX: compensate extra byte consumed by pop
    push hl             ; restore return addr
    ex de, hl           ; HL = buf
    call u8_div10
    ld (hl), b          ; buf[0] = tens
    inc hl
    ld a, c
    add a, '0'
    ld (hl), a          ; buf[1] = units
    ret

; void print_big_str(uint8_t y, uint8_t col, const char *s, uint8_t attr) __z88dk_callee
; Sets g_ps64_y, g_ps64_col, g_ps64_attr, then loops calling draw_big_char per char.
; Stack: [ret 2B] [y 1B] [col 1B] [s 2B] [attr 1B] = 7 bytes
_print_big_str:
    pop de              ; DE = return addr
    pop bc              ; C = y, B = col (two uint8_t, byte-packed in one pop)
    pop hl              ; HL = s (pointer, 2B)
    ld a, c
    ld (_g_ps64_y), a
    ld a, b
    ld (_g_ps64_col), a
    ; attr is 1 byte remaining on stack
    pop bc              ; C = attr (1B param, reads 1B extra from caller)
    dec sp              ; FIX: compensate extra byte consumed by pop
    push de             ; push return addr back
    ld a, c
    ld (_g_ps64_attr), a
pbs_loop:
    ld a, (hl)
    or a
    ret z               ; null ? done, ret to caller
    push hl             ; save string pointer
    ld l, a             ; fastcall arg for draw_big_char
    call _draw_big_char
    ld hl, _g_ps64_col
    inc (hl)            ; g_ps64_col++
    pop hl              ; restore string pointer
    inc hl              ; next char
    jr pbs_loop

; char *sb_put_u8_2d(char *p, uint8_t v) __z88dk_callee
; Status-bar slot counters are bounded by MAX_CHANNELS=10, so both callsites
; only ever pass 0..9 and the helper can stay single-digit.
_sb_put_u8_2d:
    pop bc              ; return addr
    pop hl              ; HL = p
    pop de              ; E = v (1B param, reads 1B extra from caller)
    dec sp              ; FIX: compensate extra byte consumed by pop
    push bc             ; restore return addr
    ld a, e
    add a, '0'
    ld (hl), a
    inc hl              ; HL = next position (return value)
    ret

; void puts_u8_nolz(uint8_t v) __z88dk_fastcall
; Prints uint8 without leading zero. L = value.
_puts_u8_nolz:
    ld c, l             ; C = value
    call u8_div10
    ; B = tens char, C = remainder
    ld a, b
    cp '0'
    jr z, pu8_skip_tens
    ld l, a             ; fastcall arg
    push bc
    call _main_putc
    pop bc
pu8_skip_tens:
    ld a, c
    add a, '0'
    ld l, a             ; fastcall arg
    jp _main_putc       ; tail call

; uint8_t has_other_mention(void)
; Scan ChannelInfo[10] flags, skipping current_channel_idx.
EXTERN _channels
_has_other_mention:
    ld a, (_current_channel_idx)
    ld c, a                     ; C counts down to the slot to skip
    ld hl, _channels + 30       ; flags field, ChannelInfo stride is 32
    ld de, 32
    ld b, 10                    ; MAX_CHANNELS
homm_loop:
    ld a, c
    or a
    jr z, homm_next
    ld a, (hl)
    and 0x09                    ; CH_FLAG_ACTIVE | CH_FLAG_MENTION
    cp 0x09
    jr z, homm_yes
homm_next:
    dec c
    add hl, de
    djnz homm_loop
    ld l, 0
    ret
homm_yes:
    ld l, 1
    ret

; void count_sync_tick(void)
; Silent LIST user-count resync gate:
; - only after human idle
; - only while still multichannel
; - size bucket: >=2048 users -> 4 quits, >=1024 -> 8,
;   >=256 -> 16, smaller -> 32.
; - each extra open channel above two adds one quit to the threshold.
PUBLIC _count_sync_tick
EXTERN _connection_state
EXTERN _line_len
EXTERN _pagination_active
EXTERN _names_pending
EXTERN _buffer_pressure
EXTERN _count_sync_enabled
EXTERN _count_sync_idle_frames
EXTERN _count_sync_quits
EXTERN _irc_send_cmd1
_count_sync_tick:
    ld a, (_count_sync_enabled)
    or a
    ret z
    ld a, (_connection_state)
    cp 3                        ; STATE_IRC_READY
    ret nz
    ld a, (_current_channel_idx)
    or a
    ret z
    ld a, (_line_len)
    or a
    jp nz, cst_reset_idle
    ld a, (_pagination_active)
    ld hl, _names_pending
    or (hl)
    ld hl, _buffer_pressure
    or (hl)
    jp nz, cst_reset_idle

    ld hl, _count_sync_idle_frames
    inc (hl)

    ld hl, (_cur_chan_ptr)
    ld de, 30                   ; flags offset
    add hl, de
    ld a, (hl)
    and 0x22                    ; CH_FLAG_QUERY | CH_FLAG_COUNT_DIRTY
    cp 0x20                     ; dirty channel, not query
    ret nz
    ld a, (_count_sync_idle_frames)
    cp 150
    ret c
    xor a
    ld (_count_sync_idle_frames), a

    ld hl, _channels + 32 + 30  ; flags for channels[1]
    ld de, 32
    ld b, 9
    ld c, 0
cst_find_other:
    ld a, (hl)
    and 0x03                    ; CH_FLAG_ACTIVE | CH_FLAG_QUERY
    cp 0x01
    jr nz, cst_next_slot
    inc c
cst_next_slot:
    add hl, de
    djnz cst_find_other

    ld a, c
    cp 2
    jr nc, cst_have_other
    ld hl, (_cur_chan_ptr)
    ld de, 30
    add hl, de
    res 5, (hl)                 ; clear CH_FLAG_COUNT_DIRTY
    xor a
    ld (_count_sync_quits), a
    ret

cst_have_other:
    ld b, c                     ; active channel count
    ld a, (_count_sync_quits)
    or a
    ret z

    ld hl, (_cur_chan_ptr)
    ld de, 28                   ; user_count offset
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)                  ; DE = current user_count
    ld a, d
    or e
    ret z

    ld c, 32                    ; threshold default: <256 users
    ld a, d
    or a
    jr z, cst_have_threshold
    ld c, 16
    cp 4                        ; <1024 users
    jr c, cst_have_threshold
    ld c, 8
    cp 8                        ; <2048 users
    jr c, cst_have_threshold
    ld c, 4                     ; >=2048 users
cst_have_threshold:
    ld a, b
    sub 2
    add a, c
    ld c, a
    ld a, (_count_sync_quits)
    cp c
    ret c

    xor a
    ld (_count_sync_quits), a
    inc hl                      ; HL was at user_count MSB, now flags
    res 5, (hl)                 ; clear CH_FLAG_COUNT_DIRTY
    ld hl, (_cur_chan_ptr)      ; channel name is at offset 0
    push hl
    ld hl, cst_list_cmd
    push hl
    call _irc_send_cmd1
    ret
cst_reset_idle:
    xor a
    ld (_count_sync_idle_frames), a
    ret

cst_list_cmd:
    DEFM "LIST", 0

; =============================================================================
; FRAME WAIT ? Wait for next frame (50Hz sync via IM1 ROM ISR)
; ROM ISR at $0038 increments FRAMES (23672) and scans keyboard.
; =============================================================================
PUBLIC _frame_wait
PUBLIC _frame_wait_drain
IFDEF SPECTALK_NEXT
EXTERN _next_overlay_active
EXTERN _next_overlay_suspend
EXTERN _next_overlay_restore
ENDIF
IFDEF SPECTALK_SPECTRANEXT
EXTERN _spxn_rom_held
EXTERN _spxn_overlay_page
DEFC SPXN_PAGEIN     = $3FF9
DEFC SPXN_PAGEOUT    = $007C
DEFC SPXN_SET_PAGE_B = $3E36
ENDIF
IFNDEF SPECTALK_SPECTRANEXT
IFNDEF SPECTALK_NEXT
EXTERN uartRead
EXTERN _rb_push
ENDIF
ENDIF
_frame_wait:
IFDEF SPECTALK_NEXT
    ld a, (_next_overlay_active)
    or a
    jr z, frame_wait_plain
    di
    call _next_overlay_suspend
    push iy
    ld iy, 0x5C3A
    ei
    halt
    di
    pop iy
    call _next_overlay_restore
    ret
ENDIF
IFDEF SPECTALK_SPECTRANEXT
    ld a, (_spxn_rom_held)
    or a
    jr z, frame_wait_plain
    di
    xor a
    ld (_spxn_rom_held), a
    call SPXN_PAGEOUT
    push iy
    ld iy, $5C3A
    ei
    halt
    di
    pop iy
    call SPXN_PAGEIN
    ld a, (_spxn_overlay_page)
    call SPXN_SET_PAGE_B
    ld a, 1
    ld (_spxn_rom_held), a
    ret
ENDIF
frame_wait_plain:
    push iy
    ld iy, 0x5C3A      ; ROM ISR expects IY = system variables
    ei
    halt                ; wait for next frame interrupt (exact 50Hz)
    di
    pop iy              ; restore IY for SDCC
    ret

; Resident UART targets poll throughout the frame: 32 bytes after HALT cannot
; keep up with 115200 baud during IRC registration bursts. Use the scalar
; reader under IM1; the fast drain owns shadow registers and requires DI.
_frame_wait_drain:
IFDEF SPECTALK_SPECTRANEXT
    call _frame_wait
    jp _net_pump_rx
ELSE
IFDEF SPECTALK_NEXT
    ; Keep mapped overlays on their existing ROM suspend/restore path.
    ld a, (_next_overlay_active)
    or a
    jr z, fwd_poll
    call _frame_wait
    jp _net_pump_rx
ENDIF
fwd_poll:
    push iy
    ld iy, 0x5C3A
    ld a, (0x5C78)      ; FRAMES low byte
    push af             ; keep frame snapshot across UART drain clobbers
    ei
fwd_loop:
    ld hl, (_rb_head)
    inc hl
    res 3, h            ; future head
    ld de, (_rb_tail)
    or a
    sbc hl, de
    jr z, fwd_check_frame ; ring full: leave the byte in the UART
    call uartRead
    jr nc, fwd_check_frame
    ld l, a
    call _rb_push
fwd_check_frame:
    pop bc              ; B = saved FRAMES byte
    push bc
    ld a, (0x5C78)
    cp b
    jr z, fwd_loop
    pop bc
    di
    pop iy
    ret
ENDIF

; =============================================================================
; SYSTEM RAM HIJACKING - Variables mapped to unused ZX system areas
; IM1 mode: ROM ISR runs via divMMC automapper at $0038.
; Normal IM1 does not consume these owners. esxDOS preservation is not assumed:
; runtime transactions invalidate the input cache at their final boundary and
; Printer-tail scratch lifetimes never cross RST 8. CHANS still needs HW guards.
; Zeroed during CRT init (code_crt_init section above)
; =============================================================================

; PRINTER BUFFER (0x5B00 - 0x5BFF: 256 bytes, unused ? no ZX Printer)
PUBLIC _input_cache_char

defc _input_cache_char = 0x5B00  ; 128 bytes (INPUT_LINES * SCREEN_COLS)
; Classic: 0x5B80-0x5BBF free. Spectranext: XFS state + persistent target data,
; with the exact owners locked by tools/check_memory_layout.py.
; 0x5BC0-0x5BFF: scratch transitorio mapeado en 00_preamble.asm. No persistente
; a llamadas esxDOS; render paths no cruzan esxDOS → estable mid-render.
; irc_pass, nickserv_pass, network_name en BSS (deben sobrevivir esxDOS).

; CHANS WORKSPACE (0x5CB6 - 0x5DB5: 256 bytes, unused ? no ROM I/O channels)
PUBLIC _line_buffer
PUBLIC _temp_input

defc _line_buffer      = 0x5CB6  ; 128 bytes (LINE_BUFFER_SIZE)
defc _temp_input       = 0x5D36  ; 128 bytes (LINE_BUFFER_SIZE)

; UDG AREA (0xFF58 - 0xFFF1: 154 bytes, unused ? program uses custom 64-col font)
PUBLIC _friend_nicks
PUBLIC _away_message
PUBLIC _names_target_channel

defc _friend_nicks          = 0xFF58  ;  90 bytes (MAX_FRIENDS * IRC_NICK_SIZE)
defc _away_message          = 0xFFB2  ;  32 bytes
defc _names_target_channel  = 0xFFD2  ;  32 bytes (NAMES_TARGET_CHANNEL_SIZE)

