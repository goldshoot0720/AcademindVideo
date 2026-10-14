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
    "deno-the-complete-introduction": ("#111827", "#06b6d4", "DN"),
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


def watch_slug(lib, folder):
    """Key the player writes into localStorage. It is the last segment of
    seriesUrl, which is not always the folder name."""
    url = (lib.get("seriesUrl") or "").strip().rstrip("/")
    tail = url.split("/")[-1] if url else ""
    return tail or folder


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
        lesson_rows = []
        for lesson in lessons:
            lesson_slug = lesson.get("slug") or ""
            has_video = bool(lesson_slug and os.path.exists(
                os.path.join(d, "video", f"{lesson_slug}.mp4")))
            lesson_rows.append({
                "n": lesson.get("number") or 0,
                "slug": lesson_slug,
                "title": lesson.get("title") or "",
                "section": lesson.get("sectionTitle") or "",
                "duration": lesson.get("duration") or "",
                "video": 1 if has_video else 0,
            })
        courses.append({
            "slug": slug,
            "watch": watch_slug(lib, slug),
            "lessonRows": lesson_rows,
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
# Paints the per-card "已觀看" row from av:watched, and exports / imports a
# CSV of every lecture (已播放 / 未播放, plus the resume point).
PROGRESS_JS = r"""
<script>
(function(){
  var WATCH_KEY="av:watched", LAST_KEY="av:last";
  var HEADS=["課程代碼","課程名稱","課號","單元代碼","單元標題","章節","時長","有影片","狀態","觀看時間","播放進度秒"];
  var ALIAS={
    course:["course_slug","課程代碼","watch_slug"],
    lesson:["lesson_slug","單元代碼","slug"],
    status:["status","狀態"],
    video:["has_video","有影片"],
    watchedAt:["watched_at","觀看時間"],
    position:["position_sec","播放進度秒","position"],
    title:["lesson_title","單元標題"],
    courseTitle:["course_title","課程名稱"],
    number:["lesson_number","課號"]
  };

  function readJson(key, fallback){
    try{
      var j=JSON.parse(localStorage.getItem(key)||"");
      return (j&&typeof j==="object")?j:fallback;
    }catch(e){ return fallback; }
  }
  function readWatched(){ return readJson(WATCH_KEY, {}); }
  function readLast(){ return readJson(LAST_KEY, null); }
  function catalog(){
    var el=document.getElementById("lessonCatalog");
    if(!el) return [];
    try{ var j=JSON.parse(el.textContent||"[]"); return Array.isArray(j)?j:[]; }
    catch(e){ return []; }
  }
  function pad(n){ return (n<10?"0":"")+n; }
  function fmtTime(ms){
    var d=new Date(Number(ms));
    if(!ms || isNaN(d.getTime())) return "";
    return d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate())+" "+pad(d.getHours())+":"+pad(d.getMinutes())+":"+pad(d.getSeconds());
  }
  function parseTime(s){
    s=String(s||"").trim();
    if(!s) return 0;
    if(/^\d+$/.test(s)){ var n=Number(s); return n<1e12 ? n*1000 : n; }
    var t=Date.parse(s.replace(" ","T"));
    return isNaN(t)?0:t;
  }
  function statusKind(s){
    s=String(s||"").trim().toLowerCase();
    if(!s) return "";
    if(["已播放","已觀看","played","watched","yes","y","true","1"].indexOf(s)>=0) return "played";
    if(["未播放","未觀看","unplayed","unwatched","no","n","false","0"].indexOf(s)>=0) return "unplayed";
    if(["無影片","novideo","none"].indexOf(s)>=0) return "novideo";
    return "";
  }
  function videoFlag(s){
    s=String(s||"").trim().toLowerCase();
    if(!s) return "";
    if(["0","無","no","n","false","無影片"].indexOf(s)>=0) return 0;
    if(["1","有","yes","y","true"].indexOf(s)>=0) return 1;
    return "";
  }
  function csvCell(v){
    v=v==null?"":String(v);
    if(/[",\n\r]/.test(v)) return '"'+v.replace(/"/g,'""')+'"';
    return v;
  }
  function parseCsv(text){
    text=String(text||"").replace(/^\uFEFF/,"").replace(/\r\n/g,"\n").replace(/\r/g,"\n");
    var rows=[], row=[], cur="", q=false;
    for(var i=0;i<text.length;i++){
      var ch=text[i];
      if(q){
        if(ch==='"'){
          if(text[i+1]==='"'){ cur+='"'; i++; }
          else q=false;
        } else cur+=ch;
      } else if(ch==='"') q=true;
      else if(ch===","){ row.push(cur); cur=""; }
      else if(ch==="\n"){ row.push(cur); rows.push(row); row=[]; cur=""; }
      else cur+=ch;
    }
    if(cur.length||row.length){ row.push(cur); rows.push(row); }
    if(rows.length && rows[rows.length-1].every(function(c){ return c===""; })) rows.pop();
    return rows;
  }
  function colIndex(header){
    var idx={};
    Object.keys(ALIAS).forEach(function(key){
      idx[key]=-1;
      for(var i=0;i<header.length;i++){
        if(ALIAS[key].indexOf(header[i])>=0){ idx[key]=i; break; }
      }
    });
    return idx;
  }
  function cell(row, i){ return i>=0 && i<row.length ? String(row[i]||"").trim() : ""; }

  function paintWatch(){
    var all=readWatched();
    var byWatch={};
    catalog().forEach(function(c){ byWatch[c.slug]=c; });
    var cards=document.querySelectorAll(".card[data-slug]");
    var totW=0, doneCourses=0, seen={};
    Array.prototype.forEach.call(cards,function(card){
      var slug=card.getAttribute("data-slug");
      var key=card.getAttribute("data-watch")||slug;
      if(seen[key]) return; seen[key]=1;
      var playable=parseInt(card.getAttribute("data-playable"),10)||0;
      var m=(all&&all[key])||{}, n=0, cat=byWatch[key];
      if(cat){
        cat.lessons.forEach(function(l){ if(l.video && m[l.slug]) n++; });
      } else {
        for(var k in m){ if(Object.prototype.hasOwnProperty.call(m,k)) n++; }
        if(playable && n>playable) n=playable;
      }
      var row=card.querySelector(".covrow.watch");
      var wn=row&&row.querySelector(".wn"), wf=row&&row.querySelector(".wfill");
      if(wn) wn.textContent=n;
      if(wf) wf.style.width=(playable?Math.round(100*n/playable):0)+"%";
      if(row) row.classList.toggle("has", n>0);
      var done=playable && n>=playable;
      card.classList.toggle("allwatched", done);
      var db=card.querySelector(".chip.done"); if(db) db.hidden=!done;
      if(done) doneCourses++;
      totW+=n;
    });
    var sv=document.getElementById("statWatchV"); if(sv) sv.textContent=totW;
    var sc=document.getElementById("statDone"); if(sc) sc.textContent=doneCourses;
    var box=document.getElementById("statWatch"); if(box) box.hidden=totW<=0;
    var total=0;
    catalog().forEach(function(c){
      (c.lessons||[]).forEach(function(l){ if(l.video) total++; });
    });
    if(!total){
      var seenT={};
      Array.prototype.forEach.call(cards,function(card){
        var key=card.getAttribute("data-watch")||card.getAttribute("data-slug");
        if(seenT[key]) return; seenT[key]=1;
        total+=parseInt(card.getAttribute("data-playable"),10)||0;
      });
    }
    var nEl=document.getElementById("donePosN"), pEl=document.getElementById("donePosP");
    if(nEl) nEl.textContent=totW+"/"+total;
    if(pEl){
      var pct=total?Math.floor(totW/total*10000)/100:0;
      pEl.textContent=pct.toFixed(2)+"%";
    }
    var pos=document.getElementById("donePos");
    if(pos) pos.title="課程完成度：已看完 "+totW+" 堂有字幕的課，共 "+total+" 堂";
  }

  function buildCsv(){
    var all=readWatched(), last=readLast(), lines=[HEADS.join(",")], played=0, rows=0, seen={};
    catalog().forEach(function(c){
      var m=all[c.slug]||{};
      (c.lessons||[]).forEach(function(l){
        if(!l.slug) return;
        seen[c.slug+"\n"+l.slug]=1;
        var at=m[l.slug]||0;
        var status = !l.video ? "無影片" : (at ? "已播放" : "未播放");
        if(at && l.video) played++;
        var pos="";
        if(last && last.course===c.slug && last.lesson===l.slug && last.t!=null && last.t!=="") pos=String(Math.round(Number(last.t)||0));
        lines.push([c.slug, c.title, l.n, l.slug, l.title, l.section, l.duration, l.video?1:0, status, at?fmtTime(at):"", pos].map(csvCell).join(","));
        rows++;
      });
    });
    Object.keys(all).forEach(function(course){
      var m=all[course]||{};
      Object.keys(m).forEach(function(lesson){
        if(seen[course+"\n"+lesson]) return;
        played++;
        rows++;
        lines.push([course, "", "", lesson, "", "", "", 1, "已播放", fmtTime(m[lesson]), ""].map(csvCell).join(","));
      });
    });
    return {text: lines.join("\r\n")+"\r\n", rows: rows, played: played};
  }

  function showMsg(text, kind){
    var el=document.getElementById("xferMsg");
    if(!el) return;
    el.hidden=false;
    el.textContent=text;
    el.className="xfermsg"+(kind?(" "+kind):"");
  }

  function exportCsv(){
    var built=buildCsv();
    var blob=new Blob(["\uFEFF"+built.text], {type:"text/csv;charset=utf-8"});
    var a=document.createElement("a");
    var url=URL.createObjectURL(blob);
    var d=new Date();
    a.href=url;
    a.download="academind-playback-"+d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate())+".csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function(){ URL.revokeObjectURL(url); }, 1500);
    showMsg("已匯出 "+built.rows+" 列，其中 "+built.played+" 課已播放", "ok");
  }

  function parseImport(text){
    var table=parseCsv(text);
    if(!table.length) return {error:"CSV 是空的"};
    var header=table[0].map(function(h){ return String(h||"").trim().toLowerCase(); });
    var col=colIndex(header);
    if(col.course<0 || col.lesson<0) return {error:"CSV 需要「課程代碼」和「單元代碼」欄位"};
    var watchOf={};
    catalog().forEach(function(c){
      watchOf[c.slug]=c.slug;
      if(c.folder) watchOf[c.folder]=c.slug;
    });
    var played=0, unplayed=0, skipped=0, position=null;
    var changes=[];
    for(var r=1;r<table.length;r++){
      var row=table[r];
      if(!row || row.every(function(c){ return String(c||"").trim()===""; })) continue;
      var courseRaw=cell(row, col.course), lesson=cell(row, col.lesson);
      if(!courseRaw || !lesson){ skipped++; continue; }
      var course=watchOf[courseRaw]||courseRaw;
      var kind=statusKind(cell(row, col.status));
      var video=videoFlag(cell(row, col.video));
      if(!kind){ skipped++; continue; }
      if(kind==="played" && video!==0){
        var at=parseTime(cell(row, col.watchedAt))||Date.now();
        changes.push({course:course, lesson:lesson, on:true, at:at});
        played++;
      } else if(kind==="unplayed"){
        changes.push({course:course, lesson:lesson, on:false});
        unplayed++;
      } else {
        changes.push({course:course, lesson:lesson, on:false});
      }
      var posRaw=cell(row, col.position);
      if(posRaw!=="" && isFinite(Number(posRaw))){
        position={
          course:course,
          courseTitle:cell(row, col.courseTitle),
          lesson:lesson,
          lessonNumber:parseInt(cell(row, col.number),10)||0,
          title:cell(row, col.title),
          t:Math.max(0, Number(posRaw)||0),
          at:Date.now()
        };
      }
    }
    if(!changes.length && !position) return {error:"CSV 沒有可套用的播放狀態"};
    return {played:played, unplayed:unplayed, skipped:skipped, changes:changes, position:position};
  }

  function applyImport(parsed){
    var all=readWatched();
    (parsed.changes||[]).forEach(function(ch){
      var m=all[ch.course];
      if(!m || typeof m!=="object") m={};
      if(ch.on) m[ch.lesson]=ch.at;
      else delete m[ch.lesson];
      if(Object.keys(m).length) all[ch.course]=m;
      else delete all[ch.course];
    });
    try{ localStorage.setItem(WATCH_KEY, JSON.stringify(all)); }catch(e){}
    if(parsed.position){
      try{ localStorage.setItem(LAST_KEY, JSON.stringify(parsed.position)); }catch(e){}
    }
  }

  function importCsv(text){
    var parsed=parseImport(text);
    if(parsed.error){ showMsg(parsed.error, "bad"); return; }
    var note="這份 CSV 記載 "+parsed.played+" 課已播放、"+parsed.unplayed+" 課未播放。匯入後會更新這些課的狀態。";
    if(parsed.position) note+="並回到「"+((parsed.position.title)||parsed.position.lesson)+"」。";
    if(!window.confirm(note+"繼續？")){ showMsg("已取消匯入", ""); return; }
    applyImport(parsed);
    paintWatch();
    var msg="已匯入 "+parsed.played+" 課已播放、"+parsed.unplayed+" 課未播放";
    if(parsed.skipped) msg+="，略過 "+parsed.skipped+" 列";
    if(parsed.position) msg+="，已記錄播放進度";
    showMsg(msg, "ok");
  }

  var exportBtn=document.getElementById("exportCsv");
  var importBtn=document.getElementById("importCsv");
  var file=document.getElementById("importCsvFile");
  if(exportBtn) exportBtn.addEventListener("click", exportCsv);
  if(importBtn && file){
    importBtn.addEventListener("click", function(){ file.click(); });
    file.addEventListener("change", function(){
      var f=file.files && file.files[0];
      file.value="";
      if(!f) return;
      var reader=new FileReader();
      reader.onload=function(){ importCsv(String(reader.result||"")); };
      reader.onerror=function(){ showMsg("無法讀取檔案", "bad"); };
      reader.readAsText(f);
    });
  }
  paintWatch();
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
    <div class="card" data-slug="{html.escape(c['slug'])}" data-watch="{html.escape(c['watch'])}" data-playable="{c['videos']}"
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
    catalog = [{
        "slug": c["watch"],
        "folder": c["slug"],
        "title": c["series"],
        "lessons": c["lessonRows"],
    } for c in courses]
    catalog_json = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    catalog_json = catalog_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

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
  /* Overall completion, above the title: "112/1001  11.18%".
     The percent is cut at 2 decimals (not rounded) so 112/1001 stays 11.18. */
  .donepos{{display:flex;align-items:baseline;gap:10px;margin:0 0 14px;
    font-variant-numeric:tabular-nums;letter-spacing:-.03em;line-height:1}}
  .donepos .frac{{font-size:28px;font-weight:800;color:var(--ink)}}
  .donepos .pct{{font-size:22px;font-weight:800;color:#7c5cff}}
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
  .sortbar .grow{{flex:1}}
  .xfer{{display:inline-flex;gap:8px;flex-wrap:wrap}}
  .xfer button{{border:1px solid var(--line);background:var(--panel);color:var(--ink);
    font:700 12.5px/1.2 inherit;padding:7px 12px;border-radius:10px;cursor:pointer;white-space:nowrap}}
  .xfer button:hover{{border-color:#7c5cff;color:#7c5cff}}
  .xfer button.primary{{background:#7c5cff;border-color:#7c5cff;color:#fff}}
  .xfer button.primary:hover{{filter:brightness(1.06);color:#fff}}
  .xfermsg{{margin:-6px 0 16px;font-size:12.5px;color:var(--muted)}}
  .xfermsg.ok{{color:#0a7a45}}
  .xfermsg.bad{{color:#b42318}}

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
    .donepos .frac{{font-size:24px}}
    .donepos .pct{{font-size:18px}}
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
    <div class="donepos" id="donePos" title="已看完的有字幕影片 / 全部有字幕影片">
      <span class="frac" id="donePosN">–/–</span><span class="pct" id="donePosP"></span>
    </div>
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
    <span class="grow"></span>
    <div class="xfer">
      <button type="button" class="primary" id="exportCsv">匯出 CSV</button>
      <button type="button" id="importCsv">匯入 CSV</button>
      <input type="file" id="importCsvFile" accept=".csv,text/csv" hidden>
    </div>
  </div>
  <p class="xfermsg" id="xferMsg" hidden></p>

  <div class="grid">
{cards}
  </div>

  <footer>
    本機瀏覽：於專案根目錄執行 <code>python3 scripts/serve.py --open</code>，
    首頁即為本課程列表。<br>
    影片與原始課程內容版權屬 Academind 與原作者所有，僅供個人學習用途，請勿再散布。
  </footer>
</div>
""" + '<script id="lessonCatalog" type="application/json">' + catalog_json + "</script>\n" + PROGRESS_JS + SORT_JS + "\n</body>\n</html>\n"
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
