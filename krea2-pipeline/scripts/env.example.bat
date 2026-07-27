@echo off
rem ---------------------------------------------------------------------------
rem Copy to env.bat and edit for your machine. Every other .bat calls this.
rem env.bat is gitignored so your local paths never get committed.
rem ---------------------------------------------------------------------------

rem Python that has musubi-tuner's deps installed (embedded python is fine).
set PY="C:\ai-toolkit\python_embeded\python.exe"

rem Clone of https://github.com/kohya-ss/musubi-tuner
set MUSUBI=C:\musubi-tuner

rem Krea 2 RAW weights — train against these.
set DIT_RAW=C:/models/krea2-raw/raw.safetensors

rem Krea 2 Turbo weights — validate/generate with these (8 steps, CFG 1.0).
set DIT_TURBO=C:/models/krea2-turbo/turbo.safetensors

rem Qwen3-VL-4B text encoder. Point at the SINGLE safetensors file, not the
rem HF folder — musubi's krea2 loader expects one file.
set TE=C:/models/krea2-raw/text_encoder/model.safetensors

rem Qwen-Image VAE (shared with Anima).
set VAE=C:/models/anima/models/vae/qwen_image_vae.safetensors

rem Per-run working dir: expects musubi_dataset.toml inside, writes output/ here.
set WORK=D:/work/mychar

rem Trigger / output name for the LoRA.
set NAME=mychar-krea2-v1

rem Where logs go.
set LOGDIR=%MUSUBI%\logs
