# Collect & tag — building a dataset from nothing

How the pipeline turns a **character name** into a captioned dataset, using two
external local tools. This is the front half of `lora-pipeline`; the back half
(train → validate → publish) is in [`validate-and-publish.md`](validate-and-publish.md).

Both tools run locally and are **environment-specific** — the paths/ports below are
this machine's defaults; override via the CLI flags / env vars noted per script.

---

## Phase 1 — COLLECT (Danbooru)

Tool: **DanbooruDownload** (`https://github.com/storyAura/DanbooruDownload`), a CLI
that pulls posts by tag. Driver: `lora-pipeline/scripts/collect.py`
(env `DANBOORU_DL_DIR`, default `C:\tools\DanbooruDownload`).

```
python collect.py --tag "my_character_(my_series)" --work "D:/work/mychar" --limit 200 --apply
```

Writes `<work>/raw/{id}.{ext}` + `{id}.txt` danbooru sidecars.

**The 2-tag gotcha (important).** Danbooru's anonymous API allows only **2 tags per
query**, and `rating:` / `score:` filters count as tags too. So:

- Query with the **single character tag only** — do not add `rating:safe` or
  `score:>10` server-side (they'd burn the tag budget and often 422).
- Set `save_tag_txt: true` and curate locally instead (Phase 3). `collect.py`
  already writes the right `download.yaml`.
- The character tag is the danbooru form, usually `name_(series)` lowercase with
  underscores — e.g. `my_character_(my_series)`. If unsure, confirm the exact tag
  on danbooru before a big pull.

Aim for **≥ 30–40 raw images** so ~20–35 survive curation.

---

## Phase 2 — TAG (WD14 via sd-image-sorter)

Tool: **sd-image-sorter** — a local FastAPI tagger with WD14 + the Anima caption
machinery. Run its `run.bat` → serves `http://127.0.0.1:8487` (env `SORTER_URL`). Models
`wd-eva02-large-tagger-v3` / `wd-swinv2-tagger-v3` / `camie-tagger-v2` /
`pixai-tagger-v0.9` ship with it. Driver: `lora-pipeline/scripts/tag_dataset.py`.

```
python tag_dataset.py --work "D:/work/mychar" --concept mychar --trigger mychar
```

This is **not** a naive WD14 dump. Anima's error cost is asymmetric (missing tags are
tolerated, wrong tags are harmful — see [`caption-guide.md`](caption-guide.md) →
*Anima tagging craft*, and the sd-image-sorter tagger audit report), so the flow uses a
clean tagger, the Anima section-order template, and the caption-paradox trait prune.

Contract (verified against the sd-image-sorter backend):

| Call | Body (key fields) | Purpose |
|---|---|---|
| `POST /api/scan` | `{folder_path, recursive:true}` → poll `/api/scan/progress` | index the concept folder |
| `POST /api/images/selection-token` | `{folder}` → `{selection_token}` | scope a token to the folder |
| `GET /api/images/selection-chunk` | `?selection_token=&offset=&limit=2000` | expand to `image_ids` |
| `POST /api/tag` | `{image_ids, model_name:"wd-eva02-large-tagger-v3", threshold:0.35, character_threshold:0.85, use_gpu, pre_tag_blacklist, max_tags_per_image:0}` → poll `/api/tag/progress` | WD14 tag |
| `POST /api/tags/trait-candidates` | `{selection_token, min_ratio:0.6}` → `{candidates:[{tag,family,ratio}]}` | list invariant identity traits |
| `POST /api/tags/export-batch` | see below | write Anima-format `.txt` |

Export body (Anima section-ordered, trait-pruned, single-line):

```json
{
  "selection_token": "<token>",
  "output_mode": "beside_image",
  "content_mode": "template",
  "template_options": { "preset_id": "anima_tags_only", "trigger": "<trigger>" },
  "training_purpose": "character",
  "blacklist": ["silver_hair", "green_eyes"],
  "dedupe_implications": true,
  "overwrite_policy": "overwrite"
}
```

**Why these fields (the rules that make or break an Anima LoRA):**

1. **`content_mode:"template"` + `preset_id:"anima"`/`"anima_tags_only"`** — this applies
   the model-card order `quality, safety, count, trigger, characters, series, @artists,
   general[. NL]`, maps danbooru ratings to Anima's `safe/sensitive/nsfw/explicit`,
   `@`-prefixes artists, converts `_`→space (keeping `score_*`), and single-lines the
   caption. A plain `tags`/`tags_nl` dump is *confidence-ordered* and skips all of this.
   Use `anima` when you also generated a VLM natural-language sentence, `anima_tags_only`
   otherwise (an empty NL slot is worse than none).
2. **`training_purpose:"character"` + a `trigger`** drops the character-NAME tag so the
   trigger carries identity. `"style"` instead drops style/artist tags and keeps content.
3. **`blacklist` = the invariant traits** from `/api/tags/trait-candidates` (ratio ≥ ~0.9)
   — hair/eye/skin/body markers the trigger should absorb. The driver prints every
   candidate (reviewed prune, never silent); transient states (`wet_hair`, `closed_eyes`)
   are excluded by the endpoint and stay taggable.
4. **Model choice matters** — `wd-eva02-large-tagger-v3` (best) or `wd-swinv2-tagger-v3`
   (lighter); **never** `toriigate-0.5` as a tagger (it invents anatomy — captioner only),
   and `pixai-tagger-v0.9` only inside consensus (`--consensus` → `/api/smart-tag/start`
   with a swinv2+eva02+pixai vote), because it hallucinates above its own threshold.
5. **Thresholds bind to the model** (0.35 general / 0.85 character for WD14). Keep the
   character threshold high — a hallucinated identity is worse than a missing tag.

CPU tagging (default) avoids contending with the trainer/ComfyUI for VRAM; pass `--gpu`
for speed. A natural-language sentence (`--nl`, Anima is hybrid) needs a VLM configured in
the sorter and uses `/api/smart-tag/start`.

The captions this produces match [`caption-guide.md`](caption-guide.md) →
*Anima tagging craft* exactly.

---

## Phase 3 — CURATE & BUILD (local, offline)

WD14 tags are only as good as the images. Curate **before** tagging so you tag a clean
set. Two drivers, both under `lora-pipeline/scripts/`:

**`curate.py`** — reads `raw/` + danbooru sidecars, writes `curation_manifest.json`
(keep/drop). Drops: multi-subject / comic / reference-sheet, **off-model content**
(genderswap / futanari / cosplay / male-present — these muddy a single-character
identity), **explicit** (unless `--keep-nsfw` — a SFW character LoRA learns identity
fine without it, and explicit art skews the trigger), short-side `< 512 px`, and any
image that fails to decode. (Discovered in practice: top danbooru fanart for a popular
character is full of genderswaps/futanari/cosplay — filtering on the sidecar tags
catches most of it. A few genderswaps are only visible to WD14, not the danbooru
sidecar, so a small amount can still slip through to the tag step.)

```
python curate.py --work "D:/work/mychar"     # report + manifest (non-destructive)
```

**`build_dataset.py`** — copies the keeps into the kohya `<repeats>_<concept>/` folder,
normalizing to RGB (RGBA/P flattened onto white → PNG). Repeats auto-pick from the
~1500-step formula `clamp(round(150 / keeps), 1, 10)`.

```
python build_dataset.py --work "D:/work/mychar" --concept mychar
```

Order matters: **collect → curate → build → tag → doctor.** Tag the *built* concept
folder (clean images), not `raw/`.

---

## Handoff to the doctor gate

After `tag_dataset.py`, the concept folder has images + trigger-first `.txt` captions.
Run the standard gate — nothing new here, this is the existing `dataset-doctor`:

```
doctor.py "<work>/dataset" --trigger <trigger> --epochs 10 --report
```

Fix per `dataset-doctor/SKILL.md`, re-check to PASS, then continue to
[`validate-and-publish.md`](validate-and-publish.md) → train.
