#!/usr/bin/env python3
"""Transcribe lecture audio with AssemblyAI and write English SRT.

Flow per lecture:
  audio/<slug>.m4a  --upload-->  https://api.assemblyai.com/v2/upload
                    --create-->  /v2/transcript  (language_code=en, punctuate,
                                 disfluencies off, word timestamps on)
                    --poll-->    /v2/transcript/<id>  until completed
  -> data/srt/en/<slug>.srt   (plus raw JSON in _scratch/asr/<slug>.json)

The API key is read from --key, $ASSEMBLYAI_API_KEY, or _scratch/assemblyai.key.

Usage:
  python3 scripts/asr.py                 # every lecture that has audio and no SRT
  python3 scripts/asr.py --only 1 2 3
  python3 scripts/asr.py --force
  python3 scripts/asr.py --concurrency 3
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

API = "https://api.assemblyai.com/v2"


def api_key(explicit=None):
    if explicit:
        return explicit.strip()
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        return os.environ["ASSEMBLYAI_API_KEY"].strip()
    p = "_scratch/assemblyai.key"
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    sys.exit("no AssemblyAI key: pass --key, set $ASSEMBLYAI_API_KEY, "
             "or write it to _scratch/assemblyai.key")


def _req(url, key, data=None, method=None, headers=None, raw=False, timeout=300):
    h = {"authorization": key}
    if headers:
        h.update(headers)
    body = data
    if data is not None and not raw:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _req_retry(url, key, data=None, method=None, raw=False, tries=8):
    """POST/GET helper that backs off on 429/5xx.

    Running several courses in parallel can exceed the AssemblyAI account
    concurrency limit; without this a 429 is returned straight to the caller
    and the lecture is silently left without a transcript.
    """
    last = None
    for i in range(tries):
        try:
            return _req(url, key, data=data, method=method, raw=raw)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 5 * (i + 1)))
                continue
            raise
    raise last


def upload(path, key):
    with open(path, "rb") as f:
        blob = f.read()
    r = _req_retry(f"{API}/upload", key, data=blob, method="POST", raw=True)
    return r["upload_url"]


def srt_ts(ms):
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(words, max_gap=520, max_chars=44):
    """Group words into cues, breaking on a pause or a length budget.

    The thresholds are tuned to mimic the course's own caption track
    (~2 s / ~40 characters per cue), which reads far better than the long
    run-on cues AssemblyAI emits by default.
    """
    cues, cur = [], []
    for w in words:
        if cur:
            gap = w["start"] - cur[-1]["end"]
            text_len = sum(len(x["text"]) + 1 for x in cur) + len(w["text"])
            if gap >= max_gap or text_len > max_chars:
                cues.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cues.append(cur)

    out = []
    for i, c in enumerate(cues, 1):
        text = "".join(
            (" " if j and not c[j]["text"].startswith(("'", ",", ".", "!", "?", ":", ";"))
             and not c[j - 1]["text"].endswith(("-", "'")) else "") + c[j]["text"]
            for j in range(len(c))).strip()
        out.append(f"{i}\n{srt_ts(c[0]['start'])} --> {srt_ts(c[-1]['end'])}\n{text}\n")
    return "\n".join(out)


def transcribe(slug, key, force=False, poll=6):
    src = None
    for ext in ("m4a", "mp3", "mp4", "wav"):
        p = f"audio/{slug}.{ext}"
        if os.path.exists(p):
            src = p
            break
    if src is None:
        return "no-audio", 0
    out = f"data/srt/en/{slug}.srt"
    if os.path.exists(out) and os.path.getsize(out) > 0 and not force:
        return "cached", sum(1 for _ in open(out, encoding="utf-8")) // 4

    os.makedirs("_scratch/asr", exist_ok=True)
    try:
        url = upload(src, key)
        job = _req_retry(f"{API}/transcript", key, method="POST", data={
            "audio_url": url,
            "language_code": "en",
            "punctuate": True,
            "format_text": True,
            "disfluencies": False,
        })
        tid = job["id"]
        while True:
            st = _req_retry(f"{API}/transcript/{tid}", key)
            if st["status"] == "completed":
                break
            if st["status"] == "error":
                return "error: " + str(st.get("error"))[:160], 0
            time.sleep(poll)
    except urllib.error.HTTPError as e:
        return f"http {e.code}: {e.read().decode('utf-8', 'replace')[:160]}", 0

    json.dump(st, open(f"_scratch/asr/{slug}.json", "w", encoding="utf-8"),
              ensure_ascii=False)
    words = st.get("words") or []
    if not words:
        return "no words returned", 0
    srt = to_srt(words)
    os.makedirs("data/srt/en", exist_ok=True)
    open(out, "w", encoding="utf-8").write(srt)
    return "ok", srt.count("--> ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key")
    ap.add_argument("--only", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()
    key = api_key(args.key)

    lib = json.load(open("data/lessons.json", encoding="utf-8"))
    todo = [l for l in lib["lessons"]
            if (not args.only or l["number"] in args.only)
            and os.path.exists(f"audio/{l['slug']}.m4a")]
    print(f"transcribing {len(todo)} lectures (concurrency {args.concurrency})")

    lock = threading.Lock()
    counter = {"n": 0}

    def work(l):
        status, cues = transcribe(l["slug"], key, args.force)
        with lock:
            counter["n"] += 1
            l["asr"] = status
            l["cueCount"] = cues or l.get("cueCount")
            print(f"  [{counter['n']:2d}/{len(todo)}] {status:>8} "
                  f"#{l['number']:2d} {l['slug']} ({cues} cues)", flush=True)

    threads = []
    for l in todo:
        while sum(t.is_alive() for t in threads) >= args.concurrency:
            time.sleep(0.4)
        t = threading.Thread(target=work, args=(l,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()

    json.dump(lib, open("data/lessons.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    ok = sum(1 for l in todo if l.get("asr") == "ok")
    print(f"\ntranscribed {ok}/{len(todo)}")


if __name__ == "__main__":
    main()
