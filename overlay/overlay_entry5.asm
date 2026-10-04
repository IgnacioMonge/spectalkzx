;; overlay_entry5.asm — Entry table for SPCTLK5.OVL
SECTION code_user
EXTERN _config_render_ovl
EXTERN _rtc_seed_ovl
EXTERN _rtc_enable_ovl
IFDEF SPECTALK_SPECTRANEXT
EXTERN _config_load_ovl
ELSE
IFDEF SPECTALK_NEXT
EXTERN _next_esp_reset_ovl
EXTERN _config_load_ovl
ENDIF
ENDIF
PUBLIC _tz_cmd_ovl
EXTERN _overlay_slot
EXTERN _sntp_tz
EXTERN _sntp_tz_last
EXTERN _sntp_init_sent
EXTERN _sntp_waiting
EXTERN _sntp_queried
EXTERN _connection_state
EXTERN _time_hour
EXTERN _status_bar_dirty
EXTERN _config_dirty
EXTERN _str_to_u16
EXTERN _overlay_rx_release
EXTERN _sys_puts
EXTERN _main_puts
EXTERN _main_putc
EXTERN _main_newline
EXTERN _puts_u8_nolz
EXTERN _ui_err
EXTERN _K_TZ

DEFC TZ_RTC        = 127
DEFC STATE_WIFI_OK = 1

IFDEF SPECTALK_SPECTRANEXT
    dw 5                      ; Spectranext adds the cold config-load entry
ELSE
IFDEF SPECTALK_NEXT
    dw 6                      ; native Next adds reset-pulse and config-load entries
ELSE
    dw 4
ENDIF
ENDIF
    dw _config_render_ovl     ; entry 0 -> config
    dw _rtc_seed_ovl          ; entry 1 -> cold RTC seed
    dw _rtc_enable_ovl        ; entry 2 -> !tz rtc
    dw _tz_cmd_ovl            ; entry 3 -> !tz numeric
IFDEF SPECTALK_SPECTRANEXT
    dw _config_load_ovl       ; entry 4 -> cold config load
ELSE
IFDEF SPECTALK_NEXT
    dw _next_esp_reset_ovl    ; entry 4 -> shared bus/ESP reset pulse
    dw _config_load_ovl       ; entry 5 -> cold config load
ENDIF
ENDIF

; ENTRY 3 — !tz numeric. overlay_slot contains the copied argument string.
_tz_cmd_ovl:
    ld hl, _overlay_slot
    ld a, (hl)
    or a
    jp z, tz_show_current

    or 0x20
    cp 'r'
    jr nz, tz_numeric_from_start
    ld a, (_overlay_slot+1)
    or 0x20
    cp 't'
    jr nz, tz_numeric_from_start
    ld a, (_overlay_slot+2)
    or 0x20
    cp 'c'
    jr nz, tz_numeric_from_start
    ld a, (_overlay_slot+3)
    or a
    jp z, _rtc_enable_ovl

tz_numeric_from_start:
    ld hl, _overlay_slot
    ld a, (hl)
    ld b, 0                    ; neg flag
    cp '-'
    jr nz, tz_check_plus
    inc b
    inc hl
    jr tz_after_sign
tz_check_plus:
    cp '+'
    jr nz, tz_after_sign
    inc hl

tz_after_sign:
    ld a, (hl)
    sub '0'
    cp 10
    jr nc, tz_range
    push bc
    call _str_to_u16           ; HL = abs value, stops on first non-digit
    pop bc
    ld a, h
    or a
    jr nz, tz_range
    ld a, l
    cp 13
    jr nc, tz_range

    dec b                      ; neg flag was 0 -> NZ (skip), was 1 -> Z
    jr nz, tz_new_ready
    cpl
    inc a
tz_new_ready:
    ld c, a

    ld a, (_sntp_tz)
    ld b, a                    ; B = old TZ/source
    ld d, 0                    ; D = changed flag
    cp TZ_RTC
    jr z, tz_changed_from_rtc
    ld a, c
    cp b
    jr z, tz_store_new

    sub b
    add a, 24
    ld e, a
    ld a, (_time_hour)
    add a, e
tz_hour_mod:
    cp 24
    jr c, tz_hour_done
    sub 24
    jr tz_hour_mod
tz_hour_done:
    ld (_time_hour), a

tz_changed_from_rtc:
    ld d, 1

tz_store_new:
    ld a, c
    ld (_sntp_tz_last), a
    ld (_sntp_tz), a
    ld a, d
    or a
    jr z, tz_suffix_none

    xor a
    ld (_sntp_init_sent), a
    ld (_sntp_waiting), a
    ld (_sntp_queried), a
    inc a
    ld (_status_bar_dirty), a
    ld (_config_dirty), a

    ld a, (_connection_state)
    cp STATE_WIFI_OK
    ld a, 1                    ; suffix: sync
    jr z, tz_print_numeric
    inc a                      ; suffix: later
    jr tz_print_numeric

tz_range:
    ld hl, tz_range_msg
    call _ui_err
    jr tz_done

tz_show_current:
    ld a, (_sntp_tz)
    cp TZ_RTC
    jr nz, tz_suffix_none
    ld hl, _K_TZ
    call _sys_puts
    ld hl, tz_rtc_msg
    call _main_puts
    call _main_newline
    jr tz_done

tz_suffix_none:
    xor a                      ; suffix: none, falls through to tz_print_numeric

tz_print_numeric:
    push af                    ; suffix
    ld hl, _K_TZ
    call _sys_puts
    ld a, (_sntp_tz)
    or a                       ; sets S flag
    ld l, '+'                  ; ld r,n preserves flags
    jp p, tz_print_sign
    ld l, '-'
    cpl
    inc a
tz_print_sign:
    push af
    call _main_putc
    pop af
    ld l, a
    call _puts_u8_nolz
    pop af
    or a
    jr z, tz_print_newline
    cp 1
    ld hl, tz_sync_msg
    jr z, tz_print_suffix
    ld hl, tz_later_msg
tz_print_suffix:
    call _main_puts
tz_print_newline:
    call _main_newline
    jr tz_done

tz_done:
    jp _overlay_rx_release

tz_rtc_msg:
    DEFM "RTC"
    DEFB 0
tz_sync_msg:
    DEFM " sync"
    DEFB 0
tz_later_msg:
    DEFM " later"
    DEFB 0
tz_range_msg:
    DEFM "Range -12..12"
    DEFB 0
