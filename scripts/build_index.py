#!/usr/bin/env python3
"""Generate the course-list homepage (index.html) from the course folders.

Scans courses/<slug>/ for a data/lessons.json plus the generated assets and
writes a self-contained landing page linking into each course's player.

Usage:
  python3 scripts/build_index.py
"""
import glob
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSES = os.path.join(ROOT, "courses")

# gradient + short logo text per course (falls back to a derived default)
STYLE = {
    "pi-the-practical-guide": ("#f2b705", "#e8590c", "Pi"),
    "htmx-the-practical-guide": ("#38bdf8", "#0ea5e9", "HX"),
    "ai-key-concepts-terms-the-missing-guide": ("#a855f7", "#6366f1", "AK"),
    "clean-code": ("#34d399", "#059669", "CC"),
    "ai-agents-workflows-the-practical-guide": ("#a78bfa", "#7c3aed", "AG"),
    "ai-for-developers": ("#7c5cff", "#3b82f6", "AI"),
    "chatgpt-the-advanced-guide": ("#10a37f", "#0d8a6a", "GPT"),
    "claude-code-the-practical-guide": ("#d97757", "#c2410c", "CC"),
    "claude-cowork-the-practical-guide": ("#d97757", "#a855f7", "CW"),
    "vps-essentials-the-practical-guide": ("#0ea5e9", "#1e40af", "VPS"),
    "bun-the-practical-guide": ("#f472b6", "#f59e0b", "Bun"),
    "local-llms-via-ollama-lm-studio-the-practical-guide": ("#22c55e", "#0891b2", "LLM"),
    "codex-the-practical-guide": ("#14b8a6", "#047857", "CDX"),
    "javascript-algorithms-the-fundamentals": ("#f7df1e", "#eab308", "JS"),
    "javascript-data-structures-the-fundamentals": ("#f7df1e", "#f97316", "DS"),
}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def dur_to_sec(s):
    """Accept both '6h 48m' / '1h 5m' and 'HH:MM' / 'H:MM:SS'."""
    s = str(s or "").strip()
    m = re.fullmatch(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", s)
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
    try:
        p = [int(x) for x in s.split(":")]
    except ValueError:
        return 0
    if len(p) == 2:
        return p[0] * 60 + p[1]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    return 0


def fmt_dur(sec):
    """312m -> '5h 12m', 47m -> '47m'."""
    h, m = divmod(int(round(sec / 60)), 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def collect():
    courses = []
    for d in sorted(glob.glob(os.path.join(COURSES, "*"))):
        if not os.path.isdir(d):
            continue
        meta_path = os.path.join(d, "data", "lessons.json")
        if not os.path.exists(meta_path):
            continue
        lib = json.load(open(meta_path, encoding="utf-8"))
        slug = os.path.basename(d)
        lessons = lib.get("lessons", [])
        # Only count real lecture videos: the mirror downloads can leave
        # fragmented ".fN.mp4" parts behind, which would otherwise push the
        # progress bars past 100%. Matches how build.py sets lesson.videoFile.
        n_video = sum(1 for l in lessons
                      if l.get("slug")
                      and os.path.exists(os.path.join(d, "video", f"{l['slug']}.mp4")))
        n_bilingual = len(glob.glob(os.path.join(d, "data", "srt", "bilingual", "*.srt")))
        n_en = len(glob.glob(os.path.join(d, "data", "srt", "en", "*.srt")))
        g = STYLE.get(slug, ("#64748b", "#0ea5e9", (lib.get("series") or slug)[:2].upper()))
        # declared total first; fall back to summing the per-lesson durations
        seconds = dur_to_sec(lib.get("totalDuration"))
        if not seconds:
            seconds = sum(dur_to_sec(l.get("duration")) for l in lessons)
        courses.append({
            "slug": slug,
            "series": lib.get("series") or slug,
            "seriesUrl": lib.get("seriesUrl"),
            "instructor": lib.get("instructor") or "",
            "platform": lib.get("platform") or "",
            "sections": lib.get("sections") or len({l.get("section") for l in lessons}),
            "totalDuration": fmt_dur(seconds),
            "seconds": seconds,
            "lessons": len(lessons),
            "videos": n_video,
            "bilingual": n_bilingual,
            "en": n_en,
            "c1": g[0], "c2": g[1], "logo": g[2],
        })
    return courses


def bar(done, total, color):
    pct = (100 * done / total) if total else 0
    return (f'<div class="bar"><span style="width:{pct:.0f}%;background:{color}"></span></div>'
            f'<div class="barlab"><b>{done}</b> / {total}</div>')


# Appended verbatim (not an f-string) so the braces stay single.
# Fills in the per-card "已觀看" row from the av:watched record the player
# writes when a lecture plays through to the end.
WATCH_JS = """
<script>
(function(){
  var all={};
  try{ all=JSON.parse(localStorage.getItem("av:watched")||"{}")||{}; }catch(e){}
  var cards=document.querySelectorAll(".card[data-slug]");
  var totW=0, totP=0, doneCourses=0, seen={};
  Array.prototype.forEach.call(cards,function(card){
    var slug=card.getAttribute("data-slug");
    if(seen[slug]) return; seen[slug]=1;
    var playable=parseInt(card.getAttribute("data-playable"),10)||0;
    var m=(all&&all[slug])||{}, n=0;
    for(var k in m){ if(Object.prototype.hasOwnProperty.call(m,k)) n++; }
    if(playable && n>playable) n=playable;
    var row=card.querySelector(".covrow.watch");
    var wn=row&&row.querySelector(".wn"), wf=row&&row.querySelector(".wfill");
    if(wn) wn.textContent=n;
    if(wf) wf.style.width=(playable?Math.round(100*n/playable):0)+"%";
    if(n>0 && row) row.classList.add("has");
    if(playable && n>=playable){
      card.classList.add("allwatched");
      var db=card.querySelector(".chip.done"); if(db) db.hidden=false;
      doneCourses++;
    }
    totW+=n; totP+=playable;
  });
  var sv=document.getElementById("statWatchV"); if(sv) sv.textContent=totW;
  var sc=document.getElementById("statDone"); if(sc) sc.textContent=doneCourses;
  var box=document.getElementById("statWatch"); if(box && totW>0) box.hidden=false;
})();
</script>
"""


# Reorders the course grid client-side. The chosen mode is remembered in
# localStorage so the list comes back the way the visitor left it.
SORT_JS = """
<script>
(function(){
  var grid=document.querySelector(".grid"), seg=document.getElementById("sortSeg");
  if(!grid||!seg) return;
  var cards=Array.prototype.slice.call(grid.querySelectorAll(".card[data-slug]"));
  if(!cards.length) return;
  function name(c){ return c.getAttribute("data-name")||""; }
  function secs(c){ return parseFloat(c.getAttribute("data-seconds"))||0; }
  function order(c){ return parseFloat(c.getAttribute("data-order"))||0; }
  function byName(a,b){ return name(a).localeCompare(name(b),undefined,{numeric:true,sensitivity:"base"}); }
  var cmp={
    "default":   function(a,b){ return order(a)-order(b); },
    "name":      byName,
    "name-desc": function(a,b){ return byName(b,a); },
    "dur":       function(a,b){ return secs(a)-secs(b); },
    "dur-desc":  function(a,b){ return secs(b)-secs(a); }
  };
  function apply(mode){
    if(!cmp[mode]) mode="default";
    cards.sort(cmp[mode]);
    var frag=document.createDocumentFragment();
    cards.forEach(function(c){ frag.appendChild(c); });
    grid.appendChild(frag);
    Array.prototype.forEach.call(seg.querySelectorAll("button[data-sort]"),function(b){
      b.classList.toggle("on", b.getAttribute("data-sort")===mode);
    });
    try{ localStorage.setItem("av:sort", mode); }catch(e){}
  }
  seg.addEventListener("click",function(e){
    var b=e.target.closest("button[data-sort]"); if(!b) return;
    apply(b.getAttribute("data-sort"));
  });
  var saved="default";
  try{ saved=localStorage.getItem("av:sort")||"default"; }catch(e){}
  apply(saved);
})();
</script>
"""


def card(c, i=0):
    title = html.escape(c["series"])
    link = f'courses/{c["slug"]}/player/'
    src = (f'<a class="src" href="{html.escape(c["seriesUrl"])}" target="_blank" '
           f'rel="noopener">課程頁 ↗</a>') if c.get("seriesUrl") else ""
    return f"""
    <div class="card" data-slug="{html.escape(c['slug'])}" data-playable="{c['videos']}"
         data-name="{html.escape(c['series'])}" data-seconds="{c['seconds']}" data-order="{i}">
      <a class="cardlink" href="{link}" aria-label="{title} — 進入播放器"></a>
      <div class="chead" style="background:linear-gradient(135deg,{c['c1']},{c['c2']})">
        <div class="logo">{html.escape(c['logo'])}</div>
        <div class="chead-txt">
          <h2>{title}</h2>
          <p>{html.escape(c['instructor'])}{(' · ' + html.escape(c['platform'])) if c['platform'] else ''}</p>
        </div>
      </div>
      <div class="cbody">
        <div class="chips">
          <span class="chip">{c['sections']} 章</span>
          <span class="chip">{c['lessons']} 課</span>
          <span class="chip dur">時長 {html.escape(c['totalDuration'])}</span>
          <span class="chip done" hidden>✓ 課程已完成</span>
        </div>
        <div class="cov">
          <div class="covrow watch"><span class="lbl">已觀看</span><div class="bar"><span class="wfill" style="width:0"></span></div><div class="barlab"><b class="wn">0</b> / {c['videos']}</div></div>
          <div class="covrow"><span class="lbl">影片</span>{bar(c['videos'], c['lessons'], c['c2'])}</div>
          <div class="covrow"><span class="lbl">雙語字幕</span>{bar(c['bilingual'], c['lessons'], '#12b76a')}</div>
          <div class="covrow"><span class="lbl">英文轉錄</span>{bar(c['en'], c['lessons'], '#94a3b8')}</div>
        </div>
      </div>
      <div class="cfoot">
        <span class="enter">進入播放器 →</span>
        {src}
      </div>
    </div>"""


def main():
    courses = collect()
    total_lessons = sum(c["lessons"] for c in courses)
    total_bilingual = sum(c["bilingual"] for c in courses)
    total_videos = sum(c["videos"] for c in courses)
    total_seconds = sum(c["seconds"] for c in courses)
    total_time = fmt_dur(total_seconds)

    cards = "\n".join(card(c, i) for i, c in enumerate(courses)) or \
        '<div class="empty">尚無課程。將課程資料夾放進 <code>courses/</code> 後執行 <code>python3 scripts/build_index.py</code>。</div>'

    page = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Academind 課程 · 中英雙語動態字幕</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%237c5cff'/%3E%3Cpath d='M12 9l12 7-12 7z' fill='white'/%3E%3C/svg%3E">
<style>
  :root{{
    --bg:#f6f7f9; --panel:#fff; --ink:#101828; --muted:#667085;
    --line:#e4e7ec; --shadow:0 1px 2px rgba(16,24,40,.05),0 12px 32px -12px rgba(16,24,40,.14);
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
    font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang TC","Noto Sans TC",sans-serif;
    -webkit-font-smoothing:antialiased}}
  .wrap{{max-width:1120px;margin:0 auto;padding:56px 24px 80px}}
  header.top{{margin-bottom:34px}}
  header.top .eyebrow{{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:700;
    letter-spacing:.04em;text-transform:uppercase;color:#7c5cff;background:#efeaff;
    padding:5px 11px;border-radius:999px;margin-bottom:16px}}
  header.top h1{{margin:0 0 10px;font-size:34px;letter-spacing:-.02em;line-height:1.2}}
  header.top p{{margin:0;color:var(--muted);font-size:15.5px;max-width:680px}}
  .stats{{display:flex;gap:26px;margin-top:22px;flex-wrap:wrap}}
  .stats div{{font-size:13px;color:var(--muted)}}
  .stats b{{display:block;font-size:22px;color:var(--ink);letter-spacing:-.01em}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(340px,100%),1fr));gap:22px}}
  .card{{position:relative;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--line);
    border-radius:18px;overflow:hidden;text-decoration:none;color:inherit;
    box-shadow:var(--shadow);transition:transform .16s ease,box-shadow .16s ease}}
  .cardlink{{position:absolute;inset:0;z-index:1;border-radius:18px}}
  .cardlink:focus-visible{{outline:2px solid #7c5cff;outline-offset:2px}}
  .card .src{{position:relative;z-index:2}}
  .card:hover{{transform:translateY(-3px);box-shadow:0 2px 4px rgba(16,24,40,.06),0 22px 44px -16px rgba(16,24,40,.24)}}
  .chead{{display:flex;gap:14px;align-items:center;padding:20px 20px 18px;color:#fff}}
  .logo{{width:52px;height:52px;border-radius:13px;background:rgba(255,255,255,.22);
    display:grid;place-items:center;font-weight:800;font-size:19px;flex:0 0 auto;
    backdrop-filter:blur(4px);border:1px solid rgba(255,255,255,.35)}}
  .chead-txt{{min-width:0}}
  .chead h2{{margin:0 0 3px;font-size:17.5px;line-height:1.3;letter-spacing:-.01em;overflow-wrap:anywhere}}
  .chead p{{margin:0;font-size:12.5px;opacity:.92}}
  .cbody{{padding:18px 20px 6px;flex:1}}
  .chips{{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:16px}}
  .chip{{font-size:12px;font-weight:600;color:#475467;background:#f2f4f7;border:1px solid var(--line);
    padding:3px 10px;border-radius:999px}}
  .chip.dur{{color:#5b45e0;background:#f4f1ff;border-color:#e3dcff;font-variant-numeric:tabular-nums}}
  .chip.done{{color:#fff;background:#12b76a;border-color:#12b76a}}
  .cov{{display:flex;flex-direction:column;gap:11px}}
  .covrow{{display:flex;align-items:center;gap:10px}}
  .lbl{{width:66px;flex:0 0 auto;font-size:12px;color:var(--muted);font-weight:600}}
  .bar{{flex:1;height:7px;border-radius:999px;background:#eef0f3;overflow:hidden}}
  .bar span{{display:block;height:100%;border-radius:999px}}
  .barlab{{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;min-width:52px;text-align:right}}
  .barlab b{{color:var(--ink)}}
  .covrow.watch .lbl{{color:#0a7a45}}
  .covrow.watch .wfill{{display:block;height:100%;border-radius:999px;background:#12b76a;transition:width .25s ease}}
  .card.allwatched{{border-color:#bfe9d3}}
  .cfoot{{display:flex;align-items:center;justify-content:space-between;
    padding:14px 20px;border-top:1px solid var(--line);margin-top:14px}}
  .enter{{font-weight:700;font-size:13.5px;color:#7c5cff}}
  .src{{font-size:12.5px;color:var(--muted);text-decoration:none}}
  .src:hover{{color:var(--ink)}}
  .empty{{grid-column:1/-1;padding:40px;text-align:center;color:var(--muted);background:var(--panel);
    border:1px dashed var(--line);border-radius:16px}}
  code{{background:#f2f4f7;border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:12.5px}}
  footer{{margin-top:44px;font-size:12.5px;color:var(--muted);line-height:1.8;
    border-top:1px solid var(--line);padding-top:20px}}
  footer a{{color:#7c5cff;text-decoration:none}}

  /* ---------- sort bar ---------- */
  .sortbar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 18px}}
  .sortbar .sortlabel{{font-size:12.5px;color:var(--muted);font-weight:700;letter-spacing:.02em}}
  .seg{{display:inline-flex;flex-wrap:wrap;gap:4px;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;padding:4px}}
  .seg button{{border:0;background:transparent;color:var(--muted);font-size:12.5px;font-weight:600;
    padding:6px 11px;border-radius:8px;cursor:pointer;font-family:inherit;white-space:nowrap}}
  .seg button:hover{{color:var(--ink);background:#f2f4f7}}
  .seg button.on{{background:#7c5cff;color:#fff}}

  /* ---------- responsive: 100% and 150% browser zoom ---------- */
  @media (max-width:1024px){{
    .wrap{{padding:40px 20px 64px}}
    header.top h1{{font-size:30px}}
    .stats{{gap:20px}}
    .grid{{gap:18px}}
  }}
  @media (max-width:760px){{
    .wrap{{padding:28px 16px 56px}}
    header.top h1{{font-size:25px}}
    header.top p{{font-size:14.5px}}
    .stats b{{font-size:19px}}
    .grid{{grid-template-columns:1fr;gap:14px}}
    .chead{{padding:16px 16px 14px}}
    .cbody{{padding:14px 16px 4px}}
    .cfoot{{padding:12px 16px}}
  }}
  @media (max-width:420px){{
    .wrap{{padding:20px 12px 48px}}
    header.top h1{{font-size:22px}}
    .logo{{width:44px;height:44px;font-size:16px}}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <span class="eyebrow">Academind · 個人學習筆記</span>
    <h1>中英雙語動態字幕課程庫</h1>
    <p>課程影片取自公開鏡像並於本機播放；英文字幕由 AssemblyAI 轉錄，翻譯為繁體中文，
       字幕以詞級時間軸驅動卡拉OK／彈跳／淡入等動態效果。</p>
    <div class="stats">
      <div><b>{len(courses)}</b>課程</div>
      <div><b>{total_lessons}</b>課</div>
      <div><b>{total_time}</b>總時長</div>
      <div><b>{total_videos}</b>部影片已下載</div>
      <div><b>{total_bilingual}</b>課雙語字幕</div>
      <div id="statWatch" hidden><b id="statWatchV">0</b>課已觀看 · <span id="statDone">0</span> 門課程已完成</div>
    </div>
  </header>

  <div class="sortbar">
    <span class="sortlabel">排序</span>
    <div class="seg" id="sortSeg" role="group" aria-label="課程排序方式">
      <button type="button" data-sort="default" class="on">預設</button>
      <button type="button" data-sort="name">名稱 A→Z</button>
      <button type="button" data-sort="name-desc">名稱 Z→A</button>
      <button type="button" data-sort="dur">時長 短→長</button>
      <button type="button" data-sort="dur-desc">時長 長→短</button>
    </div>
  </div>

  <div class="grid">
{cards}
  </div>

  <footer>
    本機瀏覽：於專案根目錄執行 <code>python3 scripts/serve.py --open</code>，
    首頁即為本課程列表。<br>
    影片與原始課程內容版權屬 Academind 與原作者所有，僅供個人學習用途，請勿再散布。
  </footer>
</div>
""" + WATCH_JS + SORT_JS + "\n</body>\n</html>\n"
    out = os.path.join(ROOT, "index.html")
    open(out, "w", encoding="utf-8").write(page)
    print(f"wrote {os.path.relpath(out, ROOT)} — {len(courses)} course(s), "
          f"{total_lessons} lessons, {total_time} total:")
    for c in courses:
        print(f"  {c['slug']:<52} {c['lessons']:>4} lessons · "
              f"{c['totalDuration']:>7} · {c['videos']:>3} videos · "
              f"{c['bilingual']:>3} bilingual")


if __name__ == "__main__":
    main()
