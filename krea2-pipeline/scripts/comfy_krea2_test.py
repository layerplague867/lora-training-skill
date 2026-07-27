import json
import time
import urllib.request

BASE = "http://127.0.0.1:8188"
PROMPT = (
    "masterpiece, best quality, 1girl, mychar, solo, green hair, cat ears, "
    "brown eyes, ear piercing, cigarette, smoking, looking at viewer, upper body"
)
SEED = 42


def api(path, payload=None):
    req = urllib.request.Request(BASE + path)
    if payload is not None:
        req.data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def find_lora_name():
    info = api("/object_info/LoraLoaderModelOnly")
    names = info["LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
    for n in names:
        if "mychar-krea2-v1" in n:
            return n
    raise SystemExit("LoRA not found in ComfyUI list! refresh needed?")


def build(use_lora, lora_name):
    nodes = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": "krea2turbo_INT8_comfyfixed.safetensors", "weight_dtype": "default"},
        },
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_4b_fp8_scaled.safetensors", "type": "krea2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "", "clip": ["2", 0]}},
        "7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {
            "class_type": "SaveImage",
            "inputs": {"images": ["9", 0], "filename_prefix": "krea2int8_" + ("with_lora" if use_lora else "no_lora")},
        },
    }
    model_src = ["1", 0]
    if use_lora:
        nodes["4"] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"lora_name": lora_name, "strength_model": 1.0, "model": ["1", 0]},
        }
        model_src = ["4", 0]
    nodes["8"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": model_src,
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
    }
    return nodes


def run(use_lora, lora_name):
    label = "with_lora" if use_lora else "no_lora"
    t0 = time.time()
    res = api("/prompt", {"prompt": build(use_lora, lora_name)})
    pid = res["prompt_id"]
    while True:
        time.sleep(3)
        hist = api("/history/" + pid)
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                print(label, "ERROR:", json.dumps(status)[:2000])
                return None
            outputs = entry.get("outputs", {})
            if outputs:
                for node_out in outputs.values():
                    for img in node_out.get("images", []):
                        print(f"{label}: {img['filename']}  ({time.time() - t0:.0f}s)")
                        return img["filename"]
        if time.time() - t0 > 900:
            print(label, "TIMEOUT")
            return None


lora = find_lora_name()
print("lora entry:", lora)
f1 = run(True, lora)
f2 = run(False, lora)
print("DONE", f1, f2)
