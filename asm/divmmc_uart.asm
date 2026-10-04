;;
;; divmmc_uart.asm - Optimized UART backend for divMMC/divTIESUS
;; SpecTalk ZX
;;

SECTION code_user

EXTERN _frame_wait
EXTERN _uart_tx_failed
EXTERN _uart_tx_fail
PUBLIC _ay_uart_init
PUBLIC _ay_uart_send
PUBLIC uartRead

; ZX-Uno compatible register interface
UART_DATA_REG     EQU 0xC6
UART_STAT_REG     EQU 0xC7
UART_BYTE_RECIVED EQU 0x80
UART_BYTE_SENDING EQU 0x40
ZXUNO_ADDR        EQU 0xFC3B
ZXUNO_REG         EQU 0xFD3B
UART_TX_POLL_BUDGET EQU 0xC0

SECTION code_user

; -----------------------------------------------------------------------------
; Internal helper: uartRead
; Return: CF=1 and A=byte if data available, CF=0 otherwise.
; -----------------------------------------------------------------------------
uartRead:
    ; Check Hardware
    ld bc, ZXUNO_ADDR
    ld a, UART_STAT_REG
    out (c), a

    ; OPTIMIZACIÓN: FC3B -> FD3B (4 ciclos vs 10 ciclos)
    inc b

    in a, (c)
    add a, a        ; RX-ready bit -> Carry; port-select/read ops below preserve CF
    ret nc

    dec b
    ld a, UART_DATA_REG
    out (c), a
    
    ; OPTIMIZACIÓN: FC3B -> FD3B
    inc b
    
    in a, (c)
    ret

; -----------------------------------------------------------------------------
; _ay_uart_init
; OPTIMIZACIÓN: Reducción de tiempos de espera y bucle de flush ajustado
; -----------------------------------------------------------------------------
_ay_uart_init:
    ; Prime reads
    ld bc, ZXUNO_ADDR
    ld a, UART_STAT_REG
    out (c), a
    
    inc b           ; OPTIMIZACIÓN
    
    in a, (c)

    dec b
    ld a, UART_DATA_REG
    out (c), a
    
    inc b           ; OPTIMIZACIÓN
    
    in a, (c)

    ld b, 10        ; OPTIMIZACIÓN: Reducido de 50 a 10 frames
uartInit_wait:
    push bc
    call uartRead
    pop bc
    call _frame_wait
    djnz uartInit_wait

    ld bc, 0x0200   ; OPTIMIZACIÓN: Reducido de 0x0800 a 512 bytes
uartInit_flush:
    push bc
    call uartRead
    pop bc
    dec bc
    ld a, b
    or c
    jr nz, uartInit_flush

    ret

; -----------------------------------------------------------------------------
; _ay_uart_send
; -----------------------------------------------------------------------------
_ay_uart_send:
    ld a, (_uart_tx_failed)
    or a
    scf
    ret nz                  ; fail-stop until the transport is reinitialized
    ; L = byte to send (fastcall), preserved until out (c), l at end
    ld d, UART_TX_POLL_BUDGET ; budget: up to 192 busy samples

    ; Select status register for TX-ready polling.
    ld bc, ZXUNO_ADDR
    ld a, UART_STAT_REG
    out (c), a
    
    inc b           ; OPTIMIZACIÓN

    ; Bounded by poll count, not wall time. RX bytes are not read here: the
    ; divTIESUS/ZX-Uno RTS line holds the ESP (CTS flow control) until a drain
    ; has ring room. Exhaustion latches a failure; no later byte may be sent.
uartSend_wait_tx:
    in a, (c)
    and UART_BYTE_SENDING
    jr z, uartSend_tx_ready
    dec d
    jp z, _uart_tx_fail
    jr uartSend_wait_tx

uartSend_tx_ready:
    ; OPT: dec b switches BC from ZXUNO_REG (FD3B) to ZXUNO_ADDR (FC3B)
    dec b
    ld a, UART_DATA_REG
    out (c), a

    inc b
    out (c), l          ; OPT: direct from fastcall reg, no push/pop
    or a                ; CF=0: transmitted
    ret
