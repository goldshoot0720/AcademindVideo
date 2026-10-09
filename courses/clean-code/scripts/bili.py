#!/usr/bin/env python3
"""Read the Bilibili mirror's part list and map it onto the course lectures.

Reads course.json for the mirror BV id. Parts carry the original lecture
titles, so the mapping is done by normalised title (with the part's own
leading number as a tie-breaker for repeated titles like "Module Introduction").

Output: data/bili.json  {bvid, title, owner, duration,
        parts:[{page,cid,title,duration,slug,lectureNumber}]}
"""
import difflib
import json
import os
import re
import subprocess
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def cfg():
    with open("course.json", encoding="utf-8") as f:
        return json.load(f)


def fetch_initial_state(page_url):
    """Bilibili serves a JS shell; curl with --compressed is the reliable way in."""
    html = subprocess.run(
        ["curl", "-sL", "--compressed", "-A", UA,
         "-H", "Accept-Language: zh-CN,zh;q=0.9", page_url],
        capture_output=True, text=True, timeout=60).stdout
    if "__INITIAL_STATE__" not in html:
        req = urllib.request.Request(page_url, headers={
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
    t = re.sub(r"^\d+([-.]\d+)?\s*[-.):]*\s*", "", t)  # leading "1. ", "1-1 -", "12 -"
    t = re.sub(r"\s*\d+k\s*$", "", t)                  # trailing bitrate "3355K"
    t = re.sub(r"[^a-z0-9]+", " ", t)                  # drop quotes, _ , / , ? , - ...
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def main():
    c = cfg()
    bv = c["bv"]
    page_url = f"https://www.bilibili.com/video/{bv}/"
    state = fetch_initial_state(page_url)
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
    lessons = sorted(lib["lessons"], key=lambda x: x["number"])
    lkeys = [(l, norm(l["title"])) for l in lessons]

    # The mirror carries the original lecture titles, but Bilibili truncates
    # them (~35 chars) and repeats some ("Module Introduction" appears 5x).
    # Match each part, in page order, to the next still-unused lecture whose
    # title best resembles it. The mirror preserves course order, so the search
    # only looks forward and never reuses a lecture -- this keeps truncated and
    # repeated titles from collapsing onto a single lecture.
    matched = 0
    pos = 0
    for p in parts:
        key = p["key"]
        best = best_j = None
        best_r = 0.0
        for j in range(pos, len(lkeys)):
            l, lk = lkeys[j]
            r = difflib.SequenceMatcher(None, key, lk).ratio()
            if lk == key:
                r = 1.0
            elif lk.startswith(key) or key.startswith(lk):
                r = max(r, 0.92)
            if r > best_r:
                best_r, best, best_j = r, l, j
        if best is not None and best_r >= 0.55:
            p["lectureNumber"] = best["number"]
            p["slug"] = best["slug"]
            p["lectureTitle"] = best["title"]
            pos = best_j + 1
            matched += 1
        else:
            p["slug"] = f"part-{p['page']:02d}"
            p["lectureNumber"] = None
            p["lectureTitle"] = None

    out = {
        "bvid": v["bvid"], "aid": v["aid"], "title": v["title"],
        "owner": v["owner"]["name"], "url": page_url,
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
