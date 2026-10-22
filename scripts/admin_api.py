#!/usr/bin/env python3
"""Admin API for the AcademindVideo local server.

Served by scripts/serve.py under /admin/api/. All responses are JSON.

    GET  /admin/api/state              -> tool availability + course summaries
    GET  /admin/api/course?slug=...    -> one course with lessons + local file state
    GET  /admin/api/sources?slug=...   -> video files under courses/<slug>/video
    GET  /admin/api/jobs               -> queued/running/finished jobs with logs
    POST /admin/api/download           -> queue a yt-dlp job   {slug, mode, cookies}
    POST /admin/api/split              -> queue an ffmpeg job  {slug, source, mode, ...}
    POST /admin/api/jobs/cancel        -> {id}
    POST /admin/api/jobs/clear         -> drop finished jobs

Jobs run one at a time on a background worker thread, so yt-dlp and ffmpeg
never fight over bandwidth/CPU and every step stays visible in the UI.

Security notes:
  * the server binds 127.0.0.1 only (see serve.py);
  * every slug is validated against the real courses/ directory;
  * every path is resolved and must stay inside courses/<slug>/video/;
  * subprocesses are started with argument lists, never a shell.
"""
import glob
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COURSES_DIR = os.path.join(ROOT, "courses")

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_LOG = 1200

# yt-dlp emits one progress line per update; keep only the latest so the log
# stays readable instead of scrolling away every real event.
PROGRESS_LINE_RE = re.compile(r"^\[download\]\s+[\d.]+%")

# Errors people actually hit, with a concrete next step for each.
FAILURE_HINTS = [
    ("Failed to decrypt with DPAPI",
     "Chrome/Edge 的 cookie 受 Windows 應用程式綁定加密保護，yt-dlp 無法解密。"
     "請改用 Firefox（--cookies-from-browser firefox）或手動匯出的 cookies.txt。"),
    ("Unable to extract initial state",
     "Bilibili 回傳的是風控頁（通常伴隨 api 412），沒有有效登入 cookie 時就會這樣。"
     "請改用「讀取瀏覽器 cookies」（此機 Firefox 可用）或 cookies.txt，並確認該 IP 未被風控。"),
    ("HTTP Error 412",
     "Bilibili 風控 412：需要登入後的 cookies，或換一個網路環境（VPN／機房 IP 特別容易被攔）。"),
    ("Sign in to confirm", "此來源需要登入，請提供 cookies。"),
    ("Private video", "此影片為私人或已下架。"),
]


# --------------------------------------------------------------- tools
def _which(name, patterns=()):
    hit = shutil.which(name)
    if hit:
        return hit
    for pattern in patterns:
        found = sorted(glob.glob(os.path.expandvars(pattern)))
        if found:
            return found[-1]
    return None


FFMPEG = _which("ffmpeg", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\ffmpeg*\bin\ffmpeg.exe"])
FFPROBE = _which("ffprobe", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\ffmpeg*\bin\ffprobe.exe"])
YTDLP = _which("yt-dlp", [r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*\yt-dlp*\yt-dlp.exe"])


# --------------------------------------------------------------- helpers
def parse_duration(text):
    """'1:22' -> 82.0, '1:02:03' -> 3723.0, junk -> 0.0"""
    if not text:
        return 0.0
    try:
        parts = [float(p) for p in str(text).strip().split(":")]
    except ValueError:
        return 0.0
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def list_slugs():
    if not os.path.isdir(COURSES_DIR):
        return []
    return sorted(
        d for d in os.listdir(COURSES_DIR)
        if SLUG_RE.match(d) and os.path.isdir(os.path.join(COURSES_DIR, d))
    )


def load_course(slug):
    """Full course record: metadata, lessons with absolute time ranges, file state."""
    base = os.path.join(COURSES_DIR, slug)
    meta = _read_json(os.path.join(base, "course.json"), {}) or {}
    doc = _read_json(os.path.join(base, "data", "lessons.json"), {}) or {}

    lessons = []
    cursor = 0.0
    for i, raw in enumerate(doc.get("lessons") or []):
        seconds = parse_duration(raw.get("duration"))
        lesson_slug = raw.get("slug") or "%02d-lesson" % (i + 1)
        rel = "video/%s.mp4" % lesson_slug
        path = os.path.join(base, rel.replace("/", os.sep))
        exists = os.path.isfile(path)
        lessons.append({
            "index": i + 1,
            "number": raw.get("number") or i + 1,
            "slug": lesson_slug,
            "title": raw.get("title") or lesson_slug,
            "section": raw.get("section"),
            "sectionTitle": raw.get("sectionTitle"),
            "duration": raw.get("duration"),
            "seconds": round(seconds, 3),
            "start": round(cursor, 3),
            "end": round(cursor + seconds, 3),
            "lectureId": raw.get("lectureId"),
            "lectureUrl": raw.get("lessonUrl") or raw.get("lectureUrl"),
            "video": {
                "path": rel,
                "exists": exists,
                "size": os.path.getsize(path) if exists else 0,
            },
        })
        cursor += seconds

    # downloaded parts that have not been mapped to a lesson file yet
    parts = _scan_parts(base, lessons)
    for lesson in lessons:
        has_file = lesson["video"]["exists"]
        lesson["video"]["pending"] = None if has_file else parts.get(lesson["slug"])

    bv = meta.get("bv") or doc.get("bv")
    mirror = (meta.get("mirrorUrl") or doc.get("mirrorUrl") or "").strip()
    bilibili_url = "https://www.bilibili.com/video/%s/" % bv if bv else None
    return {
        "slug": slug,
        "series": meta.get("series") or doc.get("series") or slug,
        "instructor": meta.get("instructor"),
        "platform": meta.get("platform"),
        "seriesUrl": meta.get("seriesUrl") or doc.get("seriesUrl"),
        "courseId": meta.get("courseId") or doc.get("courseId"),
        "bv": bv,
        "mirrorUrl": mirror or None,
        "bilibiliUrl": bilibili_url,
        "downloadUrl": mirror or bilibili_url,
        "lessonCount": len(lessons),
        "totalSeconds": round(cursor, 3),
        "done": sum(1 for l in lessons if l["video"]["exists"]),
        "pending": sum(1 for l in lessons if l["video"].get("pending")),
        "lessons": lessons,
    }


def course_summary(slug):
    course = load_course(slug)
    course.pop("lessons")
    return course


def video_root(slug):
    return os.path.join(COURSES_DIR, slug, "video")


def _safe_video_path(slug, rel):
    """Resolve rel inside courses/<slug>/video/ or raise ValueError."""
    root = os.path.realpath(video_root(slug))
    target = os.path.realpath(os.path.join(root, rel.replace("\\", "/")))
    if target != root and not target.startswith(root + os.sep):
        raise ValueError("路徑超出課程 video 目錄")
    return target


def list_sources(slug):
    """Video files already available locally (top level and _source/)."""
    root = video_root(slug)
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.lower().endswith((".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv", ".ts")):
                continue
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            item = {"path": rel, "name": name, "size": os.path.getsize(full)}
            out.append(item)
    return out


MEDIA_EXT = (".mp4", ".mkv", ".webm", ".mov", ".m4v", ".flv", ".ts")
# "01-Udemy - ... p01 1. Welcome To This Cours.mp4" -> part 1, lecture 1
PART_RE = re.compile(r"\bp(\d+)\s+(\d+)\.\s*(.+)$", re.I)


def _is_media(name):
    low = name.lower()
    if not low.endswith(MEDIA_EXT):
        return False
    if low.endswith(".part"):
        return False
    # yt-dlp keeps per-stream fragments as name.f30080.mp4 while downloading
    if re.search(r"\.f\d+\.\w+$", low):
        return False
    return True


def _norm_title(text):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def _scan_parts(base, lessons):
    """Map lesson slug -> downloaded part file, using the lecture number in the name.

    The mirror is already split per lecture, so the right move is to match each
    part to its lesson instead of cutting a single long video by timestamps.
    """
    src_dir = os.path.join(base, "video", "_source")
    if not os.path.isdir(src_dir):
        return {}
    by_number, by_title = {}, {}
    for lesson in lessons:
        if lesson.get("number") is not None:
            by_number[str(lesson["number"])] = lesson
        by_title[_norm_title(lesson.get("title"))] = lesson

    found = {}
    for name in sorted(os.listdir(src_dir)):
        if not _is_media(name):
            continue
        m = PART_RE.search(name)
        if not m:
            continue
        lesson = by_number.get(str(int(m.group(2))))
        if lesson is None:            # filenames are truncated, so title is a fallback
            lesson = by_title.get(_norm_title(m.group(3)))
        if lesson:
            found.setdefault(lesson["slug"], name)
    return found


def _child_env():
    """Force UTF-8 on child processes.

    yt-dlp is a Python binary and writes its messages in the console code page
    (cp950/cp936 on Chinese Windows), which turns into mojibake once we decode
    the pipe as UTF-8. Forcing UTF-8 mode makes the logs readable.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def probe_duration(path):
    if not FFPROBE:
        return 0.0
    try:
        res = subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=20, env=_child_env(),
        )
        return float((res.stdout or "").strip() or 0)
    except Exception:
        return 0.0


# --------------------------------------------------------------- jobs
class Job:
    """A queued command sequence (yt-dlp download or a batch of ffmpeg cuts)."""

    def __init__(self, kind, title, steps, parallel=False, prepare=None):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.title = title
        self.steps = steps          # [(label, [argv...]), ...]
        self.parallel = parallel    # run every step at the same time
        self.prepare = prepare      # callable -> steps, executed inside the worker
        self.status = "queued"      # queued | running | done | failed | cancelled
        self.log = []
        self.progress = 0.0
        self.rc = None
        self.created = time.time()
        self.started = None
        self.finished = None
        self.cancelled = False
        self.proc = None
        self.procs = []
        self.step_progress = []
        self.step_items = []    # per connection: (current item, items in that chunk)
        self.done_steps = 0
        self.detail = ""        # human readable progress tail (speed / ETA / item)
        self.items_total = 0    # playlist length, when known
        self.item_index = 0     # current playlist item (1-based)
        self.item_pct = 0.0     # percent of the current item

    # -- logging ---------------------------------------------------
    def _log(self, line):
        if PROGRESS_LINE_RE.match(line) and self.log and PROGRESS_LINE_RE.match(self.log[-1]):
            self.log[-1] = line          # collapse consecutive progress updates
            return
        self.log.append(line)
        if len(self.log) > MAX_LOG:
            del self.log[: len(self.log) - MAX_LOG]

    def _parse_progress(self, line):
        m = re.search(r"Downloading item (\d+) of (\d+)", line)
        if m:
            self.item_index = int(m.group(1))
            self.items_total = int(m.group(2))
            self.item_pct = 0.0   # new item starts from zero, don't inherit the last one
            self.detail = "%d/%d" % (self.item_index, self.items_total)
            self._recompute()
            return

        m = re.search(
            r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+\s*[KMG]?i?B)"
            r"(?:\s+at\s+([\d.]+\s*[KMG]?i?B/s))?(?:\s+ETA\s+([\d:]+))?",
            line,
        )
        if not m:
            return
        self.item_pct = float(m.group(1))
        bits = []
        if self.items_total:
            bits.append("%d/%d" % (max(1, self.item_index), self.items_total))
        bits.append("%.1f%%" % self.item_pct)
        bits.append(m.group(2))
        if m.group(3):
            bits.append(m.group(3))
        if m.group(4):
            bits.append("ETA " + m.group(4))
        self.detail = " · ".join(bits)
        self._recompute()

    def _parse_progress_at(self, idx, line):
        """Per-connection progress for parallel downloads (no playlist indexing)."""
        m = re.search(r"Downloading item (\d+) of (\d+)", line)
        if m:
            self.step_items[idx] = (int(m.group(1)), int(m.group(2)))
            self._step_set(idx, 0.0)
            self.detail = "%d 條連線 · 第 %s/%s 個" % (
                len(self.step_progress), m.group(1), m.group(2))
            return

        m = re.search(
            r"\[download\]\s+([\d.]+)%\s+of\s+~?\s*([\d.]+\s*[KMG]?i?B)"
            r"(?:\s+at\s+([\d.]+\s*[KMG]?i?B/s))?(?:\s+ETA\s+([\d:]+))?",
            line,
        )
        if not m:
            return
        pct = float(m.group(1))
        self._step_set(idx, pct / 100.0)
        bits = [m.group(2)]
        if m.group(3):
            bits.append(m.group(3))
        if m.group(4):
            bits.append("ETA " + m.group(4))
        self.detail = "%d 條連線 · %s" % (len(self.step_progress), " · ".join(bits))

    def _step_set(self, idx, frac):
        """Store one connection's progress; completed items keep the bar monotonic."""
        item, total = self.step_items[idx] if idx < len(self.step_items) else (0, 0)
        if total:
            frac = ((max(0, item - 1)) + max(0.0, min(1.0, frac))) / total
        self.step_progress[idx] = max(0.0, min(1.0, frac))
        self.progress = min(0.999, sum(self.step_progress) / len(self.step_progress))

    def _recompute(self):
        """Overall progress: playlist items are equal-sized slices of the job."""
        if self.kind != "download":
            return
        if self.items_total:
            done = max(0, self.item_index - 1)
            self.progress = min(0.999, (done + self.item_pct / 100.0) / self.items_total)
        else:
            self.progress = min(0.999, self.item_pct / 100.0)

    # -- execution -------------------------------------------------
    def _spawn(self, cmd):
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=flags, env=_child_env(),
        )

    def run(self):
        if self.cancelled:
            self.status = "cancelled"
            self.finished = time.time()
            return
        self.status = "running"
        self.started = time.time()
        try:
            if self.prepare is not None:
                self._log("[..] 準備中（偵測分 P 數量）…")
                prepared = self.prepare()
                if prepared:
                    self.steps = prepared
                self._log("[..] 分成 %d 條連線" % max(1, len(self.steps)))
            if self.parallel and len(self.steps) > 1:
                self._run_parallel()
            else:
                self._run_sequential()
        except FileNotFoundError as exc:
            self.status = "failed"
            self._log("[X] 找不到執行檔：%s" % exc)
        except Exception as exc:  # noqa: BLE001 - surface anything to the UI
            self.status = "failed"
            self._log("[X] %s: %s" % (type(exc).__name__, exc))
        finally:
            if self.cancelled:
                self.status = "cancelled"
                self._log("[--] 已取消")
            elif self.status == "failed":
                self._explain_failure()
            self.finished = time.time()
            self.proc = None
            self.procs = []

    def _run_sequential(self):
        total = max(1, len(self.steps))
        for i, (label, cmd) in enumerate(self.steps):
            if self.cancelled:
                return
            self._log("")
            self._log("[%d/%d] %s" % (i + 1, total, label))
            if self.kind != "download":
                self.detail = "%d/%d" % (i + 1, total)
                self.progress = i / total
            if callable(cmd):
                # in-process step (file copy), no subprocess needed
                try:
                    cmd(self)
                except Exception as exc:  # noqa: BLE001
                    self.status = "failed"
                    self._log("[X] %s" % exc)
                    return
                self.rc = 0
            else:
                self._log("$ " + " ".join(cmd))
                self.proc = self._spawn(cmd)
                for line in self.proc.stdout:
                    self._log(line.rstrip())
                    self._parse_progress(line)
                self.rc = self.proc.wait()
            if self.cancelled:
                return
            if self.rc != 0:
                self.status = "failed"
                self._log("[X] 退出碼 %s" % self.rc)
                return
            self.done_steps = i + 1
            self.progress = self.done_steps / total
        self.status = "done"
        self.progress = 1.0
        self._log("[OK] 完成")

    def _run_parallel(self):
        total = len(self.steps)
        self.step_progress = [0.0] * total
        self.step_items = [(0, 0)] * total
        errors = []
        lock = threading.Lock()

        def worker(idx, label, cmd):
            try:
                with lock:
                    self._log("")
                    self._log("[連線 %d/%d] %s" % (idx + 1, total, label))
                    self._log("$ " + " ".join(cmd))
                proc = self._spawn(cmd)
                with lock:
                    self.procs.append(proc)
                for line in proc.stdout:
                    text = line.rstrip()
                    # progress already surfaces in the progress bar; with several
                    # connections interleaving it would drown the real events
                    if not PROGRESS_LINE_RE.match(text):
                        with lock:
                            self._log("[%d] %s" % (idx + 1, text))
                    self._parse_progress_at(idx, text)
                rc = proc.wait()
                if rc != 0 and not self.cancelled:
                    with lock:
                        errors.append("連線 %d 退出碼 %s" % (idx + 1, rc))
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append("連線 %d：%s" % (idx + 1, exc))

        threads = [threading.Thread(target=worker, args=(i, l, c), daemon=True)
                   for i, (l, c) in enumerate(self.steps)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if self.cancelled:
            self.status = "cancelled"
            return
        if errors:
            self.status = "failed"
            for err in errors:
                self._log("[X] " + err)
            return
        self.status = "done"
        self.progress = 1.0
        self._log("[OK] 完成")

    def _explain_failure(self):
        """Append actionable hints for the errors people actually hit."""
        blob = "\n".join(self.log)
        for needle, hint in FAILURE_HINTS:
            if needle in blob:
                self._log("[!] " + hint)

    def cancel(self):
        self.cancelled = True
        procs = list(self.procs)
        if self.proc is not None:
            procs.append(self.proc)
        for proc in procs:
            if proc is None or proc.poll() is not None:
                continue
            try:
                if os.name == "nt":
                    # yt-dlp spawns ffmpeg for merging; kill the whole tree
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                else:
                    proc.terminate()
            except Exception:
                pass
        if self.status == "queued":
            self.status = "cancelled"
            self.finished = time.time()

    def snapshot(self):
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "progress": round(self.progress, 4),
            "detail": self.detail,
            "itemsTotal": self.items_total,
            "itemIndex": self.item_index,
            "rc": self.rc,
            "created": self.created,
            "started": self.started,
            "finished": self.finished,
            "steps": len(self.steps),
            "doneSteps": self.done_steps,
            "log": self.log[-MAX_LOG:],
        }


_JOBS = {}
_QUEUE = queue.Queue()
_LOCK = threading.Lock()
_WORKER = None


def _worker_loop():
    while True:
        job = _QUEUE.get()
        try:
            job.run()
        finally:
            _QUEUE.task_done()


def _ensure_worker():
    global _WORKER
    with _LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_worker_loop, name="admin-jobs", daemon=True)
            _WORKER.start()


def submit(job):
    _ensure_worker()
    _JOBS[job.id] = job
    _QUEUE.put(job)
    return job


# --------------------------------------------------------------- actions
def _require_course(slug):
    if not slug or not SLUG_RE.match(slug) or slug not in list_slugs():
        raise ValueError("未知的課程：%s" % slug)
    return load_course(slug)


def _auth_args(cookies="", cookies_from_browser=""):
    """yt-dlp arguments for the credentials the user supplied."""
    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]
    if cookies:
        return ["--cookies", cookies]
    return []


def _resolve_target(course, mode, url="", lecture_id=None):
    """Work out which URL to hand to yt-dlp, plus a human label."""
    if mode == "custom":
        url = (url or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("自訂網址必須是完整的 http(s) 連結")
        return url, "下載自訂網址：%s" % url
    if mode == "lecture":
        lesson = next((l for l in course["lessons"] if str(l["lectureId"]) == str(lecture_id)), None)
        if not lesson or not lesson["lectureUrl"]:
            raise ValueError("找不到該單元的來源連結")
        return lesson["lectureUrl"], "下載單元：%s" % lesson["title"]
    if not course["downloadUrl"]:
        raise ValueError("此課程沒有鏡像來源，請先在課程資訊卡填入 BV 號或影片網址")
    return course["downloadUrl"], "下載鏡像：%s" % course["series"]


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")


def set_mirror(slug, value):
    """Persist a new mirror source: a BV id or a full video URL."""
    course = _require_course(slug)
    value = (value or "").strip()
    path = os.path.join(COURSES_DIR, slug, "course.json")
    meta = _read_json(path, {}) or {}

    if not value:
        meta.pop("mirrorUrl", None)
        meta.pop("bv", None)
    else:
        m = BV_RE.search(value)
        if m:
            meta["bv"] = m.group(1)
            if value.lower().startswith(("http://", "https://")):
                meta["mirrorUrl"] = value
            else:
                meta.pop("mirrorUrl", None)
        elif value.lower().startswith(("http://", "https://")):
            meta["mirrorUrl"] = value
        else:
            raise ValueError("請輸入 BV 號（BV 開頭 12 碼）或完整的 http(s) 影片網址")

    _write_json(path, meta)
    return load_course(slug)


def count_playlist_items(url, auth_args):
    """Cheap flat probe: how many parts does this playlist have?"""
    cmd = [YTDLP, "--no-color", "--no-warnings", "--flat-playlist",
           "--print", "%(playlist_index)s"] + list(auth_args) + [url]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=120, creationflags=flags,
                             env=_child_env())
    except Exception:
        return 0
    if res.returncode != 0:
        return 0
    return sum(1 for line in (res.stdout or "").splitlines() if line.strip().isdigit())


def split_ranges(total, parts):
    """Even contiguous 1-based ranges, e.g. (35, 3) -> [(1,12),(13,23),(24,35)]."""
    parts = max(1, min(int(parts), total))
    size = total / parts
    out = []
    for i in range(parts):
        a = int(round(i * size)) + 1
        b = int(round((i + 1) * size))
        if a <= b:
            out.append((a, b))
    return out


def start_download(slug, mode="bilibili", cookies="", cookies_from_browser="",
                   url="", lecture_id=None, parallel=3):
    course = _require_course(slug)
    if not YTDLP:
        raise ValueError("找不到 yt-dlp，請先安裝（winget install yt-dlp.yt-dlp）")

    target, label = _resolve_target(course, mode, url, lecture_id)
    auth = _auth_args(cookies, cookies_from_browser)

    out_dir = os.path.join(video_root(slug), "_source")
    os.makedirs(out_dir, exist_ok=True)
    template = os.path.join(out_dir, "%(playlist_index|00)s-%(title).70B.%(ext)s")

    base = [YTDLP, "--no-color", "--newline", "--no-warnings",
            "-f", "bv*+ba/b", "--merge-output-format", "mp4",
            "--retries", "10", "--fragment-retries", "10",
            "-o", template] + auth
    if mode == "lecture":
        base.append("--no-playlist")

    want = max(1, int(parallel or 1))

    def build_steps():
        """Split the playlist across connections once we know its length."""
        if want < 2:
            return [(label, base + [target])]
        total = count_playlist_items(target, auth)
        if total < 2:
            return [(label, base + [target])]
        return [("%s · 分 P %d-%d" % (label, a, b),
                 base + ["--playlist-items", "%d-%d" % (a, b), target])
                for a, b in split_ranges(total, want)]

    return submit(Job("download", label, [], parallel=want > 1, prepare=build_steps))


def probe_source(slug, mode="bilibili", cookies="", cookies_from_browser="",
                 url="", lecture_id=None):
    """Dry-run the extractor so the user learns about 412/cookies *before* a long download."""
    course = _require_course(slug)
    if not YTDLP:
        raise ValueError("找不到 yt-dlp，請先安裝（winget install yt-dlp.yt-dlp）")

    target, _label = _resolve_target(course, mode, url, lecture_id)
    cmd = [YTDLP, "--no-color", "--simulate", "--no-warnings",
           "--print", "%(playlist_index|00)s|%(title)s|%(duration_string|?)s"]
    cmd += _auth_args(cookies, cookies_from_browser)
    cmd.append(target)

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=90, creationflags=flags,
                             env=_child_env())
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "探測逾時（90 秒），請確認網路或改用 cookies"}

    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip().splitlines()
        tail = " / ".join(err[-2:]) if err else "未知錯誤"
        hints = [h for needle, h in FAILURE_HINTS if needle in (res.stderr or "") + (res.stdout or "")]
        return {"ok": False, "error": tail, "hints": hints}

    items = []
    for line in (res.stdout or "").splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[1].strip():
            items.append({"index": parts[0], "title": parts[1], "duration": parts[2] if len(parts) > 2 else "?"})
    return {"ok": True, "count": len(items), "items": items[:12], "url": target}


def build_lesson_ranges(course, src_duration=0.0, calibrate=True):
    """Per-lesson [start, duration] pairs; optionally rescaled to the real file length."""
    lessons = course["lessons"]
    ranges = [(l["start"], max(0.0, l["end"] - l["start"])) for l in lessons]
    planned = sum(d for _s, d in ranges)
    scaled = False
    if calibrate and src_duration > 0 and planned > 0:
        drift = abs(src_duration - planned)
        if drift > 2.0:
            k = src_duration / planned
            ranges = [(s * k, d * k) for s, d in ranges]
            scaled = True
    return ranges, scaled


def _copy_step(src, dst):
    """In-process file copy, used when a downloaded part already IS the lesson."""
    def run(job):
        size = os.path.getsize(src)
        shutil.copy2(src, dst)
        job._log("  %s → %s（%.1f MB）" % (os.path.basename(src), os.path.basename(dst),
                                          size / 1048576.0))
    return run


def _start_map_parts(course, out_dir, overwrite):
    """Map each downloaded part in video/_source to video/<lesson-slug>.mp4."""
    base = os.path.join(COURSES_DIR, course["slug"])
    parts = _scan_parts(base, course["lessons"])
    if not parts:
        raise ValueError("video/_source/ 沒有可對應的分 P 檔案"
                         "（檔名需含「pNN M.」；也可改用按單元時長分割）")

    steps, skipped, unmatched = [], 0, []
    for lesson in course["lessons"]:
        name = parts.get(lesson["slug"])
        if not name:
            if not lesson["video"]["exists"]:
                unmatched.append(lesson)
            continue
        src = os.path.join(base, "video", "_source", name)
        dst = os.path.join(out_dir, lesson["slug"] + ".mp4")
        if os.path.exists(dst) and not overwrite:
            skipped += 1
            continue
        steps.append(("%02d %s" % (lesson["index"], lesson["title"]), _copy_step(src, dst)))

    if not steps:
        raise ValueError("可對應的單元都已有檔案（可勾選「覆寫」重建）")

    job = Job("split", "整理：%s（%d 個分 P → 單元）" % (course["series"], len(steps)), steps)
    job._log("[..] 對應到 %d 個單元，略過 %d 個已存在" % (len(steps), skipped))
    if unmatched:
        job._log("[..] 另有 %d 個單元在此鏡像中沒有對應分 P" % len(unmatched))
    return submit(job)


def start_split(slug, source, mode="lessons", seconds=600, accurate=False,
                overwrite=False, calibrate=True, only_missing=True):
    course = _require_course(slug)
    out_dir = video_root(slug)
    os.makedirs(out_dir, exist_ok=True)

    if mode == "parts":
        return _start_map_parts(course, out_dir, overwrite)

    if not FFMPEG:
        raise ValueError("找不到 ffmpeg，請先安裝（winget install yt-dlp.FFmpeg）")

    src = _safe_video_path(slug, source)
    if not os.path.isfile(src):
        raise ValueError("找不到來源影片：%s" % source)

    base_cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]

    def encode_args(duration):
        if accurate:
            return ["-t", "%.3f" % duration, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-c:a", "aac", "-b:a", "160k"]
        return ["-t", "%.3f" % duration, "-c", "copy", "-avoid_negative_ts", "make_zero"]

    steps = []
    if mode == "fixed":
        secs = max(1, int(seconds))
        pattern = os.path.join(out_dir, "part_%03d.mp4")
        cmd = base_cmd + ["-i", src, "-c", "copy", "-map", "0",
                          "-f", "segment", "-segment_time", str(secs),
                          "-reset_timestamps", "1", pattern]
        steps.append(("固定長度分割（每 %d 秒）" % secs, cmd))
    else:
        src_duration = probe_duration(src)
        ranges, scaled = build_lesson_ranges(course, src_duration, calibrate)
        for lesson, (start, duration) in zip(course["lessons"], ranges):
            if duration <= 0.2:
                continue
            target = os.path.join(out_dir, lesson["slug"] + ".mp4")
            if os.path.exists(target) and not overwrite and only_missing:
                continue
            cmd = base_cmd + ["-ss", "%.3f" % start, "-i", src] + encode_args(duration) + [target]
            steps.append(("%02d %s" % (lesson["index"], lesson["title"]), cmd))
        if not steps:
            raise ValueError("所有單元檔案都已存在（可勾選「覆寫」重切）")
        if scaled:
            steps[0] = ("（時長已依實際影片長度校正）" + steps[0][0], steps[0][1])

    title = "分割：%s ← %s" % (course["series"], os.path.basename(src))
    return submit(Job("split", title, steps))


# --------------------------------------------------------------- routing
def _json_body(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except Exception:
        raise ValueError("請求內容不是合法 JSON")


def route(method, path, body=b""):
    """Return (http_status, payload)."""
    sub = path.split("?", 1)[0]
    query = path.split("?", 1)[1] if "?" in path else ""
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = v

    try:
        if method == "GET":
            if sub.endswith("/state"):
                slugs = list_slugs()
                return 200, {
                    "root": ROOT,
                    "tools": {
                        "ffmpeg": FFMPEG,
                        "ffprobe": FFPROBE,
                        "ytdlp": YTDLP,
                        "ready": bool(FFMPEG and YTDLP),
                    },
                    "courses": [course_summary(s) for s in slugs],
                }
            if sub.endswith("/course"):
                return 200, _require_course(params.get("slug", ""))
            if sub.endswith("/sources"):
                slug = params.get("slug", "")
                _require_course(slug)
                files = list_sources(slug)
                for item in files:
                    item["duration"] = round(probe_duration(_safe_video_path(slug, item["path"])), 3)
                return 200, {"slug": slug, "files": files}
            if sub.endswith("/jobs"):
                jobs = sorted(_JOBS.values(), key=lambda j: j.created, reverse=True)
                return 200, {"jobs": [j.snapshot() for j in jobs[:20]]}
            return 404, {"error": "未知的 API 路徑"}

        if method == "POST":
            data = _json_body(body)
            if sub.endswith("/course/mirror"):
                return 200, {"course": set_mirror(data.get("slug", ""), data.get("value", ""))}
            if sub.endswith("/probe"):
                return 200, probe_source(
                    data.get("slug", ""),
                    mode=data.get("mode", "bilibili"),
                    cookies=(data.get("cookies") or "").strip(),
                    cookies_from_browser=(data.get("cookiesFromBrowser") or "").strip(),
                    url=data.get("url") or "",
                    lecture_id=data.get("lectureId"),
                )
            if sub.endswith("/download"):
                job = start_download(
                    data.get("slug", ""),
                    mode=data.get("mode", "bilibili"),
                    cookies=(data.get("cookies") or "").strip(),
                    cookies_from_browser=(data.get("cookiesFromBrowser") or "").strip(),
                    url=data.get("url") or "",
                    lecture_id=data.get("lectureId"),
                    parallel=data.get("parallel") or 3,
                )
                return 200, {"job": job.snapshot()}
            if sub.endswith("/split"):
                job = start_split(
                    data.get("slug", ""),
                    data.get("source", ""),
                    mode=data.get("mode", "lessons"),
                    seconds=data.get("seconds") or 600,
                    accurate=bool(data.get("accurate")),
                    overwrite=bool(data.get("overwrite")),
                    calibrate=bool(data.get("calibrate", True)),
                )
                return 200, {"job": job.snapshot()}
            if sub.endswith("/jobs/cancel"):
                job = _JOBS.get(data.get("id", ""))
                if not job:
                    return 404, {"error": "找不到任務"}
                job.cancel()
                return 200, {"job": job.snapshot()}
            if sub.endswith("/jobs/clear"):
                for jid in [j.id for j in _JOBS.values() if j.status in ("done", "failed", "cancelled")]:
                    _JOBS.pop(jid, None)
                return 200, {"ok": True}
            return 404, {"error": "未知的 API 路徑"}

        return 405, {"error": "不支援的方法"}
    except ValueError as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return 500, {"error": "%s: %s" % (type(exc).__name__, exc)}
