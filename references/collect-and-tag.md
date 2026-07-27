# Collect & tag — building a dataset from nothing

How the pipeline turns a **character name** into a captioned dataset, using two
external local tools. This is the front half of `lora-pipeline`; the back half
(train → validate → publish) is in [`validate-and-publish.md`](validate-and-publish.md).

Both tools run locally. The paths and ports below are conventional defaults; override
them with the CLI flags or environment variables noted per script.

---

## Phase 1 — COLLECT (Danbooru)

Tool: **DanbooruDownload** (`https://github.com/storyAura/DanbooruDownload`), a CLI
that pulls posts by tag. Driver: `lora-pipeline/scripts/collect.py`
(env `DANBOORU_DL_DIR`, default `C:\tools\DanbooruDownload`).

```
python collect.py --tag "my_character_(my_series)" --work "D:/work/mychar" --limit 200 --apply
```

Writes `<work>/raw/{id}.{ext}` + `{id}.txt` danbooru sidecars.

Numeric filenames are retained as Danbooru source URLs in `curation_manifest.json`.
That provenance is useful for review and attribution, but source availability is not a
license grant: use images you have the right to train on and follow the source site and
publishing platform rules. The pipeline records this information without turning an
uncertain rights judgment into an automatic blocker.

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

Tool: **[Rinne414/sd-image-sorter](https://github.com/Rinne414/sd-image-sorter)** — a
local FastAPI tagger with WD14 + the Anima caption machinery. The known-compatible
revision is `c449e3f3ab8057353955d8128ad46a6763daa5e9` or newer; the driver also checks
required OpenAPI paths before changing captions. Run `run.bat` → serves
`http://127.0.0.1:8487` (env `SORTER_URL`). Models
`wd-eva02-large-tagger-v3` / `wd-swinv2-tagger-v3` / `camie-tagger-v2` /
`pixai-tagger-v0.9` ship with it. Driver: `lora-pipeline/scripts/tag_dataset.py`.

```
python tag_dataset.py --dataset-dir "D:/work/mychar/dataset/5_mych4r" \
    --trigger mych4r --subject-tag 1girl
```

This is **not** a naive WD14 dump. Anima's official card says random tag dropout means
every relevant tag is not required; invented tags still describe the wrong target. The
flow therefore uses a precision-oriented WD starting point, the Anima section-order
template, and a reviewable caption-paradox trait heuristic.

Contract (verified against the sd-image-sorter backend):

| Call | Body (key fields) | Purpose |
|---|---|---|
| `POST /api/scan` | `{folder_path, recursive:true}` → poll `/api/scan/progress` | index the concept folder |
| `POST /api/images/selection-token` | `{folder}` → `{selection_token}` | scope a token to the folder |
| `GET /api/images/selection-chunk` | `?selection_token=&offset=&limit=2000` | expand to `image_ids` |
| `POST /api/tag` | `{image_ids, model_name, threshold:<per-model>, character_threshold:0.85, use_gpu, pre_tag_blacklist, max_tags_per_image:0}` → poll `/api/tag/progress` | WD14 tag |
| `POST /api/tags/trait-candidates` | `{selection_token, min_ratio:0.6}` → `{candidates:[{tag,family,ratio}]}` | list invariant identity traits |
| `POST /api/tags/export-batch` | see below | write Anima-format `.txt` |

Export body (Anima section-ordered, trait-pruned, single-line):

```json
{
  "selection_token": "<token>",
  "output_mode": "beside_image",
  "content_mode": "template",
  "template_options": {
    "preset_id": "anima_tags_only",
    "trigger": "<trigger>",
    "quality_override": ""
  },
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
   — hair/eye/skin/body markers the trigger should absorb. Frequency is a heuristic,
   not proof of identity. The driver writes candidates and selected tags to
   `<concept>.tag-audit.json`; transient states remain taggable.
4. **Model choice matters** — the suite defaults to `wd-eva02-large-tagger-v3` and offers
   `wd-swinv2-tagger-v3` as a lighter alternative. Their published validation metrics are
   starting evidence, not a guarantee on a new dataset. `--consensus` uses a 2-of-3
   swinv2+eva02+pixai vote and still requires review.
5. **Thresholds bind to the model.** Defaults use the published P=R points: EVA02
   `0.5296`, SwinV2 `0.2653`; override after reviewing a representative sample. The
   character threshold stays conservatively high at `0.85`.
6. **Unscored training images get no quality override.** Anima supports both human
   quality tags and `score_9` through `score_1`, but a constant label across every image
   is not evidence. Pass `--quality` only when the shared label is intentional.

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
catches most of it. Choose `--subject-tag 1girl|1boy|1other`; the filter rejects the
opposite subject instead of assuming every character is female. Numeric Danbooru
filenames are also recorded as source URLs in the manifest.)

```
python curate.py --work "D:/work/mychar" --subject-tag 1girl
```

**`build_dataset.py`** — copies the keeps into the kohya `<repeats>_<concept>/` folder,
normalizing to RGB (RGBA/P flattened onto white → PNG). Repeats auto-pick an initial
budget with `clamp(round(150 / keeps), 1, 10)`; doctor recomputes the real steps after
dedupe, and checkpoint validation decides when the result is good.

```
python build_dataset.py --work "D:/work/mychar" --concept mychar
```

Order matters: **collect → curate → build → tag → semantic review → doctor.** Tag the
*built* concept folder, then review `<concept>.tag-audit.json`: WD14 can expose subject
or multi-person mistakes absent from the original Danbooru sidecars. Warnings do not
auto-delete images or block training.

---

## Handoff to the doctor gate

After `tag_dataset.py`, the concept folder has images + Anima-sectioned `.txt` captions.
Run the standard gate — nothing new here, this is the existing `dataset-doctor`:

```
doctor.py "<work>/dataset" --trigger <trigger> --epochs 10 --report
```

Fix per `dataset-doctor/SKILL.md`, then continue after a PASS or after the user reviews
and accepts the remaining WARN findings. Training and validation continue in
[`validate-and-publish.md`](validate-and-publish.md).
