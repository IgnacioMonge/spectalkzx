#!/usr/bin/env python3
"""
BPE (Byte Pair Encoding) string compressor for SpecTalkZX.

Scans C source files for screen-only string literals, compresses them
using BPE with tokens 0x80-0xFF, and generates:
  1. Modified .c files with compressed string contents
  2. BPE dictionary binary (for SPECTALK.DAT or ASM include)
  3. Statistics report

Screen-only strings: passed to main_puts, main_print, main_puts2,
  sys_puts_print, set_attr_err contexts.
Excluded: uart_send_string, uart_send_line, AT commands, IRC protocol.

Usage:
  python bpe_compress.py --analyze          # Report only, no changes
  python bpe_compress.py --compress         # Generate compressed files
  python bpe_compress.py --max-tokens 64    # Limit token count
"""

import re
import os
import sys
import argparse
import struct
from collections import Counter
from copy import deepcopy

# ============================================================================
# Configuration
# ============================================================================

SRC_DIR = os.path.join(os.path.dirname(__file__), '..')
SRC_FILES = [
    os.path.join(SRC_DIR, 'src', 'spectalk.c'),
    os.path.join(SRC_DIR, 'src', 'irc_handlers.c'),
    os.path.join(SRC_DIR, 'src', 'user_cmds.c'),
]

# Functions whose string arguments are screen-only (compressible)
SCREEN_FUNCS = {
    'main_puts', 'main_print', 'main_puts2', 'sys_puts_print',
    'ui_err', 'ui_sys', 'ui_usage', 'set_or_toggle_flag',
    'ui_info', 'ensure_args',
    'SYS_PUTS', 'SYS_MSG',        # macros that expand to main_puts/ui_sys
    'print_departure',              # calls main_puts internally

}

# Functions whose string arguments go to UART (must NOT compress)
UART_FUNCS = {
    'uart_send_string', 'uart_send_line', 'uart_send_cmd',
    'irc_send_pong', 'irc_send_cmd_internal',
    # File I/O — written to SD card as plain text
    'cfg_put', 'cfg_put_csv', 'cfg_kv',
    'esx_fopen', 'esx_fcreate',
    # Direct render — bypass main_puts, no BPE decoder
    'print_str64', 'print_line64_fast', 'print_big_str', 'draw_big_char',
}

# Named constants that are KNOWN to be UART-bound (exclude from compression)
# These are used in both screen and UART contexts
UART_CONSTANTS = {
    'S_CRLF', 'S_PRIVMSG', 'S_NOTICE', 'S_SP_COLON', 'S_PONG',
    'S_NICK_SP', 'S_NICK_CMD', 'S_AWAY_CMD', 'S_CAP_END',
    'S_IDENTIFY_CMD', 'S_ACTION', 'S_OK', 'S_AT_CIPSTART',
    'S_AT_CIPSEND', 'S_AT_CIPCLOSE', 'S_AT_RST', 'S_AT_CWJAP',
    'S_AT_CIFSR', 'S_AT_GMR', 'S_QUIT_CMD',
    # Config keys — written to .CFG file as plain text by cfg_kv/cfg_put
    'K_NICK', 'K_SERVER', 'K_PORT', 'K_PASS', 'K_NKPASS',
    'K_AUTOCONN', 'K_THEME', 'K_AUTOAWAY', 'K_BEEP', 'K_TRAFFIC', 'K_DIVIDER',
    'K_TS', 'K_TZ', 'K_TOPIC',
    # File paths — used by esx_fopen (must be plain ASCII for esxDOS)
    'K_CFG_PRI', 'K_CFG_ALT', 'K_DAT',
    # Shared constants used by BOTH main_puts AND direct render (print_big_str/print_str64)
    'S_APPDESC', 'S_APPNAME', 'S_COPYRIGHT', 'S_CANCELLED', 'S_PROMPT',
}

# BPE token range
TOKEN_START = 0x80
TOKEN_END = 0xFF
MAX_TOKENS = TOKEN_END - TOKEN_START + 1  # 128

# ============================================================================
# String extraction
# ============================================================================

def extract_string_literals(src_files):
    """Extract all string literals from C source files with context."""
    strings = []  # list of (file, line_no, string_value, context, is_screen_only)

    for fpath in src_files:
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        fname = os.path.basename(fpath)

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Skip preprocessor directives (#include, #define, etc.)
            if stripped.startswith('#'):
                continue

            # Skip comments
            if stripped.startswith('//'):
                continue

            # Skip _Static_assert and compile-time strings
            if '_Static_assert' in line or 'static_assert' in line:
                continue

            # Find all string literals in this line
            # Match "..." but handle escaped quotes
            for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', line):
                raw_str = m.group(1)
                # Decode C escape sequences
                try:
                    decoded = decode_c_string(raw_str)
                except:
                    continue

                # Skip very short strings (< 3 chars) and empty
                if len(decoded) < 3:
                    continue

                # Determine context: what function is this string passed to?
                col = m.start()
                context = get_call_context(line, col)

                # If context is 'if' or 'UNKNOWN', try harder: scan the full
                # line for a screen function call containing this string
                if context in ('if', 'UNKNOWN', 'while', 'for', 'return'):
                    better = find_enclosing_func_call(line, col)
                    if better:
                        context = better

                # Determine if screen-only
                is_screen = classify_string(line, col, context, raw_str, decoded)

                strings.append({
                    'file': fname,
                    'line': i + 1,
                    'raw': raw_str,
                    'decoded': decoded,
                    'context': context,
                    'screen_only': is_screen,
                    'full_line': line.rstrip(),
                })

    return strings


def decode_c_string(s):
    """Decode C string escape sequences."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            if c == 'n': result.append('\n')
            elif c == 'r': result.append('\r')
            elif c == 't': result.append('\t')
            elif c == '0': result.append('\0')
            elif c == '\\': result.append('\\')
            elif c == '"': result.append('"')
            elif c == 'x' and i + 3 < len(s):
                hex_str = s[i+2:i+4]
                try:
                    result.append(chr(int(hex_str, 16)))
                    i += 4
                    continue
                except ValueError:
                    result.append(s[i])
                    i += 1
                    continue
            else:
                result.append(s[i])
                result.append(c)
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def get_call_context(line, string_col):
    """Find the function name that this string is being passed to."""
    # Look backwards from the string position for a function call pattern
    prefix = line[:string_col].rstrip()

    # Match: func_name( or func_name(expr,
    m = re.search(r'(\w+)\s*\([^)]*$', prefix)
    if m:
        return m.group(1)

    # Check for assignment to named constant: const char S_XXX[] = "..."
    m = re.match(r'\s*(?:static\s+)?(?:const\s+)?char\s+(\w+)\s*\[\s*\]\s*=\s*', line)
    if m:
        return f'CONST:{m.group(1)}'

    return 'UNKNOWN'


def find_enclosing_func_call(line, string_col):
    """When the immediate context is 'if'/'UNKNOWN', search the full line
    for a known screen/uart function call that contains this string position."""
    all_funcs = SCREEN_FUNCS | UART_FUNCS
    for func in all_funcs:
        # Find all occurrences of func("..." on this line
        pattern = re.escape(func) + r'\s*\('
        for m in re.finditer(pattern, line):
            call_start = m.start()
            paren_start = m.end() - 1
            # Check if string_col is inside this function call
            if call_start < string_col:
                # Simple heuristic: string is within ~80 chars after the opening paren
                if string_col - paren_start < 80:
                    return func
    return None


def classify_string(line, col, context, raw_str, decoded):
    """Determine if a string is screen-only (compressible).

    Conservative approach:
    - Named constants with SB_ prefix: ALWAYS compressible (audited safe)
    - Named constants with S_/K_ prefix: NEVER (may be shared with UART/FILE/COMPARE)
    - Inline literals in SCREEN_FUNCS: compressible
    - Everything else: excluded
    """

    # Named constant definition: SB_ prefix = safe, anything else = exclude
    if context.startswith('CONST:'):
        const_name = context[6:]
        if const_name.startswith('SB_'):
            return True
        return False

    # Direct UART/FILE/COMPARE/RENDER function calls -> exclude
    if context in UART_FUNCS:
        return False

    # Direct screen function calls with inline literals -> include
    if context in SCREEN_FUNCS:
        return True

    # Default: exclude (conservative)
    # UNKNOWN context strings are never compressed — with SB_ convention,
    # all compressible named constants are explicitly marked.
    return False


# ============================================================================
# BPE Compression
# ============================================================================

def build_corpus(strings):
    """Build byte corpus from screen-only strings."""
    corpus = []
    for s in strings:
        if s['screen_only']:
            # Convert to bytes, skip chars >= 0x80 (shouldn't exist in ASCII)
            for ch in s['decoded']:
                b = ord(ch)
                if b < 0x80:
                    corpus.append(b)
            corpus.append(0)  # null separator (won't be compressed)
    return corpus


def count_pairs(data):
    """Count all adjacent byte pairs in data."""
    pairs = Counter()
    for i in range(len(data) - 1):
        a, b = data[i], data[i + 1]
        # Don't pair across null terminators
        if a == 0 or b == 0:
            continue
        # Don't pair tokens with null (would break expansion)
        pairs[(a, b)] += 1
    return pairs


def bpe_compress(corpus, max_tokens=128):
    """Run BPE compression on corpus. Returns (compressed_data, dictionary)."""
    data = list(corpus)
    dictionary = []  # list of (byte1, byte2) pairs
    token = TOKEN_START

    for iteration in range(max_tokens):
        pairs = count_pairs(data)
        if not pairs:
            break

        # Find most frequent pair
        best_pair, best_count = pairs.most_common(1)[0]

        # Net savings: (count - 1) bytes saved, minus 3 bytes dict entry (with null term)
        savings = best_count - 1 - 3
        if savings <= 0:
            break

        # Replace all occurrences
        new_data = []
        i = 0
        while i < len(data):
            if i < len(data) - 1 and data[i] == best_pair[0] and data[i + 1] == best_pair[1]:
                # Don't replace across null boundaries
                if data[i] != 0 and data[i + 1] != 0:
                    new_data.append(token)
                    i += 2
                    continue
            new_data.append(data[i])
            i += 1

        dictionary.append(best_pair)
        data = new_data
        token += 1

        if token > TOKEN_END:
            break

    return data, dictionary


def split_compressed_strings(compressed_data, original_strings):
    """Split compressed corpus back into individual strings (split on nulls)."""
    result = []
    current = []
    str_idx = 0

    for b in compressed_data:
        if b == 0:
            result.append(bytes(current))
            current = []
            str_idx += 1
        else:
            current.append(b)

    if current:
        result.append(bytes(current))

    return result


# ============================================================================
# Analysis & reporting
# ============================================================================

def analyze(src_files, max_tokens=128):
    """Full analysis: extract, classify, compress, report."""

    print("=" * 60)
    print("SpecTalkZX BPE String Compression Analysis")
    print("=" * 60)

    # Extract
    strings = extract_string_literals(src_files)
    screen_strings = [s for s in strings if s['screen_only']]
    non_screen = [s for s in strings if not s['screen_only']]

    print(f"\nTotal string literals found (>= 3 chars): {len(strings)}")
    print(f"  Screen-only (compressible):  {len(screen_strings)}")
    print(f"  UART/excluded:               {len(non_screen)}")

    # Build corpus
    corpus = build_corpus(strings)
    # Count only non-null bytes for content size
    content_bytes = sum(1 for b in corpus if b != 0)

    print(f"\nScreen-only corpus: {content_bytes} bytes of content")

    # Show top pairs before compression
    pairs = count_pairs(corpus)
    print(f"\nTop 20 byte pairs:")
    for (a, b), count in pairs.most_common(20):
        ca = chr(a) if 32 <= a < 127 else f'\\x{a:02x}'
        cb = chr(b) if 32 <= b < 127 else f'\\x{b:02x}'
        savings = count - 1 - 3
        print(f"  '{ca}{cb}' : {count:3d} occurrences (net {savings:+d} bytes)")

    # Compress
    compressed, dictionary = bpe_compress(corpus, max_tokens)
    compressed_content = sum(1 for b in compressed if b != 0)

    dict_size = len(dictionary) * 3  # 2 bytes + null terminator per entry
    decoder_size = 50  # estimated ASM decoder size

    content_saved = content_bytes - compressed_content
    net_savings = content_saved - dict_size - decoder_size

    print(f"\n{'=' * 60}")
    print(f"COMPRESSION RESULTS ({len(dictionary)} BPE tokens used)")
    print(f"{'=' * 60}")
    print(f"  Original content:      {content_bytes:5d} bytes")
    print(f"  Compressed content:    {compressed_content:5d} bytes")
    print(f"  Content reduction:     {content_saved:5d} bytes ({100*content_saved/content_bytes:.1f}%)")
    print(f"  Dictionary ({len(dictionary)}×3):     {dict_size:5d} bytes")
    print(f"  Decoder (ASM):          ~{decoder_size:4d} bytes")
    print(f"  ---")
    print(f"  NET ROM SAVINGS:       {net_savings:5d} bytes")
    print(f"  (dict goes to SPECTALK.DAT -> actual TAP savings = {content_saved - decoder_size} bytes)")

    # BSS impact
    bss_cost = dict_size + 18  # dict + bpe stack/pointer
    print(f"\n  BSS cost (dict+stack): {bss_cost:5d} bytes")
    print(f"  BSS freed (less CODE): ~{content_saved - decoder_size:4d} bytes (BSS moves down)")
    print(f"  Net BSS change:        ~{content_saved - decoder_size - bss_cost:+4d} bytes")

    # Show dictionary
    print(f"\nDictionary ({len(dictionary)} entries):")
    for i, (a, b) in enumerate(dictionary[:30]):
        token = TOKEN_START + i
        # Recursively expand for display
        expanded = expand_token(i, dictionary)
        ca = chr(a) if 32 <= a < 127 else f'[{a:02X}]'
        cb = chr(b) if 32 <= b < 127 else f'[{b:02X}]'
        print(f"  0x{token:02X}: {ca}{cb}  -> \"{expanded}\"")
    if len(dictionary) > 30:
        print(f"  ... ({len(dictionary) - 30} more entries)")

    # List screen-only strings (abbreviated)
    print(f"\nScreen-only strings ({len(screen_strings)}):")
    for s in screen_strings[:20]:
        d = s['decoded'][:50]
        # Sanitize for console output (replace non-ASCII)
        d = ''.join(c if ord(c) < 128 else '?' for c in d)
        print(f"  {s['file']}:{s['line']:4d}  {s['context']:20s}  \"{d}\"")
    if len(screen_strings) > 20:
        print(f"  ... ({len(screen_strings) - 20} more)")

    return strings, compressed, dictionary


def expand_token(token_idx, dictionary, depth=0):
    """Recursively expand a BPE token for display."""
    if depth > 10:
        return '?'
    a, b = dictionary[token_idx]
    result = ''
    for byte in (a, b):
        if byte >= TOKEN_START and (byte - TOKEN_START) < len(dictionary):
            result += expand_token(byte - TOKEN_START, dictionary, depth + 1)
        elif 32 <= byte < 127:
            result += chr(byte)
        else:
            result += f'[{byte:02X}]'
    return result


# ============================================================================
# Output generation
# ============================================================================

BPE_DICT_BSS_SIZE = 222  # Must match asm/spectalk_asm/30_rendering.asm bpe_dict defs

def generate_dict_binary(dictionary):
    """Generate dictionary as binary data (3 bytes per entry: b1, b2, 0x00).
    Pad unused entries with literal pairs to keep the fixed runtime layout."""
    data = bytearray()
    for token, (a, b) in enumerate(dictionary, TOKEN_START):
        if not 0 < a < token or not 0 < b < token:
            raise ValueError("BPE operands must be literals or earlier tokens")
        data.append(a)
        data.append(b)
        data.append(0)  # null terminator for stack-based expansion
    if len(data) > BPE_DICT_BSS_SIZE:
        raise ValueError(
            f"BPE dict is {len(data)} bytes, but BSS reserve is "
            f"{BPE_DICT_BSS_SIZE}; update bpe_dict defs and BPE_DICT_BSS_SIZE together"
        )
    data.extend(b"??\0" * ((BPE_DICT_BSS_SIZE - len(data)) // 3))
    return bytes(data)


def generate_dict_asm(dictionary):
    """Generate dictionary as ASM source."""
    lines = [
        '; BPE dictionary - auto-generated by bpe_compress.py',
        '; Each entry: 2 expansion bytes + null terminator',
        f'; {len(dictionary)} entries, {len(dictionary) * 3} bytes',
        '',
    ]
    for i, (a, b) in enumerate(dictionary):
        token = TOKEN_START + i
        expanded = expand_token(i, dictionary)
        ca = f"0x{a:02X}"
        cb = f"0x{b:02X}"
        lines.append(f'    defb {ca}, {cb}, 0x00  ; 0x{token:02X} = "{expanded}"')
    return '\n'.join(lines)


# ============================================================================
# Source file compression (generate modified .c files)
# ============================================================================

def compress_string_bytes(decoded, dictionary):
    """Compress a decoded string using the BPE dictionary.
    Returns bytes with BPE tokens (>= 0x80)."""
    # Convert string to byte list
    data = [ord(c) for c in decoded if ord(c) < 0x80]

    # Apply BPE replacements in dictionary order (same as training)
    for idx, (a, b) in enumerate(dictionary):
        token = TOKEN_START + idx
        new_data = []
        i = 0
        while i < len(data):
            if i < len(data) - 1 and data[i] == a and data[i + 1] == b:
                new_data.append(token)
                i += 2
            else:
                new_data.append(data[i])
                i += 1
        data = new_data

    return bytes(data)


def encode_bytes_as_c_string(raw_bytes):
    """Convert compressed bytes to a C string literal content (with escapes).
    CRITICAL: After a \\xNN hex escape, if the next char is a hex digit (0-9, a-f, A-F),
    we must insert a string break ("") to prevent the C compiler from reading \\xNNX
    as a 3-digit hex escape (which truncates and produces wrong values)."""
    HEX_CHARS = set('0123456789abcdefABCDEF')
    parts = []
    prev_was_hex_escape = False
    for b in raw_bytes:
        # If previous output was \xNN and this byte produces a hex char, break the string
        if prev_was_hex_escape and b < 0x80:
            c = chr(b) if 32 <= b < 127 else ''
            if c in HEX_CHARS:
                parts.append('" "')  # string concatenation break

        prev_was_hex_escape = False

        if b >= 0x80:
            parts.append(f'\\x{b:02x}')
            prev_was_hex_escape = True
        elif b == ord('\\'):
            parts.append('\\\\')
        elif b == ord('"'):
            parts.append('\\"')
        elif b == ord('\n'):
            parts.append('\\n')
        elif b == ord('\r'):
            parts.append('\\r')
        elif b == ord('\t'):
            parts.append('\\t')
        elif 32 <= b < 127:
            parts.append(chr(b))
        else:
            parts.append(f'\\x{b:02x}')
            prev_was_hex_escape = True
    return ''.join(parts)


def generate_compressed_sources(src_files, strings, dictionary, out_dir):
    """Generate modified .c files with BPE-compressed string literals."""
    # Build a map: (filename, line_no) -> list of (raw_original, compressed_raw)
    replacements = {}
    for s in strings:
        if not s['screen_only']:
            continue
        compressed_bytes = compress_string_bytes(s['decoded'], dictionary)
        compressed_raw = encode_bytes_as_c_string(compressed_bytes)
        if compressed_raw != s['raw']:  # only if actually compressed
            key = (s['file'], s['line'])
            if key not in replacements:
                replacements[key] = []
            replacements[key].append((s['raw'], compressed_raw))

    os.makedirs(out_dir, exist_ok=True)
    files_written = 0

    for fpath in src_files:
        fname = os.path.basename(fpath)
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        modified = False
        new_lines = []
        for i, line in enumerate(lines):
            line_no = i + 1
            key = (fname, line_no)
            if key in replacements:
                for orig_raw, comp_raw in replacements[key]:
                    old = f'"{orig_raw}"'
                    new = f'"{comp_raw}"'
                    if old in line:
                        line = line.replace(old, new, 1)
                        modified = True
            new_lines.append(line)

        out_path = os.path.join(out_dir, fname)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        files_written += 1

        if modified:
            # Count replacements for this file
            count = sum(1 for k in replacements if k[0] == fname)
            print(f"  {fname}: {count} strings compressed")
        else:
            print(f"  {fname}: no changes (copied as-is)")

    return files_written


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='BPE string compressor for SpecTalkZX')
    parser.add_argument('--analyze', action='store_true', help='Analysis only (no file changes)')
    parser.add_argument('--compress', action='store_true', help='Generate compressed files')
    parser.add_argument('--max-tokens', type=int, default=MAX_TOKENS,
                        help=f'Maximum BPE tokens (default: {MAX_TOKENS})')
    parser.add_argument('--dict-asm', action='store_true', help='Output dictionary as ASM')
    args = parser.parse_args()

    if not args.analyze and not args.compress:
        args.analyze = True

    strings, compressed, dictionary = analyze(SRC_FILES, args.max_tokens)

    if args.dict_asm:
        print("\n" + generate_dict_asm(dictionary))

    if args.compress:
        build_dir = os.path.join(SRC_DIR, 'build')
        os.makedirs(build_dir, exist_ok=True)

        # 1. Generate dictionary binary
        dict_bin = generate_dict_binary(dictionary)
        dict_path = os.path.join(build_dir, 'bpe_dict.bin')
        with open(dict_path, 'wb') as f:
            f.write(dict_bin)
        print(f"\nDictionary: {dict_path} ({len(dict_bin)} bytes)")

        # 2. Generate compressed .c source files in build/bpe_src/
        bpe_src_dir = os.path.join(build_dir, 'bpe_src')
        print(f"\nCompressed sources -> {bpe_src_dir}/")
        generate_compressed_sources(SRC_FILES, strings, dictionary, bpe_src_dir)

        # 3. Summary
        print(f"\nDone. To build with BPE:")
        print(f"  1. Copy build/bpe_src/*.c over src/*.c (or use Makefile integration)")
        print(f"  2. Append build/bpe_dict.bin to SPECTALK.DAT")
        print(f"  3. make")


if __name__ == '__main__':
    main()
