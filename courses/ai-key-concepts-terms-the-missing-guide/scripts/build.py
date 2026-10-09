#!/usr/bin/env python3
"""Build bilingual subtitle assets from EN segments + zh-Hant translations.

Outputs:
  data/bilingual/<slug>.json     EN+ZH segments with word-level timings
  data/srt/bilingual/<slug>.srt  two-line bilingual SRT (EN over ZH)
  data/ass/<slug>.ass            animated ASS (karaoke sweep + fade), dual line
  player/data.js                 window.SERIES_DATA = {...} for the web player
  player/standalone.html         single-file player (hls.js + data inlined)
"""
import json
import os
import re

CJK = r"\u3400-\u9fff\u3000-\u303f\uff00-\uffef"

# Mainland-Chinese wording -> Traditional Chinese (Taiwan) equivalents, plus
# Pi / coding-agent vocabulary. Longest-first so compounds beat their prefixes.
GLOSSARY = [
    ("應用程序接口", "應用程式介面"), ("應用程序", "應用程式"),
    ("構造函數", "建構子"), ("中間件", "中介層"), ("回調函數", "回呼函數"),
    ("數據庫", "資料庫"), ("服務器", "伺服器"), ("字符串", "字串"),
    ("布爾值", "布林值"), ("字節", "位元組"), ("數組", "陣列"),
    ("對象", "物件"), ("函數", "函式"), ("回調", "回呼"), ("變量", "變數"),
    ("布爾", "布林"), ("默認值", "預設值"), ("默認", "預設"), ("信息", "資訊"),
    ("打印", "列印"), ("內存", "記憶體"), ("線程", "執行緒"), ("進程", "行程"),
    ("返回", "回傳"), ("加載", "載入"), ("保存", "儲存"), ("搜索", "搜尋"),
    ("緩存", "快取"), ("隊列", "佇列"), ("堆棧", "堆疊"),
    ("模板", "樣板"), ("校驗", "驗證"), ("響應", "回應"), ("頭部", "標頭"),
    ("異步", "非同步"), ("併發", "並行"), ("並發", "並行"), ("哈希", "雜湊"),
    ("指針", "指標"), ("引用", "參照"), ("硬盤", "硬碟"), ("網絡", "網路"),
    ("鏈接", "連結"), ("支持", "支援"), ("屏幕", "螢幕"), ("視頻", "影片"),
    ("音頻", "音訊"), ("文件夾", "資料夾"), ("光標", "游標"), ("數據", "資料"),
    ("客戶端", "用戶端"), ("插件", "外掛"), ("代碼", "程式碼"), ("編程", "程式設計"),
    ("程序", "程式"), ("軟件", "軟體"), ("硬件", "硬體"), ("項目", "專案"),
    ("日誌", "紀錄"), ("調試", "除錯"), ("斷點", "中斷點"), ("異常", "例外"),
    ("枚舉", "列舉"), ("接口", "介面"), ("字段", "欄位"), ("常量", "常數"),
    ("全局", "全域"), ("遞歸", "遞迴"), ("事務", "交易"), ("循環", "迴圈"),
    ("文件", "檔案"), ("類型", "型別"), ("用戶", "使用者"), ("選項卡", "分頁"),
    ("組件", "元件"), ("構建", "建構"), ("源代碼", "原始碼"),
    # Pi / agent vocabulary
    ("代碼庫", "程式庫"), ("代碼代理", "編碼代理"), ("命令行", "命令列"),
    ("終端", "終端機"), ("會話", "工作階段"), ("沙盒", "沙箱"),
    ("提示詞", "提示語"), ("上下文", "上下文"), ("權限", "權限"),
    ("擴展", "擴充功能"), ("配置", "設定"), ("配置檔", "設定檔"),
    ("默認配置", "預設設定"), ("自動完成", "自動補全"),
]
GLOSSARY.sort(key=lambda kv: -len(kv[0]))


def apply_glossary(text):
    for a, b in GLOSSARY:
        if a in text:
            text = text.replace(a, b)
    return text


def chunk_zh(text: str):
    """Split Chinese text into short chunks (~2 chars) for word-level highlight."""
    parts = re.findall(rf"[A-Za-z0-9.+#\-]+|[{CJK}]+|[^\s]", text)
    out = []
    for p in parts:
        if re.fullmatch(rf"[{CJK}]+", p):
            for i in range(0, len(p), 2):
                out.append(p[i:i + 2])
        else:
            out.append(p)
    return out or [text]


def word_timings(text, start, end, lang="en"):
    tokens = text.split() if lang == "en" else chunk_zh(text)
    if not tokens:
        return []
    weights = [(len(t) + 1) if lang == "en" else (len(t) + 0.6) for t in tokens]
    total = sum(weights) or 1
    t = start
    out = []
    for tok, w in zip(tokens, weights):
        d = (end - start) * w / total
        out.append({"w": tok, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    if out:
        out[-1]["end"] = end
    return out


def ts_srt(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ts_ass(sec):
    cs = int(round(sec * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(t):
    return t.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", "\\N")


def karaoke(words):
    out = []
    for w in words:
        cs = max(1, int(round((w["end"] - w["start"]) * 100)))
        out.append(f"{{\\k{cs}}}{ass_escape(w['w'])}")
    return "".join(out)


ASS_HEADER = """[Script Info]
; Bilingual dynamic subtitles - Pi: The Practical Guide
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: EN,Arial,46,&H00FFFFFF,&H00999999,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,2,60,60,205,1
Style: ZH,Noto Sans CJK TC,60,&H0000E5FF,&H00707070,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,120,1
Style: ENTop,Arial,40,&H00E8E8E8,&H00808080,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,60,60,250,1
Style: Title,Arial,52,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,60,60,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(lesson, segs):
    lines = [ASS_HEADER]
    t_end = min(3.0, segs[0]["start"]) if segs else 3.0
    title = f"{lesson['number']:02d}  {lesson['title']}"
    lines.append(
        f"Dialogue: 0,{ts_ass(0)},{ts_ass(max(2.4, t_end))},Title,,0,0,0,,"
        f"{{\\fad(400,600)}}{ass_escape(title)}")
    for s in segs:
        if not s.get("zh"):
            continue
        en_k = karaoke(s.get("enWords", []))
        zh_k = karaoke(s.get("zhWords", []))
        st, en = ts_ass(s["start"]), ts_ass(s["end"])
        lines.append(f"Dialogue: 0,{st},{en},EN,,0,0,0,,{{\\fad(120,120)}}{en_k}")
        lines.append(f"Dialogue: 0,{st},{en},ZH,,0,0,0,,"
                     f"{{\\fad(120,120)\\t(0,180,\\fscx106\\fscy106)}}{zh_k}")
    return "\n".join(lines) + "\n"


def main():
    lib = json.load(open("data/lessons.json", encoding="utf-8"))
    for d in ("data/bilingual", "data/srt/bilingual", "data/ass", "player"):
        os.makedirs(d, exist_ok=True)

    # attach the Bilibili mirror mapping (video file + part page) to each lecture
    bili = {}
    if os.path.exists("data/bili.json"):
        b = json.load(open("data/bili.json", encoding="utf-8"))
        for p in b["parts"]:
            if p.get("lectureNumber"):
                bili[p["lectureNumber"]] = p

    series_lessons = []
    done = 0
    for l in lib["lessons"]:
        slug = l["slug"]
        seg_path = f"data/segments/{slug}.json"
        segs = json.load(open(seg_path, encoding="utf-8")) if os.path.exists(seg_path) else []

        zh = None
        zh_path = f"data/translations/zh-Hant/{slug}.json"
        if os.path.exists(zh_path) and segs:
            z = json.load(open(zh_path, encoding="utf-8"))
            if len(z) == len(segs):
                zh = [apply_glossary(t) for t in z]
            else:
                print(f"  ! {slug}: translation length {len(z)} != {len(segs)}, skipped")

        out_segs, srt_blocks = [], []
        for i, s in enumerate(segs):
            rec = {"start": s["start"], "end": s["end"], "en": s["en"]}
            rec["enWords"] = word_timings(s["en"], s["start"], s["end"], "en")
            if zh:
                rec["zh"] = zh[i]
                rec["zhWords"] = word_timings(zh[i], s["start"], s["end"], "zh")
            out_segs.append(rec)
            body = s["en"] + (f"\n{zh[i]}" if zh else "")
            srt_blocks.append(f"{i+1}\n{ts_srt(s['start'])} --> {ts_srt(s['end'])}\n{body}\n")

        if segs:
            json.dump(out_segs, open(f"data/bilingual/{slug}.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            open(f"data/srt/bilingual/{slug}.srt", "w", encoding="utf-8").write("\n".join(srt_blocks))

        meta = {k: l.get(k) for k in
                ("slug", "number", "title", "duration", "section", "sectionTitle",
                 "lessonUrl", "videoId", "attachmentId", "lectureId")}
        p = bili.get(l["number"])
        meta["biliPage"] = p["page"] if p else None
        meta["videoFile"] = (f"video/{slug}.mp4"
                             if os.path.exists(f"video/{slug}.mp4") else None)
        meta["hasEn"] = bool(segs)
        meta["hasZh"] = bool(zh)
        meta["cueCount"] = len(out_segs)
        # word timings are derived client-side in the player; keep the payload lean
        meta["segments"] = [
            {"start": s["start"], "end": s["end"], "en": s["en"],
             **({"zh": s["zh"]} if s.get("zh") else {})}
            for s in out_segs
        ]
        series_lessons.append(meta)

        if zh:
            open(f"data/ass/{slug}.ass", "w", encoding="utf-8").write(build_ass(l, out_segs))
            done += 1
            print(f"  OK {slug} ({len(out_segs)} cues, bilingual)")
        elif segs:
            print(f"  -- {slug} ({len(out_segs)} cues, EN only - no translation yet)")
        else:
            print(f"  .. {slug} (no subtitles yet)")

    data = {
        "series": lib["series"],
        "seriesUrl": lib["seriesUrl"],
        "instructor": lib["instructor"],
        "platform": lib.get("platform"),
        "generatedBy": "AcademindVideo bilingual subtitle pipeline",
        "lessons": series_lessons,
    }
    with open("player/data.js", "w", encoding="utf-8") as f:
        f.write("// Auto-generated by scripts/build.py - do not edit by hand.\n")
        f.write("window.SERIES_DATA = ")
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")

    html = open("player/index.html", encoding="utf-8").read()
    inlined = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    standalone = html.replace(
        '<script src="data.js"></script>',
        '<script>window.SERIES_DATA = ' + inlined + ';</script>')
    hls_path = "player/vendor/hls.min.js"
    if os.path.exists(hls_path):
        hls_js = open(hls_path, encoding="utf-8").read()
        standalone = standalone.replace('<script src="vendor/hls.min.js"></script>',
                                        '<script>' + hls_js + '</script>')
    open("player/standalone.html", "w", encoding="utf-8").write(standalone)
    print(f"Wrote player/standalone.html ({len(standalone)//1024} KB, self-contained)")
    print(f"\n{len(series_lessons)} lessons in player data, {done} fully bilingual")


if __name__ == "__main__":
    main()
