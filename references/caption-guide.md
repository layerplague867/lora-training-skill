# Caption guide — captions that actually train well

How to caption a LoRA dataset for lora-scripts-next, and what `dataset-doctor`
checks. The format below is **verified** against the Anima official model card
and the trainer's own source code (SD-Trainer v2.7.0, vendored kohya
sd-scripts) — see [Evidence](#evidence) at the bottom.

---

## The verified format — one line, comma tags, period before natural language

```
<trigger>, <tag>, <tag>, …, <tag>. <Natural-language sentences, normal prose punctuation.>
```

- **trigger ↔ tags: comma.** The trigger is simply the *first element* of the
  comma-separated tag list — no special separator, no `@` for characters.
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
zkz, 1girl, solo, long hair, brown hair, school uniform, classroom. An anime girl with long brown hair stands by the classroom window.
```

### Official Anima tag order

```
[quality/meta/year/safety] [1girl/1boy/1other] [character] [series] [artist] [general tags]
```

All comma-separated; order *within* each section is free. Lowercase, spaces
instead of underscores (score tags like `score_7` are the only underscore
tags).

### Official recommended quality tags (the `[quality/meta]` slot)

Anima's card recommends leading with quality/meta tags. The standard, safe set:

```
masterpiece, best quality, newest, highres
```

(sometimes `absurdres`, `very aesthetic`; year/meta like `newest` steers toward
recent art). Two rules:

- **At generation time (prompts + sample gallery):** always lead with this prefix.
  `lora-pipeline`'s `validate.py` and the generated model card both use exactly
  `masterpiece, best quality, newest, highres`.
- **In training captions:** these are legitimate `[quality/meta]` tags and may lead
  the caption, but they are optional — do **not** confuse them with *negative*
  artefacts (`worst quality`, `low quality`, `jpeg artifacts`, `blurry`), which are
  negative-prompt tags and must be stripped from captions (see Tag hygiene). The WD14
  export blacklist in `lora-pipeline` already drops the negatives and the WD14 rating
  words (`general` / `sensitive` / `questionable` / `explicit`).

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
- Put it **first** in every caption (the first comma-separated tag).
- It must appear in **~100% of captions** — `dataset-doctor --trigger zkz` reports
  presence % and first-position %, and fails the gate if it is inconsistent.
- When auto-tagging with WD14, force it via `additional_tags` (see `trainer-api.md`).
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

## Anima tagging craft — the asymmetric-error rules

The single fact that reshapes everything: **Anima was pretrained on tags, natural
language, and both together, with random tag dropout — so a *missing* tag is
tolerated, but a *wrong/invented* tag is actively harmful.** This is the opposite of
the SDXL/booru instinct to maximize recall (dump every tag WD14 emits). For Anima,
**prefer a clean, high-precision caption over a complete one.** (Verified against the
`sd-image-sorter` tagger audit, `claude-code-sd-image-sorter-tagger-audit-REPORT.md`;
`lora-pipeline/scripts/tag_dataset.py` automates the rules below.)

### 1. Section order, not confidence order

A raw WD14 dump sorts tags by **confidence descending**, which scatters
character/series/artist tags among the generals and *violates the Anima model-card
order*. Emit the documented sections instead:

```
{quality}, {safety}, {count}, {trigger}, {characters}, {series}, {@artists}, {general}. {NL}
```

`masterpiece, best quality, safe, 1girl, mych4r, silver hair, … . An anime girl stands …`

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

### 3. Quality tags: `masterpiece, best quality` — but don't fake per-image quality

The safe, on-card Anima quality prefix is **`masterpiece, best quality`** (Anima's
quality vocab is `masterpiece/best/good/normal/low/worst quality` — **not** Pony's
`score_5`, which is out-of-vocabulary). Ideally quality is *derived per image* from an
aesthetic score and **omitted when unscored** ("no token beats a meaningless one");
stamping `masterpiece` on a mediocre image teaches the wrong thing. If you have no
scorer, the constant `masterpiece, best quality` prefix is acceptable.

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
   `tag_dataset.py` blacklists the ≥0.9 ones and **prints every candidate** so the
   prune is reviewed, never silent.

**Style LoRAs invert this:** prune the *style/artist* tags (so the style isn't named
in every caption — the trigger carries it) and **keep** all content/subject tags;
skip trait-pruning entirely.

### 5. Pick a clean tagger; never trust a captioner as a tagger

From a measured 6-tagger shootout on real images (audit §9.1):

| model | use | why |
|---|---|---|
| `wd-eva02-large-tagger-v3` | **best default** | swinv2 precision + extra true detail, no hallucinations |
| `wd-swinv2-tagger-v3` | safe/light default | clean, misses niche detail, no hallucinations |
| `pixai-tagger-v0.9` | **consensus only** | highest recall but *confident* hallucinations above its own threshold (two guitars, phantom objects) |
| `camie-tagger-v2` | ok *after* head-fix | must read the refined output head or characters score ~0 |
| `toriigate-0.5` | **captioner only** | as a tagger it invents anatomy at confidence 1.0 — never use it for tags; use it/ a VLM for the NL sentence |

**Consensus** (vote of swinv2 + eva02 + pixai, keep a tag if ≥2 agree) removes ~90% of
pixai's hallucinations while keeping its true finds — the "thorough" setting.

### 6. Thresholds are per-model, not global

`threshold=0.35` is the WD14 default, but the *same* 0.35 on other models is a footgun
(0.35 on OppaiOracle produced ~2,000 tags/image). Bind the threshold to the model.
Keep the **character threshold high (≈0.85)**: character-name tags are
high-confidence-or-wrong, and under the asymmetric rule a hallucinated identity is
worse than a missing one.

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
- **Negative/quality artefacts don't belong in training captions.** Tags like
  `worst quality`, `low quality`, `jpeg artifacts`, `watermark`, `signature`,
  `text`, `bad anatomy` are *negative-prompt* tags. Remove them.
- **Be consistent: underscores vs spaces.** WD14 defaults to spaces
  (`replace_underscore=true`), matching Anima's official "spaces, not
  underscores" rule. Pick one and stick to it across the whole set.
- **Avoid over-/under-tagging.** Roughly **5–40 tags** per image. Too few →
  the model can't disentangle the concept; too many → the signal is diluted.
- **No duplicate tags** within one caption.
- **Watch caption length** for token limits (Qwen3/T5 `*_max_token_length=512`).

---

## WD14 auto-tagging defaults (for reference)

| setting | default | tune when |
|---|---|---|
| `interrogator_model` | `wd14-convnextv2-v2` | bundled; swap for other WD models |
| `threshold` | `0.35` | raise for fewer/cleaner tags, lower for coverage |
| `character_threshold` | `0.6` | character-name tags |
| `replace_underscore` | `true` | keep on for SDXL/Anima space-style tags |
| `additional_tags` | `""` | **put the trigger word here** |
| `exclude_tags` | `""` | drop tags you never want |

WD14 writes tags only. To add a natural-language line, append it manually (or
with a VLM) after the tags on the **same line**, separated by `. `.

Typical flow: WD14 auto-tag with the trigger in `additional_tags` →
`dataset-doctor` to verify trigger consistency + prune artefacts/ubiquitous tags
→ train.

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
