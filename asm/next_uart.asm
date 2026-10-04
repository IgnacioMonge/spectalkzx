;; Native ZX Spectrum Next UART backend for the internal ESP.

SECTION code_user

EXTERN _frame_wait
EXTERN _rb_push
EXTERN _overlay_mode
EXTERN _uart_tx_failed
EXTERN _uart_tx_fail
EXTERN _rx_discard_pending
PUBLIC _next_uart_status
PUBLIC _ay_uart_init
PUBLIC _ay_uart_send
PUBLIC uartRead

UART_TX_STATUS       EQU 0x133B
UART_RX_BAUD         EQU 0x143B
UART_SELECT          EQU 0x153B
UART_FRAME           EQU 0x163B
UART_SELECT_ESP      EQU 0x30 ; bit 5 selects ESP; bit 4 latches prescaler high bits
UART_FRAME_RESET_8N1 EQU 0x98
UART_FRAME_8N1       EQU 0x18
UART_TX_POLL_BUDGET  EQU 0xC0

NEXTREG_SELECT       EQU 0x243B
NEXTREG_DATA         EQU 0x253B
NEXTREG_VIDEO_TIMING EQU 0x11

;; CF=1/A=byte when RX data is available; CF=0 otherwise.
uartRead:
    ld bc, UART_TX_STATUS
    call _next_uart_status
    rrca
    ret nc
    inc b
    in a, (c)
    ret

;; Select ESP, set 8N1/115200 for the active video timing and drain startup RX.
_ay_uart_init:
    ld bc, UART_SELECT
    ld a, UART_SELECT_ESP
    out (c), a

    inc b
    ld a, UART_FRAME_RESET_8N1
    out (c), a
    ld a, UART_FRAME_8N1
    out (c), a

    call next_uart_set_baud_115200

    ld b, 10
next_uart_init_wait:
    push bc
    call uartRead
    pop bc
    call _frame_wait
    djnz next_uart_init_wait

    ; Fixed bounded scan: do not stop at the first transient FIFO gap.
    ld de, 512
next_uart_init_flush:
    call uartRead
    dec de
    ld a, d
    or e
    jr nz, next_uart_init_flush
    ret

;; Fastcall byte in L. Bound TX wait and preserve RX progress while resident.
_ay_uart_send:
    ld a, (_uart_tx_failed)
    or a
    scf
    ret nz
    ld d, UART_TX_POLL_BUDGET
    ld bc, UART_TX_STATUS
next_uart_send_wait:
    call _next_uart_status
    bit 1, a
    jr z, next_uart_send_ready
    dec d
    jp z, _uart_tx_fail
    rrca
    jr nc, next_uart_send_wait
    ld a, (_overlay_mode)
    or a
    jr nz, next_uart_send_wait

    inc b
    in a, (c)
    dec b
    push hl
    push de
    ld l, a
    call _rb_push
    pop de
    pop hl
    ld bc, UART_TX_STATUS
    jr next_uart_send_wait

next_uart_send_ready:
    out (c), l
    or a
    ret

; Read all clear-on-read error flags at every status access.
; On a fault, discard through FIFO-empty before exposing bytes again. Each
; call consumes at most 32 bytes; a persistent fault survives budget exits.
; BC=$133B. Preserves BC/DE/HL, returns status with RX hidden and bit6 set
; whenever the caller must reload cached ring indices after invalidation.
; https://wiki.specnext.dev/UART_TX (bits 7/6/5/2)
_next_uart_status:
    in a, (c)
    push af
    and 0xE4
    jr nz, next_uart_rx_fault
    ld a, (next_rx_fault)
    or a
    jr nz, next_uart_rx_fault
    pop af
    ret
next_uart_rx_fault:
    push hl
    call _rx_discard_pending
    pop hl
    ld a, 1
    ld (next_rx_fault), a
    pop af
    push de
    ld d, 32
next_uart_rx_flush:
    bit 0, a
    jr z, next_uart_rx_empty
    inc b
    in a, (c)
    dec b
    in a, (c)
    dec d
    jr nz, next_uart_rx_flush
    jr next_uart_rx_hidden
next_uart_rx_empty:
    push af
    xor a
    ld (next_rx_fault), a
    pop af
next_uart_rx_hidden:
    pop de
    and 0xFE
    or 0x40
    ret

SECTION bss_user
next_rx_fault: defs 1
SECTION code_user

next_uart_set_baud_115200:
    di
    ld bc, NEXTREG_SELECT
    ld a, NEXTREG_VIDEO_TIMING
    out (c), a
    inc b
    in a, (c)
    and 7
    add a, a
    ld e, a
    ld d, 0
    ld hl, next_uart_baud_115200
    add hl, de
    ld e, (hl)
    inc hl
    ld d, (hl)
    ex de, hl

    ld bc, UART_RX_BAUD
    ld a, l
    and 0x7F
    out (c), a
    ld a, h
    rl l
    rla
    or 0x80
    out (c), a
    ret

;; Divisors for NextReg $11 timings VGA0..VGA6 and HDMI.
next_uart_baud_115200:
    DEFW 243, 248, 256, 260, 269, 278, 286, 234
