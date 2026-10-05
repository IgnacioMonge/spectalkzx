/*
 * spectalk.h - Common header for SpecTalk ZX modular build
 * SpecTalk ZX - IRC Client for ZX Spectrum
 * Copyright (C) 2026 M. Ignacio Monge Garcia
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <https://www.gnu.org/licenses/>.
 */

#ifndef SPECTALK_H
#define SPECTALK_H

#include <string.h>
#include <stdint.h>
#include <input.h>
#include <arch/zx.h>
#include "spectalk_contract.h"

// =============================================================================
// SDCC COMPATIBILITY
// =============================================================================
#ifdef __SDCC
#define ST_NAKED __naked
#pragma disable_warning 110
#else
#define ST_NAKED
#endif

// =============================================================================
// SCREEN LAYOUT CONSTANTS
// =============================================================================
#define SCREEN_COLS     64
#define MAIN_START        3
#define MAIN_LINES        17
#define MAIN_END          (MAIN_START + MAIN_LINES - 1)
#define INFO_LINE         21
#define INPUT_START       22
#define INPUT_LINES       2
#define INPUT_END         (INPUT_START + INPUT_LINES - 1)

// =============================================================================
// KEY CODES
// =============================================================================
#define KEY_UP        11
#define KEY_DOWN      10
#define KEY_LEFT      8
#define KEY_RIGHT     9
#define KEY_BACKSPACE 12
#define KEY_ENTER     13
#define KEY_BREAK     3

#define AUTOJOIN_IDENT_GRACE_FRAMES 250

// =============================================================================
// CHANNEL/WINDOW MANAGEMENT
// =============================================================================
#define NAV_HIST_SIZE 6
#define IS_CHAN_PREFIX(c) ((c) == '#' || (c) == '&')

typedef struct {
    char name[22];           // Channel name "#retro" or query nick or "Server"
    char mode[6];            // Channel mode (e.g. "+nt") - only for channels
    uint16_t user_count;     // Number of users - only for channels
    uint8_t flags;           // CH_FLAG_ACTIVE | CH_FLAG_QUERY | CH_FLAG_UNREAD | ...
    uint8_t _pad;            // Padding para alinear a 32 bytes (i*32 = shift)
} ChannelInfo;               // TOTAL: 32 bytes (potencia de 2)

// =============================================================================
// IRC PARSING
// =============================================================================
#define IRC_MAX_PARAMS 10

// Search modes
#define SEARCH_NONE   0
#define SEARCH_CHAN   1
#define SEARCH_USER   2

// Pending search types (para evitar mezcla de resultados)
#define PEND_NONE         0
#define PEND_LIST         1
#define PEND_WHO          2
#define PEND_SEARCH_CHAN  3
#define PEND_SEARCH_USER  4

// =============================================================================
// TIMEOUTS (frames, HALT-based)
// =============================================================================
// Exported because user_cmds.c uses them when driving the ESP AT transport.
#define TIMEOUT_DNS     400
#define TIMEOUT_SSL    1200
#define TIMEOUT_PROMPT  250

// Pagination
#define PAGINATION_MAX_COUNT 60000  // Límite de seguridad para evitar overflow

// Names timeout
#define NAMES_TIMEOUT_FRAMES 500

// =============================================================================
// DRAIN LIMITS
// =============================================================================
#ifdef SPECTALK_NEXT
// No CTS on the internal ESP: service a full burst at each resident drain.
#define DRAIN_NORMAL    0     // ASM maps zero to the bounded 255-byte budget
#else
#define DRAIN_NORMAL    32
#endif
#define RX_TICK_PARSE_BYTE_BUDGET 512   // Reduced from 1024 to prevent keyboard lag during JOIN bursts

// Buffer pressure thresholds
#define BUFFER_PRESSURE_THRESHOLD (RING_BUFFER_SIZE * 3 / 4)  // 1536 bytes = 75%
#define BUFFER_CRITICAL_MARGIN 128  // Reserve 128 bytes before full

// =============================================================================
// FRAME MACRO
// =============================================================================
// Wait for next frame (50Hz sync via IM1 ROM ISR: ei;halt;di).
extern void frame_wait(void);
extern void frame_wait_drain(void);
extern void fatal_msg(const char *msg) __z88dk_fastcall;  // never returns

// =============================================================================
// EXTERNAL ASM FUNCTIONS (spectalk_asm.asm)
// =============================================================================
extern void set_border(uint8_t color) __z88dk_fastcall;
extern char *skip_spaces(char *p) __z88dk_fastcall;

extern void mention_beep(void);
extern void key_click(void);
extern void check_caps_toggle(void);
void badge_flash_on(void);
void badge_flash_off(void);
extern uint8_t key_shift_held(void);
extern void input_cache_invalidate(void);
extern void print_str64_char(uint8_t ch) __z88dk_fastcall;
extern void print_line64_fast(uint8_t y, const char *s, uint8_t attr);
extern uint8_t plf_start_byte;
extern void print_status_left54_fast(const char *s) __z88dk_fastcall;
extern void notif_draw(uint8_t start_col, const char *str, uint8_t attr);
extern void ikkle_draw(uint8_t y, uint8_t start_col, const char *str, uint8_t attr);
extern void notif_clear(void);
void notif_center(const char *str, uint8_t attr);
void notif_cancel_current(void);
extern uint16_t notif_timeout;
extern uint8_t notif_is_pm;
extern char last_pm_nick[];
extern void redraw_input_asm(void);
extern uint8_t overlay_slot[];
extern uint8_t help_page;
extern uint8_t config_dirty;
extern uint8_t notif_enabled;
void notify(const char *msg, uint8_t attr) __z88dk_callee;
void overlay_exec(uint8_t ovl_id, uint8_t entry_id) __z88dk_callee;
void overlay_call(uint8_t entry_id) __z88dk_fastcall;
void overlay_call_timed(uint8_t entry_id) __z88dk_fastcall;
void cmd_save(const char *args) __z88dk_fastcall;
uint8_t overlay_header(const char *title) __z88dk_fastcall;
extern void draw_indicator(uint8_t y, uint8_t phys_x, uint8_t attr);
extern void clear_line(uint8_t y, uint8_t attr) __z88dk_callee;
extern void clear_zone(uint8_t start, uint8_t lines, uint8_t attr) __z88dk_callee;
// Compute screen row base: H = 0x40|(y&0x18), L = (y&7)<<5
#define SCREEN_ROW_ADDR(y) ((uint16_t)(((0x40 | ((y) & 0x18)) << 8) | (((y) & 7) << 5)))
extern int st_stricmp(const char *a, const char *b) __z88dk_callee;
extern const char* st_stristr(const char *hay, const char *needle) __z88dk_callee;
extern uint8_t st_strlen(const char *s) __z88dk_fastcall;
extern char* u16_to_dec(char *dst, uint16_t v) __z88dk_callee;
extern uint16_t str_to_u16(const char *s) __z88dk_fastcall;
extern void st_copy_n(char *dst, const char *src, uint8_t max_len);
extern void uart_send_string(const char *s) __z88dk_fastcall;
extern int16_t rb_pop(void);

extern uint8_t try_read_line_nodrain(void);

// =============================================================================
// divMMC UART backend (legacy ay_uart_* symbol names)
// =============================================================================
extern void     ay_uart_init(void);
extern void     ay_uart_send(uint8_t byte) __z88dk_fastcall;
#ifdef SPECTALK_SPECTRANEXT
#define uart_tx_failed 0
#else
extern uint8_t uart_tx_failed; /* Sticky failure: reset ESP and restart client. */
#endif

#include "spectalk_net.h"
#include "spectalk_clock.h"

// =============================================================================
// GLOBAL variables (defined in spectalk.c)
// =============================================================================

// Ring buffer
extern uint8_t ring_buffer[];
extern uint16_t rb_head;
extern uint16_t rb_tail;

// Connection state
extern char irc_server[IRC_SERVER_SIZE];
extern char irc_port[IRC_PORT_SIZE];
extern char irc_nick[IRC_NICK_SIZE];
extern uint8_t irc_is_away;
extern uint8_t ping_latency;
extern char away_message[32];
extern uint8_t away_reply_cd;
extern uint8_t autoaway_minutes;
extern uint16_t autoaway_counter;
extern uint8_t autoaway_active;
extern uint8_t beep_enabled;
extern uint8_t keyclick_enabled;
extern uint8_t has_esxdos;
extern uint8_t nick_color_mode;
extern uint8_t show_traffic;
extern uint8_t show_channel_separators;
extern int8_t sntp_tz;
extern int8_t sntp_tz_last;
extern char irc_pass[IRC_PASS_SIZE];
extern char nickserv_pass[AUTH_COMMAND_SIZE];
extern char nickserv_nick[AUTH_SERVICE_SIZE];
extern uint8_t auth_mode;
extern uint8_t auth_profile;
extern char user_mode[USER_MODE_SIZE];
extern char network_name[NETWORK_NAME_SIZE];
extern uint8_t connection_state;

// UI/time state (defined in spectalk.c)
extern uint8_t cursor_visible;
extern uint8_t time_hour;
extern uint8_t time_minute;
extern uint8_t time_second;
extern uint8_t sntp_waiting;
extern uint8_t sntp_init_sent;
extern uint8_t sntp_queried;
extern uint8_t closed_reported;
extern uint8_t disconnecting_in_progress;  // FIX: Prevent reentrant disconnection

// Main text cursor position (shared with command handlers)
extern uint8_t main_line;
extern uint8_t main_col;
extern uint8_t wrap_indent;  // Indentación para líneas que continúan
extern uint8_t deferred_wrap_active;

// Channels
extern ChannelInfo channels[];
extern uint8_t current_channel_idx;
extern ChannelInfo *cur_chan_ptr;
extern uint8_t channel_count;

// Navigation history
extern uint8_t nav_history[];
extern uint8_t nav_hist_ptr;

// Ignore list
extern char ignore_list[][16];
extern uint8_t ignore_count;

// Theme attributes array — indices match the runtime theme_attrs[] layout
extern uint8_t theme_attrs[20];
#define ATTR_BANNER     theme_attrs[0]
#define ATTR_STATUS     theme_attrs[1]
#define ATTR_MSG_CHAN   theme_attrs[2]
#define ATTR_MSG_SELF   theme_attrs[3]
#define ATTR_MSG_PRIV   theme_attrs[4]
#define ATTR_MAIN_BG    theme_attrs[5]
#define ATTR_INPUT      theme_attrs[6]
#define ATTR_PROMPT     theme_attrs[8]
#define ATTR_MSG_SERVER theme_attrs[9]
#define ATTR_MSG_JOIN   theme_attrs[10]
#define ATTR_MSG_NICK   theme_attrs[11]
#define ATTR_MSG_TIME   theme_attrs[12]
#define ATTR_MSG_TOPIC  theme_attrs[13]
#define ATTR_MSG_MOTD   theme_attrs[14]

// =============================================================================
// CROSS-MODULE FUNCTIONS (defined in spectalk.c)
// =============================================================================
extern void main_print_time_prefix(void);
extern void reset_all_channels(void);
extern void send_identify(const char *pass) __z88dk_fastcall;
void sntp_process_response(const char *line) __z88dk_fastcall;
#define ATTR_ERROR      theme_attrs[15]
#define STATUS_RED      theme_attrs[16]
#define STATUS_YELLOW   theme_attrs[17]
#define STATUS_GREEN    theme_attrs[18]
#define BORDER_COLOR    theme_attrs[19]
extern uint8_t current_theme;

#define ATTR_MSG_SYS ATTR_MSG_SERVER
// Attribute setter helpers (ASM, save 3 bytes per call vs inline)
void set_attr_sys(void);
void set_attr_err(void);
void set_attr_priv(void);
void set_attr_chan(void);
void set_attr_nick(void);
void set_attr_join(void);
void set_nick_color(const char *nick) __z88dk_fastcall;

// Current attribute for main_print
extern uint8_t current_attr;

// UI state
extern uint8_t status_bar_dirty;
extern uint8_t force_status_redraw;
extern uint8_t other_channel_activity;
extern uint8_t bookmark_active_slot;

// Names tracking
extern uint8_t names_pending;
extern uint16_t names_timeout_frames;
extern char names_target_channel[NAMES_TARGET_CHANNEL_SIZE];
extern uint8_t counting_new_users;
extern uint16_t names_count_acc;
extern uint8_t show_names_list;
extern uint8_t names_was_manual;
void names_print_summary(uint8_t incomplete) __z88dk_fastcall;
void names_finish_incomplete(void);


// Keep-alive system
extern uint16_t server_silence_frames;
extern uint8_t  keepalive_ping_sent;
extern uint16_t keepalive_timeout;
extern uint8_t count_sync_enabled;
extern uint8_t count_sync_idle_frames;
extern uint8_t count_sync_quits;

// Pagination
extern uint8_t pagination_active;
extern uint8_t pagination_lines;
extern uint8_t search_data_lost;
extern uint8_t buffer_pressure;
extern uint16_t pagination_count;
extern uint8_t pagination_timeout;

// Search
extern uint8_t search_mode;
extern uint8_t search_flush_state;    // 0=idle, 1=draining, 2=command sent
extern uint8_t search_header_rcvd;    // Flag: server sent 321/352 (not rate-limited)
extern uint8_t search_saw_server_notice; // Flag: server NOTICE during search (rate limit)
extern uint8_t post_cancel_quiet;        // Countdown post-cancel to suppress h_default_cmd
extern char search_pattern[SEARCH_PATTERN_SIZE];
extern uint16_t search_index;

// Search functions
void cancel_search_state(void);
void start_pagination(void);
void start_search_command(uint8_t type, const char *arg) __z88dk_callee;

// Timestamps
extern uint8_t show_timestamps;
extern uint8_t last_ts_hour;
extern uint8_t last_ts_minute;
extern uint8_t autojoin;
extern uint8_t autojoin_defer_flags;
extern uint8_t autojoin_ident_grace;
extern char autojoin_channels[SEARCH_PATTERN_SIZE];

// IRC parsing
extern char *irc_params[IRC_MAX_PARAMS];
extern uint8_t irc_param_count;

// Input buffers
extern char line_buffer[LINE_BUFFER_SIZE];
extern uint8_t line_len;
extern uint8_t cursor_pos;
extern char temp_input[LINE_BUFFER_SIZE];
// tx_buffer eliminado - se usa uart_send_string directo

// RX line buffer
extern char rx_line[RX_LINE_SIZE];
extern uint16_t rx_pos;
extern uint16_t rx_last_len;
extern uint8_t rx_overflow;  // Flag: overflow detected (0 or 1)
extern void reset_rx_state(void);  // Zeros rb_head/rb_tail/rx_pos/rx_overflow
extern void overlay_rx_release(void); // Preserve stream resynchronization on exit

// UART drain
extern uint8_t uart_drain_limit;


// Print context (used by ASM)
extern volatile uint8_t g_ps64_y;
extern volatile uint8_t g_ps64_col;
extern volatile uint8_t g_ps64_attr;

// Caps lock
extern uint8_t caps_lock_mode;
extern uint8_t caps_latch;

// Input cache
extern uint8_t input_cache_char[][SCREEN_COLS];

// =============================================================================
// COMMON STRINGS (save ROM by sharing)
// =============================================================================
extern const char S_NOTCONN[];
extern const char S_OK[];
extern const char S_FAIL[];
extern const char S_SERVER[];
extern const char S_CHANSERV[];
extern const char S_NOTSET[];
extern const char S_DISCONN[];
extern const char S_NICKSERV[];
extern const char S_APPNAME[];
extern const char S_APPSHORT[];
extern const char S_APPDESC[];
extern const char S_COPYRIGHT[];
extern const char S_MAXWIN[];
extern const char S_PRIVMSG[];
extern const char S_NOTICE[];
extern const char S_TIMEOUT[];
extern const char S_NOWIN[];
extern const char S_CANCELLED[];
extern const char S_RANGE_MINUTES[];
extern const char S_MUST_CHAN[];
extern const char S_ARROW_IN[];
extern const char S_ARROW_OUT[];
extern const char S_EMPTY_PAT[];
// S_CRLF removed — dead code
extern const char S_ASTERISK[];
extern const char S_COLON_SP[];
extern const char S_SP_COLON[];
extern const char S_SP_PAREN[];
extern const char S_AT_CIPCLOSE[];
extern const char S_AT_CIPMODE0[];
extern const char S_AT_CIPMUX0[];
extern const char S_AT_CIPSERVER0[];
extern const char S_PROMPT[];
extern const char S_CAP_END[];
extern const char S_GLOBAL[];
extern const char S_TOPIC_PFX[];
extern const char S_CONN_REFUSED[];
extern const char S_INIT_DOTS[];
extern const char S_ACTION[];
extern const char S_PONG[];
// OPT-AGG: Nuevas constantes compartidas
extern const char S_DOTS3[];
extern const char S_NICK_INUSE[];
extern const char S_NICK_SP[];
extern const char S_AS_SP[];
extern const char S_MIN[];
extern const char S_DOT_SP[];       // D9: ". " dedup
extern const char S_USAGE_MSG[];    // D9: "msg nick message" dedup
extern const char S_IDENTIFY_CMD[]; // D10: " :IDENTIFY "
extern const char S_JOINED_SP[];    // D10: " joined "
extern const char S_AWAY_CMD[];     // D10: "AWAY"
extern const char S_NICK_CMD[];     // D10: "NICK"
extern const char S_SMART[];        // D10: "smart"
extern const char S_AT_CMD[];
extern const char S_JOIN_CMD[];
extern const char S_PART_CMD[];     // D19: "PART"
extern const char S_TCP[];          // D19: "TCP"
extern const char S_AUTOAWAY[];     // D11: "Auto-away"
extern const char S_ALREADY[];      // S2: "Already in "
extern const char S_YOU_LEFT[];
extern const char S_MODE_SP_SCR[];     // S3: "You have left "
extern const char S_IN_SP[];
extern const char S_QUIT_SUFFIX[];
extern const char S_SP_LBRACKET[];
extern const char S_CHANNEL_WORD[];
extern const char S_CLOSED_SP[];

// =============================================================================
// UI MACROS
// =============================================================================
void ui_err(const char *s) __z88dk_fastcall;
void ui_sys(const char *s) __z88dk_fastcall;
void ui_usage(const char *a) __z88dk_fastcall;
// OPT-SHRINK-P1: dedup switch+notify pattern (4 call sites)
void switch_or_notify(uint8_t idx) __z88dk_fastcall;

#define ERR_NOTCONN() ui_err(S_NOTCONN)
#define SYS_PUTS(s)   do { set_attr_sys(); main_puts(s); } while(0)

// Compatibility macros (cur_chan_ptr avoids idx*32 multiply per access)
#define irc_channel (cur_chan_ptr->name)
#define chan_mode (cur_chan_ptr->mode)
#define chan_user_count (cur_chan_ptr->user_count)
#define chan_flags (cur_chan_ptr->flags)

// =============================================================================
// FUNCTION DECLARATIONS - UI (spectalk.c)
// =============================================================================
void main_print(const char *s) __z88dk_fastcall;
void main_print_wrapped_ram(char *s) __z88dk_fastcall;
void main_print_wrapped_clean(char *s) __z88dk_fastcall;
void deferred_wrap_start(char *s) __z88dk_fastcall;
void main_puts(const char *s) __z88dk_fastcall;
void main_puts2(const char *a, const char *b) __z88dk_callee;
// OPT-P2-A: main_puts3 eliminated (single call site inlined)
void main_putc(char c) __z88dk_fastcall;
void main_newline(void);
void main_hline(void);
void utf8_to_ascii(char *s) __z88dk_fastcall;  // UTF-8 + IRC control cleanup
void print_char64(uint8_t y, uint8_t col, uint8_t c, uint8_t attr) __z88dk_callee;
void print_str64(uint8_t y, uint8_t col, const char *s, uint8_t attr) __z88dk_callee;
void print_big_str(uint8_t y, uint8_t col, const char *s, uint8_t attr) __z88dk_callee;

extern uint8_t overlay_mode;
void draw_status_bar(void);
void clear_main(void);
uint8_t bpe_validate(void);
void overlay_exit_full(void);  // OPT-SHRINK-R01: common overlay exit sequence (ASM)
void redraw_input_full(void);
void reapply_screen_attributes(void);
void cls_fast(void);
void draw_status_bar_real(void);
void fast_u8_to_str(char *buf, uint8_t val) __z88dk_callee;

// Frameless ASM callee functions (spectalk_asm.asm)
void sys_puts_print(const char *label, const char *value) __z88dk_callee;
uint8_t ensure_args(const char *args, const char *usage) __z88dk_callee;
void puts_u8_nolz(uint8_t v) __z88dk_fastcall;
char *sb_put_u8_2d(char *p, uint8_t v) __z88dk_callee;

// =============================================================================
// FUNCTION DECLARATIONS - CHANNEL MANAGEMENT (spectalk.c)
// =============================================================================
int8_t find_channel(const char *name) __z88dk_fastcall;
int8_t find_query(const char *nick) __z88dk_fastcall;
int8_t find_empty_channel_slot(void);
int8_t add_channel(const char *name) __z88dk_fastcall;
uint8_t snapshot_autojoin_channels(void);
int8_t add_query(const char *nick) __z88dk_fastcall;
void remove_channel(uint8_t idx) __z88dk_fastcall;
void switch_to_channel(uint8_t idx) __z88dk_fastcall;
// Channel switcher is state-based (internal to spectalk.c)
void nav_push(uint8_t idx) __z88dk_fastcall;
void nav_fix_on_delete(uint8_t deleted_idx) __z88dk_fastcall;

// =============================================================================
// FUNCTION DECLARATIONS - IGNORE LIST (spectalk.c)
// =============================================================================
uint8_t is_ignored(const char *nick) __z88dk_fastcall;
uint8_t add_ignore(const char *nick) __z88dk_fastcall;
uint8_t remove_ignore(const char *nick) __z88dk_fastcall;

// =============================================================================
// FUNCTION DECLARATIONS - IRC PARAMS (spectalk.c)
// =============================================================================
void tokenize_params(char *par) __z88dk_fastcall;
const char* irc_param(uint8_t idx) __z88dk_fastcall;
void irc_params_ensure(void);
extern uint8_t irc_params_dirty;

// =============================================================================
// FUNCTION DECLARATIONS - UART/TRANSPORT (spectalk.c)
// =============================================================================
void uart_drain_to_buffer(void);
void wait_drain(uint8_t frames) __z88dk_fastcall;
void flush_all_rx_buffers(void);
void uart_send_crlf(void) __z88dk_fastcall;
void uart_send_line(const char *s) __z88dk_fastcall;

// AT response helpers (spectalk.c)
uint8_t wait_for_response(const char *expected, uint16_t max_frames) __z88dk_callee;
uint8_t wait_for_prompt_char(uint8_t prompt_ch, uint16_t max_frames) __z88dk_callee;
uint8_t esp_at_cmd(const char *cmd) __z88dk_fastcall;

// =============================================================================
// FUNCTION DECLARATIONS - IRC SEND (spectalk.c)
// =============================================================================
// irc_send_raw eliminado - se usa uart_send_string directo
void irc_send_pong(const char *token) __z88dk_fastcall;
void irc_send_cmd1(const char *cmd, const char *p1) __z88dk_callee;
void irc_send_cmd2(const char *cmd, const char *p1, const char *p2) __z88dk_callee;
void irc_send_privmsg(const char *target, const char *msg) __z88dk_callee;
void irc_check_friends_online(void);
// OPT-P2-B: Shared nick-in-use retry logic (used by h_numeric_433 and cmd_connect)
void nick_try_alternate(void);

extern char friend_nicks[MAX_FRIENDS][IRC_NICK_SIZE];
extern uint8_t friends_ison_sent;
extern uint8_t friend_count;

// =============================================================================
// FUNCTION DECLARATIONS - IRC HANDLERS (irc_handlers.c)
// =============================================================================
void parse_irc_message(char *line) __z88dk_fastcall;
void process_irc_data(void);

// =============================================================================
// FUNCTION DECLARATIONS - USER COMMANDS (user_cmds.c)
// =============================================================================
void parse_user_input(char *line) __z88dk_fastcall;
void bookmark_selector_key(uint8_t c) __z88dk_fastcall;

// =============================================================================
// FUNCTION DECLARATIONS - MISC (spectalk.c)
// =============================================================================
void force_disconnect(void);
void apply_theme(void);
void init_screen(void);
uint8_t esp_init(void);
void draw_banner(void);

// Configuration file (esxDOS)
uint8_t config_load(void);

// esxDOS detection and file I/O (ASM in spectalk_asm.asm)
extern uint8_t esx_detect(void);
extern void esx_fopen(const char *path) __z88dk_fastcall;
extern void esx_fcreate(const char *path) __z88dk_fastcall;
extern void esx_fread(void);
extern void esx_fwrite(void);
extern uint8_t esx_fclose(void);
extern void esx_funlink(const char *path) __z88dk_fastcall;
extern uint8_t esx_replace_write(const char *path) __z88dk_fastcall;
#ifdef SPECTALK_SPECTRANEXT
extern void esx_freplace(const char *path) __z88dk_fastcall;
extern void esx_opendir(const char *path) __z88dk_fastcall;
extern void esx_mkdir(const char *path) __z88dk_fastcall;
extern void esx_commit(const char *path) __z88dk_fastcall;
#endif
extern uint8_t  esx_handle;
extern uint16_t esx_buf;
extern uint16_t esx_count;
extern uint16_t esx_result;
#if defined(SPECTALK_NEXT) || defined(SPECTALK_SPECTRANEXT)
extern void dat_open(void);
#endif
#ifdef SPECTALK_NEXT
extern void dat_fread(void);
extern uint8_t dat_fseek_set(uint16_t offset) __z88dk_fastcall;
#endif

#endif // SPECTALK_H
