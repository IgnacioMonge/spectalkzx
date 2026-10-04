/*
 * spectalk_ovl3.c — "What's New" overlay for SpecTalkZX
 * Loaded from SPCTLK3.OVL on demand (ring_buffer on Classic, Page B on Spectranext).
 * Changelog/version come from tools/gen_whatsnew.py; the packed logo is
 * streamed from SPECTALK.DAT (WN_LOGO_OFFSET) because a dithered bust
 * does not fit the 2048B overlay budget.
 *
 * Entry 0: whatsnew_render — What's New screen
 *
 * For each new version: update release/logo.png, changes.txt, version.txt
 * and run make. This file doesn't need editing.
 */

#include "overlay_api.h"
#include "whatsnew_data.h"

#define MAIN_START 3

static uint8_t *logo_src;
static uint16_t logo_have;
static uint16_t logo_left;

static uint8_t logo_get(void)
{
    if (!logo_have) {
        uint16_t n = logo_left;
        if (!n)
            return 0;
        if (n > OVERLAY_SLOT_SIZE)
            n = OVERLAY_SLOT_SIZE;
        esx_buf = (uint16_t)overlay_slot;
        esx_count = n;
        data_fread();
        n = esx_result;
        if (!n) {
            logo_left = 0;
            return 0;
        }
        logo_src = overlay_slot;
        logo_have = n;
        logo_left -= n;
    }
    logo_have--;
    return *logo_src++;
}

/* Blit packed monochrome logo to screen at (start_row, start_col_bytes).
 * Writes explicit zero bytes so redraw over dirty screens matches raw logo. */
static void blit_logo(uint8_t start_row, uint8_t start_phys_col)
{
    uint8_t row, scanline;
    uint8_t ok = 0;

    logo_src = overlay_slot;
    logo_have = 0;
    logo_left = WN_LOGO_PACKED_SIZE;

    data_open();
#ifndef SPECTALK_NEXT
    if (!esx_handle)
        goto finish;
#endif
    if (!data_fseek_set(WN_LOGO_OFFSET))
        goto finish_close;

    for (row = start_row; row < 20; row++) {
        for (scanline = 0; scanline < 8; scanline++) {
            uint8_t y_pixel = (uint8_t)((row - start_row) * 8 + scanline);
            uint16_t mask;
            uint8_t *dst;
            uint8_t b;

            if (y_pixel >= WN_LOGO_H) {
                ok = 1;
                goto finish_close;
            }

            mask = logo_get();
            mask |= (uint16_t)logo_get() << 8;
            dst = (uint8_t *)(
                (uint16_t)(0x4000 | ((row & 0x18) << 8) | (scanline << 8)
                | ((row & 7) << 5)) + start_phys_col);
            for (b = 0; b < WN_LOGO_WB; b++) {
                dst[b] = (mask & 1) ? logo_get() : 0;
                mask >>= 1;
            }
        }
    }
    ok = 1;
finish_close:
    data_close();
finish:
    input_cache_invalidate();
    if (!ok)
        return;

    /* Set attributes: bright white on black */
    {
        uint8_t r, c;
        uint8_t rows_used = (WN_LOGO_H + 7) >> 3;
        for (r = 0; r < rows_used && (start_row + r) < 20; r++) {
            uint8_t *attr = (uint8_t *)(0x5800 + (start_row + r) * 32 + start_phys_col);
            for (c = 0; c < WN_LOGO_WB; c++)
                attr[c] = 0x47; /* bright white ink, black paper */
        }
    }
}

void whatsnew_render(void)
{
    uint8_t a_chan = theme_attrs[TATTR_MSG_CHAN];
    uint8_t a_nick = theme_attrs[TATTR_MSG_NICK];
    uint8_t banner_attr = theme_attrs[0];
    uint8_t version_attr = 0x45 | (banner_attr & 0x38); /* BRIGHT cyan + banner PAPER */
    uint8_t final_attr = 0x43 | (theme_attrs[TATTR_MAIN_BG] & 0x38); /* BRIGHT magenta */
    uint8_t r = MAIN_START + 3;

    /* Clear + separator, then version as centered hero title in magenta */
    overlay_header("");
    { uint8_t len = st_strlen(WN_VERSION);
      print_big_str(MAIN_START, (64 - len) >> 1, WN_VERSION, version_attr); }

    /* Logo on the left */
    blit_logo(r + 1, 1);

    /* Changelog on the right of the logo */
    {
        const char *p = wn_changes;
        uint8_t text_col = (WN_LOGO_WB + 3) * 2;
        uint8_t i, tr = r;

        print_str64(tr++, text_col, "Changes:", a_nick);
        for (i = 1; i < WN_CHANGES && *p; i++) {
            print_char64(tr, text_col, '.', theme_attrs[TATTR_MSG_TIME]);
            print_str64(tr, text_col + 2, p, a_chan);
            tr++;
            while (*p) p++;
            p++;
        }
        if (*p)
            print_str64(tr, text_col, p, final_attr);
    }

    notif_center(S_ANYKEY, theme_attrs[TATTR_MSG_SYS]);
    overlay_rx_release();
}
