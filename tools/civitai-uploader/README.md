# Civitai Uploader (Playwright)

Civitai has **no upload API**, so this drives a real logged-in Chromium session to fill the
Upload Wizard for you. Reusable for every future model — write one small JSON per model.

Your **password is never handled here** — you type it into the browser during `login`.
The tool **stops at Draft** and never publishes unless you explicitly ask.

## One-time setup (already done)
- venv + Playwright + Chromium are installed in `.venv/`.

## 1) Log in once
Double-click **`login.bat`** → a browser opens → sign in (email/Google + 2FA) → wait a few
seconds. It auto-detects login and saves the session to `.profile/`. You only redo this if
the session expires.

## 2) Write a config per model
A `*.civitai.json` next to the model's files (see `.../mychar/civitai_upload/mychar.civitai.json`):
```json
{
  "slug": "mychar",
  "name": "My Character (My Series) - Anima",
  "type": "LORA",
  "category": "Character",
  "tags": ["mychar", "my series", "character", "anime", "anima"],
  "description_file": "MODEL_CARD.md",
  "version_name": "v1",
  "base_model": "Anima",
  "trigger_words": ["mychar"],
  "files": ["mychar-anima-v1.safetensors"],
  "images_dir": "samples"
}
```
Paths (`description_file`, `files`, `images_dir`) are relative to the JSON's own folder.

## 3) Upload
Drag the `*.civitai.json` onto **`upload.bat`** (or `upload.bat "path\to\config.json"`).
It fills the wizard, uploads the model file + all PNGs in `images_dir`, screenshots every
step into `runs/<slug>/`, and **leaves it as a Draft**. Review in the browser, then click
**Publish** yourself.

To let the tool publish: `civitai_upload.py upload config.json --publish --yes`
(only do this once you trust a run — publishing is public and gets indexed).

## What it fills (confirmed working on the 4-step wizard)
1. **Edit model** — name, type (LoRA), category, tags, description (from `description_file`),
   "Depicts an actual person → No", and the required attestation checkbox.
2. **Edit version** — base model, and trigger words (turns off the "no trigger words" toggle,
   then commits each word via its "+ Create <word>" option).
3. **Upload files** — the `.safetensors` file(s); waits for "Finished uploading" before advancing.
4. **Create a post** — all sample images in `images_dir` (Civitai reads their embedded prompts).

Then it **stops at Draft**. Review in the browser and click **Publish** yourself.

## Notes / troubleshooting
- `base_model` must match Civitai's exact list (e.g. `Anima`, `Illustrious`, `Pony`, `SDXL 1.0`,
  `Flux.1 D`, `Qwen`…). If the name isn't found the tool falls back to **Other** and logs it.
- A tag identical to the category (e.g. tag `character` with category `Character`) may be de-duped
  by Civitai — harmless.
- Civitai sits behind Cloudflare and changes its UI. If a field doesn't fill, the tool logs a
  `MISS` and continues — just complete that field in the open browser.
- Check `runs/<slug>/*.png` to see exactly what happened on each step.
- Re-run `login.bat` if you see "NOT LOGGED IN".
