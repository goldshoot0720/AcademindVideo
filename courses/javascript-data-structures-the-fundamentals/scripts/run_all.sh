#!/usr/bin/env bash
# One-shot pipeline: scrape course -> download mirror -> transcribe -> translate -> build.
# Re-running is cheap: every stage skips work that is already on disk.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf "\n\033[1;36m== %s ==\033[0m\n" "$1"; }

step "1/6  course metadata            -> data/lessons.json"
python3 scripts/scrape.py

step "2/6  mirror part mapping        -> data/bili.json"
python3 scripts/bili.py

step "3/6  download videos + audio    -> video/ audio/"
python3 scripts/download.py

step "4/6  English transcript (ASR)   -> data/srt/en/"
python3 scripts/asr.py --concurrency 3

step "5/6  parse + translate          -> data/segments/ data/translations/"
python3 scripts/parse_srt.py
python3 scripts/translate.py
python3 scripts/fix_empty.py || true

step "6/6  build bilingual assets     -> data/{bilingual,srt,ass} player/"
python3 scripts/build.py

printf "\n\033[1;32mDone.\033[0m  Start the site with:  python3 scripts/serve.py --open\n"
