/*
 * local_cmds_ovl.c -- Cold local management commands for SPCTLK7.OVL.
 */

#include "overlay_api.h"

void ignore_cmd_ovl(void)
{
    char *p = (char *)overlay_slot;
    uint8_t i;

    if (!*p) {
        set_attr_sys();
        if (ignore_count == 0) {
            main_print("Ignore list is empty");
        } else {
            main_puts("Ignored (");
            main_putc('0' + ignore_count);
            main_puts("): ");
            for (i = 0; i < ignore_count; i++) {
                if (i > 0) {
                    main_putc(',');
                    main_putc(' ');
                }
                main_puts(ignore_list[i]);
            }
            main_newline();
        }
        goto done;
    }

    if (p[0] == '-') {
        p++;
        p = skip_spaces(p);
        if (!*p) {
            ui_usage("ignore -nick to unignore");
            goto done;
        }

        split_at_space(p);

        if (remove_ignore(p)) {
            notify2("Unignored: ", p, ATTR_MSG_SYS);
            config_dirty = 1;
        } else {
            notify2("Not in ignore list: ", p, ATTR_MSG_SYS);
        }
        goto done;
    }

    split_at_space(p);

    if (add_ignore(p)) {
        notify2("Now ignoring: ", p, ATTR_MSG_SYS);
        config_dirty = 1;
    } else if (is_ignored(p)) {
        notify2("Already ignoring: ", p, ATTR_MSG_SYS);
    } else {
        ui_err("Ignore list full");
    }

done:
    overlay_rx_release();
}

void pass_cmd_ovl(void)
{
    const char *args = (const char *)overlay_slot;
    const char *msg;

    if (!*args) {
        sys_puts_print("Server password: ", irc_pass[0] ? "(set)" : "(not set)");
        goto done;
    }

    if (st_stricmp(args, "clear") == 0 || st_stricmp(args, "none") == 0) {
        irc_pass[0] = '\0';
        msg = "Password cleared";
    } else {
        st_copy_n(irc_pass, args, IRC_PASS_SIZE);
        msg = "Password set";
    }

    notify(msg, ATTR_MSG_SYS);
    config_dirty = 1;

done:
    overlay_rx_release();
}

static uint8_t set_or_toggle_flag_ovl(uint8_t *flag, const char *label, const char *args) __z88dk_callee
{
    if (*args) {
        if (args[0] == '1' || st_stricmp(args, "on") == 0) *flag = 1;
        else if (args[0] == '0' || st_stricmp(args, "off") == 0) *flag = 0;
        else { ui_usage("on|off"); return 0; }
    } else {
        *flag = !*flag;
    }
    sys_puts_print(label, *flag ? SB_ON : SB_OFF);
    config_dirty = 1;
    return 1;
}

typedef struct {
    uint8_t *ptr;
    const char *label;
} FlagDef;

void local_setting_cmd_ovl(void)
{
    uint8_t id = overlay_slot[0];
    const char *args = (const char *)overlay_slot + 1;

    static const FlagDef flags[] = {
        { &beep_enabled, "Beep: " },
        { &keyclick_enabled, "Click: " },
        { &nick_color_mode, "Nick color: " },
        { &show_traffic, "Show traffic: " },
        { &notif_enabled, "Notifications: " },
        { 0, 0 },
        { &autoconnect, "Autoconnect: " },
        { &autojoin, "Autojoin: " },
        { &show_channel_separators, "Divider: " },
        { &count_sync_enabled, "Count sync: " }
    };

    if (id == 5) {
        if (*args) {
            if (args[0] == '0' || st_stricmp(args, "off") == 0) show_timestamps = 0;
            else if (args[0] == '1' || st_stricmp(args, "on") == 0) show_timestamps = 1;
            else if (args[0] == '2' || st_stricmp(args, "smart") == 0) show_timestamps = 2;
            else { ui_usage("off|on|smart"); goto done; }
        } else {
            if (++show_timestamps > 2) show_timestamps = 0;
        }
        if (show_timestamps == 2) {
            last_ts_hour = 0xFF;
            last_ts_minute = 0xFF;
        }
        sys_puts_print("Timestamps: ", show_timestamps == 0 ? SB_OFF :
                       show_timestamps == 1 ? SB_ON : SB_SMART);
        config_dirty = 1;
    } else if (id <= 9 && flags[id].ptr) {
        if (!set_or_toggle_flag_ovl(flags[id].ptr, flags[id].label, args)) goto done;
        if ((uint8_t)(id - 6) < 2) bookmark_active_slot = 0;
        if (id == 6 && !autoconnect) {
            autojoin = 0;
            autojoin_channels[0] = 0;
            search_pattern[0] = 0;
        } else if (id == 7) {
            if (autojoin) {
                autoconnect = 1;
            }
        } else if (id == 8 && !show_channel_separators) {
            channel_context_next_row = 0;
            channel_context_pending = 0;
        } else if (id == 9 && !count_sync_enabled) {
            count_sync_idle_frames = 0;
            count_sync_quits = 0;
        }
    }

done:
    overlay_rx_release();
}

void autoaway_cmd_ovl(void)
{
    const char *args = (const char *)overlay_slot;

    if (!*args) {
        set_attr_sys();
        main_puts(S_AUTOAWAY);
        main_puts(": ");
        if (autoaway_minutes) {
            puts_u8_nolz(autoaway_minutes);
            main_print(SB_MIN);
        } else {
            main_print(SB_OFF);
        }
        goto done;
    }

    if (*args == '0' || st_stricmp(args, "off") == 0) {
        autoaway_minutes = 0;
        autoaway_counter = 0;
        autoaway_active = 0;
        sys_puts_print(S_AUTOAWAY, " disabled");
        config_dirty = 1;
        goto done;
    }

    {
        uint16_t raw = str_to_u16(args);
        if (raw < 1 || raw > 60) {
            ui_err(SB_RANGE_MINUTES);
            goto done;
        }
        autoaway_minutes = (uint8_t)raw;
    }

    autoaway_counter = 0;
    set_attr_sys();
    main_puts(S_AUTOAWAY);
    main_puts(" set to ");
    puts_u8_nolz(autoaway_minutes);
    main_print(SB_MIN);
    config_dirty = 1;

done:
    overlay_rx_release();
}

void friend_cmd_ovl(void)
{
    char *args = (char *)overlay_slot;
    uint8_t i;
    char *fn;
    char *free_fn = 0;

    if (!*args) {
        set_attr_sys();
        main_puts("Friends:");
        for (i = MAX_FRIENDS, fn = friend_nicks[0]; i != 0; i--, fn += IRC_NICK_SIZE) {
            if (*fn) { main_putc(' '); main_puts(fn); }
        }
        main_newline();
        goto done;
    }

    for (i = MAX_FRIENDS, fn = friend_nicks[0]; i != 0; i--, fn += IRC_NICK_SIZE) {
        if (*fn) {
            if (st_stricmp(fn, args) == 0) {
                *fn = '\0';
                friend_count--;
                set_attr_sys();
                main_puts("- ");
                main_print(args);
                config_dirty = 1;
                goto done;
            }
        } else if (!free_fn) {
            free_fn = fn;
        }
    }

    if (free_fn) {
        st_copy_n(free_fn, args, IRC_NICK_SIZE);
        friend_count++;
        set_attr_sys();
        main_puts("+ ");
        main_print(args);
        config_dirty = 1;
        goto done;
    }

    ui_err("Max 5 friends");

done:
    overlay_rx_release();
}

/* /id remains the legacy IDENTIFY shortcut; /login teaches a complete payload. */
void id_cmd_ovl(void)
{
    const char *args = (const char *)overlay_slot;
    const char *pass = *args ? args : nickserv_pass;
    if (*args) {
        st_copy_n(nickserv_pass, args, IRC_PASS_SIZE);
        auth_mode = AUTH_LEGACY;
    }
    if (!nickserv_pass[0] || auth_mode == AUTH_PENDING) {
        ui_err("No confirmed password");
    } else {
        send_identify(pass);
        notify2("Identifying with ", nickserv_nick[0] ? (const char *)nickserv_nick : "NickServ", ATTR_MSG_SYS);
    }
    overlay_rx_release();
}

void reply_cmd_ovl(void)
{
    if (!last_pm_nick[0]) ui_err("No recent PM");
    else if (!overlay_slot[0]) ui_usage("reply message");
    else irc_send_privmsg(last_pm_nick, (const char *)overlay_slot);
    overlay_rx_release();
}
