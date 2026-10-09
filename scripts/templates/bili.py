#!/usr/bin/env python3
"""Read the Bilibili mirror's part list and map it onto the course lectures.

Reads course.json for the mirror BV id. Parts carry the original lecture
titles, so the mapping is done by normalised title (with the part's own
leading number as a tie-breaker for repeated titles like "Module Introduction").

Output: data/bili.json  {bvid, title, owner, duration,
        parts:[{page,cid,title,duration,slug,lectureNumber}]}
"""
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
    by_number = {l["number"]: l for l in lib["lessons"]}
    by_key = {}
    for l in lib["lessons"]:
        by_key.setdefault(norm(l["title"]), []).append(l)

    matched = 0
    pointers = {}      # normalised title -> next unassigned candidate index
    used = set()       # lecture numbers already claimed by a part
    for p in parts:
        cands = by_key.get(p["key"], [])
        l = None
        # Repeated titles (e.g. "Module Introduction") keep their relative order
        # in the mirror, so hand the i-th such part the i-th such lecture -- the
        # part's own leading number drifts once the mirror skips a lecture.
        idx = pointers.get(p["key"], 0)
        while idx < len(cands) and cands[idx]["number"] in used:
            idx += 1
        if idx < len(cands):
            l = cands[idx]
            pointers[p["key"]] = idx + 1
        if l is None:  # tolerate punctuation drift
            for k, cl in by_key.items():
                free = [x for x in cl if x["number"] not in used]
                if free and (k.startswith(p["key"][:22]) or p["key"].startswith(k[:22])):
                    l = free[0]
                    break
        if l:
            used.add(l["number"])
            p["lectureNumber"] = l["number"]
            p["slug"] = l["slug"]
            p["lectureTitle"] = l["title"]
            matched += 1
        else:
            p["slug"] = f"part-{p['page']:02d}"
            p["lectureNumber"] = None
            p["lectureTitle"] = None

    # Some mirrors rename every part generically ("lesson1", "lesson2", ...),
    # so title matching finds nothing. The parts still follow course order, so
    # fall back to mapping them positionally onto the lectures that have a
    # video, then fix any adjacent pair whose durations are clearly swapped.
    if matched < len(parts) * 0.5:
        vid = [l for l in lib["lessons"] if l.get("duration")]
        assign = {p["page"]: (vid[i] if i < len(vid) else None)
                  for i, p in enumerate(parts)}

        def secs(d):
            try:
                m, s = d.split(":")
                return int(m) * 60 + int(s)
            except (AttributeError, ValueError):
                return None

        for _ in range(3):
            for i in range(len(parts) - 1):
                pi, pj = parts[i], parts[i + 1]
                li, lj = assign.get(pi["page"]), assign.get(pj["page"])
                if not li or not lj:
                    continue
                di, dj = secs(li.get("duration")), secs(lj.get("duration"))
                if di is None or dj is None:
                    continue
                cur = abs(pi["duration"] - di) + abs(pj["duration"] - dj)
                swp = abs(pi["duration"] - dj) + abs(pj["duration"] - di)
                if swp + 60 < cur:          # only obvious swaps
                    assign[pi["page"]], assign[pj["page"]] = lj, li

        matched = 0
        for p in parts:
            l = assign.get(p["page"])
            if l:
                p["lectureNumber"] = l["number"]
                p["slug"] = l["slug"]
                p["lectureTitle"] = l["title"]
                matched += 1
            else:
                p["slug"] = f"part-{p['page']:02d}"
                p["lectureNumber"] = None
                p["lectureTitle"] = None
        print(f"title match failed -> positional mapping: {matched}/{len(parts)} parts")

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
