# Krea 2 LoRA Pipeline (local, 24 GB GPU)

End-to-end process used to train, validate, and publish character LoRAs for **Krea 2**
on a single RTX 3090 (24 GB, display attached). Companion to the Anima pipeline in
`lora-pipeline/`. All paths in the scripts are machine-specific — adjust before use.

## 1. Dataset

Same collection/curation/tagging flow as the Anima pipeline (`lora-pipeline/`):
Danbooru + anime-frame augmentation (yt-dlp → ffmpeg scene-detect → sub-crop → WD14
bucketing by eye colour). Captions can be reused as-is — Krea 2 is natural-language
native, but a LoRA trained on tag captions answers both prompt styles.

## 2. Training — musubi-tuner (ai-toolkit does NOT work on 24 GB)

Trainer: [kohya-ss/musubi-tuner](https://github.com/kohya-ss/musubi-tuner), krea2 arch.
Recipe that fits 12.9B in ~17 GB VRAM (see `train_krea2.bat`):

- `krea2_cache_latents.py` (Qwen-Image VAE) → `krea2_cache_text_encoder_outputs.py`
  (Qwen3-VL-4B **single safetensors file**, not the HF folder) → `krea2_train_network.py`
- Key flags: `--fp8_base --fp8_scaled --blocks_to_swap 16 --gradient_checkpointing
  --sdpa --timestep_sampling shift --discrete_flow_shift 2.5
  --network_module networks.lora_krea2`, dim 32 / alpha 32, adamw8bit lr 1e-4, 768 px.
- fp8 only quantizes the frozen DiT (QLoRA-style); the saved LoRA is normal bf16 and
  runs on RAW / Turbo / fp8 / INT8 checkpoints alike.
- `--save_every_n_steps 150 --save_state` — cheap insurance; resume works.
- Long jobs: launch via detached `.bat` (`Start-Process`), never through a terminal that
  might close. Chain follow-up jobs with `powershell Wait-Process -Id <pid>`
  (`train_krea2_chained.bat` = wait-for-PID → cache → train; `validate_checkpoints.bat` = generate the same seeds from every checkpoint).

## 3. Validation & inference

- Train on **RAW**, validate/generate on **Turbo**: 8 steps, CFG 1.0 (disabled — negative
  prompts do nothing!), sampler `er_sde`, scheduler `simple`, `--mu 1.15` in musubi's
  `krea2_generate_image.py`.
- ComfyUI (>= 0.27 for native INT8): `Load Diffusion Model` (INT8/fp8 checkpoint) +
  `CLIPLoader type=krea2` + Qwen-Image VAE + `LoraLoaderModelOnly`. On Ampere cards INT8
  beats fp8 (INT8 tensor cores; fp8 has no HW acceleration on 30-series).
  API driver scripts: `comfy_krea2_test.py` (with/without-LoRA A/B), `comfy_krea2_nl_test.py`
  (natural-language prompt check), `comfy_krea2_masterpiece.py` (2K showcase shots).

## 4. Two-character images (trait bleed)

Stacked character LoRAs bleed traits (both trained on solo data). Working recipe:
strengths ~0.85 / 0.7 + positive-only binding ("she is the only one smoking",
"the two sisters have clearly different eye colors: X brown, Y red") — CFG-free Turbo
cannot use negative prompts. Guaranteed separation needs two-pass inpainting.

## 5. Showcase craft

- Mostly SFW (default Civitai browsing hides PG-13+; the thumbnail must land while SFW),
  1–2 spicy images max, zero NSFW for youthful-coded characters.
- What works: dramatic viewpoints, scale contrast, frozen moments (light trails, rain),
  a story beat, and Krea 2's party trick — legible rendered text via quoted strings
  (`"ヤニねこ"` on a neon billboard).

## 6. Publishing (Civitai)

Automation lives in `../tools/civitai-uploader/` (Playwright; no upload API exists).
Structure convention: **one model page per character, one version per base model**
(add versions via `/models/<id>/model-versions/create`). Hard-won gotchas are documented
in that README — file-upload completion detection, tag-commit races, hidden-post
publishing, and "broken" thumbnails that are really just scan-pipeline lag (~15 min).
