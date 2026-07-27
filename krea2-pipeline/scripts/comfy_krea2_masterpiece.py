import json
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
PROMPT = (
    "A cinematic anime screenshot, flat cel-shaded style. Late night on a steel "
    "pedestrian bridge high above a vast glowing city. mychar, a lazy chainsmoker "
    "cat girl with messy pale sage-green hair, fluffy cat ears pierced with small "
    "silver earrings and tired droopy brown eyes, leans forward on the railing with "
    "a lit cigarette dangling from her mouth, thin smoke curling up into the cold "
    "night air. Next to her stands mychar2, her strict younger sister, a neat "
    "white-haired cat girl with a blue side hairclip, sharp red eyes and a dark "
    "school blazer, arms crossed, glaring at the cigarette with an annoyed pout. "
    "Below and behind them, an endless sea of skyscraper lights, neon signs and "
    "tiny moving cars stretches to the horizon under a deep blue starry sky. Wind "
    "blows their hair. Detailed background, dramatic rim lighting from the city "
    "glow, wide cinematic composition."
)


def api(path, payload=None):
    req = urllib.request.Request(BASE + path)
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build(seed):
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "krea2turbo_INT8_comfyfixed.safetensors", "weight_dtype": "default"},
        },
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "4": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"lora_name": "mychar-krea2-v1.safetensors", "strength_model": 0.9, "model": ["1", 0]},
        },
        "4b": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"lora_name": "mychar2-krea2-v1.safetensors", "strength_model": 1.0, "model": ["4", 0]},
        },
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1920, "height": 1088, "batch_size": 1}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4b", 0],
                "positive": ["5", 0],
                "negative": ["6", 0],
                "latent_image": ["7", 0],
                "seed": seed,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "er_sde",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": f"krea2_masterpiece_s{seed}"}},
    }


for seed in (777, 2026):
    t0 = time.time()
    pid = api("/prompt", {"prompt": build(seed)})["prompt_id"]
    while True:
        time.sleep(4)
        hist = api("/history/" + pid)
        if pid in hist:
            if hist[pid].get("status", {}).get("status_str") == "error":
                print(f"seed {seed} ERROR:", json.dumps(hist[pid]["status"])[:1200])
                break
            outputs = hist[pid].get("outputs", {})
            if outputs:
                for node_out in outputs.values():
                    for img in node_out.get("images", []):
                        print(f"seed {seed}: {img['filename']}  ({time.time() - t0:.0f}s)")
                break
        if time.time() - t0 > 900:
            print(f"seed {seed} TIMEOUT")
            break
