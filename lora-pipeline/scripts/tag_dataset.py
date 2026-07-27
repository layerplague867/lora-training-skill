"""Phase 2 — TAG (Anima-correct). Drive sd-image-sorter to auto-tag a concept folder
and export **Anima-format** captions: model-card section order, @artist prefix, safety
vocab, single line — and, for character LoRAs, the caption-paradox trait prune.

Why this is not a naive WD14 dump (the whole point — see references/collect-and-tag.md
and the sd-image-sorter tagger audit report):
- Anima's error cost is ASYMMETRIC — it was pretrained with tag dropout, so *missing*
  tags are tolerated but *wrong/invented* tags are harmful. So we prefer a clean tagger
  (eva02 / swinv2), not maximum recall (pixai hallucinates above its own threshold).
- WD14 emits tags in CONFIDENCE order, which interleaves character/artist among generals
  and VIOLATES the Anima model-card order. We export via the `anima` template so tags are
  sectioned: quality → safety → count → trigger → characters → copyright → @artists →
  general → NL, single-lined (kohya reads only line 1).
- The CAPTION PARADOX: for a character LoRA, invariant identity (hair/eye color, body
  traits) should bake into the TRIGGER, not be re-stated in every caption. We fetch trait
  candidates and blacklist the high-frequency ones so the trigger absorbs identity. This
  is a *reviewed* prune (we print every candidate), never silent.

Flow (sd-image-sorter, http://127.0.0.1:8487, env SORTER_URL):
  POST /api/scan                    index the folder
  POST /api/images/selection-token  scope a token to the folder; expand ids via /selection-chunk
  POST /api/tag                     WD14 (eva02 default); poll /api/tag/progress
  POST /api/tags/trait-candidates   (character) list identity traits ≥ min_ratio
  POST /api/tags/export-batch       content_mode=template, preset=anima, trigger, prune blacklist

Usage:
  python tag_dataset.py --work "D:/work/mychar" --concept mychar --trigger mychar
  python tag_dataset.py --work "D:/work/mychar" --concept mychar --trigger mychar --model wd-swinv2-tagger-v3
  python tag_dataset.py --work "D:/work/mychar" --concept mychar --trigger mychar --style
  python tag_dataset.py ... --consensus          # multi-tagger vote (kills hallucinations)
  python tag_dataset.py ... --no-trait-prune     # keep identity traits in captions
Environment overrides:
  SORTER_URL   base URL of sd-image-sorter (default http://127.0.0.1:8487)
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

SORTER = os.environ.get("SORTER_URL", "http://127.0.0.1:8487").rstrip("/")

# Never store these as tags: negative-prompt / meta noise + WD14 rating words.
# (Rating is placed once in the template's {safety} slot; these must not leak as tags.)
PRE_TAG_BLACKLIST = [
    "general",
    "sensitive",
    "questionable",
    "explicit",
    "watermark",
    "signature",
    "artist_name",
    "web_address",
    "jpeg_artifacts",
    "text",
    "english_text",
    "commentary",
    "commentary_request",
    "logo",
    "username",
    "dated",
    "twitter_username",
    "patreon_username",
    "text_focus",
]

# NOTE on STYLE LoRAs: style/era/medium/artist tags (1990s_(style), retro_artstyle,
# *_(medium), @artist, …) are stripped by the SORTER when we export with
# training_purpose="style" — it drops them by tag CATEGORY (semantic classifier,
# pattern-based), not by any hand-list here. So the trigger absorbs the look and
# there is deliberately no style word-list in this file: a list can't enumerate
# every style tag, but the category rule generalises. (Requires the sorter build
# with the tag_training_filters category-union fix.)


def _req(
    path: str, body: dict | None = None, method: str | None = None, timeout: int = 120
) -> dict:
    url = SORTER + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method or ("POST" if body is not None else "GET"),
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — local trusted service
        return json.loads(r.read().decode())


def poll(
    path: str, done=("done", "completed", "idle", "error", "cancelled"), tries=1200
) -> dict:
    last = None
    for _ in range(tries):
        p = _req(path, timeout=30)
        st = p.get("status")
        key = (st, p.get("processed"), p.get("total"))
        if key != last:
            print(
                f"    {st} {p.get('processed', '')}/{p.get('total', '')} {p.get('message', '')}",
                flush=True,
            )
            last = key
        if st in done:
            return p
        time.sleep(2)
    return {}


def selection_token(folder: Path) -> str:
    r = _req("/api/images/selection-token", {"folder": str(folder)})
    return r["selection_token"]


def expand_ids(token: str) -> list[int]:
    ids: list[int] = []
    offset = 0
    while True:
        r = _req(
            f"/api/images/selection-chunk?selection_token={token}&offset={offset}&limit=2000",
            timeout=60,
        )
        ids.extend(r.get("image_ids", []))
        if not r.get("has_more"):
            break
        offset = r.get("next_offset", offset + 2000)
    return ids


def tag_booru(
    ids: list[int], model: str, thr: float, char_thr: float, gpu: bool, retag: bool
) -> None:
    print(
        f"  tag: POST /api/tag  model={model} thr={thr} char_thr={char_thr} gpu={gpu}"
    )
    _req(
        "/api/tag",
        {
            "image_ids": ids,
            "model_name": model,
            "threshold": thr,
            "character_threshold": char_thr,
            "use_gpu": gpu,
            "retag_all": retag,
            "pre_tag_blacklist": PRE_TAG_BLACKLIST,
            "max_tags_per_image": 0,
        },
    )
    poll("/api/tag/progress")


def tag_smart(
    token: str,
    purpose: str,
    trigger: str,
    gpu: bool,
    thr: float,
    char_thr: float,
    consensus: bool,
    nl: bool,
) -> None:
    body = {
        "selection_token": token,
        "training_purpose": purpose,
        "trigger_word": trigger,
        "merge_strategy": "replace",
        "use_gpu": gpu,
        "general_threshold": thr,
        "character_threshold": char_thr,
        "enable_wd14": True,
        "enable_vlm": nl,
        "natural_language_mode": "vlm",
    }
    if consensus:
        body["taggers"] = [
            {"model": "wd-swinv2-tagger-v3"},
            {"model": "wd-eva02-large-tagger-v3"},
            {"model": "pixai-tagger-v0.9"},
        ]
        body["consensus_min"] = 2
    else:
        body["tagger_model"] = "wd-eva02-large-tagger-v3"
    print(f"  smart-tag: consensus={consensus} nl(vlm)={nl}")
    r = _req("/api/smart-tag/start", body)
    job = r.get("job_id") or r.get("id")
    poll(f"/api/smart-tag/progress?job_id={job}")


def trait_prune(token: str, min_ratio: float, apply_ratio: float) -> list[str]:
    """Return trait tags to blacklist so the trigger absorbs identity. Prints all candidates
    (reviewable — never a silent delete)."""
    r = _req(
        "/api/tags/trait-candidates",
        {"selection_token": token, "min_ratio": min_ratio, "limit": 100},
    )
    cands = r.get("candidates", [])
    if not cands:
        print("  trait-prune: no identity traits above ratio — nothing to prune.")
        return []
    print(
        f"  trait-prune candidates (of {r.get('total_images')} imgs) — auto-prune ratio ≥ {apply_ratio}:"
    )
    prune: list[str] = []
    for c in cands:
        mark = "PRUNE" if c["ratio"] >= apply_ratio else "keep "
        if c["ratio"] >= apply_ratio:
            prune.append(c["tag"])
        print(
            f"    [{mark}] {c['tag']:<28} {c['family']:<6} ratio={c['ratio']:.2f} ({c['count']}x)"
        )
    print(
        f"  → blacklisting {len(prune)} invariant traits (trigger will carry them). "
        f"Re-run with --trait-ratio / --no-trait-prune to adjust."
    )
    return prune


def export_anima(
    token: str, trigger: str, purpose: str, preset: str, prune: list[str]
) -> dict:
    body = {
        "selection_token": token,
        "output_mode": "beside_image",
        "content_mode": "template",
        "template_options": {"preset_id": preset, "trigger": trigger},
        "training_purpose": purpose,
        "blacklist": prune,
        "dedupe_implications": True,
        "overwrite_policy": "overwrite",
    }
    print(
        f"  export: content_mode=template preset={preset} purpose={purpose} prune={len(prune)}"
    )
    return _req("/api/tags/export-batch", body)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Anima-format WD14 tagging (section-ordered, trait-pruned)."
    )
    ap.add_argument("--work", required=True)
    ap.add_argument(
        "--concept", required=True, help="concept folder base name, e.g. mychar"
    )
    ap.add_argument(
        "--trigger", required=True, help="trigger word (absorbs invariant identity)"
    )
    ap.add_argument(
        "--style",
        action="store_true",
        help="style LoRA (training_purpose=style): the sorter strips style/medium/artist "
        "tags by CATEGORY so the trigger absorbs the look; content + character tags kept; "
        "no identity trait prune",
    )
    ap.add_argument(
        "--model",
        default="wd-eva02-large-tagger-v3",
        help="tagger: wd-eva02-large-tagger-v3 (best) | wd-swinv2-tagger-v3 (lighter)",
    )
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--character-threshold", type=float, default=0.85)
    ap.add_argument(
        "--nl",
        action="store_true",
        help="add a natural-language sentence (needs a VLM in the sorter)",
    )
    ap.add_argument(
        "--consensus",
        action="store_true",
        help="multi-tagger vote (swinv2+eva02+pixai) to kill hallucinations",
    )
    ap.add_argument(
        "--trait-ratio",
        type=float,
        default=0.9,
        help="auto-prune traits appearing in ≥ this fraction (default 0.9)",
    )
    ap.add_argument(
        "--min-ratio",
        type=float,
        default=0.6,
        help="trait-candidate reporting floor (default 0.6)",
    )
    ap.add_argument(
        "--no-trait-prune", action="store_true", help="keep identity traits in captions"
    )
    ap.add_argument(
        "--gpu",
        action="store_true",
        help="GPU tagging (default CPU — avoids VRAM contention)",
    )
    ap.add_argument(
        "--retag",
        action="store_true",
        help="force re-tag (else only untagged images are tagged)",
    )
    a = ap.parse_args()

    purpose = "style" if a.style else "character"
    preset = "anima" if a.nl else "anima_tags_only"  # NL slot only fills when a VLM ran

    work = Path(a.work).resolve()
    ds = work / "dataset"
    matches = (
        [p for p in ds.glob(f"*_{a.concept}") if p.is_dir()] if ds.is_dir() else []
    )
    if not matches:
        print(
            f"ERROR: no <repeats>_{a.concept} folder under {ds} — run build_dataset.py first."
        )
        return 2
    concept_dir = matches[0]

    print(f"scan   : {concept_dir}")
    # cleanup_missing drops stale DB rows from a previous build (so a rebuilt/curated
    # folder re-indexes to exactly its current files, not a stale superset).
    _req(
        "/api/scan",
        {
            "folder_path": str(concept_dir),
            "recursive": True,
            "cleanup_missing": True,
            "force_reparse": True,
        },
    )
    poll("/api/scan/progress", done=("done", "completed", "idle", "error", "cancelled"))
    token = selection_token(concept_dir)
    ids = expand_ids(token)
    print(f"ids    : {len(ids)} images")
    if not ids:
        print("ERROR: sorter indexed 0 images for this folder.")
        return 2

    if a.consensus or a.nl:
        tag_smart(
            token,
            purpose,
            a.trigger,
            a.gpu,
            a.threshold,
            a.character_threshold,
            a.consensus,
            a.nl,
        )
    else:
        tag_booru(ids, a.model, a.threshold, a.character_threshold, a.gpu, a.retag)

    # Character: prune invariant identity traits so the trigger absorbs them.
    # Style: nothing to prune here — the sorter strips style/medium/artist tags by
    # CATEGORY at export (training_purpose="style"), so the trigger carries the look.
    prune: list[str] = []
    if purpose == "character" and not a.no_trait_prune:
        prune = trait_prune(token, a.min_ratio, a.trait_ratio)

    res = export_anima(token, a.trigger, purpose, preset, prune)
    print(
        "  ->",
        json.dumps(
            {
                k: res.get(k)
                for k in ("exported", "skipped", "error_count", "content_mode")
            }
        ),
    )
    n_txt = len(list(concept_dir.glob("*.txt")))
    print(
        f"\ncaptions written: {n_txt}  (Anima order: quality, safety, count, {a.trigger}, chars, series, @artists, general)"
    )
    print(f'next: doctor.py "{ds}" --trigger {a.trigger} --epochs 10 --report')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
