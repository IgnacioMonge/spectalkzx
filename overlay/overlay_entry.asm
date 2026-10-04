;; overlay_entry.asm — Entry table for SPCTLK1.OVL (Help + Banner)
SECTION code_user
EXTERN _help_render_ovl
EXTERN _banner_render_ovl
EXTERN _windows_render_ovl
EXTERN _theme_msg_ovl
EXTERN _login_cmd_ovl
    dw 5                      ; entry_count = 5
    dw _help_render_ovl       ; entry 0 → help
    dw _banner_render_ovl     ; entry 1 → banner
    dw _windows_render_ovl    ; entry 2 -> /channels
    dw _theme_msg_ovl         ; entry 3 → /theme message
    dw _login_cmd_ovl         ; entry 4 -> learn login
