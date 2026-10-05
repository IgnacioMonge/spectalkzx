/*
 * spectalk.c - Main module for SpecTalk ZX
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
 *
 * Portions of this code are derived from BitchZX, also licensed under GPLv2.
 */

#include "../include/spectalk.h"
// font64_data.h ya no se necesita - fuente comprimida integrada en spectalk_asm.asm

// =============================================================================
// COMPILE-TIME SAFETY: Verificar que constantes C coinciden con ASM
// Si algún assert falla, actualizar AMBOS: spectalk.h Y spectalk_asm.asm
// =============================================================================
#if RING_BUFFER_SIZE != 2048
#error "RING_BUFFER_SIZE must be 2048 (sync with spectalk_asm.asm:31,122-126)"
#endif
#if RX_LINE_SIZE != 512
#error "RX_LINE_SIZE must be 512 (sync with spectalk_asm.asm:421)"
#endif

#define ATTR_BASE_ADDR 0x5800
#define SCREEN_ROW2_SCAN0_ADDR 0x4040
#define FRAMES_ADDR ((volatile uint8_t *)23672)
#define FMT_BUF_ADDR 0x5BE7

#define POST_CANCEL_QUIET_FRAMES 100
#define NOTIF_TIMEOUT_FRAMES 250
#define AUTOCONNECT_DELAY_FRAMES 250
#define PAGINATION_FLUSH_TIMEOUT_FRAMES 150
#define PAGINATION_RESPONSE_TIMEOUT_FRAMES 250
#define HELP_TIMEOUT_FRAMES 4500
#define SWITCHER_TIMEOUT_FRAMES 1000

// Theme data loaded from SPECTALK.DAT at startup (in ASM bss_user, contiguous with font)
extern uint8_t theme_raw[75];

// Forward declaration for internal function
void draw_status_bar_real(void);
void text_shift_right(char *addr, uint16_t count) __z88dk_callee; 
void text_shift_left(char *dest, uint16_t count) __z88dk_callee;

// =============================================================================
// COMMON STRINGS (save ROM by sharing across modules)
// =============================================================================
const char S_NOTCONN[] = "Not connected";
const char S_OK[] = "OK";
const char S_FAIL[] = "FAIL";
const char S_SERVER[] = "Server";
const char S_CHANSERV[] = "ChanServ";
const char S_NOTSET[] = "(not set)";
const char S_DISCONN[] = "Disconnected";
const char S_NICKSERV[] = "NickServ";
const char S_APPNAME[] = "SpecTalkZX " VERSION;
const char S_APPSHORT[] = "SpecTalkZX";
#ifdef SPECTALK_SPECTRANEXT
const char S_APPDESC[] = "IRC Client for Spectranext";
#elif defined(SPECTALK_NEXT)
const char S_APPDESC[] = "IRC Client for ZX Spectrum Next";
#else
const char S_APPDESC[] = "IRC Client for ZX Spectrum";
#endif
const char S_COPYRIGHT[] = "(C) 2026 M. Ignacio Monge Garcia";
const char S_MAXWIN[] = "Max windows reached (10).";
const char S_PRIVMSG[] = "PRIVMSG ";
const char S_NOTICE[]  = "NOTICE ";
const char S_TIMEOUT[] = "Connection timeout";
const char S_NOWIN[]   = "Not in Server window";
const char S_CANCELLED[] = "Cancelled";
const char S_RANGE_MINUTES[] = "Range: 1-60 minutes (0=off)";
const char S_MUST_CHAN[] = "Must be in a channel or specify one";
const char S_ARROW_IN[] = "<< ";
const char S_ARROW_OUT[] = ">> ";
const char S_EMPTY_PAT[] = "Empty pattern";
// S_CRLF removed — dead code (uart_send_crlf sends chars directly)
const char S_ASTERISK[] = "* ";
const char S_COLON_SP[] = ": ";
const char S_SP_COLON[] = " :";
const char S_SP_PAREN[] = " (";
#ifndef SPECTALK_SPECTRANEXT
const char S_AT_CIPCLOSE[] = "AT+CIPCLOSE";
const char S_AT_CIPMODE0[] = "AT+CIPMODE=0";
const char S_AT_CIPMUX0[] = "AT+CIPMUX=0";
const char S_AT_CIPSERVER0[] = "AT+CIPSERVER=0";
#endif
const char S_PROMPT[] = "> ";
const char S_CAP_END[] = "CAP END";
const char S_GLOBAL[] = "Global";
const char S_TOPIC_PFX[] = "Topic: ";
const char S_CONN_REFUSED[] = "Connection refused";
const char S_INIT_DOTS[] = "Initializing...";
const char S_ACTION[] = "ACTION ";
const char S_PONG[] = "PONG ";
// OPT H3: Constantes compartidas para strings duplicados
const char S_ON[] = "on";
const char S_OFF[] = "off";
const char S_DEFAULT_PORT[] = "6667";
const char S_CONNECTED[] = "connected";  // D5
// OPT-AGG: Nuevas constantes compartidas (cross-module dedup)
const char S_DOTS3[] = "...";
const char S_NICK_INUSE[] = "Nick in use, trying: ";
const char S_NICK_SP[] = "NICK ";
const char S_AS_SP[] = " as ";
const char S_MIN[] = " min";
const char S_DOT_SP[] = ". ";           // D9: dedup from search results
const char S_USAGE_MSG[] = "msg nick message"; // D9: dedup from cmd_msg
const char S_IDENTIFY_CMD[] = " :IDENTIFY ";      // D10: dedup (2 uses)
const char S_JOINED_SP[] = " joined ";            // D10: dedup (2 uses)
const char S_AWAY_CMD[] = "AWAY";                 // D10: dedup (2 uses)
const char S_NICK_CMD[] = "NICK";                 // D10: dedup (2 uses)
const char S_SMART[] = "smart";                   // D10: dedup (2 uses)
#ifndef SPECTALK_SPECTRANEXT
const char S_AT_CMD[] = "AT";
#endif
const char S_JOIN_CMD[] = "JOIN";
const char S_ANYKEY[] = "ANY KEY TO EXIT";
// S_NO_ESXDOS removed — esxDOS is now required (fatal halt at startup)
const char S_PART_CMD[] = "PART";                    // D19: dedup (2 uses, UART - no BPE)
#ifndef SPECTALK_SPECTRANEXT
const char S_TCP[] = "TCP";                          // D19: dedup (2 uses, UART - no BPE)
#endif
const char S_AUTOAWAY[] = "Auto-away";            // D11: dedup (5 uses)
// OPT-SHRINK-S1/S2/S3: cross-module string dedup
const char S_ALREADY[] = "Already in ";           // S2: dedup (4 uses)
const char S_YOU_LEFT[] = "You have left ";       // S3: dedup (3 uses)
const char S_MODE_SP_SCR[] = "Mode ";             // screen-side (2 uses in irc_handlers)
const char S_IN_SP[] = " in ";
const char S_QUIT_SUFFIX[] = " quit";
const char S_SP_LBRACKET[] = " [";
const char S_CHANNEL_WORD[] = "channel";
const char S_CLOSED_SP[] = "Closed ";

// =============================================================================
// THEME SYSTEM - Global attributes set by apply_theme()
// =============================================================================
uint8_t current_theme = 1;  // 1=DEFAULT, 2=TERMINAL, 3=COLORFUL
// Theme attributes array — layout is defined by TATTR_* in spectalk_contract.h
// Indices: 0=BANNER 1=STATUS 2=MSG_CHAN 3=MSG_SELF 4=MSG_PRIV 5=MAIN_BG
//   6=INPUT 7=INPUT_BG 8=PROMPT 9=MSG_SERVER 10=MSG_JOIN 11=MSG_NICK
//   12=MSG_TIME 13=MSG_TOPIC 14=MSG_MOTD 15=ERROR 16=IND_RED 17=IND_YELLOW
//   18=IND_GREEN 19=BORDER
#ifndef SPECTALK_SPECTRANEXT
uint8_t theme_attrs[20];
#endif
static uint8_t theme_badge_marker;

// =============================================================================
// UI STATE FLAGS
// =============================================================================

// Dirty flags for deferred UI updates
uint8_t status_bar_dirty = 1;
uint8_t counting_new_users;      // Flag: next 353 should reset count
uint16_t names_count_acc;        // Temp accumulator for NAMES user count
uint8_t show_names_list;         // Manual /names owns 353/366 until final 366/timeout
uint8_t names_was_manual;        // Flag: NAMES fue iniciado por /names (no por JOIN)

// Activity indicator for inactive channels
uint8_t other_channel_activity;      // Set when msg arrives on non-active channel
uint8_t irc_is_away;
// away_message mapped to UDG area 0xFFB2 via ASM defc
uint8_t away_reply_cd;       // Global cooldown (seconds) for away auto-replies

// Auto-away system
uint8_t autoaway_minutes;        // 0 = disabled, 1-60 = minutes until auto-away
uint16_t autoaway_counter;       // Seconds of inactivity
uint8_t autoaway_active;         // 1 = current away is auto-away (not manual)

// NAMES reply state machine (robust user counting with timeout)
uint8_t names_pending;
uint16_t names_timeout_frames;
// names_target_channel mapped to UDG area 0xFFD2 via ASM defc

// User preferences (toggle with commands)
uint8_t beep_enabled = 1;   // 0 = silent mode
uint8_t keyclick_enabled;   // 0 = off (default), 1 = key click sound
uint8_t nick_color_mode = 1;  // 0 = theme fixed, 1 = per-nick hash color
uint8_t show_traffic = 1;     // 0 = hide JOIN/PART/QUIT messages
uint8_t show_channel_separators = 1; // 0 = hide future channel separators
uint8_t notif_enabled = 1;    // 1 = ikkle notifications, 0 = classic inline messages
uint8_t show_timestamps = 2; // 0=off, 1=always, 2=on-change
// big_status removed (big mode eliminated)
uint8_t last_ts_hour = 0xFF;   // Last printed timestamp hour (0xFF = force print)
uint8_t last_ts_minute = 0xFF; // Last printed timestamp minute
#ifdef SPECTALK_NEXT
int8_t sntp_tz = TZ_RTC;    // Native Next starts from its hardware RTC.
#else
int8_t sntp_tz = 1;         // SNTP timezone offset (-12..+12), or TZ_RTC
#endif
int8_t sntp_tz_last = 1;    // Last numeric timezone for RTC fallback

// Keep-alive system: detect silent disconnections
// KEEPALIVE_SILENCE = 3 min = 9000 frames, KEEPALIVE_TIMEOUT = 30s = 1500 frames
#define KEEPALIVE_SILENCE_FRAMES 9000
#define KEEPALIVE_TIMEOUT_FRAMES 1500
#define LAGMETER_INTERVAL_FRAMES 3000  // 60 segundos entre PINGs de medición
uint16_t server_silence_frames;      // Frames since last server activity
uint8_t  keepalive_ping_sent;        // 1 = waiting for PONG
uint16_t keepalive_timeout;          // Timeout counter after PING sent
uint16_t lagmeter_counter;           // Counter for periodic lag measurement
uint8_t count_sync_enabled = 1;
uint8_t count_sync_idle_frames;
uint8_t count_sync_quits;
uint8_t ping_latency;               // 0=good, 1=medium, 2=high

// Pagination for long LIST/WHO results
uint8_t pagination_active;
uint16_t pagination_count;
uint8_t pagination_lines;        // Líneas impresas desde última pausa
uint8_t pagination_timeout;      // Frames sin datos válidos → safety timeout
uint8_t search_data_lost;        // Flag: se perdieron datos durante listado
uint8_t buffer_pressure;         // 1 = buffer >75% (indicator shows empty circle)

// Notification bar (ikkle-4 font on row 20)
uint16_t notif_timeout;              // Frames until clear; 0=inactive
uint8_t notif_is_pm;                 // 1=PM notification (enables TAB reply)
#ifndef SPECTALK_SPECTRANEXT
char last_pm_nick[IRC_NICK_SIZE];    // Nick of last PM sender
#endif

// Overlay execution slot (loaded from esxDOS on demand)
// overlay_slot aliased to rx_line (512B) in spectalk_asm.asm — mutually exclusive

// Flush state for search commands (simple drain-based approach)
// States: 0=idle, 1=draining, 2=command sent
uint8_t search_flush_state;
static uint8_t search_flush_stable;      // Frames con buffer vacío consecutivos
static uint8_t search_pending_type;      // Tipo de comando pendiente
uint8_t search_header_rcvd;              // Flag: recibimos 321/352 header (no rate-limited)
uint8_t search_saw_server_notice;        // Flag: server NOTICE durante pagination (rate limit, etc.)
uint8_t post_cancel_quiet;               // Frames restantes tras BREAK cancel para suprimir h_default_cmd
// NOTA: search_pattern[] es scratch para busquedas/snapshots; channels= persistente
// vive separado en autojoin_channels[] para que overlays y busquedas no lo pisen.

// SEARCH state
uint8_t search_mode;
char    search_pattern[SEARCH_PATTERN_SIZE];  // Scratch: busquedas, snapshots de !config
char    autojoin_channels[SEARCH_PATTERN_SIZE]; // channels= persistente cargado desde config
uint16_t search_index;
uint8_t channel_context_next_row;
uint8_t channel_context_pending;
static uint8_t channel_context_anchor_idx;

void deferred_wrap_step(void);
static void channel_context_banner(void);

static void channel_context_drain_wrap(void)
{
    if (!overlay_mode) {
        while (deferred_wrap_active) deferred_wrap_step();
    }
}

void draw_status_bar(void)
{
    status_bar_dirty = 1;
}

// Helper: clear main area and reset cursor (saves ~16 bytes per call site)
void clear_main(void)
{
    clear_zone(MAIN_START, MAIN_LINES, ATTR_MAIN_BG);
    main_line = MAIN_START;
    main_col = 0;
    channel_context_next_row = 0;
    channel_context_pending = 0;
}

static void about_keepalive_rebaseline(void)
{
    server_silence_frames = 0;
    keepalive_ping_sent = 0;
    keepalive_timeout = 0;
    lagmeter_counter = 0;
}


// Input cell cache helper: resident ASM in 30_rendering.asm
extern void put_char64_input_cached(uint8_t y, uint8_t col, char ch, uint8_t attr) __z88dk_callee;

// =============================================================================
// UART DRIVER AND RING buffer
// =============================================================================

// Ring buffer: single-producer/single-consumer, thread-safe en Z80 sin IRQ
// ring_buffer placed via defc in spectalk_asm.asm (outside BSS, fixed address)
uint16_t rb_head;
uint16_t rb_tail;

// Line parser state
char rx_line[RX_LINE_SIZE];

// Persistent render/parser state. Keep immediately after rx_line; its overlay
// alias follows the linker symbol, while BSS survives esxDOS unlike Printer RAM.
char notif_buf[64];
uint8_t names_friend_pos;
char pkt_empty[1];
uint8_t plf_start_byte;
uint8_t plf_pair_count;

uint16_t rx_pos;
uint16_t rx_last_len;
uint8_t rx_overflow;             // Flag for ASM access (0 or 1)

// TIMEOUT_* values are defined in spectalk.h (single source of truth)

uint8_t uart_drain_limit = DRAIN_NORMAL;

// Wait frames while draining UART - prevents buffer overflow during waits
void wait_drain(uint8_t frames) __z88dk_fastcall
{
    while (frames--) {
        frame_wait_drain();
    }
}

// Limpia completamente todos los buffers de recepción
// Usar antes de enviar comandos de búsqueda para evitar residuos
void flush_all_rx_buffers(void)
{
    // 1. Drain UART to ring buffer (limit=0 -> 255 iterations, sufficient for ESP buffer)
    uint8_t saved = uart_drain_limit;
    uart_drain_limit = 0;
    uart_drain_to_buffer();
    // 2. Discard and repeat drain for bytes that arrived during step 1
    rb_tail = rb_head;
    uart_drain_to_buffer();
    uart_drain_limit = saved;
    rb_tail = rb_head;

    // 3. Clear line parser state
    rx_line[0] = 0;
    rx_pos = 0;
    rx_overflow = 0;
}

void names_print_summary(uint8_t incomplete) __z88dk_fastcall
{
    char buf[8];
    pagination_active = 0;
    set_attr_sys();
    u16_to_dec(buf, names_count_acc);
    main_puts2("(", buf);
    main_print(incomplete ? " listed, incomplete)" : " listed)");
    pagination_count = 0;
    cursor_visible = 1;
    redraw_input_full();
}

void names_finish_incomplete(void)
{
    if (names_was_manual) {
        flush_all_rx_buffers();
        post_cancel_quiet = POST_CANCEL_QUIET_FRAMES;
        if (show_names_list && pagination_active) names_print_summary(1);
    }

    names_pending = 0;
    names_timeout_frames = 0;
    names_target_channel[0] = '\0';
    counting_new_users = 0;
    names_count_acc = 0;
    show_names_list = 0;
    names_was_manual = 0;
    search_data_lost = 0;
    buffer_pressure = 0;
    status_bar_dirty = 1;
}

// Direct UART-to-parser pump during OVERLAY_ABOUT. ASM keeps resident size down.
extern void about_pump(void);

// rb_pop() está implementada en spectalk_asm.asm

// =============================================================================
// GLOBAL bufferS
// =============================================================================
// line_buffer mapped to CHANS workspace 0x5CB6 via ASM defc
uint8_t line_len;
uint8_t cursor_pos;
static uint8_t input_prev_len;  // for trailing char cleanup in redraw_input_from

// CAPS LOCK state (from BitStream)
uint8_t caps_lock_mode;
uint8_t cursor_shift_held;
uint8_t caps_latch;

// =============================================================================
// IRC STATE
// =============================================================================
char irc_server[IRC_SERVER_SIZE];
char irc_port[IRC_PORT_SIZE] = "6667";
char irc_nick[IRC_NICK_SIZE];
char irc_pass[IRC_PASS_SIZE];
char nickserv_pass[AUTH_COMMAND_SIZE];
char nickserv_nick[AUTH_SERVICE_SIZE];
uint8_t auth_mode;
uint8_t auth_profile;
uint8_t autoconnect;
uint8_t autojoin;
uint8_t autojoin_defer_flags;
uint8_t autojoin_ident_grace;
uint8_t has_esxdos;
// friend_nicks mapped to UDG area 0xFF58 via ASM defc
uint8_t friends_ison_sent;
uint8_t friend_count;
#ifndef SPECTALK_SPECTRANEXT
char user_mode[USER_MODE_SIZE];
#endif
char network_name[NETWORK_NAME_SIZE];
uint8_t connection_state;

// =============================================================================
// MULTI-WINDOW SUPPORT
// =============================================================================
ChannelInfo channels[MAX_CHANNELS];
uint8_t current_channel_idx;
ChannelInfo *cur_chan_ptr = channels;
uint8_t channel_count;

uint8_t nav_history[NAV_HIST_SIZE];
uint8_t nav_hist_ptr;

// nav_push() moved to spectalk_asm.asm (OPT: 79 -> 55 bytes, LDIR shift)


void nav_fix_on_delete(uint8_t deleted_idx) __z88dk_fastcall {
    uint8_t i, j = 0;
    for (i = 0; i < nav_hist_ptr; i++) {
        uint8_t h = nav_history[i];
        if (h == deleted_idx) continue;
        if (h > deleted_idx) h--;
        nav_history[j++] = h;
    }
    nav_hist_ptr = j;
}

static void refresh_other_channel_activity(void)
{
    uint8_t i;
    ChannelInfo *ch = channels;
    other_channel_activity = 0;
    for (i = 0; i < channel_count; i++, ch++) {
        if (i != current_channel_idx &&
            (ch->flags & (CH_FLAG_ACTIVE | CH_FLAG_UNREAD)) == (CH_FLAG_ACTIVE | CH_FLAG_UNREAD)) {
            other_channel_activity = 1;
            return;
        }
    }
}

// =============================================================================
// IGNORE LIST
// =============================================================================
extern char ignore_list[MAX_IGNORES][16];  // fixed high RAM, see 00_preamble.asm
uint8_t ignore_count;

// Add nick to ignore list, returns 1 on success
uint8_t add_ignore(const char *nick) __z88dk_fastcall
{
    if (ignore_count >= MAX_IGNORES) return 0;
    if (is_ignored(nick)) return 0;  // Already ignored
    st_copy_n(ignore_list[ignore_count], nick, sizeof(ignore_list[0]));
    ignore_count++;
    return 1;
}

// Remove nick from ignore list, returns 1 on success
uint8_t remove_ignore(const char *nick) __z88dk_fastcall
{
    uint8_t i, j;
    for (i = 0; i < ignore_count; i++) {
        if (st_stricmp(ignore_list[i], nick) == 0) {
            // Shift remaining entries
            for (j = i; j < ignore_count - 1; j++) {
                st_copy_n(ignore_list[j], ignore_list[j + 1], sizeof(ignore_list[0]));
            }
            ignore_count--;
            return 1;
        }
    }
    return 0;
}

// find_channel/find_query are implemented in ASM for size optimization

// find_empty_channel_slot() moved to spectalk_asm.asm (OPT: 46 -> 23 bytes)

// Forward declarations for switcher live-update
static uint8_t sw_active;
static uint8_t sw_dirty;

// Internal: add slot with given flags
static int8_t add_slot_internal(const char *name, uint8_t flags) __z88dk_callee
{
    int8_t idx = find_empty_channel_slot();
    if (idx < 0) return -1;
    
    st_copy_n(channels[idx].name, name, sizeof(channels[0].name));
    channels[idx].mode[0] = '\0';
    channels[idx].user_count = 0;
    channels[idx].flags = flags;
    channel_count++;
    if (sw_active) sw_dirty = 1;
    return idx;
}

// Add channel, returns index or -1 if full
int8_t add_channel(const char *name) __z88dk_fastcall
{
    return add_slot_internal(name, CH_FLAG_ACTIVE);
}

// Add query window for private messages, returns index or -1 if full
int8_t add_query(const char *nick) __z88dk_fastcall
{
    // INTERCEPCIÓN DE SERVICIOS (ChanServ, NickServ)
    if (st_stricmp(nick, S_CHANSERV) == 0 || st_stricmp(nick, S_NICKSERV) == 0) {
        st_copy_n(channels[0].name, nick, sizeof(channels[0].name));
        return 0;
    }

    // Check if query already exists
    int8_t idx = find_query(nick);
    if (idx >= 0) return idx;
    
    // CRÍTICO: Limitar queries privados para reservar slots para canales
    uint8_t query_count = 0;
    uint8_t i;

    for (i = 1; i < MAX_CHANNELS; i++) {
        if ((channels[i].flags & (CH_FLAG_ACTIVE | CH_FLAG_QUERY)) == (CH_FLAG_ACTIVE | CH_FLAG_QUERY)) {
            query_count++;
        }
    }
    
    #define MAX_QUERIES 5  // Reservar 5 slots para canales
    if (query_count >= MAX_QUERIES) {
        // Rechazar silenciosamente nuevas queries para evitar spam de error
        return -1;
    }
    
    return add_slot_internal(nick, CH_FLAG_ACTIVE | CH_FLAG_QUERY);
}

void remove_channel(uint8_t idx) __z88dk_fastcall
{
    uint8_t i;
    uint8_t next_idx = 0;
    uint8_t was_current = (idx == current_channel_idx);

    if (idx >= MAX_CHANNELS || !(channels[idx].flags & CH_FLAG_ACTIVE)) return;
    if (idx == 0) return;

    if (was_current) channel_context_drain_wrap();

    // 1. Si cerramos la ventana actual, buscar a dónde ir (usando índices ORIGINALES)
    if (was_current) {
        // Buscar en historial hacia atrás el último slot válido que no sea el que cerramos
        for (i = nav_hist_ptr; i > 0; i--) {
            uint8_t h = nav_history[i - 1];
            if (h != idx && h < MAX_CHANNELS && (channels[h].flags & CH_FLAG_ACTIVE)) {
                next_idx = h;
                break;
            }
        }
    }

    // 2. DEFRAGMENTACIÓN (mover slots hacia arriba)
    for (i = idx; i < MAX_CHANNELS - 1; i++) {
        channels[i] = channels[i + 1];
    }
    // Mark trailing duplicate slot inactive; add_slot_internal overwrites it on reuse.
    channels[MAX_CHANNELS - 1].flags = 0;
    if (channel_count > 1) channel_count--;
    if (sw_active) sw_dirty = 1;

    // 3. Ajustar índices DESPUÉS de defragmentar
    if (channel_context_anchor_idx < MAX_CHANNELS) {
        if (channel_context_anchor_idx == idx) channel_context_anchor_idx = 0xFF;
        else if (channel_context_anchor_idx > idx) channel_context_anchor_idx--;
    }
    if (was_current) {
        // Ajustar next_idx si apuntaba a un slot que se movió
        if (next_idx > idx) next_idx--;
        current_channel_idx = next_idx;
        if (main_col || main_line != channel_context_next_row)
            channel_context_anchor_idx = next_idx;
    } else if (current_channel_idx > idx) {
        current_channel_idx--;
    }
    cur_chan_ptr = &channels[current_channel_idx];
    if (was_current) channels[current_channel_idx].flags &= (uint8_t)~(CH_FLAG_UNREAD | CH_FLAG_MENTION);
    refresh_other_channel_activity();

    // 4. Limpiar historial (ajustar índices y eliminar el borrado)
    nav_fix_on_delete(idx);

    draw_status_bar();
    if (was_current) {
        channel_context_banner();
        redraw_input_full();
    }
}

static uint8_t channel_context_ink(const char *name) __z88dk_fastcall
{
    uint8_t h = 0;
    uint8_t c;
    static const uint8_t cc_inks[] = { 2, 5, 6, 4, 3, 7 };

    if (current_channel_idx == 0) return (uint8_t)(ATTR_MSG_SERVER & 7);
    if (!nick_color_mode) return (uint8_t)(ATTR_MSG_CHAN & 7);

    while ((c = (uint8_t)*name++) != 0) {
        if (c <= 32 || c == '@') continue;
        c |= 0x20;
        h += (uint8_t)((c ^ (c >> 3)) & 7);
        if (h >= 6) h -= 6;
        if (h >= 6) h -= 6;
    }

    return cc_inks[h];
}

static void channel_context_banner(void)
{
    uint8_t row;
    uint8_t ink;
    uint8_t divider_attr;
    uint8_t label_attr;
    uint8_t start_byte;
    uint8_t end_byte;
    uint8_t name_col;
    uint8_t name_len;
    uint8_t i;
    uint8_t erase_only = 0;
    uint8_t v;
    const char *src;
    char *p;
    char *name;
    uint8_t *pix;
    uint8_t *ap;

    if (!show_channel_separators) {
        channel_context_next_row = 0;
        channel_context_pending = 0;
        return;
    }
    if (overlay_mode || pagination_active || deferred_wrap_active) {
        channel_context_pending = 1;
        return;
    }
    if (!irc_channel[0]) {
        channel_context_pending = 0;
        return;
    }

    if (main_col) {
        channel_context_next_row = 0;
        main_newline();
    } else if (main_line == channel_context_next_row) {
        main_line--;
        if (current_channel_idx == channel_context_anchor_idx) {
            erase_only = 1;
        }
    }

    p = temp_input;
    i = '0';
    v = time_hour;
    while (v >= 10) { v -= 10; i++; }
    *p++ = (char)i;
    *p++ = (char)('0' + v);
    *p++ = ':';
    i = '0';
    v = time_minute;
    while (v >= 10) { v -= 10; i++; }
    *p++ = (char)i;
    *p++ = (char)('0' + v);
    *p = 0;

    name = temp_input + 8;
    p = name;
    if (current_channel_idx == 0 || (chan_flags & CH_FLAG_QUERY)) *p++ = ' ';
    src = irc_channel;
    while (*src && (uint8_t)(p - name) < 28) {
        v = (uint8_t)*src++;
        *p++ = (v == '#' || v == '&') ? ' ' : (char)v;
    }
    *p = 0;
    name_len = (uint8_t)(p - name);
    if (!name_len) {
        channel_context_pending = 0;
        return;
    }

    row = main_line;
    ink = channel_context_ink(name);
    divider_attr = (uint8_t)((ATTR_MAIN_BG & 0x38) | 0x40 | ink);
    label_attr = (uint8_t)(0x40 | (ink << 3) | ((ATTR_MAIN_BG >> 3) & 7));
    clear_line(row, ATTR_MAIN_BG);
    if (erase_only) {
        channel_context_next_row = 0;
        channel_context_pending = 0;
        return;
    }

    name_col = (uint8_t)(SCREEN_COLS - name_len);
    start_byte = 3; /* after HH:MM + one 64-col gap */
    end_byte = (uint8_t)((name_col >> 1) - 1);

    pix = (uint8_t *)(SCREEN_ROW_ADDR(row) + 0x0400); /* scanline 4 */
    ap = (uint8_t *)(ATTR_BASE_ADDR + ((uint16_t)row << 5));
    if (end_byte >= start_byte) {
        i = (uint8_t)(end_byte - start_byte + 1);
        pix += start_byte;
        ap += start_byte;
        while (i--) {
            *pix++ = 0xFF;
            *ap++ = divider_attr;
        }
    }

    ikkle_draw(row, 0, temp_input, divider_attr);
    ikkle_draw(row, name_col, name, label_attr);
    last_ts_hour = time_hour;
    last_ts_minute = time_minute;
    main_newline();
    channel_context_next_row = main_line;
    channel_context_pending = 0;
}

void switch_to_channel(uint8_t idx) __z88dk_fastcall
{
    if (idx >= MAX_CHANNELS || !(channels[idx].flags & CH_FLAG_ACTIVE)) return;
    if (idx == current_channel_idx) return;

    channel_context_drain_wrap();
    if (main_col || main_line != channel_context_next_row) {
        channel_context_anchor_idx = current_channel_idx;
    }
    nav_push(current_channel_idx);

    current_channel_idx = idx;
    cur_chan_ptr = &channels[idx];

    // Clear unread + mention when user switches in
    channels[idx].flags &= (uint8_t)~(CH_FLAG_UNREAD | CH_FLAG_MENTION);

    other_channel_activity = 0;
    set_border(BORDER_COLOR);
    force_status_redraw = 1;
    status_bar_dirty = 1;
    channel_context_banner();
    redraw_input_full();
}

// OPT-SHRINK-P1: Common switch+notify pattern (dedup 4 identical blocks)
void switch_or_notify(uint8_t idx) __z88dk_fastcall
{
    if (idx != current_channel_idx) {
        switch_to_channel(idx);
        if (!show_channel_separators) notify2("Switched to ", irc_channel, ATTR_MSG_JOIN);
    } else {
        notify2(S_ALREADY, irc_channel, ATTR_MSG_SYS);
    }
}

// =============================================================================
// CHANNEL SWITCHER OVERLAY (state-based, non-blocking)
// =============================================================================

// Forward declaration (defined later in this file)
extern uint8_t last_frames_lo;

// Switcher state — persists across main loop frames
// (sw_active and sw_dirty declared earlier for live-update from add/remove channel)
static uint8_t sw_sel;
static uint8_t sw_first;
// OPT: sw_map + sw_flags_snap aliased onto search_pattern[] — mutually exclusive:
// switcher requires !pagination_active && search_mode==SEARCH_NONE (line 3068),
// search requires user ENTER which is consumed while switcher is open (line 3067).
#define sw_map       ((uint8_t *)search_pattern)        // [0..9]
#define sw_flags_snap ((uint8_t *)(search_pattern + 10)) // [10..19]
static uint8_t sw_count;
static uint8_t sw_released;  // EDIT key released after open
static uint16_t sw_timeout;  // frames since last key press (auto-close)

// Even-width tabs + 2-char separator " |" → all tab boundaries align to
// attribute cell boundaries (8px), so inverse video never bleeds into separators.
// Tab format: " N:name " with N = slot number (0-9).
// Uses print_line64_fast(), which now matches print_str64_char vertical layout:
// scanline 0 blank, glyph rows on scanlines 1-7.

static void switcher_close(void);

// Compute tab width for a given channel slot index (always even)
static uint8_t sw_tab_width(uint8_t slot) __z88dk_fastcall
{
    // " N:name " = nlen + 4, or " N:@name " = nlen + 5 for queries
    const char *name = channels[slot].name;
    uint8_t tw = st_strlen((*name == '#' || *name == '&') ? name + 1 : name) + 4;
    if (channels[slot].flags & CH_FLAG_QUERY) tw++;
    if (tw & 1) tw++;
    return tw;
}

static void switcher_rebuild_map(void)
{
    uint8_t old_slot = (sw_count > 0) ? sw_map[sw_sel] : current_channel_idx;
    uint8_t i;
    sw_count = 0;
    sw_sel = 0;
    for (i = 0; i < MAX_CHANNELS; i++) {
        if (channels[i].flags & CH_FLAG_ACTIVE) {
            if (i == old_slot) sw_sel = sw_count;
            sw_map[sw_count++] = i;
        }
    }
    if (sw_sel >= sw_count && sw_count > 0) sw_sel = sw_count - 1;
}

static void switcher_render(void)
{
    if (deferred_wrap_active) return;
    overlay_exec(5, 1); /* SPCTLK6 entry 1 */
}

static void switcher_open(void)
{
    sw_count = 0;   // forces rebuild to select current_channel_idx
    sw_first = 0;
    switcher_rebuild_map();
    if (sw_count < 2) return;
    sw_active = 1;
    sw_released = 0;
    sw_timeout = 0;
    sw_dirty = 1;
}

static void switcher_part(uint8_t idx) __z88dk_fastcall
{
    uint8_t f = channels[idx].flags;
    if (f & CH_FLAG_ACTIVE) {
        if (f & CH_FLAG_QUERY) {
            notify2(S_CLOSED_SP, channels[idx].name, ATTR_MSG_SYS);
        } else {
            irc_send_cmd1(S_PART_CMD, channels[idx].name);
            notif_cancel_current();
            notify2(S_YOU_LEFT, channels[idx].name, ATTR_MSG_JOIN);
        }
        remove_channel(idx);
    }
    sw_count = 0;
    switcher_rebuild_map();
}

static void switcher_close(void)
{
    sw_active = 0;
    clear_line(2, ATTR_MAIN_BG);
    // Redraw 1px separator (row 2, scanline 0)
    memset((void *)SCREEN_ROW2_SCAN0_ADDR, 0xFF, 32);
    last_frames_lo = *FRAMES_ADDR;
}


// Reset all channels (on disconnect)
void reset_all_channels(void)
{
    uint8_t i;
    ChannelInfo *ch = channels;

    for (i = 0; i < MAX_CHANNELS; i++, ch++) {
        ch->flags = 0;
        ch->name[0] = '\0';
        ch->mode[0] = '\0';
        ch->user_count = 0;
    }

    // Slot 0: SIEMPRE reservado para Server / ChanServ
    channels[0].flags = CH_FLAG_ACTIVE | CH_FLAG_QUERY;  // Active + query (no user count)
    st_copy_n(channels[0].name, S_SERVER, sizeof(channels[0].name));

    current_channel_idx = 0;
    cur_chan_ptr = channels;
    channel_context_next_row = 0;
    channel_context_pending = 0;
    channel_context_anchor_idx = 0;
    channel_count = 1;
    other_channel_activity = 0;  // FIX: limpiar indicador de actividad
}

// ============================================================
// IRC PARAMETER TOKENIZATION
// ============================================================
// Pre-tokenize IRC message params to avoid repeated strchr/skip
// in individual handlers. Based on BitchZX str_word_find pattern.
// 
// After calling tokenize_params(par):
// =============================================================================
// IRC PARAMS TOKENIZER
// =============================================================================
char *irc_params[IRC_MAX_PARAMS];
uint8_t irc_param_count;
uint8_t irc_params_dirty;

// tokenize_params está implementada en ASM (spectalk_asm.asm)
extern void tokenize_params(char *par) __z88dk_fastcall;

void irc_params_ensure(void)
{
    if (irc_params_dirty) {
        irc_params_dirty = 0;
        tokenize_params(pkt_rest);
    }
}

// Safe param accessor - returns empty string if out of bounds
const char* irc_param(uint8_t idx) __z88dk_fastcall
{
    irc_params_ensure();
    if (idx >= irc_param_count) return "";
    return irc_params[idx];
}

// cursor visibility control (shared across modules)
uint8_t cursor_visible = 1;  // cursor only visible when user can type

// Connection state tracking (shared across modules)
uint8_t closed_reported;
uint8_t disconnecting_in_progress;       // FIX: Prevent reentrant disconnection

// TIME TRACKING (Optimized: No 32-bit math)
// Eliminamos uptime_frames y time_sync_frames para ahorrar librería de división
uint8_t time_hour;
uint8_t time_minute;
uint8_t time_second;             // Nuevo: Segundos explícitos
uint16_t uptime_minutes;         // Session uptime in minutes (for !status)
uint8_t sntp_init_sent;          // Flag: SNTP init commands sent (not static - needs reset on disconnect)
uint8_t sntp_waiting;            // Flag: waiting for SNTP response
uint8_t sntp_queried;            // Flag: valid time received (stop retrying)

// Frame-accurate ticker using system variable FRAMES (23672)
uint8_t last_frames_lo;          // Last read of FRAMES low byte
uint16_t tick_accum;             // Frames; native Next uses 1/64-frame units

// SCREEN STATE
uint8_t main_line = MAIN_START;
uint8_t main_col;
uint8_t wrap_indent;             // Indentación para líneas que continúan (wrap)
uint8_t deferred_wrap_active;
uint8_t current_attr;  // Initialized in apply_theme()
uint8_t deferred_wrap_attr;
char *deferred_wrap_p;

// Shared scratch buffer for u16-to-string conversions (8 bytes).
// Lives in the free Printer Buffer tail; $5BE5-$5BE6 is mpwr_last_space.
// Used by draw_clock, draw_status_bar_real and search index rendering (never simultaneously).
#define fmt_buf ((char *)FMT_BUF_ADDR)

// COMMAND HISTORY
#define HISTORY_SIZE    4
// Reduced 96 -> 48 -> 32; recall capped at 31 chars. line_buffer stays 128.
#define HISTORY_LEN     32

static char history[HISTORY_SIZE][HISTORY_LEN];
// Draft restore is cold and mutually exclusive with search/switcher scratch.
// Aliasing saves 128B BSS; drafts longer than SEARCH_PATTERN_SIZE-1 truncate
// when returning from history navigation.
#define history_draft search_pattern
static uint8_t hist_head;
static uint8_t hist_count;
static int8_t hist_pos = -1;

static void history_add(const char *cmd, uint8_t len) __z88dk_callee
{
    uint8_t i;
    if (len == 0) return;
    
    // Ignorar si solo hay espacios
    for (i = 0; i < len && cmd[i] == ' '; i++);
    if (i == len) return;
    
    st_copy_n(history[hist_head], cmd, HISTORY_LEN);
    
    // OPTIMIZADO: % 4 -> & 3
    hist_head = (hist_head + 1) & 3;
    
    if (hist_count < HISTORY_SIZE) hist_count++;
    hist_pos = -1;
}

static void history_nav_up(void)
{
    uint8_t idx;
    if (hist_count == 0) return;
    if (hist_pos == -1) st_copy_n(history_draft, line_buffer, sizeof(history_draft));
    if (hist_pos < (int8_t)(hist_count - 1)) hist_pos++;
    
    // OPTIMIZADO: % 4 -> & 3
    idx = (hist_head + HISTORY_SIZE - 1 - hist_pos) & 3;

    st_copy_n(line_buffer, history[idx], sizeof(line_buffer));
    line_len = st_strlen(line_buffer);
    cursor_pos = line_len;
}

static void history_nav_down(void)
{
    uint8_t idx;
    if (hist_pos < 0) return;
    hist_pos--;
    if (hist_pos < 0) {
        st_copy_n(line_buffer, history_draft, sizeof(history_draft));
        line_len = st_strlen(line_buffer);
    } else {
        // OPTIMIZADO: % 4 -> & 3
        idx = (hist_head + HISTORY_SIZE - 1 - hist_pos) & 3;
        st_copy_n(line_buffer, history[idx], sizeof(line_buffer));
        line_len = st_strlen(line_buffer);
    }
    cursor_pos = line_len;
}

// Draw 1-pixel horizontal line - faster and more elegant than '-' chars
// ============================================================
// CONTEXTO GLOBAL PARA RUTINAS DE IMPRESIÓN 64 COL
// Estas variables son accedidas por el código ASM en spectalk_asm.asm
// ============================================================
volatile uint8_t g_ps64_y;
volatile uint8_t g_ps64_col;
volatile uint8_t g_ps64_attr;


// print_char64() moved to spectalk_asm.asm (OPT: 33 -> 19 bytes)

// Pure C implementation: this wrapper is intentionally not hand-written in ASM.
// It is called from stack/BSS UI builders, so keep the SDCC/z88dk stack contract
// boring unless a pixel-perfect HW test proves an ASM replacement safe.
void print_str64(uint8_t y, uint8_t col, const char *s, uint8_t attr) __z88dk_callee
{
    g_ps64_y = y;
    g_ps64_col = col;
    g_ps64_attr = attr;
    while (*s) {
        if (g_ps64_col < 64)
            print_str64_char(*s);
        g_ps64_col++;
        s++;
    }
}

extern uint8_t read_key(void);

// MAIN AREA OUTPUT

// Helper interno para pausa de paginación (retorna 1 si cancelado)
uint8_t pagination_pause(void)
{
    uint8_t key;
    uint16_t backlog;
    uint8_t prev_pressure;
    uint8_t ui_throttle = 1;

    // Mostrar prompt en row 20 con ikkle-4 font (frees MAIN_END for chat)
    notif_center("- MORE: ANY KEY | BREAK: CANCEL -", ATTR_MSG_SYS);

    while (in_inkey() != 0) { frame_wait(); net_pump_rx(); }
    while ((key = in_inkey()) == 0) {
        frame_wait();
        net_pump_rx();

        prev_pressure = buffer_pressure;
        backlog = (rb_head - rb_tail) & RING_BUFFER_MASK;
        buffer_pressure = (backlog > BUFFER_PRESSURE_THRESHOLD) ? 1 : 0;

        if (backlog > (RING_BUFFER_SIZE - BUFFER_CRITICAL_MARGIN)) {
            search_data_lost = 1;
            rb_tail = rb_head;   // descarte total O(1)
            rx_pos = 0;          // FIX: Descartar línea parcial en curso
            rx_overflow = 1;     // FIX: Descartar bytes hasta próximo \n
            buffer_pressure = 0;
        }

        // Redibujar indicador si cambió, con throttling barato
        // FIX: Transición a 0 (presión aliviada) siempre se redibuja inmediatamente
        if (buffer_pressure != prev_pressure) {
            if (buffer_pressure == 0 || --ui_throttle == 0) {
                ui_throttle = 8;
                draw_status_bar_real();
            }
        } else {
            ui_throttle = 1;
        }
    }
    while (in_inkey() != 0) { frame_wait(); net_pump_rx(); }

    if (buffer_pressure) {
        buffer_pressure = 0;
        draw_status_bar_real();
    }

    if (key == KEY_BREAK) {  // BREAK = cancelar
        notif_clear();
        // "Cancelled (incomplete)" si hubo buffer overflow antes del cancel.
        print_line64_fast(MAIN_END,
                          search_data_lost ? "Cancelled (incomplete)" : S_CANCELLED,
                          ATTR_ERROR);
        main_line = MAIN_END;
        main_col = 64;
        flush_all_rx_buffers();
        cancel_search_state();
        // Ventana de silencio en h_default_cmd para evitar "><" garbage
        // de residuos de la lista cancelada (IRC no permite cancelar LIST
        // server-side). No usar drenajes fijos que bloqueen input.
        post_cancel_quiet = POST_CANCEL_QUIET_FRAMES;
        return 1;
    }

    notif_clear();
    clear_main();
    pagination_lines = 0;
    return 0;
}


/* main_newline moved to ASM (see asm/spectalk_asm.asm) */
extern void main_newline(void);

// main_print: resident ASM in 50_main_output.asm

void deferred_wrap_step(void);

void deferred_wrap_start(char *s) __z88dk_fastcall
{
    if (overlay_mode) return;
    deferred_wrap_p = s;
    deferred_wrap_attr = current_attr;
    deferred_wrap_active = 1;
}

// =============================================================================
// SEARCH SYSTEM — Lógica simplificada
// =============================================================================

void cancel_search_state(void)
{
    pagination_active = 0;
    pagination_count = 0;
    pagination_lines = 0;
    search_mode = SEARCH_NONE;
    search_index = 0;
    pagination_timeout = 0;
    // FIX: Marcar como datos perdidos para que 366 no actualice conteo
    search_data_lost = 1;
    
    // Reset flush state
    search_flush_state = 0;
    search_flush_stable = 0;
    search_pending_type = 0;
    search_header_rcvd = 0;
    search_saw_server_notice = 0;

    cursor_visible = 1;
    redraw_input_full();

    if (!(names_pending && names_was_manual)) show_names_list = 0;
    buffer_pressure = 0;
    status_bar_dirty = 1;
}

// Inicia modo paginación preparando la pantalla
void start_pagination(void)
{
    clear_main();
    pagination_active = 1;
    pagination_count = 0;
    pagination_lines = 0;
    pagination_timeout = 0;
    search_data_lost = 0;
    
    cursor_visible = 0;
    redraw_input_full();
}

// Envía el comando IRC real (llamada cuando el drenaje ha terminado)
// NOTA: search_pattern ya contiene el argumento (guardado en start_search_command)
// OPT M8: Lógica simplificada
static void send_pending_search_command(void)
{
    uint8_t is_chan = (search_pending_type == PEND_LIST || search_pending_type == PEND_SEARCH_CHAN);
    search_mode = is_chan ? SEARCH_CHAN : SEARCH_USER;
    
    rx_overflow = 0;  // FIX: No perder respuesta del servidor
    
    if (search_pending_type == PEND_SEARCH_CHAN) {
        net_send_string("LIST *");
        net_send_string(search_pattern);
        net_send_string("*\r\n");
    } else {
        irc_send_cmd1(is_chan ? "LIST" : "WHO", search_pattern);
        if (search_pending_type == PEND_WHO ||
            (search_pending_type == PEND_LIST && !IS_CHAN_PREFIX(search_pattern[0])))
            search_pattern[0] = 0;
    }
}

// Inicia un comando de búsqueda con drenaje progresivo.
// Fase 1: Vacía el buffer activamente hasta que quede estable (vacío X frames).
// Fase 2: Envía el comando y procesa respuestas normalmente.
void start_search_command(uint8_t type, const char *arg) __z88dk_callee
{
    // Throttle: rechazar búsqueda durante ventana post-cancel para evitar que
    // el servidor nos desconecte por flood (múltiples LIST rápidos).
    if (post_cancel_quiet) {
        ui_err("Wait a moment before searching again");
        return;
    }

    // 1. Cancelar búsqueda previa si la había
    cancel_search_state();

    // 2. Guardar argumento en search_pattern (arg ya viene truncado por caller)
    st_copy_n(search_pattern, arg ? arg : "", sizeof(search_pattern));
    search_pending_type = type;

    // 3. Preparar pantalla
    start_pagination();
    search_index = 0;
    
    // 4. Mostrar feedback inmediato (sin newline: resultado se concatena)
    set_attr_sys();
    main_puts("Searching... ");
    
    // 5. Vaciar TODOS los buffers y comenzar fase de drenaje
    flush_all_rx_buffers();
    
    search_flush_state = 1;   // Estado: drenando
    search_flush_stable = 0;  // Contador de frames estables
    pagination_timeout = 0;
}

extern void count_sync_tick(void);

// STATUS BAR

// Double-height string renderer (uses draw_big_char from ASM)
extern void draw_big_char(uint8_t ch) __z88dk_fastcall;

// print_big_str: frameless ASM in spectalk_asm.asm

static void draw_clock(void)
{
    char *p = fmt_buf;

    /* fmt_buf is only 8B (7 glyphs + NUL). Gap col 54 is painted separately. */
    *p++ = '[';
    fast_u8_to_str(p, time_hour); p += 2;
    *p++ = ':';
    fast_u8_to_str(p, time_minute); p += 2;
    *p++ = ']';
    *p = 0;

    /* Half-char right shift: NetChessZX STATUS_CLOCK_COL = 55. */
    print_char64(INFO_LINE, 54, ' ', ATTR_STATUS);
    print_str64(INFO_LINE, 55, fmt_buf, ATTR_STATUS);
}

// Print timestamp prefix: [HH:MM] - implemented in ASM (spectalk_asm.asm)
extern void main_print_time_prefix(void);

// =============================================================================
// STATUS BAR ARCHITECTURE — CONTRATOS Y LÍMITES
// =============================================================================
//
// LAYOUT (64 columnas lógicas = 32 físicas):
//   [0-53]  : Contenido dinámico (nick, canal, usuarios)
//   [54]    : hueco de medio carácter (alineación NetChessZX)
//   [55-61] : Reloj [HH:MM] (7 chars)
//   [62-63] : Indicador de conexión (1 char físico = 2 lógicos)
//
// BUFFER:
//   sb_left_part[57] — buffer de trabajo para columnas 0-56 (incluye \0)
//   sb_last_status[57] — caché del último estado para diff-redraw
//
// LÍMITES CLAVE:
//   - limit_end = sb_left_part + 54  → última posición antes del reloj
//   - central_limit = limit_end - user_len → reserva espacio para "[NNN]"
//
// ESTRUCTURA DEL CONTENIDO [0-53]:
//   [nick(+modes)] [indicador][idx/total:]canal(@net)(modes) [users]
//   └── 12-16 chars ──┘ └─────────── variable ───────────────┘ └ 5-7 ┘
//
// =============================================================================

// sb_append: Copia src a dst hasta que dst >= limit O src termina en \0
// CONTRATO:
//   - limit es "one-past-end": NO se escribe en *limit ni más allá
//   - Retorna puntero a la siguiente posición libre (puede ser == limit)
//   - Si dst >= limit al entrar, no escribe nada y retorna dst
//   - NUNCA escribe \0 al final (el caller debe hacerlo si lo necesita)
// EJEMPLO: sb_append(buf, "ABC", buf+2) escribe "AB", retorna buf+2
extern char *sb_append(char *dst, const char *src, const char *limit) __z88dk_callee;
extern char net_short_buf[];

// Extraer nombre de red del hostname: chat.freenode.net -> freenode
static char *extract_network_short(char *hostname) __z88dk_fastcall ST_NAKED
{
    (void)hostname;
    __asm
    push hl                         ; original hostname for no-short fallback
ens_find_first:
    ld a, (hl)
    or a
    jr z, ens_return_original
    cp '.'
    jr z, ens_have_first
    inc hl
    jr ens_find_first

ens_have_first:
    inc hl                          ; src = first_dot + 1
    ld d, h
    ld e, l                         ; DE = src
ens_find_second:
    ld a, (hl)
    or a
    jr z, ens_return_original
    cp '.'
    jr z, ens_copy_short
    inc hl
    jr ens_find_second

ens_copy_short:
    ld h, d
    ld l, e                         ; HL = src
    ld de, _net_short_buf           ; 12B transient status scratch
    ld b, 11
ens_copy_loop:
    ld a, (hl)
    cp '.'
    jr z, ens_copy_done
    ld (de), a
    inc hl
    inc de
    djnz ens_copy_loop
ens_copy_done:
    xor a
    ld (de), a
    pop bc                          ; discard original hostname
    ld hl, _net_short_buf
    ret

ens_return_original:
    pop hl
    ret
    __endasm;
}
uint8_t force_status_redraw = 1;

// sb_put_u8_2d: Escribe un número 0-19 como 1-2 dígitos
// CONTRATO:
//   - Escribe 1 dígito si v < 10, 2 dígitos si v >= 10
//   - NO verifica límites — el caller debe garantizar espacio
//   - Retorna puntero a la siguiente posición libre
// PRECONDICIÓN: p tiene al menos 2 bytes disponibles
// sb_put_u8_2d: frameless ASM in spectalk_asm.asm

static const char* sb_pick_status(uint8_t prefer_server_full) __z88dk_fastcall
{
    if (connection_state < STATE_TCP_CONNECTED) {
        return (connection_state == STATE_WIFI_OK) ? "wifi-ready" : "offline";
    }

    // prefer_server_full=1: prioridad a irc_server (hostname completo)
    // prefer_server_full=0: prioridad a network_name, o short(irc_server)
    if (prefer_server_full) {
        if (irc_server[0]) return irc_server;
        if (network_name[0]) return network_name;
    } else {
        if (network_name[0]) return network_name;
        if (irc_server[0]) return extract_network_short(irc_server);
    }
    return S_CONNECTED;
}

// sb_format_channel: Escribe nombre de canal con modos y red si caben
// CONTRATO:
//   - central_limit es "one-past-end" del área disponible (excluyendo ']')
//   - Reserva internamente 1 byte para ']' que el CALLER debe escribir
//   - Prioridad de truncamiento: modes > network > channel_name
//   - Retorna puntero a siguiente posición libre
// PRECONDICIÓN: p < central_limit (verificado internamente, retorna p si no)
// POSTCONDICIÓN: El caller DEBE escribir ']' después si hay espacio
static char *sb_format_channel(char *p, char *central_limit, uint8_t cur_flags) __z88dk_callee
{
    uint8_t space;
    char *chan, *modes, *net;
    uint8_t chan_len, mode_len, net_len;

    // FIX BUG-01: Si ya estamos en o más allá del límite, no hacer nada
    // (el ']' de cierre lo maneja el caller)
    if (p >= central_limit) return p;
    
    // Reservar 1 char para el ']' que escribe el caller
    space = (uint8_t)(central_limit - p);
    if (space > 1) space--;  // reservar espacio para ']'
    else return p;  // solo queda espacio para ']', no escribir nada

    chan = (current_channel_idx == 0 && network_name[0]) ? network_name : irc_channel;
    modes = (!(cur_flags & CH_FLAG_QUERY) && chan_mode[0]) ? chan_mode : NULL;
    net = NULL;

    chan_len = (uint8_t)st_strlen(chan);
    mode_len = modes ? (uint8_t)st_strlen(modes) + 2 : 0;  // "(modes)"
    net_len = 0;

    if (current_channel_idx != 0) {
        net = network_name[0] ? network_name : (irc_server[0] ? extract_network_short(irc_server) : NULL);
        if (net) net_len = (uint8_t)st_strlen(net) + 1;  // "@net"
    }

    // Greedy fit: try chan+modes+net, drop decorations that don't fit
    // Priority: channel > network > modes (modes are least important)
    if (chan_len + mode_len + net_len > space) {
        // Drop modes first (least useful info)
        modes = NULL; mode_len = 0;
        // If still doesn't fit, drop network too
        if (chan_len + net_len > space) {
            net = NULL; net_len = 0;
        }
    }

    // Render channel name (truncated if needed)
    {
        char *chan_limit = p + (space - mode_len - net_len);
        if (chan_limit >= central_limit) chan_limit = central_limit - 1;
        p = sb_append(p, chan, chan_limit);
    }

    // SAFETY-M1: literal writes '(', ')', '@' are covered by mode_len (+2)
    // and net_len (+1) in the greedy fit check above (lines 1260-1267).
    if (modes) {
        *p++ = '(';
        p = sb_append(p, modes, central_limit - (net_len ? net_len + 1 : 1));
        *p++ = ')';
    }
    if (net) {
        *p++ = '@';
        p = sb_append(p, net, central_limit - 1);
    }
    return p;
}

// =============================================================================
// draw_status_bar_real: Renderiza la barra de estado completa
// =============================================================================
// LAYOUT: [nick(+modes)] [indicator idx/total:channel(@net)(modes)] [users]
//         └─ SECCIÓN 1 ─┘ └────────────── SECCIÓN 2 ──────────────┘ └─ S3 ─┘
//
// LÍMITES USADOS:
//   sb_left_part + 11  : máx para nick (10 chars + '[')
//   sb_left_part + 15  : máx para nick+modes
//   limit_end (col 54) : inicio del reloj, fin del área dinámica
//   central_limit      : limit_end - user_len, fin de sección 2
//
// SECCIÓN 1: [nick(+modes)] — siempre presente, ~12-16 chars
// SECCIÓN 2: [canal+info] — variable, usa espacio restante
// SECCIÓN 3: [users] — opcional, 0 o 5-7 chars
//
// INVARIANTES:
//   - Siempre escribimos '[' al inicio de cada sección
//   - ']' se escribe AL FINAL de cada sección, con bounds check
//   - central_limit reserva espacio para sección 3 antes de escribir sección 2
// =============================================================================

uint8_t has_other_mention(void);

void draw_status_bar_real(void)
{
    char sb_left_part[57];
    char *p = sb_left_part;
    char *const limit_end = sb_left_part + 54;  // cols 54+ reserved for clock

    // === SECCIÓN 1: Nick y modos de usuario ===
    // Límites: nick máx 10 chars (col 1-10), modes máx 4 chars (col 12-15)
    // Formato: [nick(+modes)]
    *p++ = '[';
    if (irc_nick[0]) {
        // +11 = col 0 ('[') + 10 chars nick máximo
        p = sb_append(p, irc_nick, sb_left_part + 11);
        if (user_mode[0]) {
            // +15 = col 11 ('(') + 3 chars mode + ')' en col 15
            *p++ = '('; p = sb_append(p, user_mode, sb_left_part + 15); *p++ = ')';
        }
    } else {
        // +10 = '[' + "no-nick" (7) + margen
        p = sb_append(p, "no-nick", sb_left_part + 10);
    }
    *p++ = ']'; *p++ = ' '; *p++ = '[';

    // === SECCIÓN 3 (preparación): Contador de usuarios ===
    // Se calcula ANTES de sección 2 para reservar espacio
    // Formato: " [NNN]" = 1 + 1 + 1-3 + 1 = 4-6 chars
    uint8_t user_len = 0;

    if (irc_channel[0] && !(chan_flags & CH_FLAG_QUERY) && chan_user_count > 0) {
        char *u_end = u16_to_dec(fmt_buf, chan_user_count);
        user_len = (uint8_t)(u_end - fmt_buf) + 3;  // " [" + numero + "]"
    }

    // === SECCIÓN 2: Canal, indicadores, modos ===
    // Espacio disponible: desde p actual hasta central_limit
    // central_limit = limit_end - user_len (reserva espacio para sección 3)
    {
        char *central_limit = limit_end - user_len;

        if (has_other_mention()) *p++ = (time_second & 1) ? ' ' : '!';
        else if (other_channel_activity) *p++ = '*';

        if (channel_count > 1) {
            p = sb_put_u8_2d(p, current_channel_idx);
            *p++ = '/';
            p = sb_put_u8_2d(p, channel_count - 1);
            *p++ = ':';
        }

        // FIX BUG-01: Verificar espacio ANTES de escribir contenido
        // central_limit - 1 reserva espacio para ']'
        if (p < central_limit - 1) {
            // D10: Inline is_server_tab check instead of storing in variable
            if (current_channel_idx == 0 && st_stricmp(channels[0].name, S_SERVER) == 0) {
                p = sb_append(p, (char*)sb_pick_status(1), central_limit - 1);
            } else if (irc_channel[0]) {
                if ((chan_flags & CH_FLAG_QUERY) && current_channel_idx != 0) *p++ = '@';
                p = sb_format_channel(p, central_limit, chan_flags);
            } else if (current_channel_idx == 0) {
                p = sb_append(p, (char*)sb_pick_status(0), central_limit - 1);
            } else {
                // active slot with empty name — show placeholder
                *p++ = '#';
                if (p < central_limit - 1) *p++ = '?';
            }
        }

        // FIX BUG-01: Escribir ']' solo si hay espacio
        if (p < central_limit) *p++ = ']';
    }

    // === SECCIÓN 3 (renderizado): Escribir contador de usuarios ===
    if (user_len) {
        *p++ = ' ';
        *p++ = '[';
        p = sb_append(p, fmt_buf, limit_end - 1);  // -1 reserva espacio para ']'
        *p++ = ']';
    }

    // Rellenar con espacios hasta limit_end y terminar string
    while (p < limit_end) *p++ = ' ';
    *p = 0;

    print_status_left54_fast(sb_left_part);
    force_status_redraw = 0;

    draw_clock();
    draw_indicator(INFO_LINE, 31,
                   (connection_state >= STATE_TCP_CONNECTED) ? STATUS_GREEN :
                   (connection_state >= STATE_WIFI_OK) ? STATUS_YELLOW :
                   STATUS_RED);
}


// INPUT AREA

extern void draw_cursor_underline(uint8_t y, uint8_t col) __z88dk_callee;

void refresh_cursor_char(uint8_t idx, uint8_t show_cursor) __z88dk_callee
{
    uint8_t abs_pos = idx + 2;
    uint8_t row = INPUT_START + (abs_pos >> 6);
    uint8_t col = abs_pos & 63;

    if (row > INPUT_END) return;

    char c = (idx < line_len) ? line_buffer[idx] : ' ';
    
    // Only show cursor if both show_cursor AND cursor_visible are true
    if (show_cursor && cursor_visible) {
        // Draw character with cache, then add cursor
        put_char64_input_cached(row, col, c, ATTR_INPUT);
        draw_cursor_underline(row, col);
    } else {
        // redraw character without cache to ensure it's complete (no cursor artifacts)
        print_char64(row, col, c, ATTR_INPUT);
        // Update cache to match
        uint8_t r = row - INPUT_START;
        input_cache_char[r][col] = (uint8_t)c;
    }
}

// Wrappers to avoid 2-param call overhead (saves ~3 bytes per call site)
void cursor_show(void) { refresh_cursor_char(cursor_pos, 1); }
void cursor_hide(void) { refresh_cursor_char(cursor_pos, 0); }

void redraw_input_from(uint8_t start_pos) __z88dk_fastcall
{
    uint8_t i;
    uint8_t abs_pos;
    uint8_t row, col;

    // Full redraw handles prompt char (@ for query, > for channel) via ASM
    if (start_pos == 0) {
        redraw_input_full();
        return;
    }

    // 2. Dibujar el texto actual (usando caché normal)
    for (i = start_pos; i < line_len; i++) {
        abs_pos = i + 2;
        // Cálculo seguro de coordenadas
        row = INPUT_START + (abs_pos >> 6);
        col = abs_pos & 63;
        
        if (row > INPUT_END) break;
        put_char64_input_cached(row, col, line_buffer[i], ATTR_INPUT);
    }

    // 3. Clear from line_len to prev_line_len (handles multi-char delete)
    {
        uint8_t clear_to = input_prev_len > line_len ? input_prev_len : line_len + 1;
        for (i = line_len; i < clear_to; i++) {
            abs_pos = i + 2;
            row = INPUT_START + (abs_pos >> 6);
            col = abs_pos & 63;
            if (row > INPUT_END) break;
            put_char64_input_cached(row, col, ' ', ATTR_INPUT);
        }
        input_prev_len = line_len;
    }

    // 4. Restaurar cursor
    cursor_show();
}


void redraw_input_full(void)
{
    input_cache_invalidate();
    redraw_input_asm();
    cursor_show();
}

static void input_clear(void)
{
    // 1. Resetear variables de state
    line_len = 0;
    cursor_pos = 0;
    line_buffer[0] = 0;
    hist_pos = -1;  // Resetear puntero del historial
    
    // 2. Delegar el trabajo visual (Limpieza + Prompt + cursor)
    redraw_input_full();
}

// fast_u8_to_str: frameless ASM in spectalk_asm.asm

static void input_add_char(char c) __z88dk_fastcall
{
    // 1. Borrar cursor visual
    cursor_hide();

    // Límite: LINE_BUFFER_SIZE - 2 para dejar espacio para el terminador '\0'
    // y evitar que line_buffer[line_len] = 0 escriba fuera del buffer
    // Con LINE_BUFFER_SIZE=128, el máximo line_len es 126, y escribimos en [127] el '\0'
    if (c >= 32 && c < 127 && line_len < (LINE_BUFFER_SIZE - 2)) {
        
        // A. CASO INSERTAR: Usamos memmove (estándar) en lugar de ASM manual
        // memmove gestiona el solapamiento automáticamente
        if (cursor_pos < line_len) {
           text_shift_right(line_buffer + cursor_pos, line_len - cursor_pos);
        }
        
        // B. Escribir caracter
        line_buffer[cursor_pos] = c;
        line_len++;
        cursor_pos++;
        line_buffer[line_len] = 0;
        
        // Redibujar desde el cambio
        // PD5: cursor_pos already incremented, so screen_abs = (cursor_pos-1)+2 = cursor_pos+1
        if (cursor_pos == line_len) {
            // Append rápido
            uint8_t abs_pos = cursor_pos + 1;
            uint8_t row = INPUT_START + (abs_pos >> 6);
            if (row <= INPUT_END) put_char64_input_cached(row, abs_pos & 63, c, ATTR_INPUT);
            input_prev_len = line_len;
            cursor_show();
        } else {
            redraw_input_from(cursor_pos - 1);
        }
    }
}

static void input_backspace(void)
{
    if (cursor_pos > 0) {
        uint8_t old_len;

        // OPTIMIZACIÓN: Eliminada la llamada redundante a refresh_cursor_char.
        // Redraw_input_from ya asume la limpieza del final del string.
        cursor_hide();
        old_len = line_len;
        cursor_pos--;

        text_shift_left(&line_buffer[cursor_pos], (uint16_t)(old_len - cursor_pos));

        line_len = (uint8_t)(old_len - 1);

        redraw_input_from(cursor_pos);
    }
}


// Word navigation — ASM in spectalk_asm.asm
extern uint8_t key_ss_arrow(void);  // 0=none, 1=SS+LEFT, 2=SS+RIGHT, 3=SS+BKSP, 4=SS+UP, 5=SS+DOWN
extern void input_word_left(void);
extern void input_word_right(void);
extern void input_delete_word(void);
extern void input_line_start(void);
extern void input_line_end(void);

// PD1: set_input_busy() removed — cursor_hide()/cursor_show() do the same job

// KEYBOARD HANDLING
uint8_t last_k;
uint8_t repeat_timer;
uint8_t debounce_zero;

// read_key is implemented in spectalk_asm.asm for size optimization


#ifndef SPECTALK_SPECTRANEXT
void uart_send_crlf(void) __z88dk_fastcall
{
    ay_uart_send('\r');
    ay_uart_send('\n');
}

void uart_send_line(const char *s) __z88dk_fastcall
{
    uart_send_string(s);
    uart_send_crlf();
}
#endif

// Classic clock acquisition lives in clock_classic.c.

// AT COMMAND HELPERS
// try_read_line_nodrain() está implementada en spectalk_asm.asm para mejor rendimiento

uint8_t wait_for_response(const char *expected, uint16_t max_frames) __z88dk_callee
{
    uint16_t frames = 0;
    rx_pos = 0;
    
    while (frames < max_frames) {
        if (uart_tx_failed) return 0;
        frame_wait_drain();
        
        if (in_inkey() == KEY_BREAK) return 0;  // BREAK = cancel

        if (try_read_line_nodrain()) {
            // FIX P0-1: Verificar longitud antes de acceder a índices fijos
            // H11: 16-bit head read — little-endian magic numbers
            if (rx_last_len >= 2) {
                uint16_t h2 = *(uint16_t *)rx_line;
                if (h2 == 0x5245 /* "ER" */) return 0;  // ERROR
                if (h2 == 0x4146 /* "FA" */) return 0;  // FAIL
                // Si no hay expected específico, OK es suficiente
                if (!expected && h2 == 0x4B4F /* "OK" */) return 1;
            }
            // OPT-02: Usar st_stristr (ASM) en lugar de strstr (stdlib)
            if (expected && st_stristr(rx_line, expected) != NULL) return 1;
            rx_pos = 0;
        }
        
        frames++;
    }
    
    return 0;
}

#ifndef SPECTALK_SPECTRANEXT
// Classic/native Next ESP AT transport; Spectranext uses ROM sockets.
// Wait for a single prompt character, capturing received data into rx_line.
// On timeout, rx_line contains what was received (NUL-terminated) for inspection.
uint8_t wait_for_prompt_char(uint8_t prompt_ch, uint16_t max_frames) __z88dk_callee
{
    uint16_t frames = 0;
    int16_t c;
    uint8_t wp = 0;

    while (frames < max_frames) {
        if (uart_tx_failed) return 0;
        frame_wait_drain();

        if (in_inkey() == KEY_BREAK) { rx_line[0] = '\0'; return 0; }

        while ((c = rb_pop()) != -1) {
            if ((uint8_t)c == prompt_ch) { rx_line[wp] = '\0'; return 1; }
            if (wp < 254) rx_line[wp++] = (uint8_t)c;
        }

        frames++;
    }

    rx_line[wp] = '\0';
    return 0;
}

// Helper para comandos AT de configuración (ahorra código repetido)
uint8_t esp_at_cmd(const char *cmd) __z88dk_fastcall
{
    uart_send_line(cmd);
    return wait_for_response(S_OK, 30);
}

// ESP/WIFI INITIALIZATION
// OPT L1: rx_drop_buffered eliminada (no usada)

// Helper para comandos AT simples durante inicialización
// Envía comando y espera OK o timeout corto
static void esp_hard_cmd(const char *cmd) __z88dk_fastcall {
    uart_send_line(cmd);
    // Reutilizamos wait_for_response para ahorrar bytes
    wait_for_response(NULL, 30);
    rx_pos = 0;
}

#ifndef SPECTALK_NEXT
// Session-only: the ZX-Uno-style UART holds one byte and raises RTS to the
// ESP CTS input; without ESP CTS flow control no multi-byte reply survives.
static const char S_AT_UART_CTS[] = "AT+UART_CUR=115200,8,1,0,2";
#endif

uint8_t esp_init(void)
{
#ifndef SPECTALK_NEXT
    uint8_t i;
#else
    uint8_t reset_tries = 2;
    uint8_t wifi_probes = 0;
#endif
    uint16_t frames;

    if (uart_tx_failed) goto esp_init_fail;

#ifdef SPECTALK_NEXT
next_esp_start:
#endif
    ay_uart_init();

#ifndef SPECTALK_NEXT
    // waitr a que la UART se estabilice
    for (i = 0; i < 10; i++) frame_wait();
#endif
    flush_all_rx_buffers();

#ifdef SPECTALK_NEXT
    // Fast path: reuse an ESP already in command mode at 115200 baud.
    uart_send_line(S_AT_CMD);
    if (!wait_for_response(NULL, 4)) {
        if (in_inkey() == KEY_BREAK) goto esp_init_fail;
        goto next_esp_reset;
    }
#else
    // 1. Intentar salir del modo transparente (+++)
    wait_drain(55);  // 1.1s silencio
    uart_send_string("+++");
    wait_drain(55);  // 1.1s silencio
    flush_all_rx_buffers();
#endif

    // 2. Initialization commands (sequential — mixed extern/literal array
    //    causes garbage pointers on z88dk/SDCC, see audit C01)
    esp_hard_cmd(S_AT_CIPMODE0);
    esp_hard_cmd(S_AT_CIPCLOSE);
    esp_hard_cmd("ATE0");
    esp_hard_cmd(S_AT_CIPSERVER0);
#ifdef SPECTALK_NEXT
    // This must succeed: an inherited mux/server session is not safe to reuse.
    if (!esp_at_cmd(S_AT_CIPMUX0)) {
        if (in_inkey() == KEY_BREAK) goto esp_init_fail;
        goto next_esp_reset;
    }
    rx_pos = 0;
#else
    esp_hard_cmd(S_AT_CIPMUX0);
#endif
    
#ifdef SPECTALK_NEXT
next_wifi_probe:
#endif
    // 3. Test final AT - OPT M7
    uart_send_line(S_AT_CMD);
    
    rx_pos = 0;
    
    // Timeout ~3 segundos
    for (frames = 0; frames < 150; frames++) {
        if (uart_tx_failed) goto esp_init_fail;
        frame_wait_drain();
#ifdef SPECTALK_NEXT
        if (in_inkey() == KEY_BREAK) goto esp_init_fail;
#endif
        
        if (try_read_line_nodrain()) {
            // FIX P0-1: Verificar longitud antes de acceder a índices
            if (rx_last_len >= 2 && rx_line[0] == 'O' && rx_line[1] == 'K') {
                // ESP responds — check if WiFi has an IP
                uart_send_line("AT+CIFSR");
                rx_pos = 0;
                {
                    uint8_t has_ip = 0;
                    uint8_t w;
                    for (w = 0; w < 100; w++) {
                        frame_wait_drain();
#ifdef SPECTALK_NEXT
                        if (in_inkey() == KEY_BREAK) goto esp_init_fail;
#endif
                        if (try_read_line_nodrain()) {
                            // FIX P0-1: Verificar longitud
                            if (rx_last_len >= 1 && rx_line[0] == '+' && st_stristr(rx_line, "STAIP")) {
                                if (!st_stristr(rx_line, "0.0.0.0")) has_ip = 1;
                            }
                            if (rx_last_len >= 2 && rx_line[0] == 'O' && rx_line[1] == 'K') break;
                            rx_pos = 0;
                        }
                    }
                    closed_reported = 0;
                    if (has_ip) {
#ifdef SPECTALK_NEXT
                        /* A non-zero station IP is sufficient for this IRC
                         * client and covers firmwares that reject CWJAP?. */
                        connection_state = STATE_WIFI_OK;
#else
                        // Verify actual AP association (ESP may cache stale IP)
                        uart_send_line("AT+CWJAP?");
                        rx_pos = 0;
                        has_ip = 0;  // Reset - must confirm AP
                        {
                            uint8_t w2;
                            for (w2 = 0; w2 < 100; w2++) {
                                frame_wait_drain();
                                if (try_read_line_nodrain()) {
                                    // FIX P0-1: Verificar longitud antes de índices fijos
                                    if (rx_last_len >= 4) {
                                        // +CWJAP:"ssid"... means connected
                                        if (rx_line[0] == '+' && rx_line[1] == 'C' &&
                                            rx_line[2] == 'W' && rx_line[3] == 'J') {
                                            has_ip = 1;
                                        }
                                    }
                                    if (rx_last_len >= 2) {
                                        // "No AP" means not connected
                                        if (rx_line[0] == 'N' && rx_line[1] == 'o') {
                                            has_ip = 0;
                                        }
                                        if (rx_line[0] == 'O' && rx_line[1] == 'K') break;
                                    }
                                    rx_pos = 0;
                                }
                            }
                        }
                        if (has_ip) {
                            connection_state = STATE_WIFI_OK;
                        } else {
                            connection_state = STATE_DISCONNECTED;
                        }
#endif
                    } else {
                        connection_state = STATE_DISCONNECTED;
                    }
                }
#ifdef SPECTALK_NEXT
                if (connection_state != STATE_WIFI_OK) {
                    if (wifi_probes) {
                        wifi_probes--;
                        if (wifi_probes) {
                            wait_drain(25);
                            flush_all_rx_buffers();
                            goto next_wifi_probe;
                        }
                    }
                    if (reset_tries) goto next_esp_reset;
                }
#endif
                return 1;  // ESP init OK (WiFi status in connection_state)
            }
            rx_pos = 0;
        }
    }

#ifdef SPECTALK_NEXT
next_esp_reset:
    if (!reset_tries) goto esp_init_fail;
    reset_tries--;
    overlay_exec(4, 4);
    flush_all_rx_buffers();
    if (!wait_for_response("ready", 251)) {
        if (in_inkey() == KEY_BREAK) goto esp_init_fail;
        goto next_esp_reset;
    }
    wifi_probes = 12;
    goto next_esp_start;
#else
    // No OK: ESP CTS flow control may be off, which garbles every reply on
    // this UART. Enable it for this session so the next attempt can pass;
    // a working ESP never gets here, and flash UART_DEF is untouched.
    esp_hard_cmd(S_AT_UART_CTS);
#endif

esp_init_fail:
    connection_state = STATE_DISCONNECTED;
    return 0;  // ESP not responding
}
#endif

// Time synchronization function
// OPT L2: sync_time() eliminada - inlined en call site

// Force-close any active TCP connection.
// FIX ChatGPT audit: CENTRALIZED session reset - ALL disconnection paths MUST use this
// to avoid forgotten flags. Do NOT reset state manually elsewhere.
// In transparent mode, must exit with +++ first
void force_disconnect(void)
{
    if (disconnecting_in_progress) return;
    disconnecting_in_progress = 1;

    if (overlay_mode == OVERLAY_ABOUT) {
        overlay_call(1);       /* close ABOUT DAT before ring_buffer is reused */
        overlay_exit_full();
    }
    
    net_close();

    connection_state = uart_tx_failed ? STATE_DISCONNECTED : STATE_WIFI_OK;
    closed_reported = 0;
    
    server_silence_frames = 0;
    keepalive_ping_sent = 0;
    keepalive_timeout = 0;
    lagmeter_counter = 0;

    friends_ison_sent = 0;
    
    irc_is_away = 0;
    away_message[0] = '\0';
    away_reply_cd = 0;
    autoaway_counter = 0;
    autoaway_active = 0;
    ping_latency = 0;
    
    // Keep setup state: the Classic ESP configuration persists across links.
    clock_waiting = 0;
    clock_synced = 0;            // re-sync clock on reconnect
    
    network_name[0] = '\0';
    user_mode[0] = '\0';
    
    names_pending = 0;
    names_timeout_frames = 0;
    names_target_channel[0] = '\0';
    counting_new_users = 0;
    names_was_manual = 0;
    notif_cancel_current();
    last_pm_nick[0] = '\0';
    autojoin_defer_flags = 0;
    autojoin_ident_grace = 0;
    if (auth_mode == AUTH_PENDING) {
        auth_mode = AUTH_LEGACY;
        nickserv_nick[0] = nickserv_pass[0] = 0;
    }
    
    cancel_search_state();
    post_cancel_quiet = 0;
    count_sync_idle_frames = 0;
    count_sync_quits = 0;
    
    reset_rx_state();

    reset_all_channels();

    disconnecting_in_progress = 0;
}
// =============================================================================
// OPTIMIZED SENDING HELPERS (STREAMING)
// =============================================================================

// Internal: envía comando IRC con 0, 1 o 2 parámetros (implementada en ASM)
extern void irc_send_cmd_internal(const char *cmd, const char *p1, const char *p2);

// Envía "CMD param\r\n"
// Unified PONG: "PONG <server> :<token>\r\n"
void irc_send_pong(const char *token) __z88dk_fastcall
{
    net_send_string(S_PONG);
    net_send_string(irc_server);
    net_send_string(S_SP_COLON);
    net_send_line(token);
}

// irc_send_cmd1/cmd2: frameless ASM in spectalk_asm.asm

// Envía "PRIVMSG <service> :IDENTIFY <pass>\r\n"
// Uses the configured nickserv_nick, otherwise defaults to "NickServ"
void send_identify(const char *pass) __z88dk_fastcall
{
    if (auth_mode == AUTH_PENDING) return;
    net_send_string(S_PRIVMSG);
    net_send_string(nickserv_nick[0] ? (const char *)nickserv_nick : S_NICKSERV);
    net_send_string(auth_mode >= AUTH_LEARNED ? S_SP_COLON : S_IDENTIFY_CMD);
    net_send_line(pass);
}

// Enviar ISON con hasta 3 nicks de amigos (una sola vez por sesión IRC).
void irc_check_friends_online(void)
{
    // Reuse rx_line as temp buffer (not receiving during send)
    uint8_t i, any = 0;
    char *d = rx_line;

    if (friends_ison_sent) return;
    if (connection_state < STATE_TCP_CONNECTED) return;

    *d = '\0';

    for (i = 0; i < MAX_FRIENDS; i++) {
        const char *s = friend_nicks[i];
        if (!s[0]) continue;
        if (any) *d++ = ' ';
        st_copy_n(d, s, IRC_NICK_SIZE);
        while (*d) d++;
        any = 1;
    }

    if (!any || !rx_line[0]) return;
    friends_ison_sent = 1;
    irc_send_cmd1("ISON", rx_line);
}

// OPT-P2-B: Shared nick-in-use retry logic (dedup h_numeric_433 + cmd_connect)
void nick_try_alternate(void)
{
    uint8_t len = 0;
    while (irc_nick[len] && len < IRC_NICK_SIZE - 2) len++;
    if (len >= IRC_NICK_SIZE - 2) {
        // Nick at max length: rotate last char to generate variants
        char c = irc_nick[len - 1];
        if (c == '_') c = '0';
        else if (c >= '0' && c < '9') c++;
        else c = '_';
        irc_nick[len - 1] = c;
    } else {
        irc_nick[len] = '_';
        irc_nick[len + 1] = '\0';
    }

    set_attr_sys();
    main_puts(S_NICK_INUSE);
    main_print(irc_nick);

    net_send_string(S_NICK_SP);
    net_send_line(irc_nick);
}

void irc_send_privmsg(const char *target, const char *msg) __z88dk_callee
{
    // Auto-away: reset counter on activity, clear if auto-away active
    autoaway_counter = 0;
    if (autoaway_active) {
        net_send_line(S_AWAY_CMD);
        autoaway_active = 0;
    }
    
    // 1. ENVÍO DIRECTO
    if (connection_state >= STATE_TCP_CONNECTED) {
        net_send_string(S_PRIVMSG);
        net_send_string(target);
        net_send_string(S_SP_COLON);
        net_send_line(msg);
    }

    // 2. MOSTRAR EN screen
    if (IS_CHAN_PREFIX(target[0])) {
        // Mensaje en canal: hora, nick dedicado, mensaje del canal
        main_print_time_prefix();

        // En 64 cols: imprimir "nick> " entero con ATTR_MSG_NICK
        set_attr_nick();
        main_puts2(irc_nick, S_PROMPT);

        set_attr_chan();
        main_print_wrapped_ram((char*)msg);
    } else {
        int8_t query_idx = find_query(target);

        main_print_time_prefix();

        if (query_idx >= 0 && (uint8_t)query_idx == current_channel_idx) {
            // En la ventana del privado: mantener "YO> msg"
            set_attr_nick();
            main_puts2(irc_nick, S_PROMPT);

            set_attr_priv();
            main_print_wrapped_ram((char*)msg);
        } else {
            // Fuera de la ventana: >> NICKNAME (receptor) : MSG
            // Requisito: ">> NICKNAME (amarillo): MSG (verde)"
            set_attr_priv();
            main_puts2(S_ARROW_OUT, target);
            main_puts(S_COLON_SP);

            current_attr = ATTR_MSG_SELF;
            main_print_wrapped_ram((char*)msg);
        }
    }
}

// ============================================================
// REST OF MAIN MODULE (apply_theme, draw_banner, init_screen, main)
// ============================================================

void apply_theme(void)
{
    uint8_t *t, *d;
    uint8_t i;

    // Protección de rango
    // PD3: underflow trick — single comparison vs dual range check
    if ((uint8_t)(current_theme - 1) > 2) current_theme = 1;
    t = theme_raw + (current_theme - 1) * 25;

    // Copy 20 attribute bytes from theme_raw into theme_attrs[]
    d = theme_attrs;
    for (i = 20; i != 0; i--) *d++ = *t++;
    theme_badge_marker = t[1];

    // Auto-detect nick coloring: mono theme if nick INK == chan INK
    nick_color_mode = ((theme_attrs[11] & 7) != (theme_attrs[2] & 7)) ? 1 : 0;

    // 2. Aplicar cambios físicos a la pantalla
    set_border(BORDER_COLOR); 
    
    // "Barrer" la pantalla con los nuevos colores base (esto borraba el indicador)
    reapply_screen_attributes(); 
    
    // 3. RESTAURAR UI INMEDIATAMENTE (La solución)
    draw_banner();

    // Forzamos el flag para que draw_status_bar_real repinte el texto
    force_status_redraw = 1; 
    
    // Pintamos la barra Y EL INDICADOR ahora mismo, encima del barrido
    draw_status_bar_real(); 
    
    redraw_input_full();
}

// Declaración de función ASM (fastcall: count en L)
extern void draw_badge_dither(uint8_t count) __z88dk_fastcall;

static uint8_t badge_flashing;
static uint8_t flash_timer;

void badge_flash_on(void)
{
    if (theme_badge_marker != 0x40 || ((ATTR_BANNER >> 3) & 0x07)) return;
    badge_flashing = 1;
    flash_timer = 0;
}

void badge_flash_off(void)
{
    uint8_t attr;
    uint8_t top;
    uint8_t bot;
    if (!badge_flashing) return;
    badge_flashing = 0;
    attr = ATTR_BANNER;
    top = attr | 0x40;
    bot = attr & 0xBF;
    *(uint8_t *)0x581E = top;
    *(uint8_t *)0x581F = top;
    *(uint8_t *)0x583E = bot;
    *(uint8_t *)0x583F = bot;
}

// draw_banner — overlay SPCTLK1 entry 1 (banner_render_ovl)
void draw_banner(void)
{
    badge_flashing = 0; /* W12: reset flash state before redrawing banner */
    overlay_exec(0, 1); /* SPCTLK1, entry 1 */
}

void init_screen(void)
{
    // 1. Limpieza Física (ASM): Borra pixels y aplica atributos base del tema
    cls_fast();
    
    // 2. Posición inicial del texto (línea 2 = MAIN_START)
    main_line = MAIN_START; 
    main_col = 0;
    
    // 3. Restaurar elementos fijos de la interfaz
    draw_banner();
    
    // 4. Pintar barra de estado inmediatamente (cls_fast la borró)
    force_status_redraw = 1;
    draw_status_bar_real();
    
    // 5. Resetear atributos de texto al valor por defecto
    set_attr_chan();
}


// =============================================================================
// OPTIMIZED UI HELPERS (Saves ROM space vs Macros)
// =============================================================================

// Auto-centered ikkle notification
void notif_center(const char *str, uint8_t attr)
{
    uint8_t len = st_strlen(str);
    notif_draw((len < 64) ? ((64 - len) >> 1) : 0, str, attr);
}

void notif_cancel_current(void)
{
    notif_timeout = 0;
    notif_is_pm = 0;
    notif_buf[0] = '\0';
    notif_clear();
}

// Notification slide-in state
static uint8_t notif_slide_len;  // total chars to reveal
static uint8_t notif_slide_pos;  // chars currently visible
static uint8_t notif_attr;       // render attribute

// Unified notification dispatcher: ikkle (row 20) or classic (chat area)
void notify(const char *msg, uint8_t attr) __z88dk_callee
{
    if (notif_enabled) {
        if (notif_timeout && notif_buf[0]) {
            if (st_stricmp(notif_buf, msg) == 0) return;
            { char *sep = strchr(notif_buf, 1);
              char *d, *end = notif_buf + 62;
              if (sep) {
                d = notif_buf;
                { char *s = sep + 1; while (*s) *d++ = *s++; }
              } else {
                d = notif_buf + st_strlen(notif_buf);
              }
              if (d + 3 < end) { *d++ = ' '; *d++ = '-'; *d++ = 1; }
              while (*msg && d < end) *d++ = *msg++;
              *d = 0;
            }
        } else {
            st_copy_n(notif_buf, msg, 62);
        }
        // Strip '#'/'&' and UTF-8 on notif_buf (audit W04: never write through const msg)
        { char *r = notif_buf, *w = notif_buf;
          while (*r) { if (*r != '#' && *r != '&') *w++ = *r; r++; }
          *w = 0; }
        utf8_to_ascii(notif_buf);

        notif_slide_len = st_strlen(notif_buf);
        notif_slide_pos = 0;
        notif_attr = attr;
        notif_timeout = NOTIF_TIMEOUT_FRAMES;  // ~5s at 50 Hz; 150f proved too short in practice
    } else {
        if (main_col) main_newline();
        current_attr = attr;
        main_print_time_prefix();
        if (msg == temp_input) main_print_wrapped_clean((char *)msg);
        else main_print(msg);
    }
}

void ui_usage(const char *a) __z88dk_fastcall
{
    set_attr_err();
    main_puts("Usage: ");
    main_print(a);
}


// =============================================================================
// CONFIGURATION FILE LOADER (esxDOS)
// Reads /SYS/CONFIG/SPECTALK.CFG or /SYS/SPECTALK.CFG
// Uses ring_buffer[] as temporary read buffer (2048 bytes, unused at startup)
// =============================================================================

// esxDOS wrappers - parameter passing via globals (no ABI risk)
// These are defined in spectalk_asm.asm
// Try to open and read a config file into ring_buffer[]
// ring_buffer is 2048 bytes and unused at startup (before UART activity)
// Return pointer to next comma-separated token (NUL-terminates it).
// Returns NULL when no more tokens. Skips leading spaces.
#ifndef SPECTALK_SPECTRANEXT
#include "config_apply.c"
#endif

#if defined(SPECTALK_SPECTRANEXT) || defined(SPECTALK_NEXT)
uint8_t config_load(void)
{
    overlay_slot[0] = 0;
#ifdef SPECTALK_NEXT
    overlay_exec(4, 5);
#else
    overlay_exec(4, 4);
#endif
    return overlay_slot[0];
}
#else
#include "config_load.c"
#endif

// MAIN FUNCTION

void main(void)
{
    uint8_t c;
    uint8_t cfg_ok;
    uint8_t can_autoconnect;
    
    has_esxdos = esx_detect();

#ifdef SPECTALK_SPECTRANEXT
    // Fatal: no Spectranext cartridge/storage
    if (!has_esxdos) fatal_msg("REQUIRES SPECTRANEXT!");
#elif defined(SPECTALK_NEXT)
    if (!has_esxdos) fatal_msg("REQUIRES NEXTZXOS!");
#else
    // Fatal: no divMMC/esxDOS
    if (!has_esxdos) fatal_msg("REQUIRES DIVMMC!");
#endif
    // Load font + themes + BPE dict from SPECTALK.DAT
    {
        extern uint8_t font_lut[];
#if defined(SPECTALK_NEXT) || defined(SPECTALK_SPECTRANEXT)
        dat_open();
#else
        esx_fopen(K_DAT);
#endif
#ifndef SPECTALK_NEXT
        if (!esx_handle) fatal_msg("DAT NOT FOUND!");
#endif
        esx_buf = (uint16_t)font_lut;
        esx_count = 373;
#ifdef SPECTALK_NEXT
        dat_fread();
#else
        esx_fread();
        esx_fclose();
#endif
        if (esx_result < 373) fatal_msg("DAT TRUNCATED!");
        if (!bpe_validate()) fatal_msg("DAT CORRUPT!");
    }

    cfg_ok = config_load();  // Load settings before theme/screen init
    apply_theme();
    init_screen();
    if (sntp_tz == TZ_RTC) {
        clock_seed_local();  // Cold RTC seed: driver API, M_GETDATE, PCF fallback.
        if (sntp_tz == TZ_RTC) draw_status_bar_real();
    }

    main_line = MAIN_START;
    main_col = 0;
    set_attr_sys();
    main_print(S_APPNAME);
    main_print(S_APPDESC);
    main_print(S_COPYRIGHT);
    main_hline();

    bookmark_startup();

    // --- Initialization ---
    {
        uint8_t retries = 3;
        while (retries--) {
            set_attr_priv();
            main_puts(S_INIT_DOTS);
            if (net_init()) { main_newline(); break; }
            main_putc(' '); set_attr_err(); main_puts(S_FAIL); main_newline();
            if (retries) {
                ui_sys("Press any key to retry...");
                // FIX: Drenar la UART mientras esperamos la tecla
                do { net_frame_wait(); } while (!in_inkey());
                do { net_frame_wait(); } while (in_inkey());
            }
        }
    }
    
    // Check WiFi
    set_attr_priv();
    main_puts("Checking connection...");
    
    if (connection_state < STATE_WIFI_OK) {
        main_putc(' '); set_attr_err(); main_puts("NO WIFI"); main_newline();
        ui_sys("Connect to WiFi first or try !init");
    } else {
        main_newline();
        clock_init();  // No-op when RTC mode is active and valid.
    }
    // -------------------------------------------

    set_attr_sys();
    main_hline();
    main_print("Type !help, !about or !changelog for more info");

    // Autoconnect only if ALL conditions are met
    can_autoconnect = autoconnect && cfg_ok && irc_server[0]
                      && irc_nick[0]
                      && connection_state >= STATE_WIFI_OK;

    if (cfg_ok) {
        main_puts("Config loaded.");
        if (irc_server[0]) {
            if (can_autoconnect) {
                main_puts(" Autoconnecting");
                main_puts2(S_AS_SP, irc_nick);
                main_putc(' '); main_puts(S_DOTS3);
            } else if (!autoconnect) {
                main_puts(" /server to connect");
                if (irc_nick[0]) { main_puts2(S_AS_SP, irc_nick); }
            }
        }
        main_newline();
    } else {
        main_print("Tip: /nick Name then /server host");
    }
    main_newline();

    current_attr = ATTR_MAIN_BG;

    draw_status_bar();
    input_clear();

    {
        uint8_t prev_caps_mode = caps_lock_mode;
        uint8_t prev_shift_held = 0;
        uint8_t sntp_timer = 75;  // first SNTP query after ~0.5s (not 2s)
        uint8_t autoconnect_delay = can_autoconnect ? AUTOCONNECT_DELAY_FRAMES : 0;  // ~5 sec (SNTP needs time)

        // FIX: Ocultar cursor durante autoconnect countdown
        if (autoconnect_delay) { cursor_visible = 0; redraw_input_full(); }

        // FIX: muestrear SHIFT 1 vez por frame y reutilizarlo
        uint8_t shift_held = 0;
        uint8_t ss_held = 0;    // SS+arrow state tracking
        uint8_t ss_repeat = 0;  // auto-repeat timer
        static uint8_t about_anim_last = 0;  /* FRAMES low byte at last globe tick */

        // Sync frame counter before entering main loop
        last_frames_lo = *FRAMES_ADDR;
        tick_accum = 0;

        while (1) {
#ifdef SPECTALK_NEXT
            frame_wait_drain(); // No CTS: receive throughout the frame wait.
#else
            frame_wait(); // Sync to the active video cadence
#endif
#ifndef SPECTALK_SPECTRANEXT
            if (uart_tx_failed == 1) {
                net_disconnect();
                uart_tx_failed = 2;
                ui_err("UART TX failed: reset ESP and restart");
                draw_status_bar();
            }
#endif
            
            // Read system FRAMES (23672) low byte and compute elapsed frames.
            // Counts serviced ROM ticks; interrupts masked for a whole frame
            // cannot be recovered from FRAMES.
            {
            uint8_t now_lo = *FRAMES_ADDR;
            uint8_t elapsed = now_lo - last_frames_lo;  // wraps correctly (uint8)
            last_frames_lo = now_lo;
#ifdef SPECTALK_NEXT
            tick_accum += (uint16_t)elapsed << 6;
#else
            tick_accum += elapsed;
#endif
            // Post-cancel quiet window (suppresses h_default_cmd garbage from
            // residuos de lista cancelada). Decremento independiente de ticks.
            if (post_cancel_quiet) {
                if (post_cancel_quiet <= elapsed) post_cancel_quiet = 0;
                else post_cancel_quiet -= elapsed;
            }
            if (autojoin_ident_grace) {
                if (autojoin_ident_grace <= elapsed) {
                    autojoin_ident_grace = 0;
                    if (autojoin_defer_flags & AUTOJOIN_IDENT_WAIT) {
                        autojoin_defer_flags &= (uint8_t)~AUTOJOIN_IDENT_WAIT;
                        session_autojoin_try();
                    }
                } else {
                    autojoin_ident_grace -= elapsed;
                }
            }
            // H3: fold both notif blocks under shared `notif_timeout && !overlay_mode`
            // Slide-in animation runs first, then timeout decrement/clear.
            // Skip during overlays: overlay footer is static, must persist until exit.
            if (notif_timeout && !overlay_mode) {
                if (notif_slide_pos < notif_slide_len) {
                    notif_slide_pos += 6;
                    if (notif_slide_pos > notif_slide_len) notif_slide_pos = notif_slide_len;
                    notif_draw(64 - notif_slide_pos,
                               notif_buf + notif_slide_len - notif_slide_pos,
                               notif_attr);
                }
                if (notif_timeout <= elapsed) {
                    notif_timeout = 0;
                    notif_is_pm = 0;
                    notif_buf[0] = 0;
                    notif_clear();
                } else {
                    notif_timeout -= elapsed;
                }
            }
            }
            {
#ifdef SPECTALK_NEXT
            uint16_t second_ticks = next_clock_second();
#else
#define second_ticks 50
#endif
            while (tick_accum >= second_ticks) {
                tick_accum -= second_ticks;
                time_second++;

                // Away auto-reply global cooldown (1 tick per second)
                if (away_reply_cd) away_reply_cd--;
                
                if (has_other_mention()) status_bar_dirty = 1;
                
                // Auto-away check (cada segundo, si configurado y conectado)
                if (autoaway_minutes && connection_state == STATE_IRC_READY && !irc_is_away) {
                    if (autoaway_counter < 65000) autoaway_counter++;  // Prevenir overflow
                    if (autoaway_counter >= ((uint16_t)autoaway_minutes << 6) - ((uint16_t)autoaway_minutes << 2)) {
                        net_send_string("AWAY :");
                        net_send_line(S_AUTOAWAY);
                        st_copy_n(away_message, S_AUTOAWAY, sizeof(away_message));
                        autoaway_active = 1;
                        irc_is_away = 1;  // Prevenir envío duplicado antes de recibir 306
                        autoaway_counter = 0;  // Reset para evitar re-trigger
                    }
                }
                
                if (time_second >= 60) {
                    time_second = 0;
                    time_minute++;
                    uptime_minutes++;
                    if (time_minute >= 60) {
                        time_minute = 0;
                        time_hour++;
                        if (time_hour >= 24) time_hour = 0;
                    }
                    // Actualizar reloj en pantalla cada minuto, también en overlays.
                    draw_clock();
                }
            }
            
            }
#ifndef SPECTALK_NEXT
#undef second_ticks
#endif
            // 1. TAREAS DE BAJA FRECUENCIA
            clock_init();  // self-guarded: no-op if RTC, already sent, or no WiFi
            if (clock_setup_state || names_pending) {
                if (clock_setup_state && !clock_synced) {
                    if (!clock_waiting) {
                        if (clock_setup_state == 2 && overlay_mode == OVERLAY_NONE) {
                            clock_sync_fallback();
                            sntp_timer = 25;  // Retry after ~1.5 sec
                        } else if (++sntp_timer >= 100) {
                            clock_query();
                            sntp_timer = 25;
                        }
                    }
                }
                if (names_pending) {
                    if (++names_timeout_frames >= NAMES_TIMEOUT_FRAMES) {
                        names_finish_incomplete();
                    }
                }
            }
            
            // 1.1. AUTOCONNECT: countdown then connect
            if (autoconnect_delay) {
                if (--autoconnect_delay == 0) {
                    if (irc_server[0] && connection_state == STATE_WIFI_OK) {
                        { char ac[] = "/server"; parse_user_input(ac); }
                    } else {
                        // Conditions not met — restore cursor
                        cursor_visible = 1;
                        redraw_input_full();
                    }
                }
            }
            
            // 1.5. KEEP-ALIVE & LAGMETER
            if (connection_state == STATE_IRC_READY) {
                server_silence_frames++;
                lagmeter_counter++;

                if (overlay_mode == OVERLAY_ABOUT) {
                    /* ABOUT owns ring_buffer and consumes only lightweight
                     * parser pump. Do not self-timeout or launch new local
                     * probes until the ABOUT parser path is hardware-proven;
                     * about_pump() still handles server PING/PONG traffic. */
                } else if (keepalive_ping_sent) {
                    // Waiting for PONG - check timeout
                    if (++keepalive_timeout >= KEEPALIVE_TIMEOUT_FRAMES &&
                        server_silence_frames >= KEEPALIVE_TIMEOUT_FRAMES) {
                        // No response to PING - connection is dead
                        set_attr_err();
                        main_puts(S_TIMEOUT);
                        main_print(" (no response)");
                        net_disconnect();
                        draw_status_bar();
                    }
                } else if (server_silence_frames >= KEEPALIVE_SILENCE_FRAMES && !pagination_active) {
                    // No server activity for too long - send PING to check
                    net_send_string("PING :keepalive\r\n");
                    keepalive_ping_sent = 1;
                    keepalive_timeout = 0;
                    lagmeter_counter = 0;
                } else if (lagmeter_counter >= LAGMETER_INTERVAL_FRAMES && 
                           !pagination_active && !buffer_pressure) {
                    // Periodic lag measurement (postponed during heavy traffic)
                    net_send_string("PING :lag\r\n");
                    keepalive_ping_sent = 1;
                    keepalive_timeout = 0;
                    lagmeter_counter = 0;
                }
            } else {
                // Not connected - reset counters
                server_silence_frames = 0;
                keepalive_ping_sent = 0;
                lagmeter_counter = 0;
            }

            // 1.6. SEARCH FLUSH & TIMEOUT
            if (pagination_active && search_pending_type != PEND_NONE) {
                // Fase de drenaje activo
                if (search_flush_state == 1) {
                    // Drenar UART al ring buffer
                    net_pump_rx();
                    
                    // pending == 0  <=> ring vacío y sin línea parcial
                    if (rx_pos == 0 && rb_head == rb_tail) {
                        // Buffer vacío - contar frames estables
                        if (++search_flush_stable >= 10) {
                            // Drenaje completo - enviar comando
                            search_flush_state = 2;
                            flush_all_rx_buffers();
                            send_pending_search_command();
                            pagination_timeout = 0;
                        }
                    } else {
                        // Hay datos - descartar y reiniciar contador
                        search_flush_stable = 0;
                        flush_all_rx_buffers();

                        // Timeout solo cuando hay datos persistentes (~3s).
                        // Flush final antes de enviar nuevo LIST para evitar
                        // basura residual de listado previo rendering en main area.
                        if (++pagination_timeout > PAGINATION_FLUSH_TIMEOUT_FRAMES) {
                            search_flush_state = 2;
                            flush_all_rx_buffers();
                            send_pending_search_command();
                            pagination_timeout = 0;
                        }
                    }
                }
                // Fase de espera de resultados
                else if (search_flush_state == 2) {
                    if (++pagination_timeout > PAGINATION_RESPONSE_TIMEOUT_FRAMES) {
                        search_data_lost = 1;
                        ui_err("Timeout (incomplete)");
                        cancel_search_state();
                    }
                }
            }
            
            // 2. FLUSH STATUS BAR
            if (status_bar_dirty) {
                status_bar_dirty = 0;
                draw_status_bar_real();
            }

            // 3. INPUT Y teclado
            check_caps_toggle();

            // Sample SHIFT once per frame and reuse it
            shift_held = key_shift_held();
            
            c = read_key();
            if (c) key_click();

            // Badge "<<<" blink: toggle INK green every 16 frames, auto-stop after ~5s
            if (badge_flashing && !(++flash_timer & 0x0F)) {
                if (flash_timer >= 240) {
                    badge_flash_off();
                } else {
                    *(uint8_t *)(ATTR_BASE_ADDR + 30) ^= 0x04;
                    *(uint8_t *)(ATTR_BASE_ADDR + 31) ^= 0x04;
                    *(uint8_t *)(ATTR_BASE_ADDR + 32 + 30) ^= 0x04;
                    *(uint8_t *)(ATTR_BASE_ADDR + 32 + 31) ^= 0x04;
                }
            }

            // Any keypress resets auto-away counter and badge flash
            if (c) {
                autoaway_counter = 0;
                badge_flash_off();
                if (count_sync_enabled) count_sync_idle_frames = 0;
            }

            // D2: SHIFT+5/6/7/8 => cursor keys via lookup table
            // H14: short-circuit (shift first) + 8-bit underflow range check
            if (shift_held && (uint8_t)(c - '5') <= 3) {
                static const uint8_t shift_keys[] = {KEY_LEFT, KEY_DOWN, KEY_UP, KEY_RIGHT};
                c = shift_keys[c - '5'];
                shift_held = 0;  // arrow modifier must not move the caps cursor
            }

            {
                uint8_t cursor_shift_now = cursor_shift_held;
                if (!shift_held) {
                    cursor_shift_now = 0;
                } else if ((c | 32) >= 'a' && (c | 32) <= 'z') {
                    cursor_shift_now = 1;
                }
                cursor_shift_held = cursor_shift_now;
            }
            if ((prev_caps_mode != caps_lock_mode) || (prev_shift_held != cursor_shift_held)) {
                prev_caps_mode = caps_lock_mode;
                prev_shift_held = cursor_shift_held;
                cursor_show();
            }

            // Overlay system (state-based, non-blocking)
            if (overlay_mode) {
                pagination_active = 0; /* W11: overlays and pagination are mutually exclusive */
                if (overlay_mode == OVERLAY_ABOUT && connection_state >= STATE_TCP_CONNECTED) {
                    about_pump();
                }
                if (c) sw_timeout = 0; /* W14: reset help timeout on any keypress */
                // About overlay: N key opens What's New
                if (overlay_mode == OVERLAY_ABOUT && (c == 'n' || c == 'N')) {
                    overlay_call(1);
                    about_keepalive_rebaseline();
                    overlay_mode = OVERLAY_WHATSNEW;
                    overlay_exec(2, 0);
                    c = 0;
                // Config overlay: S key triggers save + refresh
                } else if (overlay_mode == OVERLAY_CONFIG && config_dirty && (c == 's' || c == 'S')) {
                    overlay_exit_full();
                    cmd_save(NULL);
                    // Re-enter config overlay to show updated state
                    overlay_mode = OVERLAY_CONFIG;
                    cursor_visible = 0;
                    overlay_exec(4, 0);
                    c = 0;
                } else if (overlay_mode == OVERLAY_BOOKMARKS) {
                    bookmark_selector_key(c);
                    c = 0;
                } else if (c == KEY_BREAK || (c && overlay_mode != OVERLAY_HELP)) {
                    // BREAK always exits; any key exits single-page overlays
                    if (overlay_mode == OVERLAY_ABOUT) {
                        overlay_call(1);
                        about_keepalive_rebaseline();
                    }
                    overlay_exit_full();
                } else if (c) {
                    // Help: paginated — advance page
                    help_page++;
                    sw_timeout = 0; /* W14: reset timeout on keypress */
                    help_render_page();
                    if (!overlay_mode) {
                        overlay_exit_full();
                    }
                } else if (overlay_mode == OVERLAY_HELP && ++sw_timeout >= HELP_TIMEOUT_FRAMES) {
                    /* W14: auto-close help after ~90s to prevent PING timeout */
                    overlay_exit_full();
                    continue;
                } else if (overlay_mode == OVERLAY_ABOUT && !c) {
                    /* Frame-counter gate: tick fires when ≥2 ROM FRAMES have
                     * passed since last tick. Guarantees 25Hz cadence even if
                     * iter time spikes (fread latency). uint8 wraps cleanly. */
                    if ((uint8_t)(last_frames_lo - about_anim_last) >= 2) {
                        about_anim_last = last_frames_lo;
                        overlay_call_timed(2);
                    }
                }
                c = 0;
            }

            if (channel_context_pending) channel_context_banner();

            // PD2: cache shared input-enabled condition (3 sites below)
            uint8_t input_enabled = !pagination_active && search_mode == SEARCH_NONE && !autoconnect_delay;

            // Channel switcher overlay (non-blocking, state-based)
            if (sw_active) {
                // Rebuild map BEFORE key handling to avoid stale sw_map
                if (sw_dirty) switcher_render();

                // Track EDIT key release to prevent instant cancel
                if (!sw_released && in_inkey() == 0) sw_released = 1;

                if (c) {
                    sw_timeout = 0;  // reset auto-close on any key

                    if (c == KEY_LEFT) {
                        sw_sel = sw_sel ? sw_sel - 1 : sw_count - 1;  // wrap
                        sw_dirty = 1;
                    } else if (c == KEY_RIGHT) {
                        sw_sel = (sw_sel < sw_count - 1) ? sw_sel + 1 : 0;  // wrap
                        sw_dirty = 1;
                    } else if (c == KEY_ENTER) {
                        switch_or_notify(sw_map[sw_sel]);
                        switcher_close();
                    } else if (c == KEY_BACKSPACE) {
                        uint8_t idx = sw_map[sw_sel];
                        if (idx > 0) {
                            switcher_part(idx);
                            switcher_close();
                        }
                    } else if (c == 7 && sw_released) {
                        switcher_close();
                    } else if (c >= '0' && c <= '9') {
                        // Direct slot jump: find slot in active map
                        uint8_t slot = c - '0';
                        uint8_t k;
                        for (k = 0; k < sw_count; k++) {
                            if (sw_map[k] == slot) {
                                switch_or_notify(slot);
                                switcher_close();
                                break;
                            }
                        }
                    }
                } else if (sw_active) {
                    // No key this frame — auto-close after ~10s (500 frames)
                    if (++sw_timeout >= SWITCHER_TIMEOUT_FRAMES) switcher_close();

                    // Live refresh: detect flag CHANGES via snapshot
                    {
                        uint8_t k;
                        for (k = 0; k < sw_count; k++) {
                            uint8_t f = channels[sw_map[k]].flags;
                            if ((f & (CH_FLAG_UNREAD | CH_FLAG_MENTION)) != (sw_flags_snap[k] & (CH_FLAG_UNREAD | CH_FLAG_MENTION))) {
                                sw_dirty = 1;
                                break;
                            }
                        }
                    }
                }

                if (sw_active && sw_dirty) switcher_render();
                c = 0;  // consume all keys while switcher is open
            } else if (c == 7 && input_enabled) {
                switcher_open();
                c = 0;
            }

            // ENTER/BREAK with empty input during PM notification
            if ((c == KEY_ENTER || c == KEY_BREAK) && line_len == 0 && notif_is_pm && notif_timeout && last_pm_nick[0]) {
                if (c == KEY_ENTER) {
                    int8_t qi = add_query(last_pm_nick);
                    if (qi >= 0) { switch_to_channel((uint8_t)qi); status_bar_dirty = 1; }
                    else ui_err("Max windows. /close first");
                }
                notif_timeout = 0; notif_is_pm = 0;
                notif_clear();
                c = 0;
            }

            // Word navigation: SS+arrow via raw port reads (with auto-repeat)
            {
                uint8_t ssa = key_ss_arrow();
                if (ssa) {
                    if (!ss_held || !ss_repeat) {
                        if (input_enabled) {
                            if (ssa == 1) input_word_left();
                            else if (ssa == 2) input_word_right();
                            else if (ssa == 3) input_delete_word();
                            else if (ssa == 4) input_line_start();
                            else input_line_end();
                            key_click();
                        }
                        ss_repeat = ss_held ? 4 : 12;  // fast repeat / initial delay
                    } else {
                        ss_repeat--;
                    }
                    ss_held = 1;
                    c = 0;
                } else {
                    ss_held = 0;
                    ss_repeat = 0;
                }
            }

            if (c != 0 && input_enabled) {
                if (c >= 32 && c <= 126) {
                    uint8_t c_lower = c | 32;

                    if (c_lower >= 'a' && c_lower <= 'z') {
                        c = c_lower ^ ((caps_lock_mode ^ shift_held) << 5);
                    }

                    input_add_char(c);
                }
                else if (c == KEY_ENTER) {
                     if (line_len > 0) {
                        // OPT H2: reutilizar temp_input[] (estático) en lugar de cmd_copy local
                        st_copy_n(temp_input, line_buffer, sizeof(temp_input));
                        history_add(temp_input, line_len); 
                        input_clear();
                        cursor_hide();
                        while (deferred_wrap_active) {
                            deferred_wrap_step();
                        }
                        parse_user_input(temp_input);
                        cursor_show();
                     }
                }
                else if (c == KEY_BACKSPACE) input_backspace();
                else if ((c & 0xFE) == KEY_LEFT) {
                    if (c == KEY_LEFT) {
                        if (cursor_pos > 0) {
                            cursor_hide();
                            cursor_pos--;
                            cursor_show();
                        }
                    } else {
                        if (cursor_pos < line_len) {
                            cursor_hide();
                            cursor_pos++;
                            cursor_show();
                        }
                    }
                }
                else if ((c & 0xFE) == KEY_DOWN) {
                    if (c == KEY_UP) history_nav_up(); else history_nav_down();
                    redraw_input_full();
                }
            }
            
            // About blocks IRC processing (ring_buffer busy with globe animation).
            // All other overlays: process_irc_data runs normally — output suppressed
            // by main_print's overlay_mode early-return, data consumed silently.
            if (overlay_mode != OVERLAY_ABOUT) {
                if (deferred_wrap_active) {
                    deferred_wrap_step();
                    net_pump_rx();
                } else {
                    process_irc_data();
                }
                count_sync_tick();
            }
            auth_save_poll();
        }
    }
}
