#!/usr/bin/env python3
"""Scrape an Academind course curriculum -> data/lessons.json.

Reads course.json (series / seriesUrl / courseId / instructor / platform) from
the course folder, fetches the public course page (falling back to the first
lecture page when the sidebar is not inlined), then parses sections + lectures
in course order.

Teachable serves three different curriculum layouts and Academind uses all of
them, so parse_sidebar() auto-detects:

  v2   <section class='bl block__curriculum__section'>
         block__curriculum__section__title + li ...data-ss-lecture-id
         + block__curriculum__section__list__item__lecture-name
  v1   <div class='col-sm-12 course-section'>
         class='section-title' + <li data-lecture-id="..."><span class='lecture-name'>
  old  <div class='col-sm-12 course-section'> with <li class='section-item'>
         anchors to /lectures/<id> and the title as bare text

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
                r"href=\"(/courses/[a-z0-9-]+/lectures/\d+)\"",
                r"(/courses/[a-z0-9-]+/lectures/\d+)"):
        m = re.search(pat, page)
        if m:
            return "https://pro.academind.com" + m.group(1)
    return course_url


def _title_and_duration(raw, kind="video"):
    """Split 'Welcome to the Course (1:03)' into ('Welcome to the Course','1:03')."""
    dur = re.search(r"\((\d+:\d+)\)", raw)
    title = re.sub(r"\s*\(\d+:\d+\)\s*", " ", raw)
    title = re.sub(r"\b(Preview|Start|Review|Complete|Start next lecture)\b", " ", title)
    title = re.sub(r"\s+", " ", title).strip(" -–—|")
    return title, (dur.group(1) if dur else None)


def parse_v2(page):
    lessons = []
    parts = re.split(r"<section class=['\"]bl block__curriculum__section['\"]>", page)[1:]
    if not parts:
        return []
    for si, p in enumerate(parts, 1):
        head = p.split("block__curriculum__section__list")[0]
        st = re.search(r"block__curriculum__section__title[^>]*>(.*)", head, re.S)
        section_title = None
        if st:
            raw = st.group(1).split("<div class=")[0]
            section_title = clean(raw) or None
        items = re.findall(
            r"<li class=['\"]block__curriculum__section__list__item[^'\"]*['\"]>(.*?)</li>",
            p, re.S)
        for body in items:
            lid = re.search(r"data-ss-lecture-id=['\"](\d+)['\"]", body)
            nm = re.search(r"lecture-name['\"][^>]*>(.*?)</span>", body, re.S)
            if not (lid and nm):
                continue
            dur = re.search(r"lecture-duration['\"][^>]*>(.*?)</span>", body, re.S)
            raw = clean(nm.group(1))
            title, d = _title_and_duration(raw)
            if not d and dur:
                d = (re.search(r"\((\d+:\d+)\)", clean(dur.group(1))) or [None, None])[1]
            kind = "video" if "icon__Video" in body else "text"
            lessons.append({
                "section": si, "sectionTitle": section_title,
                "lectureId": lid.group(1),
                "lessonUrl": "https://pro.academind.com/courses/x/lectures/" + lid.group(1),
                "title": title, "duration": d, "kind": kind,
            })
    return lessons


def parse_v1(page):
    lessons = []
    parts = re.split(r"<div class=['\"]col-sm-12 course-section['\"]>", page)[1:]
    for si, p in enumerate(parts, 1):
        head = p.split("<ul class='section-list'>")[0]
        st = re.search(r"class=['\"]section-title['\"][^>]*>(.*)", head, re.S)
        section_title = None
        if st:
            raw = st.group(1).split("<div class=")[0]
            section_title = clean(raw) or None
        # v1 markup
        items = re.findall(
            r"<li data-lecture-id=\"(\d+)\"[^>]*data-lecture-url='([^']*)'.*?"
            r"<span class='lecture-name'>(.*?)</span>(.*?)</li>", p, re.S)
        if items:
            for lid, url, name, rest in items:
                title, d = _title_and_duration(clean(name))
                if not d:
                    d = (re.search(r"\((\d+:\d+)\)", clean(rest)) or [None, None])[1]
                lessons.append({
                    "section": si, "sectionTitle": section_title,
                    "lectureId": lid,
                    "lessonUrl": "https://pro.academind.com" + url if url.startswith("/") else url,
                    "title": title, "duration": d, "kind": "video",
                })
            continue
        # old markup: <li class='section-item'> with the title as bare text
        for body in re.findall(r"<li class=['\"]section-item['\"]>(.*?)</li>", p, re.S):
            m = re.search(r"/lectures/(\d+)", body)
            if not m:
                continue
            raw = re.sub(r"\s+", " ", clean(body)).strip()
            title, d = _title_and_duration(raw)
            kind = "text" if "fa-file-text" in body else "video"
            lessons.append({
                "section": si, "sectionTitle": section_title,
                "lectureId": m.group(1),
                "lessonUrl": "https://pro.academind.com/courses/x/lectures/" + m.group(1),
                "title": title, "duration": d, "kind": kind,
            })
    return lessons


def parse_sidebar(page):
    for fn in (parse_v2, parse_v1):
        lessons = fn(page)
        if lessons:
            return lessons
    return []


def main():
    c = cfg()
    course_url = c["seriesUrl"]
    cookie = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"GET {course_url}")
    page = get(course_url, cookie)
    lessons = parse_sidebar(page)
    if not lessons:
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
        # normalise the lecture URL to the real course slug
        slug = re.search(r"/courses/([a-z0-9-]+)/", course_url)
        if slug:
            l["lessonUrl"] = (f"https://pro.academind.com/courses/{slug.group(1)}"
                              f"/lectures/{l['lectureId']}")
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
        print(f"  {l['number']:2d}. [{l['duration'] or '--:--':>5}] "
              f"{'[T] ' if l.get('kind') == 'text' else ''}{l['title']}")


if __name__ == "__main__":
    main()
