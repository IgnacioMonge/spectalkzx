/*
 * Cold startup configuration loader.
 *
 * Classic includes this parser in the resident build. Spectranext and native
 * Next include it in SPCTLK5, after the startup overlay is loaded and before
 * any network activity can use ring_buffer.
 */

#include <stddef.h>

// esxDOS wrappers - parameter passing via globals (no ABI risk)
// These are defined in spectalk_asm.asm
// Try to open and read a config file into ring_buffer[]
// ring_buffer is 2048 bytes and unused at startup (before UART activity)
static uint16_t cfg_try_read(const char *path) __z88dk_fastcall {
    uint16_t n;

    esx_fopen(path);
    if (!esx_handle) return 0;

    esx_buf = (uint16_t)(char *)ring_buffer;
    esx_count = RING_BUFFER_SIZE - 2;
    esx_fread();
    n = esx_result;
    if (n > RING_BUFFER_SIZE - 2) n = RING_BUFFER_SIZE - 2;

    esx_fclose();

    ring_buffer[n] = '\0';
    return n;
}

// Parse the config buffer (ring_buffer[]) line by line
// SAFETY-M3: depends on ring_buffer[] being NUL-terminated by cfg_try_read.
// Max read = RING_BUFFER_SIZE-2 = 2046 bytes, NUL at ring_buffer[n].
static void cfg_parse_buf(void) {
    char *p = (char *)ring_buffer;
    char *key, *val, *eol;

    while (*p) {
        // Skip whitespace and blank lines
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '\0') break;

        // Skip comments
        if (*p == ';' || *p == '#') {
            while (*p && *p != '\n' && *p != '\r') p++;
            if (*p == '\r') p++;
            if (*p == '\n') p++;
            continue;
        }

        // Skip empty lines
        if (*p == '\n' || *p == '\r') {
            if (*p == '\r') p++;
            if (*p == '\n') p++;
            continue;
        }

        // Found start of key
        key = p;

        // Find '=' or ':'
        while (*p && *p != '=' && *p != ':' && *p != '\n' && *p != '\r') p++;
        if (*p != '=' && *p != ':') {
            // No separator found, skip rest of line
            while (*p && *p != '\n' && *p != '\r') p++;
            if (*p == '\r') p++;
            if (*p == '\n') p++;
            continue;
        }

        *p = '\0';  // Terminate key
        // Trim trailing whitespace in key
        {
            char *t = p;
            while (t > key && (t[-1] == ' ' || t[-1] == '\t')) *--t = '\0';
        }
        p++;
        // Skip leading whitespace before value
        while (*p == ' ' || *p == '\t') p++;
        val = p;

        // Find end of value
        while (*p && *p != '\n' && *p != '\r') p++;
        eol = p;
        if (*p == '\r') p++;
        if (*p == '\n') p++;
        *eol = '\0';  // Terminate value
        // Trim trailing whitespace in value
        {
            char *t = eol;
            while (t > val && (t[-1] == ' ' || t[-1] == '\t')) *--t = '\0';
        }

        // Apply the key=value pair
        cfg_apply(key, val);
    }
}

uint8_t config_load(void) {
    uint16_t n;

    if (!has_esxdos) return 0;

    n = cfg_try_read(K_CFG_PRI);
    if (!n) n = cfg_try_read(K_CFG_ALT);
    if (!n) return 0;

    cfg_parse_buf();
    return 1;
}
