# Walkthrough — your first LoRA, end to end

This is the long-form version: every stage, what "good" looks like before you move
on, and the judgement calls nobody tells you about. If you just want commands, read
[GUIDE.md](../GUIDE.md) instead.

Three skills cover three different jobs, and they are meant to be used together:

| Stage | Skill | The question it answers |
|---|---|---|
| **Make** the dataset | `lora-pipeline` (phases 1–3) | Where do images come from, and how are they captioned? |
| **Verify** the dataset | `dataset-doctor` | Is this data actually trainable, or will it waste 40 minutes of GPU? |
| **Train** the LoRA | `lora-trainer` | What parameters, and did it work? |

`lora-pipeline` is the conductor that runs all three in order. You can also enter at
any stage — bring your own images and start at *Verify*.

---

## 0. What you need before starting

**Non-negotiable:**

- **An NVIDIA GPU, 8 GB VRAM minimum**, 12 GB+ comfortable, 24 GB for the Krea 2 track.
  AMD/Intel/Apple are not supported by the trainer backend.
- **Windows 10/11.** The trainer ships as a Windows bundle. Linux users can run
  sd-scripts directly, but these skills target the bundled HTTP API.
- **~30 GB free disk.** Base models are 6–12 GB each; checkpoints add up fast.
- **[SD-Trainer / lora-scripts-next](https://github.com/wochenlong/lora-scripts-next/releases)** —
  download the `.7z`, extract, run `run_gui.bat`. Backend listens on `127.0.0.1:28000`.
- **An agent that reads skills** — Claude Code, OpenCode, Codex CLI, OpenClaw, or any
  LLM agent you can point at a `SKILL.md`.

**Optional, per stage:**

| You want | You need |
|---|---|
| Auto-collect images by tag | [DanbooruDownload](https://github.com/storyAura/DanbooruDownload) |
| Auto-captioning | an sd-image-sorter WD14 service on `:8487` (or the trainer's own `/api/interrogate`) |
| Sample-image validation | [ComfyUI](https://github.com/comfyanonymous/ComfyUI) on `:8188` |
| Publish to Civitai | `tools/civitai-uploader` (Playwright) + a Civitai account |
| Krea 2 instead of Anima | [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) + 24 GB VRAM |

**What you do *not* need:** a `pip install` for this repo (scripts are stdlib +
Pillow), a paid API key, or any cloud service. Everything runs locally.

> **Set your paths.** Nothing here auto-detects your machine. Pass paths as flags, or
> set the env vars each script documents: `DANBOORU_DL_DIR`, `SORTER_URL`,
> `COMFY_URL`. For the Krea 2 track, copy `krea2-pipeline/scripts/env.example.bat`
> to `env.bat` (gitignored) and fill it in.

---

## 1. Make the dataset

Two honest paths.

### Path A — you already have images

Best case. Skip to [§2](#2-verify-the-dataset). Anything works: screenshots, art you
own, frames you extracted from video. Aim for **20–60 images** for a character.

### Path B — collect by tag

> "Collect 150 images of `<character>` from Danbooru into `D:/data/mychar`."

The agent runs `collect.py`, which writes a YAML config and shells out to
DanbooruDownload. It downloads images **plus `.txt` tag sidecars** — those sidecars
are worth more than the images later, for co-occurrence analysis.

Then curation, which is where quality is actually decided:

```
curate.py        → drops multi-character, comic pages, tiny images, corrupt files
build_dataset.py → copies keeps into <repeats>_<concept>/, normalizes to RGB
```

**Judgement call the tooling can't make for you:** `curate.py` drops
`2girls`/`comic` by tag, but it cannot see that 40 of your 150 images are the same
pose from the same artist. Over-represented near-duplicates teach the model that
pose, not the character. Open the folder and look.

### How many images, really

| Images | Reality |
|---|---|
| < 10 | Possible with a higher LR, but expect a fragile LoRA. |
| 20–40 | The sweet spot for a character. Diminishing returns after. |
| 100+ | Only helps if it adds *variety* — new angles, outfits, lighting. 100 similar images are worse than 30 varied ones. |

Variety beats volume. Every time.

## The captioning trap

This is where most first LoRAs go wrong, so it gets its own section.

A LoRA learns **what varies against what stays fixed**. The trigger word absorbs
whatever you *don't* caption.

- **Caption a trait → the model learns to control it separately.**
- **Omit a trait → it gets baked into the trigger.**

So for a character, you *want* to omit their permanent traits. If your character
always has silver hair, remove `silver hair` from the captions — then `mychar` alone
summons silver hair. Leave it in, and you must always type it, and the model may
happily give you a brunette.

Conversely, caption everything **incidental**: pose, expression, outfit, background,
camera angle. Those are what you want to change at generation time.

`tag_dataset.py` automates this: WD14 tags every image, puts the trigger first,
orders sections the way Anima expects, and prunes traits that appear across most of
the set (they're permanent, so they belong in the trigger).

**Asymmetric error cost:** wrongly *keeping* a trait tag is a small annoyance — you
type one extra word forever. Wrongly *removing* a tag that only appears in half the
images teaches the model to blend two different things into one. When unsure, keep it.

For style LoRAs, invert all of this: you *want* generalization, so caption content
thoroughly and use no trigger, or a loose one.

Full detail: [`references/caption-guide.md`](../references/caption-guide.md).

---

## 2. Verify the dataset

**Do not skip this.** It's free, it's offline, and it takes seconds. Training is what
costs you 40 minutes.

> "Check my dataset at `D:/data/mychar` before training, trigger `mychar`, 10 epochs."

```powershell
& "C:\SD-Trainer\python_embeded\python.exe" `
  ".\dataset-doctor\scripts\doctor.py" "D:\data\mychar" --trigger mychar --epochs 10 --report
```

You get one of three verdicts:

| Verdict | Meaning | Exit code |
|---|---|---|
| PASS | Train it. | 0 |
| WARN | Trainable, but you're leaving quality on the table. Read the findings. | 0 |
| FAIL | Something will break or waste the run. Fix first. | 2 |

Exit code 2 on FAIL means you can wire this in as a pre-commit hook or CI gate.

Every finding maps to a one-line fix:

```powershell
# ALWAYS dry-run first — it prints the plan and changes nothing
& $PY ".\dataset-doctor\scripts\fix_dataset.py" dedupe "D:\data\mychar"

# then, after reading the plan
& $PY ".\dataset-doctor\scripts\fix_dataset.py" dedupe "D:\data\mychar" --apply
```

**Safety model:** dry-run is the default, and removed files move to `_quarantine/`
inside the dataset. Nothing is ever deleted. If a fix was wrong, move the files back.

Common findings and what they actually mean:

| Finding | Why it matters |
|---|---|
| `missing_captions` | Uncaptioned images still train — they dump everything into the trigger. Usually not what you want. |
| `exact_duplicates` | Silently multiplies the repeat count for that image, skewing the model. |
| `trigger_missing` | Your trigger isn't in the captions, so nothing binds to it. The LoRA will do nothing when you use it. |
| `non_rgb_mode` | Palette/CMYK/grayscale images can crash or train oddly. `to-rgb` fixes it. |
| `tiny_images` | Below training resolution, they add blur, not detail. |

Re-run the doctor after fixing. Iterate to PASS.

---

## 3. Train

> "Train a character LoRA from `D:/data/mychar`."

The agent reads your VRAM via `/api/graphic_cards`, picks a preset, computes repeats
and epochs toward a **~1500-step budget** (`repeats = clamp(round(150/images), 1, 10)`),
then shows **one confirm card**.

**Read the card.** It's the last gate before the GPU spins up. Check:

- **Trigger word** — is it rare? `mychar` is fine; `girl` is a disaster.
- **Total steps** — 1000–2000 for a character. Under 500 underfits; over 4000 usually
  overfits.
- **Base model** — must match what you'll generate with. An Anima-trained LoRA used on
  a different base gives mush.
- **Resolution** — 512 is fast and weak, 768 is the usual answer, 1024 needs VRAM.
- **Output name** — you will have several of these. Version them.

Say `confirm` and it launches, streaming the live log.

### Save intermediate checkpoints

Set `save_every_n_epochs` so you get snapshots, not just a final file. **The last
epoch is frequently not the best one** — overfitting is gradual and invisible until
you compare. Snapshots cost disk; retraining costs an hour.

### Watching the log

- `loss` bouncing around a slowly-declining average is normal. It's a noisy signal —
  don't read individual steps.
- `loss` flat at 0, or `nan`: something is broken. Stop it.
- CUDA OOM: drop resolution, or batch size, or pick the lower-VRAM preset.
- A **hard crash or freeze mid-run on a high-wattage GPU** is often a power transient,
  not a software bug. Capping the board (`nvidia-smi -pl <watts>`, needs admin) is a
  known workaround. If you enabled `save_state`, resume instead of restarting.

---

## 4. Validate — pick the right file

You now have several `.safetensors`. **They are not interchangeable, and the newest is
not automatically the best.**

> "Generate validation images from every checkpoint in `D:/data/mychar/output`."

`validate.py` renders a sample gallery through ComfyUI. The important detail: **fixed
seeds across checkpoints.** Same prompt, same seed, different checkpoint — that's the
only way to see what *training* changed rather than what *noise* changed.

What you're looking for:

| Symptom | Diagnosis | Fix |
|---|---|---|
| Doesn't look like the character | Underfit, or trigger not bound | More epochs, or check that captions bound the trigger |
| Right character, every image the same pose | Overfit | Use an earlier checkpoint |
| Backgrounds/outfits all identical | Under-captioned incidentals | Caption them, retrain |
| Traits need explicit prompting | Trait tags left in captions | Prune them, retrain |
| Artifacts, melted anatomy | Overtrained or LR too high | Earlier checkpoint, lower LR |

Pick the earliest checkpoint that captures the character well — earlier means more
flexible. Test at a couple of LoRA weights (0.7, 1.0); one that only works at exactly
1.0 is over-baked.

---

## 5. Package and publish

> "Package `mychar` for Civitai."

`make_civitai_pack.py` assembles a model card, a `*.civitai.json` metadata file, and
your chosen samples. Then `tools/civitai-uploader` drives a real browser through the
upload wizard.

**It stops at Draft. Always.** Nothing is published without you opening the browser
and clicking Publish. Review the trigger words and samples there — the wizard is
easier to check visually than to verify programmatically.

Login is interactive and the browser session lives in `.profile/`, which is
gitignored. **No API keys or credentials are stored in this repo.**

### Before you publish

- **Don't name a model after a real artist.** If you trained on a specific artist's
  work, use a neutral style-descriptive name. Naming or triggering with a real
  person's handle invites takedowns and is a poor way to treat the person whose work
  you learned from.
- Credit the base model.
- State the trigger word and recommended weight in the description. Users can't guess.
- Check the platform's rules on training data. They vary and they change.

---

## Where to go next

| Doc | Contents |
|---|---|
| [GUIDE.md](../GUIDE.md) | Command reference, issue-code → fix table, agent contract (EN + 中文) |
| [`references/caption-guide.md`](../references/caption-guide.md) | Verified caption format, tag hygiene |
| [`references/anima-params.md`](../references/anima-params.md) | Every parameter, VRAM table, step math |
| [`references/presets.md`](../references/presets.md) | Ready-made `/api/run` bodies |
| [`references/trainer-api.md`](../references/trainer-api.md) | The HTTP contract, if you're building on this |
| [`krea2-pipeline/README.md`](../krea2-pipeline/README.md) | The 24 GB Krea 2 track via musubi-tuner |

**If it didn't work:** re-read §2 and the captioning trap. Most disappointing LoRAs
are dataset problems wearing a parameter-problem costume.
