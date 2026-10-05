/*
 * spectalk_ovl.c — Help overlay (SPCTLK1.OVL)
 * Compiled separately; Classic executes it from ring_buffer and Spectranext
 * from cartridge Page B.
 * overlay_slot (512B, aliased to rx_line) available as scratch data buffer.
 *
 * Entry 0: help_render_ovl
 * Entry 2: windows_render_ovl
 * Entry 3: theme_msg_ovl
 *
 * Strings are plain text (not BPE) — stored in OVL on SD, not in TAP.
 * Supports arbitrary help text length via multi-segment reading (512B each).
 */

#include "overlay_api.h"
#include <string.h>

extern void overlay_rx_release(void);

#ifdef __SDCC
#define ST_NAKED __naked
#else
#define ST_NAKED
#endif

static uint8_t *ovl_p;
static uint8_t *ovl_s;
static uint8_t cur_seg;     /* currently loaded segment */

#define SEGMENT_SIZE 512
#define MAX_SEGS     4      /* up to 2048B of help text */

static const char s_hnot[] = "ANY KEY: NEXT / BREAK: EXIT";

/* Read help text segment N from SPECTALK.DAT into overlay_slot.
 * Supports any segment index (0, 1, 2, ...). */
static void help_load_segment(uint8_t segment)
{
    data_open();
#ifndef SPECTALK_NEXT
    if (!esx_handle) goto help_io_fail;
#endif

    /* Seek directly to the requested 512B help segment. overlay_slot is only
     * 512B, so never use dummy F_READ skips when the help block sits deep in
     * SPECTALK.DAT. */
    esx_buf   = (uint16_t)overlay_slot;
    if (!data_fseek_set((uint16_t)(BPE_HELP_OFFSET + ((uint16_t)segment << 9)))) {
        data_close();
        goto help_io_fail;
    }

    esx_count = 512;
    data_fread();
    data_close();
    input_cache_invalidate();
    { uint16_t n = esx_result;
      if (n == 0) { overlay_slot[0] = 0; return; }  /* EOF — empty segment */
      if (n >= SEGMENT_SIZE) n = SEGMENT_SIZE - 1;
      overlay_slot[n] = 0;
    }
    cur_seg = segment;
    return;

help_io_fail:
    input_cache_invalidate();
    overlay_slot[0] = 0;
    overlay_mode = 0;
}

/* skip_partial removed: bpe_build.py pads help text with NUL bytes so that
 * 512-byte segment boundaries always fall on complete line endings.
 * No partial lines exist at segment starts. */

/* Try to load next segment when current one is exhausted.
 * Returns 1 if more data available, 0 if EOF. */
static uint8_t load_next_seg(void)
{
    if (cur_seg + 1 >= MAX_SEGS) return 0;
    help_load_segment(cur_seg + 1);
    if (!overlay_slot[0]) return 0;         /* EOF */
    ovl_p = overlay_slot;
    return *ovl_p ? 1 : 0;
}

void help_render_ovl(void)
{
    uint8_t r, n, c;
    uint8_t seg_cum[MAX_SEGS];  /* cumulative line count after each segment */
    uint8_t total_lines = 0;
    uint8_t num_segs = 0;
    uint8_t target_line;
    uint8_t seg;

    /* Phase 1: Count complete lines across all segments */
    for (seg = 0; seg < MAX_SEGS; seg++) {
        help_load_segment(seg);
        if (!overlay_slot[0]) break;        /* EOF or error */

        num_segs = seg + 1;
        { uint8_t *p = overlay_slot;
          /* No skip_partial needed: build script pads segments to line boundaries */
          while (*p) {
              while (*p && *p != 10 && *p != 13) p++;
              if (*p) {
                  total_lines++;    /* complete line (has newline) */
                  if (*p == 13) p++;
                  if (*p == 10) p++;
              }
          }
        }
        seg_cum[seg] = total_lines;
    }

    if (!total_lines) { overlay_mode = 0; return; }

    /* Calculate total pages */
    { uint8_t total_pages = 0;
      { uint8_t rem = total_lines;
        while (rem > 0) { total_pages++; rem = (rem > LINES_PER_PAGE) ? rem - LINES_PER_PAGE : 0; }
      }

    if (help_page >= total_pages) help_page = 0;

    /* Which line does the current page start at? */
    target_line = help_page * LINES_PER_PAGE;

    /* Find which segment contains target_line */
    seg = 0;
    while (seg < num_segs - 1 && target_line >= seg_cum[seg]) seg++;

    /* Load that segment */
    help_load_segment(seg);
    ovl_p = overlay_slot;
    if (seg > 0) {
        /* Adjust target to be relative within this segment */
        target_line -= seg_cum[seg - 1];
    }

    /* Skip to target line within loaded segment */
    n = target_line;
    while (n--) {
        if (!*ovl_p) {
            if (!load_next_seg()) {
                help_page = 0;
                help_load_segment(0);
                ovl_p = overlay_slot;
                break;
            }
        }
        while (*ovl_p && *ovl_p != 13 && *ovl_p != 10) ovl_p++;
        if (*ovl_p == 13) ovl_p++;
        if (*ovl_p == 10) ovl_p++;
    }

    /* Header: "Help 2/4" */
    { char title[12];
      char *t = title;
      *t++ = 'H'; *t++ = 'e'; *t++ = 'l'; *t++ = 'p'; *t++ = ' ';
      *t++ = '1' + help_page;
      *t++ = '/';
      *t++ = '0' + total_pages;
      *t = 0;
      r = overlay_header(title);
    }

    /* Phase 2: Render lines */
    for (n = LINES_PER_PAGE; n; n--, r++) {
        /* If segment exhausted mid-page, load next */
        if (!*ovl_p) {
            if (!load_next_seg()) break;
        }

        ovl_s = ovl_p;
        while ((c = *ovl_p) != 0 && c != 10 && c != 13 && c != 9)
            ovl_p++;

        *ovl_p = 0;
        if (c == 9) {
            print_str64(r, 2, (const char *)ovl_s, theme_attrs[TATTR_MSG_NICK]);
            *ovl_p = 9;
            ovl_s = ++ovl_p;
            while ((c = *ovl_p) != 0 && c != 10 && c != 13) ovl_p++;
            *ovl_p = 0;
            print_str64(r, 18, (const char *)ovl_s, theme_attrs[TATTR_MSG_CHAN]);
        } else {
            print_str64(r, 2, (const char *)ovl_s, theme_attrs[TATTR_MSG_CHAN]);
        }
        *ovl_p = c;
        if (*ovl_p == 13) ovl_p++;
        if (*ovl_p == 10) ovl_p++;
    }
    } /* end of total_pages scope */

    if (help_page == 0) notif_center(s_hnot, theme_attrs[TATTR_MSG_SYS]);
    overlay_rx_release();
}

/* ================================================================
 * ENTRY 1 — Draw banner (moved from SPCTLK2 to free space for globe)
 * Called from apply_theme() and init_screen() via overlay_exec(0,1)
 * ================================================================ */

void banner_render_ovl(void)
{
    uint8_t *t = theme_raw + (current_theme - 1) * 25;
    uint8_t banner_attr = theme_attrs[0];
    uint8_t bp = (banner_attr >> 3) & 0x07;

    clear_line(0, banner_attr | 0x40);
    clear_line(1, banner_attr & 0xBF);
    print_big_str(0, 0, "SPECTALKZX " VERSION " - ", banner_attr);
    print_big_str(0, 19, S_APPDESC, banner_attr);

    if (t[21] != 0x40) {
        uint8_t b1 = (t[21] & 0x7F) | 0x40, b2 = (t[22] & 0x7F) | 0x40;
        uint8_t b3 = (t[23] & 0x7F) | 0x40, b4 = (t[24] & 0x7F) | 0x40;
        uint8_t sb = 0x40 | (bp << 3) | bp;
        *(uint8_t *)(0x5800 + 27) = sb;
        *(uint8_t *)(0x5800 + 28) = b1;
        *(uint8_t *)(0x5800 + 29) = b2;
        *(uint8_t *)(0x5800 + 30) = b3;
        *(uint8_t *)(0x5800 + 31) = b4;
        *(uint8_t *)(0x5820 + 27) = b1;
        *(uint8_t *)(0x5820 + 28) = b2;
        *(uint8_t *)(0x5820 + 29) = b3;
        *(uint8_t *)(0x5820 + 30) = b4;
        *(uint8_t *)(0x5820 + 31) = 0x40 | ((t[24] & 0x07) << 3) | ((t[20] >> 3) & 0x07);
        draw_badge_dither(5);
    } else {
        print_big_str(0, bp ? 58 : 61, bp ? "_ [] X" : "<<<", banner_attr);
    }
    { uint8_t i; uint8_t *p = (uint8_t *)0x4040; for (i = 0; i < 32; i++) *p++ = 0xFF; }
    overlay_rx_release();
}

/* ================================================================
 * ENTRY 2 — /channels listing
 * ================================================================ */

void windows_render_ovl(void)
{
    uint8_t i, n = 0;
    uint8_t *ch = channels;

    set_attr_sys();
    main_puts("Open windows:");

    for (i = 0; i < MAX_CHANNELS; i++, ch += CH_SIZE) {
        uint8_t f = ch[CH_FLAGS_OFF];

        if (f & CH_FLAG_ACTIVE) {
            main_putc(' ');
            if (i == current_channel_idx) main_putc('*');

            main_putc((char)('0' + i));
            main_putc(':');

            if (i == 0) {
                main_puts(S_SERVER);
            } else {
                if (f & CH_FLAG_MENTION) {
                    set_attr_priv();
                    main_putc('!');
                }
                if (f & CH_FLAG_QUERY)  main_putc('@');
                if (f & CH_FLAG_UNREAD) main_putc('+');

                main_puts((const char *)ch);

                if (f & CH_FLAG_MENTION) set_attr_sys();
            }
            n++;
        }
    }

    if (n == 0) main_puts(" (none)");
    main_newline();
    overlay_rx_release();
}

/* ================================================================
 * ENTRY 3 — /theme status line
 * search_pattern[0]: 0 already, 1 changed
 * search_pattern[1]: theme id 1..3
 * ================================================================ */

static const char *theme_name_ovl(uint8_t t)
{
    if (t == 2) return "The Terminal";
    if (t == 3) return "The Commander";
    return "Default";
}

void theme_msg_ovl(void)
{
    sys_puts_print(search_pattern[0] ? "Theme set to " : "Already using ",
                   theme_name_ovl((uint8_t)search_pattern[1]));
    overlay_rx_release();
}

/* Only an explicit /login can nominate a destination and command. */
void login_cmd_ovl(void)
{
    char *target = (char *)overlay_slot;
    char *text = split_at_space(target);
    char *p;
    /* A new attempt replaces a pending one, e.g. after a mistyped password. */
    if (!text || !*target || !*text ||
        st_strlen(target) >= AUTH_SERVICE_SIZE ||
        st_strlen(text) >= AUTH_COMMAND_SIZE ||
        strchr("#&$*+@%~", target[0]) || strchr(text, '|')) goto bad;

    /* One scan also avoids SDCC's stale-HL fold of consecutive strchr calls. */
    for (p = target; *p; p++)
        if (*p == ',' || *p == ':' || *p == '|') goto bad;

    st_copy_n(nickserv_nick, target, AUTH_SERVICE_SIZE);
    st_copy_n(nickserv_pass, text, AUTH_COMMAND_SIZE);
    auth_mode = AUTH_PENDING;
    autojoin_defer_flags |= AUTOJOIN_IDENT_SENT;
    if (autojoin) autojoin_defer_flags |= AUTOJOIN_IDENT_WAIT;
    irc_send_cmd2("PRIVMSG", nickserv_nick, nickserv_pass);
    notify("Waiting for login confirmation", ATTR_MSG_SYS);
    goto done;
bad:
    ui_usage("login service command [arguments]");
done:
    overlay_rx_release();
}
