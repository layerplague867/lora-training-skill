"""Phase 3b — BUILD DATASET. Copy curated keeps into the kohya
`<repeats>_<concept>` concept folder, normalizing every image to RGB.

RGB images are copied byte-for-byte (no re-encode). RGBA/P/LA images are
flattened onto white and saved as PNG. Originals stay in raw/ (reversible).
Repeats default to the ~1500-step formula clamp(round(150 / keeps), 1, 10).

Usage:
  python build_dataset.py --work "D:/work/mychar" --concept mychar
  python build_dataset.py --work "D:/work/mychar" --concept mychar --repeats 5
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image


def pick_repeats(n_keep: int) -> int:
    if n_keep <= 0:
        return 1
    return max(1, min(10, round(150 / n_keep)))


def to_rgb_png(src: Path, dst: Path) -> None:
    with Image.open(src) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        im.save(dst, "PNG")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the kohya concept folder from curated keeps."
    )
    ap.add_argument(
        "--work",
        required=True,
        help="project dir (has raw/ and curation_manifest.json)",
    )
    ap.add_argument(
        "--concept", required=True, help="concept/trigger folder name, e.g. mychar"
    )
    ap.add_argument(
        "--repeats",
        type=int,
        default=0,
        help="override repeats (0 = auto from keep count)",
    )
    a = ap.parse_args()

    work = Path(a.work).resolve()
    raw = work / "raw"
    manifest = work / "curation_manifest.json"
    if not manifest.exists():
        print(f"ERROR: {manifest} missing — run curate.py first.")
        return 2

    keep = json.loads(manifest.read_text(encoding="utf-8"))["keep"]
    repeats = a.repeats or pick_repeats(len(keep))
    concept_dir = work / "dataset" / f"{repeats}_{a.concept}"
    concept_dir.mkdir(parents=True, exist_ok=True)

    copied = converted = 0
    for rec in keep:
        src = raw / rec["file"]
        if not src.exists():
            continue
        if rec["mode"] == "RGB":
            shutil.copy2(src, concept_dir / rec["file"])
            copied += 1
        else:
            to_rgb_png(src, concept_dir / f"{Path(rec['file']).stem}.png")
            converted += 1

    n = len(list(concept_dir.glob("*.*")))
    print(f"concept folder : {concept_dir}")
    print(f"repeats        : {repeats}  (keeps={len(keep)})")
    print(f"copied RGB     : {copied}   converted->RGB png: {converted}   total: {n}")
    print(
        f'\nnext: tag_dataset.py --work "{work}" --concept {a.concept} --trigger <TRIGGER>'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
