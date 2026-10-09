#!/usr/bin/env python3
"""Scaffold course folders from scripts/courses.json.

For each registered course creates courses/<slug>/ with:
  course.json            per-course config read by the generic scripts
  scripts/               generic templates + the shared pi pipeline scripts
  player/                the player (index.html + vendor/hls.min.js)
  data/ video/ audio/ preview/ _scratch/

Re-running is safe: existing data/ video/ audio/ are left untouched.

Usage:
  python3 scripts/scaffold_courses.py            # all
  python3 scripts/scaffold_courses.py clean-code htmx-the-practical-guide
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "scripts", "courses.json")
TPL = os.path.join(ROOT, "scripts", "templates")
PI = os.path.join(ROOT, "courses", "pi-the-practical-guide")

TEMPLATES = ["scrape.py", "bili.py", "download.py"]
FROM_PI = ["asr.py", "parse_srt.py", "translate.py", "fix_empty.py",
           "build.py", "preview.py", "burn.py", "serve.py", "run_all.sh"]
SUBDIRS = ["scripts", "player", "player/vendor", "data", "video", "audio",
           "preview", "_scratch"]


def scaffold(c):
    d = os.path.join(ROOT, "courses", c["slug"])
    for s in SUBDIRS:
        os.makedirs(os.path.join(d, s), exist_ok=True)

    # course.json (drop helper keys)
    cfg = {k: v for k, v in c.items() if k not in ("note",)}
    with open(os.path.join(d, "course.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)

    for name in TEMPLATES:
        shutil.copy2(os.path.join(TPL, name), os.path.join(d, "scripts", name))
    for name in FROM_PI:
        shutil.copy2(os.path.join(PI, "scripts", name),
                     os.path.join(d, "scripts", name))

    shutil.copy2(os.path.join(PI, "player", "index.html"),
                 os.path.join(d, "player", "index.html"))
    vendor = os.path.join(PI, "player", "vendor")
    if os.path.isdir(vendor):
        for v in os.listdir(vendor):
            shutil.copy2(os.path.join(vendor, v),
                         os.path.join(d, "player", "vendor", v))

    key = os.path.join(PI, "_scratch", "assemblyai.key")
    if os.path.exists(key):
        shutil.copy2(key, os.path.join(d, "_scratch", "assemblyai.key"))

    print(f"  scaffolded {c['slug']:<50} bv={c['bv']}")


def main():
    reg = json.load(open(REG, encoding="utf-8"))
    only = sys.argv[1:]
    for c in reg:
        if only and c["slug"] not in only:
            continue
        scaffold(c)
    print(f"\ndone ({len(reg)} registered)")


if __name__ == "__main__":
    main()
