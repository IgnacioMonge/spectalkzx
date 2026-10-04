# SpecTalkZX Architecture

## Working tree

| Location | Purpose |
|---|---|
| `src/`, `include/`, `asm/`, `overlay/` | Maintained C/ASM source and interfaces |
| `tools/`, `Makefile` | Generators, build and deterministic checks |
| `release/`, `images/`, `packaging/` | Maintained release inputs and packaging |
| `README.md`, `READMEsp.md`, `CHANGELOG.md` | User documentation and release history |
| `docs/overlay_map.md`, `specs/` | Overlay contracts and port/design specifications |
| `.mex/ROUTER.md`, `.mex/patterns/README.md` | Current handoff and technical lessons by subject |
| `build/classic/`, `build/next/`, `build/spectranext/` | Last validated development artifacts and linker maps |

Start at `build/README.md` for local artifacts and `build/verification.md` for
their measurements. These folders are ignored by Git and are not releases.
Normal builds retain their existing working-output paths; `make clean` removes
those temporary outputs without removing the saved per-target folders.
Retain one validated set per target; archive obsolete local evidence outside
the checkout instead of accumulating per-session directories.

## Build Shape

- Resident C builds as one SCU: `src/main_build.c` includes `irc_handlers.c`, `user_cmds.c`, then `spectalk.c`.
- Keep that order: `spectalk.c` owns globals and must stay last.
- `static` symbols are still visible across included modules; check the whole SCU before renaming or deleting.
- `make` runs the BPE pass before compile and restores source copies after compile. If a build is interrupted, run `make restore_bpe`.
- Spectranext keeps the cold configuration apply helpers in `SPCTLK5` with its existing config loader; Classic/native Next keep those helpers resident. `src/config_apply.c` supplies the same code to each location.
- Normal builds use `MAX_ALLOCS_PER_NODE=200000`, the same SDCC allocation budget as `make release`; command-line overrides remain supported.
- `make next` builds only the native Spectrum Next target and emits `build/SPECTALK.NEX`; it does not build Classic.
- Overlays are separate links against generated resident addresses from `tools/gen_overlay_defs.py`; `overlay/overlay_api.h` is their ABI surface.

## Resident Vs Overlay

- Resident owns the main loop, UART/ring receive, IRC parser, command table, hot rendering, config state, and small wrappers for cold commands.
- On Classic, `overlay_exec(ovl_id, entry_id)` drains UART, loads one `SPCTLK*.OVL` payload from `SPECTALK.OVL` into `_ring_buffer`, validates the entry pointer, discards overwritten RX ring bytes, then jumps to the entry.
- On Spectranext, `overlay_exec()` reads the 64-byte atlas header plus a 256-byte bootstrap into `_ring_buffer`; the bootstrap reuses that open atlas handle, stages the selected payload through the 512-byte slice at `_ring_buffer+512` and copies it into one reusable 4K cartridge SRAM page at Page B (`$2000`). `_overlay_slot` remains intact for overlay arguments. The resident trampoline maps that page only while executing an entry.
- Spectranext opens DAT and OVL on the inherited source mount before `/CFG` selects local slot 0. The process owns both descriptors for its lifetime; logical opens bind and rewind, and logical closes detach. HTTPS downloads occur at those two startup opens. Local configuration/bookmark path operations retain the existing slot-0 policy.
- On native Spectrum Next, the NEX holds each overlay in its own 8K page. `overlay_exec()` maps pages 16..23 directly at MMU1 (`$2000`) with no SD read or ring-buffer copy; the final two bytes of each page hold the exact compiled payload length used to reject entry pointers into padding. `SPCTLK2` retains its 512-byte page-tail reservation (`$3DFE..$3FFD`); the colour globe no longer uses it for packets.
- `overlay_call(entry_id)` calls another entry in the already-loaded overlay. Classic executes it from `_ring_buffer`; Spectranext remaps the current Page B SRAM image; native Next remaps the last MMU1 page.
- `overlay_call_timed(entry_id)` is the ABOUT-only variant. Classic enables IM1 during the entry; both paged targets keep overlay execution under DI and `frame_wait()` briefly restores ROM for each interrupt. Native Next overlay and embedded-DAT trampolines always return with the mainline DI contract intact.
- Do not load another overlay from an overlay; it replaces the active execution image.

## STOA Overlay Atlas

- `SPECTALK.OVL` is a variable-length STOA atlas, not eight padded 2K pages.
- Header: magic `STOA`, version `1`, overlay count, header length, then `<offset,size>` pairs.
- Classic overlays link under 2048 bytes at `_ring_buffer`. Spectranext overlays link under 4096 bytes at `$2000`; its atlas has a fixed 256-byte bootstrap immediately after the 64-byte header. Native Next overlays link under 8190 bytes at `$2000`; the NEX packer expands the atlas into one page per overlay and reserves `$3FFE..$3FFF` for its payload length.
- Keep `SpecTalkZX.tap`, `SPECTALK.OVL`, and `SPECTALK.DAT` from the same build on SD card.
- Native Next uses only `SPECTALK.NEX`; its DAT bytes are embedded behind a two-byte generated length header in pages 24..27.
- Native Next Earth resources occupy pages 28..59 (banks 14..29). The original SKIP/COPY codec encodes all 48 RGB333 frames, including wrap; page 30 contains their (page,u16 offset) table. Page 28 holds initial frame 47 and the shared sprite palette. ABOUT reconstructs 6400 bytes in runtime-only page 75, alternating 8-bit sprite patterns 0..24 / 25..49. The 176x24 logo retains sprites 25..46, 4-bit patterns 100..121 and palette entries 80..95 in page-tail storage. MMU0/MMU2 and CPU speed are restored after DI uploads. Close clears sprite attributes and restores video controls. No resident BSS is added.

- The oval starfield is stored in globe-page tails 31..58 (seven scanlines per page, three in the last) and copied once per ABOUT open into Layer 2 banks 38..40, which are omitted from the NEX. The copy restores MMU0/MMU2 under DI. The static screen appears behind the sprites and above ULA; only (8,24)..(247,103) contains nontransparent pixels. Its second RGB333 palette occupies page 30 offset 6400. ABOUT saves/restores Layer 2 bank, mode, scroll, clip coordinates/index, access/visibility and global transparency. No resident allocation or per-frame background copy.

## Overlay Map

- `SPCTLK1`: help, banner, `/channels`, `/theme` message, `/login` candidate capture.
- `SPCTLK2`: ABOUT open/close and globe tick. Native Next uploads banked colour frames to hardware sprites. Classic/Spectranext Earth packets use private ABOUT storage, not `overlay_slot`; the reload-on-call targets may reuse dead entry-0 code.
- `SPCTLK3`: whats-new; on Classic/native Next it also owns bookmark apply/save/delete.
- `SPCTLK4`: status and config save; on Spectranext it also owns bookmark apply/save so the XFS replace-write helper is linked only once.
- `SPCTLK5`: config screen, RTC seed, `!tz rtc`, numeric `!tz`; Spectranext/native Next also own cold startup config loading; native Next owns one shared bus/ESP reset pulse used by bounded connection recovery.
- `SPCTLK6`: raw UDP NTP fallback, channel switcher render, `/notice`, `/away`.
- `SPCTLK7`: cold local commands: ignore, pass, local settings, autoaway, friend, `/id`, `/reply`.
- `SPCTLK8`: bookmark selector render/rows/list/cursor; Spectranext also owns bookmark delete here.

## Memory Map And Aliases

- `_ring_buffer = $F500..$FCFF` is 2048 bytes. Classic also uses it as the overlay execution area. Spectranext uses it only for the transient paging bootstrap and ROM-safe staging, then executes overlays from cartridge SRAM.
- Native Next leaves `_ring_buffer` available for RX and executes overlays at MMU1. Resident code starts at `$5DC0`, so MMU3 (`$6000`) is not a legal overlay slot.
- BSS must end before `$F500`; the Makefile fails if `__BSS_END_tail >= $F500` or the guard is too small.
- Classic and native Next clear compiler and ASM BSS before loading DAT, including the UART failure latch and overlay state. Spectranext retains its driver-state clear through `_spxn_rom_held`.
- `_overlay_slot = _rx_line`; it is a 512-byte scratch buffer and is mutually exclusive with active IRC line receive.
- Overlays that reuse `overlay_slot` must reset/discard RX state according to the caller contract; `!save` has the stricter post-SD-I/O drain gate.
- Cold overlay exits use `overlay_rx_release()`, which preserves resynchronization. It collapses the overwritten Classic/Spectranext ring; native Next keeps queued ring bytes. `reset_rx_state()` is reserved for explicit session/transport resets.
- NAMES friend accumulation owns a separate 47-byte buffer; it must survive notifications arriving between `353` and `366`. Notification builders consume plain text before UTF-8 conversion, so their shared strings must stay outside BPE `SAFE_CONSTANTS`.
- High fixed RAM: `_ignore_list = $FD00..$FD4F`; stack reserve starts above the fixed area.
- Printer buffer `$5B00..$5BFF`: invalidated input cache `$5B00..$5B7F`; Classic leaves `$5B80..$5BBF` free, while Spectranext binds XFS state at `$5B80..$5B93` and persistent theme/PM/render-cache bytes at `$5B94..$5BBE`; transient render/BPE/parser scratch stays at `$5BC0..$5BFF`. Classic persistent notification/NAMES/PLF state lives in compiler BSS and must not be moved back into Printer RAM.
- Spectranext aliases the XFS directory scratch to the disposable CHANS input workspace `$5CB6..$5DB5`, and fixes `user_mode[6]` at `$FD50..$FD55` between the ignore list and stack. The linker-map gate proves every target-only owner and the unchanged 2K ring/512B stack boundaries. A command handler must not read parser arguments in `temp_input` after starting an XFS directory transaction; `READDIR` may overwrite that half of the scratch. Current storage-writing handlers either ignore their arguments or consume them before I/O.
- CHANS workspace `$5CB6..$5DB5`: `line_buffer` and `temp_input`.

## Validation

- A software ring loss invalidates all pending ring bytes and the partial line, then discards through a subsequent LF. A queued LF before the loss cannot clear that discontinuity.
- UART drains reserve a ring slot before reading the data port. A full ring leaves the byte in the UART: the Classic ZX-Uno-style UART holds one byte and raises RTS to the ESP CTS input, so the ESP waits and TCP backpressures the server; native Next keeps the byte in its hardware FIFO until an overflow flag triggers the discard above. Classic TX polling does not read RX. Classic reception therefore depends on ESP CTS flow control (`AT+UART_CUR` fifth field 2 or 3). If the ESP init `AT` probe gets no `OK`, Classic sends `AT+UART_CUR=115200,8,1,0,2` (session only; flash `UART_DEF` is untouched) before reporting the failure, so the next attempt can pass.
- Native Next UART status reads share one error-aware helper. Framing/overflow/break/error-marker conditions discard pending data and drain the hardware FIFO to empty in bounded batches before resuming line synchronization.
- Classic overlay entry/return trampolines prevent RX producers from overwriting executing ring code, including cold output that scrolls with no modal UI. The guard costs one BSS byte and two stack bytes during an entry.
- Spectranext uses its ROM clock service; UART SNTP response parsing and fallback code are excluded from that resident.
- Native Next accumulates serviced FRAMES ticks in units of 1/64 frame. Its second threshold follows NextReg `$11`/`$03`/`$05` and core 3.x VGA/HDMI timing, including 60Hz and accelerated VGA modes. SNTP resets both accumulator bytes. FRAMES cannot recover interrupts masked for an entire frame.
- IRC text commands match their complete name case-insensitively before dispatch; a matching two-character prefix is insufficient.
- Classic/native Next config and bookmark saves close a sibling `.NEW` file before replacing the target through `.BAK`. A failed install rolls back or leaves `.BAK` recoverable; config stays dirty on failure. Alternate paths are attempted only when staging and opening the primary target both fail. This handles reported I/O errors, not power-loss atomicity. Firmware-facing Next paths must remain outside the mapped-out MMU1 overlay; the writer uses 32 bytes of stack scratch.
- Classic/native Next bookmark deletion commits an empty tombstone through the same writer before clearing active-bookmark state. Resident code then reloads `SPCTLK8` to redraw; an overlay never loads another overlay while executing.
- Resident UART TX reports success/failure in carry and latches failure. String sends stop on the first unsent byte; subsequent sends remain blocked, including raw UDP fallback. The session is disconnected and the UI requests an ESP reset and client restart; partially sent commands are never retried automatically.
- Spectranext latches socket failure in its existing descriptor state. TX remains blocked after the deferred `CLOSED` notification is queued; close still owns the descriptor, and a successful reconnect enables TX again.
- Connection and IRC registration waits count every frame, including short lines and PING/CAP/nickname-retry responses, toward their absolute timeout.
- Automatic password identification accepts only the configured `nickserv=` sender, or exact `NickServ` when unset, compared case-insensitively. Incoming notices never populate the trusted service name.
- `/login` captures an explicit service destination (31 bytes) and PRIVMSG payload (63 bytes). Only a direct, own-nick NOTICE with a recognized positive phrase from that service, or an own-nick numeric 900, promotes the pending candidate. Pending methods cannot auto-send or be saved; disconnect discards them. Confirmation saves from the resident main loop after IRC processing, never from the NOTICE handler or inside another overlay.
- `authcmd=` preserves a learned payload verbatim; `nickpass=` retains legacy IDENTIFY behavior. Bookmark records append `service|payload|mode` to the four original fields; old records load with empty authentication fields. Bookmark **A** only changes the persisted startup preference (`bookmark=`) and never alters the live server, channels or credentials; ENTER retains its disconnect confirmation. A loaded or explicitly stored bookmark associates subsequent confirmed methods with that slot. Manual server/port selection clears that association and changing the endpoint clears its auth method. Storage errors leave settings dirty for an explicit `!save` retry.
- Startup config parsing remains resident on Classic; on the paged targets SPCTLK5 runs the same parser before network activity, using the unused RX ring for file input. `cfg_apply()` remains resident.
- Overlay entries must follow a complete entry table and lie below the exact payload end. Native lengths are bounded to 8190 bytes; embedded DAT is bounded to 32766 bytes.
- The 222-byte BPE dictionary is loaded completely and validated before use. Its 74 triples contain two nonzero literals/earlier tokens plus NUL; unused generated entries are padded with literal pairs. Display expansion rejects tokens above `0xC9`.
- `puts_u8_nolz()` accepts 0..99; its current callers bound autoaway to 60 and absolute numeric timezone to 12. Ikkle drawing requires cleared destination glyph areas: spaces only update attributes and odd columns OR pixels into the existing byte.
- `str_to_u16()` preserves decimal-prefix parsing and saturates at 65535 on overflow. Config `theme`, `autoaway` and `timestamps` validate that 16-bit result before narrowing. Invalid themes/autoaway preserve the current setting; invalid timestamps select mode 1.
- `main_puts()` returns Z on completion (including a full column-64 row), NZ on cancellation/suppression. ASM string wrappers preserve this distinction and stop before further drawing; `main_print()` still clears wrap indentation on cancellation. After a newline, the slow renderer restores both its cached attribute and `g_ps64_attr`.
- Word-wrap entry points accept one decoded IRC/input line without internal LF/BPE tokens. A NUL exactly at the available width completes the line before considering a word break. `print_line64_fast()` rejects start-byte offsets >=32, resetting its optional caller state without screen writes.
- `redraw_input_full()` invalidates the input cache before the full ASM redraw. Cursor hiding draws the character without the cache and then updates the cached cell; preserve those existing caller contracts.

- Before edits: `git status --short --branch`.
- Required checks for native Next code changes: `git diff --check` and `make next NO_COLOR=1`. `next-check` runs the shared source/BPE/COPT/storage contracts used by this target; do not add a redundant Classic build when shared Classic behaviour was untouched.
- `check_memory_layout.py --platform next` owns resident/BSS/stack boundaries; `test_next_nex_image.py` separately owns native bank order, page payloads, entry bounds and embedded DAT layout.
- Report TAP bytes, BSS guard/free bytes, individual `SPCTLK*.OVL` sizes, and `SPECTALK.OVL` size. Keep only the current verified baseline in `.mex/ROUTER.md`; Git history owns superseded measurements.
- Docs-only changes are `HW N/A`. Any code, timing, memory, UART, SD I/O, or user-visible behavior change is at least `HW PENDING` until tested on hardware.
