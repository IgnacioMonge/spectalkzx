/*
 * spectalk_ovl5.c — Config overlay for SpecTalkZX.
 * Loaded into ring_buffer from SPCTLK5.OVL on demand.
 *
 * Entry 0: config_render_ovl
 */

#include "overlay_api.h"

#ifdef SPECTALK_SPECTRANEXT
#include "../src/config_apply.c"
#endif

#if defined(SPECTALK_SPECTRANEXT) || defined(SPECTALK_NEXT)
#include "../src/config_load.c"

void config_load_ovl(void)
{
    overlay_slot[0] = config_load();
    overlay_rx_release();
}
#endif

static const char cl_friends[] = "friends=";
static const char cl_ignores[] = "ignores=";

static const char cv_on[]       = "on";
static const char cv_off[]      = "off";
static const char cv_set[]      = "set";
static const char cv_notset[]   = "(not set)";
static const char cv_smart[]    = "smart";
static const char cv_pending[]  = "pending";
static const char cv_autojoin[] = "+autojoin";

static uint8_t cfg_col;

extern void rtc_seed_ovl(void);
extern void overlay_rx_release(void);

void rtc_enable_ovl(void)
{
    int8_t old_tz = (sntp_tz == TZ_RTC) ? sntp_tz_last : sntp_tz;
    sntp_tz_last = old_tz;
    sntp_tz = TZ_RTC;
    rtc_seed_ovl();
    if (sntp_tz == TZ_RTC) {
        sntp_init_sent = 0;
        sntp_waiting = 0;
        sntp_queried = 0;
        sys_puts_print(K_TZ, "RTC");
        status_bar_dirty = 1;
        config_dirty = 1;
    } else {
        sntp_tz = old_tz;
        ui_err("No RTC");
    }
    overlay_rx_release();
}

/* Labels are config keys. Values start at even columns 14/44, so label and
 * value attributes never share a cell; long right-column values clip at 64. */
static void cfg_item(const char *label, const char *val)
{
    uint8_t r = g_ps64_y;
    uint8_t col = cfg_col;

    print_str64(r, col, label, theme_attrs[TATTR_MSG_NICK]);
    print_str64(r, col ? 44 : 14, val,
                theme_attrs[val == cv_notset ? TATTR_MSG_TIME : TATTR_MSG_CHAN]);
    if (col) { g_ps64_y++; cfg_col = 0; }
    else cfg_col = 32;
}

/* Names are packed one space apart from column 10. A row wraps unless a
 * maximum-length name (stride - 1) still fits, so five names take two rows. */
static void cfg_list(const char *label, const char *name, uint8_t n, uint8_t stride)
{
    uint8_t row = g_ps64_y;
    uint8_t col = 10;

    print_str64(row, 0, label, theme_attrs[TATTR_MSG_NICK]);
    for (; n != 0; n--, name += stride) {
        if (*name) {
            if (col + stride > 65) { row++; col = 10; }
            print_str64(row, col, name, theme_attrs[TATTR_MSG_CHAN]);
            col = g_ps64_col + 1;
        }
    }
    if (col == 10) print_str64(row, col, cv_notset, theme_attrs[TATTR_MSG_TIME]);
    g_ps64_y = row + 1;
}

void config_render_ovl(void)
{
    char buf[11];
    uint8_t v;

    g_ps64_y = overlay_header("Config");
    cfg_col = 0;

    /* Full-width row: a 31-character host plus :port stays visible. */
    if (irc_server[0]) {
        cfg_item(K_SERVER, irc_server);
        print_char64(g_ps64_y, g_ps64_col, ':', theme_attrs[TATTR_MSG_CHAN]);
        print_str64(g_ps64_y, g_ps64_col + 1, irc_port, theme_attrs[TATTR_MSG_CHAN]);
    } else {
        cfg_item(K_SERVER, cv_notset);
    }
    g_ps64_y++;
    cfg_col = 0;

    cfg_item(K_NICK, irc_nick[0] ? (const char*)irc_nick : cv_notset);
    cfg_item(K_NICKSERV, nickserv_nick[0] ? (const char*)nickserv_nick : cv_notset);
    cfg_item(K_PASS, irc_pass[0] ? cv_set : cv_notset);
    /* Same key selection as config save; a pending /login is never saved. */
    cfg_item(auth_mode >= AUTH_PENDING ? K_AUTHCMD : K_NKPASS,
             !nickserv_pass[0] ? cv_notset :
             auth_mode == AUTH_PENDING ? cv_pending : cv_set);
    cfg_item(K_AUTOCONN, autoconnect ? cv_on : cv_off);
    cfg_item(K_AUTOJOIN, autojoin ? cv_on : cv_off);

    /* Mirrors the saved bookmark= value; inferred UI marks are not saved. */
    v = bookmark_active_slot;
    if (!v || (v & BOOKMARK_INFERRED)) {
        cfg_item(K_BOOKMARK, cv_notset);
    } else if (!(v & BOOKMARK_SLOT_MASK)) {
        cfg_item(K_BOOKMARK, cv_off);
    } else {
        char *p = buf;
        const char *s = cv_autojoin;
        *p++ = '0' + (v & BOOKMARK_SLOT_MASK);
        if (v & 0x80) while ((*p++ = *s++) != 0) ;
        else *p = 0;
        cfg_item(K_BOOKMARK, buf);
    }

    if (autoaway_minutes) {
        fast_u8_to_str(buf, autoaway_minutes); buf[2] = 'm'; buf[3] = 0;
        cfg_item(K_AUTOAWAY, buf);
    } else {
        cfg_item(K_AUTOAWAY, cv_off);
    }

    buf[0] = '0' + current_theme; buf[1] = 0;
    cfg_item(K_THEME, buf);
    cfg_item(K_TS, show_timestamps == 0 ? cv_off :
                    show_timestamps == 1 ? cv_on : cv_smart);
    cfg_item(K_NCOLOR, nick_color_mode ? cv_on : cv_off);
    cfg_item(K_TRAFFIC, show_traffic ? cv_on : cv_off);
    cfg_item(K_DIVIDER, show_channel_separators ? cv_on : cv_off);
    cfg_item(K_NOTIF, notif_enabled ? cv_on : cv_off);
    cfg_item(K_BEEP, beep_enabled ? cv_on : cv_off);
    cfg_item(K_CLICK, keyclick_enabled ? cv_on : cv_off);
    cfg_item(K_COUNTSYNC, count_sync_enabled ? cv_on : cv_off);

    if (sntp_tz == TZ_RTC) {
        buf[0] = 'R'; buf[1] = 'T'; buf[2] = 'C'; buf[3] = 0;
    } else if (sntp_tz < 0) {
        buf[0] = '-'; fast_u8_to_str(buf + 1, (uint8_t)(-sntp_tz)); buf[3] = 0;
    } else {
        buf[0] = '+'; fast_u8_to_str(buf + 1, (uint8_t)sntp_tz); buf[3] = 0;
    }
    cfg_item(K_TZ, buf);

    /* Worst case ends on row 19: five friends and five ignores, two rows each. */
    cfg_list(cl_friends, friend_nicks[0], MAX_FRIENDS, IRC_NICK_SIZE);
    cfg_list(cl_ignores, ignore_list[0], ignore_count, 16);

    notif_center(config_dirty ? "(S)AVE TO SD | ANY KEY TO EXIT" : S_ANYKEY,
                theme_attrs[TATTR_MSG_SYS]);
    overlay_rx_release();
}
