/*
 * spectalk_ovl4.c — Status + Config Save overlay for SpecTalkZX
 * Loaded from SPCTLK4.OVL on demand (ring_buffer on Classic, Page B on Spectranext).
 *
 * Entry 0: status_render_ovl
 * Entry 1: save_config_ovl
 */

#include "overlay_api.h"

/* ================================================================
 * ENTRY 0 — Status display
 * ================================================================ */

extern uint8_t connection_state;
extern uint8_t channels[];
extern char    network_name[];
extern uint8_t ping_latency;
extern uint16_t uptime_minutes;
extern void overlay_rx_release(void);
static const char ss_nick[]  = "Nick:";
static const char ss_srv[]   = "Server:";
static const char ss_net[]   = "Network:";
static const char ss_state[] = "State:";
static const char ss_lag[]   = "Latency:";
static const char ss_up[]    = "Uptime:";
static const char ss_chans[] = "Channels:";

static uint8_t status_row(uint8_t r, const char *lbl, const char *val) __z88dk_callee
{
    print_str64(r, 2, lbl, theme_attrs[TATTR_MSG_NICK]);
    print_str64(r, 11, val, theme_attrs[TATTR_MSG_CHAN]);
    return (uint8_t)(r + 1);
}

void status_render_ovl(void)
{
    uint8_t r = overlay_header("Status");
    uint8_t a_nick = theme_attrs[TATTR_MSG_NICK];
    uint8_t a_chan  = theme_attrs[TATTR_MSG_CHAN];

    r = status_row(r, ss_nick, irc_nick[0] ? (const char *)irc_nick : "(none)");
    r = status_row(r, ss_srv, irc_server[0] ? (const char *)irc_server : "(none)");
    r = status_row(r, ss_net, network_name[0] ? (const char *)network_name : "-");

    { const char *st;
      switch (connection_state) {
          case STATE_IRC_READY:     st = "IRC ready"; break;
          case STATE_TCP_CONNECTED: st = "TCP"; break;
          case STATE_WIFI_OK:       st = "WiFi OK"; break;
          default:                  st = "Offline"; break;
      }
      r = status_row(r, ss_state, st);
    }

    /* Latency */
    { const char *lag;
      switch (ping_latency) {
          case 0:  lag = "Good"; break;
          case 1:  lag = "Medium"; break;
          default: lag = "High"; break;
      }
      r = status_row(r, ss_lag, lag);
    }

    /* Uptime */
    { char ubuf[12];
      char *p = ubuf;
      uint16_t m = uptime_minutes;
      uint16_t h = 0;
      while (m >= 60) { m -= 60; h++; }
      p = u16_to_dec(p, h);
      *p++ = 'h';
      *p++ = ' ';
      fast_u8_to_str(p, (uint8_t)m);
      p += 2;
      *p++ = 'm';
      *p = 0;
      r = status_row(r, ss_up, ubuf);
    }

    r++; /* blank line before channels */
    print_str64(r++, 2, ss_chans, a_nick);
    { uint8_t rl = r, rr = r;  /* two-column row counters */
      uint8_t *ch = channels;
      char c_idx = '0';
      uint8_t i;
      for (i = MAX_CHANNELS; i != 0; i--, ch += CH_SIZE, c_idx++) {
        uint8_t flags = ch[CH_FLAGS_OFF];
        if (flags & CH_FLAG_ACTIVE) {
            char idx[4];
            uint8_t attr = (flags & CH_FLAG_QUERY) ? theme_attrs[TATTR_MSG_TIME] : a_chan;
            uint8_t *tr = (c_idx < '5') ? &rl : &rr;
            uint8_t col = (c_idx < '5') ? 2 : 33;
            idx[0] = ' '; idx[1] = c_idx; idx[2] = '.'; idx[3] = 0;
            print_str64(*tr, col, idx, a_nick);
            print_str64((*tr)++, (uint8_t)(col + 4), (const char *)ch, attr);
        }
      }
    }

    notif_center(S_ANYKEY, theme_attrs[TATTR_MSG_SYS]);
    overlay_rx_release();
}

/* ================================================================
 * ENTRY 1 — Config save to SD
 * Uses overlay_slot (512B) as write buffer.
 * ================================================================ */

extern char *cfg_put(char *p, const char *s) __z88dk_callee;
extern char *cfg_kv(char *p, const char *key, const char *val) __z88dk_callee;
extern char *cfg_put_friends(char *p) __z88dk_fastcall;
extern char *cfg_put_ignores(char *p) __z88dk_fastcall;
extern void main_puts(const char *s) __z88dk_fastcall;
extern void main_print(const char *s) __z88dk_fastcall;
extern void set_attr_sys(void);
extern void ui_err(const char *s) __z88dk_fastcall;

static const char CK_TZLAST[] = "tzlast=";
#define CFG_END       ((char *)overlay_slot + OVERLAY_SLOT_SIZE)
#define CFG_TOO_LARGE (CFG_END + 1)
extern char *cfg_put_autojoin(char *p) __z88dk_fastcall;

static void format_tz_tmp(char *tmp, int8_t tz)
{
    if (tz < 0) { *tmp++ = '-'; tz = -tz; }
    fast_u8_to_str(tmp, (uint8_t)tz);
    tmp[2] = 0;
}

typedef struct {
    const char *k;
    const uint8_t *v;
} CfgItem;

void save_config_ovl(void)
{
    char *p = (char *)overlay_slot;
    char tmp[4];
    uint8_t i, saved;

    static const CfgItem flags[] = {
        { K_THEME, &current_theme },
        { K_BEEP, &beep_enabled },
        { K_CLICK, &keyclick_enabled },
        { K_NCOLOR, &nick_color_mode },
        { K_TRAFFIC, &show_traffic },
        { K_DIVIDER, &show_channel_separators },
        { K_TS, &show_timestamps },
        { K_AUTOCONN, &autoconnect },
        { K_AUTOJOIN, &autojoin },
        { K_NOTIF, &notif_enabled },
        { K_COUNTSYNC, &count_sync_enabled }
    };


    if (irc_server[0])    p = cfg_kv(p, K_SERVER, irc_server);
    if (irc_port[0])      p = cfg_kv(p, K_PORT, irc_port);
    if (irc_nick[0])      p = cfg_kv(p, K_NICK, irc_nick);
    if (irc_pass[0])      p = cfg_kv(p, K_PASS, irc_pass);
    if (nickserv_pass[0]) p = cfg_kv(p, auth_mode >= AUTH_LEARNED ? K_AUTHCMD : K_NKPASS, nickserv_pass);
    if (nickserv_nick[0]) p = cfg_kv(p, K_NICKSERV, nickserv_nick);

    /* W15: cfg_kv small-int trick — values 0-9 passed as (const char*)(uint16_t)N.
     * cfg_kv ASM detects D==0 && E<10 and writes single ASCII digit.
     * CONSTRAINT: all values below MUST be 0-9. */
    for (i = 0; i < 11; i++)
        p = cfg_kv(p, flags[i].k, (const char *)(uint16_t)*(flags[i].v));

    if (bookmark_active_slot && !(bookmark_active_slot & BOOKMARK_INFERRED)) {
        *u16_to_dec(tmp, bookmark_active_slot) = 0;
        p = cfg_kv(p, K_BOOKMARK, tmp);
    }

    if (autoaway_minutes) {
        fast_u8_to_str(tmp, autoaway_minutes); tmp[2] = 0;
        p = cfg_kv(p, K_AUTOAWAY, tmp);
    }

    if (sntp_tz == TZ_RTC) {
        p = cfg_kv(p, K_TZ, "rtc");
    } else {
        format_tz_tmp(tmp, sntp_tz);
        p = cfg_kv(p, K_TZ, tmp);
    }

    {
        int8_t tz = (sntp_tz == TZ_RTC) ? sntp_tz_last : sntp_tz;
        format_tz_tmp(tmp, tz);
        p = cfg_kv(p, CK_TZLAST, tmp);
    }

    p = cfg_put_autojoin(p);

    p = cfg_put_friends(p);
    p = cfg_put_ignores(p);

    if (overlay_mode != OVERLAY_BOOKMARKS) {
        set_attr_sys();
        main_puts("Saving config... ");
    }

    /* Bounded helpers return CFG_TOO_LARGE before any out-of-slot write. */
    if (p > CFG_END) {
        ui_err("Config too large");
        goto done;
    }

    esx_buf = (uint16_t)overlay_slot;
    esx_count = (uint16_t)(p - (char *)overlay_slot);
    saved = esx_replace_write(K_CFG_PRI);
#ifndef SPECTALK_SPECTRANEXT
    if (saved == 2) saved = esx_replace_write(K_CFG_ALT);
#endif
    if (saved != 1) {
        ui_err("Cannot write config");
        goto done;
    }
    if (overlay_mode != OVERLAY_BOOKMARKS) main_print("OK");
    config_dirty = 0;

done:
    input_cache_invalidate();
    /* overlay_slot aliases rx_line; cmd_save() owns the post-call discard gate. */
    overlay_rx_release();
}
