; =============================================================================
; CACHE DE INPUT
; =============================================================================

; -----------------------------------------------------------------------------
; void input_cache_invalidate(void)
; Rellena input_cache_char (128 bytes) con 0xFF
; -----------------------------------------------------------------------------
_input_cache_invalidate:
    ld hl, _input_cache_char
    ld (hl), 0xFF
    ld d, h
    ld e, l
    inc de
    ld bc, 127
    ldir
    ret

; =============================================================================
; RING BUFFER
; Size: 2048 bytes (0x0800)
; Mask: 0x07FF (Low: 0xFF, High: 0x07)
; =============================================================================

; -----------------------------------------------------------------------------
; int16_t rb_pop(void)
; Saca un byte del buffer.
; Retorna: HL = byte le?do (0-255), o -1 si buffer vac?o.
; -----------------------------------------------------------------------------
_rb_pop:
    ; 1. Comprobar si hay datos (Head != Tail)
    ld hl, (_rb_head)
    ld de, (_rb_tail)
    or a                    ; Limpiar carry
    sbc hl, de
    jr z, rb_pop_empty      ; Si resultado es 0, buffer vac?o -> salir
    
    ; 2. Leer el byte: ring_buffer[tail]
    ld hl, _ring_buffer
    add hl, de              ; HL = direcci?n real en memoria (&ring_buffer + tail)
    ld l, (hl)              ; Leemos el byte
    ld h, 0                 ; H=0 para retornar un int16 limpio
    
    ; 3. Avanzar Tail: tail = (tail + 1) & MASK
    inc de                  ; Incrementamos Tail
    ; NOTA: No hacemos AND E, 0xFF porque es redundante
    res 3, d                ; Tail is 0..7FF, inc can only set bit 3
    ld (_rb_tail), de       ; Guardamos nuevo Tail
    
    ret

rb_pop_empty:
    ld hl, -1
    ret

; -----------------------------------------------------------------------------
; uint8_t rb_push(uint8_t b) __z88dk_fastcall
; Mete un byte en el buffer.
; Input: L = byte a guardar
; Retorna: L=1 (?xito), L=0 (Buffer Lleno)
; -----------------------------------------------------------------------------
_rb_push:
IFNDEF SPECTALK_NEXT
IFNDEF SPECTALK_SPECTRANEXT
EXTERN _overlay_exec_active
    ld a, (_overlay_exec_active)
    or a
    jr nz, _rb_push_full ; byte already consumed: preserve the loss boundary
ENDIF
ENDIF
    ld a, l             ; Keep byte in A; OR A below clears Carry without changing it
    
    ; 1. Calcular d?nde ir?a el NUEVO Head = (head + 1) & MASK
    ld hl, (_rb_head)
    ld d, h             ; DE = head actual (guardamos para escribir despu?s)
    ld e, l
    inc hl
    
    ; Aplicar mascara solo a la parte alta (la baja hace overflow natural a 0)
    res 3, h                ; Head is 0..7FF, inc can only set bit 3
    
    ; HL contiene ahora el "Futuro Head"
    ; DE contiene el "Head Actual" (donde escribiremos)
    
    ; 2. Comprobar colisi?n: ?El Futuro Head choca con el Tail actual?
    ld bc, (_rb_tail)
    or a                    ; clear carry for SBC
    sbc hl, bc              ; Z=1 if future head == tail
    add hl, bc              ; restore future head; ADD HL does not alter Z
    jr z, _rb_push_full ; Si son iguales, el buffer est? lleno. Abortar.
    
_rb_push_ok:
    ; 3. Guardar el Futuro Head en la variable global
    ; NOTA: En un sistema con ISR concurrente esto ser?a incorrecto (head antes de write),
    ;       pero aqu? todo es polling s?ncrono, sin riesgo de race condition.
    ld (_rb_head), hl
    
    ; 4. Escribir el dato en la memoria: buffer[head_viejo]
    ld hl, _ring_buffer
    add hl, de              ; HL = direcci?n de escritura (buffer + head_viejo)
    
    ld (hl), a              ; Escribimos en memoria
    
    ld l, 1                 ; Retornar 1 (?xito)
    ret

_rb_push_full:
    call _rx_discard_pending
    ld l, 0             ; Retornar 0 (Fallo/Lleno)
    ret

; -----------------------------------------------------------------------------
; _try_read_line_nodrain
; Consume el buffer buscando un \n. Si hay desbordamiento, descarta bytes
; de forma segura sin escribir en memoria hasta encontrar el \n.
; -----------------------------------------------------------------------------
_try_read_line_nodrain:
    ; Cache tail, available byte count, and rx_line write pointer for this
    ; parser pass. UART drain cannot append while this routine is running.
    ld de, (_rb_tail)       ; DE = ring tail offset
    ld hl, (_rb_head)
    or a
    sbc hl, de              ; HL = (head - tail) mod 2048 after mask
    ld a, h
    and 0x07
    ld h, a
    push hl
    exx
    pop bc                  ; BC' = bytes available in ring
    exx
    ld hl, (_rx_pos)
    ld bc, _rx_line
    add hl, bc
    ld b, h
    ld c, l                 ; BC = &rx_line[rx_pos]

trln_loop:
    ; 1. Comprobar si quedan bytes del snapshot inicial
    exx
    ld a, b
    or c
    exx
    jr z, trln_return_0
    
    ; 2. Leer byte del anillo
    ld hl, _ring_buffer
    add hl, de
    ld a, (hl)          ; A = byte le?do
    
    ; 3. Avanzar Tail
    inc de
    res 3, d            ; M?scara 0x07: tail is 0..7FF, inc can only set bit 3
    exx
    dec bc              ; consume one byte from cached availability
    exx
    
    ; 4. Analyze character
    cp 0x0D             ; Ignorar \r
    jr z, trln_loop
    
    cp 0x0A             ; End of line \n
    jr z, trln_newline
    
    ; 5. CR?TICO: Chequear desbordamiento ANTES de escribir (HARDENED)
    ; BC is the live write pointer; limit is &_rx_line[RX_LINE_MAX].
    ld hl, _rx_line + RX_LINE_MAX
    or a
    sbc hl, bc
    jr c, trln_overflow_state
    jr z, trln_overflow_state ; Si rx_pos >= 510, descartar
    
    ; 6. Save character (no hay overflow)
    ld (bc), a
    
    ; 7. Incrementar posici?n
    inc bc
    jr trln_loop

trln_overflow_state:
    ; Marcar flag de overflow (ahora es uint8_t)
    ld a, 1
    ld (_rx_overflow), a
    ; IMPORTANTE: NO escribir A en memoria, ni incrementar rx_pos.
    ; Simply return to loop para consumir el siguiente byte.
    jr trln_loop

trln_newline:
    ; Terminar string con NULL
    xor a
    ld (bc), a
    
    ; Check if line had overflow (ahora es uint8_t)
    ld hl, _rx_overflow
    ld a, (hl)
    or a
    jr z, trln_check_valid
    
    ; If overflow, DISCARD line completa y resetear
    ld (hl), 0
    ld bc, _rx_line
    jr trln_loop        ; Look for next line

trln_check_valid:
    ; If length > 0, valid line
    ld a, c
    sub _rx_line & 0xFF
    ld l, a
    ld a, b
    sbc a, _rx_line >> 8
    ld h, a
    ld a, l
    or h
    jr z, trln_loop     ; Ignore empty lines
    
    ; ?xito: Reset rx_pos y retornar 1
    ; Guardar longitud de la l?nea (rx_pos) para evitar strlen() en C
    ld (_rx_last_len), hl

    ld hl, 0
    ld (_rx_pos), hl
    ld (_rb_tail), de
    ld l, 1
    ret

trln_return_0:
    ld (_rb_tail), de
    ld h, b
    ld l, c
    ld de, _rx_line
    or a
    sbc hl, de
    ld (_rx_pos), hl
    ld l, 0
    ret


