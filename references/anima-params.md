# Anima LoRA parameter reference

Authoritative parameter knowledge for **Anima LoRA** training on lora-scripts-next
(SD-Trainer v2.7.0). Distilled from the trainer's own schema
(`mikazuki/schema/sd3-lora.ts` + `shared.ts`) and the server-side defaults
(`mikazuki/app/api.py::apply_anima_training_defaults`). These are the keys you
put in the `POST /api/run` body (see `trainer-api.md`).

`model_train_type` for standard Anima LoRA is **`anima-lora`** (the WebUI's
"sd3" page; `sd3-lora` is an accepted alias). All keys below are flat (top-level
in the JSON body).

---

## Models (required)

| key | default | notes |
|---|---|---|
| `pretrained_model_name_or_path` | `./sd-models/anima/anima-base-v1.0.safetensors` | main DiT/transformer weights |
| `vae` | `./sd-models/anima/qwen_image_vae.safetensors` | **required** Qwen-Image VAE |
| `qwen3` | `./sd-models/anima/qwen_3_06b_base.safetensors` | Qwen3 text model |
| `llm_adapter_path` | *(optional)* | overrides built-in adapter |
| `t5_tokenizer_path` | *(optional)* | blank → built-in `configs/t5_old` |
| `resume` | *(optional)* | resume from a `save_state` folder |

## Adapter type — `lora_type` + `network_module`

| `lora_type` | `network_module` | when |
|---|---|---|
| `lora` *(default)* | `networks.lora_anima` | the normal choice |
| `lokr` | `lycoris.kohya` (`lycoris_algo="lokr"`) | small files, strong styles; `lokr_factor=-1` |
| `tlora` | `networks.tlora_anima` | timestep-aware; set `network_dim=32`, `tlora_min_rank≈dim/8`, `tlora_rank_schedule="cosine"` |
| `lora_fa` / `vera` | `networks.lora_anima` | memory-leaner variants |
| `loha` | `networks.loha` | LyCORIS LoHa |

## Network size

| key | default | guidance |
|---|---|---|
| `network_dim` | `16` | 4–128. Character: 16–32. Style: 16–64. **Not "bigger is better."** T-LoRA: 32 |
| `network_alpha` | `16` | = dim, or dim/2, or 1. T-LoRA: = dim |
| `network_dropout` | `0` | LoRA dropout |
| `network_train_unet_only` | `true` | keep true unless you know you need the text encoder |
| `network_train_text_encoder_only` | `false` | |

## Learning rate / optimizer

| key | default (Anima) | notes |
|---|---|---|
| `unet_lr` | **`5e-5`** | server rewrites the legacy `1e-4` default to `5e-5` for Anima |
| `text_encoder_lr` | `1e-5` | only used if training the TE |
| `learning_rate` | `1e-4` | ignored once `unet_lr`/`text_encoder_lr` are set |
| `lr_scheduler` | `cosine_with_restarts` | also: `cosine`, `constant`, `linear`, `polynomial`, `constant_with_warmup` |
| `lr_scheduler_num_cycles` | `1` | for `cosine_with_restarts` |
| `lr_warmup_steps` | `0` | |
| `optimizer_type` | `AdamW8bit` | `AdamW`, `Lion8bit`, `Prodigy`, `pytorch_optimizer.CAME`, `Automagic`, … |
| `min_snr_gamma` | *(unset)* | if used, `5` is the common value |

> **NaN guard:** with `Automagic` or `pytorch_optimizer.CAME` the server forces
> `mixed_precision=bf16` (if the GPU supports it) and disables `full_fp16`/`full_bf16`
> to avoid `loss=nan`.

## Dataset / bucketing

| key | default | notes |
|---|---|---|
| `train_data_dir` | `./train/aki` | **parent** of `<repeats>_<concept>` folders |
| `resolution` | `1024,1024` | `W,H`; must be multiples of 64 |
| `enable_bucket` | `true` | allow non-square aspect ratios |
| `min_bucket_reso` | `256` | |
| `max_bucket_reso` | `2048` | raise for very tall/wide images |
| `bucket_reso_steps` | `64` | |
| `bucket_no_upscale` | `true` | small images train at their native (lower) detail |

## Captions

| key | default | notes |
|---|---|---|
| `caption_extension` | `.txt` | the only **verified** caption format: single line, `trigger, tags. natural language` (see `caption-guide.md`) |
| `prefer_json_caption` | `true` | ⚠️ **UI-only in v2.7.0** — passed through, but no code in the install reads `.json` sidecars; keep captions in `.txt` |
| `shuffle_caption` | `false` | splits on `caption_separator` (default `,`) and re-joins with `", "`; an NL sentence with commas gets shredded — keep off, or pin prefix/suffix with `keep_tokens_separator` |
| `keep_tokens` | `0` | keep the first N **comma units** fixed when shuffling (set ≥1 to protect a trigger); `keep_tokens_separator` (e.g. `\|\|\|`) can pin a prefix *and* suffix |
| `caption_tag_dropout_rate` | *(unset)* | random per-tag dropout (also splits on commas) |

> **Conflict:** `cache_text_encoder_outputs=true` requires `shuffle_caption=false`.
> The trainer also reads only the **first line** of a `.txt` caption — multi-line
> captions silently lose everything after line 1 (`caption-guide.md` → Evidence).

## Save

| key | default | notes |
|---|---|---|
| `output_name` | `aki` | LoRA file name (no extension) |
| `output_dir` | `./output` | per-project subfolder recommended |
| `save_model_as` | `safetensors` | |
| `save_precision` | `fp16` | `bf16`/`float` also valid |
| `save_every_n_epochs` | `2` | or use `save_every_n_steps` |
| `save_state` | `false` | enables `resume` |

## Precision / VRAM / speed

| key | default | notes |
|---|---|---|
| `mixed_precision` | `bf16` | Anima default; `fp16` is more NaN-prone |
| `gradient_checkpointing` | `true` | big VRAM saver |
| `gradient_accumulation_steps` | `1` | raise to simulate a larger batch |
| `train_batch_size` | `1` | |
| `cache_latents` | `true` | VAE latent cache |
| `cache_text_encoder_outputs` | `true` | needs `shuffle_caption=false` |
| `blocks_to_swap` | *(unset)* | swap N transformer blocks CPU↔GPU for low VRAM |
| `fp8_base` / `fp8_base_unet` | `false` | FP8 base weights for extra savings |
| `max_data_loader_n_workers` | `0` | **keep 0 on Windows** (avoids repeated Triton warnings) |
| `persistent_data_loader_workers` | `false` | keep false on Windows |
| `attn_mode` | `""` (auto) | auto-pick flash→xformers→sdpa; or force `xformers`/`flash`/`sageattn`/`torch` |

### VRAM reference (Anima LoRA, 1024px, RTX 4090, from the trainer README)

| VRAM | configuration |
|---|---|
| ≥ 24 GB | defaults |
| ≥ 16 GB | `gradient_checkpointing` (recommended) |
| ≥ 12 GB | gradient checkpointing (stable) |
| ≥ 10 GB | + `blocks_to_swap=16` |
| ≥ 8 GB | + `blocks_to_swap=24` + `cache_text_encoder_outputs` + LoKr |

## Training preview (optional)

Set `enable_preview=true` to get sample images during training:

| key | Anima default | notes |
|---|---|---|
| `positive_prompts` / `negative_prompts` | conservative half-body girl / NSFW-suppressing | |
| `sample_width` / `sample_height` | `1024` / `1024` | |
| `sample_cfg` | `4.5` | Anima recommends 4–5 |
| `sample_steps` | `40` | Anima recommends 30–50 |
| `sample_sampler` | `euler` | Anima preview = Rectified Flow Euler |
| `sample_at_first` | `true` | step-0 baseline |
| `sample_every_n_epochs` | `2` | |

---

## Repeats, epochs, and the step budget

The trainer reads `<repeats>` from the folder name (`7_zkz` → 7). The real
training volume is:

```
effective_images = Σ (images_in_concept × repeats_of_concept)
steps_per_epoch  = ceil(effective_images / train_batch_size)
total_steps      = steps_per_epoch × max_train_epochs
```

Rules of thumb (character LoRA, Anima/SDXL-class):

- Aim for **~1000–2500 total steps** for a small character set.
- Balance `repeats` so a small concept is seen enough but does not overpower others.
- Fewer images → more repeats; more images → fewer repeats.
- Use `dataset-doctor` (`--epochs N --batch-size B`) to print the exact step budget before launching.

Common starting points:

| dataset size | repeats | epochs |
|---|---|---|
| 10–20 imgs | 8–10 | 10 |
| 20–50 imgs | 5–7 | 10 |
| 50–150 imgs | 2–4 | 10–15 |
| 150+ imgs | 1–2 | 10–20 |

### Auto-pick (lora-trainer quick path)

Deterministic defaults so a beginner never does this math — they reproduce the
table above and land near the 1500-step sweet spot:

```
repeats = clamp(round(150 / images), 1, 10)
epochs  = 10  (character/concept)  |  12 (style)
total_steps ≈ images × repeats × epochs ≈ 1500
```

Examples: 12 imgs → 10 repeats · 30 imgs → 5 · 75 imgs → 2 · 200 imgs → 1.
Only override when the user asks, or when total_steps falls outside
~1000–2500 (then nudge epochs first, repeats second).
