#!/usr/bin/env python3
"""Fetch English subtitles for every lecture of the Pi course.

For each lecture in data/lessons.json:
  lecture page -> attachment id (public; locked lectures need a session)
  attachment id -> Hotmart video id + signature  (needs a session when locked)
  video id + signature -> signed HLS master -> English WebVTT -> data/srt/en/<slug>.srt

Usage:
  python3 scripts/fetch_en.py                  # public lectures only (free previews)
  python3 scripts/fetch_en.py --cookie "..."   # use your enrolled session for all 47
  python3 scripts/fetch_en.py --cookie-file _scratch/cookie.txt
  python3 scripts/fetch_en.py --only 1 2 3     # subset by lesson number
  python3 scripts/fetch_en.py --force          # re-download even if cached
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hotmart  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie")
    ap.add_argument("--cookie-file")
    ap.add_argument("--only", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    cookie = args.cookie
    if args.cookie_file and os.path.exists(args.cookie_file):
        cookie = open(args.cookie_file, encoding="utf-8").read().strip()
    if cookie:
        print(f"using session cookie ({len(cookie)} chars)")

    lib = json.load(open("data/lessons.json", encoding="utf-8"))
    os.makedirs("data/srt/en", exist_ok=True)

    got = locked = failed = 0
    for l in lib["lessons"]:
        if args.only and l["number"] not in args.only:
            continue
        slug = l["slug"]
        out = f"data/srt/en/{slug}.srt"

        if not args.force and os.path.exists(out) and os.path.getsize(out) > 0:
            l["hasEn"] = True
            print(f"  = {l['number']:2d} {slug} (cached)")
            got += 1
            continue

        try:
            att, is_locked = hotmart.lecture_attachment(l["lessonUrl"], cookie)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {l['number']:2d} {slug}: page error {e}")
            failed += 1
            continue

        if not att:
            l["locked"] = True
            l["hasEn"] = False
            locked += 1
            print(f"  x {l['number']:2d} {slug}: locked (no attachment visible)")
            continue

        l["attachmentId"] = att
        l["locked"] = False
        try:
            info = hotmart.resolve_video(att, cookie)
            l["videoId"] = info["videoId"]
            l["hotmartDuration"] = info["duration"]
            srt, n, tracks = hotmart.english_srt(
                info["videoId"], info["signature"], info["applicationKey"])
            if not srt:
                print(f"  ! {l['number']:2d} {slug}: no subtitle track")
                l["hasEn"] = False
                failed += 1
                continue
            open(out, "w", encoding="utf-8").write(srt)
            l["hasEn"] = True
            l["cueCount"] = n
            l["subtitleTracks"] = tracks
            got += 1
            print(f"  + {l['number']:2d} {slug}: {n} cues, {len(srt)} bytes")
        except Exception as e:  # noqa: BLE001
            print(f"  ! {l['number']:2d} {slug}: {e}")
            failed += 1
        time.sleep(0.3)

    json.dump(lib, open("data/lessons.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nEnglish subtitles: {got} ok, {locked} locked, {failed} failed "
          f"(of {len(lib['lessons'])})")
    if locked and not cookie:
        print("→ locked lectures need your enrolled session; re-run with --cookie")


if __name__ == "__main__":
    main()
