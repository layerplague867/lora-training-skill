# Anima LoRA presets (POST /api/run body templates)

Starting configs for `lora-trainer`. These are **flat key→value templates** that
map 1:1 onto the `POST /api/run` JSON body (see `trainer-api.md`). Pick one, fill
the `<PLACEHOLDERS>`, convert to JSON, and POST. Key meanings + defaults live in
`anima-params.md`.

Placeholders to fill every time:

- `<TRAIN_DATA_DIR>` — parent folder of `<repeats>_<concept>` (forward slashes)
- `<OUTPUT_NAME>` — LoRA file name, e.g. `zkz-anima-v1`
- `<TRIGGER>` — activation tag (also pass to the WD14 tagger `additional_tags`)
- model paths only if yours differ from the defaults below

---

## 1. Character / concept LoRA (default, ~12–16 GB)

```toml
model_train_type = "anima-lora"
lora_type = "lora"
pretrained_model_name_or_path = "./sd-models/anima/anima-base-v1.0.safetensors"
vae = "./sd-models/anima/qwen_image_vae.safetensors"
qwen3 = "./sd-models/anima/qwen_3_06b_base.safetensors"

train_data_dir = "<TRAIN_DATA_DIR>"
resolution = "1024,1024"
enable_bucket = true
min_bucket_reso = 256
max_bucket_reso = 2048
bucket_no_upscale = true

output_name = "<OUTPUT_NAME>"
output_dir = "./output/<OUTPUT_NAME>"
save_model_as = "safetensors"
save_precision = "fp16"
save_every_n_epochs = 2
max_train_epochs = 10
train_batch_size = 1

network_module = "networks.lora_anima"
network_dim = 16
network_alpha = 16
network_train_unet_only = true

unet_lr = 5e-5
text_encoder_lr = 1e-5
lr_scheduler = "cosine_with_restarts"
lr_scheduler_num_cycles = 1
lr_warmup_steps = 0
optimizer_type = "AdamW8bit"

mixed_precision = "bf16"
gradient_checkpointing = true
cache_latents = true
cache_text_encoder_outputs = true
caption_extension = ".txt"
prefer_json_caption = true
shuffle_caption = false
keep_tokens = 1            # protect the leading <TRIGGER> if you shuffle later
seed = 1337
clip_skip = 2
max_data_loader_n_workers = 0   # Windows-friendly
enable_preview = false
```

---

## 2. Style LoRA (slightly larger rank, ~16 GB)

```toml
model_train_type = "anima-lora"
lora_type = "lora"
pretrained_model_name_or_path = "./sd-models/anima/anima-base-v1.0.safetensors"
vae = "./sd-models/anima/qwen_image_vae.safetensors"
qwen3 = "./sd-models/anima/qwen_3_06b_base.safetensors"

train_data_dir = "<TRAIN_DATA_DIR>"
resolution = "1024,1024"
enable_bucket = true
min_bucket_reso = 256
max_bucket_reso = 2048
bucket_no_upscale = true

output_name = "<OUTPUT_NAME>"
output_dir = "./output/<OUTPUT_NAME>"
save_model_as = "safetensors"
save_precision = "fp16"
save_every_n_epochs = 2
max_train_epochs = 12
train_batch_size = 1

network_module = "networks.lora_anima"
network_dim = 32
network_alpha = 16
network_train_unet_only = true

unet_lr = 5e-5
text_encoder_lr = 1e-5
lr_scheduler = "cosine_with_restarts"
lr_scheduler_num_cycles = 1
optimizer_type = "AdamW8bit"

mixed_precision = "bf16"
gradient_checkpointing = true
cache_latents = true
cache_text_encoder_outputs = true
caption_extension = ".txt"
prefer_json_caption = true
shuffle_caption = false
keep_tokens = 0            # style LoRAs usually have no single trigger
seed = 1337
clip_skip = 2
max_data_loader_n_workers = 0
enable_preview = false
```

---

## 3. Low-VRAM LoRA (~10–12 GB; LoKr + block swap)

```toml
model_train_type = "anima-lora"
lora_type = "lokr"
pretrained_model_name_or_path = "./sd-models/anima/anima-base-v1.0.safetensors"
vae = "./sd-models/anima/qwen_image_vae.safetensors"
qwen3 = "./sd-models/anima/qwen_3_06b_base.safetensors"

train_data_dir = "<TRAIN_DATA_DIR>"
resolution = "1024,1024"
enable_bucket = true
min_bucket_reso = 256
max_bucket_reso = 2048
bucket_no_upscale = true

output_name = "<OUTPUT_NAME>"
output_dir = "./output/<OUTPUT_NAME>"
save_model_as = "safetensors"
save_precision = "fp16"
save_every_n_epochs = 2
max_train_epochs = 10
train_batch_size = 1

network_module = "lycoris.kohya"
lycoris_algo = "lokr"
lokr_factor = -1
network_dim = 16
network_alpha = 16
network_train_unet_only = true

unet_lr = 5e-5
text_encoder_lr = 1e-5
lr_scheduler = "cosine_with_restarts"
lr_scheduler_num_cycles = 1
optimizer_type = "AdamW8bit"

mixed_precision = "bf16"
gradient_checkpointing = true
blocks_to_swap = 16            # CPU<->GPU swap; lower this if VRAM allows
cache_latents = true
cache_latents_to_disk = true
cache_text_encoder_outputs = true
cache_text_encoder_outputs_to_disk = true
caption_extension = ".txt"
prefer_json_caption = true
shuffle_caption = false
keep_tokens = 1
seed = 1337
clip_skip = 2
max_data_loader_n_workers = 0
enable_preview = false
```

---

### Notes

- These set `unet_lr=5e-5` explicitly (the server would rewrite the legacy `1e-4`
  default to this anyway for Anima).
- `prefer_json_caption = true` is kept only for parity with the trainer UI's own
  autosaved configs — it is **UI-only in v2.7.0** (no code reads `.json`
  sidecars), so captions must be single-line `.txt` regardless
  (`caption-guide.md`).
- For an **8 GB** card add `blocks_to_swap = 24` to preset 3.
- To get training previews, set `enable_preview = true` and add the
  `positive_prompts` / `sample_*` keys from `anima-params.md`.
- For SD1.5 / SDXL / Flux, switch `model_train_type` and the model paths; the
  generic LR/dataset/caption keys carry over (see the trainer's other schemas).
