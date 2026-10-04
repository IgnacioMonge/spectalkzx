/*
 * bookmarks_ovl.c -- IRC session bookmark storage for SPCTLK8.OVL.
 */

#include "overlay_api.h"

#define BM_USER_SLOTS 5
#define BM_LINE_MAX 256
#define BM_FIRST_ROW 6
#define BM_LAST_ROW 19
#define BM_INDENT 4
#define BM_ACTIVE_NONE 0xff
#define BM_AUTOLOGIN 0x80
#define BM_OCCUPIED 0x80
#define BM_ROW_MASK 0x7f

extern uint8_t bookmark_sel;
extern uint8_t bookmark_active_slot;
extern uint8_t bookmark_rows[];

#ifdef SPECTALK_SPECTRANEXT
#define BM_PATH "/CFG/SPTBM1.CFG"
#define BM_PATH_SLOT 10
#else
#define BM_PATH "/SYS/CONFIG/SPTBM1.CFG"
#define BM_PATH_SLOT 17
#define BM_PATH_ALT "/SYS/SPTBM1.CFG"
#define BM_PATH_ALT_SLOT 10
#ifndef SPECTALK_NEXT
static char bm_path_buf[] = BM_PATH;
#endif
#endif
static const char bm_title[] = "BOOKMARKS";
static const char bm_footer[] = "ENTER:CONNECT  S:STORE  A:AUTO  D:DELETE  BREAK:SAVE/EXIT";
static const char bm_empty[] = "empty";
static const char bm_autocon[] = " (autocon";
static const char bm_autojoin[] = "/autojoin";

void bookmarks_list_ovl(void);
void bookmarks_cursor_ovl(void);

static const char *bm_path(uint8_t slot) __z88dk_fastcall
{
#ifdef SPECTALK_SPECTRANEXT
    st_copy_n((char *)ring_buffer, BM_PATH, sizeof(BM_PATH));
    ring_buffer[BM_PATH_SLOT] = (uint8_t)('1' + slot);
    return (const char *)ring_buffer;
#elif defined(SPECTALK_NEXT)
    char *path = (char *)overlay_slot + BM_LINE_MAX;
    st_copy_n(path, BM_PATH, sizeof(BM_PATH));
    path[BM_PATH_SLOT] = (uint8_t)('1' + slot);
    return path;
#else
    st_copy_n(bm_path_buf, BM_PATH, sizeof(BM_PATH));
    bm_path_buf[BM_PATH_SLOT] = (uint8_t)('1' + slot);
    return bm_path_buf;
#endif
}

#ifndef SPECTALK_SPECTRANEXT
static const char *bm_path_alt(uint8_t slot) __z88dk_fastcall
{
#ifdef SPECTALK_NEXT
    char *path = (char *)overlay_slot + BM_LINE_MAX;
#else
    char *path = bm_path_buf;
#endif
    st_copy_n(path, BM_PATH_ALT, sizeof(BM_PATH_ALT));
    path[BM_PATH_ALT_SLOT] = (uint8_t)('1' + slot);
    return path;
}
#endif

static const char *bm_line(uint8_t slot) __z88dk_fastcall
{
    uint16_t n;

    esx_fopen(bm_path(slot));
#ifndef SPECTALK_SPECTRANEXT
    if (!esx_handle) esx_fopen(bm_path_alt(slot));
#endif
    if (!esx_handle) {
        input_cache_invalidate();
        return 0;
    }

    esx_buf = (uint16_t)overlay_slot;
    esx_count = BM_LINE_MAX - 1;
    esx_fread();
    n = esx_result;
    esx_fclose();
    input_cache_invalidate();
    if (!n || n >= BM_LINE_MAX) return 0;
    overlay_slot[n] = 0;
    return (const char *)overlay_slot;
}

static uint8_t bm_server_eq(const char *p) __z88dk_fastcall
{
    const char *s = irc_server;
    if (!p) return 0;
    while (*s && *p == *s) {
        p++;
        s++;
    }
    return (!*s && *p == '|');
}

static uint8_t bm_current_active(void)
{
    uint8_t slot = bookmark_active_slot & BOOKMARK_SLOT_MASK;
    if (slot) return (uint8_t)(slot - 1);
    if (!bookmark_active_slot && autoconnect && irc_server[0]) {
        for (slot = 0; slot < BM_USER_SLOTS; slot++) {
            if (bm_server_eq(bm_line(slot))) {
                bookmark_active_slot = (uint8_t)(slot + 1) | BOOKMARK_INFERRED;
                if (autojoin) bookmark_active_slot |= BM_AUTOLOGIN;
                return slot;
            }
        }
    }
    return BM_ACTIVE_NONE;
}

static const char *bm_skip_field(const char *p)
{
    while ((uint8_t)*p >= 32 && *p != '|') p++;
    if (*p == '|') p++;
    return p;
}

static void bm_server_row(uint8_t slot, uint8_t row, const char *p)
{
    char line[64];
    char *q = line;
    char *end = line + 62;
    const char *s;
    uint8_t attr = p ? theme_attrs[10] : theme_attrs[TATTR_MSG_TIME];

    clear_line(row, theme_attrs[TATTR_MAIN_BG]);

    *q++ = (slot == bookmark_sel) ? '>' : ' ';
    *q++ = (uint8_t)('1' + slot);
    *q++ = '.';
    *q++ = ' ';

    if (!p) {
        p = bm_empty;
        while (*p) *q++ = *p++;
    } else {
        while ((uint8_t)*p >= 32 && *p != '|' && q < end) *q++ = *p++;
        if (*p && *p != '|') q[-1] = '>';
        if (*p == '|') p++;
        if ((uint8_t)*p >= 32 && *p != '|' && q < end) {
            *q++ = ':';
            while ((uint8_t)*p >= 32 && *p != '|' && q < end) *q++ = *p++;
        }
        while ((uint8_t)*p >= 32 && *p != '|') p++;
        if (*p == '|') p++;
        if ((uint8_t)*p >= 32 && *p != '|' && q < end - 1) {
            *q++ = ' ';
            *q++ = 'P';
        }
        if ((bookmark_active_slot & BOOKMARK_SLOT_MASK) == slot + 1) {
            s = bm_autocon;
            while (*s && q < end) *q++ = *s++;
            if (bookmark_active_slot & BM_AUTOLOGIN) {
                s = bm_autojoin;
                while (*s && q < end) *q++ = *s++;
            }
            if (q < end) *q++ = ')';
        }
    }
    *q = 0;
    print_str64(row, 0, line, attr);
}

static uint8_t bm_channel_rows(const char *p, uint8_t row, uint8_t last_row)
{
    char line[64];
    uint8_t n;

    if ((uint8_t)*p < 32) return row;
    while ((uint8_t)*p >= 32 && *p != '|' && row <= last_row) {
        p = skip_spaces((char *)p);
        line[0] = ' ';
        line[1] = ' ';
        line[2] = ' ';
        line[3] = ' ';
        n = BM_INDENT;
        while ((uint8_t)*p >= 32 && *p != '|' && n < 62) {
            line[n++] = *p++;
            if (p[-1] == ',' && n > 45) break;
        }
        line[n] = 0;
        print_str64(row++, 0, line, theme_attrs[TATTR_MSG_CHAN]);
    }
    return row;
}

static uint8_t bm_item(uint8_t slot, uint8_t row)
{
    const char *p = bm_line(slot);

    bookmark_rows[slot] = p ? (uint8_t)(row | BM_OCCUPIED) : row;
    bm_server_row(slot, row++, p);
    if (!p || row > BM_LAST_ROW) return row;
    p = bm_skip_field(p);
    p = bm_skip_field(p);
    p = bm_skip_field(p);
    return bm_channel_rows(p, row, row);
}

void bookmarks_render_ovl(void)
{
    overlay_header(bm_title);
    bookmarks_list_ovl();
    notif_center(bm_footer, theme_attrs[TATTR_MSG_SYS]);
    overlay_rx_release();
}

void bookmarks_list_ovl(void)
{
    uint8_t i;
    uint8_t row = BM_FIRST_ROW;

    bm_current_active();
    clear_zone(BM_FIRST_ROW, BM_LAST_ROW - BM_FIRST_ROW + 1, theme_attrs[TATTR_MAIN_BG]);
    for (i = 0; i < BM_USER_SLOTS && row <= BM_LAST_ROW; i++)
        row = bm_item(i, row);
    overlay_rx_release();
}

void bookmarks_rows_ovl(void)
{
    uint8_t prev_slot = overlay_slot[0];
    bm_current_active();
    if (prev_slot < BM_USER_SLOTS)
        bm_server_row(prev_slot, bookmark_rows[prev_slot] & BM_ROW_MASK, bm_line(prev_slot));
    if (prev_slot != bookmark_sel)
        bm_server_row(bookmark_sel, bookmark_rows[bookmark_sel] & BM_ROW_MASK, bm_line(bookmark_sel));
    overlay_rx_release();
}

static void bm_cursor_char(uint8_t slot, uint8_t c)
{
    uint8_t row = bookmark_rows[slot];
    print_char64(row & BM_ROW_MASK, 0, c,
                 (row & BM_OCCUPIED) ? theme_attrs[10] : theme_attrs[TATTR_MSG_TIME]);
}

void bookmarks_cursor_ovl(void)
{
    uint8_t prev_slot = overlay_slot[0];
    if (prev_slot < BM_USER_SLOTS) bm_cursor_char(prev_slot, ' ');
    bm_cursor_char(bookmark_sel, '>');
    overlay_rx_release();
}

void bookmarks_delete_ovl(void)
{
#ifndef SPECTALK_SPECTRANEXT
    overlay_slot[0] = 0;
    overlay_rx_release();
#else
    if (!(bookmark_rows[bookmark_sel] & BM_OCCUPIED)) {
        overlay_slot[0] = 0;
        overlay_rx_release();
        return;
    }

    esx_funlink(bm_path(bookmark_sel));
    if (!esx_result) {
        input_cache_invalidate();
        overlay_slot[0] = 0;
        ui_err("Delete error");
        overlay_rx_release();
        return;
    }
    input_cache_invalidate();
    if ((bookmark_active_slot & BOOKMARK_SLOT_MASK) == bookmark_sel + 1) {
        bookmark_active_slot = BM_AUTOLOGIN;  // explicit OFF; preserve live session
        config_dirty = 1;
    }
    overlay_slot[0] = 1;
    bookmarks_list_ovl();
#endif
}
