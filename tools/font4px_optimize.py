#!/usr/bin/env python3
"""
font4px_optimize.py — Find optimal 6→4 scanline transformation for SpecTalkZX font.
Searches all valid transformation combos and reports the best match vs Tom Thumb reference.
"""

import sys
from itertools import product

SPECTALK_DAT = "src/SPECTALK.DAT"

# =============================================================================
# Load our 64-col font
# =============================================================================
def load_our_font(path=SPECTALK_DAT):
    with open(path, 'rb') as f:
        data = f.read(298)
    packed = data[10:298]
    font = {}
    for ch in range(32, 128):
        idx = (ch - 32) * 3
        scanlines = []
        for b in packed[idx:idx+3]:
            scanlines.append((b >> 4) * 0x11)
            scanlines.append((b & 0x0F) * 0x11)
        # Convert to 4-bit tuples for fast comparison
        rows = []
        for sc in scanlines[:6]:
            rows.append(((sc>>7)&1, (sc>>6)&1, (sc>>5)&1, (sc>>4)&1))
        font[ch] = rows
    return font

# =============================================================================
# Tom Thumb reference (3×5, CC0) — encoded as 4-bit tuples
# =============================================================================
def _t(*rows):
    return [((r>>2)&1, (r>>1)&1, r&1, 0) for r in rows]

TOM5 = {
    32: _t(0,0,0,0,0),
    33: _t(2,2,2,0,2), 34: _t(5,5,0,0,0), 35: _t(5,7,5,7,5), 36: _t(3,6,2,3,6),
    37: _t(5,1,2,4,5), 38: _t(2,5,2,5,3), 39: _t(2,2,0,0,0), 40: _t(1,2,2,2,1),
    41: _t(4,2,2,2,4), 42: _t(5,2,5,0,0), 43: _t(0,2,7,2,0), 44: _t(0,0,0,2,4),
    45: _t(0,0,7,0,0), 46: _t(0,0,0,0,2), 47: _t(1,1,2,4,4),
    48: _t(2,5,5,5,2), 49: _t(2,6,2,2,7), 50: _t(6,1,2,4,7), 51: _t(6,1,2,1,6),
    52: _t(5,5,7,1,1), 53: _t(7,4,6,1,6), 54: _t(3,4,6,5,2), 55: _t(7,1,2,2,2),
    56: _t(2,5,2,5,2), 57: _t(2,5,3,1,6),
    58: _t(0,2,0,2,0), 59: _t(0,2,0,2,4), 60: _t(1,2,4,2,1), 61: _t(0,7,0,7,0),
    62: _t(4,2,1,2,4), 63: _t(6,1,2,0,2), 64: _t(2,5,7,4,3),
    # Uppercase
    65: _t(2,5,7,5,5), 66: _t(6,5,6,5,6), 67: _t(3,4,4,4,3), 68: _t(6,5,5,5,6),
    69: _t(7,4,6,4,7), 70: _t(7,4,6,4,4), 71: _t(3,4,5,5,3), 72: _t(5,5,7,5,5),
    73: _t(7,2,2,2,7), 74: _t(1,1,1,5,2), 75: _t(5,5,6,5,5), 76: _t(4,4,4,4,7),
    77: _t(5,7,5,5,5), 78: _t(5,7,7,5,5), 79: _t(2,5,5,5,2), 80: _t(6,5,6,4,4),
    81: _t(2,5,5,6,3), 82: _t(6,5,6,5,5), 83: _t(3,4,2,1,6), 84: _t(7,2,2,2,2),
    85: _t(5,5,5,5,2), 86: _t(5,5,5,2,2), 87: _t(5,5,5,7,5), 88: _t(5,5,2,5,5),
    89: _t(5,5,2,2,2), 90: _t(7,1,2,4,7),
    91: _t(3,2,2,2,3), 92: _t(4,4,2,1,1), 93: _t(6,2,2,2,6), 94: _t(2,5,0,0,0),
    95: _t(0,0,0,0,7), 96: _t(2,1,0,0,0),
    # Lowercase
    97: _t(0,3,5,5,3), 98: _t(4,6,5,5,6), 99: _t(0,3,4,4,3), 100: _t(1,3,5,5,3),
    101: _t(0,2,5,6,3), 102: _t(1,2,7,2,2), 103: _t(0,3,5,3,6), 104: _t(4,6,5,5,5),
    105: _t(2,0,2,2,2), 106: _t(2,0,2,2,4), 107: _t(4,5,6,5,5), 108: _t(6,2,2,2,7),
    109: _t(0,7,7,5,5), 110: _t(0,6,5,5,5), 111: _t(0,2,5,5,2), 112: _t(0,6,5,6,4),
    113: _t(0,3,5,3,1), 114: _t(0,3,4,4,4), 115: _t(0,3,2,6,0), 116: _t(2,7,2,2,1),
    117: _t(0,5,5,5,3), 118: _t(0,5,5,5,2), 119: _t(0,5,5,7,7), 120: _t(0,5,2,2,5),
    121: _t(0,5,5,3,6), 122: _t(0,7,2,4,7), 123: _t(1,2,4,2,1), 124: _t(2,2,2,2,2),
    125: _t(4,2,1,2,4), 126: _t(0,3,6,0,0),
}

# =============================================================================
# Build all transformation operators (precomputed for speed)
# =============================================================================
def build_ops(font):
    """For each char, precompute all possible output rows.
    Returns: ops_data[char] = list of 36 possible 4-bit tuples per op index."""
    ops_per_char = {}
    for ch, rows in font.items():
        char_ops = []
        # 6 SELECT ops
        for i in range(6):
            char_ops.append(rows[i])
        # 15 OR ops
        for i in range(6):
            for j in range(i+1, 6):
                char_ops.append(tuple(a|b for a,b in zip(rows[i], rows[j])))
        # 15 AND ops
        for i in range(6):
            for j in range(i+1, 6):
                char_ops.append(tuple(a&b for a,b in zip(rows[i], rows[j])))
        ops_per_char[ch] = char_ops
    return ops_per_char

def op_name(idx):
    if idx < 6:
        return f"S{idx}"
    idx -= 6
    if idx < 15:
        pairs = [(i,j) for i in range(6) for j in range(i+1,6)]
        i, j = pairs[idx]
        return f"{i}|{j}"
    idx -= 15
    pairs = [(i,j) for i in range(6) for j in range(i+1,6)]
    i, j = pairs[idx]
    return f"{i}&{j}"

# =============================================================================
# Search (optimized: precompute + vectorized distance)
# =============================================================================
def search(our_font, ref_rows=(0,1,2,3)):
    """Find best 4-op combo minimizing total Hamming distance to Tom Thumb reference."""
    chars = sorted(ch for ch in range(33, 127) if ch in TOM5 and ch in our_font)
    n_chars = len(chars)

    # Precompute ops for our font
    ops_data = build_ops(our_font)
    n_ops = 36  # 6 + 15 + 15

    # Precompute reference as flat tuples
    refs = []
    for ch in chars:
        g = TOM5[ch]
        refs.append(tuple(g[r] for r in ref_rows))

    # Precompute per-char per-op distance to each reference row
    # dist_table[char_idx][ref_row_idx][op_idx] = hamming distance
    dist_table = []
    for ci, ch in enumerate(chars):
        char_dists = []
        for ri in range(4):
            row_dists = []
            ref_row = refs[ci][ri]
            for oi in range(n_ops):
                d = sum(a != b for a, b in zip(ops_data[ch][oi], ref_row))
                row_dists.append(d)
            char_dists.append(row_dists)
        dist_table.append(char_dists)

    # Now search: for each combo (o0,o1,o2,o3), total_dist = sum over chars of
    # dist_table[ci][0][o0] + dist_table[ci][1][o1] + dist_table[ci][2][o2] + dist_table[ci][3][o3]
    #
    # Optimization: precompute column sums
    # col_sum[row][op] = sum over all chars of dist_table[ci][row][op]
    col_sum = [[0]*n_ops for _ in range(4)]
    for ri in range(4):
        for oi in range(n_ops):
            col_sum[ri][oi] = sum(dist_table[ci][ri][oi] for ci in range(n_chars))

    # With independent rows, the optimal combo is simply the best op per row!
    # total_dist(o0,o1,o2,o3) = col_sum[0][o0] + col_sum[1][o1] + col_sum[2][o2] + col_sum[3][o3]
    # Minimum = min(col_sum[0]) + min(col_sum[1]) + min(col_sum[2]) + min(col_sum[3])
    best_ops = []
    total = 0
    for ri in range(4):
        best_oi = min(range(n_ops), key=lambda oi: col_sum[ri][oi])
        best_ops.append(best_oi)
        total += col_sum[ri][best_oi]

    names = [op_name(oi) for oi in best_ops]
    return names, best_ops, total, chars, n_chars, ops_data, refs, dist_table

def main():
    print("=" * 60)
    print("SpecTalkZX 4px Font Optimizer")
    print("=" * 60)

    our_font = load_our_font()
    print(f"Loaded {len(our_font)} glyphs\n")

    # Show our font 'A' for verification
    print("Our 'A' (6 scanlines):")
    for i, r in enumerate(our_font[65]):
        print(f"  {i}: {''.join('#' if b else '.' for b in r)}")

    print("\nTom Thumb 'A' (5 rows):")
    for i, r in enumerate(TOM5[65]):
        print(f"  {i}: {''.join('#' if b else '.' for b in r)}")

    ref_selections = [
        ((0,1,2,3), "top 4 (drop descender)"),
        ((0,1,2,4), "skip row 3"),
        ((0,1,3,4), "skip row 2"),
        ((1,2,3,4), "drop cap row"),
    ]

    overall_best = None

    for ref_rows, desc in ref_selections:
        print(f"\n{'='*60}")
        print(f"Reference: Tom Thumb rows {ref_rows} — {desc}")

        names, best_ops, total, chars, n_chars, ops_data, refs, dist_table = \
            search(our_font, ref_rows)
        avg = total / n_chars

        print(f"  Best: [{', '.join(names)}]  dist={total} ({avg:.2f}/char)")

        # Count perfect matches
        perfect = 0
        worst_chars = []
        for ci, ch in enumerate(chars):
            d = sum(dist_table[ci][ri][best_ops[ri]] for ri in range(4))
            if d == 0:
                perfect += 1
            else:
                worst_chars.append((d, ch))
        worst_chars.sort(reverse=True)

        print(f"  Perfect: {perfect}/{n_chars}  Worst: ", end="")
        for d, ch in worst_chars[:5]:
            print(f"'{chr(ch)}'={d} ", end="")
        print()

        if overall_best is None or total < overall_best[0]:
            overall_best = (total, names, best_ops, chars, n_chars, ops_data, refs,
                          dist_table, ref_rows, desc)

    # === Overall winner details ===
    total, names, best_ops, chars, n_chars, ops_data, refs, dist_table, ref_rows, desc = overall_best
    avg = total / n_chars

    print(f"\n{'='*60}")
    print(f"WINNER: [{', '.join(names)}]")
    print(f"Reference: Tom Thumb rows {ref_rows} — {desc}")
    print(f"Distance: {total} ({avg:.2f}/char)")
    print(f"{'='*60}")

    # Show all characters comparison
    print(f"\nFull comparison (ref | ours | diff):")
    for ci, ch in enumerate(chars):
        d = sum(dist_table[ci][ri][best_ops[ri]] for ri in range(4))
        marker = "  " if d == 0 else f"!{d}"
        ref_str = ""
        our_str = ""
        for ri in range(4):
            ref_row = refs[ci][ri]
            our_row = ops_data[ch][best_ops[ri]]
            ref_str += "".join("#" if b else "." for b in ref_row) + " "
            our_str += "".join("#" if b else "." for b in our_row) + " "
        print(f"  '{chr(ch)}' {marker}  ref: {ref_str}  ours: {our_str}")

    # Output for Z80 implementation
    print(f"\n{'='*60}")
    print("Z80 IMPLEMENTATION:")
    print(f"{'='*60}")
    for i, (name, oi) in enumerate(zip(names, best_ops)):
        print(f"  Output scanline {i} = {name}")
        if oi < 6:
            print(f"    → glyph_buffer[{oi}] direct")
        elif oi < 21:
            pairs = [(a,b) for a in range(6) for b in range(a+1,6)]
            a, b = pairs[oi-6]
            print(f"    → glyph_buffer[{a}] OR glyph_buffer[{b}]")
        else:
            pairs = [(a,b) for a in range(6) for b in range(a+1,6)]
            a, b = pairs[oi-21]
            print(f"    → glyph_buffer[{a}] AND glyph_buffer[{b}]")

if __name__ == '__main__':
    main()
