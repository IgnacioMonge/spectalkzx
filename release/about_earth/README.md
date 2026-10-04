# About Earth assets

Generated graphics used by the animated `!about` screen. The binary and
assembly files form one matching set and are packed into `SPECTALK.DAT` during
the normal build. Do not edit generated data by hand.

## Files

- `earth_frame0.compact.bin`: first bitmap frame.
- `earth_attr0.compact4.bin`: first packed colour frame.
- `earth_frame_deltas.bin`: bitmap changes for later frames.
- `earth_attr_deltas.compact4.bin`: colour changes for later frames.
- `earth_logo.bin`: one-bit SpecTalkZX logo.
- `earth_overlay_spans.asm`: screen and colour ranges used by the renderer.
- `earth_logo.asm`: logo screen and colour addresses.

## Native Next colour globe

`earth_next_48.zip` is the user-provided source sequence: 48 RGBA PNGs, 80x80,
75 shared RGB333 colours and binary transparency. `tools/next_earth.py` packs
them without recolouring using the original SKIP/COPY delta encoder and ASM
decoder. Each reconstructed frame contains 25 16x16 8-bit patterns (6400 bytes).
Page 28 contains frame 47 as the initial buffer image and the shared 512-byte
palette after its pixels. Page 30 starts with 48 three-byte (page,u16 offset)
delta pointers, including the 47-to-0 wrap. Records never cross offset 6400,
leaving the static-resource tails intact. Current resources occupy pages
28..59 (16 NEX banks); the 48 delta streams total 133169 bytes.

ABOUT copies the initial image into page 75, then each tick applies one delta
there before uploading the alternate sprite pattern set. MMU0/MMU2, CPU speed,
IX/IY and the DI contract are preserved. The 8 KiB buffer is runtime-only;
no resident BSS is added. The normal NEX generator validates all source assets.

`logo_next.png` is the supplied wordmark with its baked checkerboard removed
using imagegen. The packer crops transparent margins, scales to 176x24 and
quantizes to at most 15 RGB333 colours (palette entries 81..95; 80 transparent).
Its 176x32 padded canvas uses 22 4-bit sprites, indices 25..46 and patterns
100..121. The 2816 pattern bytes occupy existing padding: 1280 bytes at page
28 offset 6912 and 1536 at page 29 offset 6400. No additional NEX banks.

`starfield_oval_v1.png` is the generated oval universe background. The packer
composites its alpha over black and reduces it to 240x80 RGB333 pixels at
screen (8,24). Layer 2 uses banks 38..40 (256x192, 48 KiB), transparent black
and its second palette, stored at page 30 offset 6400. The static background
is stored in the existing tails of pages 31..58 (seven 256-byte rows per page,
three in the last), rather than including banks 38..40 in the NEX. Opening
ABOUT reconstructs all 48 KiB through MMU0/MMU2 under DI at 28 MHz, then restores
both slots; no clearing pass or decompressor is needed. The background
adds no per-frame upload. ABOUT restores Layer 2 bank, mode, offsets, clip
window/index, visibility, palette selection and global transparency on close.

`tools/test_next_earth.py` reconstructs every visible source pixel and checks
invalid inputs. `tools/test_next_earth_cpu.py PORT` runs the actual Z80N kernel
in a disposable ZEsarUX TBBlue instance with ZRCP enabled; it replaces that
instance's memory and verifies all frames, double buffering, palette, ABI,
bank/speed restoration, wrap, close and reopen. Hardware timing remains pending.
