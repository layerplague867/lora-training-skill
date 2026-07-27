"""Phase 3a — CURATE. Read the raw download, drop images that are a poor fit for a
single-character LoRA (multi-subject / comic / reference-sheet / tiny / corrupt),
and write a keep/drop manifest. Image-only: the danbooru `.txt` is used for
filtering, not copied (we re-tag with WD14 in tag_dataset.py).

Usage:
  python curate.py --work "D:/work/mychar"           # dry-run report + manifest
  python curate.py --work "D:/work/mychar" --tiny 512 # tune the short-side floor
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Sidecar tags that mark an image as unsuitable for a solo-character set.
MULTI_SUBJECT = {
    "2girls",
    "3girls",
    "4girls",
    "5girls",
    "6+girls",
    "multiple girls",
    "2boys",
    "3boys",
    "multiple boys",
    "multiple views",
    "comic",
    "4koma",
    "reference sheet",
    "character sheet",
}

# For a STYLE LoRA the target is the ARTIST's rendering, not one character — so
# multi-subject / boys / nsfw are all valid style samples and must be KEPT. The only
# genuinely harmful inputs are multi-image compositions (panels/sheets stitch several
# drawings + text into one file) and tiny/corrupt images. This is that subset.
COMIC_SHEET = {
    "comic",
    "4koma",
    "multiple views",
    "reference sheet",
    "character sheet",
}

# Off-model content that muddies a single-character identity (learned the hard way:
# top danbooru fanart of a popular character is full of genderswaps, futanari, cosplay,
# and male-present scenes). Matched as a substring of any sidecar tag ("genderswap" catches
# "genderswap (mtf)"). ALWAYS dropped — wrong sex/identity is off-model.
OFFMODEL_KEYWORDS = (
    "genderswap",
    "futanari",
    "cosplay",
    "1boy",
    "2boys",
    "3boys",
    "multiple boys",
    "penis",
    "testicles",
)

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
    if not txt_path.exists():
        return set()
    raw = txt_path.read_text(encoding="utf-8", errors="replace")
    return {t.strip().lower() for t in raw.split(",") if t.strip()}


def match_keyword(tags: set[str], keywords) -> list[str]:
    """Return the keywords that appear as a substring of any tag (deduped, sorted)."""
    hit = {k for k in keywords if any(k in t for t in tags)}
    return sorted(hit)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Curate raw downloads into a keep/drop manifest."
    )
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
    ap.add_argument(
        "--lowres", type=int, default=768, help="keep-but-note threshold (default 768)"
    )
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
    a = ap.parse_args()

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
        bad = sorted(tags & (COMIC_SHEET if a.style else MULTI_SUBJECT))
        if bad:
            reasons.append("comic/sheet:" + "+".join(bad))
        if not a.style:
            offmodel = match_keyword(tags, OFFMODEL_KEYWORDS)
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
            "reasons": reasons,
        }
        if reasons:
            drop.append(rec)
        else:
            rec["note_lowres"] = short < a.lowres
            keep.append(rec)

    manifest.write_text(
        json.dumps({"keep": keep, "drop": drop}, indent=2), encoding="utf-8"
    )
    print(f"KEEP: {len(keep)}   DROP: {len(drop)}   -> {manifest.name}")
    for d in drop:
        print(f"  drop {d['file']}: {d.get('reason') or ', '.join(d['reasons'])}")
    lowres = sum(1 for k in keep if k.get("note_lowres"))
    nonsolo = sum(1 for k in keep if not k["solo"])
    modes: dict[str, int] = {}
    for k in keep:
        modes[k["mode"]] = modes.get(k["mode"], 0) + 1
    print(
        f"KEEP stats — lowres(<{a.lowres}): {lowres}  non-solo: {nonsolo}  modes: {modes}"
    )
    if len(keep) < 15:
        print(
            "WARNING: <15 keeps — consider a broader tag or higher --limit before training."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
