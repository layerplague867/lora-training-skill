r"""Phase 7a — PACKAGE FOR CIVITAI. Assemble a self-contained upload package that the
civitai-uploader tool can drive: a model card, a *.civitai.json config, the trained
.safetensors, and a samples/ folder of validation images.

Produces <work>/civitai_upload/ with:
  MODEL_CARD.md            generated description (edit before publishing if you like)
  <name>.civitai.json      config consumed by civitai-uploader (upload.bat)
  <name>.safetensors       copied from --lora-file
  samples/*.png            copied from <work>/validation/<lora-stem>/

Then hand it to the uploader (never auto-publishes):
  <civitai-uploader>\upload.bat  <work>\civitai_upload\<name>.civitai.json
It fills the 4-step wizard, uploads file + samples, and STOPS at Draft for you to Publish.

Usage:
  python make_civitai_pack.py --work "D:/work/mychar" --concept mychar --trigger mychar \
      --name mychar-anima-v1 --lora-file "D:/work/mychar/output/mychar-anima-v1/mychar-anima-v1.safetensors" \
      --display "My Character (My Series) - Anima" --series "My Series"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

MODEL_CARD = """# {display}

A character LoRA for **{concept}**{series_line}, trained on the **Anima** base model.

## ✨ Trigger word
`{trigger}`

Put `{trigger}` near the front of your prompt. The character's signature look comes
through from the trigger alone — you don't need to describe them manually.

## 🎨 Recommended usage
- Base model: **Anima** (anima-base-v1.0 family: anima_baseV10 / animayume / animaOfficial).
- LoRA strength: **0.8 – 1.0** (0.9 is a good default).
- Sampler / scheduler: **dpmpp_2m_sde_gpu + beta57** (Euler / Rectified-Flow also fine).
- CFG: **4.0 – 4.5** · Steps: **30 – 40**.
- Quality prefix: `masterpiece, best quality, score_7, safe`.
- Add outfit / pose / background tags freely — identity stays consistent because those
  were captioned during training (changeable, not baked in).

## 🧠 Training details
- Type: **LoRA** · trainer: lora-scripts-next / SD-Trainer (Anima LoRA).
- Auto-tagged with WD14, Anima-sectioned captions, deduped & structurally checked (dataset-doctor).

## ⚠️ Notes
- Fan-made, for non-commercial fan use. Not affiliated with the original work or artists.
"""

STYLE_MODEL_CARD = """# {display}

A **style LoRA** that brings the art style of **{concept}** to the **Anima** base model.

## ✨ Trigger
`{trigger}`

Anima invokes artists with an `@` prefix, so this LoRA's trigger is `{trigger}`. Put it near
the front of your prompt (you can weight it, e.g. `({trigger}:1.1)`), then describe whatever
subject, pose or scene you want — the **style rides on the trigger, the content is yours**.

## 🎨 Recommended usage
- Base model: **Anima** (anima-base-v1.0 family: anima_baseV10 / animaOfficial).
- LoRA strength: **0.7 – 1.0** (0.8–0.9 default; lower to blend with other styles/artists).
- Sampler: **dpmpp_2m_sde_gpu**, **er_sde** or **euler_a** · scheduler **beta57** · CFG **4.0–4.5** · Steps **30–40**.
- Quality prefix: `masterpiece, best quality, score_7, safe`.
- Stacks with character LoRAs and with other Anima `@artist` tags.

## 🧠 Training details
- Type: **LoRA (style)** · base **Anima base v1.0** · trainer lora-scripts-next / SD-Trainer.
- Captions: WD14 content tags with **style/medium/artist tags stripped by category** so the
  trigger — not an explicit tag — carries the look. Trained **unet-only** (the LLM adapter is
  left untouched, per the Anima training guide), **LR 2e-5**, **rank 32**, 1024px buckets.

## 🙏 Credit
Style trained from the works of the Danbooru artist **{concept}**. All credit for the original
art style belongs to the artist — this is a fan-made, non-commercial tool. Please support the
original artist, and I'll remove this on request.
"""


def version_name_from_output_name(name: str) -> str:
    match = re.search(r"(?:^|[-_])v(\d+)$", name, flags=re.IGNORECASE)
    return f"v{match.group(1)}" if match else "v1"


def build_pack(
    work: Path,
    concept: str,
    trigger: str,
    name: str,
    lora: Path,
    display: str,
    series: str,
    category: str,
    extra_tags: str,
    nsfw: bool,
) -> dict[str, int | str]:
    if not lora.is_file():
        raise FileNotFoundError(f"LoRA file not found: {lora}")

    pack = work / "civitai_upload"
    staging = work / ".civitai_upload.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    samples = staging / "samples"
    samples.mkdir(parents=True)

    try:
        series_line = f" from *{series}*" if series else ""
        card = STYLE_MODEL_CARD if category == "Style" else MODEL_CARD
        (staging / "MODEL_CARD.md").write_text(
            card.format(
                display=display,
                concept=concept,
                trigger=trigger,
                series_line=series_line,
            ),
            encoding="utf-8",
        )
        shutil.copy2(lora, staging / lora.name)

        validation_root = work / "validation"
        checkpoint_validation = validation_root / lora.stem
        validation = checkpoint_validation if checkpoint_validation.is_dir() else validation_root
        sample_count = 0
        if validation.is_dir():
            for image in sorted(validation.glob("*.png")):
                shutil.copy2(image, samples / image.name)
                sample_count += 1

        base_tags = (
            [concept] + ([series.lower()] if series else []) + [category.lower(), "anime", "anima"]
        )
        supplied_tags = [tag.strip() for tag in extra_tags.split(",") if tag.strip()]
        tags = list(dict.fromkeys(base_tags + supplied_tags))
        config = {
            "slug": concept,
            "name": display,
            "type": "LORA",
            "category": category,
            "tags": tags,
            "description_file": "MODEL_CARD.md",
            "version_name": version_name_from_output_name(name),
            "base_model": "Anima",
            "trigger_words": [trigger],
            "files": [lora.name],
            "images_dir": "samples",
            "nsfw": nsfw,
        }
        config_name = f"{name}.civitai.json"
        (staging / config_name).write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if pack.exists():
            shutil.rmtree(pack)
        staging.replace(pack)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return {
        "pack": str(pack),
        "model": lora.name,
        "samples": sample_count,
        "config": str(pack / config_name),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a Civitai upload package from a trained LoRA.")
    ap.add_argument("--work", required=True)
    ap.add_argument("--concept", required=True, help="lowercase concept/trigger, e.g. mychar")
    ap.add_argument("--trigger", required=True)
    ap.add_argument("--name", required=True, help="output/version base name, e.g. mychar-anima-v1")
    ap.add_argument(
        "--lora-file", required=True, help="path to the trained .safetensors to publish"
    )
    ap.add_argument("--display", default="", help="human title; default derived from --name")
    ap.add_argument("--series", default="", help="series/franchise, e.g. 'My Series'")
    ap.add_argument("--category", default="Character", choices=["Character", "Style", "Concept"])
    ap.add_argument("--tags", default="", help="comma-separated extra tags")
    ap.add_argument("--nsfw", action="store_true")
    a = ap.parse_args()

    work = Path(a.work).resolve()
    lora = Path(a.lora_file)
    if not lora.exists():
        print(f"ERROR: --lora-file not found: {lora}")
        return 2

    display = a.display or f"{a.concept.title()} - Anima"
    result = build_pack(
        work,
        a.concept,
        a.trigger,
        a.name,
        lora,
        display,
        a.series,
        a.category,
        a.tags,
        bool(a.nsfw),
    )

    print(f"package  : {result['pack']}")
    print(f"model    : {result['model']}")
    print(f"samples  : {result['samples']}")
    print(f"config   : {Path(str(result['config'])).name}")
    print("\nnext (never auto-publishes — stops at Draft):")
    print(f'  <civitai-uploader>\\upload.bat "{result["config"]}"')
    if result["samples"] == 0:
        print("NOTE: no samples found — run validate.py first so the Civitai post has images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
