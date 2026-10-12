#!/usr/bin/env python3
"""Read the Bilibili mirror's part list and map it onto the course lectures.

Reads course.json for the mirror BV id. `bv` may be a single id or a list of
ids -- some courses are uploaded as several videos ("... part1", "... part2"),
and their parts are concatenated in the order given. Every part carries the bv
it lives in, so download.py can build the right `?p=` URL.

Parts carry the original lecture titles, so the mapping is done by normalised
title (with the part's own leading number as a tie-breaker for repeated titles
like "Module Introduction").

Output: data/bili.json  {bvid, title, owner, duration, partCount, mirrors:[...],
        parts:[{bv,page,cid,title,duration,slug,lectureNumber,lectureTitle}]}
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


def bv_list(c):
    """`bv` may be a bare string or a list of mirror ids."""
    bv = c.get("bv") or []
    if isinstance(bv, str):
        bv = [bv]
    return [b for b in bv if b]


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
    # The mirror drops punctuation the course keeps (and vice versa): "Deno's"
    # -> "Denos", "Node.js" -> "Nodejs", "Cross-Origin" -> "CrossOrigin". Erase
    # apostrophes/dots/hyphens outright so both spellings collapse together.
    t = re.sub(r"['\u2019.\-]", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)                  # drop quotes, _ , / , ? ...
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def read_mirror(bv):
    """Fetch one mirror -> (videoData, [part dicts]) with a per-part `bv`."""
    page_url = f"https://www.bilibili.com/video/{bv}/"
    state = fetch_initial_state(page_url)
    v = state["videoData"]
    parts = []
    for p in v["pages"]:
        title = re.sub(r"\s*\d+K\s*$", "", p["part"]).strip()
        num = re.match(r"^(\d+)\.", title)
        parts.append({
            "bv": bv,
            "page": p["page"],
            "cid": p["cid"],
            "title": title,
            "duration": p["duration"],
            "key": norm(title),
            "number": int(num.group(1)) if num else None,
        })
    return v, parts, page_url


def main():
    c = cfg()
    bvs = bv_list(c)
    if not bvs:
        raise SystemExit("course.json has no 'bv'")

    parts = []
    mirrors = []
    for bv in bvs:
        v, ps, page_url = read_mirror(bv)
        parts.extend(ps)
        mirrors.append({
            "bvid": v["bvid"], "title": v["title"],
            "owner": v["owner"]["name"], "url": page_url,
            "duration": v["duration"], "partCount": len(ps),
        })
        print(f"  {bv}: {len(ps)} parts — {v['title']}")

    lib = json.load(open("data/lessons.json", encoding="utf-8"))
    by_number = {l["number"]: l for l in lib["lessons"]}
    by_key = {}
    for l in lib["lessons"]:
        by_key.setdefault(norm(l["title"]), []).append(l)

    matched = 0
    pointers = {}      # normalised title -> next unassigned candidate index
    used = set()       # lecture numbers already claimed by a part
    for i, p in enumerate(parts):
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
            p["slug"] = f"part-{i + 1:03d}"
            p["lectureNumber"] = None
            p["lectureTitle"] = None

    # Some mirrors rename every part generically ("lesson1", "lesson2", ...),
    # so title matching finds nothing. The parts still follow course order, so
    # fall back to mapping them positionally onto the lectures that have a
    # video, then fix any adjacent pair whose durations are clearly swapped.
    if matched < len(parts) * 0.5:
        vid = [l for l in lib["lessons"] if l.get("duration")]
        assign = {i: (vid[i] if i < len(vid) else None)
                  for i in range(len(parts))}

        def secs(d):
            try:
                m, s = d.split(":")
                return int(m) * 60 + int(s)
            except (AttributeError, ValueError):
                return None

        for _ in range(3):
            for i in range(len(parts) - 1):
                pi, pj = parts[i], parts[i + 1]
                li, lj = assign.get(i), assign.get(i + 1)
                if not li or not lj:
                    continue
                di, dj = secs(li.get("duration")), secs(lj.get("duration"))
                if di is None or dj is None:
                    continue
                cur = abs(pi["duration"] - di) + abs(pj["duration"] - dj)
                swp = abs(pi["duration"] - dj) + abs(pj["duration"] - di)
                if swp + 60 < cur:          # only obvious swaps
                    assign[i], assign[i + 1] = lj, li

        matched = 0
        for i, p in enumerate(parts):
            l = assign.get(i)
            if l:
                p["lectureNumber"] = l["number"]
                p["slug"] = l["slug"]
                p["lectureTitle"] = l["title"]
                matched += 1
            else:
                p["slug"] = f"part-{i + 1:03d}"
                p["lectureNumber"] = None
                p["lectureTitle"] = None
        print(f"title match failed -> positional mapping: {matched}/{len(parts)} parts")

    total_duration = sum(m["duration"] for m in mirrors)
    title = " + ".join(m["title"] for m in mirrors) if len(mirrors) > 1 else mirrors[0]["title"]
    out = {
        "bvid": mirrors[0]["bvid"],
        "aid": None,
        "title": title,
        "owner": mirrors[0]["owner"],
        "url": mirrors[0]["url"],
        "duration": total_duration,
        "partCount": len(parts),
        "mirrors": mirrors,
        "parts": parts,
    }
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/bili.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"{title} — {len(parts)} parts, {total_duration // 60} min, "
          f"matched {matched} to lectures")
    for p in parts:
        flag = " " if p["lectureTitle"] else "?"
        print(f" {flag} {p['bv']} p{p['page']:02d} #{p['lectureNumber'] or '--':>2} "
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
