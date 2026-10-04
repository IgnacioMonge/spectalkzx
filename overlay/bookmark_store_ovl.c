/*
 * bookmark_store_ovl.c -- cold bookmark load/save/autojoin entries.
 * Linked into SPCTLK3 on Classic and SPCTLK4 on Spectranext.
 */

#include "overlay_api.h"

#define BM_LINE_MAX 256
#define BM_AUTOLOGIN 0x80

extern uint8_t bookmark_sel;
extern uint8_t bookmark_active_slot;
#ifndef SPECTALK_SPECTRANEXT
extern uint8_t bookmark_rows[];
#endif

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
static const char bm_error[] = "Error";
#ifndef SPECTALK_SPECTRANEXT
static const char bm_delete_error[] = "Delete error";
#endif

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

/* Callee stack: return, source, destination, one-byte destination size. */
static const char *bm_next_field(const char *p, char *dst, uint8_t max) __z88dk_callee __naked
{
    (void)p; (void)dst; (void)max;
    __asm
    push ix
    ld ix,0
    add ix,sp
    ld l,(ix+4)
    ld h,(ix+5)
    ld e,(ix+6)
    ld d,(ix+7)
    ld b,(ix+8)
    dec b
bm_field_loop:
    ld a,(hl)
    cp 32
    jr c,bm_field_end
    cp '|'
    jr z,bm_field_end
    ld c,a
    ld a,b
    or a
    jr z,bm_field_skip
    ld a,c
    ld (de),a
    inc de
    dec b
bm_field_skip:
    inc hl
    jr bm_field_loop
bm_field_end:
    ld c,a
    xor a
    ld (de),a
    ld a,c
    cp '|'
    jr nz,bm_field_return
    inc hl
bm_field_return:
    pop ix
    pop bc
    pop de
    pop de
    inc sp
    push bc
    ret
    __endasm;
}

static void bm_apply_line(const char *p)
{
    p = bm_next_field(p, irc_server, IRC_SERVER_SIZE);
    p = bm_next_field(p, irc_port, IRC_PORT_SIZE);
    p = bm_next_field(p, irc_pass, IRC_PASS_SIZE);
    p = bm_next_field(p, autojoin_channels, SEARCH_PATTERN_SIZE);
    st_copy_n(search_pattern, autojoin_channels, SEARCH_PATTERN_SIZE);
    if (*p >= 32) {
        p = bm_next_field(p, nickserv_nick, AUTH_SERVICE_SIZE);
        p = bm_next_field(p, nickserv_pass, AUTH_COMMAND_SIZE);
        auth_mode = (*p == '2') ? AUTH_LEARNED : AUTH_LEGACY;
    } else {
        nickserv_nick[0] = nickserv_pass[0] = 0;
        auth_mode = AUTH_LEGACY;
    }
    auth_profile = bookmark_sel + 1;

    autojoin = (autojoin_channels[0] ? 1 : 0);
}

#if IRC_SERVER_SIZE + IRC_PORT_SIZE + IRC_PASS_SIZE + SEARCH_PATTERN_SIZE + AUTH_SERVICE_SIZE + AUTH_COMMAND_SIZE + 2 > BM_LINE_MAX
#error Bookmark record exceeds buffer
#endif
static char *bm_put_field(char *p, const char *s) __z88dk_callee
{
    while (*s) *p++ = *s++;
    *p++ = '|';
    return p;
}

void bookmarks_apply_ovl(void)
{
    uint8_t mode = overlay_slot[0];
    const char *p;

    p = bm_line(bookmark_sel);
    if (!p || *p <= ' ' || *p == '|') {
        ui_err(bm_error);
        goto fail;
    }
    if (mode) {
        bookmark_active_slot = (uint8_t)(bookmark_sel + 1);
        if (mode == 2) bookmark_active_slot |= BM_AUTOLOGIN;
        config_dirty = 1;
    } else {
        bm_apply_line(p);
    }
    overlay_slot[0] = 1;
    goto done;
fail:
    overlay_slot[0] = 0;
done:
    overlay_rx_release();
}

void bookmarks_save_ovl(void)
{
    char *p = (char *)overlay_slot;
    uint8_t saved;

    if (!irc_server[0] || auth_mode == AUTH_PENDING) goto err;

    p = bm_put_field(p, irc_server);
    p = bm_put_field(p, irc_port);
    p = bm_put_field(p, irc_pass);
    p = bm_put_field(p, search_pattern);
    p = bm_put_field(p, nickserv_nick);
    p = bm_put_field(p, nickserv_pass);
    *p++ = (auth_mode >= AUTH_LEARNED) ? '2' : '0';
    *p++ = '\n';

    esx_buf = (uint16_t)overlay_slot;
    esx_count = (uint16_t)(p - (char *)overlay_slot);
    saved = esx_replace_write(bm_path(bookmark_sel));
#ifndef SPECTALK_SPECTRANEXT
    if (saved == 2) saved = esx_replace_write(bm_path_alt(bookmark_sel));
#endif
    input_cache_invalidate();
    if (saved != 1) goto err;
    overlay_slot[0] = 1;
    overlay_rx_release();
    return;
err:
    overlay_slot[0] = 0;
    ui_err(bm_error);
    overlay_rx_release();
}

#ifndef SPECTALK_SPECTRANEXT
void bookmarks_delete_store_ovl(void)
{
    uint8_t saved;

    if (!(bookmark_rows[bookmark_sel] & 0x80)) {
        overlay_slot[0] = 0;
        overlay_rx_release();
        return;
    }

    esx_buf = (uint16_t)overlay_slot;
    esx_count = 0;
    saved = esx_replace_write(bm_path(bookmark_sel));
    if (saved == 2) saved = esx_replace_write(bm_path_alt(bookmark_sel));
    else if (saved == 1) esx_funlink(bm_path_alt(bookmark_sel));
    if (saved != 1) {
        input_cache_invalidate();
        overlay_slot[0] = 0;
        ui_err(bm_delete_error);
        overlay_rx_release();
        return;
    }

    input_cache_invalidate();
    if ((bookmark_active_slot & BOOKMARK_SLOT_MASK) == bookmark_sel + 1) {
        bookmark_active_slot = BM_AUTOLOGIN;  // explicit OFF; preserve live session
        config_dirty = 1;
    }
    overlay_slot[0] = 1;
    overlay_rx_release();
}
#endif
