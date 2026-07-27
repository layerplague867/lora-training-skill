import json
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
PROMPT = (
    "An anime screenshot of mychar, a lazy chainsmoker cat girl with messy "
    "pale sage-green hair, fluffy cat ears pierced with small earrings, and "
    "tired droopy brown eyes. A cigarette dangles from her mouth as she "
    "slouches against the wall of a dim, cluttered apartment, looking "
    "unimpressed. Flat cel-shaded anime style."
)
SEED = 7


def api(path, payload=None):
    req = urllib.request.Request(BASE + path)
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


nodes = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "krea2turbo_INT8_comfyfixed.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
    "4": {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {"lora_name": "mychar-krea2-v1.safetensors", "strength_model": 1.0, "model": ["1", 0]},
    },
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["2", 0]}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
    "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "8": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["4", 0],
            "positive": ["5", 0],
            "negative": ["6", 0],
            "latent_image": ["7", 0],
            "seed": SEED,
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "er_sde",
            "scheduler": "simple",
            "denoise": 1.0,
        },
    },
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
    "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "krea2int8_natural_lang"}},
}

t0 = time.time()
pid = api("/prompt", {"prompt": nodes})["prompt_id"]
while True:
    time.sleep(3)
    hist = api("/history/" + pid)
    if pid in hist:
        if hist[pid].get("status", {}).get("status_str") == "error":
            print("ERROR:", json.dumps(hist[pid]["status"])[:1500])
            break
        outputs = hist[pid].get("outputs", {})
        if outputs:
            for node_out in outputs.values():
                for img in node_out.get("images", []):
                    print(f"{img['filename']}  ({time.time() - t0:.0f}s)")
            break
    if time.time() - t0 > 600:
        print("TIMEOUT")
        break
