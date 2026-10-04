/*
 * user_cmds.c - User command parsing and handling (SIZE OPTIMIZED)
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
void cmd_quit(const char *args) __z88dk_fastcall;

extern const char S_DEFAULT_PORT[];
extern uint8_t autoconnect;

// Config key strings exported to overlays through overlay_defs.
static const char K_NICK[]     = "nick=";
static const char K_SERVER[]   = "server=";
static const char K_PORT[]     = "port=";
static const char K_PASS[]     = "pass=";
static const char K_NKPASS[]   = "nickpass=";
static const char K_AUTOCONN[] = "autoconnect=";
static const char K_AUTOJOIN[] = "autojoin=";
static const char K_THEME[]    = "theme=";
static const char K_AUTOAWAY[] = "autoaway=";
static const char K_BEEP[]     = "beep=";
static const char K_CLICK[]    = "click=";
static const char K_NCOLOR[]   = "nickcolor=";
static const char K_TRAFFIC[]  = "traffic=";
static const char K_TS[]       = "timestamps=";
static const char K_DIVIDER[]  = "divider=";
static const char K_CHANNELS[] = "channels=";
static const char K_TOPIC[]    = "TOPIC";
static const char K_MODE_SP[]  = "MODE ";
#ifdef SPECTALK_SPECTRANEXT
static const char K_CFG_PRI[]  = "/CFG/SPECTALK.CFG";
#else
static const char K_CFG_PRI[]  = "/SYS/CONFIG/SPECTALK.CFG";
#endif
static const char K_CFG_ALT[]  = "/SYS/SPECTALK.CFG";
static const char K_TZ[]       = "tz=";
static const char K_TZLAST[]   = "tzlast=";
static const char K_NOTIF[]    = "notif=";
static const char K_COUNTSYNC[] = "countsync=";
static const char K_NICKSERV[] = "nickserv=";
static const char K_AUTHCMD[] = "authcmd=";
static const char K_BOOKMARK[] = "bookmark=";
static const char K_FRIENDS[]  = "friends=";
static const char K_IGNORES[]  = "ignores=";

// PD1: cut_at_space() removed — split_at_space() does same buffer cut

static char *split_at_space(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
split_at_space_scan:
    ld a,(hl)
    or a
    jr z,split_at_space_none
    cp 32
    jr z,split_at_space_found
    inc hl
    jr split_at_space_scan
split_at_space_found:
    ld (hl),0
    inc hl
    ld a,(hl)
    or a
    jr z,split_at_space_none
split_at_space_skip:
    ld a,(hl)
    cp 32
    ret nz
    inc hl
    jr split_at_space_skip
split_at_space_none:
    ld hl,0
    ret
    __endasm;
}

static char *ping_params_start(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
    ld de,ping_params_start_key
    ld b,4
ping_params_start_loop:
    ld a,(de)
    cp (hl)
    jr nz,ping_params_start_no
    inc de
    inc hl
    djnz ping_params_start_loop
    ret
ping_params_start_no:
    ld hl,0
    ret
ping_params_start_key:
    DEFM "PING"
    __endasm;
}

static char *cap_params_start(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
    inc hl
    ld de,cap_params_start_key
    ld b,3
    jp ping_params_start_loop
cap_params_start_key:
    DEFM "CAP"
    __endasm;
}

#ifndef SPECTALK_SPECTRANEXT
static uint8_t is_ban_numeric_at(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
    ld a,(hl)
    cp '4'
    jr nz,is_ban_numeric_at_no
    inc hl
    ld a,(hl)
    cp '6'
    jr nz,is_ban_numeric_at_no
    inc hl
    ld a,(hl)
    cp '5'
    jr z,is_ban_numeric_at_yes
    cp '6'
    jr z,is_ban_numeric_at_yes
is_ban_numeric_at_no:
    ld l,0
    ret
is_ban_numeric_at_yes:
    ld l,1
    ret
    __endasm;
}
#endif

// Generic yes/no prompt with ~5s timeout. Returns 1 on y/Y, 0 on n/N or timeout.
// Drains UART/parser between key polls to keep IRC state consistent during the wait.
// Caller is responsible for any "Cancelled"/"Aborted" message on a 0 return.
static uint8_t prompt_yn(const char *q) __z88dk_fastcall
{
    uint16_t tmout = 500;

    set_attr_err();
    main_puts(q);
    while (tmout--) {
        uint8_t k = in_inkey();
        net_frame_wait();
        while (try_read_line_nodrain());
        if (k == KEY_BREAK) { main_newline(); return 0; }
        k |= 32;
        if (k == 'y' || k == 'n') {
            main_putc(' ');
            main_putc(k);
            main_newline();
            while (in_inkey()) {
                frame_wait();
                net_pump_rx();
            }
            return (k == 'y');
        }
    }
    main_print(" Timeout!");
    main_newline();
    return 0;
}

static uint8_t confirm_disconnect(void)
{
    if (prompt_yn("Disconnect (y/n)?")) return 1;
    ui_err(S_CANCELLED);
    return 0;
}

static void disconnect_with_feedback(void)
{
    set_attr_sys();
    main_print("Disconnecting...");
    net_disconnect();
    draw_status_bar();
}

static void err_maxwin(void)
{
    ui_err(S_MAXWIN);
    main_print("Use /close first.");
}

// =============================================================================
// INTERNAL HELPERS
// =============================================================================

// sys_puts_print: frameless ASM in spectalk_asm.asm


// Help overlay state (state-based, non-blocking — main loop keeps running)
// Non-static: ASM main_puts checks this to suppress output during help
uint8_t overlay_mode;
uint8_t help_page;              // current page (0-based) — non-static for overlay access
uint8_t config_dirty;           // 1 = unsaved config changes exist
uint8_t bookmark_sel;
// 0 = legacy CFG; bits 0..5 = slot, bit 6 = inferred UI, bit 7 = JOIN; 0x80 = OFF.
uint8_t bookmark_active_slot;
uint8_t bookmark_rows[5];

// NIVELES DE VALIDACIÓN JERÁRQUICA
#define LVL_TCP  1  // Conectado a Internet (Socket abierto)
#define LVL_IRC  2  // Conectado a Servidor (Registrado con NICK/USER)
#define LVL_CHAN 3  // Conectado a Canal (Ventana válida y activa)

uint8_t check_status(uint8_t level) __z88dk_fastcall
{
    // LVL_TCP  -> requiere STATE_TCP_CONNECTED
    // LVL_IRC+ -> requiere STATE_IRC_READY (que implícitamente incluye TCP)
    uint8_t min_state = (level == LVL_TCP) ? STATE_TCP_CONNECTED : STATE_IRC_READY;

    if (connection_state < min_state) {
        ERR_NOTCONN();
        return 0;
    }

    // Si solo pedíamos validación de conexión, terminamos aquí
    if (level <= LVL_IRC) return 1;

    // Nivel 3: Contexto de Canal (Necesario para KICK, ME, etc.)
    if (current_channel_idx == 0 || !(chan_flags & CH_FLAG_ACTIVE)) {
        ui_err(S_NOWIN); // "No window..."
        return 0;
    }

    return 1;
}


#define REQUIRE_CHAN() do { if (!IS_CHAN_PREFIX(irc_channel[0])) { ui_err(S_MUST_CHAN); return; } } while(0)

// ensure_args: frameless ASM in spectalk_asm.asm

// FIX-H6: redundant externs removed - already in spectalk.h with correct types

// puts_u8_nolz: frameless ASM in spectalk_asm.asm

// =============================================================================
// SEARCH COMMAND HELPER (Unifica lógica de list/who/search)
// Ahorra ~90 bytes al eliminar código duplicado
// =============================================================================
// =============================================================================
// COMMAND HANDLERS
// =============================================================================

// OPT L3: cmd_connect_abort eliminada - inlined en call site

static void cmd_connect(const char *args) __z88dk_fastcall
{ 
    const char *port;
    char *sep;
    uint8_t result;
    uint8_t use_ssl = 0;
    uint8_t use_saved_session = 0;

    if (connection_state < STATE_WIFI_OK) {
        ui_err("No WiFi. Use !init");
        return;
    }

    if (!args || !*args) {
        if (connection_state >= STATE_TCP_CONNECTED) {
            // No args + connected: show current server
            set_attr_sys();
            main_puts2("Already connected to ", irc_server);
            main_putc(':'); main_print(irc_port);
            return;
        }
        // No args + not connected: reconnect using config-preloaded server if available
        if (irc_server[0]) {
            use_saved_session = 1;
            goto do_connect;
        }
        ui_usage("server host [port]");
        return;
    }

    if (connection_state >= STATE_TCP_CONNECTED) {
        set_attr_err();
        main_puts("Already connected. ");
        if (!confirm_disconnect()) return;
        disconnect_with_feedback();
        draw_status_bar_real();
    }
    
    sep = strchr(args, ' ');
    if (!sep) sep = strchr(args, ':');
    
    if (sep) {
        *sep = '\0';
        port = sep + 1;
        port = (const char *)skip_spaces((char *)port);
    } else {
        port = NULL;
    }
    if (!port || !*port) port = S_DEFAULT_PORT;
    auth_profile = 0;
    if (st_stricmp(irc_server, args) || st_stricmp(irc_port, port)) {
        auth_mode = AUTH_LEGACY;
        nickserv_nick[0] = nickserv_pass[0] = 0;
    }
    st_copy_n(irc_server, args, sizeof(irc_server));
    if (strchr(irc_server, '"')) { ui_err("Bad server name"); return; }  // audit L04

    st_copy_n(irc_port, port, sizeof(irc_port));

do_connect:

    if (!irc_nick[0]) {
        ui_sys("Set /nick first");
        return;
    }
    
    if (str_to_u16(irc_port) == 6697) use_ssl = 1;
    
    set_attr_priv();
    main_puts2("Connecting to ", irc_server); main_putc(':'); main_puts2(irc_port, "... ");
    
    net_disconnect();
    clock_init();  // self-guarded
    if (clock_setup_state) (void)wait_for_response(S_OK, 50);
    if (!use_saved_session) {
        search_pattern[0] = 0;
        autojoin_channels[0] = 0;
    }
    reset_rx_state(); rx_line[0] = '\0';
    result = 0;
    
    draw_status_bar(); cursor_visible = 0; redraw_input_full(); 

    net_prepare(use_ssl);

    // If the WiFi-idle SNTP path has not produced a clock yet, use raw UDP NTP
    // before opening the IRC TCP link. This also covers old AT firmwares that
    // lack CIPSNTPTIME.
    clock_sync_fallback();
    if (connection_state < STATE_WIFI_OK) {
        ui_err(S_FAIL);
        goto connect_cleanup;
    }

    result = net_connect(irc_server, irc_port, use_ssl);
    if (result != NET_CONNECT_OK) {
        if (result == NET_CONNECT_CANCELLED) ui_err(S_CANCELLED);
        else if (result == NET_CONNECT_DNS_FAILED) ui_err("DNS failed");
        else if (result == NET_CONNECT_REFUSED) ui_err(S_CONN_REFUSED);
        else if (result == NET_CONNECT_ERROR) ui_err("Connection error");
        else ui_err(S_TIMEOUT);
        goto connect_fail;
    }

    set_attr_priv(); main_print(S_OK);

#ifndef SPECTALK_SPECTRANEXT
    result = net_start_stream();
    if (result == NET_STREAM_MODE_FAILED) {
        ui_err("CIPMODE FAIL");
        goto connect_fail;
    }
    if (result == NET_STREAM_PROMPT_FAILED) {
        // rx_line has captured data — scan for IRC ban numeric (465/466)
        char *p = (char *)rx_line;
        while (*p) {
            if (is_ban_numeric_at(p)) {
                ui_err("Banned"); goto connect_fail;
            }
            p++;
        }
        ui_err("No '>' prompt"); goto connect_fail;
    }
#endif
    
    connection_state = STATE_TCP_CONNECTED; closed_reported = 0;
    rx_pos = 0; rx_overflow = 0;
    
    if (irc_nick[0]) {
        char *line; 
        uint8_t loop_done = 0;
        uint16_t silence_frames = 0;
        uint16_t total_frames = 0;

        const char *abort_msg = 0;
        uint8_t abort_disc = 1;
        
        set_attr_priv(); main_puts("Registering... ");
        
        if (irc_pass[0]) irc_send_cmd1("PASS", irc_pass);
        irc_send_cmd1(S_NICK_CMD, irc_nick);
        net_send_string("USER "); net_send_string(irc_nick);
        net_send_string(" 0 * :"); net_send_line(irc_nick);

        rx_pos = 0;
        
        while (!loop_done) {
            if (uart_tx_failed) { abort_msg = S_FAIL; goto join_fail; }
            net_frame_wait();
            if (in_inkey() == KEY_BREAK) {
                abort_msg = "Aborted.";
                abort_disc = 1;
                goto join_fail;
            }
            
            if (try_read_line_nodrain()) {
                char *sp;
                uint16_t code;
                
                silence_frames = 0;
                line = rx_line;
                if (line[0] == '@') {
                    line = strchr(line, ' ');
                    if (line) line++; else { rx_pos = 0; goto registration_next; }
                }
                
                // Buscar código numérico de forma eficiente
                sp = strchr(line, ' ');
                if (sp && sp[1] >= '0' && sp[1] <= '9') {
                    code = str_to_u16(sp + 1);
                    switch (code) {
                        case 1: // RPL_WELCOME
                            set_attr_priv(); main_print("Connected!");
                            if (autojoin && nickserv_pass[0]) {
                                autojoin_defer_flags |= AUTOJOIN_IDENT_WAIT;
                                autojoin_ident_grace = 0;
                            }
                            connection_state = STATE_IRC_READY; loop_done = 1; rx_pos = 0; continue;
                        case 433: // Nick in use - try alternate
                            // OPT-P2-B: use shared helper
                            nick_try_alternate();
                            rx_pos = 0;
                            goto registration_next;
                        case 432: case 436: abort_msg = "Invalid nick"; abort_disc = 0; goto join_fail;
                        case 464: case 461: abort_msg = "Auth failed"; abort_disc = 1; goto join_fail;
                        case 465: case 466: abort_msg = "Banned"; abort_disc = 1; goto join_fail;
                    }
                }
                
                // CAP LS - format: ":server CAP * LS ..."
                if (line[0] == ':' && sp) {
                    // Check for LS after CAP
                    char *ls = cap_params_start(sp);
                    if (ls) {
                        ls = skip_spaces(ls);
                        if (*ls == '*') { ls++; ls = skip_spaces(ls); }
                        if (ls[0] == 'L' && ls[1] == 'S') {
                            net_send_line(S_CAP_END);
                            rx_pos = 0; goto registration_next;
                        }
                    }
                }
                
                // PING
                {
                    char *params = ping_params_start(line);
                    if (!params && sp) params = ping_params_start(sp + 1);

                    if (params) {
                        params = skip_spaces(params);
                        net_send_string(S_PONG); net_send_line(params);
                        rx_pos = 0; goto registration_next;
                    }
                }

                // ERROR : - siempre al inicio de línea
                // FIX P0-1: Verificar longitud antes de acceder a índices
                // FIX-H5: usar longitud restante desde 'line', no rx_last_len global
                // The command is exactly five bytes; line[5] is its token boundary.
                {
                uint16_t remaining = rx_last_len - (uint16_t)(line - rx_line);
                if (remaining >= 5 && line[0] == 'E' && line[1] == 'R' &&
                    line[2] == 'R' && line[3] == 'O' && line[4] == 'R' &&
                    (remaining == 5 || line[5] == ' ')) {
                    abort_msg = "Server error";
                    abort_disc = 1;
                    goto join_fail;
                }
                }

                // FIX P0-1: Verificar longitud antes de acceder a índices
                if (rx_last_len >= 3 && rx_line[0] == 'C' && rx_line[1] == 'L' && rx_line[2] == 'O') {  // CLOSED
                    abort_msg = "Connection lost";
                    abort_disc = 1;
                    goto join_fail;
                }
                
                rx_pos = 0;
            } else {
                silence_frames++;
                if (silence_frames > 1500) {
                    abort_msg = S_TIMEOUT;
                    abort_disc = 1;
                    goto join_fail;
                }
            }
registration_next:
            // Absolute timeout (~60s) prevents infinite hang if server
            // keeps sending data (throttle NOTICEs) without completing registration
            if (++total_frames > 3000) {
                abort_msg = S_TIMEOUT;
                abort_disc = 1;
                goto join_fail;
            }
        }

join_fail:
        if (abort_msg) {
            // OPT L3: inlined cmd_connect_abort
            ui_err(abort_msg);
            if (abort_disc) net_disconnect();
            abort_msg = 0;
            reset_rx_state();
        }
    } else {
        net_disconnect();
    }
    goto connect_cleanup;

    connect_fail:
        net_disconnect();

    connect_cleanup:
        cursor_visible = 1; draw_status_bar(); redraw_input_full();
}

// Wrapper around cmd_connect that offers a one-key retry on failure. Kept
// outside cmd_connect to avoid SDCC re-entry register spills (a goto back
// into cmd_connect's body cost ~115B; this wrapper is ~30B).
static void cmd_connect_retry(const char *args) __z88dk_fastcall
{
    cmd_connect(args);
    while (connection_state >= STATE_WIFI_OK && connection_state < STATE_TCP_CONNECTED
           && irc_server[0] && irc_nick[0]
           && prompt_yn("Retry (y/n)?")) {
        cmd_connect(NULL);
    }
}

static void overlay_exec_rx(uint8_t group, uint8_t entry)
{
    uint16_t had_partial = rx_pos;
    overlay_exec(group, entry);
    if (had_partial) rx_overflow = 1;
}

#define BOOKMARK_TOTAL 5
#define BOOKMARK_AUTOLOGIN 0x80
#define BOOKMARK_OCCUPIED 0x80
#define bookmark_save_config() cmd_save(NULL)
#ifdef SPECTALK_SPECTRANEXT
#define BOOKMARK_STORE_GROUP 3
#define BOOKMARK_APPLY_ENTRY 2
#define BOOKMARK_SAVE_ENTRY 3
#else
#define BOOKMARK_STORE_GROUP 2
#define BOOKMARK_APPLY_ENTRY 1
#define BOOKMARK_SAVE_ENTRY 2
#define BOOKMARK_DELETE_ENTRY 3
#endif

#define bookmark_render() overlay_exec_rx(7, 0)
#define bookmark_render_list() overlay_exec_rx(7, 2)

static void bookmark_render_rows(uint8_t prev_slot) __z88dk_fastcall
{
    overlay_slot[0] = prev_slot;
    overlay_exec_rx(7, 1);
}

static void bookmark_render_cursor(uint8_t prev_slot) __z88dk_fastcall
{
    overlay_slot[0] = prev_slot;
    overlay_exec_rx(7, 4);
}

static void bookmark_load_current(void)
{
    uint8_t was_connected = (connection_state >= STATE_TCP_CONNECTED);

    if (!(bookmark_rows[bookmark_sel] & BOOKMARK_OCCUPIED)) return;
    if (was_connected) {
        overlay_exit_full();
        if (!confirm_disconnect()) return;
    }

    overlay_slot[0] = 0;
    overlay_exec(BOOKMARK_STORE_GROUP, BOOKMARK_APPLY_ENTRY);
    if (overlay_slot[0] != 1) return;

    if (!was_connected) overlay_exit_full();
    if (was_connected) {
        disconnect_with_feedback();
    }
    cmd_connect_retry(NULL);
}

static void bookmark_save_current(void)
{
    uint8_t slot = bookmark_sel + 1;

    if (connection_state < STATE_IRC_READY) search_pattern[0] = 0;
    snapshot_autojoin_channels();

    overlay_exec(BOOKMARK_STORE_GROUP, BOOKMARK_SAVE_ENTRY);
    if (overlay_slot[0]) {
        auth_profile = slot;
        bookmark_render_list();
        if ((bookmark_active_slot & BOOKMARK_SLOT_MASK) == slot) config_dirty = 1;
    }
}

static void bookmark_activate_current(void)
{
    uint8_t slot = bookmark_sel + 1;
    uint8_t active = bookmark_active_slot & BOOKMARK_SLOT_MASK;
    uint8_t prev_slot = active ? (uint8_t)(active - 1) : 0xFF;

    if (active == slot && (bookmark_active_slot & BOOKMARK_AUTOLOGIN)) {
        bookmark_active_slot = BOOKMARK_AUTOLOGIN;  // explicit OFF; preserve live session
        config_dirty = 1;
        bookmark_render_rows(0xFF);
        return;
    }

    overlay_slot[0] = (active == slot) ? 2 : 1;
    overlay_exec_rx(BOOKMARK_STORE_GROUP, BOOKMARK_APPLY_ENTRY);
    if (overlay_slot[0] == 1) {
        bookmark_render_rows(prev_slot);
    }
}

/* Called once before networking: apply the saved startup preference, never live. */
static void bookmark_startup(void)
{
    uint8_t slot = bookmark_active_slot & BOOKMARK_SLOT_MASK;
    if (!bookmark_active_slot || (bookmark_active_slot & BOOKMARK_INFERRED)) return;
    autoconnect = autojoin = 0;
    if (!slot) return;
    bookmark_sel = slot - 1;
    overlay_slot[0] = 0;
    overlay_exec_rx(BOOKMARK_STORE_GROUP, BOOKMARK_APPLY_ENTRY);
    if (overlay_slot[0]) {
        autoconnect = 1;
        autojoin = (bookmark_active_slot & BOOKMARK_AUTOLOGIN) ? 1 : 0;
    } else {
        bookmark_active_slot = BOOKMARK_AUTOLOGIN;
    }
}

void bookmark_selector_key(uint8_t c) __z88dk_fastcall
{
    if (c == KEY_UP || c == KEY_DOWN) {
        uint8_t prev_slot = bookmark_sel;
        if (c == KEY_UP) {
            bookmark_sel = bookmark_sel ? bookmark_sel - 1 : BOOKMARK_TOTAL - 1;
        } else if (++bookmark_sel >= BOOKMARK_TOTAL) {
            bookmark_sel = 0;
        }
        bookmark_render_cursor(prev_slot);
    } else if (c == KEY_ENTER) {
        bookmark_load_current();
    } else if ((c | 0x20) == 's') {
        bookmark_save_current();
    } else if ((c | 0x20) == 'a') {
        bookmark_activate_current();
    } else if ((c | 0x20) == 'd') {
        uint8_t active = bookmark_active_slot & BOOKMARK_SLOT_MASK;
#ifdef SPECTALK_SPECTRANEXT
        overlay_exec(7, 3);
#else
        overlay_exec(BOOKMARK_STORE_GROUP, BOOKMARK_DELETE_ENTRY);
#endif
        if (overlay_slot[0]) {
            if (auth_profile == bookmark_sel + 1) auth_profile = 0;
            if (active == bookmark_sel + 1) config_dirty = 1;
#ifndef SPECTALK_SPECTRANEXT
            bookmark_render_list();
#endif
        }
    } else if (c == KEY_BREAK) {
        if (config_dirty) bookmark_save_config();
        overlay_exit_full();
    }
}

static void cmd_bookmarks(const char *args) __z88dk_fastcall
{
    (void)args;
    bookmark_sel = 0;
    overlay_mode = OVERLAY_BOOKMARKS;
    cursor_visible = 0;
    redraw_input_full();
    bookmark_render();
}


static void cmd_nick(const char *args) __z88dk_fastcall
{
    char *p;
    uint8_t n;

    if (!args || !*args) {
        set_attr_sys();
        main_puts("Current nick: ");
        main_print(irc_nick[0] ? (const char *)irc_nick : S_NOTSET);
        return;
    }

    /* args viene ya sin espacios iniciales desde parse_user_input */
    p = (char *)args;
    if (!*p) return;

    /* Truncar en primer espacio o al límite del nick (mismo comportamiento que antes) */
    n = 0;
    while (p[n] && p[n] != ' ' && n < (uint8_t)(sizeof(irc_nick) - 1)) n++;
    if (p[n]) p[n] = 0;

    if (connection_state >= STATE_TCP_CONNECTED) {
        // Conectado: Solo enviar comando, el handler actualizará la UI/Variable si es exitoso
        irc_send_cmd1(S_NICK_CMD, p);
    } else {
        // Desconectado: Actualizar inmediatamente
        st_copy_n(irc_nick, p, sizeof(irc_nick));

        notify2("Nick set to ", irc_nick, ATTR_MSG_SYS);
        draw_status_bar();
        config_dirty = 1;
    }
}

static void cmd_str_ovl(const char *args, uint8_t entry) __z88dk_callee
{
    if (args && *args) st_copy_n((char *)overlay_slot, args, LINE_BUFFER_SIZE);
    else overlay_slot[0] = 0;

    overlay_exec_rx(6, entry);
}

static void cmd_pass(const char *args) __z88dk_fastcall
{
    cmd_str_ovl(args, 1);
}

static void cmd_join(const char *args) __z88dk_fastcall
{
    const char *lookup;
    int8_t idx;

    if (!ensure_args(args, "join #channel")) return;
    // Nivel 2: Servidor
    if (!check_status(LVL_IRC)) return;

    // Tomar SOLO el primer token y truncar en el primer espacio
    char *p = (char *)args;
    if (!*p) return;

    split_at_space(p);

    // Fast-path: si ya trae # o &, usar el puntero directo
    if (*p == '#' || *p == '&') {
        lookup = p;
    } else {
        search_pattern[0] = '#';
        st_copy_n(search_pattern + 1, p, 20);
        search_pattern[21] = '\0';
        lookup = search_pattern;
    }

    idx = find_channel(lookup);
    if (idx >= 0) {
        switch_or_notify((uint8_t)idx);
        return;
    }

    if (find_empty_channel_slot() == -1) { err_maxwin(); return; }

    irc_send_cmd1(S_JOIN_CMD, lookup);
    notify2("Joining ", lookup, ATTR_MSG_JOIN);
}

static void cmd_part(const char *args) __z88dk_fastcall
{
    // Nivel 2: Servidor (Se puede salir de un canal sin estar en él explícitamente usando args)
    if (!check_status(LVL_IRC)) return;

    char *chan_name = irc_channel;
    char *reason = NULL;
    char *input = (char *)args;
    int8_t idx = current_channel_idx;

    if (input && *input) {
        if (IS_CHAN_PREFIX(*input)) {
            chan_name = input;
            reason = split_at_space(input);
            idx = find_channel(chan_name);
        } else {
            reason = input;
        }
    }

    if (idx <= 0 || idx >= MAX_CHANNELS || !(channels[idx].flags & CH_FLAG_ACTIVE)) {
        set_attr_err();
        main_print(idx == 0 ? "Cannot part Status" : "Not in a channel");
        return;
    }

    /* OPT: evitar buffer local (saved_name[32]) y strncpy().
       Imprimimos el nombre ANTES de remove_channel(), mientras sigue siendo válido. */
    char *cname_ptr = channels[idx].name;

    // FIX: si es query/privado, NO enviar PART (evita 403 -> "Cannot join ... No such channel")
    if (!(channels[idx].flags & CH_FLAG_QUERY)) {
        // OPT: unificar envío (irc_send_cmd2 ignora p2 si es NULL/vacío)
        irc_send_cmd2(S_PART_CMD, cname_ptr, reason);
    }

    notif_cancel_current();
    notify2(S_YOU_LEFT, cname_ptr, ATTR_MSG_JOIN);

    // remove_channel() YA llama a draw_status_bar()
    remove_channel((uint8_t)idx);
}

static void cmd_msg(const char *args) __z88dk_fastcall
{
    // Nivel 2: Requiere estar registrado para enviar PRIVMSG
    if (!check_status(LVL_IRC)) return;

    char *p = (char *)args;
    if (!ensure_args(p, S_USAGE_MSG)) return;

    char *target = p;

    char *msg = split_at_space(p);
    if (!msg) { ui_usage(S_USAGE_MSG); return; }

    if (!IS_CHAN_PREFIX(target[0])) {
        int8_t idx = find_query(target);
        if (idx > 0 && (uint8_t)idx != current_channel_idx) {
            /* Banner reuses temp_input. Copy past the empty input's NUL so
               switch_to_channel() redraws a blank prompt, not the message. */
            char *copy = line_buffer + 1;
            st_copy_n(copy, msg, sizeof(line_buffer) - 1);
            switch_to_channel((uint8_t)idx);
            irc_send_privmsg(irc_channel, copy);
            return;
        }
    }

    irc_send_privmsg(target, msg);
}

static void cmd_reply(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    st_copy_n((char *)overlay_slot, args ? args : "", LINE_BUFFER_SIZE);
    overlay_exec_rx(6, 6);
}

static void cmd_notice(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    st_copy_n((char *)overlay_slot, args ? args : "", LINE_BUFFER_SIZE);
    overlay_exec_rx(5, 2);
}

static void cmd_query(const char *args) __z88dk_fastcall
{
    char *p;

    // Nivel 2: Requiere IRC para tener un NICK propio válido
    if (!check_status(LVL_IRC)) return;
    if (!ensure_args(args, "query nick")) return;

    // Zero-copy: usar el buffer de entrada in-situ
    p = (char *)args;
    if (!*p) return;

    split_at_space(p);

    {
        int8_t idx = add_query(p);

        if (idx >= 0) {
            if ((uint8_t)idx != current_channel_idx) {
                switch_to_channel((uint8_t)idx);
                notify2("Query: ", channels[idx].name, ATTR_MSG_SYS);
            }
            status_bar_dirty = 1;
        } else {
            err_maxwin();
        }
    }
}

void cmd_quit(const char *args) __z88dk_fastcall
{
    const char *msg;

    // Nivel 1: Solo requiere TCP
    if (!check_status(LVL_TCP)) return;

    if (!confirm_disconnect()) return;

    set_attr_sys();

    // FIX: Ocultar cursor inmediatamente al iniciar desconexión
    cursor_visible = 0;
    redraw_input_full();
    notif_cancel_current();

    main_puts2("Disconnecting from ", irc_server);
    main_print(S_DOTS3);

    // Mantener workaround callee/ternario (ya validado por ti)
    msg = (args && *args) ? args : S_APPSHORT;

    irc_send_cmd2("QUIT", NULL, msg);

    net_disconnect();

    rx_pos = 0;
    rx_overflow = 0;

    // FIX: Restaurar cursor después de la desconexión completa
    cursor_visible = 1;
    redraw_input_full();
    ui_sys(S_DISCONN);
    draw_status_bar();
}



static void cmd_me(const char *args) __z88dk_fastcall
{
    if (!ensure_args(args, "me action")) return;
    
    // Nivel 3: Requiere estar DENTRO de un canal/query válido
    if (!check_status(LVL_CHAN)) return;
    
    net_send_string(S_PRIVMSG);
    net_send_string(irc_channel);
    net_send_string(S_SP_COLON);
    net_send_byte(1);            // SOH
    net_send_string(S_ACTION);
    net_send_string(args);
    net_send_byte(1);            // SOH
    net_send_crlf();
    
    current_attr = ATTR_MSG_SELF;
    main_puts2(S_ASTERISK, irc_nick);
    main_putc(' '); main_print(args);
}

static void cmd_away(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    st_copy_n((char *)overlay_slot, args ? args : "", LINE_BUFFER_SIZE);
    overlay_exec_rx(5, 3);
}

// Cold authentication commands own a stable copy of the input.
static void cmd_id(const char *args) __z88dk_fastcall
{
    if (check_status(LVL_IRC)) cmd_str_ovl(args, 5);
}

static void cmd_login(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    st_copy_n((char *)overlay_slot, args ? args : "", LINE_BUFFER_SIZE);
    overlay_exec_rx(0, 4);
}

static void cmd_raw(const char *args) __z88dk_fastcall
{
    if (!ensure_args(args, "raw IRC_COMMAND")) return;
    if (!check_status(LVL_IRC)) return; // Nivel 2
    net_send_line(args);
}

static void cmd_whois(const char *args) __z88dk_fastcall
{
    char *p;

    if (!ensure_args(args, "whois nick")) return;
    if (!check_status(LVL_IRC)) return; // Nivel 2

    /* args viene ya sin espacios iniciales desde parse_user_input */
    p = (char *)args;
    if (!*p) return;

    // PD2: split_at_space() truncates at first space (same as cmd_ignore/friend)
    split_at_space(p);

    irc_send_cmd1("WHOIS", p);
    
    // FIX UX: Feedback optimista
    set_attr_sys();
    
    // FUSIÓN SEGURA
    main_puts2("Querying ", p);
    
    main_print(S_DOTS3);
}


static void cmd_list(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    if (!args || !*args) { ui_usage("list #channel"); main_print("(Full list disabled)"); return; }

    sys_puts_print("LIST: ", args);
    start_search_command(PEND_LIST, args);
}

static void cmd_who(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return;
    
    const char *target = (args && *args) ? args : (current_channel_idx ? irc_channel : NULL);
    if (!target || !target[0]) { ui_usage("who #channel or nick"); return; }

    sys_puts_print("WHO: ", target);
    start_search_command(PEND_WHO, target);
}

static void cmd_names(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return; // Nivel 2

    const char *target = (args && *args) ? args : irc_channel;
    if (!target[0] || !IS_CHAN_PREFIX(target[0])) { ui_err(S_MUST_CHAN); return; }
    
    counting_new_users = 1;
    show_names_list = 1;
    names_was_manual = 1;
    names_count_acc = 0;
    names_friend_pos = 0;
    st_copy_n(names_target_channel, target, sizeof(names_target_channel));
    names_pending = 1;
    names_timeout_frames = 0;
    start_pagination();

    irc_send_cmd1("NAMES", target);
    set_attr_sys();
    main_print("Listing users...");
}

static void cmd_topic(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return; // Nivel 2

    // Sin args: consultar topic del canal actual
    if (!args || !*args) {
        REQUIRE_CHAN();
        irc_send_cmd2(K_TOPIC, irc_channel, NULL);
        return;
    }

    // Si args empieza con prefijo de canal: comportamiento original (primer token = canal)
    if (IS_CHAN_PREFIX(args[0])) {
        char *mutable_target = (char *)(void *)args;
        char *new_topic = NULL;
        char *space = strchr(mutable_target, ' ');
        if (space) {
            *space = '\0';
            new_topic = space + 1;
        }
        irc_send_cmd2(K_TOPIC, mutable_target, new_topic);
        return;
    }

    // Args sin prefijo de canal: usar canal actual como target, args entero como topic
    if (!IS_CHAN_PREFIX(irc_channel[0])) { ui_err(S_MUST_CHAN); return; }
    irc_send_cmd2(K_TOPIC, irc_channel, args);
}

static void cmd_mode(const char *args) __z88dk_fastcall
{
    if (!check_status(LVL_IRC)) return; // Nivel 2

    if (!args || !*args || args[0] == '+' || args[0] == '-') {
        REQUIRE_CHAN();
        net_send_string(K_MODE_SP);
        net_send_string(irc_channel);
        if (args && *args) {
            net_send_byte(' ');
            net_send_string(args);
        }
        net_send_crlf();
        return;
    }

    net_send_string(K_MODE_SP);
    net_send_line(args);
}

static void cmd_search(const char *args) __z88dk_fastcall
{
    char *src;
    char *end;
    char *mutable_args;
    uint8_t is_chan;
    uint8_t len;

    if (!ensure_args(args, "search #pattern or nick")) return;
    if (!check_status(LVL_IRC)) return;

    // args proviene de cmd_copy/line_buffer que es RAM escriturable.
    mutable_args = (char *)args;

    if (mutable_args[0] == '#') {
        is_chan = 1;
        src = mutable_args + 1; // Saltamos '#'
        src = skip_spaces(src);
    } else {
        is_chan = 0;
        src = mutable_args;
    }

    if (!*src) { ui_err(S_EMPTY_PAT); return; }

    end = src;
    len = 0;
    while (*end && *end != ' ' && len < SEARCH_PATTERN_SIZE - 1) { end++; len++; }
    if (*end) *end = '\0';

    set_attr_sys();
    if (is_chan) {
        main_puts2("Searching: *", src); main_print("*");
        start_search_command(PEND_SEARCH_CHAN, src);
    } else {
        main_puts("Searching users: "); main_print(src);
        start_search_command(PEND_SEARCH_USER, src);
    }
}

static void cmd_ignore(const char *args) __z88dk_fastcall
{
    cmd_str_ovl(args, 0);
}

static void cmd_kick(const char *args) __z88dk_fastcall
{
    char *nick;
    char *reason;

    if (!ensure_args(args, "kick nick [reason]")) return;
    if (!check_status(LVL_CHAN)) return;

    if (chan_flags & CH_FLAG_QUERY) {
        ui_err("Not in a channel");
        return;
    }

    nick = (char *)args;

    reason = split_at_space(nick);

    net_send_string("KICK ");
    net_send_string(irc_channel);
    net_send_byte(' ');
    net_send_string(nick);
    if (reason && *reason) {
        net_send_string(S_SP_COLON);
        net_send_string(reason);
    }
    net_send_crlf();

    notify2("Kicking ", nick, ATTR_MSG_SYS);
}


// Sets overlay_mode and hides cursor. Shared by all sys_* overlay launchers.
static void enter_overlay_mode(uint8_t m) __z88dk_fastcall
{
    overlay_mode = m;
    cursor_visible = 0;
}

static void sys_status(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld de,0x0304
    jr sys_overlay_common
    __endasm;
}


static void sys_about(const char *args) __z88dk_fastcall;

// overlay_header: frameless ASM in 40_text_numeric_screen.asm

// overlay_config_render — moved to SPCTLK5.OVL entry 0
static void sys_config(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld de,0x0403
    jr sys_overlay_common
    __endasm;
}

static void sys_whatsnew(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld de,0x0205
sys_overlay_common:
    ld a,e
    ld (_overlay_mode),a
    xor a
    ld (_cursor_visible),a
    ld e,d
    ld d,a
    push de
    call _overlay_exec
    ret
    __endasm;
}

static void sys_init(const char *args) __z88dk_fastcall
{
    (void)args;
    uint8_t result;
    
    set_attr_priv();
#ifdef SPECTALK_SPECTRANEXT
    main_puts(S_INIT_DOTS);
    main_putc(' ');
#else
    main_puts("Re-initializing ESP... ");
#endif
    
#ifdef SPECTALK_SPECTRANEXT
    /* The cartridge owns sockets directly; do not use the Classic UART path. */
    net_disconnect();
#else
#ifndef SPECTALK_NEXT
    flush_all_rx_buffers(); 
    uart_send_line(S_AT_CMD);  // OPT M7
    
    if (wait_for_response(S_OK, 25)) {
        uart_send_line(S_AT_CIPCLOSE);
        wait_for_response(NULL, 10);
    } 
#endif
#endif
    
    connection_state = STATE_DISCONNECTED;
    reset_all_channels();
    network_name[0] = '\0';
    user_mode[0] = '\0';
    
    result = net_init();
    
    if (result == 0) {
#ifdef SPECTALK_SPECTRANEXT
        ui_err(S_FAIL);
#else
        ui_err("FAILED: no ESP response");
#endif
    } else if (connection_state == STATE_WIFI_OK) {
        set_attr_priv();
        main_print("WiFi connected");
#ifdef SPECTALK_SPECTRANEXT
        clock_sync_fallback();  // Explicit retry bypasses the idle SNTP backoff.
#else
        clock_init();  // Sync clock after successful reinit
#endif
    } else {
        ui_err("no WiFi");
    }
    draw_status_bar();
}

static void cmd_theme(const char *args) __z88dk_fastcall
{
    uint8_t t;
    uint16_t had_partial;
    const char *p;
    /* Require exactly one digit (1..3), allow trailing spaces only */
    if (!args || args[0] < '1' || args[0] > '3') goto theme_usage;
    p = (const char *)skip_spaces((char *)(args + 1));
    if (*p) goto theme_usage;

    t = (uint8_t)(args[0] - '0');
    had_partial = rx_pos;
    search_pattern[1] = (char)t;

    if (t == current_theme) {
        search_pattern[0] = 0;
        overlay_exec(0, 3);
        if (had_partial) rx_overflow = 1;
        return;
    }

    current_theme = t;
    apply_theme();

    search_pattern[0] = 1;
    overlay_exec(0, 3);
    if (had_partial) rx_overflow = 1;
    config_dirty = 1;
    return;
theme_usage:
    ui_err("Usage: !theme 1|2|3");
}

static void cmd_autoaway(const char *args) __z88dk_fastcall
{
    st_copy_n((char *)overlay_slot, args ? args : "", 16);
    overlay_exec_rx(6, 3);
}

static void cmd_local_setting(const char *args) __z88dk_fastcall
{
    if (args && *args) st_copy_n((char *)overlay_slot + 1, args, 16);
    else overlay_slot[1] = 0;

    overlay_exec_rx(6, 2);
}

static void cmd_beep(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    xor a
cmd_local_setting_a:
    ld (_overlay_slot),a
    jp _cmd_local_setting
    __endasm;
}

static void cmd_click(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,1
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_nickcolor(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,2
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_traffic(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,3
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_divider(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,8
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_notif(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,4
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_timestamps(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,5
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_autoconnect(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,6
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_autojoin(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,7
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_countsync(const char *args) __z88dk_fastcall ST_NAKED
{
    (void)args;
    __asm
    ld a,9
    jr cmd_local_setting_a
    __endasm;
}

static void cmd_tz(const char *args) __z88dk_fastcall
{
    st_copy_n((char *)overlay_slot, args ? args : "", 8);
    overlay_exec_rx(4, 3);
}

static void cmd_friend(const char *args) __z88dk_fastcall
{
    if (args && *args) {
        split_at_space((char *)args);
        st_copy_n((char *)overlay_slot, args, IRC_NICK_SIZE);
    } else {
        overlay_slot[0] = 0;
    }
    overlay_exec_rx(6, 4);
}

// cmd_save — moved to overlay (SPCTLK4.OVL entry 1)
// After the overlay returns, drain any bytes that arrived during SD I/O and
// discard through the next LF; those bytes may be a tail fragment.
void cmd_save(const char *args) __z88dk_fastcall
{
    uint8_t discard = (rx_pos != 0) || rx_overflow;
    (void)args;
    if (auth_mode == AUTH_PENDING) { ui_err("Login pending"); return; }
    if (auth_mode == AUTH_SAVE) st_copy_n(search_pattern, autojoin_channels, SEARCH_PATTERN_SIZE);
    else if (overlay_mode != OVERLAY_BOOKMARKS) snapshot_autojoin_channels();
    if (auth_mode >= AUTH_LEARNED) {
        uint8_t selected = bookmark_sel;
        auth_mode = AUTH_LEARNED;
        if (auth_profile) {
            bookmark_sel = auth_profile - 1;
            overlay_exec(BOOKMARK_STORE_GROUP, BOOKMARK_SAVE_ENTRY);
            bookmark_sel = selected;
            if (!overlay_slot[0]) goto done;
        }
    }
    overlay_exec(3, 1);
done:
    net_pump_rx();
    if (discard || rb_head != rb_tail) rx_overflow = 1;
}

static void auth_save_poll(void)
{
    if (auth_mode == AUTH_SAVE && !overlay_mode && !deferred_wrap_active &&
        !(autojoin_defer_flags & AUTOJOIN_IDENT_WAIT)) cmd_save(0);
}

// OPT-C14: cmd_clear eliminated — command table points directly to clear_main


// ============================================================
// COMMAND DISPATCHER
// ============================================================

// UserCmd ya está definido arriba (forward declaration para sys_help)

// Wrappers
static void cmd_close_wrapper(const char *a) __z88dk_fastcall {
    uint8_t f;
    (void)a;
    if (current_channel_idx == 0) {
        ui_err("Can't close Server");
        return;
    }
    f = chan_flags;
    if (!(f & CH_FLAG_ACTIVE)) {
        ui_err("No window to close");
        return;
    }
    if (f & CH_FLAG_QUERY) {
        notify2(S_CLOSED_SP, irc_channel, ATTR_MSG_SYS);
        remove_channel(current_channel_idx);
    } else {
        cmd_part("");
    }
}


static void cmd_windows_wrapper(const char *a) __z88dk_fastcall
{
    (void)a;
    overlay_exec_rx(0, 2);
}


// =============================================================================
// =============================================================================
// COMMAND TABLE - SINGLE POOL (names+aliases+help) with uint8 indices
// =============================================================================

typedef void (*user_cmd_handler_t)(const char *args) __z88dk_fastcall;

typedef struct {
    uint8_t name_idx;   // index (0..N-1) of NUL-terminated string in cmd_pool
    uint8_t alias_idx;  // CMD_IDX_NONE if no alias
    user_cmd_handler_t fn;
} PackedCmd;

// Forward declaration needed because sys_help is referenced in USER_COMMANDS initializer.
static void sys_help(const char *args) __z88dk_fastcall;

#define CMD_IDX_NONE  ((uint8_t)0xFF)
#define SYS_CMDS_COUNT 23

// Command names/aliases pool (help strings moved to /SYS/SPECTALK.HLP)
static const char cmd_pool[] =
    "help\0h\0status\0s\0init\0i\0config\0cfg\0theme\0about\0server\0connec"
    "t\0nick\0pass\0id\0join\0j\0part\0p\0msg\0m\0query\0q\0close\0quit\0me"
    "\0away\0autoaway\0aa\0raw\0whois\0wi\0who\0list\0ls\0names\0topic\0sea"
    "rch\0ignore\0kick\0k\0channels\0w\0beep\0traffic\0timestamps\0ts\0clear\0cls\0"
    "save\0sv\0autoconnect\0ac\0tz\0friend\0nickcolor\0nc\0notif\0nf\0"
    "changelog\0click\0mode\0reply\0notice\0autojoin\0divider\0countsync\0cs\0"
    "bookmarks\0bm\0login\0"
;

static const PackedCmd USER_COMMANDS[] = {
    // --- System commands (! prefix) - SYS_CMDS_COUNT entries ---
    {   0,   1, sys_help },
    {   2,   3, sys_status },
    {   4,   5, sys_init },
    {   6,   7, sys_config },
    {   8, 255, cmd_theme },
    {   9, 255, sys_about },
    {  43, 255, cmd_beep },
    {  57,  58, cmd_notif },
    {  59, 255, sys_whatsnew },
    {  27,  28, cmd_autoaway },
    {  44, 255, cmd_traffic },
    {  45,  46, cmd_timestamps },
    {  47,  48, (void (*)(const char *))clear_main },
    {  49,  50, cmd_save },
    {  51,  52, cmd_autoconnect },
    {  64, 255, cmd_autojoin },
    {  53, 255, cmd_tz },
    {  54, 255, cmd_friend },
    {  55,  56, cmd_nickcolor },
    {  65, 255, cmd_divider },
    {  66,  67, cmd_countsync },
    {  60, 255, cmd_click },
    {  68,  69, cmd_bookmarks },
    // --- IRC commands (/ prefix) ---
    {  10,  11, cmd_connect_retry },
    {  12, 255, cmd_nick },
    {  13, 255, cmd_pass },
    {  14, 255, cmd_id },
    {  70, 255, cmd_login },
    {  15,  16, cmd_join },
    {  17,  18, cmd_part },
    {  19,  20, cmd_msg },
    {  62, 255, cmd_reply },
    {  63, 255, cmd_notice },
    {  21,  22, cmd_query },
    {  23, 255, cmd_close_wrapper },
    {  24, 255, cmd_quit },
    {  25, 255, cmd_me },
    {  26, 255, cmd_away },
    {  29, 255, cmd_raw },
    {  30,  31, cmd_whois },
    {  32, 255, cmd_who },
    {  33,  34, cmd_list },
    {  35, 255, cmd_names },
    {  36, 255, cmd_topic },
    {  37, 255, cmd_search },
    {  38, 255, cmd_ignore },
    {  39,  40, cmd_kick },
    {  41,  42, cmd_windows_wrapper },
    {  61, 255, cmd_mode },
};

#define USER_COMMANDS_COUNT ((uint8_t)(sizeof(USER_COMMANDS) / sizeof(USER_COMMANDS[0])))

static const char *pool_nth(uint8_t idx) __z88dk_fastcall ST_NAKED
{
    (void)idx;
    __asm
    ld a,l
    ld hl,_cmd_pool
    or a
    ret z
    ld c,a
    xor a
pool_nth_scan:
    cp (hl)
    inc hl
    jr nz,pool_nth_scan
    dec c
    jr nz,pool_nth_scan
    ret
    __endasm;
}

const char K_DAT[] = "SPECTALK.DAT";

// help_render_page — moved to overlay (SPECTALK.OVL entry 0)
static void help_render_page(void)
{
    overlay_exec_rx(0, 0);
}

static void sys_help(const char *args) __z88dk_fastcall
{
    (void)args;
    help_page = 0;
    enter_overlay_mode(OVERLAY_HELP);
    help_render_page();
}

static void about_process_pending_lines(void) ST_NAKED
{
    __asm
about_pending_loop:
    call _try_read_line_nodrain
    ld a,l
    or a
    ret z
    ld hl,0
    ld (_server_silence_frames),hl
    ld hl,_rx_line
    call _parse_irc_message
    jr about_pending_loop
    __endasm;
}

// overlay_about_render — moved to overlay (SPECTALK.OVL entry 1)
static void sys_about(const char *args) __z88dk_fastcall
{
    (void)args;
    enter_overlay_mode(OVERLAY_ABOUT);
    about_process_pending_lines();
    overlay_exec(1, 0);
}

void parse_user_input(char *line) __z88dk_fastcall
{
    char *args;
    char *cmd_str;
    uint8_t is_sys = 0;

    line = skip_spaces(line);
    if (!*line) return;

    cmd_str = line;

    if (cmd_str[0] == '!') {
        is_sys = 1;
        cmd_str++;
    } else if (cmd_str[0] == '/') {
        cmd_str++;
    } else {
        // FIX-M10: require IRC_READY, not just TCP_CONNECTED
        if (connection_state < STATE_IRC_READY) {
            ERR_NOTCONN();
            return;
        }

        // For regular messages, need to be in a channel/query window
        if (current_channel_idx == 0 || !irc_channel[0]) {
            ui_err(S_NOWIN);
            return;
        }

        irc_send_privmsg(irc_channel, line);
        return;
    }

    args = strchr(cmd_str, ' ');
    if (args) {
        *args++ = '\0';
        args = skip_spaces(args);
    }

    {
        uint8_t c0 = cmd_str[0];
    if ((uint8_t)(c0 - '0') <= 9 && cmd_str[1] == 0) {
        uint8_t idx = c0 - '0';

        if (idx < MAX_CHANNELS && (channels[idx].flags & CH_FLAG_ACTIVE)) {
            switch_or_notify(idx);
        } else {
            set_attr_err();
            main_puts("No window ");
            main_putc(c0);
            main_newline();
        }
        return;
    }}

    {
        uint8_t cmds_left = is_sys ? SYS_CMDS_COUNT : (USER_COMMANDS_COUNT - SYS_CMDS_COUNT);
        const PackedCmd *cmd = is_sys ? USER_COMMANDS : (USER_COMMANDS + SYS_CMDS_COUNT);

        for (; cmds_left != 0; cmds_left--, cmd++) {
            if (st_stricmp(cmd_str, pool_nth(cmd->name_idx)) == 0 ||
                (cmd->alias_idx != CMD_IDX_NONE && st_stricmp(cmd_str, pool_nth(cmd->alias_idx)) == 0)) {
                cmd->fn(args);
                return;
            }
        }
    }

    set_attr_err();
    main_puts("Unknown command: ");
    main_putc(is_sys ? '!' : '/');
    main_print(cmd_str);
}
