#!/usr/bin/env python3
"""Per-lesson inventory: what exists on disk vs. what is still missing.

Scans every course under courses/ (a course qualifies if it has
data/lessons.json) and reports, for each lesson:

  mirror   the lesson is mapped to a part of the Bilibili mirror
  video    video/<slug>.mp4
  audio    audio/<slug>.m4a            (ASR input)
  en       data/srt/en/<slug>.srt      (English transcript)
  zh       data/srt/bilingual/<slug>.srt or data/bilingual/<slug>.json
  ass      data/ass/<slug>.ass         (dynamic subtitle)

and derives a stage + the list of remaining steps:

  done        video+audio+en+zh present              -> nothing to do
  translate   video+audio+en present, zh missing     -> translate + build
  asr         audio present, en missing              -> transcribe
  audio       video present, audio missing           -> ffmpeg extract
  download    mirror mapped, nothing on disk         -> download part
  blocked     no mirror part and nothing on disk     -> needs another source

Outputs (under report/):
  lesson_inventory.csv   one row per lesson
  inventory.json         machine readable, feeds the per-lesson agent dispatcher
  inventory.md           human summary, per course + overall
  inventory.html         browsable dashboard

Usage:
  python3 scripts/inventory.py
  python3 scripts/inventory.py --only clean-code pi-the-practical-guide
"""
import argparse
import csv
import html
import json
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSES = os.path.join(ROOT, "courses")
REPORT = os.path.join(ROOT, "report")

MIN_VIDEO = 10_000
MIN_AUDIO = 5_000

ARTIFACTS = {
    "video": ["video/{slug}.mp4"],
    "audio": ["audio/{slug}.m4a"],
    "en": ["data/srt/en/{slug}.srt"],
    "zh": ["data/srt/bilingual/{slug}.srt", "data/bilingual/{slug}.json"],
    "ass": ["data/ass/{slug}.ass"],
}

STAGES = ["done", "translate", "asr", "audio", "download", "blocked"]
TODO = {
    "done": [],
    "translate": ["translate", "fix_empty", "build"],
    "asr": ["asr", "parse_srt", "translate", "fix_empty", "build"],
    "audio": ["ffmpeg_audio", "asr", "parse_srt", "translate", "fix_empty", "build"],
    "download": ["download", "ffmpeg_audio", "asr", "parse_srt",
                 "translate", "fix_empty", "build"],
    "blocked": ["find_source"],
}
LABEL = {
    "done": "完整（影片+音訊+英+中）",
    "translate": "缺中文譯文",
    "asr": "缺英文轉錄",
    "audio": "缺音訊",
    "download": "缺影片（鏡像可下載）",
    "blocked": "缺影片（鏡像無對應）",
}
COLOR = {
    "done": "#16a34a", "translate": "#2563eb", "asr": "#7c3aed",
    "audio": "#d97706", "download": "#dc2626", "blocked": "#9ca3af",
}


def has(d, slug, key, min_size=1):
    for pat in ARTIFACTS[key]:
        p = os.path.join(d, pat.format(slug=slug))
        if os.path.exists(p) and os.path.getsize(p) >= min_size:
            return True
    return False


def course_dirs(only=None):
    out = []
    for name in sorted(os.listdir(COURSES)):
        d = os.path.join(COURSES, name)
        if not os.path.isdir(d):
            continue
        if not os.path.exists(os.path.join(d, "data", "lessons.json")):
            continue
        if only and name not in only:
            continue
        out.append(d)
    return out


def mirror_map(d):
    p = os.path.join(d, "data", "bili.json")
    if not os.path.exists(p):
        return {}
    try:
        b = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    return {part["slug"]: part for part in b.get("parts", []) if part.get("slug")}


def scan(d):
    slug = os.path.basename(d)
    meta = json.load(open(os.path.join(d, "data", "lessons.json"), encoding="utf-8"))
    mir = mirror_map(d)
    rows = []
    for l in meta["lessons"]:
        s = l["slug"]
        v = has(d, s, "video", MIN_VIDEO)
        a = has(d, s, "audio", MIN_AUDIO)
        en = has(d, s, "en", 100)
        zh = has(d, s, "zh", 100)
        ass = has(d, s, "ass", 100)
        m = mir.get(s)

        if v and a and en and zh:
            stage = "done"
        elif v and a and en:
            stage = "translate"
        elif v and a:
            stage = "asr"
        elif v:
            stage = "audio"
        elif m:
            stage = "download"
        else:
            stage = "blocked"

        rows.append({
            "course": slug,
            "section": l.get("section"),
            "sectionTitle": l.get("sectionTitle", ""),
            "number": l.get("number"),
            "slug": s,
            "title": l.get("title", ""),
            "duration": l.get("duration", ""),
            "lectureId": l.get("lectureId", ""),
            "lessonUrl": l.get("lessonUrl", ""),
            "mirror": bool(m),
            "mirrorPage": m.get("page") if m else "",
            "video": v, "audio": a, "en": en, "zh": zh, "ass": ass,
            "stage": stage,
            "todo": "|".join(TODO[stage]),
        })
    return slug, meta, rows


def dur_to_sec(s):
    try:
        parts = [int(x) for x in str(s).split(":")]
    except ValueError:
        return 0
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def hhmm(sec):
    if not sec:
        return "-"
    h, rem = divmod(sec, 3600)
    return f"{h}h {rem // 60}m" if h else f"{rem // 60}m"


def count(rows):
    out = {}
    for r in rows:
        out[r["stage"]] = out.get(r["stage"], 0) + 1
    return out


def write_md(path, courses, rows, payload):
    gt = count(rows)
    L = ["# 每堂課素材盤點", "",
         f"產生時間：{payload['generatedAt']}　|　"
         f"{payload['totals']['courses']} 門課 / {payload['totals']['lessons']} 堂課 / "
         f"總時長 {hhmm(payload['totals']['seconds'])}", "",
         "## 總覽", "",
         "| 階段 | 堂數 | 說明 | 待處理步驟 |", "|---|---:|---|---|"]
    for s in STAGES:
        steps = " → ".join(TODO[s]) or "無"
        L.append(f"| `{s}` | {gt.get(s, 0)} | {LABEL[s]} | {steps} |")
    L += ["", "## 各課程", "",
          "| course | series | 課數 | 鏡像對應 | " + " | ".join(STAGES) + " | 時長 |",
          "|---|---|---:|---:|" + "---:|" * len(STAGES) + "---|"]
    for slug, c in courses.items():
        cells = " | ".join(str(c["stages"].get(s, 0)) for s in STAGES)
        L.append(f"| `{slug}` | {c['series']} | {c['lessons']} | "
                 f"{c['mirrorMapped']} | {cells} | {c['totalDuration']} |")
    L += ["", "## 待處理清單（前 15 堂）", "",
          "| course | # | title | 時長 | stage | 待處理步驟 |",
          "|---|---:|---|---|---|---|"]
    todo = sorted([r for r in rows if r["stage"] != "done"],
                  key=lambda r: (r["course"], r["number"] or 0))
    for r in todo[:15]:
        L.append(f"| `{r['course']}` | {r['number']} | {r['title']} | {r['duration']} | "
                 f"{r['stage']} | {r['todo'].replace('|', ' → ')} |")
    L += ["", f"完整清單共 {len(rows)} 列，見 `lesson_inventory.csv` / `inventory.json`。", ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def write_html(path, courses, rows, payload):
    e = html.escape
    gt = count(rows)
    n = max(1, len(rows))
    big = "".join(
        f'<div class="bar" style="width:{gt.get(s,0)/n*100:.4f}%;background:{COLOR[s]}" '
        f'title="{s}: {gt.get(s,0)}"></div>' for s in STAGES if gt.get(s, 0))
    legend = "".join(
        f'<span class="lg"><i style="background:{COLOR[s]}"></i>{s} '
        f'<b>{gt.get(s,0)}</b> <em>{LABEL[s]}</em></span>' for s in STAGES)

    cards = []
    for slug, c in courses.items():
        tot = max(1, c["lessons"])
        seg = "".join(
            f'<div class="bar" style="width:{c["stages"].get(s,0)/tot*100:.4f}%;'
            f'background:{COLOR[s]}" title="{s}: {c["stages"].get(s,0)}"></div>'
            for s in STAGES if c["stages"].get(s, 0))
        cells = "".join(f'<td class="n" style="color:{COLOR[s]}">'
                        f'{c["stages"].get(s,0)}</td>' for s in STAGES)
        cards.append(
            '<div class="card"><h3>' + e(c["series"]) + '</h3>'
            '<div class="sub"><code>' + e(slug) + '</code> · ' + str(c["lessons"]) +
            ' 堂 · ' + e(str(c["totalDuration"])) + ' · 鏡像對應 ' +
            str(c["mirrorMapped"]) + '/' + str(c["lessons"]) + '</div>'
            '<div class="track">' + seg + '</div>'
            '<table class="mini"><tr>' +
            "".join(f"<th>{s}</th>" for s in STAGES) +
            "</tr><tr>" + cells + "</tr></table></div>")

    doc = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每堂課素材盤點 · AcademindVideo</title>
<style>
:root{--bg:#f6f7f9;--fg:#111827;--mut:#6b7280;--bd:#e5e7eb;--card:#fff}
*{box-sizing:border-box}
body{margin:0;padding:28px 24px 60px;background:var(--bg);color:var(--fg);
font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC",
"Microsoft YaHei",sans-serif}
h1{font-size:20px;margin:0 0 4px}
h3{font-size:15px;margin:0 0 2px}
.sub{color:var(--mut);font-size:12px;margin-bottom:10px}
code{background:#eef0f3;padding:1px 5px;border-radius:4px;font-size:12px}
.head{color:var(--mut);font-size:12px;margin-bottom:14px}
.track{display:flex;height:34px;border-radius:6px;overflow:hidden;background:#e5e7eb;
margin:14px 0 12px}
.bar{height:100%}
.lg{display:inline-flex;align-items:center;gap:6px;margin:0 16px 6px 0;font-size:12px;
color:#374151}
.lg i{width:10px;height:10px;border-radius:3px;display:inline-block}
.lg em{color:var(--mut);font-style:normal}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;
margin-top:20px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px 16px}
table.mini{width:100%;border-collapse:collapse;font-size:12px}
table.mini th{color:var(--mut);font-weight:500;text-align:right;padding:2px 0}
table.mini td.n{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
table.tbl{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px;
background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden}
table.tbl th,table.tbl td{padding:6px 10px;border-bottom:1px solid var(--bd);
text-align:left}
table.tbl th{background:#f3f4f6;font-weight:600;color:#374151}
table.tbl td.n{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;color:#fff;font-size:11px;
font-weight:600}
h2{font-size:16px;margin:28px 0 4px}
</style></head><body>
<h1>每堂課素材盤點</h1>
<div class="head">__HEAD__</div>
<div class="track">__BIG__</div>
<div>__LEGEND__</div>
<h2>各課程</h2>
<div class="grid">__CARDS__</div>
<h2>待處理清單（前 __N__ 堂，共 __T__ 堂）</h2>
<table class="tbl"><tr><th>course</th><th>#</th><th>title</th><th>時長</th>
<th>stage</th><th>缺什麼</th><th>待處理步驟</th></tr>
__ROWS__
</table></body></html>"""

    todo = sorted([r for r in rows if r["stage"] != "done"],
                  key=lambda r: (r["course"], r["number"] or 0))
    trs = []
    for r in todo[:200]:
        missing = [k for k in ("video", "audio", "en", "zh")
                   if not r[k]]
        trs.append(
            "<tr><td><code>" + e(r["course"]) + "</code></td><td class='n'>" +
            str(r["number"]) + "</td><td>" + e(r["title"]) + "</td><td>" +
            e(str(r["duration"])) + "</td><td><span class='pill' style='background:" +
            COLOR[r["stage"]] + "'>" + r["stage"] + "</span></td><td>" +
            (", ".join(missing) or "-") + "</td><td>" +
            e(r["todo"].replace("|", " → ")) + "</td></tr>")

    doc = (doc
           .replace("__HEAD__", f"{payload['totals']['courses']} 門課 · "
                                f"{payload['totals']['lessons']} 堂課 · 總時長 "
                                f"{hhmm(payload['totals']['seconds'])} · "
                                f"產生於 {payload['generatedAt']}")
           .replace("__BIG__", big)
           .replace("__LEGEND__", legend)
           .replace("__CARDS__", "".join(cards))
           .replace("__ROWS__", "".join(trs))
           .replace("__N__", str(min(200, len(todo))))
           .replace("__T__", str(len(todo))))
    open(path, "w", encoding="utf-8").write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    os.makedirs(REPORT, exist_ok=True)
    dirs = course_dirs(args.only)
    if not dirs:
        sys.exit("no courses found")

    all_rows, courses = [], {}
    for d in dirs:
        slug, meta, rows = scan(d)
        all_rows.extend(rows)
        courses[slug] = {
            "series": meta.get("series", slug),
            "seriesUrl": meta.get("seriesUrl", ""),
            "instructor": meta.get("instructor", ""),
            "courseId": meta.get("courseId", ""),
            "sections": meta.get("sections"),
            "totalDuration": meta.get("totalDuration", ""),
            "lessons": len(rows),
            "mirrorMapped": sum(1 for r in rows if r["mirror"]),
            "stages": count(rows),
        }

    cols = ["course", "section", "sectionTitle", "number", "slug", "title", "duration",
            "lectureId", "lessonUrl", "mirror", "mirrorPage", "video", "audio", "en",
            "zh", "ass", "stage", "todo"]
    with open(os.path.join(REPORT, "lesson_inventory.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(all_rows)

    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "root": ROOT,
        "totals": {
            "courses": len(courses),
            "lessons": len(all_rows),
            "seconds": sum(dur_to_sec(r["duration"]) for r in all_rows),
            **count(all_rows),
        },
        "courses": courses,
        "lessons": all_rows,
    }
    with open(os.path.join(REPORT, "inventory.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    write_md(os.path.join(REPORT, "inventory.md"), courses, all_rows, payload)
    write_html(os.path.join(REPORT, "inventory.html"), courses, all_rows, payload)

    print(f"{'course':52s} " + " ".join(f"{s:>9s}" for s in STAGES) + "   total")
    for slug, c in courses.items():
        print(f"{slug:52s} " +
              " ".join(f"{c['stages'].get(s, 0):9d}" for s in STAGES) +
              f"   {c['lessons']}")
    gt = count(all_rows)
    print(f"{'TOTAL':52s} " + " ".join(f"{gt.get(s, 0):9d}" for s in STAGES) +
          f"   {len(all_rows)}")
    print("\nwrote report/{lesson_inventory.csv,inventory.json,inventory.md,inventory.html}")


if __name__ == "__main__":
    main()
