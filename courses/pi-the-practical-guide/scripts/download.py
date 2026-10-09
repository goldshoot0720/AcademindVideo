#!/usr/bin/env python3
"""Download the Bilibili mirror parts and extract ASR-ready audio.

For every part in data/bili.json:
  video/<slug>.mp4   720p muxed video (played by the local site)
  audio/<slug>.m4a   16 kHz mono AAC (uploaded to AssemblyAI)

Skips anything already on disk, so it is safe to re-run.

Usage:
  python3 scripts/download.py               # all parts
  python3 scripts/download.py --only 1 2 3  # subset by lecture number
  python3 scripts/download.py --audio-only
  python3 scripts/download.py --max-height 1080
"""
import argparse
import json
import os
import subprocess
import sys

BV = "BV1Bxbk64Ep6"


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def download_part(part, max_height, audio_only):
    slug = part["slug"]
    url = f"https://www.bilibili.com/video/{BV}/?p={part['page']}"
    video = f"video/{slug}.mp4"
    audio = f"audio/{slug}.m4a"

    if not (os.path.exists(video) and os.path.getsize(video) > 10000):
        if audio_only:
            pass
        else:
            fmt = (f"bv*[height<={max_height}]+ba/b[height<={max_height}]"
                   f"/bv*+ba/b")
            r = run(["yt-dlp", "--no-warnings", "--no-playlist", "--retries", "5",
                     "--concurrent-fragments", "4", "-f", fmt,
                     "--merge-output-format", "mp4",
                     "-o", video, url])
            if not os.path.exists(video) or os.path.getsize(video) < 10000:
                return False, (r.stderr or r.stdout or "yt-dlp failed").strip()[-300:]

    if not (os.path.exists(audio) and os.path.getsize(audio) > 5000):
        src = video if os.path.exists(video) else None
        if src is None:
            return False, "no video to extract audio from"
        r = run(["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                 "-vn", "-ac", "1", "-ar", "16000", "-c:a", "aac", "-b:a", "48k",
                 audio])
        if not os.path.exists(audio):
            return False, (r.stderr or "ffmpeg failed").strip()[-300:]

    return True, f"{os.path.getsize(video)//1024 if os.path.exists(video) else 0} KB"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", type=int)
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--max-height", type=int, default=720)
    args = ap.parse_args()

    b = json.load(open("data/bili.json", encoding="utf-8"))
    os.makedirs("video", exist_ok=True)
    os.makedirs("audio", exist_ok=True)

    parts = [p for p in b["parts"]
             if not args.only or p.get("lectureNumber") in args.only]
    print(f"downloading {len(parts)} parts (max height {args.max_height}p)")

    ok = fail = 0
    for i, p in enumerate(parts, 1):
        label = f"#{p.get('lectureNumber') or '--':>2} p{p['page']:02d} {p['slug']}"
        good, note = download_part(p, args.max_height, args.audio_only)
        if good:
            ok += 1
            print(f"  [{i:2d}/{len(parts)}] OK  {label}  {note}", flush=True)
        else:
            fail += 1
            print(f"  [{i:2d}/{len(parts)}] ERR {label}  {note}", flush=True)

    print(f"\n{ok} downloaded, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
