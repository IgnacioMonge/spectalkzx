#include <stddef.h>

#ifndef ST_NAKED
#ifdef __SDCC
#define ST_NAKED __naked
#else
#define ST_NAKED
#endif
#endif

static char *csv_next_tok(char **pp) {
    char *tok = *pp;
    char *comma;
    if (!tok || !*tok) return NULL;
    tok = skip_spaces(tok);
    if (!*tok) return NULL;
    comma = tok;
    while (*comma && *comma != ',') comma++;
    if (*comma) { *comma = '\0'; *pp = comma + 1; }
    else *pp = NULL;
    // Trim trailing spaces
    { char *e = comma; while (e > tok && e[-1] == ' ') e--; *e = '\0'; }
    return tok;
}

// Config helpers: reduce repeated st_copy_n/str_to_u16 patterns
static const char *cfg_vp;  // cached val pointer for helpers

static void cfg_s(char *dst, uint8_t sz) __z88dk_callee {
    st_copy_n(dst, cfg_vp, sz);
}

static void cfg_b(uint8_t *dst) __z88dk_fastcall {
    *dst = (uint8_t)str_to_u16(cfg_vp) & 1;
}

enum {
    CFGK_NICK, CFGK_NKPASS, CFGK_NCOLOR, CFGK_NICKSERV,
    CFGK_SERVER, CFGK_PORT, CFGK_PASS, CFGK_THEME,
    CFGK_AUTOJOIN, CFGK_AUTOCONN, CFGK_AUTOAWAY,
    CFGK_FRIENDS, CFGK_IGNORES, CFGK_CHANNELS, CFGK_COUNTSYNC,
    CFGK_BEEP, CFGK_CLICK, CFGK_TRAFFIC, CFGK_TS,
    CFGK_TZ, CFGK_TZLAST, CFGK_DIVIDER, CFGK_NOTIF, CFGK_AUTHCMD, CFGK_BOOKMARK
};

static uint8_t cfg_key_id(const char *key) __z88dk_fastcall ST_NAKED {
    (void)key;
    __asm
    push ix
    ld ix,cfg_key_table
    ld b,25
    ld c,0                   ; C = current ID
cfg_ki_next:
    push hl
    ld e,(ix+0)
    ld d,(ix+1)
cfg_ki_cmp:
    ld a,(hl)
    or a
    jr z,cfg_ki_end
    ld a,(de)
    cp (hl)
    jr nz,cfg_ki_no
    inc hl
    inc de
    jr cfg_ki_cmp
cfg_ki_end:
    ld a,(de)
    cp '='
    jr z,cfg_ki_found
cfg_ki_no:
    pop hl
    inc ix
    inc ix
    inc c
    djnz cfg_ki_next
    ld l,255
    pop ix
    ret
cfg_ki_found:
    pop hl
    ld l,c
    pop ix
    ret
cfg_key_table:
    defw _K_NICK, _K_NKPASS, _K_NCOLOR, _K_NICKSERV
    defw _K_SERVER, _K_PORT, _K_PASS, _K_THEME
    defw _K_AUTOJOIN, _K_AUTOCONN, _K_AUTOAWAY
    defw _K_FRIENDS, _K_IGNORES, _K_CHANNELS, _K_COUNTSYNC
    defw _K_BEEP, _K_CLICK, _K_TRAFFIC, _K_TS
    defw _K_TZ, _K_TZLAST, _K_DIVIDER, _K_NOTIF
    defw _K_AUTHCMD, _K_BOOKMARK
    __endasm;
}

static void cfg_tz_apply(char *key) __z88dk_fastcall ST_NAKED {
    (void)key;
    __asm
    inc hl
    inc hl
    ld a, (hl)
    cp 'l'
    jr z, cfg_tza_last

    ld hl, (_cfg_vp)
    ld a, (hl)
    cp 'r'
    jr nz, cfg_tza_num
    inc hl
    ld a, (hl)
    cp 't'
    jr nz, cfg_tza_num
    ld a, TZ_RTC
    ld (_sntp_tz), a
    ret

cfg_tza_num:
    ld hl, (_cfg_vp)
    call cfg_tza_parse
    cp TZ_RTC
    ret z
    ld (_sntp_tz), a
    ld (_sntp_tz_last), a
    ret

cfg_tza_last:
    ld hl, (_cfg_vp)
    call cfg_tza_parse
    cp TZ_RTC
    ret z
    ld (_sntp_tz_last), a
    ret

cfg_tza_parse:
    ld a, (hl)
    cp '+'
    jr nz, cfg_tza_sign
    inc hl
cfg_tza_sign:
    ld a, (hl)
    cp '-'
    jr nz, cfg_tza_pos
    inc hl
    call _str_to_u16
    ld a, h
    or a
    jr nz, cfg_tza_bad
    ld a, l
    cp 13
    jr nc, cfg_tza_bad
    neg
    ret
cfg_tza_pos:
    call _str_to_u16
    ld a, h
    or a
    jr nz, cfg_tza_bad
    ld a, l
    cp 13
    jr nc, cfg_tza_bad
    ret
cfg_tza_bad:
    ld a, TZ_RTC
    ret
    __endasm;
}

// Apply a key=value pair
static void cfg_apply(char *key, char *val) __z88dk_callee {
    cfg_vp = val;
    switch (cfg_key_id(key)) {
        case CFGK_NICK: cfg_s(irc_nick, IRC_NICK_SIZE); break;
        case CFGK_NKPASS: cfg_s(nickserv_pass, IRC_PASS_SIZE); auth_mode = AUTH_LEGACY; break;
        case CFGK_AUTHCMD: cfg_s(nickserv_pass, AUTH_COMMAND_SIZE); auth_mode = AUTH_LEARNED; break;
        case CFGK_NCOLOR: cfg_b(&nick_color_mode); break;
        case CFGK_NICKSERV: cfg_s(nickserv_nick, AUTH_SERVICE_SIZE); break;
        case CFGK_SERVER: cfg_s(irc_server, IRC_SERVER_SIZE); break;
        case CFGK_PORT: cfg_s(irc_port, IRC_PORT_SIZE); break;
        case CFGK_PASS: cfg_s(irc_pass, IRC_PASS_SIZE); break;
        case CFGK_THEME: {
            uint16_t v = str_to_u16(val);
            if ((uint16_t)(v - 1) <= 2) current_theme = (uint8_t)v;
            break;
        }
        case CFGK_BOOKMARK: {
            uint16_t v = (uint8_t)(*val - '0') < 10 ? str_to_u16(val) : 255;
            bookmark_active_slot = ((v & 0xFF7F) <= 5) ? (uint8_t)v : 0x80;
            break;
        }
        case CFGK_AUTOJOIN:
            cfg_b(&autojoin);
            break;
        case CFGK_AUTOCONN:
            autoconnect = (uint8_t)str_to_u16(val) & 1;
            break;
        case CFGK_AUTOAWAY: {
            uint16_t v = str_to_u16(val);
            if (v <= 60) autoaway_minutes = (uint8_t)v;
            break;
        }
        case CFGK_FRIENDS: {
            uint8_t idx = 0;
            char *tok, *p = val;
            while (idx < MAX_FRIENDS && (tok = csv_next_tok(&p)) != NULL)
                st_copy_n(friend_nicks[idx++], tok, IRC_NICK_SIZE);
            friend_count = idx;
            break;
        }
        case CFGK_IGNORES: {
            char *tok, *p = val;
            while (ignore_count < MAX_IGNORES && (tok = csv_next_tok(&p)) != NULL)
                add_ignore(tok);
            break;
        }
        case CFGK_CHANNELS:
            cfg_s(autojoin_channels, SEARCH_PATTERN_SIZE);
            cfg_s(search_pattern, SEARCH_PATTERN_SIZE);
            break;
        case CFGK_COUNTSYNC: cfg_b(&count_sync_enabled); break;
        case CFGK_BEEP: cfg_b(&beep_enabled); break;
        case CFGK_CLICK: cfg_b(&keyclick_enabled); break;
        case CFGK_TRAFFIC: cfg_b(&show_traffic); break;
        case CFGK_TS: {
            uint16_t v = str_to_u16(val);
            show_timestamps = (v > 2) ? 1 : (uint8_t)v;
            break;
        }
        case CFGK_TZ:
        case CFGK_TZLAST:
            cfg_tz_apply(key);
            break;
        case CFGK_DIVIDER: cfg_b(&show_channel_separators); break;
        case CFGK_NOTIF: cfg_b(&notif_enabled); break;
    }
}
