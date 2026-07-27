"""Phase 3a — CURATE. Read the raw download, drop images that are a poor fit for a
single-character LoRA (multi-subject / comic / reference-sheet / tiny / corrupt),
and write a keep/drop manifest. Image-only: the danbooru `.txt` is used for
filtering, not copied (we re-tag with WD14 in tag_dataset.py).

Usage:
  python curate.py --work "D:/work/mychar" --subject-tag 1girl
  python curate.py --work "D:/work/style" --style
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dataset_profile as profile  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Explicit content — dropped by default for a SFW character LoRA; --keep-nsfw keeps it.
# (A character LoRA learns identity fine from SFW; explicit art also skews the trigger.)
NSFW_KEYWORDS = (
    "sex",
    "vaginal",
    "anal",
    "fellatio",
    "cum",
    "ejaculation",
    "nude",
    "pussy",
    "clitoris",
    "nipples",
    "areola",
)


def parse_tags(txt_path: Path) -> set[str]:
    return profile.parse_tags_file(txt_path)


def match_keyword(tags: set[str], keywords) -> list[str]:
    """Return the keywords that appear as a substring of any tag (deduped, sorted)."""
    return profile.match_keywords(tags, tuple(keywords))


def source_url(image: Path) -> str | None:
    return f"https://danbooru.donmai.us/posts/{image.stem}" if image.stem.isdigit() else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Curate raw downloads into a keep/drop manifest.")
    ap.add_argument(
        "--work",
        required=True,
        help="project dir; reads <work>/raw/, writes curation_manifest.json",
    )
    ap.add_argument(
        "--tiny",
        type=int,
        default=512,
        help="drop images whose short side < this (default 512)",
    )
    ap.add_argument("--lowres", type=int, default=768, help="keep-but-note threshold (default 768)")
    ap.add_argument(
        "--keep-nsfw",
        action="store_true",
        help="keep explicit images (default: drop them for a SFW character LoRA)",
    )
    ap.add_argument(
        "--style",
        action="store_true",
        help="STYLE LoRA mode: keep nsfw/multi-subject/male (all valid style samples); "
        "drop ONLY multi-image comics/sheets + tiny/corrupt. Implies --keep-nsfw.",
    )
    ap.add_argument(
        "--subject-tag",
        choices=profile.SUBJECT_TAGS,
        help="character subject count tag; required unless --style",
    )
    a = ap.parse_args()
    if not a.style and not a.subject_tag:
        ap.error("--subject-tag is required for character curation")

    work = Path(a.work).resolve()
    raw = work / "raw"
    if not raw.is_dir():
        print(f"ERROR: {raw} not found — run collect.py first.")
        return 2
    manifest = work / "curation_manifest.json"

    keep: list[dict] = []
    drop: list[dict] = []
    for img in sorted(raw.iterdir()):
        if img.suffix.lower() not in IMAGE_EXTS:
            continue
        tags = parse_tags(img.with_suffix(".txt"))
        try:
            with Image.open(img) as im:
                im.verify()
            with Image.open(img) as im:
                w, h = im.size
                mode = im.mode
        except Exception as e:  # noqa: BLE001 — any decode failure = drop
            drop.append({"file": img.name, "reason": f"corrupt: {e}"})
            continue

        short = min(w, h)
        reasons: list[str] = []
        # STYLE mode keeps multi-subject/male/nsfw (all valid style samples) and only
        # rejects multi-image comics/sheets; character mode is the stricter solo filter.
        bad = sorted(tags & (profile.COMIC_SHEET if a.style else profile.MULTI_SUBJECT))
        if bad:
            reasons.append("comic/sheet:" + "+".join(bad))
        if not a.style:
            offmodel = match_keyword(tags, profile.offmodel_keywords(a.subject_tag))
            if offmodel:
                reasons.append("off-model:" + "+".join(offmodel))
            if not a.keep_nsfw:
                nsfw = match_keyword(tags, NSFW_KEYWORDS)
                if nsfw:
                    reasons.append("nsfw:" + "+".join(nsfw))
        if short < a.tiny:
            reasons.append(f"tiny({w}x{h})")

        rec = {
            "file": img.name,
            "w": w,
            "h": h,
            "mode": mode,
            "short": short,
            "n_tags": len(tags),
            "solo": "solo" in tags,
            "source": source_url(img),
            "reasons": reasons,
        }
        if reasons:
            drop.append(rec)
        else:
            rec["note_lowres"] = short < a.lowres
            keep.append(rec)

    manifest.write_text(json.dumps({"keep": keep, "drop": drop}, indent=2), encoding="utf-8")
    print(f"KEEP: {len(keep)}   DROP: {len(drop)}   -> {manifest.name}")
    for d in drop:
        print(f"  drop {d['file']}: {d.get('reason') or ', '.join(d['reasons'])}")
    lowres = sum(1 for k in keep if k.get("note_lowres"))
    nonsolo = sum(1 for k in keep if not k["solo"])
    modes: dict[str, int] = {}
    for k in keep:
        modes[k["mode"]] = modes.get(k["mode"], 0) + 1
    print(f"KEEP stats — lowres(<{a.lowres}): {lowres}  non-solo: {nonsolo}  modes: {modes}")
    if len(keep) < 15:
        print("WARNING: <15 keeps — consider a broader tag or higher --limit before training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
