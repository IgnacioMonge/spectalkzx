;;
;; spectalk_asm.asm - Optimized assembly routines for SpecTalk ZX
;; SpecTalk ZX - IRC Client for ZX Spectrum
;; Copyright (C) 2026 M. Ignacio Monge Garcia
;;
;; This program is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License version 2 as
;; published by the Free Software Foundation.
;;
;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
;; GNU General Public License for more details.
;;
;; You should have received a copy of the GNU General Public License
;; along with this program. If not, see <https://www.gnu.org/licenses/>.

; =============================================================================
; BSS ZEROING - runs before main() via code_crt_init
; Allows the TAP binary to be truncated before BSS (saving ~4KB of zeros)
; Classic and native Next clear compiler and ASM state, including UART latches.
; Spectranext also clears driver state through its ROM-held byte.
; =============================================================================
; Paged startup moves the last resident caller of this shared overlay ABI helper.
IFDEF SPECTALK_NEXT
SECTION rodata_user
EXTERN ____sdcc_4_push_hlix
    defw ____sdcc_4_push_hlix
ELSE
IFDEF SPECTALK_SPECTRANEXT
SECTION rodata_user
EXTERN ____sdcc_4_push_hlix
    defw ____sdcc_4_push_hlix
ENDIF
ENDIF

SECTION code_crt_init
EXTERN __data_compiler_tail
EXTERN __bss_user_tail
EXTERN ___sdcc_enter_ix
EXTERN _cur_chan_ptr
EXTERN _current_channel_idx
IFDEF SPECTALK_SPECTRANEXT
EXTERN _spxn_rom_held
ENDIF
    ; Mainline DI contract: ROM IM1 needs IY=0x5C3A, while sdcc_iy uses IY.
    ; Only guarded waits, ABOUT ticks, and the internal scroll install ROM IY
    ; before enabling interrupts; every path restores the mainline DI state.
    di
IFDEF SPECTALK_NEXT
    ; NEX loaders enter in IM0; frame_wait() requires the ROM IM1 handler.
    im 1
ENDIF
IFDEF SPECTALK_SPECTRANEXT
    ; DAT repopulates font/theme/BPE data before use.  Clearing through the
    ; last driver-state byte also invalidates installer residue at no cost.
    ld hl, _spxn_rom_held + 1
ELSE
    ld hl, __bss_user_tail
ENDIF
    ld de, __data_compiler_tail
    or a
    sbc hl, de          ; HL = total size to zero
    ld b, h
    ld c, l             ; BC = size
    ld a, b
    or c
    jr z, bss_zero_skip ; W10: skip if BSS size = 0
    ex de, hl           ; HL = start address (1 byte vs 2)
bss_loop:
    ld (hl), 0
    inc hl
    dec bc
    ld a, b
    or c
    jr nz, bss_loop
bss_zero_skip:
    ; OPT-SHRINK: zero_fill_256 subroutine saves 5B for 2 identical fills
    ; Zero Printer Buffer: 0x5B00..0x5BFF (256 bytes)
    ld hl, 0x5B00
    call zero_fill_256
    ; Zero CHANS workspace: 0x5CB6..0x5DB5 (256 bytes)
    ld hl, 0x5CB6
    call zero_fill_256
    ; Zero UDG area: 0xFF58..0xFFF1 (154 bytes)
    ld hl, 0xFF58
    ld b, 154
udg_zero_loop:
    ld (hl), a
    inc hl
    djnz udg_zero_loop
IFDEF SPECTALK_SPECTRANEXT
    ; The fixed user-mode string is outside compiler BSS.  An initial NUL is
    ; sufficient to make it empty before the first status-bar render.
    ld (_user_mode), a
ENDIF
    ; --- IM2 removed ---
    ; IM2 was dead code: frame_wait() uses IM1 exclusively.
    ; The CRT IM2 setup was overwriting BSS at $FC00+ (bpe_dict, esx_* vars).
    ; Classic enters in IM1; native NEX sets it explicitly above.
    ; Invalidar cache de fila screen/attr
    ld a, 0xFF
    ld (cache_row_y), a
    jr bss_zero_done         ; skip past subroutine

; OPT-SHRINK: zero-fill 256 bytes from HL (saves 5B for 2 identical fills)
zero_fill_256:
    xor a
    ld b, a
zf_loop:
    ld (hl), a
    inc hl
    djnz zf_loop
    ret

bss_zero_done:

SECTION code_user

; =============================================================================
; CONSTANTS - Video and Memory Addresses
; =============================================================================
VIDEO_BASE      EQU 0x4000      ; Screen memory base
ATTR_BASE       EQU 0x5800      ; Attribute memory base
SCREEN_WIDTH    EQU 32          ; Physical screen width in characters
SCREEN_HEIGHT   EQU 24          ; Physical screen height in rows

; =============================================================================
; CONSTANTS - Ring Buffer
; =============================================================================
; WARNING-M14: Estas constantes DEBEN coincidir con spectalk.h
; RING_BUFFER_SIZE=2048, RING_BUFFER_MASK=0x07FF
RING_SIZE       EQU 2048        ; == RING_BUFFER_SIZE  (spectalk.h:85)
RING_MASK       EQU 0x07FF      ; == RING_BUFFER_MASK  (spectalk.h:86)
RX_LINE_MAX     EQU 510         ; == RX_LINE_SIZE - 2  (spectalk.h:103)

; =============================================================================
; PUBLIC FUNCTIONS (visible from C)
; =============================================================================
IFDEF SPECTALK_SPECTRANEXT
EXTERN _esx_detect
ELSE
PUBLIC _esx_detect
ENDIF
PUBLIC _hl_mul32
PUBLIC _a_sext_mul32
PUBLIC _l_mul32
PUBLIC _channel_name_ptr
PUBLIC _channel_flags_ptr
PUBLIC _l_channel_flags_ptr
PUBLIC _channel_dec_users
PUBLIC _friend_initial_match
PUBLIC _is_tracked_friend
PUBLIC _irc_param_0
PUBLIC _irc_param_1
PUBLIC _irc_param_2
PUBLIC _rx_pos_reset
PUBLIC _reset_rx_state
PUBLIC _leave_ix
PUBLIC _ld_hl_ix4
PUBLIC _ld_hl_ixm2
PUBLIC _ld_hl_ix6
PUBLIC _ld_hl_ixm4
PUBLIC _st_hl_ix4
PUBLIC _st_hl_ixm2
PUBLIC _set_border
PUBLIC _check_caps_toggle
PUBLIC _key_shift_held
PUBLIC _input_cache_invalidate
PUBLIC _print_str64_char
PUBLIC _print_line64_fast
PUBLIC _print_status_left54_fast
PUBLIC _draw_indicator
PUBLIC _draw_cursor_underline
; draw_indicator_big removed (big mode eliminated)
PUBLIC _clear_line
PUBLIC _clear_zone
PUBLIC _compute_screen_base
PUBLIC _st_stricmp
PUBLIC _st_stristr
PUBLIC _u16_to_dec
PUBLIC _str_to_u16
PUBLIC _uart_send_string
PUBLIC _rb_pop
PUBLIC _rb_push
PUBLIC _try_read_line_nodrain
PUBLIC _reapply_screen_attributes
PUBLIC _cls_fast
PUBLIC _uart_drain_to_buffer
PUBLIC _main_print
PUBLIC _main_newline
PUBLIC _main_hline
PUBLIC _overlay_header
PUBLIC _tokenize_params
PUBLIC _sb_append
PUBLIC _draw_badge_dither
PUBLIC _notif_clear
PUBLIC _notif_draw
PUBLIC _ikkle_draw
PUBLIC _ikkle_packed
PUBLIC _in_inkey
PUBLIC asm_in_inkey
PUBLIC _nav_push
PUBLIC _find_empty_channel_slot
PUBLIC _snapshot_autojoin_channels
PUBLIC _print_char64
PUBLIC _draw_big_char
PUBLIC _font_lut
PUBLIC _sys_puts_print
PUBLIC _irc_send_cmd1
PUBLIC _irc_send_cmd2
PUBLIC _ensure_args
PUBLIC _fast_u8_to_str
PUBLIC _print_big_str
PUBLIC _sb_put_u8_2d
PUBLIC _puts_u8_nolz
PUBLIC _has_other_mention
PUBLIC _input_word_left
PUBLIC _input_word_right
PUBLIC _input_delete_word
PUBLIC _input_line_start
PUBLIC _input_line_end
PUBLIC _pkt_usr
PUBLIC _pkt_par
PUBLIC _pkt_rest
PUBLIC _pkt_txt
PUBLIC _pkt_cmd
PUBLIC _last_cmd_id
PUBLIC _nb_p
PUBLIC _net_short_buf

; =============================================================================
; EXTERNAL VARIABLES AND FUNCTIONS (defined in C or other .asm)
; =============================================================================
EXTERN _caps_lock_mode
EXTERN _cursor_shift_held
EXTERN _caps_latch
EXTERN _beep_enabled
EXTERN _ui_usage
EXTERN _g_ps64_y
EXTERN _g_ps64_col
EXTERN _g_ps64_attr
EXTERN _ay_uart_send
EXTERN _theme_attrs
; theme_attrs[] offsets (must match spectalk.h #defines)
TA_BANNER   EQU 0
TA_STATUS   EQU 1
TA_MSG_CHAN  EQU 2
TA_MAIN_BG  EQU 5
TA_INPUT_BG EQU 7
TA_MSG_TOPIC EQU 13
TA_BORDER   EQU 19
EXTERN _current_attr
EXTERN _irc_params
EXTERN _irc_param_count
EXTERN _force_status_redraw
EXTERN _status_bar_dirty
EXTERN _uart_drain_limit
EXTERN uartRead         ; CF=1/A=byte si hay datos (divMMC backend)
; _line_buffer, _temp_input, _input_cache_char: via defc at end of file
; (mapped to system RAM: Printer Buffer, CHANS workspace)
EXTERN _irc_pass
EXTERN _nickserv_pass
EXTERN _network_name
EXTERN _irc_is_away
EXTERN _buffer_pressure
EXTERN _ping_latency
EXTERN _pagination_active
EXTERN _pagination_lines
EXTERN _pagination_pause
; _main_newline is implemented below in this file
; EXTERN _main_newline
EXTERN _main_col
EXTERN _main_line
EXTERN _channel_context_next_row
EXTERN _wrap_indent

; Ring buffer ? fixed address outside BSS (between BSS and stack)
PUBLIC _ring_buffer
defc _ring_buffer = 0xF500
EXTERN _rb_head
EXTERN _rb_tail
EXTERN _rx_line
PUBLIC _overlay_slot
defc _overlay_slot = _rx_line   ; alias ? mutually exclusive with IRC receive
EXTERN _rx_pos
EXTERN _rx_overflow
EXTERN _rx_last_len

; Ignore list (para is_ignored)
; Fixed high RAM: ring_buffer ends at $FCFF, stack reserve starts at $FD58.
PUBLIC _ignore_list
defc _ignore_list = 0xFD00  ; 80B (MAX_IGNORES * 16), $FD00-$FD4F
IFDEF SPECTALK_SPECTRANEXT
PUBLIC _user_mode
defc _user_mode = 0xFD50    ; 6B, immediately before the $FD58 stack reserve
ENDIF
EXTERN _ignore_count
; _big_status removed (big mode eliminated)

; =============================================================================
; RING BUFFER CONSTANTS
; Size: 2048 bytes (MUST match RING_BUFFER_SIZE in spectalk.h)
; =============================================================================
DEFC RB_MASK_H = 0x07   ; High byte mask for 2048 (0x0800)
                         ; WARNING: If RING_BUFFER_SIZE changes in C,
                         ; this MUST be updated: 2048?0x07, 4096?0x0F, etc.

; =============================================================================
; SCRATCH TRANSITORIO - Printer Buffer tail ($5BC0-$5BFF, 64B)
; =============================================================================
; Treat this tail as clobberable across esxDOS RST 8. Only data that does not
; survive file I/O may live here (overlay load, DAT, config, help).
; Los render paths (unpack_glyph, print_line64_fast, main_puts/BPE) NO llaman
; esxDOS mid-execution → la zona es estable dentro de cada render.
; Zero-fill inicial cubierto por CRT init (zero_fill_256 en $5B00).
; =============================================================================
defc glyph_buffer    = 0x5BC0  ; 7B  scratch unpack_glyph
defc plf_left_buf    = 0x5BC8  ; 8B  scratch print_line64_fast (nibbles izq)
defc plf_attr_val    = 0x5BD0  ; 1B  scratch print_line64_fast
defc plf_y_val       = 0x5BD1  ; 1B  scratch print_line64_fast
EXTERN _plf_start_byte          ; persistent caller state in compiler BSS
EXTERN _plf_pair_count          ; persistent optional limit in compiler BSS
defc bpe_rstack      = 0x5BD3  ; 16B BPE return stack (8 niveles x 2B)
defc bpe_rsp         = 0x5BE3  ; 2B  BPE stack pointer
defc _net_short_buf  = bpe_rstack ; 12B status temp, copied before render/BPE
; $5BE5-$5BE6 2B  main_print_wrapped_ram() last-space scratch
; $5BE7-$5BEE 8B  C fmt_buf transient decimal/time scratch
; $5BEF unused
; $5BF0-$5BFF 16B IRC parser context. No esxDOS while live; handlers can
; print without corrupting packet globals.
defc _pkt_usr          = 0x5BF0  ; 2B
defc _pkt_par          = 0x5BF2  ; 2B
defc _pkt_rest         = 0x5BF4  ; 2B
defc _pkt_txt          = 0x5BF6  ; 2B
defc _pkt_cmd          = 0x5BF8  ; 2B
defc _last_cmd_id      = 0x5BFA  ; 2B
; $5BFC-$5BFD unused; pkt_empty/names_friend_pos persist in compiler BSS
defc _nb_p             = 0x5BFE  ; 2B

; =============================================================================
; VARIABLES BSS (solo las que deben sobrevivir a llamadas esxDOS RST 8)
; =============================================================================
SECTION bss_user
; Not CRT-zeroed. cache_row_y is explicitly invalidated to avoid false hits.
IFDEF SPECTALK_SPECTRANEXT
; Target-only persistent tail after the driver-owned XFS state ($5B80-$5B93).
; The XFS directory scratch is elsewhere ($5CB6-$5DB5).
PUBLIC _theme_attrs
PUBLIC _last_pm_nick
defc _theme_attrs  = 0x5B94  ; 20B, $5B94-$5BA7
defc _last_pm_nick = 0x5BA8  ; 18B, $5BA8-$5BB9
defc cache_scr_base = 0x5BBA ; 2B
defc cache_atr_base = 0x5BBC ; 2B
defc cache_row_y     = 0x5BBE ; 1B; $5BBF remains free
ELSE
cache_scr_base: defs 2  ; Screen base addr cacheada (print_str64_char)
cache_atr_base: defs 2  ; Attr base addr cacheada (print_str64_char)
cache_row_y:   defs 1   ; Fila Y del cache (0xFF = inv?lido)
                        ; NOTA: cache_row_y DEBE estar en BSS. Si esxDOS
                        ; dejase aquí un valor != 0xFF coincidente con y
                        ; actual, next lookup tendría cache hit falso.
ENDIF


SECTION code_user


