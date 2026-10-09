#!/usr/bin/env python3
"""Verify each course's generated player/data.js is coherent.

Checks that window.SERIES_DATA has the right series name, the lesson count
matches lessons.json, and how many lessons actually carry bilingual segments.
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

rows = []
for d in sorted(glob.glob("courses/*/")):
    s = os.path.basename(d.rstrip("/"))
    dj = d + "player/data.js"
    lj = d + "data/lessons.json"
    if not os.path.exists(lj):
        continue
    nl = len(json.load(open(lj, encoding="utf-8"))["lessons"])
    if not os.path.exists(dj):
        rows.append((s, "NO data.js", nl, 0, 0))
        continue
    txt = open(dj, encoding="utf-8", errors="replace").read()
    m = re.search(r"window\.SERIES_DATA\s*=\s*(\{.*\});?\s*$", txt, re.S)
    if not m:
        rows.append((s, "unparsable", nl, 0, 0))
        continue
    data = json.loads(m.group(1))
    les = data.get("lessons", [])
    nzh = sum(1 for l in les if l.get("hasZh"))
    nvid = sum(1 for l in les if l.get("videoFile"))
    rows.append((s, data.get("series", "?"), nl, len(les), nzh, nvid))

print(f"{'course':<52}{'series':<40}{'lessons':>8}{'inData':>7}{'biling':>7}{'video':>6}")
for r in rows:
    if len(r) == 5:
        print(f"{r[0]:<52}{r[1]:<40}{r[2]:>8}{r[3]:>7}{r[4]:>7}")
    else:
        print(f"{r[0]:<52}{r[1]:<40}{r[2]:>8}{r[3]:>7}{r[4]:>7}{r[5]:>6}")
