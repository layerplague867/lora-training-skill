@echo off
rem Train one Krea 2 character LoRA. Recipe fits 12.9B in ~17 GB VRAM.
rem Prereq: env.bat (copy from env.example.bat) + %WORK%/musubi_dataset.toml,
rem         with latents/TE outputs already cached (see train_krea2_chained.bat).
rem Launch detached for long runs:  Start-Process -FilePath .\train_krea2.bat

call "%~dp0env.bat"
cd /d %MUSUBI%
set LOG="%LOGDIR%\%NAME%.log"

%PY% -m accelerate.commands.launch ^
  --num_processes 1 --num_machines 1 --num_cpu_threads_per_process 1 ^
  --mixed_precision bf16 --dynamo_backend no ^
  src/musubi_tuner/krea2_train_network.py ^
  --dit "%DIT_RAW%" --vae "%VAE%" ^
  --dataset_config "%WORK%/musubi_dataset.toml" ^
  --sdpa --mixed_precision bf16 ^
  --timestep_sampling shift --weighting_scheme none --discrete_flow_shift 2.5 ^
  --optimizer_type adamw8bit --learning_rate 1e-4 ^
  --gradient_checkpointing --fp8_base --fp8_scaled --blocks_to_swap 16 ^
  --max_data_loader_n_workers 2 --persistent_data_loader_workers ^
  --network_module networks.lora_krea2 --network_dim 32 --network_alpha 32 ^
  --max_train_epochs 12 --save_every_n_epochs 4 ^
  --save_every_n_steps 150 --save_state --save_last_n_steps_state 300 ^
  --logging_dir "%LOGDIR%" --log_prefix %NAME% --seed 42 ^
  --output_dir "%WORK%/output" --output_name "%NAME%" > %LOG% 2>&1

echo [train] %NAME% finished with exit code %errorlevel% >> %LOG%
