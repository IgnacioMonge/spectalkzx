/*
 * overlay_api.h — Minimal ABI for overlay C code
 * Declarations match the resident binary's actual prototypes.
 * Addresses resolved at link time via overlay_defs.asm (gen_overlay_defs.py).
 *
 * DO NOT include spectalk.h — this header is self-contained.
 */

#ifndef OVERLAY_API_H
#define OVERLAY_API_H

#include <stdint.h>
#include "../include/spectalk_contract.h"

/* ===== Resident wrappers ===== */

extern uint8_t overlay_header(const char *title) __z88dk_fastcall;

/* ===== Rendering primitives ===== */

extern void print_str64(uint8_t y, uint8_t col, const char *s, uint8_t attr)
    __z88dk_callee;
extern void print_char64(uint8_t y, uint8_t col, uint8_t c, uint8_t attr)
    __z88dk_callee;
extern void clear_line(uint8_t y, uint8_t attr) __z88dk_callee;
extern void print_big_str(uint8_t y, uint8_t col, const char *s, uint8_t attr)
    __z88dk_callee;
/* Uses IYL as scratch after saving IY: call only from DI overlay paths. */
extern void print_line64_fast(uint8_t y, const char *s, uint8_t attr);
extern void clear_zone(uint8_t start, uint8_t lines, uint8_t attr) __z88dk_callee;
extern void draw_badge_dither(uint8_t count) __z88dk_fastcall;
extern void notif_center(const char *str, uint8_t attr);
extern void input_cache_invalidate(void);
extern void main_putc(char c) __z88dk_fastcall;
extern void main_puts(const char *s) __z88dk_fastcall;
extern void main_print(const char *s) __z88dk_fastcall;
extern void main_newline(void);
extern void set_attr_sys(void);
extern void set_attr_priv(void);
extern void sys_puts_print(const char *label, const char *value) __z88dk_callee;
extern void notify(const char *msg, uint8_t attr) __z88dk_callee;
extern void notify2(const char *a, const char *b, uint8_t attr) __z88dk_callee;
extern void ui_err(const char *s) __z88dk_fastcall;
extern void ui_usage(const char *a) __z88dk_fastcall;
extern void overlay_rx_release(void);
extern const uint8_t ikkle_packed[];

/* ===== String/number utilities ===== */

extern char *skip_spaces(char *p) __z88dk_fastcall;
extern char *split_at_space(char *p) __z88dk_fastcall;
extern uint8_t st_strlen(const char *s) __z88dk_fastcall;
extern int st_stricmp(const char *a, const char *b) __z88dk_callee;
extern void st_copy_n(char *dst, const char *src, uint8_t max_len);
extern uint16_t str_to_u16(const char *s) __z88dk_fastcall;
extern char *u16_to_dec(char *dst, uint16_t v) __z88dk_callee;
extern void fast_u8_to_str(char *buf, uint8_t val) __z88dk_callee;
extern void puts_u8_nolz(uint8_t v) __z88dk_fastcall;

/* ===== esxDOS file I/O ===== */

extern void esx_fopen(const char *path) __z88dk_fastcall;
extern void esx_fcreate(const char *path) __z88dk_fastcall;
extern void esx_fread(void);
extern void esx_fwrite(void);
extern uint8_t esx_fclose(void);
extern uint8_t esx_replace_write(const char *path) __z88dk_fastcall;
extern void esx_funlink(const char *path) __z88dk_fastcall;
extern uint8_t esx_fseek_set(uint16_t offset) __z88dk_fastcall;

#if defined(SPECTALK_NEXT) || defined(SPECTALK_SPECTRANEXT)
extern void dat_open(void);
#define data_open() dat_open()
#else
#define data_open() esx_fopen(K_DAT)
#endif
#ifdef SPECTALK_NEXT
extern void dat_fread(void);
extern uint8_t dat_fseek_set(uint16_t offset) __z88dk_fastcall;
#define data_fread() dat_fread()
#define data_fseek_set(offset) dat_fseek_set(offset)
#define data_close() ((void)0)
#else
#define data_fread() esx_fread()
#define data_fseek_set(offset) esx_fseek_set(offset)
#define data_close() esx_fclose()
#endif

/* ===== Resident variables ===== */

/* esxDOS state */
extern uint8_t  esx_handle;
extern uint16_t esx_buf;
extern uint16_t esx_count;
extern uint16_t esx_result;

/* Overlay state */
extern uint8_t  overlay_mode;
extern uint8_t  help_page;
extern uint8_t  config_dirty;
extern uint8_t  notif_enabled;
extern uint8_t  status_bar_dirty;
extern uint8_t  bookmark_sel;
extern uint8_t  bookmark_active_slot;
extern uint8_t  bookmark_rows[];

/* Buffers */
extern uint8_t  ring_buffer[];    /* 2K staging/RX ring; Page B executes elsewhere */
extern uint8_t  overlay_slot[];   /* 512B scratch buffer (aliased to rx_line) */
extern uint16_t rx_last_len;

/* Theme */
extern uint8_t  theme_attrs[];
extern uint8_t  theme_raw[];      /* 75B: 3 themes x 25B, loaded from DAT */

/* Print cursor state (set by print_str64, used by cfg_item layout) */
extern volatile uint8_t g_ps64_y;
extern volatile uint8_t g_ps64_col;

/* Shared string constants from resident */
extern const char K_DAT[];
extern const char S_APPDESC[];
extern const char S_AUTOAWAY[];
extern const char S_SERVER[];
extern const char SB_MIN[];
extern const char SB_OFF[];
extern const char SB_ON[];
extern const char SB_RANGE_MINUTES[];
extern const char SB_SMART[];

/* === Config variables (read-only from overlay) === */
extern char     irc_nick[];
extern char     irc_server[];
extern char     irc_port[];
extern char     irc_pass[];
extern char     nickserv_pass[];
extern char     nickserv_nick[];
extern uint8_t  autojoin_defer_flags;
extern uint8_t  auth_mode;
extern uint8_t  auth_profile;
extern uint8_t  has_esxdos;
#ifndef SPECTALK_SPECTRANEXT
extern void cfg_apply(char *key, char *value) __z88dk_callee;
#endif
extern void send_identify(const char *pass) __z88dk_fastcall;
extern void irc_send_cmd2(const char *cmd, const char *target, const char *text) __z88dk_callee;
extern uint8_t  current_theme;
extern uint8_t  current_channel_idx;
extern uint8_t  channels[];
extern uint8_t  beep_enabled;
extern uint8_t  keyclick_enabled;
extern uint8_t  nick_color_mode;
extern uint8_t  show_traffic;
extern uint8_t  show_channel_separators;
extern uint8_t  count_sync_enabled;
extern uint8_t  count_sync_idle_frames;
extern uint8_t  count_sync_quits;
extern uint8_t  channel_context_next_row;
extern uint8_t  channel_context_pending;
extern uint8_t  show_timestamps;
extern uint8_t  autoconnect;
extern uint8_t  autojoin;
extern uint8_t  autoaway_minutes;
extern uint16_t autoaway_counter;
extern uint8_t  autoaway_active;
extern uint8_t  irc_is_away;
extern char     away_message[];
extern char     last_pm_nick[];
extern void irc_send_privmsg(const char *target, const char *msg) __z88dk_callee;
extern const char S_AWAY_CMD[];
extern void draw_status_bar(void);
extern uint8_t  connection_state;
extern int8_t   sntp_tz;
extern int8_t   sntp_tz_last;
extern uint8_t  sntp_init_sent;
extern uint8_t  sntp_waiting;
extern uint8_t  sntp_queried;
extern uint8_t  time_hour;
extern uint8_t  time_minute;
extern uint8_t  time_second;
extern uint8_t  last_ts_hour;
extern uint8_t  last_ts_minute;
extern uint8_t  last_frames_lo;
extern uint16_t tick_accum;
extern char     search_pattern[];
extern char     autojoin_channels[];
extern char     friend_nicks[][18];   /* MAX_FRIENDS(5) x IRC_NICK_SIZE(18) */
extern uint8_t  friend_count;
extern char     ignore_list[][16];
extern uint8_t  ignore_count;
extern uint8_t  add_ignore(const char *nick) __z88dk_fastcall;
extern uint8_t  remove_ignore(const char *nick) __z88dk_fastcall;
extern uint8_t  is_ignored(const char *nick) __z88dk_fastcall;

/* Shared config-key strings from resident core */
extern const char K_NICK[];
extern const char K_SERVER[];
extern const char K_PORT[];
extern const char K_PASS[];
extern const char K_NKPASS[];
extern const char K_AUTHCMD[];
extern const char K_BOOKMARK[];
extern const char K_NICKSERV[];
#ifdef SPECTALK_SPECTRANEXT
extern const char K_TZLAST[];
extern const char K_FRIENDS[];
extern const char K_IGNORES[];
#endif
extern const char K_AUTOCONN[];
extern const char K_AUTOJOIN[];
extern const char K_THEME[];
extern const char K_AUTOAWAY[];
extern const char K_BEEP[];
extern const char K_CLICK[];
extern const char K_NCOLOR[];
extern const char K_TRAFFIC[];
extern const char K_TS[];
extern const char K_DIVIDER[];
extern const char K_CHANNELS[];
extern const char K_CFG_PRI[];
extern const char K_CFG_ALT[];
extern const char K_TZ[];
extern const char K_NOTIF[];
extern const char K_COUNTSYNC[];
extern const char S_ANYKEY[];

/* ===== Layout constants ===== */
#define LINES_PER_PAGE  12
#define BPE_HELP_OFFSET 15147
#define WN_LOGO_OFFSET 14336
#define EARTH_FRAME0_OFFSET 595
#define EARTH_ATTR0_OFFSET 1182
#define EARTH_LOGO_OFFSET 1226
#define EARTH_DELTA_OFFSET 2048
#define EARTH_DELTA_SIZE 12288
#define EARTH_PACKET_SIZE 512
#define EARTH_FRAME_COUNT 24
#define EARTH_FRAME0_SIZE 587
#define EARTH_ATTR0_SIZE 44
#define EARTH_LOGO_SIZE 528
#define EARTH_LOGO_W_BYTES 22
#define EARTH_LOGO_H 24
#define EARTH_LOGO_ATTR_H 3
#define ATTR_MSG_SYS    theme_attrs[TATTR_MSG_SYS]

#endif /* OVERLAY_API_H */
