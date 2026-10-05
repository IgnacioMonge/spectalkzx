"""Registration-burst probe with splice detection.

Each session: 001-005, a MOTD of --lines lines with PING :M<nnn>-<cc> every
5 lines, then after the client's JOIN a 353 NAMES burst with PING :J<nnn>-<cc>.
<cc> is a check byte, so a PONG whose token was cut or mixed with another line
is reported as CORRUPT (a spliced line) instead of being silently accepted.
"""

import argparse
import re
import socket
import time

SRV = "irc.example.net"
TOKEN = re.compile(r"^([MJ])(\d{3})-([0-9a-f]{2})$")


def check(kind, idx):
    return f"{(idx * 37 + (11 if kind == 'M' else 29)) & 0xFF:02x}"


def token(kind, idx):
    return f"{kind}{idx:03d}-{check(kind, idx)}"


def session(conn, peer, n_lines, log):
    conn.settimeout(0.5)
    sent, pongs, corrupt, nick, buf = set(), set(), [], None, b""
    last_sent = time.time()
    t0 = time.time()

    def send(text):
        conn.sendall(text.encode() + b"\r\n")

    def burst(kind, count, line_of):
        nonlocal last_sent
        k = 0
        for i in range(count):
            send(line_of(i))
            if i % 5 == 4:
                tok = token(kind, k)
                sent.add(tok)
                send(f"PING :{tok}")
                k += 1
        last_sent = time.time()

    joined = False
    while time.time() - t0 < 120:
        try:
            data = conn.recv(4096)
            if not data:
                break
        except socket.timeout:
            data = b""
        buf += data
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("latin-1").strip()
            word = line.split(" ", 1)[0].upper()
            if word == "NICK":
                nick = line.split(" ", 1)[1].lstrip(":").split()[0]
            elif word == "USER" and nick:
                for num, txt in (
                    ("001", f"Welcome {nick}"),
                    ("002", f"Host {SRV}"),
                    ("003", "Created now"),
                    ("004", f"{SRV} probe io ov"),
                ):
                    send(f":{SRV} {num} {nick} :{txt}")
                send(f":{SRV} 005 {nick} NETWORK=ProbeNet PREFIX=(ov)@+ :are supported")
                send(f":{SRV} 375 {nick} :- {SRV} Message of the Day -")
                burst(
                    "M",
                    n_lines,
                    lambda i: (
                        f":{SRV} 372 {nick} :- MOTD line {i:03d} "
                        "abcdefghijklmnopqrstuvwxyz0123456789"
                    ),
                )
                send(f":{SRV} 376 {nick} :End of /MOTD command.")
            elif word == "JOIN" and not joined:
                joined = True
                chan = line.split(" ", 1)[1].split()[0].lstrip(":").split(",")[0]
                send(f":{nick}!u@203.0.113.9 JOIN :{chan}")
                send(f":{SRV} 332 {nick} {chan} :Probe channel")
                burst(
                    "J",
                    60,
                    lambda i: (
                        f":{SRV} 353 {nick} = {chan} :"
                        + " ".join(f"user{i:02d}{j:02d}" for j in range(8))
                    ),
                )
                send(f":{SRV} 366 {nick} {chan} :End of /NAMES list.")
            elif word == "PONG":
                tok = line.rsplit(":", 1)[-1].strip()
                m = TOKEN.match(tok)
                if (
                    m
                    and tok in sent
                    and m.group(3) == check(m.group(1), int(m.group(2)))
                ):
                    pongs.add(tok)
                else:
                    corrupt.append(tok[:40])
            elif word == "PING":
                send(f":{SRV} PONG {SRV} :{line.split(':', 1)[-1]}")
        if sent and time.time() - last_sent > 15 and (joined or time.time() - t0 > 60):
            break

    def lost(kind):
        all_k = sorted(t for t in sent if t[0] == kind)
        miss = [int(t[1:4]) for t in all_k if t not in pongs]
        return f"{len(miss)}/{len(all_k)} {miss[:12]}"

    msg = (
        f"{time.strftime('%H:%M:%S')} {peer[0]} nick={nick} MOTD lost {lost('M')} | "
        f"JOIN {'sent' if joined else 'NOT RECEIVED'} NAMES lost {lost('J')} | "
        f"CORRUPT {len(corrupt)} {corrupt[:4]}"
    )
    print(msg, flush=True)
    log.write(msg + "\n")
    log.flush()
    try:
        send("ERROR :Closing link (probe session done)")
    except OSError:
        pass
    conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6667)
    ap.add_argument("--lines", type=int, default=150)
    args = ap.parse_args()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"motd probe2 on :{args.port}, {args.lines} MOTD lines", flush=True)
    with open("motd_probe2_results.txt", "a") as log:
        while True:
            conn, peer = srv.accept()
            if peer[0] == "127.0.0.1" and args.port != 6667:
                pass
            session(conn, peer, args.lines, log)


if __name__ == "__main__":
    main()
