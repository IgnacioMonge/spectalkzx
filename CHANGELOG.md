# SpecTalkZX changelog

Only user-visible changes and compatibility notes are listed here.

## [1.4.1] - Triton - Unreleased

### Added

- Spectranext runs SpecTalkZX straight from the web. Choose **Load Resource
  URL** and enter `https://ignaciomonge.github.io/SpecTalkZX/`: the client
  starts without being installed, after a short loading screen that any key
  skips. Configuration and bookmarks still live in local cartridge storage.
  The guided installer, for starting without a network, is now at
  `https://ignaciomonge.github.io/SpecTalkZX/install/`.
- `/login service command [arguments]` learns an IRC service login, such as
  NickServ or QuakeNet Q, once the service confirms it. The login is saved
  with the bookmark or current configuration and sent automatically on the
  next connection. Only reusable credentials are supported.
- Native Next About shows a new animated colour globe and wordmark over a
  starfield.

### Changed

- What's New presents the 1.4.1 Triton highlights with a new Triton portrait.
- `!config` labels every setting with its configuration-file name, such as
  `nickpass`, `nickcolor`, `autoaway` and `tz`, and adds `nickserv` and the
  startup `bookmark`. The server appears as `host:port` on its own row, and
  values are aligned in two columns. A learned `/login` appears as `authcmd`,
  or `pending` until the service confirms it; passwords still show only
  whether they are set.
- Text draws faster: about 25% for chat lines and about 15% for single
  characters such as nicks and timestamps.

### Fixed

- Heavy IRC traffic no longer drops blocks of up to 2 KB of received text
  when the receive buffer fills. On Classic the ESP holds the data until there
  is room; native Next keeps it in its hardware buffer for longer.
- Classic now works with an ESP whose CTS flow control is disabled, for
  example after a factory reset. Previously every ESP initialization attempt
  failed; now a failed attempt enables CTS for the current session, so the
  next retry or `!init` succeeds. The ESP's saved settings are never changed.
- Bookmark **A:AUTO** works while connected again. It saves the next startup
  choice without replacing the live server, channels or login credentials.
- `/msg` to a nick whose query window is open in the background no longer
  leaves the sent text, including service passwords, drawn in the input line.
- `!config` no longer labels the autojoin setting as `autologin`.
- An empty `nickpass=` or `authcmd=` line in the configuration file no longer
  erases the other service login.
- A failed configuration or bookmark save or delete keeps the previous file
  instead of leaving a damaged one.
- The native Next clock follows the active video frame rate, so it keeps
  correct time in 60 Hz and other video modes.
- Spectranext `!init` retries the clock synchronization as soon as the
  cartridge reports an IP address, keeping the active timezone.
- Quit, mode, channel and disconnect notifications no longer show garbled
  text. Friends found in a channel's name list are no longer missed while
  another notification is on screen.

### Release verification

- Classic: TAP **36,471 bytes**; BSS ends at **0xF483**, leaving **125 bytes**
  before the receive ring; overlays **2045 / 1902 / 2007 / 2047 / 2008 / 1983 /
  2039 / 1980 bytes**; packed `SPECTALK.OVL` **16,075 bytes**.
- Native Next: `SPECTALK.NEX` **410,112 bytes**; resident **36,238 bytes**; BSS
  ends at **0xF3F3**, leaving **269 bytes**; overlays **2028 / 2429 / 2015 /
  2047 / 2713 / 1996 / 2039 / 1957 bytes**; embedded data **16,829 bytes**.
- Spectranext: TAP **35,405 bytes**; BSS ends at **0xF035**, leaving **1,227
  bytes**; overlays **2042 / 1919 / 831 / 2523 / 3244 / 2114 / 2039 / 1994
  bytes**; packed `SPECTALK.OVL` **17,026 bytes**.
- Spectranext web resource: `SPECTALK.TAP` **42,361 bytes** with its loading
  screen, `SPECTALK.OVL` **17,026 bytes**, `SPECTALK.DAT` **16,829 bytes**.
  Installer: `SPCTX.INS` **3,313 bytes**, `SPCTX.PKG` **45,048 bytes**,
  `SPCTX.SCR` **6,912 bytes**.

### Compatibility

- `SPECTALK.DAT` uses a new font layout. Install the TAP or NEX, `SPECTALK.OVL`
  and `SPECTALK.DAT` files from the same release.
- Existing configuration and bookmark files need no migration. The new
  optional keys `authcmd` and `bookmark` are written by `/login` and the
  bookmark manager.
- Classic needs a ZX-Uno-compatible UART, such as divTIESUS, whose RTS line
  reaches the ESP CTS input. SpecTalkZX enables ESP CTS flow control for the
  session when it is missing.
- Spectranext requires cartridge firmware `0.9-6fc153a3` or later. A 1.4.0
  installation keeps working; reinstall from `/install/` to update it.

## [1.4.0] - Proteus - 2026-09-04

### Added

- Native ZX Spectrum Next support as a self-contained `SPECTALK.NEX` file.
- Use of the Spectrum Next internal ESP and real-time clock.
- Target-specific About screens for Classic ZX, native Spectrum Next and the
  Spectranext cartridge.

### Changed

- Spectranext now keeps secondary screens and commands separate from incoming
  IRC data through cartridge memory paging.
- Native Next embeds help, themes, What's New and About data in the NEX file;
  no separate OVL or DAT files are needed.
- Native Next startup and `!init` can recover from an inherited or unresponsive
  ESP state. BREAK cancels initialization.
- Classic ZX and native Next try `/SYS` for bookmark files when
  `/SYS/CONFIG` is unavailable.
- The Spectranext installer artwork and package have been updated for 1.4.0.

### Release verification

- Classic: TAP **35,386 bytes**; BSS ends at **0xEFDD**, leaving **1,315
  bytes** before the receive ring; overlays **1705 / 1902 / 1573 / 1745 / 1934
  / 1798 / 1816 / 1973 bytes**; packed `SPECTALK.OVL` **14,510 bytes**.
- Native Next: `SPECTALK.NEX` **147,968 bytes**; resident **35,466 bytes**; BSS
  ends at **0xF086**, leaving **1,146 bytes**; overlays **1688 / 1882 / 1581 /
  1745 / 1965 / 1787 / 1816 / 1994 bytes**; embedded data **16,633 bytes**.
- Spectranext: TAP **36,512 bytes**; BSS ends at **0xF420**, leaving **224
  bytes**; overlays **1705 / 1922 / 746 / 2532 / 1490 / 1937 / 1816 / 1906
  bytes**; packed `SPECTALK.OVL` **14,374 bytes**.
- Spectranext resource: `SPCTX.INS` **3,296 bytes**, `SPCTX.PKG` **43,785
  bytes**, `SPCTX.SCR` **6,912 bytes**.

### Compatibility

- Classic ZX remains compatible with the 1.3.9 configuration format and
  command set. It still requires matching `SpecTalkZX.tap`, `SPECTALK.OVL` and
  `SPECTALK.DAT` files from one build.
- Native Next requires NextZXOS and a configured internal ESP.
- Existing Classic and Spectranext configuration and bookmark files need no
  migration.
- Spectranext requires cartridge firmware `0.9-6fc153a3` or later.

## [1.3.9.1] - Spectranext installation fix - 2026-08-30

The client remains SpecTalkZX 1.3.9 Juno. This maintenance release changes only
the Spectranext installer and storage handling.

### Fixed

- Installed program files now remain available after a power cycle.
- Later configuration changes now remain available after a power cycle instead
  of reverting to an earlier saved copy.
- Installation now starts through **Load Resource URL** in the Spectranext menu.

The installer labels this package `1.3.9-2`, the three-component form accepted
by the cartridge package format. Classic ZX is unchanged.

## [1.3.9] - Juno - 2026-08-28

### Added

- Native support for ZX Spectrum models equipped with the Spectranext
  cartridge.
- Guided Spectranext installation from
  `https://ignaciomonge.github.io/SpecTalkZX/`.
- Cartridge storage for configuration and five bookmark slots under `/CFG`.
- UDP/SNTP clock synchronization for Spectranext.
- Target-specific startup and About identification.

### Improved

- UART and UDP operations no longer wait indefinitely when hardware stops
  responding.
- Partial UDP sends stop safely instead of continuing with an incomplete
  packet.
- Configuration keys must match their complete names; unknown or truncated
  names are ignored.
- Long friend and ignore lists fit the configuration screen.
- File access no longer leaves stale keyboard input or damages visible
  interface state.
- About rejects incomplete animation data and remains responsive to IRC
  connection traffic.
- IRC registration errors and status messages display more reliably.

### Compatibility

- The Classic release uses `SpecTalkZX.tap`, `SPECTALK.OVL` and
  `SPECTALK.DAT`; all three files must come from the same release.
- Spectranext IRC is plaintext. IRC TLS on port 6697 is not supported by this
  target.
- Spectranext has no Z80-visible RTC. Selecting `tz=rtc` uses the last numeric
  timezone with SNTP.
- A power loss during a configuration or bookmark write can leave the file
  incomplete.

## [1.3.8] - Hermes - 2026-06-25

### Added

- Five-slot IRC bookmark manager with store, connect, delete and automatic
  startup controls.
- Session saving for server, port, joined channels and startup policy.
- `/mode`, `/reply`, `/notice` and direct `/0` through `/9` window switching.
- Paginated four-column `/names` view.
- Optional long-session channel count refresh with `!countsync`.
- Optional channel context separators with `!divider`.
- Local RTC clock mode with `!tz rtc` where supported.
- Animated, theme-aware About screen.

### Improved

- Bookmark slots keep their channel lists isolated.
- Autojoin waits for IRC registration and NickServ identification.
- `/names`, `/list` and `/search` handle long results and paging more clearly.
- NickServ identification accepts non-standard service names.
- Help paging, command prompts, IRC formatting and accented text handling are
  more reliable.
- About continues processing keepalive traffic while open.
- Notifications, cursor movement, status information and key repeat are more
  consistent.

### Compatibility

- esxDOS/divMMC storage is required.
- `SpecTalkZX.tap`, `SPECTALK.OVL` and `SPECTALK.DAT` must be copied together.

## [1.3.7] - Artemis II - 2026-04-06

### Added

- On-demand Help, About, Config, Status and What's New screens.
- Compact notifications for private messages, mentions and friends.
- Per-nick colours, word navigation, key repeat and an animated globe.
- Expanded connection and channel status information.

### Compatibility

- esxDOS/divMMC became mandatory.
- Releases from this version onward require the TAP, OVL and DAT files from the
  same archive.

Earlier releases are available on the
[GitHub Releases page](https://github.com/IgnacioMonge/SpecTalkZX/releases).

[1.4.1]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.4.1
[1.4.0]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.4.0
[1.3.9.1]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.3.9.1
[1.3.9]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.3.9
[1.3.8]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.3.8
[1.3.7]: https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.3.7
