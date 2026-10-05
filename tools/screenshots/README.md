# README screenshots

These scripts regenerate the gallery images in `images/` from a real build,
running in ZEsarUX with the ZXESPEmu ESP modem. The client connects to a
fictional network, `irc.example.net` (ExampleNet), served on localhost, so no
public IRC server or account appears in the captures.

Requirements: Python 3, a ZXESPEmu checkout with ZEsarUX installed, and the
`ZXESPEMU` environment variable pointing at it.

```sh
export ZXESPEMU=/path/to/ZXESPEmu
python tools/screenshots/irc_fake.py &          # ExampleNet on 127.0.0.1:6667

# Classic: configuration and What's New (BUILD = a release build/ directory)
python tools/screenshots/shots.py classic BUILD \
  wait:75 'keys:!config' ascii:13 wait:5 shot:config.scr ascii:32 wait:3 \
  'keys:!changelog' ascii:13 wait:5 shot:changes.scr ascii:32
python tools/screenshots/scr2png.py build/screenshots/out/config.scr images/snapshot-config.png
python tools/screenshots/scr2png.py build/screenshots/out/changes.scr images/snapshot-changes.png

# Native Next: About with Layer 2 and sprites, captured as BMP
python tools/screenshots/shots.py next BUILD \
  wait:60 'keys:!about' ascii:13 wait:8 shot:about.bmp ascii:32
python tools/screenshots/bmp2png.py build/screenshots/out/about.bmp images/snapshot-about.png

# Spectranext run-from-the-web loading screen
python tools/screenshots/scr2png.py packaging/spectranext/loading.scr images/snapshot-run-from-web.png
```

`scr2png.py` and `bmp2png.py` produce the gallery format: the 256x192 screen
scaled 2.5x with box filtering, centred on a 682x520 black canvas.
`python tools/screenshots/test_scr2png.py` checks that geometry.

## UART burst measurements

`tools/motd_probe.py --port 6667 --lines 150` replaces `irc_fake.py` for
MOTD/NAMES burst checks (run only one server on the port). It records 30 MOTD
and 12 NAMES PING marks, missing replies and corrupted PONG tokens in
`motd_probe2_results.txt`. A valid run requires `JOIN sent`, denominators 30/12
and `CORRUPT 0`; a session that never registers is not a passing measurement.

For the emulator, select 3.5 MHz before autoconnection:

```sh
python tools/screenshots/shots.py next BUILD \
  'zrcp:tbblue-set-register 7 0' 'zrcp:tbblue-get-register 7' wait:90
```

The installed ZXESPEmu ZEsarUX 13.0 UART bridge does **not** emulate a finite
Next RX FIFO, serial arrival timing or overflow flags: it reads TCP directly, so
emulator runs never lose data and only validate application integration. Burst
integrity needs real hardware. To compare builds without hardware, measure the
per-line cost of the linked image with `tools/next_rx_throughput.py build/next`.
