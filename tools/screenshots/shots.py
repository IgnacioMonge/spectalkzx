"""Drive a SpecTalkZX build in ZEsarUX through ZRCP and save screens.

usage: shots.py classic|next BUILD_DIR STEP... [--window]

BUILD_DIR holds SpecTalkZX.tap, SPECTALK.OVL and SPECTALK.DAT (classic) or
SPECTALK.NEX (next). Steps run in order:
  wait:SECONDS   keys:TEXT   ascii:CODE   shot:NAME.scr|NAME.bmp   zrcp:COMMAND
Screens are written to build/screenshots/out/. ZEsarUX and the ESP modem come
from the ZXESPEmu checkout named by the ZXESPEMU environment variable.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ZXESPEMU = os.environ.get("ZXESPEMU")
if not ZXESPEMU:
    raise SystemExit("set ZXESPEMU to the ZXESPEmu checkout")
sys.path.insert(0, ZXESPEMU)
import run as zr  # noqa: E402

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[1] / "build" / "screenshots"
OUT = WORK / "out"
# Fictional profile: irc.example.net is mapped to localhost by modem_wrap.py.
CFG = """nick=spectalk
server=irc.example.net
port=6667
autoconnect=1
autojoin=1
channels=#spectrum
theme=1
timestamps=2
autoaway=15
beep=0
click=0
traffic=1
divider=1
countsync=1
tz=1
notif=1
nickcolor=1
friends=zxfan,retrogal
"""


def stage(target, build):
    sd = WORK / f"sd_{target}"
    shutil.rmtree(sd, ignore_errors=True)
    (sd / "SYS" / "CONFIG").mkdir(parents=True)
    (sd / "SYS" / "CONFIG" / "SPECTALK.CFG").write_text(CFG.replace("\n", "\r\n"))
    if target == "classic":
        for name in ("SpecTalkZX.tap", "SPECTALK.OVL", "SPECTALK.DAT"):
            shutil.copy2(build / name, sd / name)
        return sd, sd / "SpecTalkZX.tap"
    shutil.copy2(build / "SPECTALK.NEX", sd / "SPECTALK.NEX")
    return sd, sd / "SPECTALK.NEX"


def launch(target, build, headless):
    sd, artifact = stage(target, build)
    uart = WORK / f"uart_{target}"
    if uart.exists():
        uart.unlink()
    modem = subprocess.Popen(
        [
            sys.executable,
            str(HERE / "modem_wrap.py"),
            "--link",
            str(uart),
            "--bind",
            "127.0.0.1",
            "--reported-ip",
            "192.168.1.64",
            "--wifi-mode",
            "simulated",
        ],
        stdout=open(WORK / f"modem_{target}.log", "wb"),
        stderr=subprocess.STDOUT,
    )
    zr.wait_for_uart(modem, uart)
    model = "zxuno" if target == "classic" else "next"
    cmd, _ = zr.artifact_emulator_command(artifact, model, uart, headless, sd, True)
    port = zr.free_tcp_port()
    cmd[-1:-1] = [
        "--enable-remoteprotocol",
        "--remoteprotocol-port",
        str(port),
        "--remoteprotocol-prompt",
        "ZXESP",
    ]
    zr.apply_uart_endpoint(cmd, uart)
    emu = subprocess.Popen(
        cmd,
        cwd=zr.RESOURCES,
        stdout=open(WORK / f"zesarux_{target}.log", "wb"),
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 15
    while True:
        try:
            conn = socket.create_connection(("127.0.0.1", port), timeout=5)
            zr.read_zrcp_prompt(conn)
            return modem, emu, conn
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


def main():
    target, build = sys.argv[1], Path(sys.argv[2]).resolve()
    headless = "--window" not in sys.argv
    steps = [a for a in sys.argv[3:] if a != "--window"]
    OUT.mkdir(parents=True, exist_ok=True)
    modem, emu, conn = launch(target, build, headless)
    try:
        for step in steps:
            kind, _, arg = step.partition(":")
            if kind == "wait":
                time.sleep(float(arg))
            elif kind == "keys":
                # 200 ms per key: faster typing loses keys while chat arrives.
                zr.zrcp_send(conn, f"send-keys-string 200 {arg}")
            elif kind == "ascii":
                zr.zrcp_send(conn, f"send-keys-ascii 200 {arg}")
            elif kind == "shot":
                zr.zrcp_send(conn, f"save-screen {OUT / arg}")
                print(OUT / arg)
            elif kind == "zrcp":
                print(zr.zrcp_send(conn, arg).decode("latin-1"))
            else:
                raise SystemExit(f"unknown step {step}")
    finally:
        conn.close()
        zr.stop(emu)
        zr.stop(modem)


if __name__ == "__main__":
    main()
