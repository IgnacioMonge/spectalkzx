#!/usr/bin/env python3
"""Loss-boundary regressions and the ASM entry points that implement them."""
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def code(path):
    return " ".join(line.split(";", 1)[0].strip()
                    for line in (ROOT / path).read_text(encoding="utf-8").splitlines())


class Receiver:
    def __init__(self, start=0):
        self.head = self.tail = start
        self.ring = bytearray(2048)
        self.partial = bytearray()
        self.discard = False

    def gap(self):
        self.tail = self.head
        self.partial.clear()
        self.discard = True

    def push(self, byte):
        following = (self.head + 1) & 2047
        if following == self.tail:
            self.gap()
            return False
        self.ring[self.head] = byte
        self.head = following
        return True

    def read(self):
        lines = []
        while self.tail != self.head:
            byte = self.ring[self.tail]
            self.tail = (self.tail + 1) & 2047
            if byte == 13:
                continue
            if byte == 10:
                if self.partial and not self.discard:
                    lines.append(bytes(self.partial))
                self.partial.clear()
                self.discard = False
            elif len(self.partial) < 510:
                self.partial.append(byte)
            else:
                self.discard = True
        return lines


def receive(receiver, data):
    for byte in data:
        receiver.push(byte)
    return receiver.read()


def loss_boundaries():
    # Old complete lines cannot acknowledge a later loss, for any ring wrap.
    pending = b"a\n" * 1019 + b"\nPING :ab"
    assert len(pending) == 2047
    for start in range(2048):
        rx = Receiver(start)
        for byte in pending:
            assert rx.push(byte)
        assert not rx.push(ord("X"))
        assert rx.read() == []
        assert receive(rx, b"cd\r\nPING :safe\r\n") == [b"PING :safe"]
    rx = Receiver()
    assert receive(rx, b"a" * 510 + b"\r\n") == [b"a" * 510]
    assert receive(rx, b"a" * 511 + b"\nOK\n") == [b"OK"]
    assert receive(rx, b"PING :ab") == []
    rx.gap()
    assert receive(rx, b"cd\n") == []
    assert receive(rx, b"PING :safe\n") == [b"PING :safe"]


def cts_backpressure():
    # A full ring leaves the byte in the UART (CTS holds the ESP): no gap, no loss.
    lines = [b":s NOTICE n :seq %06d xxxxxxxx" % i for i in range(400)]
    sent = b"".join(line + b"\r\n" for line in lines)
    rx = Receiver(1500)
    pos = 0
    got = []
    while pos < len(sent):
        while pos < len(sent) and (rx.head + 1) & 2047 != rx.tail:
            assert rx.push(sent[pos])
            pos += 1
        got += rx.read()
        assert not rx.discard
    assert got == lines


def hardware_fifo_gap():
    rx = Receiver()
    receive(rx, b"PING :head")
    fifo = deque(b"old\n" * 40 + b"damaged")
    calls = 0
    while fifo:
        rx.gap()
        for _ in range(min(32, len(fifo))):
            fifo.popleft()
        calls += 1
        assert rx.read() == []
    assert calls > 1
    assert receive(rx, b"tail\nPING :safe\n") == [b"PING :safe"]


def tx_fail_stop():
    for failed_at in range(len(b"CMD arg\r\n")):
        sent = bytearray()
        failed = False
        for index, byte in enumerate(b"CMD arg\r\nNEXT\r\n"):
            busy = 192 if index == failed_at else 0
            if failed:
                continue
            for poll in range(192):
                if poll >= busy:
                    sent.append(byte)
                    break
            else:
                failed = True
        assert sent == b"CMD arg\r\n"[:failed_at]
    assert next(p for p in range(192) if p >= 191) == 191


def source_contract():
    helpers = code("asm/spectalk_asm/10_core_helpers.asm")
    gap = helpers.split("_rx_discard_pending:", 1)[1].split("PUBLIC", 1)[0]
    assert "ld hl, (_rb_head) ld (_rb_tail), hl" in gap
    assert "ld a, 1 ld (_rx_overflow), a jp _rx_pos_reset" in gap
    ring = code("asm/spectalk_asm/20_rx_ring_uart.asm")
    assert "_rb_push_full: call _rx_discard_pending" in ring
    assert "ld a, (_overlay_exec_active) or a jr nz, _rb_push_full" in ring
    loader = code("asm/overlay_loader.asm")
    assert " ".join(loader.split()).count("jp ovl_enter") == 2
    assert "ld de, ovl_return push de jp (hl) ovl_return: xor a ld (_overlay_exec_active), a ret" in loader
    output = code("asm/spectalk_asm/40_text_numeric_screen.asm")
    assert "ld a, (_overlay_exec_active) or a ret nz" in output
    assert "call _ay_uart_send pop hl ret c inc hl" in output
    ready = output.split("drain_read_ready:", 1)[1].split("drain_maybe_wait:", 1)[0]
    assert ready.index("jr z, drain_ring_full") < ready.index("in a, (c)")
    assert "drain_ring_full: ld h, b ld l, c ld (_rb_head), hl exx ret" in ready
    assert "_rx_discard_pending" not in ready
    runtime = code("asm/spectalk_asm/80_ui_runtime.asm")
    assert "sbc hl, de jr z, fwd_check_frame call uartRead" in runtime
    assert "_rb_push" not in code("asm/divmmc_uart.asm")
    assert output.count("call drain_next_status") == 2
    assert "call _next_uart_status bit 6, a ret z exx ld hl, (_rb_head) ld de, (_rb_tail) exx ret" in output
    for target in ("divmmc", "next"):
        driver = code(f"asm/{target}_uart.asm")
        assert "ld a, (_uart_tx_failed) or a scf ret nz" in driver
        assert "jp z, _uart_tx_fail" in driver
        assert "out (c), l or a ret" in driver
    driver = code("asm/next_uart.asm")
    assert driver.count("call _next_uart_status") == 2
    assert "and 0xE4" in driver and "ld d, 32" in driver
    assert "call _rx_discard_pending" in driver
    assert "and 0xFE or 0x40 ret" in driver
    release = helpers.split("_overlay_rx_release:", 1)[1].split("EXTERN", 1)[0]
    assert "IFNDEF SPECTALK_NEXT ld hl, (_rb_head)" in release
    exit_body = helpers.split("_overlay_exit_full:", 1)[1].split("_set_border:", 1)[0]
    assert "call _overlay_rx_release" in exit_body
    assert "ld (_rx_overflow), a" not in exit_body
    app = (ROOT / "src/spectalk.c").read_text(encoding="utf-8")
    assert "uart_tx_failed == 1" in app and "uart_tx_failed = 2;" in app
    assert "uart_tx_failed ? STATE_DISCONNECTED : STATE_WIFI_OK" in app
    # Classic enables session CTS only on the AT-probe timeout path.
    assert 'S_AT_UART_CTS[] = "AT+UART_CUR=115200,8,1,0,2"' in app
    init = app.split("uint8_t esp_init(void)", 1)[1].split("esp_init_fail:", 1)[0]
    probe = init.index("// 3. Test final AT")
    assert init.count("esp_hard_cmd(S_AT_UART_CTS)") == 1
    assert probe < init.index("esp_hard_cmd(S_AT_UART_CTS)")
    assert init.index("next_esp_reset:") < init.index("esp_hard_cmd(S_AT_UART_CTS)")
    for path in (ROOT / "overlay").glob("*.c"):
        assert "reset_rx_state()" not in path.read_text(encoding="utf-8"), path


if __name__ == "__main__":
    loss_boundaries()
    cts_backpressure()
    hardware_fifo_gap()
    tx_fail_stop()
    source_contract()
    print("Transport loss, fail-stop and overlay RX contracts OK")
