#!/usr/bin/env python3
"""Translate English subtitle segments to Traditional Chinese (zh-TW).

Uses the public Google translate endpoint, batching several segments per
request with newline separation. Validates that the response line count
matches the batch; if not, recursively splits the batch. Results are cached
so re-runs are cheap. A hand-authored override file (if present) wins.

Output: data/translations/zh-Hant/<slug>.json  (array of zh strings, aligned to segments)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://clients5.google.com/translate_a/t"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
BATCH = 20
BATCH_SLEEP = 1.4      # seconds between requests


def translate_batch(texts, sl="en", tl="zh-TW", retries=6):
    """Translate a list of strings via the multi-query endpoint.

    Sends one `q` param per line and expects a JSON array back, so there is
    no line-count ambiguity. Falls back to splitting on mismatch.
    """
    if not texts:
        return []
    params = [("client", "dict-chrome-ex"), ("sl", sl), ("tl", tl)]
    params += [("q", t) for t in texts]
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                raw = r.read().decode("utf-8", "replace")
            data = json.loads(raw)
            if isinstance(data, str):
                data = [data]
            if isinstance(data, list) and len(data) == len(texts):
                return [str(x).strip() for x in data]
            if len(texts) == 1:
                return [str(data).strip() if not isinstance(data, list) else str(data[0]).strip()]
            mid = len(texts) // 2
            time.sleep(0.4)
            return (translate_batch(texts[:mid], sl, tl, retries)
                    + translate_batch(texts[mid:], sl, tl, retries))
        except Exception as e:  # noqa: BLE001
            last = e
            code = getattr(e, "code", None)
            wait = (10, 20, 35, 55, 80, 120)[min(attempt, 5)] if code == 429 else 2 * (attempt + 1)
            time.sleep(wait)
    raise RuntimeError(f"translate failed after {retries} tries: {last}")


def main():
    d = json.load(open("data/lessons.json", encoding="utf-8"))
    out_dir = "data/translations/zh-Hant"
    os.makedirs(out_dir, exist_ok=True)

    only = sys.argv[1:] if len(sys.argv) > 1 else None

    for l in d["lessons"]:
        slug = l["slug"]
        if only and slug not in only:
            continue
        seg_path = f"data/segments/{slug}.json"
        if not os.path.exists(seg_path):
            continue
        segs = json.load(open(seg_path, encoding="utf-8"))
        out_path = f"{out_dir}/{slug}.json"

        # hand-authored override wins
        if os.path.exists(out_path):
            try:
                existing = json.load(open(out_path, encoding="utf-8"))
                if len(existing) == len(segs) and existing and all(existing):
                    print(f"SKIP {slug} (override/cache present, {len(existing)} lines)")
                    continue
            except Exception:  # noqa: BLE001
                pass

        ens = [s["en"] for s in segs]
        zh = []
        t0 = time.time()
        for i in range(0, len(ens), BATCH):
            chunk = ens[i:i + BATCH]
            zh.extend(translate_batch(chunk))
            time.sleep(BATCH_SLEEP)
            sys.stdout.write(f"\r  {slug}: {min(i+BATCH,len(ens))}/{len(ens)}")
            sys.stdout.flush()
        print(f"\r  {slug}: {len(zh)} lines in {time.time()-t0:.0f}s")
        json.dump(zh, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
