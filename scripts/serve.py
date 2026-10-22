#!/usr/bin/env python3
"""Site server for the Academind bilingual-subtitle collection.

Serves the course-list homepage plus every course folder:

    /                             -> index.html  (course list)
    /courses/<slug>/player/       -> that course's player
    /courses/<slug>/video/*.mp4   -> lecture video (HTTP Range, so seeking works)
    /courses/<slug>/data/...      -> generated subtitle assets (SRT / ASS / JSON)

Every course is a self-contained folder, so adding a course needs no changes
here -- just drop it under courses/ and re-run scripts/build_index.py.

Usage:
  python3 scripts/serve.py                 # -> http://localhost:8788/
  python3 scripts/serve.py --port 9000
  python3 scripts/serve.py --open
"""
import argparse
import json
import os
import re
import socket
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import admin_api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def parse_range(header, size):
    """Parse one `Range: bytes=...` header for a file of `size` bytes.

    Returns (start, end) inclusive, False when the range cannot be satisfied
    (-> 416), or None when the header should be ignored (-> 200 full body).

    Suffix ranges matter: `bytes=-1024` means the *last* 1024 bytes, not the
    first 1025. Browsers ask for them when they need the tail of an MP4 (the
    moov atom), and getting the wrong bytes aborts playback.
    """
    m = RANGE_RE.match((header or "").strip())
    if not m:
        return None
    first, last = m.group(1), m.group(2)
    if first == "" and last == "":
        return None
    if first == "":
        n = int(last)
        if n <= 0 or size <= 0:
            return False
        return max(0, size - n), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if start >= size or start > end:
        return False
    return start, end


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        parts = [p for p in path.split("/") if p and p not in (os.curdir, os.pardir)]
        return os.path.join(ROOT, *parts) if parts else os.path.join(ROOT, "index.html")

    def do_GET(self):
        p = self.path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/admin/api/"):
            return self._admin_api("GET")
        target = self.translate_path(p)
        # a bare course folder -> its player
        if os.path.isdir(target) and not os.path.exists(os.path.join(target, "index.html")):
            if os.path.exists(os.path.join(target, "player", "index.html")):
                loc = p.rstrip("/") + "/player/"
                self.send_response(302)
                self.send_header("Location", loc)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        if os.path.isdir(target):
            self.path = p.rstrip("/") + "/index.html"
        super().do_GET()

    # ------------------------------------------------------------ admin api
    def _admin_api(self, method):
        """JSON endpoint for /admin/api/* (see scripts/admin_api.py)."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""
        code, payload = admin_api.route(method, self.path, body)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        p = self.path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/admin/api/"):
            return self._admin_api("POST")
        self.send_error(404, "Not Found")

    # ------------------------------------------------------------ range / mp4
    def send_head(self):
        path = self.translate_path(self.path)
        rng = self.headers.get("Range")
        if rng and os.path.isfile(path):
            size = os.path.getsize(path)
            span = parse_range(rng, size)
            if span is False:                      # unsatisfiable
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            if span:                               # (start, end) inclusive
                start, end = span
                self.send_response(206)
                self.send_header("Content-Type", self.guess_type(path))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(end - start + 1))
                self.end_headers()
                f = open(path, "rb")
                f.seek(start)
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
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    port = find_free_port(args.port)
    courses_dir = os.path.join(ROOT, "courses")
    slugs = sorted(d for d in os.listdir(courses_dir)
                   if os.path.isdir(os.path.join(courses_dir, d))) \
        if os.path.isdir(courses_dir) else []

    url = f"http://localhost:{port}/"
    print("AcademindVideo · bilingual subtitle collection")
    print(f"  courses        : {len(slugs)} ({', '.join(slugs) or 'none'})")
    print(f"  serving        : {url}")
    print("  Ctrl-C to stop\n")
    if args.open:
        webbrowser.open(url)

    srv = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler))
    srv.serve_forever()


if __name__ == "__main__":
    main()
