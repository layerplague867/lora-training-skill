# Changelog

All notable changes to the LoRA Training Skill Suite are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions use SemVer.

## [0.3.0] — 2026-07-08

End-to-end pipeline release: the suite now goes from a bare **character name** to a
ready-to-publish **Civitai draft**, not just from an image folder to a `.safetensors`.
All contracts are verified against a real end-to-end run of a character Anima LoRA.

### Added

- **New skill `lora-pipeline/`** — a 7-phase end-to-end conductor (collect → tag →
  curate/build → doctor gate → train → validate → package/publish) that delegates
  training to `lora-trainer` and quality to `dataset-doctor`, and enforces two human
  gates: the training confirm card, and **never auto-publishing** (stops at Draft).
- **`lora-pipeline/scripts/`** — six stdlib+Pillow drivers generalized from that
  run: `collect.py` (Danbooru, 2-tag-safe), `curate.py` (drop multi/comic/tiny/corrupt),
  `build_dataset.py` (keeps → `<repeats>_<concept>/`, RGB-normalize, auto-repeats),
  `tag_dataset.py` (**Anima-correct** WD14 tagging — see below), `validate.py`
  (ComfyUI Anima+LoRA sample gallery), `make_civitai_pack.py` (model card +
  `*.civitai.json` + samples for the civitai-uploader).
- **Anima tagging craft** (not a naive WD14 dump) — `tag_dataset.py` and
  `caption-guide.md` now encode the rules verified in the sd-image-sorter tagger audit:
  the asymmetric error cost (missing tags tolerated, wrong tags harmful → prefer a clean
  tagger over max recall); **section ordering** via the sorter's `content_mode="template"`
  + `preset_id="anima"` (model-card order, `@artist`, `safe/sensitive/nsfw/explicit`
  safety vocab with `questionable→nsfw`, single-line) instead of a confidence-ordered
  dump; the **caption-paradox trait prune** for character LoRAs (blacklist invariant
  hair/eye/body traits at ratio ≥0.9 so the trigger absorbs identity, keeping transient
  states — a *reviewed*, printed prune) via `/api/tags/trait-candidates`, inverted for
  style LoRAs; tagger selection (`wd-eva02-large`/`wd-swinv2` best, `pixai` consensus-only,
  `toriigate` captioner-only) and per-model thresholds; `--consensus` / `--nl` opt-ins.
- **`references/collect-and-tag.md`** — DanbooruDownload contract (the 2-tag anonymous
  limit) + the code-verified sd-image-sorter HTTP API (scan → selection-token → tag →
  trait-candidates → `template`/`anima` export) with the field-by-field rationale.
- **`references/validate-and-publish.md`** — the verified ComfyUI Anima generation graph
  (UNET/CLIP/VAE + LoRA, dpmpp_2m_sde_gpu/beta57) and the civitai-uploader 4-step-wizard
  contract, including the trigger-word "+ Create" commit gotcha and the async
  file-upload wait — plus the hard rule that publishing is always the user's click.
- **`caption-guide.md`** — a new **"Anima tagging craft"** section (asymmetric error
  cost, section-vs-confidence order, safety-vocab mapping, per-image quality, the
  3-level caption-paradox prune, tagger shootout, per-model thresholds, kaomoji /
  implication traps) plus the **official recommended quality tags** note
  (`masterpiece, best quality`) distinguished from negative-prompt artefacts.

### Changed

- `README.md` — skill-family table, repo tree, and flow diagram now cover the full
  `lora-pipeline` (name → Draft) alongside the training-only sub-flow; Requirements note
  the external tools the pipeline drives.

## [0.2.2] — 2026-06-11

Caption-format verification release: the caption advice is now backed by the
Anima official model card and the trainer's own source code instead of folklore.

### Added

- `check_captions.py`: new **`multiline_caption`** issue (HIGH) — kohya's
  `read_caption` keeps only the first line of a `.txt` caption
  (`train_util.py`: `caption.split("\n")[0]`), so multi-line captions silently
  lose everything after line 1. Reported in `per_caption.multiline`; new test
  (31 tests total, all passing).
- `README.md`: new **"Caption format — verified findings"** section.
- `caption-guide.md`: **Evidence** section with verbatim official quotes and
  trainer-source line references.

### Changed

- **Verified caption format** documented everywhere:
  `trigger, tag, …, tag. Natural language sentence.` — comma between trigger
  and tags, period + space before the natural-language part (the Anima card's
  own mixed example), normal prose punctuation inside it, never a newline.
- **Anima structured `.json` captions downgraded to "unverified"**: in
  SD-Trainer v2.7.0, `prefer_json_caption` exists only in the UI schema and
  the backend pass-through list — no code in the install reads `.json`
  sidecars. `.txt` is now documented as the source of truth
  (`caption-guide.md`, both SKILL.md files, `anima-params.md`, `presets.md`);
  an end-to-end verification task was added to `TODO.md`.
- `caption-guide.md` rewritten around the verified format: shuffle/dropout
  comma machinery (`caption_separator`, re-join with `", "`,
  `keep_tokens_separator` prefix+suffix pinning), the `@` artist-prefix rule
  for style LoRAs ("very weak without it" — official), and WD14 NL guidance
  (append on the same line after `. `).
- `GUIDE.md` / `dataset-doctor/SKILL.md` fix tables gained the
  `multiline_caption` row (no auto-fix; merge to one line).

## [0.2.1] — 2026-06-11

### Changed

- Both SKILL.md files now teach the agent the **trainer scope** explicitly:
  - `lora-trainer` — launching/tagging is bound to SD-Trainer's mikazuki API;
    never send the `/api/run` contract to other trainers. With a non-SD-Trainer
    setup: still run the doctor (trainer-agnostic), reuse the kohya parameter
    vocabulary to generate a config the user can run manually, and never
    auto-launch. Offline rule: only tagging + launching need the trainer;
    preparation, audit, and fixes all work offline. New self-check item #1.
  - `dataset-doctor` — new "scope" section: audits the standard kohya dataset
    convention, useful for any trainer; WD14 tagging and Anima `.json` checks
    are the only SD-Trainer/Anima-specific parts, with fallback guidance.
- `README.md` gained the matching "Which trainers does this work with?" section.

## [0.2.0] — 2026-06-11

Beginner-friendly release: a bare folder of images is now enough to train.

### Added

- **`dataset-doctor/scripts/fix_dataset.py`** — one command per doctor issue
  code, replacing hand-rolled shell fixes. Safety model: **dry-run by default**
  (prints a plan, changes nothing until `--apply`) and **quarantine, never
  delete** (files move to `_quarantine/` inside the dataset, with their caption
  sidecars, restorable at any time).
  - `organize` → `no_concept_folders` (build `<repeats>_<concept>/` from loose images)
  - `quarantine-corrupt` → `corrupt_images`
  - `dedupe [--near]` → `exact_duplicates` / `near_duplicates` (keeps the
    highest-resolution copy per group)
  - `to-rgb` → `non_rgb_mode` (alpha composited over white; original backed up)
  - `add-trigger` → `trigger_inconsistent` (first `.txt` tag / JSON `character`,
    rewritten in the recommended Anima key order)
  - `strip-tags [--tags ...]` → `artifact_tags` + per-caption `duplicate_tags`
- **`lora-trainer` quick path** — the new default flow for non-expert users.
  Needs only an image folder: detects VRAM via `GET /api/graphic_cards` (never
  asks), suggests a trigger from the concept name, organizes + WD14-tags +
  doctor-checks + fixes the dataset (each fix dry-run → one confirmation →
  `--apply`), auto-picks repeats/epochs via a deterministic formula
  (`repeats = clamp(round(150 / images), 1, 10)`, ~1500 total steps) and the
  preset via detected VRAM, then shows **one plain-language confirm card**
  before launching.
- **Post-training guidance** in `lora-trainer` — which epoch snapshot to try
  first, how to spot overfitting, and how to verify with the trigger word.
- `tests/test_fix_dataset.py` — 14 tests covering every fixer command,
  dry-run no-op behaviour, quarantine invisibility, and caption rewriting
  (30 tests total, all passing under the trainer's embedded Python).
- **`GUIDE.md`** — bilingual (English + 简体中文) hands-on guide for users
  (prompts, confirm card, snapshot picking, troubleshooting) and for agents
  (the execution contract, exact pipeline, fix-command table, API quick
  reference), plus install paths for Claude Code / OpenCode / Codex CLI /
  OpenClaw (all support the open SKILL.md Agent Skills format).

### Changed

- `_common.iter_images()` now skips `_quarantine/` folders so quarantined files
  no longer count as training data for any scan.
- `dataset-doctor/SKILL.md` remediation playbook now maps every issue code to
  its `fix_dataset.py` one-liner.
- `references/anima-params.md` documents the quick-path auto-pick formula
  alongside the repeats/epochs table.
- `README.md` rewritten: why-first structure, flow diagram, per-agent install
  table (Claude Code / OpenCode / Codex / OpenClaw), safety model, and links
  to `GUIDE.md`.

## [0.1.0] — 2026-06-02

Initial release. A two-skill suite for quality-gated LoRA training on
`lora-scripts-next` (SD-Trainer v2.7.0), Anima-first.

### Added

- **`dataset-doctor` skill** — read-only dataset + caption audit with a
  PASS / WARN / FAIL readiness verdict and prioritized fixes.
  - `scripts/scan_dataset.py` — image-level scan: `<repeats>_<concept>` layout,
    effective-image / step budget, resolution + aspect-ratio buckets vs the
    target resolution, colour-mode (non-RGB) issues, corrupt/unreadable files,
    exact (md5) duplicates and near-duplicates (perceptual dhash), and
    missing-caption pairing.
  - `scripts/check_captions.py` — caption-level audit: missing/empty captions,
    trigger-word presence & first-position consistency (or inference), tag
    frequency (ubiquitous "baked-in" tags, rare noise), over-/under-tagging,
    negative/quality artefact tags, underscore-vs-space consistency, duplicate
    tags, and Anima JSON structure validation.
  - `scripts/doctor.py` — orchestrator that merges both into one verdict +
    de-duplicated, severity-ordered recommendations. Exit code 2 on FAIL.
  - `scripts/_common.py` — shared layout/caption/severity/io helpers.
  - `tests/test_dataset_doctor.py` — 15 stdlib `unittest` tests over a synthetic
    dataset (all passing under the trainer's embedded Python).
- **`lora-trainer` skill** — orchestration entry: model-type routing, a
  `dataset-doctor` quality gate, preset-based config assembly, step-budget
  estimation, mandatory confirm-before-launch, `POST /api/run`, and live-log
  monitoring.
- **`references/`** — trainer knowledge distilled from the trainer's own schema
  and server code:
  - `trainer-api.md` — mikazuki HTTP API (`/api/run`, `/api/interrogate`, SSE log
    stream, tagger, discovery endpoints; port 28000, `/api` prefix).
  - `anima-params.md` — Anima LoRA parameters, defaults, VRAM table, step budget.
  - `caption-guide.md` — `.txt` vs Anima `.json`, trigger words, tag hygiene.
  - `presets.md` — ready `/api/run` body templates (character / style / low-VRAM).
- Project `README.md`.

### Notes

- Scripts depend only on the standard library + Pillow, so they run under the
  trainer's bundled `python_embeded` (Python 3.10, Pillow 10.4) with no extra
  install.
