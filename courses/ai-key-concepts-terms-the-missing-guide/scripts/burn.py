#!/usr/bin/env python3
"""Burn bilingual dynamic subtitles into a video with ffmpeg.

Usage:
    python3 scripts/burn.py <input-video> <lesson-slug> [output.mp4]

Requires the animated ASS produced by scripts/build.py at
data/ass/<lesson-slug>.ass
"""
import os
import shutil
import subprocess
import sys


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    src, slug = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else f"out/{slug}.bilingual.mp4"

    ass = os.path.abspath(f"data/ass/{slug}.ass")
    if not os.path.exists(ass):
        sys.exit(f"No ASS found for '{slug}'. Run: python3 scripts/build.py")
    if not os.path.exists(src):
        sys.exit(f"Input video not found: {src}")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found on PATH.")

    # escape the ASS path for the subtitles filter
    ass_filter = ass.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-vf", f"subtitles='{ass_filter}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        out,
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
