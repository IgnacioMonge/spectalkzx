#ifndef SPECTALK_NET_H
#define SPECTALK_NET_H

#include <stdint.h>

/* Target-neutral IRC stream and lifecycle surface. */
#ifdef SPECTALK_SPECTRANEXT

void net_send_byte(uint8_t value) __z88dk_fastcall;
void net_send_string(const char *text) __z88dk_fastcall;
void net_send_crlf(void);
void net_send_line(const char *text) __z88dk_fastcall;
void net_pump_rx(void);
void net_frame_wait(void);

#else

/* Classic resolves the stream names directly to the UART implementation. */
#define net_send_byte   ay_uart_send
#define net_send_string uart_send_string
#define net_send_crlf   uart_send_crlf
#define net_send_line   uart_send_line

#endif

/* Classic lifecycle/RX backend. Session and protocol code use only the
 * target-neutral names below; a later target binds the same surface to the
 * Spectranext socket adapter at compile time. */
#define NET_CONNECT_OK          1
#define NET_CONNECT_CANCELLED   2
#define NET_CONNECT_DNS_FAILED  3
#define NET_CONNECT_REFUSED     4
#define NET_CONNECT_ERROR       5
#define NET_CONNECT_TIMEOUT     6

#define NET_STREAM_OK            1
#define NET_STREAM_MODE_FAILED   2
#define NET_STREAM_PROMPT_FAILED 3

#ifdef SPECTALK_SPECTRANEXT

uint8_t net_init(void);
void net_prepare(uint8_t secure) __z88dk_fastcall;
uint8_t net_connect(const char *host, const char *port,
                    uint8_t secure) __z88dk_callee;
#define net_start_stream() NET_STREAM_OK
void net_close(void);
void spectranext_about_pump(void);

#else

uint8_t classic_net_connect(const char *host, const char *port,
                            uint8_t secure) __z88dk_callee;
void classic_net_prepare(uint8_t secure) __z88dk_fastcall;
uint8_t classic_net_start_stream(void);
void classic_net_close(void);

#define net_connect      classic_net_connect
#define net_prepare      classic_net_prepare
#define net_start_stream classic_net_start_stream
#define net_close        classic_net_close
#define net_init         esp_init
#define net_pump_rx      uart_drain_to_buffer
#define net_frame_wait   frame_wait_drain

#endif

#define net_disconnect force_disconnect

#endif
