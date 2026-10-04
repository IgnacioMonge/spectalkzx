/*
 * irc_handlers.c - IRC message parsing and handling (Table-Driven Optimized)
 * SpecTalk ZX - IRC Client for ZX Spectrum
 * Copyright (C) 2026 M. Ignacio Monge Garcia
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 2 as
 * published by the Free Software Foundation.
 */

#include "../include/spectalk.h"

// =============================================================================
// GLOBAL PARSING CONTEXT (Replaces Stack Args)
// Optimization: Saves pushing 8 bytes to stack for every handler call.
// Handlers access these directly via fast memory loads.
// =============================================================================
static void print_topic_line(char *text) __z88dk_fastcall;
extern char *pkt_usr;
extern char *pkt_par;
extern char *pkt_rest;
extern char *pkt_txt;
extern char *pkt_cmd;

// OPT L7: Cache cmd_id para evitar re-parseo en handlers
extern uint16_t last_cmd_id;

// Empty string sentinel to keep parser globals valid even on malformed lines.
// Must remain zero: parser initialization aliases all empty packet fields here.
extern char pkt_empty[];

// Friend accumulator for one NAMES (353→366) batch notification.
// It must survive unrelated notifications interleaved by the server.
static char names_friend_buf[47];
extern uint8_t names_friend_pos;

// =============================================================================

// Forward decl (used by selective numeric handlers)
static void h_numeric_default(void);
static void session_autoidentify_done(void);
extern uint8_t names_render_grid(char *p) __z88dk_fastcall;
extern uint8_t names_count_line(char *p) __z88dk_fastcall;
extern uint8_t friend_initial_match(char c) __z88dk_fastcall;
// INTERNAL HELPERS
// =============================================================================

// Notification string builder: global pointer + fastcall = ~6B per call
extern char *nb_p;
#define NB_END() (*nb_p = 0)

static void nb(const char *s) __z88dk_fastcall
{
    char *end = temp_input + (notif_enabled ? 56 : LINE_BUFFER_SIZE - 1);
    while (*s && nb_p < end) *nb_p++ = *s++;
}

// Init + first append in one call (saves ~6B per notification vs NB_START+nb)
static void nb_init(const char *s) __z88dk_fastcall
{
    nb_p = temp_input;
    nb(s);
}

static char *split_prefix_nick(char *prefix) __z88dk_fastcall ST_NAKED
{
    (void)prefix;
    __asm
spn_prefix_loop:
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,spn_sep
    jr z,spn_bang
    inc hl
    jr spn_prefix_loop
spn_bang:
    ld (hl),0
    inc hl
spn_host_loop:
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,spn_sep
    inc hl
    jr spn_host_loop
spn_sep:
    ld (hl),0
spn_skip:
    inc hl
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,spn_skip
    cp 127
    jr nc,spn_skip
    ret
    __endasm;
}

static char *split_next_param(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
split_next_param_scan:
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,split_next_param_found
    inc hl
    jr split_next_param_scan
split_next_param_found:
    ld (hl),0
split_next_param_skip:
    inc hl
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,split_next_param_skip
    ret
    __endasm;
}

static char *split_head_param(char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
split_head_param_scan:
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,split_head_param_found
    cp 127
    jr nc,split_head_param_found
    inc hl
    jr split_head_param_scan
split_head_param_found:
    ld (hl),0
split_head_param_skip:
    inc hl
    ld a,(hl)
    or a
    ret z
    cp 33
    jr c,split_head_param_skip
    ret
    __endasm;
}

static uint8_t is_irc_numeric_cmd(const char *cmd) __z88dk_fastcall ST_NAKED
{
    (void)cmd;
    __asm
    inc hl                  ; c[0] already known to be a digit
    ld a,(hl)
    sub '0'
    cp 10
    jr nc,inc_bad
    inc hl
    ld a,(hl)
    sub '0'
    cp 10
    jr nc,inc_bad
    inc hl
    ld a,(hl)
    or a
    jr nz,inc_bad
    ld l,1
    ret
inc_bad:
    ld l,0
    ret
    __endasm;
}

// Notify with prefix+value: replaces nb_init+nb+NB_END+notify at each call site
static void notify2(const char *a, const char *b, uint8_t attr) __z88dk_callee
{
    // Save b at end of temp_input — b may point into temp_input (user input)
    st_copy_n(temp_input + 64, b, 56);
    nb_init(a); nb(temp_input + 64); NB_END();
    notify(temp_input, attr);
}

// 3-piece notification builder for stable strings/pointers already outside temp_input.
static void notify3(const char *a, const char *b, const char *c, uint8_t attr) __z88dk_callee
{
    nb_init(a); nb(b); nb(c); NB_END();
    notify(temp_input, attr);
}

// Helper: Marcar actividad en canales no activos (Deduplicated logic)
static void mark_channel_activity(uint8_t idx) __z88dk_fastcall

{
    if ((uint8_t)idx != current_channel_idx) {
        channels[idx].flags |= CH_FLAG_UNREAD;
        other_channel_activity = 1;
        status_bar_dirty = 1;
    }
}

// Helper: Mostrar razón entre paréntesis si existe y forzar salto
static void print_reason_and_newline(void)
{
    if (*pkt_txt) { main_puts2(S_SP_PAREN, pkt_txt); main_putc(')'); }
    wrap_indent = 0;      // FIX: do not carry timestamp indent to next message
    main_newline();
}

// ASM helper: comprobar si un nick está en la lista de amigos (friend1..friend5).
uint8_t is_tracked_friend(const char *nick) __z88dk_fastcall;

// ASM helper: decrement channels[idx].user_count if > 0.
void channel_dec_users(uint8_t idx) __z88dk_fastcall;

// Helper: Respuesta CTCP optimizada
static void send_ctcp_reply(const char *target, const char *tag, const char *data) __z88dk_callee
{
    net_send_string(S_NOTICE);
    net_send_string(target);
    net_send_string(" :\x01");
    net_send_string(tag);
    if (data && *data) {
        net_send_byte(' ');
        net_send_string(data);
    }
    net_send_line("\x01");
}

// =============================================================================
// HANDLERS (Void signature - access context via globals)
// =============================================================================

static void h_nick(void)
{
    char *new_nick = (*pkt_txt) ? pkt_txt : pkt_par;
    if (*new_nick == ':') new_nick++;

    if (st_stricmp(pkt_usr, irc_nick) == 0) {
        st_copy_n(irc_nick, new_nick, sizeof(irc_nick));
        draw_status_bar();
        notify2("You are now ", irc_nick, ATTR_MSG_SYS);
        if (autojoin_defer_flags & AUTOJOIN_IDENT_SENT) session_autoidentify_done();
        return;
    }

    uint8_t i;
    ChannelInfo *ch;
    for (i = 1, ch = &channels[1]; i < MAX_CHANNELS; i++, ch++) {
        if ((ch->flags & (CH_FLAG_ACTIVE | CH_FLAG_QUERY)) == (CH_FLAG_ACTIVE | CH_FLAG_QUERY)) {
            if (st_stricmp(ch->name, pkt_usr) == 0) {
                st_copy_n(ch->name, new_nick, sizeof(channels[0].name));
                
                if (current_channel_idx == i) {
                    main_print_time_prefix();
                    set_attr_sys();
                    main_puts2("*** ", pkt_usr);
                    main_puts(" is now known as ");
                    main_print(new_nick);
                } else {
                    mark_channel_activity(i);  // audit L10
                }
                draw_status_bar();
            }
        }
    }
}

static void h_cap(void)
{
    const char *p = pkt_par;
    if (!(p[0] == 'L' && (p[1] == 'S' || p[1] == 0))) {
        p = irc_param(1);
        if (!(p[0] == 'L' && (p[1] == 'S' || p[1] == 0))) return;
    }
    net_send_line(S_CAP_END);
}

static void h_ping(void)
{
    const char *token = pkt_txt;
    if (!*token) token = irc_param(0);
    irc_send_pong(token);
}

static void session_autojoin_replay(void)
{
    char c = autojoin_channels[0];
    if (autojoin && (c == '#' || c == '&')) {
        notify2("Autojoining ", autojoin_channels, ATTR_MSG_JOIN);
        irc_send_cmd1(S_JOIN_CMD, autojoin_channels);
        autojoin_defer_flags &= AUTOJOIN_IDENT_SENT;
    }
}

static void session_autojoin_try(void)
{
    if (!(autojoin_defer_flags & AUTOJOIN_MOTD_DONE)) return;
    if (autojoin_defer_flags & AUTOJOIN_IDENT_WAIT) return;
    session_autojoin_replay();
}

static void session_autoidentify_done(void)
{
    if (autojoin_defer_flags & AUTOJOIN_IDENT_WAIT) {
        autojoin_defer_flags &= (uint8_t)~AUTOJOIN_IDENT_WAIT;
        autojoin_ident_grace = 0;
        session_autojoin_try();
    }
}

// PD2: is_ident_success_notice() inlined at single caller (h_privmsg_notice)

static void h_mode(void)
{
    const char *target = irc_param(0);
    const char *mode_text = pkt_txt;
    if (!*target) target = pkt_par;

    if (!*target) return;

    // --- MODE de usuario ---
    if (irc_nick[0] && st_stricmp(target, irc_nick) == 0) {
        // FIX: pkt_txt puede apuntar al target (troceado por tokenize_params)
        // cuando no hay ':' trailing. Usar irc_param(1) primero.
        const char *modes = irc_param(1);
        if (!*modes) modes = pkt_txt;

        if (*modes) {
            if (*modes == ':') modes++;
            st_copy_n(user_mode, modes, sizeof(user_mode));
            draw_status_bar();
        }
        return;
    }

    // --- MODE de canal ---
    if (IS_CHAN_PREFIX(target[0])) {
        int8_t idx = find_channel(target);
        const char *modes;
        if (idx < 0) return;
        modes = irc_param(1);
        if (*modes) {
            st_copy_n(channels[idx].mode, modes, sizeof(channels[0].mode));
            mode_text = modes;
        }
        if ((uint8_t)idx != current_channel_idx) return;

        if (!*mode_text) mode_text = "(unknown)";

        /* Human-readable for +b/-b (ban/unban), notify() for the rest */
        if ((mode_text[0] == '+' || mode_text[0] == '-') && mode_text[1] == 'b') {
            { const char *mask = irc_param(2);
              notify3(pkt_usr,
                      mode_text[0] == '+' ? " sets ban on " : " removes ban on ",
                      *mask ? mask : target,
                      ATTR_MSG_SYS); }
        } else {
            nb_init(pkt_usr);
            nb(" sets mode ");
            nb(mode_text);
            nb(" on ");
            nb(target);
            NB_END();
            notify(temp_input, ATTR_MSG_SYS);
        }
        return;
    }

    set_attr_sys();
    main_print_time_prefix();
    main_puts(S_MODE_SP_SCR);
    main_print(pkt_par);
}

static uint8_t is_ctcp_action_tail(const char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
    inc hl
    ld de,is_ctcp_action_tail_key
    ld b,6
fixed_token_bool_loop:
    ld a,(de)
    cp (hl)
    jr nz,fixed_token_bool_no
    inc de
    inc hl
    djnz fixed_token_bool_loop
    ld l,1
    ret
fixed_token_bool_no:
    ld l,0
    ret
is_ctcp_action_tail_key:
    DEFM "CTION "
    __endasm;
}

static uint8_t auth_service_sender(void)
{
    char *at = strchr(nickserv_nick, '@');
    uint8_t ok;
    if (at) *at = 0;
    ok = st_stricmp(pkt_usr, nickserv_nick[0] ? (const char *)nickserv_nick : S_NICKSERV) == 0;
    if (at) *at = '@';
    return ok;
}

static uint8_t auth_word_boundary(uint8_t c) __z88dk_fastcall
{
    return (uint8_t)((c | 32) - 'a') > 25;
}

static uint8_t auth_match(const char *needle) __z88dk_fastcall
{
    const char *hit = st_stristr(pkt_txt, needle);
    return hit && (hit == pkt_txt || auth_word_boundary(hit[-1])) &&
           auth_word_boundary(hit[st_strlen(needle)]);
}

static void auth_confirm(void)
{
    if (auth_mode == AUTH_PENDING) {
        auth_mode = AUTH_SAVE;
        config_dirty = 1;
    }
}

static void h_privmsg_notice(void)
{
    char *target = pkt_par;
    if (!*target) return;
    if (!*pkt_txt) {
        const char *body = irc_param(1);
        if (!*body) return;
        pkt_txt = (char *)body;
    }
    if ((target[0] == '@' || target[0] == '+' || target[0] == '%' || target[0] == '~') &&
        IS_CHAN_PREFIX(target[1])) {
        target++;
    }
    badge_flash_on();

    uint8_t is_notice = (pkt_cmd[0] == 'N');
    uint8_t is_server = is_notice && strchr(pkt_usr, '.') != NULL;
    // PD2: inlined is_ident_success_notice — single caller
    uint8_t ident_ok = 0;
    uint8_t auth_sender = is_notice && st_stricmp(target, irc_nick) == 0 && auth_service_sender();
    if (auth_sender && !st_stristr(pkt_txt, "not ")) {
        /* ponytail: known acknowledgements only; extend for verified service replies. */
        static const char *const accepted[] = {
            "now identified", "now logged in", "password accepted",
            "authentication successful", "successfully identified"
        };
        uint8_t i;
        for (i = 0; i < sizeof(accepted) / sizeof(accepted[0]); i++) {
            if (auth_match(accepted[i])) {
                ident_ok = 1;
                auth_confirm();
                break;
            }
        }
        if (!ident_ok && st_stristr(pkt_txt, "already identified")) ident_ok = 1;
    }
    if (ident_ok) session_autoidentify_done();

    // Only the configured service (default NickServ) may request the password.
    if (nickserv_pass[0] && auth_mode == AUTH_LEGACY && !ident_ok && auth_sender &&
        !(autojoin_defer_flags & AUTOJOIN_IDENT_SENT) && st_stristr(pkt_txt, "identify")) {
        {
            send_identify(nickserv_pass);
            autojoin_defer_flags |= (AUTOJOIN_IDENT_WAIT | AUTOJOIN_IDENT_SENT);
            autojoin_ident_grace = 0;
            notify("Auto-identifying...", ATTR_MSG_SYS);
            return;
        }
    }

    // Durante búsqueda activa, NOTICE del servidor puede ser rate limit.
    // Filtrar drenaje (state=1) para evitar basura de búsqueda cancelada anterior.
    // Imprimir en main area debajo de "Searching..." (visible con notif on/off),
    // y marcar flag para que h_end_of_list no diga "No matches" falsamente.
    if (is_server && pagination_active && search_flush_state != 1) {
        search_saw_server_notice = 1;
        main_newline();         // siempre: garantiza línea propia debajo de "Searching..."
        set_attr_sys();
        main_print(pkt_txt);
        return;
    }

    // Filtrar mensajes de conexión del servidor (Ident, Looking, Checking, ***)
    // Solo durante handshake — después de 001, dejar pasar (ej: AVISO chatzona)
    if (is_server && (target[0] == '*' || !target[0]) &&
        connection_state < STATE_IRC_READY) {
        char c = pkt_txt[0];
        if (c == 'I' || c == 'L' || c == 'C' || c == '*') return;
    }

    if (is_ignored(pkt_usr) && !is_server) return;

    // Filtrar NOTICE de servicios de red
    if (is_notice && !is_server) {
        char c = pkt_usr[0] | 0x20;  // lowercase first char
        if (c == 'g' || c == 'n' || c == 'm' || c == 'i') {
            if (st_stricmp(pkt_usr, S_GLOBAL) == 0 ||
                st_stricmp(pkt_usr, S_NICKSERV) == 0 ||
                st_stricmp(pkt_usr, "MemoServ") == 0 ||
                st_stricmp(pkt_usr, "InfoServ") == 0) {
                // Filter verbose auth messages
                if (!pkt_txt[0]) return;
                if (pkt_txt[0] == '*') return;
                if (pkt_txt[0] == 'L' && pkt_txt[1] == 'a') return;
                if (strchr(pkt_txt, '!') && strchr(pkt_txt, '@')) return;

                current_attr = ATTR_MSG_TOPIC;
                main_print(pkt_txt);
                return;
            }
        }
    }

    // Detectar NOTICE de ChanServ con topic
    if (is_notice && st_stricmp(pkt_usr, S_CHANSERV) == 0) {
        if (pkt_txt[0] == '[') {
            char *close_bracket = strchr(pkt_txt, ']');
            if (close_bracket && close_bracket[1] == ' ') {
                print_topic_line(close_bracket + 2);
                return;
            }
        }
        current_attr = ATTR_MSG_SERVER;
        main_print(pkt_txt);
        return;
    }

    if (IS_CHAN_PREFIX(target[0])) {
        int8_t idx = find_channel(target);
        if (idx < 0) return;
        mark_channel_activity((uint8_t)idx);
        if (!is_server && count_sync_enabled) count_sync_idle_frames = 0;

        // Mención en canal NO activo: marcar flag y salir
        if (!overlay_mode && (uint8_t)idx != current_channel_idx && irc_nick[0] && st_stristr(pkt_txt, irc_nick)) {
            channels[(uint8_t)idx].flags |= CH_FLAG_MENTION;
            status_bar_dirty = 1;
            mention_beep();
            notify3(pkt_usr, " mentioned you in ", target, ATTR_MSG_NICK);
        }

        if ((uint8_t)idx != current_channel_idx) return;
    } else if (!is_server && count_sync_enabled) {
        count_sync_idle_frames = 0;
    }

    // --- CTCP HANDLING ---
    if (pkt_txt[0] == 1) {
        char *ctcp_cmd = pkt_txt + 1;

        switch (ctcp_cmd[0]) {
            case 'A': // ACTION - "ACTION "
                if (is_ctcp_action_tail(ctcp_cmd)) {
                    char *act = ctcp_cmd + 7;
                    char *end = strchr(act, 1);
                    if (end) *end = 0;

                    if (IS_CHAN_PREFIX(target[0])) {
                        set_attr_chan();
                    } else {
                        int8_t query_idx = add_query(pkt_usr);
                        if (query_idx >= 0) mark_channel_activity((uint8_t)query_idx);
                        set_attr_priv();
                    }
                    main_print_time_prefix();
                    main_puts2(S_ASTERISK, pkt_usr);
                    main_putc(' ');
                    deferred_wrap_start(act);
                    return;
                }
                break;

            case 'V': // VERSION
                if (*(uint16_t *)(ctcp_cmd + 1) == 0x5245) { send_ctcp_reply(pkt_usr, "VERSION", S_APPSHORT); return; }
                break;

            case 'P': // PING
                if (*(uint16_t *)(ctcp_cmd + 1) == 0x4E49 && ctcp_cmd[3] == 'G') {
                    char *p = ctcp_cmd + 4;
                    char *end;
                    if (*p == ' ') p++;
                    end = strchr(p, 1);
                    if (end) *end = 0;
                    send_ctcp_reply(pkt_usr, "PING", p);
                    return;
                }
                break;

            case 'T': // TIME
                if (*(uint16_t *)(ctcp_cmd + 1) == 0x4D49) { send_ctcp_reply(pkt_usr, "TIME", "(no rtc)"); return; }
                break;

        }
        return; // Ignore unhandled CTCP (DCC, CLIENTINFO, etc.)
    }

    // Service messages (NickServ, NiCK, ChanServ, etc.): always main area
    // Prevents long service text from being truncated in ikkle notifications
    if (!IS_CHAN_PREFIX(target[0]) && !is_server) {
        if (st_stricmp(pkt_usr, S_NICKSERV) == 0 ||
            st_stricmp(pkt_usr, S_CHANSERV) == 0 ||
            auth_service_sender()) {
            current_attr = ATTR_MSG_NICK;
            main_puts2(pkt_usr, S_COLON_SP);
            current_attr = ATTR_MSG_TOPIC;
            if (ident_ok) {
                main_print_wrapped_clean(pkt_txt);
            } else {
                deferred_wrap_start(pkt_txt);
            }
            return;
        }
    }

    // --- STANDARD MESSAGE RENDERING ---
    if (pkt_cmd[0] == 'N') {
        if (is_server) {
            main_print_time_prefix();
            current_attr = ATTR_MSG_SERVER;
            main_puts("*** ");
            if (ident_ok) main_print_wrapped_clean(pkt_txt);
            else deferred_wrap_start(pkt_txt);
        } else {
            current_attr = ATTR_MSG_SERVER;
            main_print(pkt_txt);
        }
        return;
    }

    if (IS_CHAN_PREFIX(target[0])) {
        set_attr_chan();
        main_print_time_prefix();

        set_nick_color(pkt_usr);

        // FUSIÓN SEGURA - formato: NICK> mensaje
        main_puts2(pkt_usr, S_PROMPT);

        // Mention: BRIGHT highlight + beep
        set_attr_chan();
        if (!overlay_mode && irc_nick[0] && st_stristr(pkt_txt, irc_nick)) {
            current_attr |= 0x40;
            mention_beep();
        }
        deferred_wrap_start(pkt_txt);
    } else {
        int8_t query_idx = add_query(pkt_usr);
        if (query_idx >= 0) mark_channel_activity((uint8_t)query_idx);

        if (query_idx >= 0 && (uint8_t)query_idx == current_channel_idx) {
            // PM in active query: display normally
            main_print_time_prefix();
            set_nick_color(pkt_usr);
            main_puts2(pkt_usr, S_PROMPT);
            set_attr_priv();
            deferred_wrap_start(pkt_txt);
        } else {
            // PM not in active window
            mention_beep();
            st_copy_n(last_pm_nick, pkt_usr, IRC_NICK_SIZE);
            notif_is_pm = 1;
            if (notif_enabled) {
                // Ikkle: compact notification in footer
                nb_init(pkt_usr); nb(S_COLON_SP); nb(pkt_txt);
                nb(" [ENTER]"); NB_END();
                notify(temp_input, ATTR_MSG_PRIV);
            } else {
                // Classic: full rendering in main area (v1.3.6)
                main_print_time_prefix();
                current_attr = ATTR_MSG_SELF;
                main_puts2(S_ARROW_IN, pkt_usr);
                main_puts(S_COLON_SP);
                set_attr_priv();
                deferred_wrap_start(pkt_txt);
            }
        }
        
        // Auto-reply if away with custom message (global cooldown)
        if (irc_is_away && away_message[0] && !away_reply_cd) {
            // Use NOTICE to avoid loops/flood with other clients/bots
            net_send_string(S_NOTICE);
            net_send_string(pkt_usr);
            net_send_string(S_SP_COLON);
            net_send_line(away_message);
            away_reply_cd = 60;  // seconds
        }
    }
}

static void h_join(void)
{
    // Channel is first param; fallback to pkt_txt only if pkt_par is empty
    // (some servers send ":nick JOIN :#chan" where chan goes to trailing)
    // IRCv3 extended-join: ":nick JOIN #chan account :realname" — pkt_txt is realname
    const char *p0 = irc_param(0);
    char *chan = (char *)(IS_CHAN_PREFIX(p0[0]) ? p0 : pkt_txt);
    if (*chan == ':') chan++;
    if (!*chan) return;  // audit W09: reject malformed JOIN

    if (st_stricmp(pkt_usr, irc_nick) == 0) {
        wrap_indent = 0;
        notify2("Now talking in ", chan, ATTR_MSG_JOIN);

        int8_t idx = find_channel(chan);
        if (idx < 0) idx = add_channel(chan);
        
        if (idx < 0) { ui_err(S_MAXWIN); return; }
        
        if ((uint8_t)idx != current_channel_idx) switch_to_channel((uint8_t)idx);

        // GUARD: re-copy name to slot — workaround for observed corruption
        // when joining channels rapidly while NAMES flood is in progress
        st_copy_n(channels[idx].name, chan, sizeof(channels[0].name));
        
        channels[idx].user_count = 0;
        channels[idx].flags |= CH_FLAG_NAMING;
        counting_new_users = 1;
        st_copy_n(names_target_channel, chan, sizeof(names_target_channel));
        names_pending = 1;
        names_timeout_frames = 0;
        draw_status_bar();
    } else {
        int8_t idx = find_channel(chan);
        if (idx >= 0) {
            channels[idx].user_count++;

            if (!overlay_mode && is_tracked_friend(pkt_usr)) {
                mention_beep();
                nb_init("Friend: "); nb(pkt_usr); nb(S_IN_SP); nb(chan); NB_END();
                notify(temp_input, ATTR_MSG_NICK);
            }

            if ((uint8_t)idx == current_channel_idx) {
                if (show_traffic) {
                    main_print_time_prefix();
                    set_attr_join();
                    main_puts2(S_ARROW_OUT, pkt_usr);
                    main_puts(S_JOINED_SP);
                    main_print(chan);
                }
                draw_status_bar();  // Siempre actualizar conteo
            }
        }
    }
}

static void handle_connection_drop(void)
{
    // FIX: Don't trigger disconnect if already disconnecting (e.g., /quit in progress)
    if (disconnecting_in_progress) return;
    net_disconnect();  // ya resetea canales internamente
    status_bar_dirty = 1;
    notify(S_DISCONN, ATTR_ERROR);
}

static void print_departure(const char *verb) __z88dk_fastcall {
    main_print_time_prefix();
    set_attr_join();
    main_puts(S_ARROW_IN);
    main_puts2(pkt_usr, verb);
    print_reason_and_newline();
}

static void h_part(void)
{
    const char *p0 = irc_param(0);
    char *chan = (*p0) ? (char *)p0 : pkt_par;  // audit L05: const-safe
    if (*chan == ':') chan++;

    int8_t idx = find_channel(chan);
    if (idx >= 0) {
        if (st_stricmp(pkt_usr, irc_nick) == 0) {
            notif_cancel_current();
            notify2(S_YOU_LEFT, chan, ATTR_MSG_JOIN);
            remove_channel((uint8_t)idx);
        } else {
            channel_dec_users(idx);

            if ((uint8_t)idx == current_channel_idx) {
                if (show_traffic) print_departure(" left");
                draw_status_bar();
            }
        }
    }
}

static void h_quit(void)
{
    // audit L09: notify friend quit
    if (!overlay_mode && is_tracked_friend(pkt_usr))
        notify2(pkt_usr, S_QUIT_SUFFIX, ATTR_MSG_NICK);

    if (show_traffic && current_channel_idx) {
        print_departure(S_QUIT_SUFFIX);
    }

    {
        int8_t qidx = find_query(pkt_usr);
        if (qidx > 0) {
            /* W13: close query window when other user QUITs */
            remove_channel((uint8_t)qidx);
        }
    }

    // Decrementar user_count si solo hay 1 canal
    // NOTA: Con múltiples canales no decrementamos porque IRC QUIT no indica
    // en qué canales estaba el usuario. Marcamos los canales como sucios para
    // una resincronización ligera por LIST #canal cuando el runtime esté quieto.
    {
        uint8_t joined_cnt = 0, target_idx = 0;
        ChannelInfo *ch = &channels[1];
        uint8_t i;
        for (i = 1; i < MAX_CHANNELS; i++, ch++) {
            if ((ch->flags & (CH_FLAG_ACTIVE | CH_FLAG_QUERY)) == CH_FLAG_ACTIVE) {
                joined_cnt++;
                target_idx = i;
                if (count_sync_enabled) ch->flags |= CH_FLAG_COUNT_DIRTY;
            }
        }
        if (joined_cnt == 1) {
            if (count_sync_enabled) {
                channels[target_idx].flags &= (uint8_t)~CH_FLAG_COUNT_DIRTY;
                count_sync_quits = 0;
            }
            channel_dec_users(target_idx);
        } else if (count_sync_enabled && joined_cnt > 1 && count_sync_quits != 255) {
            count_sync_quits++;
        }
    }
    draw_status_bar();
}

static void h_kick(void)
{
    // tokenize_params() ya ha separado los params en irc_params[] y ha eliminado espacios en pkt_par.
    const char *channel = irc_param(0);
    const char *target  = irc_param(1);

    if (!*channel || !*target) return;

    int8_t idx = find_channel(channel);

    if (st_stricmp(target, irc_nick) == 0) {
        nb_init("Kicked from "); nb(channel);
        nb(" by "); nb(pkt_usr);
        if (*pkt_txt) { nb(S_COLON_SP); nb(pkt_txt); } NB_END();
        notify(temp_input, ATTR_ERROR);
        // remove_channel() YA llama a draw_status_bar()
        // NOTE-L4: idx > 0 (not >= 0) is correct: channel 0 is Server, can't be kicked from it
        if (idx > 0) remove_channel((uint8_t)idx);
    } else {
        if (idx >= 0) {
            channel_dec_users(idx);
            if ((uint8_t)idx == current_channel_idx) {
                nb_init(S_ASTERISK);
                nb(target);
                nb(" kicked by ");
                nb(pkt_usr);
                if (*pkt_txt) {
                    nb(S_SP_PAREN);
                    nb(pkt_txt);
                    nb(")");
                }
                NB_END();
                notify(temp_input, ATTR_MSG_SYS);
                draw_status_bar();
            }
        }
    }
}



static void h_kill(void)
{
    if (st_stricmp(pkt_par, irc_nick) == 0) {
        nb_init("Killed by "); nb(pkt_usr);
        if (*pkt_txt) { nb(S_COLON_SP); nb(pkt_txt); } NB_END();
        notify(temp_input, ATTR_ERROR);
        handle_connection_drop();
    } else {
        main_print_time_prefix();
        set_attr_join();
        main_puts(S_ASTERISK);
        main_puts(pkt_par);
        main_puts2(" killed by ", pkt_usr);
        print_reason_and_newline();  // FIX BUG-03: faltaba newline
    }
}



static void h_error(void)
{
    set_attr_err();
    main_puts("*** Server: ");
    main_print(*pkt_txt ? (const char *)pkt_txt : S_DISCONN);
    handle_connection_drop();
}

static void h_numeric_401(void)
{
    const char *bad_nick = irc_param(1);
    
    set_attr_err();
    main_puts("Error: ");
    if (*bad_nick) { main_puts(bad_nick); main_putc(' '); }  // audit L06
    main_print(pkt_txt);

    if (*bad_nick) {
        int8_t idx = find_query(bad_nick);
        if (idx > 0) {
            // remove_channel() YA llama a draw_status_bar()
            remove_channel((uint8_t)idx);
        }
    }
}

// 433 ERR_NICKNAMEINUSE: Try alternative nick during registration
static void h_numeric_433(void)
{
    // Only auto-retry if not yet registered
    if (connection_state >= STATE_IRC_READY) {
        notify("Nick already in use", ATTR_ERROR);
        return;
    }
    
    // Append underscore to nick and retry
    // OPT-P2-B: use shared helper
    nick_try_alternate();
    draw_status_bar();
}

static void h_numeric_451(void)
{
    if (pagination_active || search_mode != SEARCH_NONE) {
        cancel_search_state();
        ui_err("Search aborted (not registered)");
        return;
    }

    ui_err("*** Session expired");
    handle_connection_drop();
    set_attr_sys(); main_print("Use /server to reconnect");
}

static void h_numeric_305_306(void)
{
    // 305 = RPL_UNAWAY ("You are no longer marked as being away")
    // 306 = RPL_NOWAWAY ("You have been marked as being away")
    // OPT L5: comparar tercer carácter ('5' vs '6') en lugar de str_to_u16
    uint8_t is_306 = (pkt_cmd[2] == '6');
    irc_is_away = is_306;
    
    if (!is_306) {
        // Ya no away (305) - resetear sistema de auto-away
        autoaway_active = 0;
        autoaway_counter = 0;
    }
    
    draw_status_bar();
    if (is_306 && away_message[0])
        notify2("Away: ", away_message, ATTR_MSG_SYS);
    else
        notify(is_306 ? "Away" : "You are back", ATTR_MSG_SYS);
}

// 324 RPL_CHANNELMODEIS: :server 324 nick #channel +modes
static void h_numeric_324(void)
{
    const char *chan = irc_param(1);
    const char *modes = irc_param(2);
    if (!*chan || !*modes) return;
    int8_t idx = find_channel(chan);
    if (idx < 0) return;
    st_copy_n(channels[idx].mode, modes, sizeof(channels[0].mode));
    if ((uint8_t)idx != current_channel_idx) return;
    draw_status_bar();
    nb_init(S_MODE_SP_SCR);
    nb(chan);
    nb(" ");
    nb(modes);
    NB_END();
    notify(temp_input, ATTR_MSG_SYS);
}

static void print_topic_line(char *text) __z88dk_fastcall
{
    current_attr = ATTR_MSG_TOPIC;
    main_print_time_prefix();
    main_puts(S_TOPIC_PFX);
    deferred_wrap_start(text);
}

static void h_numeric_332(void)
{
    if (*pkt_txt) print_topic_line(pkt_txt);
}

// Helper: incrementa pagination_count con check de overflow
// Retorna 0 si OK, 1 si overflow (y cancela búsqueda)
static uint8_t pagination_inc(void) ST_NAKED {
    __asm
    ld hl, (_pagination_count)
    ld de, PAGINATION_MAX_COUNT
    or a
    sbc hl, de
    jr nc, paginc_limit
    add hl, de
    inc hl
    ld (_pagination_count), hl
    ld l, 0
    ret

paginc_limit:
    call _cancel_search_state
    ld hl, paginc_limit_msg
    call _ui_err
    ld l, 1
    ret

paginc_limit_msg:
    DEFM "Result limit"
    DEFB 0
    __endasm;
}

static void h_numeric_353(void)
{
    const char *msg_chan = irc_param(2);
    const char *target = names_target_channel[0] ? names_target_channel : irc_channel;
    if (!target[0]) return;
    if (st_stricmp(msg_chan, target) != 0) {
        int8_t ci = find_channel(msg_chan);
        if (ci >= 0 && (channels[ci].flags & CH_FLAG_NAMING)) {
            channels[ci].user_count += names_count_line(pkt_txt);
        }
        return;
    }

    names_timeout_frames = 0;

    // After Cancelled/incomplete, manual /names still owns the stream until
    // 366, but pagination_active is off. Keep consuming 353 without output.
    if (show_names_list && !pagination_active) {
        names_pending = 1;
        return;
    }

    // Accumulate user count in temp variable (only committed on 366)
    {
        uint8_t count = names_count_line(pkt_txt);

        if (counting_new_users || !names_pending) {
            names_count_acc = count;
            names_friend_pos = 0;
            counting_new_users = 0;
        } else {
            names_count_acc += count;
        }
    }
    names_pending = 1;

    // Render /names
    if (show_names_list) {
        if (names_render_grid(pkt_txt)) return;

        if (pagination_inc()) return;
        pagination_timeout = 0;
        if (search_data_lost) {
            names_print_summary(1);
            return;
        }
    }

    // Accumulate friends found in NAMES for batch notification on 366.
    // Overlay output is suppressed, so skip this CPU-heavy cosmetic pass there.
    // Skip entirely when no friends configured (avoids per-nick parse cost).
    if (!overlay_mode && friend_count) {
        char *p = pkt_txt;
        if (names_friend_pos >= sizeof(names_friend_buf)) names_friend_pos = 0;
        while (*p) {
            char *ns;
            while (*p == '@' || *p == '+' || *p == '~' || *p == '%' || *p == '&') p++;
            ns = p;
            while (*p && *p != ' ') p++;
            if (friend_initial_match(*ns) && p > ns) {
                char sv = *p; *p = 0;
                if (is_tracked_friend(ns)) {
                    if (!names_friend_pos ||
                        names_friend_pos < sizeof(names_friend_buf) - 3) {
                        if (names_friend_pos > 0) {
                            names_friend_buf[names_friend_pos++] = ',';
                            names_friend_buf[names_friend_pos++] = ' ';
                        }
                        while (*ns && names_friend_pos < sizeof(names_friend_buf) - 1)
                            names_friend_buf[names_friend_pos++] = *ns++;
                        names_friend_buf[names_friend_pos] = 0;
                    }
                }
                *p = sv;
            }
            while (*p == ' ') p++;
        }
    }
}


static void h_numeric_366(void)
{
    const char *msg_chan = irc_param(1);
    int8_t ci = find_channel(msg_chan);

    if (ci >= 0) {
        channels[ci].flags &= (uint8_t)~CH_FLAG_NAMING;
    }

    const char *target = names_target_channel[0] ? names_target_channel : irc_channel;

    if (!target[0]) return;
    if (st_stricmp(msg_chan, target) != 0) return;

    names_pending = 0;
    names_target_channel[0] = '\0';
    
    // Commit user count to status bar:
    // - JOIN automático (names_was_manual=0): siempre actualizar
    // - /names manual (names_was_manual=1): solo si no hubo pérdida de datos ni cancelación
    // FIX BUG-10: write user_count to the channel named in 366, not current channel
    // PD1: collapse update flag — direct condition equivalent
    if (names_count_acc > 0 && (!names_was_manual || !search_data_lost)) {
        if (ci >= 0) channels[ci].user_count = names_count_acc;
    }
    
    // Finalizar paginación de /names
    if (show_names_list && pagination_active) {
        names_print_summary(search_data_lost);
    }

    if (names_was_manual) {
        flush_all_rx_buffers();
    }
    
    show_names_list = 0;
    names_was_manual = 0;  // Reset flag

    // Batch friend notification (accumulated during 353 chunks)
    if (names_friend_pos >= sizeof(names_friend_buf)) names_friend_pos = 0;
    if (names_friend_pos > 0) {
        if (!overlay_mode && !search_data_lost) {
            mention_beep();
            notify3(names_friend_buf, S_IN_SP, msg_chan, ATTR_MSG_NICK);
        }
        names_friend_pos = 0;
    }

    search_data_lost = 0;  // Reset aquí después de usarlo

    draw_status_bar();
}

static void h_numeric_321(void)
{
    if (search_flush_state == 1) return;  // Todavía drenando
    search_header_rcvd = 1;              
    // 321 es solo el header, no hacemos nada visible
    // (ya mostramos "Searching..." al inicio)
}

static uint8_t is_network_param(const char *p) __z88dk_fastcall ST_NAKED
{
    (void)p;
    __asm
    ld de,is_network_param_key
    ld b,8
    jp fixed_token_bool_loop
is_network_param_key:
    DEFM "NETWORK="
    __endasm;
}

static void h_end_of_list(void)
{
    if (search_flush_state == 1) return;  // Todavía drenando

    // OPT L6: Verificar segundo carácter ('2' para 323, '1' para 315)
    uint8_t c1 = pkt_cmd[1];
    if (search_mode == SEARCH_CHAN && c1 != '2') return;  // 323
    if (search_mode == SEARCH_USER && c1 != '1') return;  // 315
    if (search_mode == SEARCH_NONE) return;

    uint8_t data_lost = search_data_lost;

    // Disable pagination BEFORE printing summary to avoid
    // triggering "Any key: more" when there's nothing more to show
    pagination_active = 0;

    set_attr_sys();
    if (pagination_count > 0) {
        main_print(data_lost ? "Done (incomplete)" : "Done");
    } else if (search_saw_server_notice) {
        // NOTICE ya se imprimió vía h_privmsg_notice con newline final;
        // no añadir mensaje falso. Cursor ya está en línea limpia.
    } else if (search_header_rcvd == 1 || search_mode == SEARCH_USER) {
        main_print("No matches");
    } else {
        ui_err("Search denied");
    }

    cancel_search_state();
}

// D9: Shared preamble for search result index rendering
static void search_render_index(void) {
    char buf[6];
    search_index++;
    set_attr_sys();
    main_putc(' ');
    u16_to_dec(buf, search_index);
    main_puts(buf);
    main_puts(S_DOT_SP);
    set_attr_nick();
}

static void list_count_update(const char *chan, const char *users) __z88dk_callee
{
    int8_t ci;
    ci = find_channel(chan);
    if (ci >= 0) {
        channels[ci].user_count = str_to_u16(users);
        channels[ci].flags &= (uint8_t)~CH_FLAG_COUNT_DIRTY;
        if ((uint8_t)ci == current_channel_idx) draw_status_bar();
    }
}

static void h_numeric_322_352(void)
{
    const char *chan, *users, *nick, *user, *host, *t;
    uint8_t len;

    if (!pagination_active) {
        if (!count_sync_enabled) return;
        if (pkt_cmd[1] == '2') { // 322 from silent count LIST
            list_count_update(irc_param(1), irc_param(2));
        }
        return;
    }

    if (search_mode == SEARCH_NONE) return;
    if (search_flush_state == 1) return;

    search_header_rcvd = 2;
    pagination_timeout = 0;

    // Primera entrada: saltar a línea nueva si "Searching... " dejó cursor mid-línea
    if (pagination_count == 0 && main_col) main_newline();

    if (search_mode == SEARCH_CHAN) { // 322
        chan = irc_param(1);
        users = irc_param(2);

        if (!chan[0]) return;
        if (search_pattern[0]) {
            if (IS_CHAN_PREFIX(search_pattern[0])) {
                if (st_stricmp(chan, search_pattern) == 0)
                    list_count_update(chan, users);
            } else if (!st_stristr(chan, search_pattern)) {
                return;
            }
        }

        search_render_index();
        main_puts(chan);

        // Align to even column so attr change falls on cell boundary
        if (main_col & 1) main_putc(' ');

        set_attr_chan();
        main_puts2(S_SP_PAREN, users);
        main_putc(')');

        if (*pkt_txt) {
            set_attr_chan();
            main_putc(' ');
            t = pkt_txt;
            len = 0;
            while (*t && len < 20) { main_putc(*t++); len++; }
            if (*t) main_puts(S_DOTS3);
        }

        main_newline();
        pagination_inc();
        return;
    }

    if (search_mode == SEARCH_USER) { // 352
        // RFC 1459: nick=param[5], host=param[3]
        user = irc_param(2);
        host = irc_param(3);
        nick = irc_param(5);

        if (!nick || !nick[0]) nick = "?";
        if (!host || !host[0]) host = "?";

        if (search_pattern[0]) {
            if (!st_stristr(nick, search_pattern) && !st_stristr(user, search_pattern)) return;
        }

        search_render_index();
        main_puts(nick);

        // Align to even column so attr change falls on cell boundary
        if (main_col & 1) main_putc(' ');

        set_attr_chan();
        main_puts2(S_SP_LBRACKET, user);
        main_putc('@');
        main_puts2(host, "]");

        main_newline();
        pagination_inc();
        return;
    }
}


static void h_numeric_1(void)
{
    if (connection_state >= STATE_IRC_READY) return;

    const char *confirmed_nick = irc_param(0);
    if (confirmed_nick && *confirmed_nick) {
        st_copy_n(irc_nick, confirmed_nick, sizeof(irc_nick));
    }
    connection_state = STATE_IRC_READY;
    cursor_visible = 1;
    if (autojoin && nickserv_pass[0]) {
        autojoin_defer_flags |= AUTOJOIN_IDENT_WAIT;
        autojoin_ident_grace = 0;
    }
    draw_status_bar();
    notify2("Connected to ", irc_server, ATTR_MSG_SYS);
}

static void h_logged_in(void)
{
    /* Learn from the server's explicit account acknowledgement. Legacy autojoin
       still waits for the visible acceptance NOTICE after 900. */
    if (st_stricmp(irc_param(0), irc_nick) == 0) {
        auth_confirm();
        if (auth_mode >= AUTH_LEARNED) session_autoidentify_done();
    }
}

// End of MOTD / no MOTD: delayed autojoin, then friend ISON.
static void h_motd_done(void)
{
    autojoin_defer_flags |= AUTOJOIN_MOTD_DONE;
    if (auth_mode >= AUTH_LEARNED && nickserv_pass[0] &&
        !(autojoin_defer_flags & AUTOJOIN_IDENT_SENT)) {
        send_identify(nickserv_pass);
        autojoin_defer_flags |= AUTOJOIN_IDENT_SENT;
        if (autojoin) autojoin_defer_flags |= AUTOJOIN_IDENT_WAIT;
    }
    if ((autojoin_defer_flags & AUTOJOIN_IDENT_WAIT) &&
        !(autojoin_defer_flags & AUTOJOIN_IDENT_SENT)) {
        autojoin_ident_grace = AUTOJOIN_IDENT_GRACE_FRAMES;
    }
    session_autojoin_try();
    irc_check_friends_online();
}

// RPL_ISON (303): show friends online via ikkle notification
static void h_numeric_303(void)
{
    char *p = pkt_txt;
    char *e;
    if (!p || !*p) return;
    if (*p == ':') p++;
    if (!*p) return;
    // Trim trailing spaces from ISON response
    e = p; while (*e) e++; while (e > p && e[-1] == ' ') e--; *e = 0;
    if (!*p) return;

    notify2("Friends online: ", p, ATTR_MSG_NICK);
}

static void h_numeric_5(void)
{
    // Busca "NETWORK=" en los params tokenizados (no en pkt_par raw)
    uint8_t pi;
    const char *net = NULL;
    irc_params_ensure();
    for (pi = 1; pi < irc_param_count; pi++) {
        const char *p = irc_param(pi);
        if (is_network_param(p)) {
            net = p + 8;
            break;
        }
    }
    if (net) {
        st_copy_n(network_name, net, sizeof(network_name));
        draw_status_bar();
    }
}

// 404 ERR_CANNOTSENDTOCHAN: banned or +m without voice — NOT a join error
static void h_cannotsend(void)
{
    const char *chan = irc_param(1);
    notify2("Cannot send to ", *chan ? chan : S_CHANNEL_WORD, ATTR_ERROR);
}

static void h_join_error(void)
{
    const char *bad_chan = irc_param(1);

    set_attr_err();
    main_puts("Cannot join ");
    main_print(*bad_chan ? bad_chan : (const char *)S_CHANNEL_WORD);
    main_puts(S_COLON_SP);
    main_print(*pkt_txt ? (const char *)pkt_txt : "Access denied");

    // SEGURIDAD: Si la ventana existe (estado zombie), forzar su cierre inmediato.
    // Esto corrige el bug visual de la barra de estado.
    if (*bad_chan) {
        int8_t idx = find_channel(bad_chan);
        if (idx > 0) {
            remove_channel((uint8_t)idx);
        }
    }
}

static void h_numeric_default(void)
{
    // OPT L7: usar last_cmd_id en lugar de re-parsear
    uint16_t num = last_cmd_id;

    if (num == 311) {
        const char *nick = irc_param(1);
        const char *user = irc_param(2);
        const char *host = irc_param(3);

        set_attr_nick();
        main_puts(*nick ? nick : "?");
        set_attr_chan();
        main_puts(S_SP_LBRACKET);
        main_puts(*user ? user : "?");
        main_putc('@');
        main_puts(*host ? host : "?");
        main_putc(']');

        if (*pkt_txt) {
            set_attr_sys();
            main_puts(S_COLON_SP);
            main_print_wrapped_clean(pkt_txt);
        } else {
            main_newline();
        }
        return;
    }

    if (num == 319) {
        set_attr_sys();
        main_puts("Channels: ");
        main_print_wrapped_clean(pkt_txt);
        return;
    }

    // Filtrar ruido de conexión y canal (silencioso)
    // 001-005: welcome/server info, 250-266: stats, 329: channel creation time,
    // 333: topic who/time, 396: host hidden
    // H1: underflow trick — single 8-bit-fitting comparison vs dual 16-bit
    if ((uint16_t)(num - 250) <= 16 ||
        num == 329 || num == 333 || num == 396) {
        return;
    }

    // 2. Gestión de Errores (400-599)
    if ((uint16_t)(num - 400) <= 199) {
        // Si estábamos paginando o buscando, cancelamos para ver el error
        if (pagination_active || search_mode != SEARCH_NONE) cancel_search_state();

        set_attr_err();
        main_puts2("Err ", pkt_cmd); main_puts(S_COLON_SP);

        goto print_tail;
    }

    // 3. Mensajes Informativos Genéricos (Para /raw version, time, etc.)
    if (num == 372 || num == 375 || num == 376) current_attr = ATTR_MSG_MOTD;
    else current_attr = ATTR_MSG_SERVER;

print_tail:
    // Imprimir parámetros intermedios (saltando el 0 que es nuestro nick)
    // H12: outer guard removed — for loop self-protects (1 < 0/1 = false)
    // H9: bypass irc_param() accessor — loop already bounds-checks vs irc_param_count
    {
        uint8_t i;
        irc_params_ensure();
        for (i = 1; i < irc_param_count; i++) {
            const char *p = irc_params[i];
            if (p && *p) {
                main_puts(p);
                main_putc(' ');
            }
        }
    }

    // Imprimir texto final si existe
    if (*pkt_txt) {
        main_print(pkt_txt);
    } else {
        main_newline();
    }
}


static void h_default_cmd(void)
{
    const char *p = pkt_cmd;
    // Ignore single-char command tails
    if (!p[1]) return;

    // Ignore corrupted/fragmented lines: IRC commands are ALL UPPERCASE
    // If any lowercase letter exists, it's likely a fragment (e.g., "PublicWiFi", "spectalk")
    while (*p) {
        if ((uint8_t)(*p - 'a') <= 25) return;
        p++;
    }

    // Unknown no-prefix commands are mid-line fragments (e.g. RIVMSG tails).
    if (pkt_usr == irc_server) return;

    // FIX: Suprimir output de comandos no reconocidos durante búsqueda activa
    // (incluye fase de drenaje donde search_mode es SEARCH_NONE) y durante la
    // ventana de silencio post-cancel (residuos de lista cancelada).
    if (pagination_active || post_cancel_quiet) return;
    
    set_attr_sys();
    main_print_time_prefix();
    main_puts2(">< ", pkt_cmd);
    if (*pkt_par) { main_putc(' '); main_puts(pkt_par); }
    if (*pkt_rest) { main_putc(' '); main_puts(pkt_rest); }
    if (*pkt_txt) { main_puts2(S_SP_COLON, pkt_txt); }
    main_newline();
}

// =============================================================================
// DISPATCH TABLES
// =============================================================================

static void h_ignore(void) { /* Intentional no-op: suppress numerics 2,3,4 */ }

static void h_pong(void)
{
    // Calculate latency from keepalive_timeout (frames since PING)
    // 50 frames = 1 second
    // H17: segregated byte evaluation (high-byte short-circuits 16-bit cmp)
    if ((uint8_t)(keepalive_timeout >> 8) || (uint8_t)keepalive_timeout >= 40) {
        ping_latency = 2;       // High: > 800ms
        notify("High lag", ATTR_ERROR);
    } else if ((uint8_t)keepalive_timeout >= 20) {
        ping_latency = 1;       // Medium: 400-800ms
    } else {
        ping_latency = 0;       // Good: < 400ms
    }
    status_bar_dirty = 1;       // Redraw indicator
    
    // FIX ChatGPT audit: Borrar keepalive_ping_sent SOLO con PONG
    keepalive_ping_sent = 0;
    keepalive_timeout = 0;
}

typedef struct {
    uint16_t id;
    void (*fn)(void);
} CmdEntry;

// Exact case-insensitive text-command dispatch. Each record is a
// high-bit-terminated command followed by its handler pointer.
static void dispatch_text_cmd(void) ST_NAKED
{
    __asm
    ld de,dtc_records
dtc_scan:
    ld a,(de)
    or a
    jr z,dtc_unknown
    ld hl,(_pkt_cmd)
dtc_match:
    ld a,(de)
    inc de
    ld c,a
    and 0x7f
    ld b,a
    ld a,(hl)
    and 0xdf
    cp b
    jr nz,dtc_mismatch
    bit 7,c
    jr nz,dtc_end
    inc hl
    jr dtc_match
dtc_mismatch:
    bit 7,c
    jr nz,dtc_skip_handler
dtc_mismatch_skip:
    ld a,(de)
    inc de
    add a,a
    jr nc,dtc_mismatch_skip
dtc_skip_handler:
    inc de
    inc de
    jr dtc_scan
dtc_end:
    inc hl
    ld a,(hl)
    or a
    jr nz,dtc_skip_handler
    ld a,(_show_names_list)
    or a
    jr z,dtc_call
    ld hl,(_pkt_cmd)
    ld a,(hl)
    cp 'P'
    ret nz
    inc hl
    ld a,(hl)
    cp 'I'                  ; PING
    jr z,dtc_call
    cp 'O'                  ; PONG
    ret nz
dtc_call:
    ld a,(de)
    inc de
    ld l,a
    ld a,(de)
    ld h,a
    jp (hl)
dtc_unknown:
    ld a,(_show_names_list)
    or a
    ret nz
    jp _h_default_cmd

dtc_records:
    DEFB 'P','R','I','V','M','S','G'+128
    DEFW _h_privmsg_notice
    DEFB 'N','O','T','I','C','E'+128
    DEFW _h_privmsg_notice
    DEFB 'P','I','N','G'+128
    DEFW _h_ping
    DEFB 'P','O','N','G'+128
    DEFW _h_pong
    DEFB 'P','A','R','T'+128
    DEFW _h_part
    DEFB 'N','I','C','K'+128
    DEFW _h_nick
    DEFB 'J','O','I','N'+128
    DEFW _h_join
    DEFB 'Q','U','I','T'+128
    DEFW _h_quit
    DEFB 'K','I','C','K'+128
    DEFW _h_kick
    DEFB 'K','I','L','L'+128
    DEFW _h_kill
    DEFB 'M','O','D','E'+128
    DEFW _h_mode
    DEFB 'E','R','R','O','R'+128
    DEFW _h_error
    DEFB 'C','A','P'+128
    DEFW _h_cap
    DEFB 0
    __endasm;
}

static const CmdEntry CMD_TABLE[] = {
    // Comandos Numéricos (0x0001 - 0x03E7)
    { 353, h_numeric_353 },
    { 366, h_numeric_366 },
    { 322, h_numeric_322_352 },
    { 352, h_numeric_322_352 },
    { 323, h_end_of_list },
    { 315, h_end_of_list },
    { 1,   h_numeric_1 },
    { 2,   h_ignore },
    { 3,   h_ignore },
    { 4,   h_ignore },
    { 900, h_logged_in },        // RPL_LOGGEDIN (after NickServ IDENTIFY)
    { 5,   h_numeric_5 },
    { 303, h_numeric_303 },
    { 305, h_numeric_305_306 },
    { 306, h_numeric_305_306 },
    { 321, h_numeric_321 },
    { 324, h_numeric_324 },
    { 332, h_numeric_332 },
    { 376, h_motd_done },
    { 401, h_numeric_401 },
    { 433, h_numeric_433 },
    { 422, h_motd_done },
    { 451, h_numeric_451 },

    { 403, h_join_error },
    { 404, h_cannotsend },
    { 405, h_join_error },
    { 471, h_join_error },
    { 473, h_join_error },
    { 474, h_join_error },
    { 477, h_join_error },
    { 0,   NULL }
};

// =============================================================================
// MAIN PARSING FUNCTIONS
// =============================================================================

void parse_irc_message(char *line) __z88dk_fastcall
{
    char *cmd_start, *params, *rest, *p;
    const char *c;

    // Populate Globals directly (always initialize to safe values)
    pkt_usr = irc_server;
    pkt_par = pkt_empty;
    pkt_rest = pkt_empty;
    pkt_txt = pkt_empty;
    pkt_cmd = pkt_empty;
    irc_param_count = 0;
    irc_params_dirty = 0;
    
    if (!line || !*line) return;

    while (*line && (line[0] == '>' || (uint8_t)*line <= 32 || (uint8_t)*line >= 127)) line++;

    if (line[0] == '@') {
        while ((uint8_t)*line > 32) line++;
        while (*line && ((uint8_t)*line <= 32 || (uint8_t)*line >= 127)) line++;
        if (line[0] == '@') return;
    }
    if (!*line) return;

    if (line[0] == ':') {
        pkt_usr = line + 1;
        cmd_start = split_prefix_nick(pkt_usr);
        if (*cmd_start == 0) return;
    } else {
        cmd_start = line;
    }

    pkt_cmd = cmd_start;

    {
        params = split_head_param(cmd_start);
        if (*params) {
            if (params[0] == ':') {
                *params++ = 0;
                pkt_txt = params;
            } else {
                pkt_par = params;
                rest = split_next_param(params);
                irc_params[0] = pkt_par;
                irc_param_count = 1;
                if (*rest) {
                    if (rest[0] == ':') {
                        *rest = 0;
                        pkt_txt = rest + 1;
                    } else {
                        p = rest;
                        while (*p) {
                            if (p[0] == ' ' && p[1] == ':') {
                                *p = 0;
                                pkt_txt = p + 2;
                                break;
                            }
                            p++;
                        }
                        irc_params_dirty = 1;
                    }
                    pkt_rest = rest;
                }
            }
        }
    }

    c = pkt_cmd;

    // Sanitize only text that can reach display/BPE paths. NAMES payloads are
    // protocol ASCII and hot during JOIN bursts. c[2] is only read after the
    // short-circuit proves the command starts with "35".
    if (*pkt_txt && !overlay_mode &&
        (c[0] != '3' || c[1] != '5' ||
         (c[2] != '3' && c[2] != '6'))) {
        utf8_to_ascii(pkt_txt);
    }

    // --- UNIFIED DISPATCHER ---
    {
        uint16_t cmd_id;
        uint8_t c0 = c[0];
        uint8_t c1 = c[1];
        if ((uint8_t)(c0 - '0') <= 9) {
            if (!is_irc_numeric_cmd(c)) return;
            cmd_id = str_to_u16(pkt_cmd);
        } else if ((uint8_t)((c0 | 0x20) - 'a') <= 25 &&
                   (uint8_t)((c1 | 0x20) - 'a') <= 25) {
            // Normalize to uppercase: 0xDF clears bit 5 (a→A, A→A, \0→\0)
            pkt_cmd[0] = c0 & 0xDF; pkt_cmd[1] = c1 & 0xDF;
            dispatch_text_cmd();
            return;
        } else {
            return;
        }
        
        last_cmd_id = cmd_id;  // OPT L7: guardar para handlers

        // Manual /names owns the main area. Keep the normal pagination/cancel
        // path, but do not let interleaved channel traffic render into it.
        if (show_names_list &&
            cmd_id != 353 && cmd_id != 366) {
            return;
        }

        {
            const CmdEntry *n = CMD_TABLE;
            while (n->id) {
                if (n->id == cmd_id) { n->fn(); return; }
                n++;
            }
        }

        // Only validated three-digit numerics reach this path.
        h_numeric_default();
    }
}


void process_irc_data(void)
{
    uint16_t bytes_this_call = 0;
    uint8_t lines_this_call = 0;
    uint8_t max_lines;
    uint16_t backlog;
    uint8_t refill_limit;
    uint8_t refills_left;

    if (clock_poll_rx()) return;

    if (connection_state < STATE_TCP_CONNECTED) return;

    // Drain UART first, then measure real backlog
    net_pump_rx();

    backlog = (uint16_t)(rb_head - rb_tail) & RING_BUFFER_MASK;

    // Early-out when nothing to process
    if (backlog == 0 && rx_pos == 0) return;

    // Scale parse budget to real backlog
    if (backlog > 1024)      { max_lines = 32; }
    else if (backlog > 512)  { max_lines = 24; }
    else if (backlog > 256)  { max_lines = 16; }
    else if (backlog > 128)  { max_lines = 10; }
    else                     { max_lines = 6;  }

    // Raw peek only; read_key() still owns debounce/consumption.
    refill_limit = 4;
    if (in_inkey()) { max_lines = 4; refill_limit = 1; }
    refills_left = refill_limit;

    // FIX P0-2: Variable para detectar CLOSED sin actuar dentro del bucle
    uint8_t closed_detected = 0;

    while (1) {
        if (!try_read_line_nodrain()) {
            if (!rx_pos || !refills_left || deferred_wrap_active) break;

            backlog = rb_head;
            net_pump_rx();
            if (rb_head == backlog) break;

            --refills_left;
            continue;
        }

        refills_left = refill_limit;

        if (pagination_active) pagination_timeout = 0;

        // FIX: Skip all message processing if disconnect is in progress
        // This prevents ERROR/CLOSED from server triggering reentrant handlers
        if (disconnecting_in_progress) continue;

        // FIX P0-1: Verificar longitud antes de acceder a índices fijos
        // "CLOSED" via 16-bit reads (Z80 little-endian: 'C','L' = 0x4C43)
        if (rx_last_len >= 6 &&
            *(uint16_t*)(rx_line) == 0x4C43 &&
            *(uint16_t*)(rx_line+2) == 0x534F &&
            *(uint16_t*)(rx_line+4) == 0x4445) {
            // FIX P0-2: Solo marcar, no actuar dentro del bucle
            if (!closed_reported) {
                closed_detected = 1;
            }
        } else {
            // Reset silence counter on ANY server activity
            server_silence_frames = 0;
            // FIX ChatGPT audit: NO borrar keepalive_ping_sent aquí
            // Solo debe borrarse al recibir PONG (se hace en handler de PONG)
            parse_irc_message(rx_line);
        }

        // Resident-only cooperative drain: keep UART/ESP from backing up while
        // handlers/rendering consume a burst. Do not move this into frame_wait().
        net_pump_rx();

        if (deferred_wrap_active) break;

        lines_this_call++;

        {
            uint16_t current_budget = RX_TICK_PARSE_BYTE_BUDGET;
            if (pagination_active) current_budget = RX_TICK_PARSE_BYTE_BUDGET * 8;
            bytes_this_call += (rx_last_len + 1);
            if (bytes_this_call >= current_budget) break;  // FIX P0-2: break en vez de return
        }

        if (lines_this_call >= max_lines) break;  // FIX P0-2: break en vez de return
    }

    // FIX P0-2: Actuar DESPUÉS de salir del bucle de consumo
    if (closed_detected) {
        closed_reported = 1;
        ui_err("Connection closed by server");
        net_disconnect();
        draw_status_bar();
    }
}
