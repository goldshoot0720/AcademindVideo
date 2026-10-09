#!/usr/bin/env python3
"""Read the Bilibili mirror's part list and map it onto the course lectures.

The mirror (BV1Bxbk64Ep6, "academind - Pi - The Practical Guide") is a 45-part
re-upload whose parts carry the original lecture titles. Two lectures of the
47 are absent from it ("Ideas For Extensions", "/tree Examples"), so the mapping
is done by normalised title rather than by index.

Output: data/bili.json  {bvid, title, owner, duration, parts:[{page,cid,title,
        duration,slug,lectureNumber}]}
"""
import json
import os
import re
import sys
import urllib.request

BV = "BV1Bxbk64Ep6"
PAGE_URL = f"https://www.bilibili.com/video/{BV}/"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch_initial_state():
    """Bilibili serves a JS shell; curl with --compressed is the reliable way in."""
    import subprocess
    html = subprocess.run(
        ["curl", "-sL", "--compressed", "-A", UA,
         "-H", "Accept-Language: zh-CN,zh;q=0.9", PAGE_URL],
        capture_output=True, text=True, timeout=60).stdout
    if "__INITIAL_STATE__" not in html:
        # fall back to urllib in case curl is unavailable
        req = urllib.request.Request(PAGE_URL, headers={
            "User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "identity"})
        html = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.*)", html, re.S)
    if not m:
        raise RuntimeError("no __INITIAL_STATE__ -- page layout changed or blocked")
    raw = m.group(1)
    depth = 0
    for i, ch in enumerate(raw):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[:i + 1].replace("undefined", "null"))
    raise RuntimeError("unbalanced JSON in __INITIAL_STATE__")


def norm(t):
    t = t.lower()
    t = re.sub(r"^\d+\.\s*", "", t)          # leading "1. "
    t = re.sub(r"\s*\d+k\s*$", "", t)        # trailing bitrate "3355K"
    t = t.replace(":", "").replace("/", "").replace("-", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def main():
    state = fetch_initial_state()
    v = state["videoData"]
    parts = []
    for p in v["pages"]:
        title = re.sub(r"\s*\d+K\s*$", "", p["part"]).strip()
        num = re.match(r"^(\d+)\.", title)
        parts.append({
            "page": p["page"],
            "cid": p["cid"],
            "title": title,
            "duration": p["duration"],
            "key": norm(title),
            "number": int(num.group(1)) if num else None,
        })

    lib = json.load(open("data/lessons.json", encoding="utf-8"))
    by_number = {l["number"]: l for l in lib["lessons"]}
    by_key = {}
    for l in lib["lessons"]:
        by_key.setdefault(norm(l["title"]), []).append(l)

    matched = 0
    for p in parts:
        # The mirror renumbers sequentially, so it drifts from the course order
        # once it skips a lecture ("Ideas For Extensions"). Match on the title,
        # which is unique except for the three "Module Introduction" parts --
        # those are disambiguated by the part's own number.
        cands = by_key.get(p["key"], [])
        l = cands[0] if len(cands) == 1 else None
        if l is None and cands:
            l = next((c for c in cands if c["number"] == p["number"]), cands[0])
        if l is None:  # tolerate punctuation drift
            for k, cl in by_key.items():
                if k.startswith(p["key"][:22]) or p["key"].startswith(k[:22]):
                    l = cl[0]
                    break
        if l:
            p["lectureNumber"] = l["number"]
            p["slug"] = l["slug"]
            p["lectureTitle"] = l["title"]
            matched += 1
        else:
            p["slug"] = f"part-{p['page']:02d}"
            p["lectureTitle"] = None

    out = {
        "bvid": v["bvid"], "aid": v["aid"], "title": v["title"],
        "owner": v["owner"]["name"], "url": PAGE_URL,
        "duration": v["duration"], "partCount": len(parts),
        "parts": parts,
    }
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/bili.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"{v['title']} — {len(parts)} parts, {v['duration'] // 60} min, "
          f"matched {matched} to lectures")
    for p in parts:
        flag = " " if p["lectureTitle"] else "?"
        print(f" {flag} p{p['page']:02d} #{p['lectureNumber'] or '--':>2} "
              f"[{p['duration']:>4}s] {p['title'][:52]}")
    covered = {p.get("lectureNumber") for p in parts}
    missing = [f"{l['number']}. {l['title']}" for l in lib["lessons"]
               if l["number"] not in covered]
    if missing:
        print("\nnot in the mirror (%d):" % len(missing))
        for m in missing:
            print("  -", m)


if __name__ == "__main__":
    main()
