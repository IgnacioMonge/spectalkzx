"""Run the ZXESPEmu ESP modem with *.example.net mapped to localhost."""

import os
import socket
import sys

sys.path.insert(0, os.environ["ZXESPEMU"])
_create = socket.create_connection


def create_connection(address, *args, **kwargs):
    host, port = address
    if host.endswith(".example.net"):
        host = "127.0.0.1"
    return _create((host, port), *args, **kwargs)


socket.create_connection = create_connection

import zxesp  # noqa: E402

sys.argv[0] = "zxesp.py"
raise SystemExit(zxesp.run(zxesp.parse_args()))
