"""Audit the captions of a LoRA training dataset.

Pairs every image with its sidecar caption (``.txt`` or, for Anima, ``.json``)
and reports caption-level problems that the trainer never checks:

  * missing / empty captions
  * trigger-word presence and consistency (is it in every caption, and first?)
  * tag-frequency distribution (ubiquitous tags that get "baked in", rare noise)
  * over-/under-tagged images
  * negative/quality artefact tags that do not belong in training captions
  * underscore vs space inconsistency and duplicate tags within a caption
  * multi-line .txt captions (the trainer reads only the first line)
  * Anima JSON structure validation (recommended key order/types)

Usage:
    python check_captions.py <path> [--trigger zkz] [--no-prefer-json]
                             [--no-recursive] [--json] [--report] [--output FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

# The trainer ships an embedded Python whose ._pth file suppresses the usual
# "script dir on sys.path" behaviour, so make sibling imports explicit.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as C  # noqa: E402

# --- Tunable thresholds ------------------------------------------------------

UNDER_TAGGED = 5  # fewer than this many tags is suspiciously sparse
OVER_TAGGED = 45  # more than this many tags dilutes the signal
LONG_CAPTION_CHARS = 1500
UBIQUITOUS_PCT = 99.0  # tag present in >= this % of captions == "baked in"
TRIGGER_OK_PCT = 90.0  # trigger should appear in >= this % of captions
EMPTY_HIGH_PCT = 5.0
MAX_EXAMPLES = 12

# Negative-prompt / quality tags that usually should NOT be in a training
# caption (they describe what you do not want, or are watermark noise).
ARTIFACT_TAGS: frozenset[str] = frozenset(
    {
        "lowres", "worst quality", "low quality", "normal quality", "bad anatomy",
        "bad hands", "jpeg artifacts", "signature", "watermark", "username",
        "blurry", "text", "error", "cropped", "artist name", "logo",
    }
)

# Recommended Anima JSON caption key order.
ANIMA_JSON_ORDER = [
    "quality", "count", "character", "series", "artist",
    "appearance", "tags", "environment", "nl",
]
ANIMA_JSON_LIST_KEYS = {"appearance", "tags", "environment"}


# --- Tag parsing -------------------------------------------------------------


def split_tags(text: str) -> list[str]:
    """Split a comma-separated caption into normalised tags (lowercased, inner
    whitespace collapsed, empties dropped)."""
    tags: list[str] = []
    for raw in text.split(","):
        tag = " ".join(raw.split()).strip().lower()
        if tag:
            tags.append(tag)
    return tags


def flatten_json_caption(obj: dict) -> list[str]:
    """Collapse an Anima JSON caption into a flat tag list for frequency stats."""
    tags: list[str] = []
    for key in ("character", "series", "artist"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value.strip().lower())
    for key in ANIMA_JSON_LIST_KEYS:
        value = obj.get(key)
        if isinstance(value, list):
            tags.extend(str(v).strip().lower() for v in value if str(v).strip())
    return tags


def validate_anima_json(obj: dict) -> list[str]:
    """Return a list of human-readable structure problems (empty == valid)."""
    problems: list[str] = []
    if not isinstance(obj, dict):
        return ["caption JSON is not an object"]
    unexpected = [k for k in obj if k not in ANIMA_JSON_ORDER]
    if unexpected:
        problems.append(f"unexpected keys: {unexpected}")
    for key in ANIMA_JSON_LIST_KEYS:
        if key in obj and not isinstance(obj[key], list):
            problems.append(f"'{key}' should be a list")
    present = [k for k in obj if k in ANIMA_JSON_ORDER]
    expected_order = [k for k in ANIMA_JSON_ORDER if k in obj]
    if present != expected_order:
        problems.append(f"key order {present} != recommended {expected_order}")
    return problems


# --- Per-caption read --------------------------------------------------------


def load_caption(caption_path: Path) -> dict:
    """Read one caption file into {tags, char_len, fmt, empty, multiline, json_problems}."""
    fmt = caption_path.suffix.lower().lstrip(".")
    text = C.read_text(caption_path)
    if fmt == "json":
        try:
            obj = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            return {"fmt": "json", "tags": [], "char_len": len(text),
                    "empty": not text.strip(), "multiline": False,
                    "json_problems": [f"invalid JSON: {exc}"]}
        return {"fmt": "json", "tags": flatten_json_caption(obj),
                "char_len": len(text), "empty": not flatten_json_caption(obj),
                "multiline": False, "json_problems": validate_anima_json(obj)}
    tags = split_tags(text)
    # kohya's read_caption keeps only the first line (train_util.py:
    # ``caption.split("\n")[0]``) — anything after a newline never trains.
    return {"fmt": "txt", "tags": tags, "char_len": len(text),
            "empty": len(tags) == 0, "multiline": "\n" in text.strip(),
            "json_problems": []}


# --- Core analysis -----------------------------------------------------------


def analyze_captions(
    root: Path,
    recursive: bool = True,
    prefer_json: bool = True,
    trigger: Optional[str] = None,
) -> dict:
    root = Path(root)
    images = C.iter_images(root, recursive=recursive)

    total = len(images)
    captioned = 0
    empty: list[str] = []
    missing: list[str] = []
    tag_counts: Counter[str] = Counter()
    first_tag_counts: Counter[str] = Counter()
    under_tagged: list[str] = []
    over_tagged: list[str] = []
    long_caption: list[str] = []
    multiline: list[str] = []
    dup_within: list[str] = []
    artifact_hits: list[str] = []
    json_problem_files: list[dict] = []
    underscore_files = 0
    space_files = 0

    for image in images:
        cap_path = C.find_caption_path(image, prefer_json=prefer_json)
        if cap_path is None:
            missing.append(str(image))
            continue
        captioned += 1
        info = load_caption(cap_path)
        if info["empty"]:
            empty.append(str(cap_path))
            continue
        tags = info["tags"]

        seen: set[str] = set()
        has_dup = False
        for t in tags:
            tag_counts[t] += 1
            if t in seen:
                has_dup = True
            seen.add(t)
        if tags:
            first_tag_counts[tags[0]] += 1
        if has_dup:
            dup_within.append(str(cap_path))

        if len(tags) < UNDER_TAGGED:
            under_tagged.append(str(cap_path))
        if len(tags) > OVER_TAGGED:
            over_tagged.append(str(cap_path))
        if info["char_len"] > LONG_CAPTION_CHARS:
            long_caption.append(str(cap_path))
        if info["multiline"]:
            multiline.append(str(cap_path))
        if any(t in ARTIFACT_TAGS for t in tags):
            artifact_hits.append(str(cap_path))
        if any("_" in t for t in tags):
            underscore_files += 1
        else:
            space_files += 1
        if info["json_problems"]:
            json_problem_files.append({"file": str(cap_path), "problems": info["json_problems"]})

    effective_caption_count = captioned - len(empty)
    ubiquitous = [
        {"tag": tag, "count": cnt, "pct": C.pct(cnt, effective_caption_count)}
        for tag, cnt in tag_counts.most_common()
        if C.pct(cnt, effective_caption_count) >= UBIQUITOUS_PCT
    ]
    rare = [tag for tag, cnt in tag_counts.items() if cnt == 1]
    top = [{"tag": t, "count": c} for t, c in tag_counts.most_common(25)]

    trigger_info = _analyze_trigger(
        trigger, tag_counts, first_tag_counts, effective_caption_count
    )

    issues = _build_issues(
        total=total, captioned=captioned, missing=missing, empty=empty,
        under_tagged=under_tagged, over_tagged=over_tagged, dup_within=dup_within,
        artifact_hits=artifact_hits, ubiquitous=ubiquitous, trigger_info=trigger_info,
        json_problem_files=json_problem_files, underscore_files=underscore_files,
        space_files=space_files, long_caption=long_caption, multiline=multiline,
    )

    return {
        "tool": "check_captions",
        "root": str(root),
        "totals": {
            "images": total,
            "captioned": captioned,
            "missing": len(missing),
            "empty": len(empty),
        },
        "tags": {
            "unique": len(tag_counts),
            "ubiquitous": ubiquitous,
            "rare_count": len(rare),
            "top": top,
        },
        "trigger": trigger_info,
        "per_caption": {
            "under_tagged": len(under_tagged),
            "over_tagged": len(over_tagged),
            "duplicate_tags_within": len(dup_within),
            "long_caption": len(long_caption),
            "multiline": len(multiline),
            "underscore_files": underscore_files,
            "space_files": space_files,
        },
        "json_validation": {
            "files_with_problems": len(json_problem_files),
            "examples": json_problem_files[:MAX_EXAMPLES],
        },
        "missing_examples": missing[:MAX_EXAMPLES],
        "issues": [i.to_dict() for i in C.sort_issues(issues)],
    }


def _analyze_trigger(trigger, tag_counts, first_tag_counts, captioned) -> dict:
    if captioned <= 0:
        return {"requested": trigger, "status": "no_captions"}
    if trigger:
        key = trigger.strip().lower()
        present = tag_counts.get(key, 0)
        first = first_tag_counts.get(key, 0)
        return {
            "requested": trigger,
            "presence_pct": C.pct(present, captioned),
            "first_position_pct": C.pct(first, captioned),
            "consistent": C.pct(present, captioned) >= TRIGGER_OK_PCT,
        }
    # Infer a candidate: highest presence, tie-broken by first-position rate.
    if not tag_counts:
        return {"requested": None, "status": "no_tags"}
    candidate = max(
        tag_counts,
        key=lambda t: (tag_counts[t], first_tag_counts.get(t, 0)),
    )
    return {
        "requested": None,
        "inferred_candidate": candidate,
        "presence_pct": C.pct(tag_counts[candidate], captioned),
        "first_position_pct": C.pct(first_tag_counts.get(candidate, 0), captioned),
    }


def _build_issues(**kw) -> list[C.Issue]:
    issues: list[C.Issue] = []
    total = kw["total"]
    captioned = kw["captioned"]

    if total == 0:
        issues.append(C.Issue(C.SEV_CRITICAL, "no_images",
                              "No images found to check captions against.",
                              "Verify the dataset path."))
        return issues

    if kw["empty"]:
        sev = C.SEV_HIGH if C.pct(len(kw["empty"]), max(1, captioned)) > EMPTY_HIGH_PCT else C.SEV_MEDIUM
        issues.append(C.Issue(sev, "empty_captions",
                              f"{len(kw['empty'])} caption file(s) are empty.",
                              "Re-tag with WD14 (POST /api/interrogate) or write captions.",
                              kw["empty"][:MAX_EXAMPLES]))

    ti = kw["trigger_info"]
    if ti.get("requested") and not ti.get("consistent", False):
        issues.append(C.Issue(C.SEV_HIGH, "trigger_inconsistent",
                              f"Trigger '{ti['requested']}' only appears in {ti.get('presence_pct', 0)}% "
                              f"of captions (want >= {TRIGGER_OK_PCT}%).",
                              "Add the trigger word as the first tag in every caption."))

    if kw["multiline"]:
        issues.append(C.Issue(C.SEV_HIGH, "multiline_caption",
                              f"{len(kw['multiline'])} .txt caption(s) span multiple lines; "
                              "the trainer reads ONLY the first line, the rest is silently ignored.",
                              "Merge each caption into one line: trigger, tags, "
                              "then '. ' before any natural-language sentence.",
                              kw["multiline"][:MAX_EXAMPLES]))

    if kw["artifact_hits"]:
        issues.append(C.Issue(C.SEV_MEDIUM, "artifact_tags",
                              f"{len(kw['artifact_hits'])} caption(s) contain negative/quality artefact tags "
                              "(e.g. 'worst quality', 'watermark').",
                              "Remove negative-prompt tags from training captions.",
                              kw["artifact_hits"][:MAX_EXAMPLES]))

    if kw["ubiquitous"] and not ti.get("requested"):
        baked = [u["tag"] for u in kw["ubiquitous"]]
        issues.append(C.Issue(C.SEV_MEDIUM, "ubiquitous_tags",
                              f"Tag(s) present in nearly every caption: {baked[:8]}. "
                              "These get 'baked' into the concept.",
                              "Keep ONE intended trigger ubiquitous; prune the rest if unintended."))

    if kw["over_tagged"]:
        issues.append(C.Issue(C.SEV_MEDIUM, "over_tagged",
                              f"{len(kw['over_tagged'])} caption(s) have > {OVER_TAGGED} tags.",
                              "Trim weak/irrelevant tags; they dilute learning.",
                              kw["over_tagged"][:MAX_EXAMPLES]))
    if kw["under_tagged"]:
        issues.append(C.Issue(C.SEV_LOW, "under_tagged",
                              f"{len(kw['under_tagged'])} caption(s) have < {UNDER_TAGGED} tags.",
                              "Add descriptive tags so the model can disentangle the concept.",
                              kw["under_tagged"][:MAX_EXAMPLES]))

    if kw["dup_within"]:
        issues.append(C.Issue(C.SEV_LOW, "duplicate_tags",
                              f"{len(kw['dup_within'])} caption(s) repeat a tag within the same file.",
                              "De-duplicate tags inside each caption.",
                              kw["dup_within"][:MAX_EXAMPLES]))

    if kw["underscore_files"] and kw["space_files"]:
        issues.append(C.Issue(C.SEV_LOW, "underscore_inconsistent",
                              f"Mixed tag style: {kw['underscore_files']} file(s) use underscores, "
                              f"{kw['space_files']} use spaces.",
                              "Pick one (WD14 default replaces underscores with spaces) and apply consistently."))

    if kw["json_problem_files"]:
        issues.append(C.Issue(C.SEV_MEDIUM, "json_structure",
                              f"{len(kw['json_problem_files'])} Anima JSON caption(s) have structure problems.",
                              f"Use the order {ANIMA_JSON_ORDER}.",
                              [f["file"] for f in kw["json_problem_files"]][:MAX_EXAMPLES]))

    if kw["long_caption"]:
        issues.append(C.Issue(C.SEV_LOW, "long_caption",
                              f"{len(kw['long_caption'])} caption(s) exceed {LONG_CAPTION_CHARS} chars.",
                              "Very long captions may exceed token limits and get truncated."))
    return issues


# --- Reporting ---------------------------------------------------------------


def build_markdown(result: dict) -> str:
    lines: list[str] = []
    t = result["totals"]
    lines.append(f"# Caption check — `{result['root']}`")
    lines.append("")
    lines.append(f"- Images: **{t['images']}** · captioned **{t['captioned']}** · "
                 f"missing **{t['missing']}** · empty **{t['empty']}**")
    lines.append(f"- Unique tags: **{result['tags']['unique']}** "
                 f"(rare/one-off: {result['tags']['rare_count']})")
    tr = result["trigger"]
    if tr.get("requested"):
        lines.append(f"- Trigger `{tr['requested']}`: present in **{tr.get('presence_pct', 0)}%** "
                     f"(first tag in {tr.get('first_position_pct', 0)}%) — "
                     f"{'OK' if tr.get('consistent') else 'INCONSISTENT'}")
    elif tr.get("inferred_candidate"):
        lines.append(f"- Inferred trigger candidate: `{tr['inferred_candidate']}` "
                     f"(present {tr.get('presence_pct', 0)}%, first {tr.get('first_position_pct', 0)}%)")
    if result["tags"]["ubiquitous"]:
        baked = ", ".join(f"{u['tag']} ({u['pct']}%)" for u in result["tags"]["ubiquitous"][:8])
        lines.append(f"- Ubiquitous tags: {baked}")

    lines.append("")
    lines.append("## Issues")
    if not result["issues"]:
        lines.append("✅ No caption-level issues found.")
    for issue in result["issues"]:
        lines.append(f"- {C.severity_emoji(issue['severity'])} "
                     f"**[{issue['severity'].upper()}] {issue['code']}** — {issue['message']}")
        if issue["fix"]:
            lines.append(f"  - fix: {issue['fix']}")
    return "\n".join(lines) + "\n"


# --- CLI ---------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit LoRA dataset captions.")
    parser.add_argument("path", help="train_data_dir or an image folder")
    parser.add_argument("--trigger", default=None, help="expected trigger word / activation tag")
    parser.add_argument("--no-recursive", action="store_true")
    parser.add_argument("--no-prefer-json", action="store_true", help="match .txt before .json")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.is_dir():
        parser.error(f"path is not a directory: {root}")

    result = analyze_captions(
        root,
        recursive=not args.no_recursive,
        prefer_json=not args.no_prefer_json,
        trigger=args.trigger,
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
