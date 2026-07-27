# LoRA Training Skill Suite

**Bring a folder of images. Leave with a trained LoRA.**
Or bring just a **name** — `lora-pipeline` collects, tags, curates, trains, validates,
and stages a **Civitai draft**, stopping only for you to click Publish.

A small family of agent skills (open [SKILL.md format](https://developers.openai.com/codex/skills))
that turns LoRA training on the [`lora-scripts-next`](https://github.com/wochenlong/lora-scripts-next)
trainer (a.k.a. *Next Trainer* / SD-Trainer) into a guided, quality-gated, one-confirmation
workflow — **Anima-first**, with SD1.5 / SDXL / Flux support.

Built for **Claude Code**, and works in any SKILL.md-compatible agent —
**OpenCode, Codex CLI, OpenClaw** — see [Compatibility](#compatibility-claude-code-opencode-codex-openclaw).

> 📖 **New here? Start with [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md)** — the full
> process from empty folder to published LoRA, including what to check at each stage
> and the captioning mistake that ruins most first attempts.
> For command reference and the agent contract, see **[GUIDE.md](GUIDE.md)**
> (English + 简体中文).

---

## The full process at a glance

Three skills, three jobs. `lora-pipeline` runs all of them in order, or enter at any
stage with what you already have.

```
        ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
        │  1. MAKE     │──▶│  2. VERIFY    │──▶│  3. TRAIN    │
        │ lora-pipeline│   │dataset-doctor │   │ lora-trainer │
        └──────────────┘   └───────────────┘   └──────────────┘
         collect · curate    PASS/WARN/FAIL      confirm card
         build · caption     + one-line fixes    → train → snapshots
               │                    │                    │
               │            ⛔ FAIL blocks here          ▼
               │            (seconds, offline,     4. VALIDATE  fixed-seed
               │             before the GPU)          gallery per checkpoint
               │                                          │
               └──────────── bring your own images ───▶    ▼
                                                    5. PUBLISH  Civitai draft
                                                       🛑 you click Publish
```

| Stage | Skill | The question it answers |
|---|---|---|
| **Make** | `lora-pipeline` | Where do images come from, and how are they captioned? |
| **Verify** | `dataset-doctor` | Is this trainable, or will it waste 40 minutes of GPU? |
| **Train** | `lora-trainer` | What parameters — and did it actually work? |

The point of the middle stage: dataset problems are cheap to find and expensive to
discover after training. The doctor is offline, takes seconds, and exits non-zero on
FAIL so you can gate on it.

---

## Why this exists

The trainer's GUI has ~80 knobs, but whether a LoRA turns out well is mostly decided
**before** training starts:

1. **Dataset & caption quality** — corrupt/duplicate images, missing or inconsistent
   captions, a diluted trigger word. The trainer never checks any of this; it only
   checks that the folder *exists and has images*.
2. **The step budget** — repeats × images × epochs. Too low: nothing is learned.
   Too high: a fried, overfitted LoRA.

This suite automates both, and keeps the human in exactly one loop: a single
plain-language confirmation card before training starts.

## What it feels like

```text
You:  Train a character LoRA from D:/data/mychar.

Agent: (detects your GPU · proposes trigger "mych4r" · organizes the folder into
        kohya <repeats>_<concept> form · auto-tags with WD14 · runs the doctor ·
        fixes findings with your OK · picks repeats/epochs for ~1500 steps)

        📋 Confirm card — character LoRA "mych4r"
        30 images × 5 repeats × 10 epochs = 1500 steps · RTX 4070 12GB → low-VRAM preset
        Output: ./output/mych4r-anima-v1/   Reply "confirm" to start.

You:  confirm.

Agent: (POSTs /api/run, tails the live log, then tells you which
        .safetensors snapshot to try first)
```

Every step that touches your files is **dry-run first, confirmed, and reversible**.

## The skill family

| Skill | What it does |
|---|---|
| **`lora-pipeline`** | **End-to-end conductor.** From just a character/concept *name*: collect images (Danbooru) → auto-tag (WD14) → curate + build the dataset → doctor gate → train (via `lora-trainer`) → validate a sample gallery (ComfyUI) → package + fill the Civitai upload wizard and **stop at Draft** for you to click Publish. Never trains without the confirm card; never auto-publishes. |
| **`lora-trainer`** | Training-orchestration entry. **Quick path needs only a folder of images**: auto-organize → auto-tag → doctor gate → auto-pick params from image count + detected VRAM → one confirm card → launch & monitor via the trainer's HTTP API. An expert path accepts explicit presets/dims/LRs. |
| **`dataset-doctor`** | Dataset + caption audit → **PASS / WARN / FAIL** verdict with prioritized fixes. Every finding maps to a one-line `fix_dataset.py` command — **dry-run by default, originals quarantined, never deleted**. |
| `references/` | Shared knowledge the skills cite: trainer API contract, Anima parameters, caption guide, presets, plus the collect-and-tag and validate-and-publish contracts for the full pipeline. |

```
lora-training-skill/
├── lora-pipeline/               # end-to-end: name → collect → … → Civitai draft
│   ├── SKILL.md                 # the 7-phase conductor (two human gates)
│   └── scripts/
│       ├── collect.py           # Danbooru download (2-tag-safe config)
│       ├── curate.py            # drop multi/comic/tiny/corrupt → keep/drop manifest
│       ├── build_dataset.py     # copy keeps → <repeats>_<concept>/, RGB-normalize
│       ├── tag_dataset.py       # Anima-correct WD14 tagging (section order + trait prune)
│       ├── validate.py          # ComfyUI Anima+LoRA sample gallery
│       └── make_civitai_pack.py # assemble model card + *.civitai.json + samples/
├── lora-trainer/
│   └── SKILL.md                 # quick path (folder → confirm card → train) + expert path
├── dataset-doctor/
│   ├── SKILL.md                 # audit & fix playbook
│   ├── scripts/
│   │   ├── _common.py           # shared helpers (layout, captions, severity, io)
│   │   ├── scan_dataset.py      # image-level scan (resolution, dupes, modes, steps)
│   │   ├── check_captions.py    # caption-level audit (trigger, tags, JSON, hygiene)
│   │   ├── doctor.py            # orchestrator → PASS/WARN/FAIL verdict
│   │   └── fix_dataset.py       # safe fixer: organize/dedupe/to-rgb/add-trigger/strip-tags
│   └── tests/                   # 30 stdlib unittest tests
└── references/
    ├── trainer-api.md           # mikazuki HTTP API (/api/run, /api/interrogate, SSE)
    ├── anima-params.md          # params, defaults, VRAM table, step-budget math
    ├── caption-guide.md         # verified caption format, trigger words, tag hygiene
    ├── presets.md               # /api/run body templates (character / style / low-VRAM)
    ├── collect-and-tag.md       # Danbooru + sd-image-sorter WD14 contracts (pipeline front half)
    └── validate-and-publish.md  # ComfyUI validation + civitai-uploader contract (back half)
```

## How a run flows

**Training-only** (`lora-trainer`, when you already have images):

```
image folder
   │  organize (<repeats>_<concept>)        fix_dataset.py · dry-run → confirm → --apply
   │  auto-caption (WD14 tagger)            POST /api/interrogate
   ▼
dataset-doctor gate                          doctor.py → PASS / WARN / FAIL
   │  fix findings (dedupe, to-rgb, …)      fix_dataset.py · originals → _quarantine/
   ▼
auto-pick params                             repeats = clamp(round(150/images), 1, 10)
   │                                         preset by detected VRAM (/api/graphic_cards)
   ▼
📋 ONE confirm card  ──  user says "confirm"
   ▼
POST /api/run  →  monitor live log  →  pick the right .safetensors snapshot
```

**End-to-end** (`lora-pipeline`, from just a name — wraps the above at TRAIN):

```
character name
   │ 1 COLLECT   collect.py      Danbooru → raw/ (+ .txt sidecars)
   │ 2 CURATE    curate.py       drop multi/comic/tiny/corrupt → manifest
   │   BUILD     build_dataset.py keeps → <repeats>_<concept>/, RGB-normalize
   │ 3 TAG       tag_dataset.py  WD14 (sd-image-sorter) → trigger-first captions
   ▼ 4 DOCTOR ── same gate as above ── PASS
   │ 5 TRAIN     → delegates to lora-trainer (📋 confirm card required)
   ▼ 6 VALIDATE  validate.py     ComfyUI Anima+LoRA sample gallery
   │ 7 PACKAGE   make_civitai_pack.py → model card + *.civitai.json + samples/
   ▼   PUBLISH   civitai-uploader fills the wizard → 🛑 stops at DRAFT
                 you review & click Publish (never auto-published)
```

## Requirements

- **The trainer**: download `SD-Trainer-vX.Y.Z.7z` from
  [lora-scripts-next releases](https://github.com/wochenlong/lora-scripts-next/releases),
  extract, run `run_gui.bat` → backend serves on `http://127.0.0.1:28000`.
- **Windows 10/11 + NVIDIA GPU** (RTX 20-series or newer) for the actual training.
- **Any Python 3.10+ with Pillow** for the scripts (no GPU needed). The trainer's
  bundled interpreter works out of the box: `<SD-Trainer>/python_embeded/python.exe`.

`dataset-doctor` works fully offline; `lora-trainer` talks to the trainer's local API.

**For the full `lora-pipeline`** you also need three local tools it drives (all optional
if you only want training): [DanbooruDownload](https://github.com/storyAura/DanbooruDownload)
(image collection), an sd-image-sorter WD14 service (tagging, `:8487`), ComfyUI
(validation, `:8188`), and the standalone **civitai-uploader** (Playwright, fills the
Civitai wizard). Paths/ports are configurable per script — see
[`references/collect-and-tag.md`](references/collect-and-tag.md) and
[`references/validate-and-publish.md`](references/validate-and-publish.md).

**For `krea2-pipeline`** (optional, separate track): a clone of
[kohya-ss/musubi-tuner](https://github.com/kohya-ss/musubi-tuner), Krea 2 weights, and a
24 GB GPU. Copy `krea2-pipeline/scripts/env.example.bat` to `env.bat` and fill in your
paths — `env.bat` is gitignored.

> **Every path in this repo is a placeholder.** Examples use `D:/data/...`,
> `C:/SD-Trainer/...`, and `mychar` as the trigger word. Nothing auto-detects your
> layout: pass paths as flags, or set the env vars each script documents
> (`DANBOORU_DL_DIR`, `SORTER_URL`, `COMFY_URL`, …).

## Install

**Keep the repo together** — the skills reference `../references/` and each other by
relative path, so the three top-level folders must stay siblings.

| Agent | Where to put it |
|---|---|
| **Claude Code** | Drop the whole repo under `~/.claude/skills/` (or the project's `.claude/skills/`). |
| **OpenCode** | Same paths work — OpenCode natively reads `.claude/skills/` and `~/.claude/skills/` (or use `.opencode/skills/`). |
| **Codex CLI** | Drop the repo under `~/.codex/skills/` (or `.codex/skills/` in a repo). Invoke via `$skill-name` / `/skills`, or let it trigger on the description. |
| **OpenClaw** | Drop it under `<workspace>/skills/` or `~/.openclaw/skills/`. |
| **Anything else** | The skills are plain markdown + stdlib-Python scripts + HTTP calls — tell your agent to read `lora-trainer/SKILL.md` and follow it. |

Then just ask: *"check my dataset before training"* or *"train a LoRA from this folder"*.

## Compatibility (Claude Code · OpenCode · Codex · OpenClaw)

The suite follows the open **Agent Skills** convention — a folder with a `SKILL.md`
(YAML frontmatter: `name` + `description`) plus supporting files. That format is now
supported natively by [Claude Code](https://code.claude.com/docs),
[OpenCode](https://opencode.ai/docs/skills/),
[OpenAI Codex](https://developers.openai.com/codex/skills), and
[OpenClaw](https://docs.openclaw.ai/tools/skills). Auto-triggering quality varies by
agent; explicit invocation ("use the lora-trainer skill") always works. Details and
per-agent notes: [GUIDE.md → Using outside Claude Code](GUIDE.md#5-using-outside-claude-code).

## Which trainers does this work with?

Short answer: **launching is SD-Trainer-specific; checking and fixing are not.**

- **`lora-trainer`** drives the mikazuki HTTP API of
  [lora-scripts-next](https://github.com/wochenlong/lora-scripts-next) (SD-Trainer) —
  `/api/run`, `/api/interrogate`, port 28000. Pointing it at a different trainer
  (kohya_ss GUI, OneTrainer, ai-toolkit, …) means rewriting
  `references/trainer-api.md` and `references/presets.md`; the rest of the flow
  carries over unchanged.
- **`dataset-doctor`** (scan / check / fix) is **trainer-agnostic**: it audits the
  standard kohya dataset convention — `<repeats>_<concept>` folders + sidecar
  caption files — shared by sd-scripts, kohya_ss, and most LoRA trainers. It's
  useful before training on *anything*. (Only the optional Anima `.json` caption
  checks and the WD14 tagging endpoint are SD-Trainer-specific.)
- The parameter knowledge (`anima-params.md`, the presets) is ultimately
  [kohya sd-scripts](https://github.com/kohya-ss/sd-scripts) vocabulary, so it
  transfers to any kohya-based pipeline.

Model-wise the suite is Anima-first, and the same flow supports SD1.5 / SDXL / Flux
through the same trainer.

## Caption format — verified findings (2026-06-11)

We verified the caption format against the
[Anima official model card](https://huggingface.co/circlestone-labs/Anima) and
the trainer's own source code (SD-Trainer v2.7.0, vendored kohya sd-scripts),
instead of folklore. The short version:

```
<trigger>, <tag>, <tag>, …, <tag>. <Optional natural-language sentences, normal prose punctuation.>
```

- **Comma** between the trigger and the tags (the trigger is just the first
  tag). **Period + space** between the tag block and the natural-language
  part — exactly what the official card demonstrates:
  `masterpiece, best quality, @big chungus. An anime girl with medium-length blonde hair is...`
- **One line only.** kohya's `read_caption` keeps just the first line of a
  `.txt` caption (`train_util.py`: `caption.split("\n")[0]`) — anything after
  a newline silently never trains. `dataset-doctor` flags this as
  `multiline_caption`.
- **Commas are structural** when `shuffle_caption` / tag dropout is on: the
  trainer splits on `caption_separator` (default `,`) and re-joins with `", "`,
  so an NL sentence with commas gets shredded. This suite keeps
  `shuffle_caption=false` (forced by `cache_text_encoder_outputs=true`), so
  captions are fed verbatim.
- **Style LoRAs should use Anima's `@` artist prefix** (`@mystyle`); character
  triggers should not.
- ⚠️ **`prefer_json_caption` is UI-only in v2.7.0.** The flag exists in the
  trainer's UI schema and is passed through, but no code in the install reads
  a `.json` caption sidecar — so structured Anima JSON captions are
  **unverified** and `.txt` is the source of truth until an end-to-end test
  proves otherwise (tracked in `TODO.md`).

Full rules, examples, and the line-by-line evidence:
[`references/caption-guide.md`](references/caption-guide.md).

## Safety model

- **Quality gate, not just a launcher.** No training run starts without a doctor verdict.
- **One confirmation, always.** The assembled config is shown in plain language and the
  user must explicitly confirm before `POST /api/run`.
- **Dry-run + quarantine.** Every `fix_dataset.py` command prints its plan first and
  changes nothing; with `--apply`, displaced files go to `_quarantine/` inside the
  dataset (ignored by doctor and trainer) — nothing is ever deleted.
- **Beginner math is automated.** Repeats/epochs from a deterministic ~1500-step
  formula; VRAM read from `/api/graphic_cards`; preset chosen accordingly. Experts can
  override everything.
- **Anima-first, accurate.** Defaults, enums, and quirks come from the trainer's own
  schema (`sd3-lora.ts` / `shared.ts`) and server code — not guessed.

## Manual CLI (no agent needed)

```powershell
# audit (read-only)
& "C:\SD-Trainer\python_embeded\python.exe" `
  ".\dataset-doctor\scripts\doctor.py" "D:\data\mychar" --trigger mych4r --epochs 10 --report

# fix — dry-run by default; add --apply after reviewing the plan
& "C:\SD-Trainer\python_embeded\python.exe" `
  ".\dataset-doctor\scripts\fix_dataset.py" dedupe "D:\data\mychar"
```

Full command reference: [GUIDE.md](GUIDE.md).

## Credits

- Trainer: [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)
  (Akegarasu-style GUI, powered by [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)).
- Structural inspiration: [ShiroEirin/comfyui-good-anima](https://github.com/ShiroEirin/comfyui-good-anima).
- Tagging: WD14 taggers; LyCORIS; T-LoRA.

See [CHANGELOG.md](CHANGELOG.md) for version history.
