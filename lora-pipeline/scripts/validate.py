"""Phase 6 — VALIDATE. Generate a small varied gallery with the trained LoRA on
Anima via the local ComfyUI API, so you (and the Civitai page) can see whether the
character is consistent before publishing.

The workflow is the verified Anima graph: UNETLoader(anima base) + CLIPLoader(qwen3)
+ VAELoader(qwen vae) -> LoraLoader -> dpmpp_2m_sde_gpu / beta57, cfg 4.4, 32 steps.
Copy your trained <name>.safetensors into ComfyUI/models/loras/ first.

Usage:
  python validate.py --work "D:/work/mychar" --lora mychar-anima-v1.safetensors --trigger mychar
Environment overrides:
  COMFY_URL   base URL of ComfyUI (default http://127.0.0.1:8188)
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
BASE_UNET = os.environ.get("ANIMA_UNET", r"Anima\anime\anima_baseV10.safetensors")
QWEN_CLIP = "qwen_3_06b_base.safetensors"
QWEN_VAE = "qwen_image_vae.safetensors"
NEG = (
    "low quality, worst quality, lowres, bad anatomy, bad hands, extra digits, "
    "watermark, signature, text, jpeg artifacts, blurry"
)
QUALITY = "masterpiece, best quality, newest, highres"

# (suffix, scene-specific prompt fragment, seed)
SHOTS = [
    (
        "portrait",
        "solo, close-up, portrait, looking at viewer, detailed face, soft smile, simple background",
        7001,
    ),
    (
        "scene",
        "solo, upper body, smile, outdoors, cherry blossoms, day, wind, looking at viewer",
        7002,
    ),
    (
        "fullbody",
        "solo, full body, standing, cowboy shot, city street, day, looking at viewer, simple background",
        7003,
    ),
]


def build(pos: str, seed: int, prefix: str, lora: str, strength: float) -> dict:
    return {
        "prompt": {
            "15": {"class_type": "VAELoader", "inputs": {"vae_name": QWEN_VAE}},
            "44": {
                "class_type": "UNETLoader",
                "inputs": {"unet_name": BASE_UNET, "weight_dtype": "default"},
            },
            "45": {
                "class_type": "CLIPLoader",
                "inputs": {"clip_name": QWEN_CLIP, "type": "stable_diffusion"},
            },
            "101": {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": ["44", 0],
                    "clip": ["45", 0],
                    "lora_name": lora,
                    "strength_model": strength,
                    "strength_clip": strength,
                },
            },
            "11": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["101", 1], "text": pos},
            },
            "12": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["101", 1], "text": NEG},
            },
            "28": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 896, "height": 1152, "batch_size": 2},
            },
            "19": {
                "class_type": "KSampler",
                "inputs": {
                    "model": ["101", 0],
                    "positive": ["11", 0],
                    "negative": ["12", 0],
                    "latent_image": ["28", 0],
                    "seed": seed,
                    "steps": 32,
                    "cfg": 4.4,
                    "sampler_name": "dpmpp_2m_sde_gpu",
                    "scheduler": "beta57",
                    "denoise": 1.0,
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["19", 0], "vae": ["15", 0]},
            },
            "48": {
                "class_type": "SaveImage",
                "inputs": {"images": ["8", 0], "filename_prefix": prefix},
            },
        }
    }


def post(wf: dict) -> str:
    req = urllib.request.Request(
        COMFY + "/prompt",
        data=json.dumps(wf).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode())["prompt_id"]


def wait(pid: str, timeout: int = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with urllib.request.urlopen(f"{COMFY}/history/{pid}", timeout=20) as r:  # noqa: S310
            h = json.loads(r.read().decode())
        if pid in h:
            return h[pid]
        time.sleep(3)
    raise TimeoutError(f"comfy job {pid} timed out")


def save(hist: dict, outdir: Path) -> int:
    n = 0
    for out in hist.get("outputs", {}).values():
        for img in out.get("images", []):
            url = (
                f"{COMFY}/view?filename={urllib.parse.quote(img['filename'])}"
                f"&subfolder={urllib.parse.quote(img.get('subfolder', ''))}&type={img.get('type', 'output')}"
            )
            with urllib.request.urlopen(url, timeout=30) as r:  # noqa: S310
                (outdir / img["filename"]).write_bytes(r.read())
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generate an Anima+LoRA validation gallery."
    )
    ap.add_argument(
        "--work", required=True, help="project dir; images saved to <work>/validation/"
    )
    ap.add_argument(
        "--lora", required=True, help="lora filename as seen in ComfyUI/models/loras/"
    )
    ap.add_argument("--trigger", required=True)
    ap.add_argument("--strength", type=float, default=0.9)
    a = ap.parse_args()

    outdir = Path(a.work).resolve() / "validation"
    outdir.mkdir(parents=True, exist_ok=True)
    total = 0
    for suffix, frag, seed in SHOTS:
        pos = f"{QUALITY}, 1girl, {a.trigger}, {frag}"
        prefix = f"{a.trigger}_val_{suffix}"
        pid = post(build(pos, seed, prefix, a.lora, a.strength))
        print(f"{prefix}: {pid} ...", end=" ", flush=True)
        h = wait(pid)
        got = save(h, outdir)
        total += got
        print(f"saved {got}  status={h.get('status', {}).get('status_str')}")
    print(f"\ntotal {total} images -> {outdir}")
    print(
        "Inspect them: consistent identity across shots = good. Same-pose/stiff-face = overfit,"
    )
    print(
        "retry an earlier epoch snapshot. Weak identity = raise --strength or add epochs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
