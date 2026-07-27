@echo off
rem Fetch the INT8 Krea 2 Turbo checkpoint for ComfyUI (>= 0.27 for native INT8).
rem On Ampere, INT8 beats fp8 -- INT8 has tensor-core support, fp8 does not.
rem Set COMFY_MODELS to your ComfyUI diffusion_models folder before running.

if "%COMFY_MODELS%"=="" set COMFY_MODELS=C:\ComfyUI\models\diffusion_models
if "%PY%"=="" set PY=python

%PY% -c "from huggingface_hub import hf_hub_download; import os; p = hf_hub_download(repo_id='tsolful/Krea2_Turbo_Raw_INT8', filename='krea2turbo_INT8_comfyfixed.safetensors', local_dir=os.environ['COMFY_MODELS']); print('DOWNLOADED:', p)"
echo [download] finished with exit code %errorlevel%
