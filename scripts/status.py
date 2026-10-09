#!/usr/bin/env python3
"""Print a build-status table for every course folder."""
import glob
import json
import os
import re

FRAG = re.compile(r"\.f\d+\.")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

reg = json.load(open("scripts/courses.json", encoding="utf-8"))
regslugs = {c["slug"] for c in reg}
print(f"registered in courses.json: {len(reg)}")

tv = te = tb = tl = 0
for d in sorted(glob.glob("courses/*/")):
    s = os.path.basename(d.rstrip("/"))
    if not os.path.exists(d + "course.json"):
        print(f"  [no course.json] {s}")
        continue
    L = os.path.exists(d + "data/lessons.json")
    B = os.path.exists(d + "data/bili.json")
    nl = len(json.load(open(d + "data/lessons.json", encoding="utf-8"))["lessons"]) if L else 0
    nv = len([f for f in glob.glob(d + "video/*.mp4")
              if not FRAG.search(os.path.basename(f))])
    nfrag = len([f for f in glob.glob(d + "video/*")
                 if FRAG.search(os.path.basename(f))])
    ne = len(glob.glob(d + "data/srt/en/*.srt"))
    nb = len(glob.glob(d + "data/srt/bilingual/*.srt"))
    tag = "" if s in regslugs else "   <-- NOT in registry"
    flag = "OK " if (nb >= nl and nl) else "   "
    tv += nv
    te += ne
    tb += nb
    tl += nl
    print(f"  {flag}{s:<52} lessons={nl:<4} bili={'Y' if B else 'n'} "
          f"video={nv:<4} frag={nfrag:<3} en={ne:<4} bi={nb}{tag}")
print(f"\n  TOTAL lessons={tl} video={tv} en={te} bilingual={tb}")
