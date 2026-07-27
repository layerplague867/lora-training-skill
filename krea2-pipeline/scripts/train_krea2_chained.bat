@echo off
rem Cache → cache → train, optionally after another job finishes.
rem   train_krea2_chained.bat            → start now
rem   train_krea2_chained.bat 12345      → wait for PID 12345 first
rem Chaining by PID is how you queue a second LoRA behind a running one on a
rem single GPU without babysitting a terminal.

call "%~dp0env.bat"
cd /d %MUSUBI%
set LOG="%LOGDIR%\%NAME%-chain.log"
set WAIT_PID=%~1

if not "%WAIT_PID%"=="" (
  echo [chain] waiting for PID %WAIT_PID% to finish... > %LOG%
  powershell -NoProfile -Command "Wait-Process -Id %WAIT_PID% -ErrorAction SilentlyContinue"
) else (
  echo [chain] starting immediately > %LOG%
)

echo [chain] caching latents... >> %LOG%
%PY% src/musubi_tuner/krea2_cache_latents.py ^
  --dataset_config "%WORK%/musubi_dataset.toml" --vae "%VAE%" >> %LOG% 2>&1
if errorlevel 1 (echo [chain] LATENT CACHE FAILED >> %LOG% & exit /b 1)

echo [chain] caching text encoder outputs... >> %LOG%
%PY% src/musubi_tuner/krea2_cache_text_encoder_outputs.py ^
  --dataset_config "%WORK%/musubi_dataset.toml" --text_encoder "%TE%" ^
  --batch_size 1 >> %LOG% 2>&1
if errorlevel 1 (echo [chain] TE CACHE FAILED >> %LOG% & exit /b 1)

echo [chain] starting training... >> %LOG%
call "%~dp0train_krea2.bat"
echo [chain] done, exit code %errorlevel% >> %LOG%
