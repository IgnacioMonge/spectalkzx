# SpecTalkZX

<p align="center">
  <img src="images/spectalkzx-banner.png" alt="SpecTalkZX" width="90%">
</p>

<p align="center"><strong>IRC client for ZX Spectrum, Spectrum Next and the Spectranext cartridge</strong></p>

<p align="center">🇪🇸 <a href="READMEsp.md">Leer en español</a></p>

<p align="center">
  <strong>Installation:</strong>
  <a href="#classic-zx--divmmc">Classic ZX / divMMC</a> ·
  <a href="#native-spectrum-next">Native Spectrum Next</a> ·
  <a href="#spectranext-cartridge">Spectranext cartridge</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-ZX%20Spectrum%20%7C%20Next%20%7C%20Spectranext-blue" alt="Platform: ZX Spectrum, Next and Spectranext">
  <img src="https://img.shields.io/badge/License-GPLv2-green" alt="License: GPLv2">
  <img src="https://img.shields.io/badge/Version-1.4.1-orange" alt="Version: 1.4.1">
</p>

Current release:
[SpecTalkZX 1.4.1 Triton](https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.4.1).

Version 1.4.1 runs straight from the web on the Spectranext cartridge, learns
IRC service logins, keeps up with heavy channel traffic and draws text faster.
Classic ZX, native Spectrum Next and Spectranext share the same interface,
commands and configuration format.

---

## Contents

- [Highlights in 1.4.1](#highlights-in-141)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Screenshots](#screenshots)
- [Interface](#interface)
- [Keyboard Controls](#keyboard-controls)
- [IRC Behaviour](#irc-behaviour)
- [Commands](#commands)
- [Configuration](#configuration)
- [Spectranext limits](#spectranext-limits)
- [Build](#build)
- [Troubleshooting](#troubleshooting)
- [License](#license)
- [Author](#author)

---

## Highlights in 1.4.1

- **Run from the web on Spectranext**: one URL starts the client, with no
  installation step.
- **Automatic service login**: `/login` learns a NickServ or QuakeNet Q login
  once the service confirms it, then sends it on every connection.
- **Steady under heavy traffic**: busy channels and long name lists no longer
  lose blocks of received text.
- **Faster text**: chat lines draw about 25% faster.
- **Colour globe on native Next**: a new animated About screen.
- **Clearer `!config`**: every setting appears under its configuration-file
  name.

See [CHANGELOG.md](CHANGELOG.md) for the complete user-visible change history
and compatibility notes.

---

## Requirements

| Target | Computer | Storage | Network |
|---|---|---|---|
| Classic | ZX Spectrum 48K, 128K, +2, +2A, +3 or compatible | divMMC/esxDOS SD storage | ZX-Uno-compatible UART, such as divTIESUS, with an ESP8266 running ESP-AT at 115200 baud |
| Native Next | ZX Spectrum Next with NextZXOS/esxDOS | SD card for the NEX and writable `/SYS/CONFIG` or `/SYS` | Configured internal ESP |
| Spectranext | ZX Spectrum model supported by the Spectranext cartridge | Local cartridge XFS for configuration and bookmarks | Cartridge Wi-Fi; firmware `0.9-6fc153a3` or later |

Classic uses <code>SpecTalkZX.tap</code>, <code>SPECTALK.OVL</code> and
<code>SPECTALK.DAT</code>. Keep all three files from the same release.
Native Next uses one self-contained <code>SPECTALK.NEX</code>. Spectranext runs
its matching files from the web or installs them in cartridge storage.

---

## Installation

### Classic ZX / divMMC

1. Download `spectalk_divmmc_v1.4.1.zip` from the
   [1.4.1 release](https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.4.1).
2. Copy <code>SpecTalkZX.tap</code>, <code>SPECTALK.OVL</code> and
   <code>SPECTALK.DAT</code> into the same directory on the SD card.
3. Configure the ESP-AT bridge for **115200 baud**. Wi-Fi credentials can be
   prepared with [NetManZX](https://github.com/IgnacioMonge/NetManZX) or an
   equivalent ESP-AT setup tool. If the ESP has CTS flow control disabled, the
   first startup attempt reports `FAIL`; press a key and the retry enables it
   for the session.
4. Load <code>SpecTalkZX.tap</code>, wait for the network indicator and connect
   to IRC.

### Native Spectrum Next

1. Download `spectalk_next_v1.4.1.zip` from the
   [1.4.1 release](https://github.com/IgnacioMonge/SpecTalkZX/releases/tag/v1.4.1).
2. Configure the Spectrum Next internal ESP for the desired Wi-Fi network.
3. Copy <code>SPECTALK.NEX</code> to the Next SD card.
4. Launch it from the NextZXOS browser. Configuration and bookmarks are written
   under <code>/SYS/CONFIG</code>, with <code>/SYS</code> as a fallback.

### Spectranext cartridge

Both options need cartridge firmware `0.9-6fc153a3` or later and a Wi-Fi
connection. Configuration and bookmarks always stay in local XFS under
<code>/CFG</code>.

**Run from the web.** Nothing is installed, and you always get the published
release.

1. In the Spectranext menu, select **Load Resource URL** and enter:
   <code>https://ignaciomonge.github.io/SpecTalkZX/</code>.
2. SpecTalkZX starts after a short loading screen; any key skips it.

**Install for use without the web.**

1. Select **Load Resource URL** and enter:
   <code>https://ignaciomonge.github.io/SpecTalkZX/install/</code>.
2. The guided installer validates the package, writes
   <code>SPECTALK.TAP</code>, <code>SPECTALK.OVL</code>,
   <code>SPECTALK.DAT</code> and <code>SPCTX.ZX</code> to local XFS, then
   launches the client.
3. Afterwards start <code>SPCTX.ZX</code> from local XFS. To update, run the
   installer again; <code>/CFG/SPECTALK.CFG</code> and the five bookmark files
   are preserved.

---

## Quick Start

```text
/nick YourNick
/server irc.libera.chat 6667
/join #spectrum
```

Useful first setup:

```text
!theme 1
!timestamps smart
!notif on
!nickcolor on
!save
```

To save a complete session, open `!bm`. In bookmarks: **UP/DOWN** selects a slot, **S** stores the current server/channel snapshot, **A** marks it for startup, **ENTER** connects, **D** deletes, and **BREAK** saves/exits. **A** cycles autoconnect, autoconnect with autojoin, and off for the next startup; it also works while connected without changing the current session.

---

## Screenshots

The gallery combines captures from native Spectrum Next, Spectranext and
Classic. Configuration, About and What's New show 1.4.1 Triton on a fictional
demo network.

### Getting started and navigation

<table>
  <tr>
    <td align="center" valign="top" width="50%">
      <strong>Run from the web</strong><br>
      <a href="images/snapshot-run-from-web.png"><img src="images/snapshot-run-from-web.png" width="420" alt="SpecTalkZX loading screen when run from the web on Spectranext"></a><br>
      <sub>Spectranext loads SpecTalkZX straight from its web address; any key skips this screen.</sub>
    </td>
    <td align="center" valign="top" width="50%">
      <strong>Choose your nick</strong><br>
      <a href="images/snapshot-nick.png"><img src="images/snapshot-nick.png" width="420" alt="Choosing an IRC nick"></a><br>
      <sub>First-run nick selection before opening a server connection.</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="50%">
      <strong>Connected server</strong><br>
      <a href="images/snapshot-connected.png"><img src="images/snapshot-connected.png" width="420" alt="Connected to Libera Chat"></a><br>
      <sub>The server window after Spectranext connects to IRC.</sub>
    </td>
    <td align="center" valign="top" width="50%">
      <strong>Window navigation</strong><br>
      <a href="images/snapshot-options.png"><img src="images/snapshot-options.png" width="420" alt="Server and channel windows"></a><br>
      <sub>The tab bar keeps the server and active channel contexts one key away.</sub>
    </td>
  </tr>
</table>

### Conversation and discovery

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>Joining a channel</strong><br>
      <a href="images/snapshot-joining.png"><img src="images/snapshot-joining.png" width="280" alt="Joining an IRC channel"></a><br>
      <sub>Join progress and channel context remain visible during registration.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Live conversation</strong><br>
      <a href="images/snapshot-chat.png"><img src="images/snapshot-chat.png" width="280" alt="IRC conversation on native Spectrum Next"></a><br>
      <sub>Native Spectrum Next chat with timestamps, nick colours, modes and unread state.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Fast private reply</strong><br>
      <a href="images/snapshot-fast-reply.png"><img src="images/snapshot-fast-reply.png" width="280" alt="Fast reply to a private message"></a><br>
      <sub>Press ENTER on a private-message notification to open the conversation.</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>Friends online</strong><br>
      <a href="images/snapshot-friends-online.png"><img src="images/snapshot-friends-online.png" width="280" alt="Friend detection"></a><br>
      <sub>Friends found during NAMES are collected into one compact notification.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Channel users</strong><br>
      <a href="images/snapshot-users.png"><img src="images/snapshot-users.png" width="280" alt="Channel user list"></a><br>
      <sub>The paginated four-column /names view keeps long nick lists readable.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Channel search</strong><br>
      <a href="images/snapshot-channel-search.png"><img src="images/snapshot-channel-search.png" width="280" alt="Channel search results"></a><br>
      <sub>Search and paging present large channel lists without colliding with input.</sub>
    </td>
  </tr>
</table>

### Management and information

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>Bookmarks</strong><br>
      <a href="images/snapshot-bookmarks.png"><img src="images/snapshot-bookmarks.png" width="280" alt="IRC bookmark manager"></a><br>
      <sub>Five independent slots store server, port, channels and startup policy.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Configuration</strong><br>
      <a href="images/snapshot-config.png"><img src="images/snapshot-config.png" width="280" alt="Configuration overview with configuration-file names"></a><br>
      <sub>Every active setting appears under the name it has in the configuration file.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Connection status</strong><br>
      <a href="images/snapshot-status.png"><img src="images/snapshot-status.png" width="280" alt="Connection status"></a><br>
      <sub>Network state, latency, uptime and open windows are summarized together.</sub>
    </td>
  </tr>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>Command help</strong><br>
      <a href="images/snapshot-help.png"><img src="images/snapshot-help.png" width="280" alt="Built-in command help"></a><br>
      <sub>Built-in help covers local and IRC commands without leaving the client.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>About</strong><br>
      <a href="images/snapshot-about.png"><img src="images/snapshot-about.png" width="280" alt="Animated colour globe About screen on native Spectrum Next"></a><br>
      <sub>Native Spectrum Next spins a colour globe over a starfield during a live connection.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>What's New</strong><br>
      <a href="images/snapshot-changes.png"><img src="images/snapshot-changes.png" width="280" alt="SpecTalkZX 1.4.1 Triton What's New screen"></a><br>
      <sub>The 1.4.1 Triton screen lists the release highlights.</sub>
    </td>
  </tr>
</table>

### Themes

<table>
  <tr>
    <td align="center" valign="top" width="33%">
      <strong>Theme 1</strong><br>
      <a href="images/snapshot-theme-1-away.png"><img src="images/snapshot-theme-1-away.png" width="280" alt="Theme 1 with away state"></a><br>
      <sub>Default palette showing away state, notifications and coloured nicks.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Theme 2</strong><br>
      <a href="images/snapshot-theme-2.png"><img src="images/snapshot-theme-2.png" width="280" alt="Theme 2"></a><br>
      <sub>Green terminal-style palette with the same full IRC interface.</sub>
    </td>
    <td align="center" valign="top" width="33%">
      <strong>Theme 3</strong><br>
      <a href="images/snapshot-theme-3.png"><img src="images/snapshot-theme-3.png" width="280" alt="Theme 3"></a><br>
      <sub>High-contrast blue/red palette.</sub>
    </td>
  </tr>
</table>

---

## Interface

- **64-column chat display** with a custom 4-pixel font.
- **Up to 10 windows**: server window `0` plus channel or private-chat windows `1` to `9`.
- **Direct window switching** with `!0` through `!9` or `/0` through `/9`.
- **EDIT selector** with unread/mention markers and direct numeric selection.
- **Three themes** with distinct status indicators and colour behaviour.
- **Per-nick colours** with `!nickcolor`.
- **Smart notifications** using the Ikkle-4 mini-font at the bottom row.
- **PM quick reply**: ENTER on a PM notification opens a private chat with the sender.
- **Optional timestamps**: off, on, or smart.
- **Channel context dividers** with `!divider`.
- **Status bar** with nick, current window, network/modes, user count, clock, away marker, and three-state connection indicator.


## Keyboard Controls

| Key | Action |
|-----|--------|
| **ENTER** | Send message, run command, or accept an action |
| **EDIT** | Open or close the channel selector |
| **DELETE** | Delete character behind cursor |
| **LEFT/RIGHT** | Move cursor or selection |
| **UP/DOWN** | Command history or row selection |
| **Symbol Shift + LEFT/RIGHT** | Word-by-word cursor movement |
| **Symbol Shift + DELETE** | Delete previous word |
| **BREAK** | Dismiss notification, cancel paging, or leave a secondary screen |
| **ENTER on PM notification** | Open a private chat with the sender |

---


## IRC Behaviour

- Supports the usual IRC workflow: `JOIN`, `PART`, `QUIT`, `NICK`, `PRIVMSG`, `NOTICE`, `TOPIC`, `MODE`, `KICK`, `WHO`, `WHOIS`, `LIST`, and `NAMES`.
- Supports CTCP `VERSION`, `PING`, `TIME`, and `ACTION`.
- NickServ can be used manually with `/id` or automatically with `nickpass=`.
- `nickserv=` can override the service nick when a network does not use standard `NickServ` naming.
- Auto-identify accepts requests only from that configured nick, or `NickServ` by default; other service names require an explicit `nickserv=` setting.
- Friends are monitored through `!friend`; JOIN/NAMES results generate compact notifications.
- Ignores are managed with `/ignore`, including `-nick` removal.
- Away state supports manual `/away` and idle `!autoaway`.
- Connection checks detect silent disconnects and remain active during About.
- Long sessions keep channel user counts more stable through NAMES handling and optional `!countsync`.

### Service login

`/login service command [arguments]` sends `PRIVMSG <service> :<command>
[arguments]` and, once the service confirms it, remembers it as your login for
later connections:

```text
/login NickServ IDENTIFY account secret
/login Q@CServe.quakenet.org AUTH account secret
```

- **Confirmation.** The login is learned only from a direct NOTICE sent by that
  service to your current nick with a recognized positive answer, or from
  numeric `900` for this nick. `already identified`, errors, notices from other
  senders and notices for another nick do not count. An unrecognized answer
  leaves the login pending, and `!save` and bookmark `S:STORE` reject it.
- **Saving.** A confirmed login is saved automatically: into the bookmark it
  was loaded from, or into the current configuration after a manual `/server`
  connection, where `S:STORE` can link it to a bookmark. A failed write is
  reported and left for a manual `!save`.
- **Next connection.** The saved login is sent once, after the MOTD.
- **Retrying.** While a login is pending, another `/login` does not replace it.
  If an attempt fails or is not recognized, disconnect before trying again. A
  pending login is discarded on disconnect; the last confirmed one stays on
  disk and returns when you reload its bookmark or restart.
- **Limits.** One service destination of up to 31 characters and a command of
  up to 63; channels, several destinations and `|` are rejected. The command is
  replayed verbatim and stored as plaintext in configuration and bookmark
  files, so only reusable credentials work. SASL, CertFP, IRC `PASS` and
  changing OTP/TOTP codes are not supported.
- `/id` and `nickpass=` remain available as the classic IDENTIFY path.

---
## Commands

### Local Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `!help` | `!h` | Show command help |
| `!status` | `!s` | Show connection, latency, uptime, and window status |
| `!init` | `!i` | Restart the network connection |
| `!config` | `!cfg` | Show all current settings |
| `!theme N` | | Switch theme `1`, `2`, or `3` |
| `!about` | | Animated About screen |
| `!changelog` | | What's New screen |
| `!bookmarks` | `!bm` | Open the IRC bookmark manager |
| `!save` | `!sv` | Save config and current session |
| `!autoconnect` | `!ac` | Toggle startup server connection |
| `!autojoin` | | Toggle replay of saved channels after registration |
| `!tz` | | Show/set timezone `-12`..`+12`; `rtc` uses a supported local RTC |
| `!timestamps` | `!ts` | Cycle off/on/smart timestamp modes |
| `!notif` | `!nf` | Toggle notifications |
| `!beep` | | Toggle mention sound |
| `!click` | | Toggle key click |
| `!traffic` | | Toggle JOIN/PART/QUIT presence noise |
| `!divider` | | Toggle channel context separators |
| `!countsync` | `!cs` | Toggle idle user-count resync |
| `!autoaway` | `!aa` | Auto-away after N minutes, `0` disables |
| `!friend` | | List or toggle tracked friends |
| `!nickcolor` | `!nc` | Toggle per-nick colours |
| `!clear` | `!cls` | Clear chat area |

Toggle commands with no argument alternate their state; they accept `on`/`off`/`1`/`0`.
`!timestamps` also accepts `smart`.

### IRC Commands

| Command | Alias | Description |
|---------|-------|-------------|
| `/server [host [port]\|host:port]` | `/connect` | No args: show state or reconnect saved server; otherwise connect to the given host |
| `/nick [name]` | | View or set nick |
| `/pass [password\|clear\|none]` | | View/set stored password; `clear`/`none` remove it for the next connection |
| `/id [password]` | | Identify with NickServ or configured service nick |
| `/login service command [arguments]` | | Send a service login command and wait for confirmation |
| `/join channel\|#channel\|&channel` | `/j` | Join a bare, `#`- or `&`-prefixed channel |
| `/part [#channel\|&channel] [message]` | `/p` | Leave the current or named `#`/`&` channel |
| `/msg nick text` | `/m` | Send private message |
| `/reply text` | | Reply to the last PM sender |
| `/notice target text` | | Send IRC NOTICE |
| `/query nick` | `/q` | Open a private query window |
| `/close` | | Close current query or part current channel |
| `/quit [message]` | | Disconnect, with confirmation guard |
| `/me action` | | Send CTCP ACTION |
| `/away [message]` | | Set or clear away |
| `/raw command` | | Send raw IRC command |
| `/whois nick` | `/wi` | Show WHOIS information |
| `/who [channel\|nick]` | | Search users; defaults to the current channel |
| `/list pattern` | `/ls` | List channels |
| `/names [#channel\|&channel]` | | Paginated grid of users in the current or named channel |
| `/topic [#channel] [text]` | | View/set topic; target and text are optional |
| `/mode [args]` | | View/set channel or target modes |
| `/search #pattern\|nick` | | Search LIST channels with `#pattern` or WHO users with `nick` |
| `/ignore [nick]` | | List, add, or remove ignored nicks (`-nick`) |
| `/kick nick [reason]` | `/k` | Kick from current channel |
| `/channels` | `/w` | List open windows |
| `/0`..`/9` | | Switch to a numbered window |

`/pass` only updates the stored password used when opening the next connection; it
does not send an immediate IRC `PASS` command. The numeric `!0`..`!9` and
`/0`..`/9` forms select numbered windows directly.

See [Service login](#service-login) for how `/login` learns and replays a
login.

---

## Configuration

SpecTalkZX writes the current configuration with `!save`. Classic and native
Next load `SPECTALK.CFG` from `/SYS/CONFIG/`, with `/SYS/` as a fallback.
Spectranext loads `/CFG/SPECTALK.CFG` from local cartridge XFS.

```ini
nick=MyNick
server=irc.libera.chat
port=6667
pass=
nickpass=myNickServPassword
nickserv=NickServ
autoconnect=1
autojoin=1
channels=#spectrum,#zx
theme=1
timestamps=2
autoaway=15
beep=1
click=1
traffic=1
divider=1
countsync=1
tz=1
notif=1
nickcolor=1
friends=Friend1,Friend2
ignores=NoisyNick
```


Supported settings:

| Setting | Values | Notes |
|---------|--------|-------|
| `nick` | IRC nick | Default nick |
| `server` | Hostname/IP | IRC server |
| `port` | Decimal port | Default IRC port is `6667` |
| `pass` | Text or empty | Server password |
| `nickpass` | Text or empty | NickServ password for `/id` / auto-identify |
| `authcmd` | Text | Confirmed `/login` command, written by SpecTalkZX as plaintext; do not add it by hand |
| `nickserv` | Nick or empty | Service nick override, for non-standard networks |
| `autoconnect` | `0`/`1` | Connect to saved server at startup |
| `autojoin` | `0`/`1` | Join saved `channels` after IRC registration |
| `bookmark` | `0`, `1`–`5`, `128`–`133` | Startup choice saved by **A**; overrides the current profile at boot |
| `channels` | Comma-separated channels | Session restore channel list |
| `theme` | `1`, `2`, `3` | Colour theme |
| `timestamps` | `0`, `1`, `2` | Off, on, smart |
| `beep` | `0`/`1` | Mention sound |
| `click` | `0`/`1` | Key click sound |
| `traffic` | `0`/`1` | JOIN/PART/QUIT traffic display |
| `divider` | `0`/`1` | Channel context separators |
| `countsync` | `0`/`1` | Idle user-count resync |
| `notif` | `0`/`1` | Bottom-row notifications |
| `nickcolor` | `0`/`1` | Per-nick colours |
| `autoaway` | `0`-`60` | Idle minutes, `0` disables |
| `tz` | `-12`..`+12` or `rtc` | Numeric SNTP offset or a local RTC where supported |
| `tzlast` | `-12`..`+12` | Last numeric timezone used when leaving RTC mode |
| `friends` | Comma-separated nicks | Up to five tracked friends |
| `ignores` | Comma-separated nicks | Up to five ignored nicks |

Notable settings:

- `bookmark=1`–`5` selects a stored server for startup; `129`–`133` also enables autojoin. `128` disables both; absent or `0` uses the ordinary configuration. **A** saves this choice with **BREAK**. A missing selected bookmark prevents automatic connection. Explicit `!autoconnect` or `!autojoin` commands return to the current profile.

- `autoconnect=1` connects to the saved server on startup.
- `autojoin=1` replays the saved `channels=` list after IRC registration and after any required NickServ grace period.
- On Classic and native Next, `tz=rtc` uses a detected local RTC. Spectranext
  has no Z80-visible RTC: it uses UDP/SNTP and falls back from `rtc` to
  `tzlast`.
- `divider=0` hides future channel context separators.
- `countsync=0` disables idle count refresh after long sessions.
- `friends=` and `ignores=` hold up to five nicks each.

Bookmark files use `/SYS/CONFIG/SPTBM1.CFG` through `SPTBM5.CFG` on Classic
and native Next, falling back to `/SYS/SPTBM1.CFG` through `SPTBM5.CFG` when
`/SYS/CONFIG` is absent. Spectranext uses `/CFG/SPTBM1.CFG` through
`SPTBM5.CFG`.

---

## Spectranext limits

- IRC uses plaintext on the configured server port. The cartridge exposes TLS
  only on its fixed port-443 service, so IRC TLS on port 6697 is unavailable.
- The cartridge exposes no RTC to Z80 software. Spectranext uses UDP/SNTP;
  `tz=rtc` falls back to the last numeric timezone stored in `tzlast`.
- SpecTalkZX uses one cartridge network connection at a time. Clock
  synchronization runs before the IRC connection opens.
- Configuration and bookmarks are saved in XFS. A power loss during a write can
  leave the file incomplete.
- When run from the web, SpecTalkZX downloads <code>SPECTALK.TAP</code>,
  <code>SPECTALK.OVL</code> and <code>SPECTALK.DAT</code> once at startup and
  keeps them open for the whole session.

---

## Build

Requirements: z88dk with SDCC support, GNU Make, Python 3.8 or newer, and a
POSIX-compatible shell toolset. On Windows, w64devkit provides the required
Make and shell utilities.

```sh
# Classic ZX
make NO_COLOR=1

# Native Spectrum Next
make next NO_COLOR=1

# Spectranext, and its run-from-the-web resource in build/spectranext-direct/
make spectranext NO_COLOR=1 SPXN_DIR=/path/to/Spectranext/driver
make spectranext-direct NO_COLOR=1 SPXN_DIR=/path/to/Spectranext/driver

# Release builds
make release NO_COLOR=1
make release NO_COLOR=1 PLATFORM=next
make release NO_COLOR=1 PLATFORM=spectranext SPXN_DIR=/path/to/Spectranext/driver
```

Build outputs:

- `build/SpecTalkZX.tap`
- `build/SPECTALK.OVL`
- `build/SPECTALK.DAT`
- `build/SPECTALK.NEX` from `make next` (self-contained native Next image)
- `build/spectranext-direct/` from `make spectranext-direct` (`boot.zx`, TAP,
  OVL, DAT and listing, ready to host over HTTPS)

The Spectranext target also needs the driver directory from the Spectranext SDK.

---

## Troubleshooting

| Problem | Check |
|---|---|
| Classic indicator stays red | ESP-AT bridge wiring, power and 115200 baud |
| Classic startup shows `FAIL` once | Press a key: the retry enables ESP CTS flow control for the session |
| Spectranext cartridge is not detected | Cartridge present and local XFS `/CFG` available |
| Indicator is ready but IRC will not connect | Wi-Fi credentials, hostname and plaintext IRC port |
| Startup stops on esxDOS/DAT | Classic divMMC mounted; all three files together and from one build |
| Help/About/bookmarks fail | `SPECTALK.OVL` or `SPECTALK.DAT` is missing or stale |
| Spectranext does not start from the web | Firmware `0.9-6fc153a3` or later, Wi-Fi connected, and **Load Resource URL** `https://ignaciomonge.github.io/SpecTalkZX/` |
| Spectranext must start without the web | Install from `https://ignaciomonge.github.io/SpecTalkZX/install/`, then start `SPCTX.ZX` |
| Clock remains at `00:00` | SNTP access and numeric timezone; Classic and native Next may also use `!tz rtc` |
| NickServ identify fails | Use `/id`, `nickpass=` or the `nickserv=` override |
| Too much JOIN/PART noise | Toggle `!traffic` |
| Channel counts drift | Keep `!countsync` enabled or run `/names` |
| Accented text looks odd | UTF-8 is converted to the ZX display character set |
| `/reply` has no target | Receive a PM first so its sender can be remembered |

---

## License

SpecTalkZX is free software released under the **GNU General Public License
v2.0**.

Includes code derived from:

- **BitchZX** IRC client.
- UART driver work by **Nihirash**.
- **Ikkle-4** mini font by Jack Oatley.

---

## Author

**M. Ignacio Monge Garcia** — 2025–2026

*Connecting the ZX Spectrum to IRC since 2025.*
