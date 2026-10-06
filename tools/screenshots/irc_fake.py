"""Tiny fictional IRC network for README screenshots (ExampleNet on localhost)."""

import itertools
import socket
import threading
import time

SERVER = "irc.example.net"
NICKS = [
    "@retrogal",
    "+zxfan",
    "Batch_Coder",
    "manic_miner",
    "pixeljoe",
    "KempstonKid",
    "dizzy_egg",
    "Matthew48K",
    "sinclair_c5",
    "knightlore",
    "zxdemo",
    "jetpac",
]
CHAT = [
    ("retrogal", "Welcome to #spectrum! Grab a cuppa and a cassette."),
    ("zxfan", "Just finished my divTIESUS build, works first time"),
    ("pixeljoe", "anyone tried the new colour globe on the Next?"),
    ("manic_miner", "Willy says hi from the Central Cavern"),
    ("KempstonKid", "loading... R Tape loading error, 0:1"),
    ("dizzy_egg", "SpecTalkZX on a real 48K, still amazed"),
    ("Matthew48K", "anyone up for a game of Chaos tonight?"),
    ("zxdemo", "new 256-byte intro coming this weekend"),
    ("Batch_Coder", "the 64-column font is lovely to read"),
    ("jetpac", "beep beep, fuel pod incoming"),
]


def serve(conn):
    nick = None
    buf = b""
    chat = itertools.cycle(CHAT)
    joined = threading.Event()
    lock = threading.Lock()

    def send(line):
        with lock:
            conn.sendall(line.encode() + b"\r\n")

    def talker():
        joined.wait()
        time.sleep(2)
        while True:
            who, text = next(chat)
            try:
                send(f":{who}!{who}@198.51.100.{len(who)} PRIVMSG #spectrum :{text}")
            except OSError:
                return
            time.sleep(1.5)

    threading.Thread(target=talker, daemon=True).start()
    while True:
        data = conn.recv(4096)
        if not data:
            return
        buf += data
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("latin-1").strip()
            cmd = line.split(" ", 1)[0].upper()
            arg = line.split(" ", 1)[1] if " " in line else ""
            if cmd == "NICK":
                nick = arg.lstrip(":")
            elif cmd == "USER" and nick:
                for n, text in [
                    ("001", f"Welcome to ExampleNet, {nick}"),
                    ("002", f"Your host is {SERVER}"),
                    ("003", "This server was created for a demo"),
                    ("004", f"{SERVER} demo-1.0 iow ovb"),
                ]:
                    send(f":{SERVER} {n} {nick} :{text}")
                send(
                    f":{SERVER} 005 {nick} NETWORK=ExampleNet CHANTYPES=#& PREFIX=(ov)@+ :are supported"
                )
                send(f":{SERVER} 375 {nick} :- {SERVER} Message of the Day -")
                send(
                    f":{SERVER} 372 {nick} :- A fictional network for SpecTalkZX screenshots"
                )
                send(f":{SERVER} 376 {nick} :End of /MOTD command.")
                send(f":{nick} MODE {nick} :+iw")
            elif cmd == "JOIN":
                for chan in arg.split(" ")[0].split(","):
                    send(f":{nick}!~zx@203.0.113.7 JOIN :{chan}")
                    send(
                        f":{SERVER} 332 {nick} {chan} :ZX Spectrum chat | SpecTalkZX 1.4.2 Triton is out"
                    )
                    send(f":{SERVER} 333 {nick} {chan} retrogal 1790000000")
                    send(f":{SERVER} 353 {nick} = {chan} :{nick} " + " ".join(NICKS))
                    send(f":{SERVER} 366 {nick} {chan} :End of /NAMES list.")
                joined.set()
            elif cmd == "PING":
                send(f":{SERVER} PONG {SERVER} :{arg.lstrip(':')}")
            elif cmd == "QUIT":
                return


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 6667))
    srv.listen(4)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
