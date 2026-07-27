"""Phase 6 — VALIDATE. Generate a small varied gallery with the trained LoRA on
Anima via the local ComfyUI API, so you (and the Civitai page) can see whether the
character is consistent before publishing.

The workflow is the verified Anima graph: UNETLoader(anima base) + CLIPLoader(qwen3)
+ VAELoader(qwen vae) -> LoraLoader -> dpmpp_2m_sde_gpu / beta57, cfg 4.4, 32 steps.
Copy your trained <name>.safetensors into ComfyUI/models/loras/ first.

Usage:
  python validate.py --work "D:/work/mychar" --lora early.safetensors final.safetensors \
      --trigger mych4r --target character --subject-tag 1girl
Environment overrides:
  COMFY_URL   base URL of ComfyUI (default http://127.0.0.1:8188)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
REQUEST_ATTEMPTS = 3
BASE_UNET = os.environ.get("ANIMA_UNET", r"Anima\anime\anima_baseV10.safetensors")
QWEN_CLIP = "qwen_3_06b_base.safetensors"
QWEN_VAE = "qwen_image_vae.safetensors"
NEG = (
    "low quality, worst quality, lowres, bad anatomy, bad hands, extra digits, "
    "watermark, signature, text, jpeg artifacts, blurry"
)
QUALITY = "masterpiece, best quality, score_7, safe"

# Character tuple: (suffix, scene-specific prompt fragment, seed, width, height)
CHARACTER_SHOTS: tuple[tuple[str, str, int, int, int], ...] = (
    (
        "portrait",
        "solo, close-up, portrait, looking at viewer, detailed face, soft smile, simple background",
        7001,
        896,
        1152,
    ),
    (
        "scene",
        "solo, upper body, smile, outdoors, cherry blossoms, day, wind, looking at viewer",
        7002,
        1152,
        896,
    ),
    (
        "fullbody",
        "solo, full body, standing, cowboy shot, city street, day, looking at viewer, simple background",
        7003,
        896,
        1152,
    ),
)

STYLE_SHOTS: tuple[tuple[str, str, str, int, int, int], ...] = (
    (
        "portrait",
        "1girl",
        "solo, close-up portrait, detailed face, studio lighting",
        7001,
        896,
        1152,
    ),
    ("action", "1boy", "solo, full body, running, city street, dramatic lighting", 7002, 896, 1152),
    ("landscape", "", "mountain lake, forest, clouds, wide establishing shot", 7003, 1152, 896),
)


def validation_shots(
    target: str, subject_tag: str | None
) -> tuple[tuple[str, str, str, int, int, int], ...]:
    if target == "style":
        return STYLE_SHOTS
    if target != "character":
        raise ValueError(f"target must be character or style: {target!r}")
    if not subject_tag:
        raise ValueError("character validation requires a subject tag")
    return tuple(
        (suffix, subject_tag, fragment, seed, width, height)
        for suffix, fragment, seed, width, height in CHARACTER_SHOTS
    )


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    if not safe:
        raise ValueError(f"LoRA filename has no safe stem: {filename!r}")
    return safe


def positive_prompt(trigger: str, count: str, fragment: str) -> str:
    count_section = f"{count}, " if count else ""
    return f"{QUALITY}, {count_section}{trigger}, {fragment}"


def read_response(request: str | urllib.request.Request, timeout: int) -> bytes:
    request_url = request.full_url if isinstance(request, urllib.request.Request) else request
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return response.read()
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")
            detail = {
                "request": request_url,
                "status": exc.code,
                "response": response_body,
                "attempt": attempt,
            }
            if attempt == REQUEST_ATTEMPTS:
                raise RuntimeError(f"ComfyUI request failed: {json.dumps(detail)}") from exc
            print(
                "WARNING: ComfyUI request failed",
                json.dumps(detail),
                flush=True,
            )
            time.sleep(attempt)
        except (TimeoutError, urllib.error.URLError) as exc:
            detail = {"request": request_url, "attempt": attempt, "error": str(exc)}
            if attempt == REQUEST_ATTEMPTS:
                raise RuntimeError(f"ComfyUI request failed: {json.dumps(detail)}") from exc
            print("WARNING: ComfyUI request failed", json.dumps(detail), flush=True)
            time.sleep(attempt)
    raise RuntimeError("ComfyUI request exhausted without result")


def require_successful_history(prompt_id: str, history: dict) -> dict:
    status = history.get("status", {})
    if status.get("status_str") != "error":
        return history

    messages = status.get("messages", [])
    detail = ""
    for message in messages:
        if isinstance(message, list) and len(message) > 1 and isinstance(message[1], dict):
            detail = str(
                message[1].get("exception_message") or message[1].get("exception_type") or ""
            )
            if detail:
                break
    if not detail:
        detail = json.dumps(status, ensure_ascii=False)
    raise RuntimeError(f"ComfyUI job failed: prompt_id={prompt_id} detail={detail}")


def build(
    pos: str,
    seed: int,
    prefix: str,
    lora: str,
    strength: float,
    width: int,
    height: int,
) -> dict:
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
                "inputs": {"width": width, "height": height, "batch_size": 2},
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
    response = json.loads(read_response(req, 30).decode())
    prompt_id = response.get("prompt_id") if isinstance(response, dict) else None
    if not isinstance(prompt_id, str) or not prompt_id:
        raise RuntimeError(f"ComfyUI prompt response has no prompt_id: response={response!r}")
    return prompt_id


def wait(pid: str, timeout: int = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = json.loads(read_response(f"{COMFY}/history/{pid}", 20).decode())
        if pid in h:
            return require_successful_history(pid, h[pid])
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
            (outdir / img["filename"]).write_bytes(read_response(url, 30))
            n += 1
    return n


def run_gallery(
    validation_root: Path,
    gallery_name: str,
    lora: str,
    trigger: str,
    strength: float,
    shots: tuple[tuple[str, str, str, int, int, int], ...],
) -> int:
    outdir = validation_root / gallery_name
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)

    total = 0
    for suffix, count, fragment, seed, width, height in shots:
        pos = positive_prompt(trigger, count, fragment)
        prefix = f"{gallery_name}_{suffix}"
        pid = post(build(pos, seed, prefix, lora, strength, width, height))
        print(f"{prefix}: {pid} ...", end=" ", flush=True)
        history = wait(pid)
        saved = save(history, outdir)
        if saved == 0:
            raise RuntimeError(f"ComfyUI job produced no images: prompt_id={pid} history={history}")
        total += saved
        print(f"saved {saved}  status={history.get('status', {}).get('status_str')}")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate an Anima+LoRA validation gallery.")
    ap.add_argument(
        "--work", required=True, help="project dir; galleries saved under <work>/validation/"
    )
    ap.add_argument(
        "--lora",
        required=True,
        nargs="+",
        help="one or more checkpoint filenames as seen in ComfyUI/models/loras/",
    )
    ap.add_argument("--trigger", required=True)
    ap.add_argument("--target", required=True, choices=("character", "style"))
    ap.add_argument("--subject-tag", choices=("1girl", "1boy", "1other"))
    ap.add_argument("--strength", type=float, default=0.9)
    a = ap.parse_args()

    if a.target == "character" and not a.subject_tag:
        ap.error("--subject-tag is required when --target character")
    if a.target == "style" and not a.trigger.startswith("@"):
        ap.error("style triggers must use Anima's @artist namespace")

    shots = validation_shots(a.target, a.subject_tag)
    validation_root = Path(a.work).resolve() / "validation"
    validation_root.mkdir(parents=True, exist_ok=True)

    baseline_lora = a.lora[0]
    baseline_total = run_gallery(
        validation_root,
        "baseline",
        baseline_lora,
        a.trigger,
        0.0,
        shots,
    )
    total = baseline_total
    for lora in a.lora:
        total += run_gallery(
            validation_root,
            safe_stem(lora),
            lora,
            a.trigger,
            a.strength,
            shots,
        )

    print(f"\ntotal {total} images -> {validation_root}")
    print(
        "Compare each checkpoint with baseline at the same seeds. Consistent target behavior "
        "with preserved prompt variation is good; same-pose/stiff-face is overfit."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
