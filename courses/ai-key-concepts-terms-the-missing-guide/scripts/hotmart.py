#!/usr/bin/env python3
"""Hotmart player + HLS subtitle extraction for Academind (Teachable) courses.

How the chain works (reverse-engineered, verified against the live site):

  1. A lecture page embeds  <div class='hotmart_video_player private-hotmart-video'
       data-attachment-id='124718696' data-course-id='3008094' data-lecture-id='66409091'>
  2. GET /api/v2/hotmart/private_video?attachment_id=<id>
       -> { video_id, signature, teachable_application_key, duration, status }
     (the v2 path is the live one; v1 returns 404)
  3. https://player.hotmart.com/embed/<video_id>?signature=..&token=<app_key>
       -> SSR page whose __NEXT_DATA__ holds applicationData
          with mediaAssets[0].url = signed HLS master playlist
  4. master.m3u8 lists  #EXT-X-MEDIA:TYPE=SUBTITLES ... URI="...-textstream_eng=1000.m3u8"
     (English is the only language Academind publishes)
  5. that media playlist lists 6s WebVTT segments -> concatenate -> full English VTT

Everything from step 3 onwards is public once the signature is known; only
step 2 needs the learner's session for non-preview lectures.
"""
import json
import os
import re
import urllib.parse
import urllib.request

SITE = "https://pro.academind.com"
PLAYER = "https://player.hotmart.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
CACHE = "_scratch/cache"


def _get(url, cookie=None, referer=None, timeout=45):
    h = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    if cookie:
        h["Cookie"] = cookie
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _cache_path(name):
    os.makedirs(CACHE, exist_ok=True)
    return os.path.join(CACHE, name)


# ---------------------------------------------------------------- step 1 + 2
def lecture_attachment(lecture_url, cookie=None):
    """Return (attachment_id or None, locked_bool) for a lecture page."""
    page = _get(lecture_url, cookie)
    m = re.search(r"data-attachment-id='(\d+)'", page)
    locked = "Enroll in Course to Unlock" in page or "drip-lecture-locked" in page
    return (m.group(1) if m else None), locked


def resolve_video(attachment_id, cookie=None):
    """attachment_id -> dict(videoId, signature, applicationKey, duration)."""
    url = f"{SITE}/api/v2/hotmart/private_video?attachment_id={attachment_id}"
    h = {"User-Agent": UA, "Accept": "application/json",
         "X-Requested-With": "XMLHttpRequest", "Referer": SITE + "/"}
    if cookie:
        h["Cookie"] = cookie
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=45) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    if "video_id" not in d:
        raise RuntimeError(f"unexpected private_video response: {str(d)[:200]}")
    return {
        "videoId": d["video_id"],
        "signature": d["signature"],
        "applicationKey": d["teachable_application_key"],
        "duration": d.get("duration"),
        "status": d.get("status"),
        "userCode": d.get("user_code") or "",
    }


# -------------------------------------------------------------------- step 3
def embed_url(video_id, signature, application_key, user=None):
    q = {"signature": signature}
    if application_key:
        q["token"] = application_key
    if user:
        q["user"] = user
    return f"{PLAYER}/embed/{video_id}?" + urllib.parse.urlencode(q)


def player_data(video_id, signature, application_key, user=None, use_cache=True):
    """Fetch the player's applicationData (cached, since signatures are short-lived)."""
    cp = _cache_path(f"appdata_{video_id}.json")
    if use_cache and os.path.exists(cp):
        try:
            d = json.load(open(cp, encoding="utf-8"))
            if d.get("mediaAssets"):
                return d
        except Exception:  # noqa: BLE001
            pass
    url = embed_url(video_id, signature, application_key, user)
    page = _get(url, referer=SITE + "/")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        raise RuntimeError("player embed returned no __NEXT_DATA__")
    pp = json.loads(m.group(1))["props"]["pageProps"]
    if "error" in pp or "applicationData" not in pp:
        raise RuntimeError(f"player embed error: {pp.get('error')}")
    ad = pp["applicationData"]
    json.dump(ad, open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return ad


def master_url(appdata):
    for a in appdata.get("mediaAssets", []):
        if a.get("contentType") == "application/x-mpegURL" or ".m3u8" in a.get("url", ""):
            return a["url"]
    raise RuntimeError("no HLS asset in applicationData")


# ------------------------------------------------------------- steps 4 + 5
def subtitle_tracks(appdata):
    """[(lang, name, absolute_url)] from the master playlist."""
    master = master_url(appdata)
    base = master.rsplit("/", 1)[0] + "/"
    text = _get(master, referer=PLAYER + "/")
    out = []
    for line in text.splitlines():
        if not line.startswith("#EXT-X-MEDIA"):
            continue
        if "TYPE=SUBTITLES" not in line:
            continue
        uri = re.search(r'URI="([^"]+)"', line)
        if not uri:
            continue
        lang = (re.search(r'LANGUAGE="([^"]+)"', line) or [None, "?"])[1]
        name = (re.search(r'NAME="([^"]+)"', line) or [None, lang])[1]
        out.append((lang, name, urllib.parse.urljoin(base, uri.group(1))))
    return out


def fetch_vtt(track_url):
    """Concatenate every WebVTT segment of a subtitle media playlist."""
    base = track_url.rsplit("/", 1)[0] + "/"
    pl = _get(track_url, referer=PLAYER + "/")
    segs = [l.strip() for l in pl.splitlines() if l.strip() and not l.startswith("#")]
    chunks = [_get(urllib.parse.urljoin(base, s), referer=PLAYER + "/") for s in segs]
    return "\n".join(chunks)


# ------------------------------------------------------------------ VTT -> SRT
TS = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*"
                r"(\d+):(\d{2}):(\d{2})[.,](\d{1,3})")


def _sec(g):
    return (int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3].ljust(3, "0")) / 1000)


def vtt_cues(vtt_text):
    """[(start, end, text)] merged across segments, de-duplicated at boundaries."""
    cues = []
    for block in re.split(r"\n\s*\n", vtt_text.replace("\r\n", "\n")):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if not lines or lines[0].startswith(("WEBVTT", "X-TIMESTAMP-MAP", "NOTE")):
            lines = [l for l in lines if not l.startswith(("WEBVTT", "X-TIMESTAMP-MAP", "NOTE"))]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        m = TS.search(lines[ti])
        if not m:
            continue
        g = m.groups()
        start, end = _sec(g[:4]), _sec(g[4:])
        text = " ".join(lines[ti + 1:]).strip()
        text = re.sub(r"<[^>]+>", "", text).strip()
        if not text:
            continue
        if cues and text == cues[-1][2] and abs(start - cues[-1][1]) < 0.05:
            cues[-1] = (cues[-1][0], max(cues[-1][1], end), text)  # stitch split cue
            continue
        cues.append((start, end, text))
    return cues


def srt_timestamp(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def cues_to_srt(cues):
    out = []
    for i, (s, e, t) in enumerate(cues, 1):
        out.append(f"{i}\n{srt_timestamp(s)} --> {srt_timestamp(e)}\n{t}\n")
    return "\n".join(out)


def english_srt(video_id, signature, application_key, user=None):
    """Full chain: video id + signature -> (srt_text, cue_count)."""
    ad = player_data(video_id, signature, application_key, user)
    tracks = subtitle_tracks(ad)
    if not tracks:
        return None, 0, []
    lang, name, url = tracks[0]
    cues = vtt_cues(fetch_vtt(url))
    return cues_to_srt(cues), len(cues), [{"lang": l, "name": n} for l, n, _ in tracks]


def main():
    """CLI: python3 scripts/hotmart.py <attachment_id> [cookie] [out.srt]"""
    import sys
    att = sys.argv[1]
    cookie = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else "_scratch/en.srt"
    info = resolve_video(att, cookie)
    print("resolved:", {k: v for k, v in info.items() if k != "signature"})
    srt, n, tracks = english_srt(info["videoId"], info["signature"],
                                 info["applicationKey"])
    print(f"tracks={tracks} cues={n}")
    open(out, "w", encoding="utf-8").write(srt or "")
    print("wrote", out)


if __name__ == "__main__":
    main()
