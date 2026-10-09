#!/usr/bin/env python3
"""Render preview frames showing the bilingual dynamic subtitles.

Since the bundled ffmpeg has no libass, this uses Pillow to compose a
realistic "video frame" (fake editor + subtitle overlay) so you can see
exactly how the EN + ZH dynamic subtitles look.

Usage:  python3 scripts/preview.py [slug] [seconds] [out.png]
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
CJK_FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
LAT_FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
LAT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
MONO = "/System/Library/Fonts/SFNSMono.ttf"

ACCENT = (139, 123, 255)
YELLOW = (255, 212, 81)
PAST = (185, 178, 255)


def font(path, size, idx=0):
    for p in (path, LAT_FONT, CJK_FONT):
        try:
            return ImageFont.truetype(p, size, index=idx)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default()


def chunk_zh(text):
    import re
    parts = re.findall(r"[A-Za-z0-9.+#\-]+|[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]+|[^\s]", text)
    out = []
    for p in parts:
        if all("\u3400" <= ch <= "\uffef" for ch in p) and p:
            for i in range(0, len(p), 2):
                out.append(p[i:i + 2])
        else:
            out.append(p)
    return out or [text]


def word_times(tokens, start, end, lang):
    if not tokens:
        return []
    weights = [(len(t) + 1) if lang == "en" else (len(t) + 0.6) for t in tokens]
    total = sum(weights) or 1
    t, out = start, []
    for tok, w in zip(tokens, weights):
        d = (end - start) * w / total
        out.append((tok, t, t + d))
        t += d
    if out:
        out[-1] = (out[-1][0], out[-1][1], end)
    return out


def draw_line(draw, words, t, cx, y, fnt, base_col, space):
    """Draw a centred line of words, highlighting the active one."""
    widths = [draw.textlength(w, font=fnt) for w, _, _ in words]
    total = sum(widths) + space * (len(words) - 1)
    x = cx - total / 2
    for (w, s, e), wd in zip(words, widths):
        if t < s:
            col = tuple(int(c * 0.45) for c in base_col)
        elif t > e:
            col = PAST
        else:
            col = YELLOW
        if col == YELLOW:
            draw.text((x + 2, y + 2), w, font=fnt, fill=(0, 0, 0))
        draw.text((x, y), w, font=fnt, fill=col)
        x += wd + space
    return y


def fake_editor(draw, img, title):
    x0, y0, x1, y1 = 300, 150, 1620, 720
    draw.rounded_rectangle([x0, y0, x1, y1], 18, fill=(17, 21, 30), outline=(38, 45, 60), width=2)
    draw.rounded_rectangle([x0, y0, x1, y0 + 46], 18, fill=(23, 28, 40))
    draw.rectangle([x0, y0 + 30, x1, y0 + 46], fill=(23, 28, 40))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        draw.ellipse([x0 + 22 + i * 22, y0 + 16, x0 + 34 + i * 22, y0 + 28], fill=c)
    f = font(MONO, 24)
    draw.text((x0 + 110, y0 + 12), title, font=f, fill=(150, 160, 180))

    lines = [
        ("$ ", "pi", "", "                    # start a Pi session"),
        ("", "", "", ""),
        ("› ", "Add a /health route to the Express server", "", ""),
        ("", "", "", ""),
        ("⏺ ", "Reading src/server.ts", "", ""),
        ("⏺ ", "Editing src/server.ts", "", "  (+6 −0)"),
        ("⏺ ", "Running npm test", "", "  ✓ 12 passing"),
        ("", "", "", ""),
        ("› ", "/tree", "", "                   # inspect the session"),
        ("", "", "", ""),
        ("› ", "commit this", "", ""),
    ]
    colors = [(122, 214, 168), (130, 170, 255), (199, 146, 234), (150, 160, 180)]
    lf = font(MONO, 26)
    yy = y0 + 76
    for ln in lines:
        xx = x0 + 46
        draw.text((x0 + 20, yy), "", font=lf, fill=(90, 98, 115))
        for tok, col in zip(ln, colors):
            if tok:
                draw.text((xx, yy), tok, font=lf, fill=col)
            xx += draw.textlength(tok, font=lf)
        yy += 44


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "01-welcome-to-the-course"
    sec = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    out = sys.argv[3] if len(sys.argv) > 3 else f"preview/{slug}-{sec:g}s.png"

    segs = json.load(open(f"data/bilingual/{slug}.json", encoding="utf-8"))
    seg = next((s for s in segs if s["start"] <= sec <= s["end"]), segs[0])
    lesson = next((l for l in json.load(open("data/lessons.json", encoding="utf-8"))["lessons"]
                   if l["slug"] == slug), {"title": slug, "number": ""})

    img = Image.new("RGB", (W, H), (10, 13, 19))
    d = ImageDraw.Draw(img)
    # vertical gradient
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(10 + 14 * k), int(13 + 17 * k), int(19 + 26 * k)))
    # glow
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.10, -H * 0.55, W * 0.90, H * 0.60], fill=85)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    img.paste(Image.new("RGB", (W, H), (74, 62, 158)), (0, 0), glow)

    fake_editor(d, img, f"{lesson.get('number','')}  {lesson['title']}")

    # chip
    chip_f = font(LAT_FONT, 24)
    label = f"Pi: The Practical Guide  ·  {lesson.get('number','')} {lesson['title']}"
    d.rounded_rectangle([300, 92, 300 + d.textlength(label, font=chip_f) + 36, 138], 23,
                        fill=(30, 34, 48), outline=(52, 58, 78))
    d.text((318, 104), label, font=chip_f, fill=(170, 180, 200))

    # subtitles
    t = sec - seg["start"]
    en_words = word_times(seg["en"].split(), seg["start"], seg["end"], "en")
    zh_words = word_times(chunk_zh(seg["zh"]), seg["start"], seg["end"], "zh") if seg.get("zh") else []
    en_f = font(LAT_BOLD, 40)
    zh_f = font(CJK_FONT, 56)

    # scrim
    scrim = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    for i in range(300):
        sd.line([(0, i), (W, i)], fill=(0, 0, 0, int(150 * (i / 300) ** 1.4)))
    img.paste(Image.alpha_composite(img.crop((0, H - 300, W, H)).convert("RGBA"), scrim).convert("RGB"),
              (0, H - 300))

    draw_line(d, en_words, sec, W / 2, H - 240, en_f, (238, 241, 246), 14)
    if zh_words:
        draw_line(d, zh_words, sec, W / 2, H - 172, zh_f, (255, 255, 255), 6)

    # progress bar
    total = segs[-1]["end"]
    d.rounded_rectangle([300, H - 74, W - 300, H - 68], 3, fill=(60, 66, 84))
    d.rounded_rectangle([300, H - 74, 300 + (W - 600) * (sec / total), H - 68], 3, fill=ACCENT)

    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
