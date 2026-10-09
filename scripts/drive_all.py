#!/usr/bin/env python3
"""Drive the full bilingual-subtitle pipeline for every course under courses/.

Three phases, each fully resumable (every stage skips work already on disk):

  1. download   yt-dlp + ffmpeg, parallel across courses (COURSE_WORKERS)
  2. asr        one global thread pool over every lecture of every course
                (ASR_WORKERS, keeps under the AssemblyAI concurrency limit)
  3. build      per course: parse_srt -> translate -> fix_empty -> build

Progress is written to _drive/status.json (machine readable) and appended to
_drive/drive.log.  Re-running after an interruption continues where it stopped.

Usage:
  python3 scripts/drive_all.py                 # everything
  python3 scripts/drive_all.py --phase download
  python3 scripts/drive_all.py --only clean-code htmx-the-practical-guide
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSES = os.path.join(ROOT, "courses")
DRIVE = os.path.join(ROOT, "_drive")
PY = sys.executable
API = "https://api.assemblyai.com/v2"

COURSE_WORKERS = int(os.environ.get("COURSE_WORKERS", "4"))
ASR_WORKERS = int(os.environ.get("ASR_WORKERS", "4"))
ASR_POLL = 6

_log_lock = threading.Lock()
_status_lock = threading.Lock()
STATUS = {}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _log_lock:
        print(line, flush=True)
        with open(os.path.join(DRIVE, "drive.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def save_status():
    with _status_lock:
        tmp = os.path.join(DRIVE, "status.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(STATUS, f, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(DRIVE, "status.json"))


def course_dirs(only=None):
    out = []
    for name in sorted(os.listdir(COURSES)):
        d = os.path.join(COURSES, name)
        if not os.path.isdir(d):
            continue
        if not os.path.exists(os.path.join(d, "course.json")):
            continue
        if not os.path.exists(os.path.join(d, "data", "lessons.json")):
            continue
        if only and name not in only:
            continue
        out.append(d)
    return out


def lessons(d):
    return json.load(open(os.path.join(d, "data", "lessons.json"), encoding="utf-8"))["lessons"]


def run(cwd, args, timeout=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


# ----------------------------------------------------------------- phase 1
def phase_download(d):
    slug = os.path.basename(d)
    r = run(d, [PY, "scripts/download.py"], timeout=3600 * 6)
    tail = (r.stdout or "").strip().splitlines()
    last = tail[-1] if tail else (r.stderr or "")[-200:]
    with _status_lock:
        STATUS.setdefault(slug, {})["download"] = last
    log(f"download {slug}: {last}")


# ----------------------------------------------------------------- phase 2
def api_key(d):
    p = os.path.join(d, "_scratch", "assemblyai.key")
    if os.path.exists(p):
        return open(p, encoding="utf-8").read().strip()
    env = os.environ.get("ASSEMBLYAI_API_KEY")
    if env:
        return env.strip()
    raise SystemExit("no AssemblyAI key")


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


def srt_ts(ms):
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(words, max_gap=520, max_chars=44):
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


def _req_retry(url, key, data=None, method=None, raw=False, tries=6):
    """POST/PUT helper that backs off on 429 (concurrency/rate limit)."""
    last = None
    for i in range(tries):
        try:
            return _req(url, key, data=data, method=method, raw=raw)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                time.sleep(min(30, 3 * (i + 1)))
                continue
            raise
    raise last


def transcribe_one(d, slug, key):
    src = os.path.join(d, "audio", f"{slug}.m4a")
    out = os.path.join(d, "data", "srt", "en", f"{slug}.srt")
    if not os.path.exists(src):
        return "no-audio"
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return "cached"
    try:
        with open(src, "rb") as f:
            blob = f.read()
        up = _req_retry(f"{API}/upload", key, data=blob, method="POST", raw=True)
        job = _req_retry(f"{API}/transcript", key, method="POST", data={
            "audio_url": up["upload_url"], "language_code": "en",
            "punctuate": True, "format_text": True, "disfluencies": False})
        tid = job["id"]
        while True:
            st = _req(f"{API}/transcript/{tid}", key)
            if st["status"] == "completed":
                break
            if st["status"] == "error":
                return "error: " + str(st.get("error"))[:120]
            time.sleep(ASR_POLL)
    except urllib.error.HTTPError as e:
        return f"http {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"err {type(e).__name__}"
    words = st.get("words") or []
    if not words:
        return "no-words"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(to_srt(words))
    return "ok"


def phase_asr(dirs):
    key = api_key(dirs[0])
    tasks = []
    for d in dirs:
        for l in lessons(d):
            tasks.append((d, l["slug"]))
    # skip already done
    todo = [(d, s) for (d, s) in tasks
            if not os.path.exists(os.path.join(d, "data", "srt", "en", f"{s}.srt"))]
    log(f"asr: {len(todo)} lectures to transcribe ({len(tasks) - len(todo)} cached)")
    done = [0]
    lock = threading.Lock()

    def work(d, slug):
        slug_course = os.path.basename(d)
        r = transcribe_one(d, slug, key)
        with lock:
            done[0] += 1
            STATUS.setdefault(slug_course, {}).setdefault("asr", {})[slug] = r
            if done[0] % 10 == 0 or r != "ok":
                log(f"asr [{done[0]}/{len(todo)}] {slug_course}/{slug} -> {r}")
                save_status()

    threads = []
    for d, s in todo:
        while sum(t.is_alive() for t in threads) >= ASR_WORKERS:
            time.sleep(0.3)
        t = threading.Thread(target=work, args=(d, s))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    log("asr phase done")
    save_status()


# ----------------------------------------------------------------- phase 3
def phase_build(d):
    slug = os.path.basename(d)
    for step in ("parse_srt.py", "translate.py", "fix_empty.py", "build.py"):
        r = run(d, [PY, f"scripts/{step}"], timeout=3600 * 4)
        if r.returncode != 0 and step != "fix_empty.py":
            log(f"build {slug}: {step} rc={r.returncode} {(r.stderr or '')[-200:]}")
    n_b = len([f for f in os.listdir(os.path.join(d, "data", "srt", "bilingual"))
               if f.endswith(".srt")]) if os.path.isdir(os.path.join(d, "data", "srt", "bilingual")) else 0
    with _status_lock:
        STATUS.setdefault(slug, {})["build"] = f"{n_b} bilingual"
    log(f"build {slug}: {n_b} bilingual SRT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["download", "asr", "build", "all"], default="all")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    os.makedirs(DRIVE, exist_ok=True)
    dirs = course_dirs(args.only)
    log(f"=== drive_all start: {len(dirs)} courses, phase={args.phase} ===")

    if args.phase in ("download", "all"):
        log(f"--- phase 1: download ({COURSE_WORKERS} courses in parallel) ---")
        threads = []
        for d in dirs:
            while sum(t.is_alive() for t in threads) >= COURSE_WORKERS:
                time.sleep(0.5)
            t = threading.Thread(target=phase_download, args=(d,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        save_status()

    if args.phase in ("asr", "all"):
        log("--- phase 2: ASR (global pool) ---")
        phase_asr(dirs)

    if args.phase in ("build", "all"):
        log(f"--- phase 3: parse + translate + build ---")
        for d in dirs:
            phase_build(d)
        save_status()

    log("=== drive_all done ===")
    save_status()


if __name__ == "__main__":
    main()
