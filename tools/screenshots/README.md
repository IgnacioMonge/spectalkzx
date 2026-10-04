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
