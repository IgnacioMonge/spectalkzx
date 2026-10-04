;; overlay_entry3.asm — Entry table for SPCTLK3.OVL
;; Must be linked FIRST so the table sits at offset 0.

SECTION code_user

EXTERN _whatsnew_render
IFNDEF SPECTALK_SPECTRANEXT
EXTERN _bookmarks_apply_ovl
EXTERN _bookmarks_save_ovl
EXTERN _bookmarks_delete_store_ovl
ENDIF

IFDEF SPECTALK_SPECTRANEXT
    dw 1                      ; entry_count = 1
    dw _whatsnew_render       ; entry 0 → what's new
ELSE
    dw 4                      ; entry_count = 4
    dw _whatsnew_render       ; entry 0 → what's new
    dw _bookmarks_apply_ovl   ; entry 1
    dw _bookmarks_save_ovl    ; entry 2
    dw _bookmarks_delete_store_ovl ; entry 3
ENDIF
