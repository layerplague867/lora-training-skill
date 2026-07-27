"""Scan a LoRA training dataset for image-level quality problems.

Walks a ``train_data_dir`` (kohya ``<repeats>_<concept>`` layout) or a single
image folder and reports: per-concept image counts and repeat balance, the
effective-step budget, resolution / aspect-ratio distribution versus the target
training resolution, colour-mode issues, unreadable/corrupt files, exact
(md5) duplicates and near-duplicates (perceptual dhash), and how many images are
missing a caption sidecar.

This complements the trainer: lora-scripts-next only checks that the folder
*exists and contains images*; it never inspects quality. This script does.

Usage:
    python scan_dataset.py <path> [--epochs 10] [--batch-size 1]
                           [--target-reso 1024,1024] [--no-recursive]
                           [--json] [--report] [--output FILE]

Exit code is always 0 (this is a reporting tool); read ``issues`` in the JSON
or run doctor.py for a PASS/WARN/FAIL verdict.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# The trainer ships an embedded Python whose ._pth file suppresses the usual
# "script dir on sys.path" behaviour, so make sibling imports explicit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

# --- Tunable thresholds (named, not magic) -----------------------------------

DHASH_SIZE = 8
NEAR_DUP_HAMMING = 5  # <= this Hamming distance on a 64-bit dhash == near-dup
NEAR_DUP_MAX_IMAGES = 1500  # skip O(n^2) near-dup scan above this many images
TINY_SHORT_SIDE = 384  # short side below this is too small to train well
SQUARE_LO, SQUARE_HI = 0.9, 1.111  # aspect ratio band treated as "square"
EXTREME_ASPECT = 2.5  # width/height (or inverse) beyond this is extreme
MISSING_CAPTION_HIGH_PCT = 5.0  # >this % of images missing captions -> HIGH
MAX_EXAMPLES = 12  # cap example offenders carried in issues


# --- Perceptual hash ---------------------------------------------------------


def dhash(image, hash_size: int = DHASH_SIZE) -> int:
    """Difference hash. Grayscale, resize to (hash_size+1, hash_size), then
    encode the sign of each horizontal neighbour difference into one bit.
    Pure Pillow, no numpy."""
    small = image.convert("L").resize((hash_size + 1, hash_size))
    pixels = small.load()
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = pixels[col, row]
            right = pixels[col + 1, row]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# --- Image probing -----------------------------------------------------------


def probe_image(path: Path) -> dict:
    """Read geometry/mode and compute a dhash. On any decode failure return a
    record with an ``error`` key instead of raising."""
    from PIL import Image

    try:
        with Image.open(path) as img:
            width, height = img.size
            mode = img.mode
            fmt = img.format or path.suffix.lstrip(".").upper()
            phash = dhash(img)
    except Exception as exc:  # noqa: BLE001 - any decode error == unusable image
        return {"path": str(path), "error": f"{type(exc).__name__}: {exc}"}

    short_side = min(width, height)
    long_side = max(width, height)
    aspect = round(width / height, 4) if height else 0.0
    return {
        "path": str(path),
        "width": width,
        "height": height,
        "mode": mode,
        "format": fmt,
        "megapixels": round(width * height / 1_000_000, 3),
        "aspect": aspect,
        "short_side": short_side,
        "long_side": long_side,
        "filesize": path.stat().st_size,
        "dhash": phash,
    }


def aspect_bucket(aspect: float) -> str:
    if aspect <= 0:
        return "unknown"
    if SQUARE_LO <= aspect <= SQUARE_HI:
        return "square"
    if aspect > EXTREME_ASPECT:
        return "extreme_wide"
    if aspect < 1 / EXTREME_ASPECT:
        return "extreme_tall"
    return "landscape" if aspect > 1 else "portrait"


# --- Duplicate grouping ------------------------------------------------------


def group_exact_duplicates(records: list[dict], paths: list[Path]) -> list[list[str]]:
    by_md5: dict[str, list[str]] = defaultdict(list)
    for rec, path in zip(records, paths, strict=True):
        if "error" in rec:
            continue
        by_md5[C.md5_file(path)].append(rec["path"])
    return [sorted(group) for group in by_md5.values() if len(group) > 1]


def group_near_duplicates(
    records: list[dict], threshold: int = NEAR_DUP_HAMMING
) -> list[list[str]]:
    """Union-find over pairwise dhash Hamming distance. Caller guards size."""
    usable = [r for r in records if "error" not in r]
    parent = list(range(len(usable)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            if hamming(usable[i]["dhash"], usable[j]["dhash"]) <= threshold:
                union(i, j)

    clusters: dict[int, list[str]] = defaultdict(list)
    for idx, rec in enumerate(usable):
        clusters[find(idx)].append(rec["path"])
    return [sorted(group) for group in clusters.values() if len(group) > 1]


# --- Core analysis -----------------------------------------------------------


class ConceptInfo:
    __slots__ = ("repeats",)

    def __init__(self, repeats: int):
        self.repeats = repeats


def analyze_dataset(
    root: Path,
    recursive: bool = True,
    epochs: Optional[int] = None,
    batch_size: int = 1,
    target_reso: tuple[int, int] = (1024, 1024),
    prefer_json: bool = False,
) -> dict:
    root = Path(root)
    concepts = C.discover_concept_dirs(root)
    if not concepts:
        # The path may itself be a single "<repeats>_<concept>" folder rather
        # than the parent train_data_dir.
        reps, concept_name = C.parse_concept_folder(root.name)
        if reps is not None:
            concepts = [C.ConceptDir(path=root, repeats=reps, concept=concept_name)]
    mode = "concept" if concepts else "flat"

    # Build per-concept image lists and a flat (records, paths) view.
    concept_reports: list[dict] = []
    all_paths: list[Path] = []
    concept_of: dict[str, ConceptInfo] = {}

    if concepts:
        for cd in concepts:
            imgs = C.iter_images(cd.path, recursive=recursive)
            concept_reports.append(
                {
                    "name": cd.path.name,
                    "concept": cd.concept,
                    "repeats": cd.repeats,
                    "images": len(imgs),
                    "effective_images": len(imgs) * cd.repeats,
                }
            )
            for p in imgs:
                all_paths.append(p)
                concept_of[str(p)] = ConceptInfo(cd.repeats)
    else:
        imgs = C.iter_images(root, recursive=recursive)
        all_paths = imgs
        for p in imgs:
            concept_of[str(p)] = ConceptInfo(1)

    records = [probe_image(p) for p in all_paths]
    good = [r for r in records if "error" not in r]
    corrupt = [r for r in records if "error" in r]

    # Caption pairing.
    missing_caption = [
        str(p) for p in all_paths if C.find_caption_path(p, prefer_json=prefer_json) is None
    ]

    # Aggregates.
    modes = Counter(r["mode"] for r in good)
    buckets = Counter(aspect_bucket(r["aspect"]) for r in good)
    target_long = max(target_reso)
    tiny = [r["path"] for r in good if r["short_side"] < TINY_SHORT_SIDE]
    below_target = [r["path"] for r in good if r["long_side"] < target_long]
    non_rgb = [r["path"] for r in good if r["mode"] not in ("RGB",)]

    short_sides = sorted(r["short_side"] for r in good)
    resolution_stats = {
        "count": len(good),
        "min_short_side": short_sides[0] if short_sides else 0,
        "median_short_side": short_sides[len(short_sides) // 2] if short_sides else 0,
        "max_short_side": short_sides[-1] if short_sides else 0,
        "target": list(target_reso),
        "below_target_long_side": len(below_target),
        "tiny": len(tiny),
    }

    exact_dups = group_exact_duplicates(records, all_paths)
    if len(good) <= NEAR_DUP_MAX_IMAGES:
        near_dups = group_near_duplicates(good)
        near_skipped = False
    else:
        near_dups = []
        near_skipped = True

    total_images = len(all_paths)
    total_effective = sum(concept_of[str(p)].repeats for p in all_paths if str(p) in concept_of)
    effective = {
        "total_images": total_images,
        "total_effective_images": total_effective,
        "batch_size": batch_size,
    }
    if epochs:
        steps_per_epoch = math.ceil(total_effective / max(1, batch_size))
        effective.update(
            {
                "epochs": epochs,
                "steps_per_epoch": steps_per_epoch,
                "total_steps": steps_per_epoch * epochs,
            }
        )

    issues = _build_issues(
        total_images=total_images,
        mode=mode,
        corrupt=corrupt,
        missing_caption=missing_caption,
        exact_dups=exact_dups,
        near_dups=near_dups,
        near_skipped=near_skipped,
        below_target=below_target,
        tiny=tiny,
        non_rgb=non_rgb,
        buckets=buckets,
        concept_reports=concept_reports,
    )

    return {
        "tool": "scan_dataset",
        "root": str(root),
        "mode": mode,
        "concepts": concept_reports,
        "totals": {
            "images": total_images,
            "readable": len(good),
            "corrupt": len(corrupt),
            "missing_caption": len(missing_caption),
        },
        "resolution": resolution_stats,
        "aspect_buckets": dict(buckets),
        "modes": dict(modes),
        "duplicates": {
            "exact_groups": exact_dups,
            "near_groups": near_dups,
            "near_skipped": near_skipped,
        },
        "captions": {
            "missing": len(missing_caption),
            "missing_examples": missing_caption[:MAX_EXAMPLES],
        },
        "effective_steps": effective,
        "corrupt": [r["path"] for r in corrupt],
        "issues": [i.to_dict() for i in C.sort_issues(issues)],
    }


def _build_issues(**kw) -> list[C.Issue]:
    issues: list[C.Issue] = []
    total = kw["total_images"]

    if total == 0:
        issues.append(
            C.Issue(
                C.SEV_CRITICAL,
                "no_images",
                "No training images found.",
                "Point at the correct train_data_dir (parent of <repeats>_<concept> folders).",
            )
        )
        return issues

    if kw["corrupt"]:
        issues.append(
            C.Issue(
                C.SEV_CRITICAL,
                "corrupt_images",
                f"{len(kw['corrupt'])} image(s) cannot be decoded and will crash training.",
                "Remove or re-export these files.",
                [r["path"] for r in kw["corrupt"]][:MAX_EXAMPLES],
            )
        )

    miss = kw["missing_caption"]
    if miss:
        sev = C.SEV_HIGH if C.pct(len(miss), total) > MISSING_CAPTION_HIGH_PCT else C.SEV_MEDIUM
        issues.append(
            C.Issue(
                sev,
                "missing_captions",
                f"{len(miss)} of {total} images ({C.pct(len(miss), total)}%) have no caption sidecar.",
                "Use tag_dataset.py for Anima, or the trainer WD14 tagger for other bases.",
                miss[:MAX_EXAMPLES],
            )
        )

    if kw["mode"] == "flat":
        issues.append(
            C.Issue(
                C.SEV_HIGH,
                "no_concept_folders",
                "No <repeats>_<concept> folders found; every image defaults to 1 repeat.",
                "Move images into a folder like '7_<concept>' so repeats are explicit.",
            )
        )

    if kw["exact_dups"]:
        dup_files = sum(len(g) - 1 for g in kw["exact_dups"])
        issues.append(
            C.Issue(
                C.SEV_MEDIUM,
                "exact_duplicates",
                f"{len(kw['exact_dups'])} group(s) of byte-identical images ({dup_files} redundant files).",
                "Delete duplicates; they bias the model and waste steps.",
                [g[0] for g in kw["exact_dups"]][:MAX_EXAMPLES],
            )
        )
    if kw["near_dups"]:
        issues.append(
            C.Issue(
                C.SEV_MEDIUM,
                "near_duplicates",
                f"{len(kw['near_dups'])} cluster(s) of visually near-identical images.",
                "Keep the best one per cluster to avoid overfitting.",
                [g[0] for g in kw["near_dups"]][:MAX_EXAMPLES],
            )
        )
    if kw["near_skipped"]:
        issues.append(
            C.Issue(
                C.SEV_INFO,
                "near_dup_skipped",
                f"Near-duplicate scan skipped (> {NEAR_DUP_MAX_IMAGES} images).",
                "Run on a subset if you suspect duplicates.",
            )
        )

    if kw["non_rgb"]:
        issues.append(
            C.Issue(
                C.SEV_MEDIUM,
                "non_rgb_mode",
                f"{len(kw['non_rgb'])} image(s) are not RGB (e.g. RGBA/CMYK/palette).",
                "Convert to RGB; alpha/CMYK can corrupt latents.",
                kw["non_rgb"][:MAX_EXAMPLES],
            )
        )
    if kw["below_target"]:
        issues.append(
            C.Issue(
                C.SEV_MEDIUM,
                "below_target_resolution",
                f"{len(kw['below_target'])} image(s) are smaller than the target training resolution.",
                "Replace with higher-res sources; bucket_no_upscale keeps them at low effective detail.",
                kw["below_target"][:MAX_EXAMPLES],
            )
        )
    if kw["tiny"]:
        issues.append(
            C.Issue(
                C.SEV_LOW,
                "tiny_images",
                f"{len(kw['tiny'])} image(s) have a short side < {TINY_SHORT_SIDE}px.",
                "Consider removing very small images.",
                kw["tiny"][:MAX_EXAMPLES],
            )
        )

    extreme = kw["buckets"].get("extreme_wide", 0) + kw["buckets"].get("extreme_tall", 0)
    if extreme:
        issues.append(
            C.Issue(
                C.SEV_LOW,
                "extreme_aspect",
                f"{extreme} image(s) have an extreme aspect ratio (> {EXTREME_ASPECT}:1).",
                "Crop to a trainable aspect or raise max_bucket_reso.",
            )
        )

    # Repeat-balance sanity across concepts.
    reps = {r["repeats"] for r in kw["concept_reports"]}
    if len(reps) > 1:
        issues.append(
            C.Issue(
                C.SEV_INFO,
                "mixed_repeats",
                f"Concepts use different repeat counts: {sorted(reps)}.",
                "Intentional for balancing; verify the effective-image ratio is what you want.",
            )
        )
    return issues


# --- Reporting ---------------------------------------------------------------


def build_markdown(result: dict) -> str:
    lines: list[str] = []
    t = result["totals"]
    lines.append(f"# Dataset scan — `{result['root']}`")
    lines.append("")
    lines.append(
        f"- Mode: **{result['mode']}** · Images: **{t['images']}** "
        f"(readable {t['readable']}, corrupt {t['corrupt']}) · "
        f"Missing captions: **{t['missing_caption']}**"
    )
    eff = result["effective_steps"]
    if "total_steps" in eff:
        lines.append(
            f"- Effective images: **{eff['total_effective_images']}** · "
            f"{eff['epochs']} epochs × {eff['steps_per_epoch']} steps = "
            f"**{eff['total_steps']} total steps** (batch {eff['batch_size']})"
        )
    else:
        lines.append(f"- Effective images (images × repeats): **{eff['total_effective_images']}**")
    res = result["resolution"]
    lines.append(
        f"- Short side: min {res['min_short_side']} / median "
        f"{res['median_short_side']} / max {res['max_short_side']} "
        f"(target {res['target']})"
    )
    lines.append(f"- Aspect buckets: {result['aspect_buckets']}")
    lines.append(f"- Colour modes: {result['modes']}")

    if result["concepts"]:
        lines.append("")
        lines.append("## Concepts")
        lines.append("| folder | concept | repeats | images | effective |")
        lines.append("|---|---|---:|---:|---:|")
        for c in result["concepts"]:
            lines.append(
                f"| {c['name']} | {c['concept']} | {c['repeats']} | "
                f"{c['images']} | {c['effective_images']} |"
            )

    lines.append("")
    lines.append("## Issues")
    if not result["issues"]:
        lines.append("✅ No image-level issues found.")
    for issue in result["issues"]:
        lines.append(
            f"- {C.severity_emoji(issue['severity'])} "
            f"**[{issue['severity'].upper()}] {issue['code']}** — {issue['message']}"
        )
        if issue["fix"]:
            lines.append(f"  - fix: {issue['fix']}")
        if issue["items"]:
            shown = ", ".join(Path(i).name for i in issue["items"][:5])
            lines.append(f"  - e.g. {shown}")
    return "\n".join(lines) + "\n"


# --- CLI ---------------------------------------------------------------------


def _parse_reso(text: str) -> tuple[int, int]:
    parts = [p for p in text.replace("x", ",").split(",") if p.strip()]
    if len(parts) == 1:
        v = int(parts[0])
        return v, v
    return int(parts[0]), int(parts[1])


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scan a LoRA dataset for image-level problems.")
    parser.add_argument(
        "path", help="train_data_dir (parent of <repeats>_<concept>) or an image folder"
    )
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--target-reso", default="1024,1024", help="WxH, e.g. 1024,1024")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument(
        "--prefer-json",
        action="store_true",
        help="accept experimental .json captions instead of requiring trainer-supported .txt",
    )
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--report", action="store_true", help="print markdown only")
    parser.add_argument("--output", default=None, help="write JSON to this file")
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        parser.error(f"path is not a directory: {root}")

    result = analyze_dataset(
        root,
        recursive=not args.no_recursive,
        epochs=args.epochs,
        batch_size=args.batch_size,
        target_reso=_parse_reso(args.target_reso),
        prefer_json=args.prefer_json,
    )

    out = Path(args.output) if args.output else None
    if args.json:
        print(C.dump_json(result, out))
    elif args.report:
        print(build_markdown(result))
        if out:
            C.dump_json(result, out)
    else:
        print(build_markdown(result))
        print()
        print(C.dump_json(result, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
