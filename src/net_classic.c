/* Classic divMMC UART + ESP-AT network backend. */

#include "../include/spectalk.h"

static uint8_t classic_wait_connect(uint16_t max_frames) __z88dk_fastcall
{
    uint16_t frames = 0;

    rx_pos = 0;
    while (frames < max_frames) {
        uint16_t h2;

        if (uart_tx_failed) return NET_CONNECT_ERROR;

        frame_wait_drain();
        frames++;
        if (in_inkey() == KEY_BREAK) return NET_CONNECT_CANCELLED;
        if (!try_read_line_nodrain()) continue;
        if (rx_last_len < 2) {
            rx_pos = 0;
            continue;
        }

        h2 = *(uint16_t *)rx_line;
        if ((h2 == 0x4F43 && rx_last_len == 7) ||
            h2 == 0x4C41 || h2 == 0x4B4F) {
            rx_pos = 0;
            return NET_CONNECT_OK;
        }
        if (h2 == 0x4E44) { rx_pos = 0; return NET_CONNECT_DNS_FAILED; }
        if (h2 == 0x4C43 || h2 == 0x6F63) {
            rx_pos = 0;
            return NET_CONNECT_REFUSED;
        }
        if (h2 == 0x5245) { rx_pos = 0; return NET_CONNECT_ERROR; }
        rx_pos = 0;
    }
    return NET_CONNECT_TIMEOUT;
}

void classic_net_prepare(uint8_t secure) __z88dk_fastcall
{
    esp_at_cmd(S_AT_CIPMUX0);
    esp_at_cmd(S_AT_CIPSERVER0);
    esp_at_cmd("AT+CIPDINFO=0");
    if (secure) esp_at_cmd("AT+CIPSSLSIZE=4096");
}

uint8_t classic_net_connect(const char *host, const char *port,
                            uint8_t secure) __z88dk_callee
{
    wait_drain(20);
    flush_all_rx_buffers();
    uart_send_string("AT+CIPSTART=\"");
    uart_send_string(secure ? "SSL" : S_TCP);
    uart_send_string("\",\"");
    uart_send_string(host);
    uart_send_string("\",");
    uart_send_line(port);

    return classic_wait_connect(secure ? TIMEOUT_SSL : TIMEOUT_DNS);
}

uint8_t classic_net_start_stream(void)
{
    wait_drain(20);
    rb_tail = rb_head;
    rx_pos = 0;

    uart_send_line("AT+CIPMODE=1");
    if (!wait_for_response(S_OK, 100)) return NET_STREAM_MODE_FAILED;

    wait_drain(20);
    uart_send_string("AT+CIPSEND\r\n");
    if (!wait_for_prompt_char('>', TIMEOUT_PROMPT)) {
        return NET_STREAM_PROMPT_FAILED;
    }
    return NET_STREAM_OK;
}

void classic_net_close(void)
{
    uint8_t i;

    if (uart_tx_failed) return; /* A partial command must not be retried. */

    if (connection_state >= STATE_TCP_CONNECTED) {
        for (i = 0; i < 65; i++) { frame_wait(); flush_all_rx_buffers(); }
        ay_uart_send('+'); ay_uart_send('+'); ay_uart_send('+');
        for (i = 0; i < 55; i++) { frame_wait(); flush_all_rx_buffers(); }
    }

    uart_send_line(S_AT_CIPCLOSE);
    (void)wait_for_response(S_OK, 50);
    uart_send_line(S_AT_CIPMODE0);
    (void)wait_for_response(S_OK, 50);
}
