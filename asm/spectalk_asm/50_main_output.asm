; =============================================================================

EXTERN _ignore_count
EXTERN _ignore_list

EXTERN _show_timestamps
EXTERN _wrap_indent
EXTERN _current_attr
EXTERN _deferred_wrap_active
EXTERN _deferred_wrap_attr
EXTERN _deferred_wrap_p
EXTERN _main_clear_indent6
EXTERN _time_hour
EXTERN _time_minute
; _ATTR_MSG_TIME = _theme_attrs + 12
EXTERN _last_ts_hour
EXTERN _last_ts_minute

; 2B transient scratch in the free printer-buffer tail ($5BE5-$5BFF).
; Only live inside main_print_wrapped_ram()'s scan, before render/BPE calls.
defc mpwr_last_space = 0x5BE5

; -----------------------------------------------------------------------------
; void main_print(const char *s) __z88dk_fastcall
; HL = string. Mirrors the former C wrapper.
; -----------------------------------------------------------------------------
_main_print:
    ld a, (_overlay_mode)
    or a
    ret nz

    ld a, (_main_col)
    ld c, a
    ld a, (_wrap_indent)
    or c
    jr nz, mp_slow

    push hl                     ; save original string
    ld d, h
    ld e, l
    ld b, 64
mp_scan:
    ld a, (de)
    or a
    jr z, mp_fast
    cp 10
    jr z, mp_bpe_slow           ; embedded LF needs main_puts newline handling
    add a, a
    jr c, mp_bpe_slow
    inc de
    djnz mp_scan
    ld a, (de)                  ; exactly 64 chars also uses fast path
    or a
    jr z, mp_fast

mp_bpe_slow:
    pop hl

mp_slow:
    call _main_puts
mp_wrap_reset:
    ld a, 0                     ; preserve puts/cut-end Z while clearing indent
    ld (_wrap_indent), a
    ret nz                      ; cancelled; Z also covers a normal full row
    jp _main_newline

mp_fast:
    pop de                      ; DE = original string
    ld a, (_current_attr)
    ld b, a
    ld c, d                     ; C = str_hi
    push bc                     ; [str_hi][attr]
    ld a, (_main_line)
    ld c, a                     ; C = y
    ld b, e                     ; B = str_lo
    push bc                     ; [y][str_lo]
    call _print_line64_fast
    pop bc
    pop bc
    jp _main_newline

; -----------------------------------------------------------------------------
; void main_print_time_prefix(void)
; Prints "HH:MM| " using ATTR_MSG_TIME, then restores current_attr.
; show_timestamps: 0=off, 1=always, 2=on-change (only when HH:MM differs)
; Sets wrap_indent=6 when printed, 0 when skipped.
; -----------------------------------------------------------------------------
PUBLIC _main_print_time_prefix
_main_print_time_prefix:
    ld a, (_overlay_mode)
    or a
    ret nz

    ld a, (_show_timestamps)
    or a
    jr nz, mptp_check
    ld (_wrap_indent), a    ; mode 0: off, A is already 0
    ret

mptp_check:
    cp 2
    jr nz, mptp_do          ; mode 1: always print

    ; mode 2: on-change ? check if HH:MM matches last printed
    ld a, (_time_hour)
    ld hl, _last_ts_hour
    cp (hl)
    jr nz, mptp_changed     ; hour differs
    ld a, (_time_minute)
    ld hl, _last_ts_minute
    cp (hl)
    jr nz, mptp_changed     ; minute differs

    ; Same time ? clear the fixed 6-char indent directly instead of
    ; paying six full _main_putc(' ') calls.
    ld a, 6
    ld (_wrap_indent), a
    jp _main_clear_indent6

mptp_changed:
    ; Update last printed time
    ld a, (_time_hour)
    ld (_last_ts_hour), a
    ld a, (_time_minute)
    ld (_last_ts_minute), a

mptp_do:
    ; saved_attr = current_attr
    ld a, (_current_attr)
    push af

    ; current_attr = ATTR_MSG_TIME
    ld a, (_theme_attrs + 12) ; ATTR_MSG_TIME
    ld (_current_attr), a

    ; print HH
    ld a, (_time_hour)
    call mptp_put2

    ; ':'
    ld l, ':'
    call _main_putc

    ; print MM
    ld a, (_time_minute)
    call mptp_put2

    ; " " (solo espacio, sin barra vertical)
    ld l, ' '
    call _main_putc

    ; restore current_attr AND g_ps64_attr (prevent color leak to next char)
    pop af
    ld (_current_attr), a
    ld (_g_ps64_attr), a

    ; wrap_indent = 6
    ld a, 6
    ld (_wrap_indent), a
    ret

; --- local: print 2-digit decimal from A (00..99), leading zero ---
; clobbers AF, BC
mptp_put2:
    ld b, '0'
mptp_div10:
    sub 10
    jr c, mptp_div_done
    inc b
    jr mptp_div10
mptp_div_done:
    add a, 10 + '0'
    ld c, a            ; ones as ASCII

    ; tens
    ld l, b
    push bc
    call _main_putc
    pop bc

    ; ones
    ld l, c
    jr _main_putc           ; tail call (in range)

; -----------------------------------------------------------------------------
; void main_putc(char c) __z88dk_fastcall
; Imprime un caracter gestionando saltos de l?nea y coordenadas.
; L = c
; -----------------------------------------------------------------------------
PUBLIC _main_putc
PUBLIC _main_putc_space
_main_putc_space:
    ld l, 0x20
    jp _main_putc

_main_putc:
    ; Suppress output during help overlay
    ld a, (_overlay_mode)
    or a
    ret nz
    ld a, l
    cp 10               ; ?Es '\n'?
    jp z, _main_newline
    
    ld b, a             ; Guardar caracter en B
    
    ; Chequear l?mite de columna (SCREEN_COLS = 64)
    ld a, (_main_col)
    cp 64
    jr c, mputc_no_wrap
    
    ; Necesitamos wrap - guardar B antes de llamar a main_newline
    push bc
    call _main_newline
    pop bc
    ld a, (_main_col)
    cp 64
    ret z
    
mputc_no_wrap:
    ; Configurar variables globales para el driver de video (bypasea print_char64 de C)
    ld (_g_ps64_col), a
    ld c, a

    ld a, (_main_line)
    ld (_g_ps64_y), a
    
    ; Inline space fast path when row cache is already warm.
    ld a, b
    cp 32
    jr nz, mputc_char
    ld a, (_g_ps64_y)
    ld hl, cache_row_y
    cp (hl)
    jr nz, mputc_char

    ld a, (_current_attr)
    ld b, c
    ld c, a
    call main_space_inline
    jr mputc_inc_col

mputc_char:
    ; Llamar al driver (L = caracter)
    ld a, (_current_attr)
    ld (_g_ps64_attr), a
    ld l, b
    call _print_str64_char
    
mputc_inc_col:
    ; Incrementar columna: main_col++
    ld hl, _main_col
    inc (hl)
    ret

; Shared cached-space renderer.
; Input: B = col, C = attr, cache row must already match _g_ps64_y.
; Destroys: AF, DE, HL. Preserves: BC.
main_space_inline:
    ld hl, (cache_scr_base)
    ld a, b
    srl a
    add a, l
    ld l, a

    ld e, 0x0F
    bit 0, b
    jr z, msi_mask_set
    ld e, 0xF0
msi_mask_set:
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a
    inc h
    ld a, (hl)
    and e
    ld (hl), a

    ld hl, (cache_atr_base)
    ld a, b
    srl a
    add a, l
    ld l, a
    ld (hl), c
    ret


; -----------------------------------------------------------------------------
; void main_print_wrapped_ram(char *s) __z88dk_fastcall
; Wrap por palabras dentro del ancho disponible (64 - main_col).
; HL = string (RAM)  [MODIFICA temporalmente RAM insertando 0]
; Input is one decoded IRC/input line, without embedded LF or BPE tokens.
; -----------------------------------------------------------------------------
PUBLIC _main_print_wrapped_clean
_main_print_wrapped_clean:
    ld a, (_overlay_mode)
    or a
    ret nz
    jr mpwr_loop

PUBLIC _main_print_wrapped_ram
_main_print_wrapped_ram:
    ld a, (_overlay_mode)
    or a
    ret nz

    ; Convertir UTF-8 a ASCII in-place antes de procesar
    call _utf8_to_ascii     ; HL se preserva (fastcall, mismo puntero)

mpwr_loop:
    ld a, (hl)
    or a
    jp z, mp_wrap_reset

    ; Si estamos al final de l?nea, pasar a la siguiente SIN perder HL
    ld a, (_main_col)
    cp 64
    jr c, mpwr_have_col
    push hl
    call _main_newline
    pop hl

    ; Si la paginaci?n fue cancelada durante el pause, main_col queda en 64.
    ; Salir para no pisar "Cancelled".
    ld a, (_main_col)
    cp 64
    ret z

mpwr_have_col:
    ; avail = 64 - main_col  -> B
    cpl
    add a, 65
    ld b, a

    ; DE = start
    ld d, h
    ld e, l

    ld (mpwr_last_space), hl     ; start sentinel: none/first-space => hard cut

mpwr_scan:
    ld a, (hl)
    or a
    jr z, mpwr_cut_end

    cp 32                        ; ' '
    jr nz, mpwr_scan_next
    ld (mpwr_last_space), hl

mpwr_scan_next:
    inc hl
    djnz mpwr_scan

    ; A complete exact-width string needs no word-boundary cut.
    ld a, (hl)
    or a
    jr z, mpwr_cut_end

    ; Alcanzados "avail" chars
    ld b, h
    ld c, l                      ; hard cutpoint / next_start
    ld hl, (mpwr_last_space)     ; last usable space, or start sentinel

    ; Si no hubo espacio usable (o el único espacio es el primero), hard cut
    or a
    sbc hl, de
    jr z, mpwr_cut_hard_from_bc
    add hl, de

mpwr_use_space:
    ; cutpoint = HL (espacio), next_start = HL+1
    ld b, h
    ld c, l
    inc bc
    jr mpwr_cut_common

mpwr_cut_hard_from_bc:
    ld h, b
    ld l, c
mpwr_cut_end:
mpwr_cut_hard:
    ; cutpoint = HL (NUL o start+avail), next_start = HL
    ld b, h
    ld c, l
    ; fall through

mpwr_cut_common:
    ; Guardar char original y cortar temporalmente
    ld a, (hl)
    push af
    xor a
    ld (hl), a

    push hl                      ; cutpoint
    push bc                      ; next_start

    ; Imprimir segmento (start = DE)
    ; Fast path: si estamos al inicio de l?nea, usar print_line64_fast
    ld a, (_main_col)
    or a
    jr nz, mpwr_print_puts

    ; Set start byte offset from wrap_indent (0 if no indent)
    ld a, (_wrap_indent)
    rrca                         ; indent_bytes = wrap_indent / 2 (wrap_indent 0/6)
    ld (_plf_start_byte), a

    ; Args para _print_line64_fast: [y][start_lo][start_hi][attr]
    ld a, (_current_attr)
    ld b, a
    ld c, d                      ; C = start_hi
    push bc                      ; [start_hi][attr]

    ld a, (_main_line)
    ld c, a                      ; C = y
    ld b, e                      ; B = start_lo
    push bc                      ; [y][start_lo]

    call _print_line64_fast

    ; Limpiar 4 bytes de args
    pop bc
    pop bc
    jr mpwr_print_done

mpwr_print_puts:
    ex de, hl
    call _main_puts

mpwr_print_done:
    ; Restaurar next_start, cutpoint y char
    pop hl                       ; HL = next_start
    pop de                       ; DE = cutpoint
    pop af
    ld (de), a

    ; Si termin? cadena, salir al finalize
    ld a, (hl)
    or a
    jp z, mp_wrap_reset

    ; Nueva l?nea para continuar SIN perder HL
    push hl
    call _main_newline
    pop hl

    ; Si la paginaci?n fue cancelada durante el pause, salir
    ld a, (_main_col)
    cp 64
    ret z

    jp mpwr_loop                 ; <-- era jr mpwr_loop

; -----------------------------------------------------------------------------
; uint8_t names_render_grid(char *p) __z88dk_fastcall
; Render manual /names as 4 fixed 16-column cells per row using temp_input.
; Keeps prefixes (@/+) and truncates long nicks with '>'.
; Returns L=1 if pagination BREAK cancelled, else L=0.
; -----------------------------------------------------------------------------
PUBLIC _names_render_grid
_names_render_grid:
    ; cmd_names()/pagination_pause() always leave the manual list at column 0.
    ld de, _temp_input
    ld c, 0                         ; cells used in current row

nrg_skip_spaces:
    ld a, (hl)
    or a
    jr z, nrg_end
    cp 33
    jr nc, nrg_token
    inc hl
    jr nrg_skip_spaces

nrg_token:
    ld b, 15                        ; max visible chars per 16-col cell
nrg_copy:
    ld a, (hl)
    cp 33
    jr c, nrg_fill_tail
    ld (de), a
    inc de
    inc hl
    djnz nrg_copy

    ; Token continues past 15 chars: mark truncation and consume the rest.
    ld a, (hl)
    cp 33
    jr c, nrg_fill_tail
    dec de
    ld a, '>'
    ld (de), a
    inc de
nrg_consume_long:
    inc hl
    ld a, (hl)
    cp 33
    jr nc, nrg_consume_long

nrg_fill_tail:
    inc b                           ; remaining chars plus cell separator
    ld a, ' '
nrg_fill_loop:
    ld (de), a
    inc de
    djnz nrg_fill_loop

    inc c
    bit 2, c
    jr z, nrg_skip_spaces

    call nrg_flush
    jr z, nrg_cancel
    ld de, _temp_input
    ld c, 0
    jr nrg_skip_spaces

nrg_end:
    ld a, c
    or a
    jr z, nrg_ok
    ld b, 15                        ; pad one empty cell via nrg_fill_tail

    jr nrg_fill_tail
nrg_ok:
    ld l, c                          ; C is zero on all successful exits
    ret
nrg_cancel:
    ld l, 1
    ret

nrg_flush:
    push hl

    ld a, (_theme_attrs + 11)        ; ATTR_MSG_NICK
    ld b, a
    ld c, 0x5D                       ; high(_temp_input)
    push bc                         ; [str_hi][attr]
    ld a, (_main_line)
    ld c, a
    ld b, 0x36                       ; low(_temp_input)
    push bc                         ; [y][str_lo]
    call _print_line64_fast
    pop bc
    pop bc

    call _main_newline
    ld a, (_main_col)
    cp 64                           ; Z means pagination BREAK cancelled

    pop hl
    ret

; -----------------------------------------------------------------------------
; uint8_t names_count_line(char *p) __z88dk_fastcall
; Match the old C NAMES count: empty => 0, otherwise 1 + number of spaces.
; -----------------------------------------------------------------------------
PUBLIC _names_count_line
_names_count_line:
    ld b, 0
    ld a, (hl)
    or a
    jr z, ncl_done
    inc b
ncl_loop:
    cp ' '
    jr nz, ncl_next
    inc b
ncl_next:
    inc hl
    ld a, (hl)
    or a
    jr nz, ncl_loop
ncl_done:
    ld l, b
    ret

; -----------------------------------------------------------------------------
; void deferred_wrap_step(void)
; ASM version of the C line-step wrapper. Same contract:
; - render one wrapped segment from deferred_wrap_p
; - preserve visible text and word-cut behavior
; - even main_col uses print_line64_fast, odd main_col falls back to main_puts
; - always finishes the step with main_newline()
; -----------------------------------------------------------------------------
PUBLIC _deferred_wrap_step
_deferred_wrap_step:
    ld a, (_deferred_wrap_active)
    or a
    ret z
    ld a, (_overlay_mode)
    or a
    ret nz
    ld a, (_main_col)
    cp 64
    jp z, dws_cancel

    ld a, (_deferred_wrap_attr)
    ld (_current_attr), a

    ld hl, (_deferred_wrap_p)
    ld d, h
    ld e, l                      ; DE = start
    ld (mpwr_last_space), hl     ; start sentinel

    ld a, (_main_col)
    cpl
    add a, 65                    ; B = SCREEN_COLS - main_col
    ld b, a

dws_scan:
    ld a, b
    or a
    jr z, dws_scan_done
    ld a, (hl)
    or a
    jr z, dws_scan_done
    cp ' '
    jr nz, dws_scan_next
    ld (mpwr_last_space), hl
dws_scan_next:
    inc hl
    djnz dws_scan

dws_scan_done:
    ld a, (hl)
    or a
    jr z, dws_cut_end

    ld bc, (mpwr_last_space)
    ld a, b
    cp d
    jr nz, dws_use_space
    ld a, c
    cp e
    jr nz, dws_use_space

    ; No usable space: cut at current HL, next is the same pointer.
    ld b, h
    ld c, l
    jr dws_cut_common

dws_use_space:
    ; Cut at last usable space, continue at last_space + 1.
    ld h, b
    ld l, c
    inc bc
    jr dws_cut_common

dws_cut_end:
    ; End of string: cut at NUL and clear pending pointer after render.
    ld bc, 0

dws_cut_common:
    ld a, (hl)
    push af                      ; saved cut byte
    xor a
    ld (hl), a
    push hl                      ; cutpoint
    push bc                      ; next_start

    ld a, (_main_col)
    bit 0, a
    jr nz, dws_print_puts

    rrca
    ld (_plf_start_byte), a

    ; segment length = cut - start (low byte is enough, max 64)
    ld a, l
    sub e
    push af

    ; call print_line64_fast(main_line, start, current_attr)
    ld a, (_current_attr)
    ld b, a
    ld c, d                      ; C = start_hi
    push bc                      ; [start_hi][attr]
    ld a, (_main_line)
    ld c, a                      ; C = y
    ld b, e                      ; B = start_lo
    push bc                      ; [y][start_lo]
    call _print_line64_fast
    pop bc
    pop bc

    pop af                       ; A = segment length
    ld hl, _main_col
    add a, (hl)
    ld (hl), a
    jr dws_render_done

dws_print_puts:
    ld h, d
    ld l, e
    call _main_puts

dws_render_done:
    pop hl                       ; HL = next_start
    pop de                       ; DE = cutpoint
    pop af
    ld (de), a

    ld (_deferred_wrap_p), hl
    ld a, h
    or l
    jr nz, dws_newline
    xor a
    ld (_deferred_wrap_active), a
    ld (_wrap_indent), a

dws_newline:
    jp _main_newline

dws_cancel:
    xor a
    ld (_deferred_wrap_active), a
    ld (_wrap_indent), a
    ret
    
; -----------------------------------------------------------------------------
; void main_puts(const char *s) __z88dk_fastcall
; Imprime una cadena usando la versi?n optimizada de putc.
; HL = string
; ASM result: Z=complete (including column 64), NZ=cancelled/suppressed.
; -----------------------------------------------------------------------------

EXTERN _overlay_mode
PUBLIC _main_puts
_main_puts:
    ; Suppress output during help overlay
    ld a, (_overlay_mode)
    or a
    ret nz

    ; Fast path for plain ASCII chunks starting on an even column.
    ; Odd-column starts keep the old path; special tails resume slow after
    ; any safe even prefix has been rendered.
    ld a, (_main_col)
    bit 0, a
    jr nz, puts_slow_entry
    cp 64
    jr nc, puts_slow_entry

    ld c, a              ; C = start column
    ld d, h
    ld e, l              ; DE = original string
    ld b, 0              ; B = visible byte count
puts_fast_scan:
    ld a, (hl)
    or a
    jr z, puts_fast_ready
    cp 32
    jr c, puts_fast_segment
    cp 128
    jr nc, puts_fast_segment
    inc b
    ld a, b
    add a, c
    cp 65
    jr nc, puts_fast_wrap_segment
    inc hl
    jr puts_fast_scan

puts_fast_ready:
puts_fast_segment:
    ld a, b
    cp 4
    jr c, puts_fast_fallback
    bit 0, b
    jr z, puts_fast_segment_even
    dec b
    dec hl
    ld a, b
    cp 4
    jr c, puts_fast_fallback

puts_fast_segment_even:
    push hl              ; tail pointer for slow path, or NUL for done

    ld a, c
    rrca                 ; even column -> byte offset
    ld (_plf_start_byte), a
    ld a, b
    srl a
    ld (_plf_pair_count), a

    ld a, c
    add a, b
    push af              ; final main_col

    ld a, (_current_attr)
    ld b, a
    ld c, d
    push bc              ; [str_hi][attr]
    ld a, (_main_line)
    ld c, a
    ld b, e
    push bc              ; [y][str_lo]
    call _print_line64_fast
    pop bc
    pop bc
    pop af
    ld (_main_col), a
    pop hl
    ld a, (hl)
    or a
    ret z
    jp puts_slow_entry

puts_fast_wrap_segment:
    dec b                ; current char would wrap; leave it for slow path
    jr puts_fast_segment

puts_fast_fallback:
    ld h, d
    ld l, e

puts_slow_entry:
    ; HL = string pointer
    ; Initialize BPE return stack (empty)
    ; Optimizaci?n: cargar globals una vez y mantener en registros
    ; B = main_col, C = current_attr, D/E = string pointer
    ld d, h
    ld e, l             ; DE = puntero string
    ld hl, bpe_rstack
    ld (bpe_rsp), hl

    ld a, (_main_line)
    ld (_g_ps64_y), a
    ld a, (_current_attr)
    ld c, a             ; C = attr
    ld (_g_ps64_attr), a
    ld a, (_main_col)
    ld b, a             ; B = col

puts_opt_loop:
    ld a, (de)
    or a
    jp z, puts_bpe_pop  ; 0x00: end of string or end of BPE dict entry

    cp 0x80
    jp nc, puts_bpe_expand ; >= 0x80: BPE token, expand from dictionary

    cp 10
    jr z, puts_opt_nl   ; '\n' -> newline

    ; Chequear wrap
    ld h, a             ; H = caracter (temporal)
    bit 6, b
    jr nz, puts_opt_wrap
    
puts_opt_emit:
    ; --- Inline space fast path (skip unpack_glyph + full render) ---
    ; ~50 T-states for space vs ~650 for full print_str64_char path
    ld a, h
    cp 32
    jr nz, puts_opt_char

    ; Verify row cache is valid (cold on first char after newline/scroll)
    ; If miss, fall through to full path which warms the cache
    ld a, (_g_ps64_y)
    ld hl, cache_row_y
    cp (hl)
    jr z, puts_opt_space_cached
    ld h, 32             ; LD HL above clobbered the pending space in H
    jr puts_opt_char

    ; Cache hit ? render space inline
    ; B = col, C = attr, DE = string ptr
puts_opt_space_cached:
    push de              ; save string pointer
    call main_space_inline
    pop de               ; restore string pointer
    jr puts_opt_next

puts_opt_char:
    ; Emitir caracter normal sin re-cargar globals
    ld a, b
    ld (_g_ps64_col), a
    ld l, h             ; L = caracter para print_str64_char
    push bc
    push de
    call _print_str64_char
    pop de
    pop bc

puts_opt_next:
    inc b                ; main_col++
    inc de               ; next char
    jr puts_opt_loop

puts_opt_wrap:
    ; Necesitamos wrap - sincronizar y llamar main_newline
    ld a, b
    ld (_main_col), a
    push de
    push hl             ; H tiene el caracter actual
    call _main_newline
    pop hl
    pop de
    call puts_reload_nl
    ret nz
    jr puts_opt_emit

puts_opt_nl:
    ; '\n' - sincronizar col y llamar newline
    ld a, b
    ld (_main_col), a
    push de
    call _main_newline
    pop de
    call puts_reload_nl
    ret nz
    inc de
    jr puts_opt_loop

puts_reload_nl:
    ; Shared reload after newline (main_newline clobbers BC)
    ld a, (_main_line)
    ld (_g_ps64_y), a
    ld a, (_current_attr)
    ld c, a
    ld (_g_ps64_attr), a
    ld a, (_main_col)
    ld b, a
    bit 6, b
    ret

; --- BPE expansion for puts_opt ---
; Token >= 0x80 found in A: push continuation (DE+1) to BPE stack,
; set DE to dict entry (3 bytes: b1, b2, 0x00). Loop continues reading
; from dict. On null, pops continuation and resumes original string.
puts_bpe_expand:
    ; A = token, DE = current string position. Dictionary has 74 entries:
    ; tokens 0x80..0xC9; higher bytes are invalid display input and are skipped.
    ; B = main_col, C = current_attr ? MUST be preserved!
    inc de                  ; advance past the token
    cp 0xCA
    jp nc, puts_opt_loop
    push bc                 ; save B=col, C=attr
    ; W8 fix: check rstack overflow before push (8 levels = 16 bytes)
    ld c, a                 ; save token while comparing fixed-page rsp low byte
    ld hl, (bpe_rsp)
    ld a, l
    cp 0xE3                 ; low byte of bpe_rstack + 16
    jr nc, puts_bpe_overflow
    ld a, c                 ; restore token
    ; Push continuation address (DE) onto BPE return stack
    ld (hl), e
    inc hl
    ld (hl), d
    inc hl
    ld (bpe_rsp), hl
    ; Calculate dict entry address: bpe_dict + (token - 0x80) * 3
    sub 0x80
    ld l, a
    ld h, 0
    ld c, l
    ld b, h                 ; BC = (token - 0x80) ? temp, will restore
    add hl, hl              ; HL = * 2
    add hl, bc              ; HL = * 3
    ld bc, bpe_dict
    add hl, bc
    ex de, hl               ; DE = &bpe_dict[(token-0x80)*3]
    pop bc                  ; restore B=col, C=attr
    jp puts_opt_loop         ; continue reading from dict entry

puts_bpe_overflow:
    ; W8: rstack full ? treat token as literal '?', skip it
    pop bc                  ; restore B=col, C=attr
    jp puts_opt_loop         ; continue with DE (already advanced past token)

puts_bpe_pop:
    ; Null byte hit: end of string or end of BPE dict entry
    ; Check if BPE stack has entries
    ld hl, (bpe_rsp)
    ld a, l
    cp 0xD3                 ; low byte of bpe_rstack
    jr z, puts_opt_done     ; stack empty -> real end of string
    ; Pop continuation address from BPE stack
    dec hl
    ld d, (hl)
    dec hl
    ld e, (hl)
    ld (bpe_rsp), hl
    jp puts_opt_loop         ; resume original string

puts_opt_done:
    ; Sincronizar main_col de vuelta
    ld a, b
    ld (_main_col), a
    ret


; -----------------------------------------------------------------------------
; uint8_t is_ignored(const char *nick) __z88dk_fastcall
; Verifica si un nick est? en la lista de ignorados (Array de 16 bytes stride).
; HL = nick
; Retorna L=1 (true) o L=0 (false)
; -----------------------------------------------------------------------------
PUBLIC _is_ignored
_is_ignored:
    ld a, (_ignore_count)
    or a
    jr z, ign_fail      ; Si count == 0, retornar 0
    
    ld b, a             ; B = contador de bucle
    ld de, _ignore_list ; DE = puntero al inicio de la lista
    ld a, (hl)
    or 0x20
    ld c, a             ; C = first char folded like RFC1459 ASCII subset
    
ign_loop:
    ld a, (de)
    or 0x20
    cp c
    jr nz, ign_skip

    ; Guardar contexto
    push bc
    push de
    push hl
    
    ; Preparar llamada a st_stricmp(list_item, nick)
    ; Convenci?n C (stack): push right-to-left
    push hl             ; Arg2: nick
    push de             ; Arg1: list_item
    call _st_stricmp
    
    ; Resultado en HL. Si es 0, hay coincidencia.
    ld a, h
    or l
    ; Restaurar contexto
    pop hl              ; nick
    pop de              ; list_ptr actual
    pop bc              ; contador
    jr nz, ign_skip
    ld l, 1
    ret
    
ign_skip:
    ; Avanzar DE + 16 (tama?o fijo de cada entrada en ignore_list)
    ld a, e
    add a, 16
    ld e, a
    jr nc, ign_next
    inc d
    
ign_next:
    djnz ign_loop       ; Siguiente iteraci?n
    
ign_fail:
    ld l, 0
    ret


