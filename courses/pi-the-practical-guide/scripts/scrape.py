#!/usr/bin/env python3
"""Scrape the Academind "Pi - The Practical Guide" course structure.

Reads the public course page sidebar (sections + lectures, in course order)
and writes data/lessons.json.

The page is public: no login required. Lecture pages themselves are also
public, but only the free-preview lectures expose a video attachment to
anonymous visitors -- see scripts/fetch_en.py.

Output: data/lessons.json
"""
import html
import json
import os
import re
import sys
import urllib.request

COURSE_URL = "https://pro.academind.com/courses/pi-the-practical-guide"
COURSE_ID = "3008094"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def get(url, cookie=None):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def slugify(title, number):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return f"{number:02d}-{s}"[:70]


def parse_sidebar(page):
    """Return [{section, sectionTitle, lectureId, title, duration}] in course order."""
    lessons = []
    parts = re.split(r"<div class='col-sm-12 course-section'>", page)[1:]
    for si, p in enumerate(parts, 1):
        st = re.search(r"class='section-title'[^>]*>(.*?)</div>", p, re.S)
        section_title = clean(st.group(1)) if st else None
        items = re.findall(
            r"<li data-lecture-id=\"(\d+)\"[^>]*data-lecture-url='([^']*)'.*?"
            r"<span class='lecture-name'>(.*?)</span>(.*?)</li>",
            p, re.S)
        for lid, url, name, rest in items:
            # the title cell contains the name plus a "(3:55)" duration
            raw = clean(name)
            dur = re.search(r"\((\d+:\d+)\)", raw) or re.search(r"\((\d+:\d+)\)", clean(rest))
            title = re.sub(r"\s*\(\d+:\d+\)\s*$", "", raw).strip()
            lessons.append({
                "section": si,
                "sectionTitle": section_title,
                "lectureId": lid,
                "lessonUrl": COURSE_URL + "/lectures/" + lid,
                "title": title,
                "duration": dur.group(1) if dur else None,
            })
    return lessons


def main():
    cookie = None
    if len(sys.argv) > 1:
        cookie = sys.argv[1]
    print(f"GET {COURSE_URL}")
    page = get(COURSE_URL + "/lectures/" + "66409091", cookie)
    lessons = parse_sidebar(page)
    if not lessons:
        sys.exit("could not parse any lectures -- page layout changed?")

    total = 0
    for i, l in enumerate(lessons, 1):
        l["number"] = i
        l["slug"] = slugify(l["title"], i)
        l["courseId"] = COURSE_ID
        if l["duration"]:
            mm, ss = l["duration"].split(":")
            total += int(mm) * 60 + int(ss)

    out = {
        "series": "Pi - The Practical Guide",
        "seriesUrl": COURSE_URL,
        "instructor": "Maximilian Schwarzmüller",
        "platform": "Academind (Teachable + Hotmart player)",
        "courseId": COURSE_ID,
        "sections": len({l["section"] for l in lessons}),
        "totalDuration": f"{total // 3600}h {(total % 3600) // 60}m",
        "generatedBy": "AcademindVideo/scripts/scrape.py",
        "lessons": lessons,
    }
    os.makedirs("data", exist_ok=True)
    json.dump(out, open("data/lessons.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"wrote data/lessons.json: {len(lessons)} lectures, "
          f"{out['sections']} sections, {out['totalDuration']}")
    for l in lessons:
        print(f"  {l['number']:2d}. [{l['duration'] or '--:--':>5}] {l['title']}")


if __name__ == "__main__":
    main()
