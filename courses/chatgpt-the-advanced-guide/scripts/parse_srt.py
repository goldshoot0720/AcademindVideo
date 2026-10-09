#!/usr/bin/env python3
"""Parse SRT files into structured JSON segments."""
import json
import os
import re
import sys


def parse_srt(text: str):
    text = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text.strip())
    segs = []
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip() != ""]
        if len(lines) < 2:
            continue
        m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*"
                      r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})", b)
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        # text is everything after the timestamp line
        ti = lines.index(next(l for l in lines if "-->" in l))
        txt = " ".join(lines[ti + 1:]).strip()
        txt = re.sub(r"<[^>]+>", "", txt)  # strip html tags
        if not txt:
            continue
        segs.append({"start": round(start, 3), "end": round(end, 3), "en": txt})
    return segs


def main():
    d = json.load(open("data/lessons.json", encoding="utf-8"))
    out_dir = "data/segments"
    os.makedirs(out_dir, exist_ok=True)
    grand = 0
    for l in d["lessons"]:
        slug = l["slug"]
        p = f"data/srt/en/{slug}.srt"
        if not os.path.exists(p):
            continue
        segs = parse_srt(open(p, encoding="utf-8", errors="replace").read())
        json.dump(segs, open(f"{out_dir}/{slug}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        grand += len(segs)
        print(f"{slug:52s} {len(segs):>4d} cues")
    print(f"\nTOTAL CUES: {grand}")


if __name__ == "__main__":
    main()
