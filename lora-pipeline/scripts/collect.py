"""Phase 1 — COLLECT. Download a character/concept image set from Danbooru via
the DanbooruDownload CLI (https://github.com/storyAura/DanbooruDownload).

Writes images + danbooru `.txt` sidecars into <work>/raw/. The sidecar tags are
used later by curate.py for filtering; we re-tag with WD14 for the real captions.

Danbooru gotcha (anonymous API): a query is limited to **2 tags**, and
`--rating` / `--min-score` become `rating:` / `score:` metatags that ALSO count
toward that limit. So download with just the single character tag + save the
sidecar tags, and curate locally (curate.py) instead of server-side filtering.

Usage:
  python collect.py --tag "my_character_(my_series)" --work "D:/work/mychar" --limit 200
Environment overrides:
  DANBOORU_DL_DIR   path to the cloned DanbooruDownload repo (has main.py + .venv)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_DL_DIR = os.environ.get("DANBOORU_DL_DIR", r"C:\tools\DanbooruDownload")


def build_yaml(tag: str, save_dir: Path, limit: int) -> str:
    return (
        f'tags: "{tag}"\n'
        f'save_dir: "{save_dir.as_posix()}"\n'
        'filename_format: "{id}.{ext}"\n'
        f"max_posts: {limit}\n"
        "concurrent_downloads: 8\n"
        "skip_existing: true\n"
        "timeout: 30.0\n"
        "save_tag_txt: true\n"
        "tag_txt_categories:\n"
        "  - artist\n  - copyright\n  - character\n  - general\n  - meta\n"
        "tag_txt_underscore_to_space: true\n"
        "tag_txt_escape_special_chars: false\n"
    )


def find_python(dl_dir: Path) -> str:
    venv = dl_dir / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else sys.executable


def main() -> int:
    ap = argparse.ArgumentParser(description="Download a concept image set from Danbooru.")
    ap.add_argument(
        "--tag",
        required=True,
        help="single danbooru character tag, e.g. my_character_(my_series)",
    )
    ap.add_argument("--work", required=True, help="project work dir; images land in <work>/raw/")
    ap.add_argument("--limit", type=int, default=200, help="max posts (default 200)")
    ap.add_argument(
        "--downloader-dir", default=DEFAULT_DL_DIR, help="path to DanbooruDownload repo"
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually run (default: print the plan only)",
    )
    a = ap.parse_args()

    work = Path(a.work).resolve()
    raw = work / "raw"
    dl_dir = Path(a.downloader_dir)
    if not (dl_dir / "main.py").exists():
        print(
            f"ERROR: DanbooruDownload not found at {dl_dir} (set --downloader-dir or $DANBOORU_DL_DIR)"
        )
        return 2

    cfg_path = work / "download.yaml"
    py = find_python(dl_dir)
    cmd = [py, "main.py", "--config", str(cfg_path)]

    print(f"tag        : {a.tag}")
    print(f"save_dir   : {raw}")
    print(f"limit      : {a.limit}")
    print(f"downloader : {dl_dir}  (python: {py})")
    print(f"config     : {cfg_path}")
    if not a.apply:
        print("\n[dry-run] would run:  cd <downloader> &&", " ".join(cmd))
        print("re-run with --apply to download.")
        return 0

    raw.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(build_yaml(a.tag, raw, a.limit), encoding="utf-8")
    print("\nrunning download...")
    proc = subprocess.run(cmd, cwd=str(dl_dir), check=False)
    n = len([p for p in raw.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}])
    print(f"\ndownload exit={proc.returncode} | images now in raw/: {n}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
