/*
 * switcher_ovl.c -- channel switcher render entry for SPCTLK6.OVL.
 * Loaded into ring_buffer. State stays resident in spectalk.c.
 */

#include "overlay_api.h"

#define SCREEN_COLS     64
#define ATTR_STATUS     theme_attrs[1]

#define sw_map          ((uint8_t *)search_pattern)
#define sw_flags_snap   ((uint8_t *)(search_pattern + 10))
#define sw_ch(slot)     (channels + ((uint16_t)(slot) << 5))

extern uint8_t sw_sel;
extern uint8_t sw_first;
extern uint8_t sw_count;
extern uint8_t sw_dirty;

extern uint8_t sw_tab_width(uint8_t slot) __z88dk_fastcall;
extern void switcher_rebuild_map(void);
extern void switcher_close(void);

void switcher_render_ovl(void)
{
    char buf[SCREEN_COLS];
    uint8_t i, j, pos;
    uint8_t last_shown;
    uint8_t tw;

    switcher_rebuild_map();
    if (sw_count < 2) { switcher_close(); return; }

    if (sw_first > sw_sel) sw_first = sw_sel;
    while (sw_first < sw_sel) {
        pos = (sw_first > 0) ? 2 : 0;
        for (i = sw_first; i <= sw_sel; i++) {
            if (i > sw_first) pos += 2;
            pos += sw_tab_width(sw_map[i]);
        }
        if (pos <= SCREEN_COLS) break;
        sw_first++;
    }

    {
        char *p = buf;
        for (i = SCREEN_COLS; i != 0; i--) *p++ = ' ';
    }

    pos = (sw_first > 0) ? 2 : 0;
    last_shown = sw_first;

    for (i = sw_first; i < sw_count; i++) {
        uint8_t slot = sw_map[i];
        uint8_t *ch = sw_ch(slot);
        const char *name = (const char *)ch;
        uint8_t is_q = (ch[CH_FLAGS_OFF] & CH_FLAG_QUERY) ? 1 : 0;
        uint8_t nlen;
        uint8_t need;

        if (*name == '#' || *name == '&') name++;
        nlen = st_strlen(name);
        tw = sw_tab_width(slot);
        need = tw + ((i > sw_first) ? 2 : 0);

        if (pos + need > SCREEN_COLS) break;

        if (i > sw_first) {
            buf[pos] = ' ';
            buf[pos + 1] = '|';
            pos += 2;
        }

        buf[pos] = ' ';
        buf[pos + 1] = '0' + slot;
        buf[pos + 2] = ':';
        if (is_q) buf[pos + 3] = '@';
        for (j = 0; j < nlen; j++) buf[pos + 3 + is_q + j] = name[j];
        pos += tw;
        last_shown = i;
    }

    if (sw_first > 0) buf[0] = '<';
    if (last_shown < sw_count - 1) buf[SCREEN_COLS - 1] = '>';

    print_line64_fast(2, buf, ATTR_STATUS);

    {
        uint8_t sel_attr = (ATTR_STATUS & 0xC0)
                         | ((ATTR_STATUS & 0x07) << 3)
                         | ((ATTR_STATUS >> 3) & 0x07);
        uint8_t *attr_base = (uint8_t *)0x5840;
        uint8_t x0, attr, px, flags;

        pos = (sw_first > 0) ? 2 : 0;
        for (i = sw_first; i <= last_shown; i++) {
            uint8_t slot = sw_map[i];
            uint8_t *ch = sw_ch(slot);
            tw = sw_tab_width(slot);

            if (i > sw_first) pos += 2;
            x0 = pos;
            pos += tw;

            flags = ch[CH_FLAGS_OFF];

            if (i == sw_sel) {
                attr = sel_attr;
            } else if (flags & CH_FLAG_MENTION) {
                attr = ATTR_STATUS | 0x80;
            } else if (flags & CH_FLAG_UNREAD) {
                attr = ATTR_STATUS | 0x40;
            } else {
                continue;
            }

            {
                uint8_t *dst_attr = attr_base + (x0 >> 1);
                for (px = (pos >> 1) - (x0 >> 1); px != 0; px--) {
                    *dst_attr++ = attr;
                }
            }
        }
    }

    for (i = 0; i < sw_count; i++)
        sw_flags_snap[i] = sw_ch(sw_map[i])[CH_FLAGS_OFF];

    sw_dirty = 0;
}

void notice_cmd_ovl(void)
{
    char *target = (char *)overlay_slot;
    char *msg = split_at_space(target);
    if (!msg) { ui_usage("notice nick message"); goto done; }
    autoaway_counter = 0;
    if (autoaway_active) {
        irc_send_cmd2(S_AWAY_CMD, 0, 0);
        autoaway_active = 0;
    }
    irc_send_cmd2("NOTICE", target, msg);
done:
    overlay_rx_release();
}

void away_cmd_ovl(void)
{
    const char *args = (const char *)overlay_slot;
    irc_send_cmd2(S_AWAY_CMD, 0, *args ? args : 0);
    st_copy_n(away_message, args, 32);
    irc_is_away = (*args != 0);
    if (!*args) autoaway_counter = 0;
    autoaway_active = 0;
    draw_status_bar();
    overlay_rx_release();
}
