#!/usr/bin/env python3
"""Lock the Classic IRC stream/lifecycle/backend boundary."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LEGACY_CALL = re.compile(r"\b(?:uart_send_string|uart_send_line|uart_send_crlf|ay_uart_send)\s*\(")
NET_CALL = re.compile(r"\bnet_send_(?:byte|string|line|crlf)\s*\(")
NET_AT_CALL = re.compile(r"net_send_(?:string|line)\s*\([^;]*(?:AT\+|\+\+\+)")
LEGACY_PUMP_CALL = re.compile(r"\buart_drain_to_buffer\s*\(")
LEGACY_DISCONNECT_CALL = re.compile(r"\bforce_disconnect\s*\(")
LEGACY_INIT_CALL = re.compile(r"\besp_init\s*\(")


def function_span(text: str, name: str) -> tuple[int, int]:
    match = re.search(rf"\b{name}\s*\([^;]*?\)\s*[^;{{]*\{{", text, re.S)
    if not match:
        raise AssertionError(f"missing function body: {name}")
    start = match.start()
    pos = match.end() - 1
    depth = 0
    while pos < len(text):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                return start, pos + 1
        pos += 1
    raise AssertionError(f"unterminated function body: {name}")


def assert_legacy_calls_owned(path: str, owners: tuple[str, ...]) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    spans = [function_span(text, owner) for owner in owners]
    for match in LEGACY_CALL.finditer(text):
        if not any(start <= match.start() < end for start, end in spans):
            line = text.count("\n", 0, match.start()) + 1
            raise AssertionError(f"{path}:{line}: legacy UART call outside Classic backend owner")


def function_text(path: str, name: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    start, end = function_span(text, name)
    return text[start:end]


def assert_in_order(text: str, items: tuple[str, ...], owner: str) -> None:
    pos = -1
    for item in items:
        next_pos = text.find(item, pos + 1)
        if next_pos < 0:
            raise AssertionError(f"{owner}: missing ordered operation: {item}")
        pos = next_pos


header = (ROOT / "include/spectalk_net.h").read_text(encoding="utf-8")
if not re.search(r"^#define\s+net_start_stream\(\)\s+NET_STREAM_OK$", header, re.M):
    raise AssertionError("missing zero-cost Spectranext stream start")

spectranext = (ROOT / "src/net_spectranext.c").read_text(encoding="utf-8")
if "uint8_t net_start_stream(" in spectranext:
    raise AssertionError("Spectranext stream start must not emit a runtime stub")

for alias, target in (
    ("net_send_byte", "ay_uart_send"),
    ("net_send_string", "uart_send_string"),
    ("net_send_crlf", "uart_send_crlf"),
    ("net_send_line", "uart_send_line"),
    ("net_connect", "classic_net_connect"),
    ("net_prepare", "classic_net_prepare"),
    ("net_start_stream", "classic_net_start_stream"),
    ("net_close", "classic_net_close"),
    ("net_init", "esp_init"),
    ("net_disconnect", "force_disconnect"),
    ("net_pump_rx", "uart_drain_to_buffer"),
    ("net_frame_wait", "frame_wait_drain"),
):
    if not re.search(rf"^#define\s+{alias}\s+{target}$", header, re.M):
        raise AssertionError(f"missing zero-cost Classic alias: {alias} -> {target}")

irc_handlers = (ROOT / "src/irc_handlers.c").read_text(encoding="utf-8")
if LEGACY_CALL.search(irc_handlers):
    raise AssertionError("src/irc_handlers.c bypasses the IRC TX seam")

assert_legacy_calls_owned(
    "src/user_cmds.c",
    ("sys_init",),
)
assert_legacy_calls_owned(
    "src/spectalk.c",
    (
        "uart_send_crlf",
        "uart_send_line",
        "esp_at_cmd",
        "esp_hard_cmd",
        "esp_init",
    ),
)

classic = (ROOT / "src/net_classic.c").read_text(encoding="utf-8")
for symbol in (
    "classic_net_connect",
    "classic_net_prepare",
    "classic_net_start_stream",
    "classic_net_close",
):
    function_text("src/net_classic.c", symbol)
if NET_CALL.search(classic):
    raise AssertionError("Classic ESP-AT backend routes control through IRC TX seam")

prepare_body = function_text("src/net_classic.c", "classic_net_prepare")
assert_in_order(
    prepare_body,
    ("S_AT_CIPMUX0", "S_AT_CIPSERVER0", "AT+CIPDINFO=0", "AT+CIPSSLSIZE=4096"),
    "classic_net_prepare",
)

classic_connect = function_text("src/net_classic.c", "classic_net_connect")
assert_in_order(
    classic_connect,
    (
        "wait_drain(20)",
        "flush_all_rx_buffers()",
        'AT+CIPSTART=\\"',
        'secure ? "SSL" : S_TCP',
        "host",
        "port",
        "secure ? TIMEOUT_SSL : TIMEOUT_DNS",
    ),
    "classic_net_connect",
)

stream_body = function_text("src/net_classic.c", "classic_net_start_stream")
assert_in_order(
    stream_body,
    (
        "wait_drain(20)",
        "rb_tail = rb_head",
        'AT+CIPMODE=1',
        "wait_for_response(S_OK, 100)",
        "wait_drain(20)",
        'AT+CIPSEND\\r\\n',
        "wait_for_prompt_char('>', TIMEOUT_PROMPT)",
    ),
    "classic_net_start_stream",
)

close_body = function_text("src/net_classic.c", "classic_net_close")
assert_in_order(
    close_body,
    (
        "connection_state >= STATE_TCP_CONNECTED",
        "i < 65",
        "ay_uart_send('+')",
        "i < 55",
        "S_AT_CIPCLOSE",
        "wait_for_response(S_OK, 50)",
        "S_AT_CIPMODE0",
        "wait_for_response(S_OK, 50)",
    ),
    "classic_net_close",
)

connect_body = function_text("src/user_cmds.c", "cmd_connect")
for required in ("net_prepare(", "net_connect(", "net_start_stream(", "net_disconnect("):
    if required not in connect_body:
        raise AssertionError(f"cmd_connect bypasses lifecycle seam: missing {required}")
if LEGACY_CALL.search(connect_body):
    raise AssertionError("cmd_connect contains Classic UART mechanism")
if connect_body.index("net_prepare(") > connect_body.index("clock_sync_fallback("):
    raise AssertionError("cmd_connect changed ESP prepare/NTP fallback order")
if connect_body.index("clock_sync_fallback(") > connect_body.index("net_connect("):
    raise AssertionError("cmd_connect changed NTP fallback/connect order")
assert_in_order(
    connect_body,
    ("net_connect(", "net_start_stream(", "connection_state = STATE_TCP_CONNECTED"),
    "cmd_connect",
)

force_body = function_text("src/spectalk.c", "force_disconnect")
if "net_close();" not in force_body or LEGACY_CALL.search(force_body):
    raise AssertionError("force_disconnect bypasses the backend close seam")

for path in ("src/irc_handlers.c", "src/user_cmds.c"):
    text = (ROOT / path).read_text(encoding="utf-8")
    if LEGACY_PUMP_CALL.search(text):
        raise AssertionError(f"{path} bypasses the RX pump seam")
    if LEGACY_DISCONNECT_CALL.search(text):
        raise AssertionError(f"{path} bypasses the disconnect seam")
    if LEGACY_INIT_CALL.search(text):
        raise AssertionError(f"{path} bypasses the init seam")

spectalk = (ROOT / "src/spectalk.c").read_text(encoding="utf-8")
for match in LEGACY_PUMP_CALL.finditer(spectalk):
    start, end = function_span(spectalk, "flush_all_rx_buffers")
    if not start <= match.start() < end:
        raise AssertionError("src/spectalk.c bypasses the RX pump seam")

for owner in ("sys_init",):
    if NET_CALL.search(function_text("src/user_cmds.c", owner)):
        raise AssertionError(f"Classic ESP-AT owner uses IRC TX seam: {owner}")

for owner in (
    "uart_send_crlf",
    "uart_send_line",
    "esp_at_cmd",
    "esp_hard_cmd",
    "esp_init",
):
    if NET_CALL.search(function_text("src/spectalk.c", owner)):
        raise AssertionError(f"Classic ESP-AT owner uses IRC TX seam: {owner}")

for path in ("src/irc_handlers.c", "src/user_cmds.c", "src/spectalk.c"):
    text = (ROOT / path).read_text(encoding="utf-8")
    match = NET_AT_CALL.search(text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise AssertionError(f"{path}:{line}: ESP-AT control routed through IRC TX seam")

asm = (ROOT / "asm/spectalk_asm/60_protocol_storage.asm").read_text(encoding="utf-8")
helper = asm.split("_irc_send_cmd_internal:", 1)[1].split("; ABOUT OVERLAY UART PUMP", 1)[0]
if re.search(r"\b(?:call|jp)\s+_(?:uart_send|ay_uart_send)", helper):
    raise AssertionError("IRC ASM helper bypasses the IRC TX seam")
for symbol in ("_net_send_string", "_net_send_byte", "_net_send_crlf"):
    if symbol not in helper:
        raise AssertionError(f"IRC ASM helper does not use {symbol}")

runtime_asm = (ROOT / "asm/spectalk_asm/80_ui_runtime.asm").read_text(encoding="utf-8")
for symbol in ("_net_sp_colon", "_net_privmsg"):
    if symbol not in runtime_asm:
        raise AssertionError(f"missing target-neutral fused TX helper: {symbol}")
if re.search(r"\b(?:PUBLIC|jp)\s+_uart_(?:sp_colon|privmsg|send_string)", runtime_asm):
    raise AssertionError("fused IRC TX helper bypasses the target-neutral ABI")

copt = (ROOT / "src/spectalk_copt.rul").read_text(encoding="utf-8")
for symbol in ("_net_sp_colon", "_net_privmsg"):
    if symbol not in copt:
        raise AssertionError(f"copt rule bypasses {symbol}")
if "_uart_sp_colon" in copt or "_uart_privmsg" in copt:
    raise AssertionError("legacy UART-named IRC copt target remains")

for path in (
    "asm/overlay_loader.asm",
    "asm/spectalk_asm/40_text_numeric_screen.asm",
):
    text = (ROOT / path).read_text(encoding="utf-8")
    if re.search(r"\b(?:call|jp)\s+_uart_drain_to_buffer", text):
        raise AssertionError(f"{path} bypasses the RX pump seam")
    if "_net_pump_rx" not in text:
        raise AssertionError(f"{path} does not use the RX pump seam")

main_build = (ROOT / "src/main_build.c").read_text(encoding="utf-8")
if '#include "net_classic.c"' not in main_build:
    raise AssertionError("Classic backend missing from SCU composition")

print("Network seam contract OK")
