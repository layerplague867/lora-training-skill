# Caption guide — captions that actually train well

How to caption a LoRA dataset for lora-scripts-next, and what `dataset-doctor`
checks. The format below is **verified** against the Anima official model card
and the trainer's own source code (SD-Trainer v2.7.0, vendored kohya
sd-scripts) — see [Evidence](#evidence) at the bottom.

---

## The verified format — one line, comma tags, period before natural language

```
<quality/meta/safety>, <count>, <trigger>, <tag>, …, <tag>. <Natural-language sentences.>
```

- **Trigger ↔ surrounding tags: comma.** Character triggers use no special
  marker; place them in the character section after quality/meta/safety and count.
- **tags ↔ natural language: period + space.** This is the transition Anima's
  own model card demonstrates verbatim:

  > `masterpiece, best quality, @big chungus. An anime girl with medium-length blonde hair is...`

  A comma also works (the card says tags and natural language mix "in
  arbitrary order"), but the period is the documented example — prefer it.
- **Inside the natural-language part: normal prose punctuation.** Sentences
  end with `. `; commas inside a sentence are ordinary grammar. The official
  NL examples are plain prose ("Digital artwork of Fern from Sousou no
  Frieren, with long purple hair and purple eyes, wearing a black coat…").
  Keep it to 1–3 sentences, all on the same line.
- **Never a newline.** Two independent reasons:
  1. The trainer keeps only the **first line** of a `.txt` caption
     (`train_util.py`: `caption = caption.split("\n")[0]`) — everything after
     a newline is silently dropped at training time, with no warning.
  2. Anima reserves "first line + newline" for its *dataset tag* format
     (`ye-pop` / `deviantart`), so newlines also shift the caption into the
     wrong training distribution.
- The natural-language part is **optional** — Anima was trained on tags-only,
  NL-only, and mixed captions.

Full example:

```
safe, 1girl, zkz, solo, long hair, brown hair, school uniform, classroom. An anime girl with long brown hair stands by the classroom window.
```

### Official Anima tag order

```
[quality/meta/year/safety] [1girl/1boy/1other] [character] [series] [artist] [general tags]
```

All comma-separated; order *within* each section is free. Lowercase, spaces
instead of underscores (score tags like `score_7` are the only underscore
tags).

### Official recommended quality tags (the `[quality/meta]` slot)

For the Anima base model, the current recommended generation prefix is:

```
masterpiece, best quality, score_7, safe
```

For Anima-Aesthetic, omit `score_*`; quality tags are optional. Two rules:

- **At generation time (prompts + sample gallery):** always lead with this prefix.
  `lora-pipeline`'s `validate.py` and the generated model card both use exactly
  `masterpiece, best quality, score_7, safe` for Anima base.
- **In training captions:** human quality and `score_9` through `score_1` are valid
  conditional labels only when they describe that image. Do not stamp one quality
  label over an unscored dataset. Source-noise tags such as `watermark`, `signature`,
  and `jpeg artifacts` should still be removed.

### Why commas are load-bearing (trainer machinery)

When `shuffle_caption`, `caption_tag_dropout_rate` or `token_warmup_step` is
active, the trainer splits the caption on `caption_separator` (default `,`),
shuffles/drops those comma units, and re-joins them with `", "`. Consequences:

- Periods are **not** unit boundaries — a period-separated caption is one
  giant token to the shuffler.
- A natural-language sentence containing commas gets shredded into pseudo-tags
  and shuffled/dropped along with the real ones. If you must combine shuffle
  with NL, pin a fixed prefix (trigger) *and* fixed suffix (NL) with
  `keep_tokens_separator` (e.g. `|||`): `trigger ||| tags… ||| nl sentence`.
- This suite's Anima defaults keep `shuffle_caption=false` (forced by
  `cache_text_encoder_outputs=true`), so captions are fed **verbatim** and the
  period transition is safe.

The caption text enters the Qwen3 tokenizer raw — no chat template, no
preprocessing (`strategy_anima.py`). Punctuation has no special meaning to the
trainer; the only thing that matters is matching what the base model saw
during pretraining, i.e. the official format above.

---

## Caption files

Captions are **sidecar files next to each image, same stem**:

```
5_zkz/
  img001.png
  img001.txt
```

`.txt`, **one single line**, in the verified format above. This is what the
WD14 tagger writes and what every kohya-based trainer reads.

### Anima structured `.json` — ⚠️ unverified, don't rely on it

SD-Trainer v2.7.0's UI advertises a `prefer_json_caption` option ("read a
same-stem `.json` first") with a recommended structure:

```
quality → count → character → series → artist → appearance[] → tags[] → environment[] → nl
```

**However, no code in the v2.7.0 install actually reads `.json` sidecars.**
The flag exists only in the UI schema (`mikazuki/schema/sd3-lora.ts`) and the
backend's field pass-through list (`anima_backend/adapter.py`); the vendored
sd-scripts `read_caption()` only opens `caption_extension` text files. Until
an end-to-end test proves otherwise (tracked in `TODO.md`), **write captions
as `.txt`** — a `.json` sidecar may be silently ignored, leaving the image
effectively uncaptioned.

`dataset-doctor` still validates `.json` structure for datasets that already
have them (key order above), and `fix_dataset.py` can write the trigger into
their `character` field — but treat `.txt` as the source of truth.

---

## The trigger word (activation tag)

The single most important caption decision for a **character/concept LoRA**.

- Pick a **short, rare, non-dictionary token** so it does not collide with the
  base model's existing concepts (`zkz`, `mych4r`, `ohwx_girl` — not `mychar` or
  `girl`).
- Put it in the documented character section in every caption. It need not be the
  first comma-separated item when quality/meta/safety and count precede it.
- It must appear in **~100% of captions** — `dataset-doctor --trigger zkz` reports
  presence and flags inconsistent coverage.
- For Anima, pass it through `tag_dataset.py --trigger` so template export places it in
  the documented section. The trainer's generic tagger uses `additional_tags` for
  other base-model paths (see `trainer-api.md`).
- **Style/artist LoRA: use Anima's `@` artist namespace** (`@mystyle`). The
  official card is explicit that artists must be prefixed with `@` — "the
  effect will be very weak without it". Do **not** use `@` for character
  triggers; it means "artist" to the base model.

### The caption paradox (what to tag vs. omit)

> **Tag what you want to be able to change later; omit what you want baked into
> the trigger.**

- A **character** LoRA: tag the trigger + the things that *vary* (pose, outfit,
  expression, background, camera). Do **not** tag the character's invariant
  identity features you want fused into the trigger (unless you want to be able
  to toggle them). Over-tagging invariant features spreads the identity across
  many tags and weakens the trigger.
- A **style** LoRA: use an `@`-prefixed trigger (see above). Tag content
  normally; do **not** describe "the style" in words — the weights learn it.
  Keep captions plain.

`dataset-doctor` surfaces **ubiquitous tags** (present in ~every caption). Exactly
one of those should be your intended trigger; the rest are usually accidental
bake-ins to prune.

---

## Anima tagging craft — precision-oriented rules

Anima was pretrained on tags, natural language, combinations of both, and random tag
dropout. The official card therefore says every relevant tag is not required. That does
not quantify the cost of false positives, but invented tags still describe the wrong
training target, so prefer reviewed, high-precision captions over maximum recall.
`lora-pipeline/scripts/tag_dataset.py` applies the reproducible rules below.

### 1. Section order, not confidence order

A raw WD14 dump sorts tags by **confidence descending**, which scatters
character/series/artist tags among the generals and *violates the Anima model-card
order*. Emit the documented sections instead:

```
{quality}, {safety}, {count}, {trigger}, {characters}, {series}, {@artists}, {general}. {NL}
```

`masterpiece, best quality, score_7, safe, 1girl, mych4r, silver hair, … . An anime girl stands …`

Doing this requires knowing each tag's **category** (WD14 tags carry general vs
character vs rating). The sd-image-sorter `template` export with `preset_id="anima"`
applies this ordering, the `@`-artist prefix, single-lining, and the safety mapping
automatically — use it rather than hand-concatenating tags.

### 2. Safety vocabulary is Anima's, not danbooru's

Anima's rating words are **`safe / sensitive / nsfw / explicit`** — note **`nsfw`**,
which danbooru doesn't have. Map danbooru → Anima: `general→safe`,
`sensitive→sensitive`, **`questionable→nsfw`**, `explicit→explicit`, place the rating
**once** in the `{safety}` slot, and **strip rating words out of the general tag
list** (a caption must never carry two contradictory ratings). Many character-LoRA
recipes drop the rating token entirely — either is defensible; what's wrong is leaving
raw `questionable`/`general` in the tag body.

### 3. Quality tags: use a measured label or omit it

Anima supports human labels (`masterpiece` through `worst quality`) and aesthetic
labels (`score_9` through `score_1`). Derive them per image from a human or compatible
scorer and omit them when unscored. `tag_dataset.py` explicitly sends an empty quality
override by default so the sorter's preset cannot stamp one label over every image.

### 4. The caption-paradox prune, done properly (character LoRAs)

"Tag what varies, omit what should bake into the trigger" — concretely, three levels:

1. **Drop the character-NAME tag** (`furina_(genshin_impact)`) once a trigger word
   carries the identity. (The `training_purpose="character"` export filter does this
   when a trigger is set.)
2. **Prune invariant TRAIT tags** — hair color/length, eye color, skin, fixed body
   markers — so the trigger absorbs them. But **keep transient states** (`wet_hair`,
   `closed_eyes`, `hair_ornament`, `adjusting_hair`): those *vary*, so they must stay
   taggable.
3. **Only prune a trait that's actually invariant** — i.e. it appears in a high
   fraction (≈ **≥0.9**) of the set. A one-off "wet hair" in one shot must NOT be
   pruned. sd-image-sorter's `trait-candidates` endpoint computes these ratios;
   `tag_dataset.py` blacklists the ≥0.9 ones and writes every candidate and decision
   to `<concept>.tag-audit.json`; printing is not considered human approval.

**Style LoRAs invert this:** prune the *style/artist* tags (so the style isn't named
in every caption — the trigger carries it) and **keep** all content/subject tags;
skip trait-pruning entirely.

### 5. Pick a documented tagger and review a sample

The two default WD14 models publish different validation metrics and operating points.
Those model-card numbers are useful starting evidence, but they are not a direct benchmark
on your dataset and do not prove either model is hallucination-free:

| model | use | why |
|---|---|---|
| `wd-eva02-large-tagger-v3` | suite default | published v1.0 P=R threshold `0.5296`, F1 `0.4772`; heavier runtime |
| `wd-swinv2-tagger-v3` | lighter alternative | published v2.0 P=R threshold `0.2653`, F1 `0.4541` |
| `pixai-tagger-v0.9` | optional consensus member | different model/calibration; this suite does not use it alone by default |
| VLM captioners | optional NL sentence | use for prose, not as a drop-in replacement for category-aware WD tag rows |

**Consensus** keeps a tag when at least two of swinv2, eva02, and pixai agree. It can
reduce single-model errors, but it also changes recall and calibration; treat it as an
optional mode and inspect the resulting audit rather than assuming it is strictly better.

### 6. Thresholds are per-model, not global

The published P=R points differ substantially: EVA02 v1.0 is `0.5296`, while SwinV2
v2.0 is `0.2653`. They are transparent starting points, not universal optima;
calibrate upward when a reviewed sample shows false positives. `tag_dataset.py` binds
these defaults to the selected model and requires an explicit threshold for unknown
models. Keep the **character threshold conservative (≈0.85)**: character-name tags are
especially costly when wrong because it teaches the wrong identity; review a sample and
raise or lower the threshold from evidence.

### 7. Small traps that silently degrade captions

- **Kaomoji** (`^_^`, `>_<`, `0_0`) are **real** WD14 tags — don't strip them as
  "symbols" and don't underscore-normalize them into `^ ^`.
- **Collapse implication parents** — drop `animal_ears` when `cat_ears` is present,
  `swimsuit` when `school_swimsuit` is present (dedupe redundant generality).
- **Hybrid captions add NL that tags can't** — spatial layout, lighting direction,
  material/texture, atmosphere; the NL must **not** restate the tags, and the whole
  caption stays **one line** (kohya keeps only line 1).

---

## Tag hygiene (what dataset-doctor flags)

- **One line per caption.** The trainer silently drops every line after the
  first — `dataset-doctor` flags this as `multiline_caption` (HIGH).
- **Source-noise tags don't belong in training captions.** Remove `jpeg artifacts`,
  `watermark`, `signature`, usernames, logos, and unrelated text. Valid per-image
  quality labels are not source noise.
- **Be consistent: underscores vs spaces.** WD14 defaults to spaces
  (`replace_underscore=true`), matching Anima's official "spaces, not
  underscores" rule. Pick one and stick to it across the whole set.
- **Avoid over-/under-tagging.** Roughly **5–40 tags** per image. Too few →
  the model can't disentangle the concept; too many → the signal is diluted.
- **No duplicate tags** within one caption.
- **Watch caption length** for token limits (Qwen3/T5 `*_max_token_length=512`).

---

## SD-Trainer generic WD14 defaults (other base-model paths)

| setting | default | tune when |
|---|---|---|
| `interrogator_model` | `wd14-convnextv2-v2` | bundled; swap for other WD models |
| `threshold` | `0.35` in the generic endpoint | calibrate on a reviewed sample |
| `character_threshold` | `0.6` | character-name tags |
| `replace_underscore` | `true` | keep on for SDXL/Anima space-style tags |
| `additional_tags` | `""` | **put the trigger word here** |
| `exclude_tags` | `""` | drop tags you never want |

WD14 writes tags only. To add a natural-language line, append it manually (or
with a VLM) after the tags on the **same line**, separated by `. `.

Typical non-Anima flow: WD14 auto-tag with the trigger in `additional_tags` →
`dataset-doctor` to verify trigger consistency and inspect hygiene findings → train.
For Anima, use the sectioned `tag_dataset.py` flow documented above.

---

## Evidence

Findings verified 2026-06-11 (see also `README.md` → "Caption format").

**Anima official model card** ([circlestone-labs/Anima](https://huggingface.co/circlestone-labs/Anima)):

- Mixed example (verbatim): `masterpiece, best quality, @big chungus. An anime
  girl with medium-length blonde hair is...` — period + space between the tag
  block and the prose.
- "You can mix tags and natural language in arbitrary order." / "You can put
  quality / artist tags at the beginning of a natural language prompt."
- Tag order `[quality/meta/year/safety] [count] [character] [series] [artist]
  [general]`; lowercase; spaces not underscores; artists need the `@` prefix.
- Dataset-tag format: dataset name on line 1 + newline (ye-pop / deviantart) —
  the only documented use of newlines.

**Trainer source** (SD-Trainer v2.7.0, `vendor/sd-scripts` pinned `068bcd7`):

- `library/train_util.py:873` — `caption = caption.split("\n")[0]`: only the
  first line of a `.txt` caption is used (non-wildcard mode).
- `library/train_util.py:4613` — `--caption_separator` default `","`;
  `:892` splits on it for shuffle/dropout/warmup; `:923` re-joins with `", "`.
- `library/train_util.py:879-890` — `keep_tokens_separator` supports a fixed
  prefix *and* fixed suffix around the shuffled middle.
- `library/strategy_anima.py:53-69` — captions go into the Qwen3 tokenizer
  raw; no chat template.
- `prefer_json_caption` appears **only** in `mikazuki/schema/sd3-lora.ts` and
  `mikazuki/anima_backend/adapter.py` (pass-through list); no `.json`-reading
  code exists anywhere in the install.
