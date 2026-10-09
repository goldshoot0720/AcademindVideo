#!/usr/bin/env python3
"""Local server for the bilingual subtitle site.

Serves the player plus the locally downloaded lecture videos:

    /                 -> player/index.html
    /video/<slug>.mp4 -> lecture video (HTTP Range supported, so seeking works)
    /data/...         -> generated subtitle assets (SRT / ASS / JSON)

Usage:
  python3 scripts/serve.py                 # -> http://localhost:8765/
  python3 scripts/serve.py --port 9000
  python3 scripts/serve.py --open
"""
import argparse
import json
import os
import posixpath
import re
import socket
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    # ---------------------------------------------------------------- routing
    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        path = posixpath.normpath(path)
        parts = [p for p in path.split("/") if p and p not in (os.curdir, os.pardir)]
        if not parts:
            parts = ["player", "index.html"]
        elif parts[-1].endswith("/"):
            parts.append("index.html")
        return os.path.join(ROOT, *parts)

    def do_GET(self):
        p = self.path.split("?", 1)[0]
        # the player lives at /player/ so that its relative script/video paths
        # (vendor/hls.min.js, data.js, ../data/...) resolve correctly
        if p in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/player/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p in ("/player", "/player/"):
            self.path = "/player/index.html"
        elif p.startswith("/video/") or p.startswith("/data/"):
            if not os.path.exists(self.translate_path(p)):
                self.send_error(404, "not generated yet")
                return
        elif not p.startswith("/player/"):
            self.send_error(404, "not found")
            return
        super().do_GET()

    # ------------------------------------------------------------ range / mp4
    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if rng and os.path.isfile(path):
            m = RANGE_RE.match(rng.strip())
            if m:
                size = os.path.getsize(path)
                start = int(m.group(1)) if m.group(1) else 0
                end = int(m.group(2)) if m.group(2) else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return None
                self.send_response(206)
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                f = open(path, "rb")
                f.seek(start)
                self._range_left = end - start + 1
                return _RangeFile(f, end - start + 1)
        if os.path.isfile(path) and path.endswith((".mp4", ".m4a")):
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(os.path.getsize(path)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return open(path, "rb")
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        msg = fmt % args
        if " 404 " in msg or " 416 " in msg or " 500 " in msg:
            sys.stderr.write("  %s\n" % msg)


class _RangeFile:
    """Wrap a file so copyfile() stops at the requested byte count."""

    def __init__(self, f, left):
        self.f, self.left = f, left

    def read(self, n=-1):
        if self.left <= 0:
            return b""
        if n < 0 or n > self.left:
            n = self.left
        data = self.f.read(n)
        self.left -= len(data)
        return data

    def close(self):
        self.f.close()


def find_free_port(preferred):
    for port in [preferred] + list(range(preferred + 1, preferred + 20)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    port = find_free_port(args.port)
    n_video = len([f for f in os.listdir(os.path.join(ROOT, "video"))
                   if f.endswith(".mp4")]) if os.path.isdir(os.path.join(ROOT, "video")) else 0
    n_srt = len(os.listdir(os.path.join(ROOT, "data", "srt", "bilingual"))) \
        if os.path.isdir(os.path.join(ROOT, "data", "srt", "bilingual")) else 0

    url = f"http://localhost:{port}/"
    print(f"AcademindVideo · Pi - The Practical Guide")
    print(f"  videos on disk : {n_video}")
    print(f"  bilingual SRTs : {n_srt}")
    print(f"  serving        : {url}")
    print("  Ctrl-C to stop\n")
    if args.open:
        webbrowser.open(url)

    srv = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler))
    srv.serve_forever()


if __name__ == "__main__":
    main()
