@echo off
rem Generate the same fixed-seed prompt set from several checkpoints so you can
rem pick the best one instead of assuming the last epoch wins.
rem Usage:  validate_checkpoints.bat  step00000600 step00001050 final
rem         (bare "final" means %NAME%.safetensors)
rem Train on RAW, validate on Turbo: 8 steps, CFG 1.0 (negatives do nothing).

call "%~dp0env.bat"
cd /d %MUSUBI%
set LOG="%LOGDIR%\%NAME%-validate.log"
set PROMPTS=%~dp0..\prompts\prompts_example_krea2.txt

set GEN=src/musubi_tuner/krea2_generate_image.py --dit "%DIT_TURBO%" ^
  --vae "%VAE%" --text_encoder "%TE%" --steps 8 --guidance_scale 1 --mu 1.15 ^
  --width 1024 --height 1024 --attn_mode torch --fp8_scaled ^
  --blocks_to_swap 8 --block_swap_h2d_only --lora_multiplier 1.0

echo [validate] %NAME% > %LOG%
if "%~1"=="" (echo [validate] pass checkpoint labels as arguments >> %LOG% & exit /b 1)

:loop
if "%~1"=="" goto done
if "%~1"=="final" (
  set LORA=%WORK%/output/%NAME%.safetensors
) else (
  set LORA=%WORK%/output/%NAME%-%~1.safetensors
)
echo [validate] %~1 ... >> %LOG%
%PY% %GEN% --from_file "%PROMPTS%" --lora_weight "%LORA%" ^
  --save_path "%WORK%/validation/%~1" >> %LOG% 2>&1
shift
goto loop

:done
echo [validate] ALL DONE >> %LOG%
