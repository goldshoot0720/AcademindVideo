#!/usr/bin/env python3
"""Scrape an Academind course sidebar -> data/lessons.json.

Reads course.json (series / seriesUrl / courseId / instructor / platform) from
the course folder, fetches the public course page, finds the first lecture id,
then parses that lecture page's sidebar (sections + lectures in course order).

Output: data/lessons.json
"""
import html
import json
import os
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


def cfg():
    with open("course.json", encoding="utf-8") as f:
        return json.load(f)


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


def find_lecture_page(course_url, page):
    """Return the URL of the first lecture page (the sidebar lives there)."""
    for pat in (r"data-lecture-url='(/courses/[^']+/lectures/\d+)'",
                r"href='(/courses/[^']+/lectures/\d+)'",
                r"\"(/courses/[a-z0-9-]+/lectures/\d+)\"",
                r"(/courses/[a-z0-9-]+/lectures/\d+)"):
        m = re.search(pat, page)
        if m:
            return "https://pro.academind.com" + m.group(1)
    # fall back to the course page itself (some layouts inline the sidebar)
    return course_url


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
            raw = clean(name)
            dur = re.search(r"\((\d+:\d+)\)", raw) or re.search(r"\((\d+:\d+)\)", clean(rest))
            title = re.sub(r"\s*\(\d+:\d+\)\s*$", "", raw).strip()
            lessons.append({
                "section": si,
                "sectionTitle": section_title,
                "lectureId": lid,
                "lessonUrl": "https://pro.academind.com" + url if url.startswith("/") else url,
                "title": title,
                "duration": dur.group(1) if dur else None,
            })
    return lessons


def main():
    c = cfg()
    course_url = c["seriesUrl"]
    cookie = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"GET {course_url}")
    page = get(course_url, cookie)
    lec_url = find_lecture_page(course_url, page)
    if lec_url != course_url:
        print(f"GET {lec_url}")
        page = get(lec_url, cookie)
    lessons = parse_sidebar(page)
    if not lessons:
        sys.exit("could not parse any lectures -- page layout changed?")

    total = 0
    for i, l in enumerate(lessons, 1):
        l["number"] = i
        l["slug"] = slugify(l["title"], i)
        l["courseId"] = c["courseId"]
        if l["duration"]:
            mm, ss = l["duration"].split(":")
            total += int(mm) * 60 + int(ss)

    out = {
        "series": c["series"],
        "seriesUrl": course_url,
        "instructor": c["instructor"],
        "platform": c.get("platform", ""),
        "courseId": c["courseId"],
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
