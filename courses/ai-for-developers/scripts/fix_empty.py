#!/usr/bin/env python3
"""Re-translate cues whose zh translation came back empty.

Runs after translate.py to patch any blanks left by batch line-count
mismatches. Writes the filled translations back in place.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from translate import translate_batch  # noqa: E402


def main():
    d = json.load(open("data/lessons.json", encoding="utf-8"))
    total = 0
    for l in d["lessons"]:
        slug = l["slug"]
        tp = f"data/translations/zh-Hant/{slug}.json"
        if not os.path.exists(tp):
            continue
        zh = json.load(open(tp, encoding="utf-8"))
        segs = json.load(open(f"data/segments/{slug}.json", encoding="utf-8"))
        idxs = [i for i, t in enumerate(zh) if t is None or not str(t).strip()]
        if not idxs:
            continue
        print(f"{slug}: refilling {len(idxs)} blanks")
        for k in range(0, len(idxs), 20):
            chunk = idxs[k:k + 20]
            texts = [segs[i]["en"] for i in chunk]
            try:
                out = translate_batch(texts)
            except Exception as e:  # noqa: BLE001
                print(f"   ! {e}")
                continue
            for i, t in zip(chunk, out):
                if str(t).strip():
                    zh[i] = t
                    total += 1
            time.sleep(1.4)
        json.dump(zh, open(tp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nFilled {total} blanks")


if __name__ == "__main__":
    main()
