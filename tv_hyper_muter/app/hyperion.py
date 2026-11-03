"""Minimal read-only Hyperion.NG websocket client (stdlib only).

Sends only `ledcolors imagestream-start/stop` and keeps the stream on just long enough to
receive one frame, so the TV does not encode a continuous stream for us.
"""
import base64
import json
import os
import socket
import struct
import time


class Hyperion:
    def __init__(self, host, port):
        self.host, self.port = host, port
        self.s = None

    def close(self):
        if self.s:
            try:
                self.s.close()
            except OSError:
                pass
        self.s = None

    def _recvn(self, n):
        b = b""
        while len(b) < n:
            c = self.s.recv(n - len(b))
            if not c:
                raise EOFError("connection closed")
            b += c
        return b

    def _connect(self):
        s = socket.create_connection((self.host, self.port), 8)
        s.settimeout(10)
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall((f"GET / HTTP/1.1\r\nHost: {self.host}:{self.port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        h = b""
        while b"\r\n\r\n" not in h:
            c = s.recv(1)
            if not c:
                raise EOFError("closed during handshake")
            h += c
        if b" 101 " not in h.split(b"\r\n")[0]:
            raise RuntimeError(f"websocket upgrade refused: {h[:80]!r}")
        self.s = s

    def _send(self, payload, op=1):
        m = os.urandom(4)
        n = len(payload)
        if n < 126:
            hdr = bytes([0x80 | op, 0x80 | n])
        else:
            hdr = bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
        self.s.sendall(hdr + m + bytes(c ^ m[i % 4] for i, c in enumerate(payload)))

    def _recv(self):
        data, first = b"", None
        while True:
            a, b = self._recvn(2)
            op, n = a & 15, b & 127
            if n == 126:
                n = struct.unpack(">H", self._recvn(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._recvn(8))[0]
            pl = self._recvn(n)
            if op == 9:
                self._send(pl, 10)
                continue
            if op == 8:
                raise EOFError("close frame")
            if op == 10:
                continue
            first = first if first is not None else op
            data += pl
            if a & 0x80:
                return first, data

    def _cmd(self, sub):
        self._send(json.dumps({"command": "ledcolors", "subcommand": sub}).encode())

    def frame(self):
        """Return one JPEG/PNG frame as bytes. Reconnects on demand; raises on failure."""
        if self.s is None:
            self._connect()
        try:
            self._cmd("imagestream-start")
            deadline = time.time() + 8
            while time.time() < deadline:
                op, d = self._recv()
                if op == 2:
                    return d
                r = json.loads(d)
                if r.get("command", "").endswith("imagestream-update"):
                    return base64.b64decode(r["result"]["image"].split(",", 1)[1])
            raise TimeoutError("no frame from Hyperion")
        except Exception:
            self.close()
            raise
        finally:
            if self.s:
                try:
                    self._cmd("imagestream-stop")
                except OSError:
                    self.close()
