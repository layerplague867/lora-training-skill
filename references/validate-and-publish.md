# Validate & publish — from a trained LoRA to a Civitai draft

The back half of `lora-pipeline`, after the doctor gate and training. Front half
(collect → tag → curate) is in [`collect-and-tag.md`](collect-and-tag.md); training
itself is `lora-trainer` + [`trainer-api.md`](trainer-api.md).

All tools here are local + **environment-specific** (paths/ports are this machine's
defaults; override via the flags/env vars noted).

---

## Phase 6 — VALIDATE (ComfyUI + Anima)

Before publishing, prove the character is consistent. Driver:
`lora-pipeline/scripts/validate.py` → drives ComfyUI's API
(`http://127.0.0.1:8188`, env `COMFY_URL`).

1. Copy the chosen snapshot into `<ComfyUI>/models/loras/`.
2. Generate a small gallery:

```
python validate.py --work "D:/work/mychar" --lora mychar-anima-v1.safetensors --trigger mychar
```

Writes portrait / scene / full-body shots to `<work>/validation/`. These double as the
**Civitai sample images** (Phase 7 copies them in — Civitai reads their embedded
prompts).

**The verified Anima generation graph** (what `validate.py` POSTs to `/prompt`):

| Node | value |
|---|---|
| `UNETLoader` | `Anima\anime\anima_baseV10.safetensors` (env `ANIMA_UNET`) |
| `CLIPLoader` | `qwen_3_06b_base.safetensors`, type `stable_diffusion` |
| `VAELoader` | `qwen_image_vae.safetensors` |
| `LoraLoader` | your `<name>.safetensors`, strength 0.9 model+clip |
| `KSampler` | `dpmpp_2m_sde_gpu` / `beta57`, cfg 4.4, steps 32, 896×1152 |
| positive | `masterpiece, best quality, newest, highres, 1girl, <trigger>, <scene…>` |

**Reading the gallery:** consistent identity across all shots = good → publish. Same
pose / stiff face / training images leaking = overfit → re-run with an earlier epoch
snapshot. Weak/absent identity = raise `--strength` (0.9 → 1.1) or add training epochs.

Only ComfyUI is needed here; start it **after** training frees the GPU.

---

## Phase 7 — PUBLISH (Civitai, stop at Draft)

Civitai has **no upload API** — the reusable **civitai-uploader** tool drives a
logged-in Chromium through the 4-step publish wizard. It lives at
`<repo>\tools\civitai-uploader\` (own README + `.venv`).

### 7a. Package (this repo)

`lora-pipeline/scripts/make_civitai_pack.py` assembles what the uploader consumes:

```
python make_civitai_pack.py --work "D:/work/mychar" --concept mychar --trigger mychar \
    --name mychar-anima-v1 --lora-file "<...>/output/mychar-anima-v1/mychar-anima-v1.safetensors" \
    --display "My Character (My Series) - Anima" --series "My Series"
```

→ `<work>/civitai_upload/` with `MODEL_CARD.md`, `<name>.civitai.json`, the
`.safetensors`, and `samples/` (from `validation/`). The config schema:

```json
{ "slug":"mychar", "name":"My Character (My Series) - Anima", "type":"LORA",
  "category":"Character", "tags":["mychar","my series","character","anime","anima"],
  "description_file":"MODEL_CARD.md", "version_name":"v1", "base_model":"Anima",
  "trigger_words":["mychar"], "files":["mychar-anima-v1.safetensors"],
  "images_dir":"samples", "nsfw":false }
```

`base_model` **must** be an exact Civitai base-model name — `Anima` is a valid one
(the uploader falls back to `Other` if not found).

### 7b. Upload (external tool)

One-time: run the uploader's `login.bat` (you type your own password in the browser;
session saved, never handled by the tool). Then:

```
<civitai-uploader>\upload.bat  "<work>\civitai_upload\<name>.civitai.json"
```

It fills the 4-step wizard, uploads the file + all samples, screenshots each step to
`runs/<slug>/`, and **stops at Draft**. You review and click **Publish**. It never
publishes unless explicitly invoked with `--publish --yes`.

### Wizard gotchas the tool already handles (don't re-derive)

- **Trigger words** (`#input_trainedWords`) do **not** commit on Enter/comma/Tab —
  Enter submits the form. Must turn OFF the "This version doesn't require any trigger
  words" toggle, type the word, then **click the "+ Create <word>"** option. An empty
  field makes Civitai silently re-enable the toggle.
- **Model file upload** is async; advancing too fast shows a spurious "No files
  uploaded" modal. Wait for the "Finished uploading" toast before Next.
- **Model tags** are a Mantine TagsInput — click the inner box, then type + Enter per
  tag. A tag identical to the category may be de-duped (harmless).
- Opening `/models/<id>/wizard?step=N` directly lands on the post editor, not the step
  form — use the on-page stepper links to move between steps.

---

## The one human gate that never moves

Everything up to a **Draft** can be automated. **Publishing is public and gets
indexed** — the agent must stop at Draft and let the user click Publish. Never pass
`--publish` without an explicit, in-the-moment "yes, publish it" from the user.
