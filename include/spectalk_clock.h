#ifndef SPECTALK_CLOCK_H
#define SPECTALK_CLOCK_H

#include <stdint.h>

#ifdef SPECTALK_NEXT
/* Actual video cadence, scaled by 64 to retain fractional frame rates. */
uint16_t next_clock_second(void);
#endif

/* The application owns timezone/display/tick policy; the selected backend
 * owns only platform time acquisition and its transport pump. */
#ifdef SPECTALK_SPECTRANEXT

void clock_seed_local(void);
void clock_init(void);
void clock_query(void);
uint8_t clock_poll_rx(void);
void clock_sync_fallback(void);

#else

void classic_clock_init(void);
void classic_clock_query(void);
uint8_t classic_clock_poll_rx(void);
void sntp_udp_fallback(void);

#define clock_seed_local()   overlay_exec(4, 1)
#define clock_init           classic_clock_init
#define clock_query          classic_clock_query
#define clock_poll_rx        classic_clock_poll_rx
#define clock_sync_fallback  sntp_udp_fallback

#endif

/* Preserve the established public state ABI while removing SNTP-specific
 * names from application/session policy. */
#define clock_setup_state sntp_init_sent
#define clock_waiting     sntp_waiting
#define clock_synced      sntp_queried

#endif
