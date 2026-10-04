"""Minimal IRC-like burst source for SpecTalkZX receive tests.

Connect the client with `/server <pc-ip> 6667`. After registration the probe
streams NOTICE lines with an interleaved `PING :P<n>` every --ping-every lines.
SpecTalkZX answers each PING with `PONG <server> :P<n>`, so missing PONGs are
lines lost end to end. The per-second `sent` counter is bytes accepted by the
PC TCP stack: it stalls only when the ESP closes its TCP window (backpressure).
"""

import argparse
import queue
import re
import socket
import threading
import time

PONG_RE = re.compile(rb"PONG\s+\S+\s+:?P(\d+)")
PING_RE = re.compile(rb"^PING\s+:?(\S+)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=6667)
    ap.add_argument("--rate", type=int, default=0, help="bytes/s cap, 0 = flat out")
    ap.add_argument("--ping-every", type=int, default=8)
    ap.add_argument("--sndbuf", type=int, default=4096)
    ap.add_argument("--pad", type=int, default=60, help="NOTICE filler length")
    ap.add_argument(
        "--seconds", type=int, default=0, help="stop sending after N s, 0 = Ctrl+C"
    )
    ap.add_argument(
        "--settle", type=int, default=30, help="wait for late PONGs after stop"
    )
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    print(f"listening on :{args.port}  (client: /server <this-pc-ip> {args.port})")
    conn, peer = srv.accept()
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, args.sndbuf)
    conn.settimeout(0.5)  # lets Ctrl+C through while the peer window is closed
    print(
        f"client {peer[0]} connected, sndbuf={conn.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)}"
    )

    st = {"sent": 0, "pings": {}, "pongs": set(), "nick": None, "done": False}
    replies = queue.Queue()

    def send_all(data):
        view = memoryview(data)
        while view:
            try:
                view = view[conn.send(view) :]
            except socket.timeout:
                pass  # nothing sent; retry

    registered = threading.Event()

    def reader():
        buf = b""
        while not st["done"]:
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.rstrip(b"\r")
                m = PONG_RE.search(line)
                if m:
                    st["pongs"].add(int(m.group(1)))
                elif line.startswith(b"NICK "):
                    st["nick"] = line[5:].split()[0].lstrip(b":")
                elif line.startswith(b"USER ") and st["nick"]:
                    registered.set()
                else:
                    m = PING_RE.match(line)
                    if m:
                        replies.put(b":probe PONG probe :" + m.group(1) + b"\r\n")
        st["done"] = True

    def monitor():
        last = 0
        t0 = time.time()
        while not st["done"]:
            time.sleep(1)
            now = time.time()
            sent = st["sent"]
            # PINGs older than the newest PONG and still unanswered were lost;
            # newer ones may simply be queued in TCP/ESP/ring buffers.
            top = max(st["pongs"], default=-1)
            lost = sum(1 for k in range(top) if k not in st["pongs"])
            print(
                f"t={now - t0:6.0f}s sent={sent:9d}B rate={sent - last:6d}B/s "
                f"pings={len(st['pings']):6d} pongs={len(st['pongs']):6d} lost={lost}"
            )
            last = sent

    threading.Thread(target=reader, daemon=True).start()
    registered.wait()
    nick = st["nick"]
    welcome = (
        b":probe 001 " + nick + b" :burst probe\r\n"
        b":probe 376 " + nick + b" :End of MOTD\r\n"
    )
    send_all(welcome)
    time.sleep(3)
    threading.Thread(target=monitor, daemon=True).start()

    seq = 0
    ping = 0
    t_start = time.time()
    fill = b"x" * args.pad
    try:
        while not st["done"]:
            if args.seconds and time.time() - t_start > args.seconds:
                break
            while not replies.empty():
                send_all(replies.get())
            if seq % args.ping_every == 0:
                st["pings"][ping] = time.time()
                line = b"PING :P%d\r\n" % ping
                ping += 1
            else:
                line = b":probe NOTICE " + nick + b" :seq %06d " % seq + fill + b"\r\n"
            seq += 1
            send_all(line)
            st["sent"] += len(line)
            if args.rate:
                ahead = st["sent"] / args.rate - (time.time() - t_start)
                if ahead > 0:
                    time.sleep(ahead)
    except (KeyboardInterrupt, OSError):
        pass
    print(f"stopped sending; settling {args.settle}s for late PONGs (Ctrl+C to skip)")
    try:
        t_end = time.time() + args.settle
        while time.time() < t_end and not st["done"]:
            while not replies.empty():
                send_all(replies.get())
            time.sleep(0.2)
    except (KeyboardInterrupt, OSError):
        pass
    st["done"] = True
    top = max(st["pongs"], default=-1)
    lost = [k for k in range(top) if k not in st["pongs"]]
    print(
        f"\nsummary: bytes={st['sent']} pings={len(st['pings'])} confirmed_upto=P{top} "
        f"lost={len(lost)} ({100.0 * len(lost) / max(1, top + 1):.1f}%) "
        f"unconfirmed_tail={len(st['pings']) - top - 1}"
    )
    conn.close()


if __name__ == "__main__":
    main()
