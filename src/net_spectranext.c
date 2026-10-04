/* Spectranext direct socket backend. No UART or ESP-AT layer. */

#include "../include/spectalk.h"
#include "spxn_rom.h"

#define NET_RECV_CHUNK 512u
#define NET_SEND_ZERO_BUDGET 50u
static uint8_t net_hup_pending;
static uint8_t net_fd;
static uint8_t net_open; /* 0=no fd, 1=TX usable, 2=closed/TX failed */
static uint8_t net_poll_in;

extern uint8_t rb_push(uint8_t value) __z88dk_fastcall;

static void net_mark_closed(void)
{
    if (net_open == 1) {
        net_open = 2;
        net_hup_pending = 1;
    }
}

static void net_publish_closed(void)
{
    static const char closed[] = "CLOSED\r\n";
    const char *p = closed;
    uint16_t free = (uint16_t)(rb_tail - rb_head - 1u) & RING_BUFFER_MASK;

    if (!net_hup_pending || free < sizeof(closed) - 1u) return;
    while (*p) rb_push((uint8_t)*p++);
    net_hup_pending = 0;
}

#define net_rom_failed(flags) ((flags) & ROM_CARRY)

static void net_send_block(const void *data, uint16_t length)
{
    const uint8_t *next = (const uint8_t *)data;
    uint8_t zero_budget = NET_SEND_ZERO_BUDGET;
    uint16_t sent;

    if (connection_state < STATE_TCP_CONNECTED || net_open != 1 || !length) return;
    while (length) {
        spxn_regs.a = net_fd;
        spxn_regs.de = (uint16_t)(uintptr_t)next;
        spxn_regs.bc = length;
        if (net_rom_failed(spxn_rom_hlcall(ROM_SEND)) ||
            spxn_regs.bc > length) {
            net_mark_closed();
            return;
        }
        sent = spxn_regs.bc;
        if (!sent) {
            if (!--zero_budget) { net_mark_closed(); return; }
            frame_wait();
            continue;
        }
        next += sent;
        length -= sent;
    }
}

void net_send_byte(uint8_t value) __z88dk_fastcall
{
    net_send_block(&value, 1);
}

void net_send_string(const char *text) __z88dk_fastcall
{
    net_send_block(text, st_strlen(text));
}

void net_send_crlf(void)
{
    static const char crlf[] = "\r\n";
    net_send_block(crlf, 2);
}

void net_send_line(const char *text) __z88dk_fastcall
{
    net_send_string(text);
    net_send_crlf();
}

uint8_t net_init(void)
{
    uint8_t ip4host[4];
    uint8_t has_ip;

    connection_state = STATE_DISCONNECTED;
    if (spxn_rom_detect() != 1) return 0;
    spxn_regs.a = 0;
    spxn_regs.de = (uint16_t)(uintptr_t)ip4host;
    if (net_rom_failed(spxn_rom_ixcall(ROM_SPECTRANEXT))) return 0;

    has_ip = ip4host[0] | ip4host[1] | ip4host[2] | ip4host[3];
    if (has_ip) connection_state = STATE_WIFI_OK;
    return 1;
}

void net_prepare(uint8_t secure) __z88dk_fastcall
{
    (void)secure;
}

uint8_t net_connect(const char *host, const char *port,
                    uint8_t secure) __z88dk_callee
{
    uint8_t ip4be[4];
    uint16_t number;

    if (secure) return NET_CONNECT_ERROR; /* Cart TLS is fixed to port 443. */
    number = str_to_u16(port);
    if (!number || number == 22u || number == 443u) return NET_CONNECT_ERROR;
    if (spxn_resolve(host, ip4be) != SPXN_OK) return NET_CONNECT_DNS_FAILED;

    spxn_regs.bc = SOCK_STREAM;
    if (net_rom_failed(spxn_rom_hlcall(ROM_SOCKET))) return NET_CONNECT_ERROR;
    net_fd = spxn_regs.a;
    spxn_regs.a = net_fd;
    spxn_regs.de = (uint16_t)(uintptr_t)ip4be;
    spxn_regs.bc = number;
    if (net_rom_failed(spxn_rom_hlcall(ROM_CONNECT))) {
        spxn_regs.a = net_fd;
        (void)spxn_rom_hlcall(ROM_CLOSE);
        return NET_CONNECT_REFUSED;
    }
    net_open = 1;
    net_poll_in = 0;
    net_hup_pending = 0;
    return NET_CONNECT_OK;
}

void net_close(void)
{
    if (net_open) {
        spxn_regs.a = net_fd;
        (void)spxn_rom_hlcall(ROM_CLOSE);
    }
    net_open = 0;
    net_poll_in = 0;
    net_hup_pending = 0;
}

static int16_t net_poll(void)
{
    uint8_t flags;

    if (!net_open) return SPXN_EBADSTATE;
    net_poll_in = 0;
    spxn_regs.a = net_fd;
    flags = spxn_rom_hlcall(ROM_POLLFD);
    if (net_rom_failed(flags)) return SPXN_EROM;
    if (flags & ROM_ZERO) return 0;
    if ((uint8_t)spxn_regs.bc & SPXN_POLLIN) net_poll_in = 1;
    return (uint8_t)spxn_regs.bc;
}

static int16_t net_recv(void *buffer, uint16_t maximum)
{
    if (!net_open || !net_poll_in) return SPXN_EBADSTATE;
    net_poll_in = 0;
    spxn_regs.a = net_fd;
    spxn_regs.de = (uint16_t)(uintptr_t)buffer;
    spxn_regs.bc = maximum;
    if (net_rom_failed(spxn_rom_hlcall(ROM_RECV))) return SPXN_EROM;
    if (spxn_regs.bc > maximum) return SPXN_EPROTO;
    return (int16_t)spxn_regs.bc;
}

void net_pump_rx(void)
{
    int16_t flags;
    uint16_t free;
    uint16_t contiguous;
    int16_t received;

    if (connection_state < STATE_TCP_CONNECTED) return;
    flags = net_poll();
    if (flags < 0) {
        net_mark_closed();
        net_publish_closed();
        return;
    }
    if (flags & (SPXN_POLLHUP | SPXN_POLLNVAL)) net_mark_closed();
    if (!(flags & SPXN_POLLIN)) {
        net_publish_closed();
        return;
    }

    free = (uint16_t)(rb_tail - rb_head - 1u) & RING_BUFFER_MASK;
    if (!free) return; /* Backpressure: no socket byte was consumed or lost. */
    contiguous = RING_BUFFER_SIZE - rb_head;
    if (contiguous > free) contiguous = free;
    if (contiguous > NET_RECV_CHUNK) contiguous = NET_RECV_CHUNK;
    received = net_recv(ring_buffer + rb_head, contiguous);
    if (received > 0)
        rb_head = (rb_head + (uint16_t)received) & RING_BUFFER_MASK;
    else if (received < 0)
        net_mark_closed();
    net_publish_closed();
}

void net_frame_wait(void)
{
    frame_wait();
    net_pump_rx();
}

void spectranext_about_pump(void)
{
    uint8_t budget = 4;

    while (budget--) {
        uint8_t byte;
        int16_t flags = net_poll();
        int16_t received;

        if (flags < 0) { net_mark_closed(); return; }
        if (flags & (SPXN_POLLHUP | SPXN_POLLNVAL)) net_mark_closed();
        if (!(flags & SPXN_POLLIN)) return;
        received = net_recv(&byte, 1);
        if (received != 1) return;
        if (byte == '\r') continue;
        if (byte == '\n') {
            if (rx_overflow) {
                rx_overflow = 0;
            } else if (rx_pos) {
                rx_line[rx_pos] = 0;
                rx_last_len = rx_pos;
                parse_irc_message(rx_line);
            }
            rx_pos = 0;
            return;
        } else if (rx_pos < RX_LINE_SIZE - 2u) {
            rx_line[rx_pos++] = (char)byte;
        } else {
            rx_overflow = 1;
        }
    }
}
