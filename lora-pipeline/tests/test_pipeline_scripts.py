"""Focused tests for local pipeline behavior and external job status handling."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from PIL import Image

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load pipeline script: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_dataset = load_script("build_dataset")
curate = load_script("curate")
dataset_profile = load_script("dataset_profile")
make_civitai_pack = load_script("make_civitai_pack")
tag_dataset = load_script("tag_dataset")
validate = load_script("validate")


class BuildDatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary_dir = tempfile.mkdtemp(prefix="pipeline-build-")
        self.work = Path(self.temporary_dir)
        self.raw = self.work / "raw"
        self.raw.mkdir()

    def tearDown(self):
        shutil.rmtree(self.temporary_dir, ignore_errors=True)

    def write_manifest(self, names: list[str]) -> None:
        records = []
        for index, name in enumerate(names):
            image = self.raw / name
            Image.new("RGB", (64, 64), (index, 0, 0)).save(image)
            records.append({"file": name, "mode": "RGB"})
        (self.work / "curation_manifest.json").write_text(
            json.dumps({"keep": records, "drop": []}),
            encoding="utf-8",
        )

    def test_rebuild_replaces_stale_concept_files(self):
        self.write_manifest(["current.png"])
        concept = self.work / "dataset" / "5_zkz"
        concept.mkdir(parents=True)
        Image.new("RGB", (64, 64), "red").save(concept / "stale.png")

        result = build_dataset.build_dataset(self.work, "zkz", 5)

        self.assertEqual(result["images"], 1)
        self.assertEqual(sorted(path.name for path in concept.iterdir()), ["current.png"])

    def test_build_fails_when_manifest_source_is_missing(self):
        (self.work / "curation_manifest.json").write_text(
            json.dumps({"keep": [{"file": "missing.png", "mode": "RGB"}], "drop": []}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(FileNotFoundError, "missing.png"):
            build_dataset.build_dataset(self.work, "zkz", 5)

        self.assertFalse((self.work / "dataset").exists())

    def test_build_rejects_concept_path(self):
        self.write_manifest(["current.png"])

        with self.assertRaisesRegex(ValueError, "single directory name"):
            build_dataset.build_dataset(self.work, "../outside", 5)

        self.assertFalse((self.work / "dataset").exists())


class CollectTests(unittest.TestCase):
    def test_dry_run_does_not_create_work_files(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-collect-") as temporary_dir:
            root = Path(temporary_dir)
            downloader = root / "downloader"
            downloader.mkdir()
            (downloader / "main.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            work = root / "work"

            result = subprocess.run(
                [
                    sys.executable,
                    str(_SCRIPTS / "collect.py"),
                    "--tag",
                    "example_character",
                    "--work",
                    str(work),
                    "--downloader-dir",
                    str(downloader),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(work.exists())


class ExternalJobStatusTests(unittest.TestCase):
    def test_tagger_error_status_raises(self):
        with self.assertRaisesRegex(RuntimeError, "tag failed"):
            tag_dataset.is_progress_complete(
                "/api/tag/progress",
                {"status": "error", "message": "tag failed"},
            )

    def test_tagger_done_status_completes(self):
        self.assertTrue(
            tag_dataset.is_progress_complete(
                "/api/tag/progress",
                {"status": "completed"},
            )
        )

    def test_tagger_idle_status_does_not_silently_complete(self):
        with self.assertRaisesRegex(RuntimeError, "idle before completion"):
            tag_dataset.is_progress_complete("/api/tag/progress", {"status": "idle"})

    def test_tagger_thresholds_are_model_specific(self):
        eva = tag_dataset.resolve_general_threshold("wd-eva02-large-tagger-v3", None)
        swin = tag_dataset.resolve_general_threshold("wd-swinv2-tagger-v3", None)

        self.assertEqual(eva, 0.5296)
        self.assertEqual(swin, 0.2653)
        self.assertNotEqual(eva, swin)

    def test_post_tag_semantic_review_uses_subject_profile(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-tag-audit-") as temporary_dir:
            concept = Path(temporary_dir)
            (concept / "good.txt").write_text("1boy, solo, zkz", encoding="utf-8")
            (concept / "bad.txt").write_text("1girl, solo, zkz", encoding="utf-8")

            warnings = tag_dataset.semantic_warnings(concept, "1boy")

            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0]["tags"], ["1girl"])

    def test_comfy_error_history_raises(self):
        history = {
            "status": {
                "status_str": "error",
                "messages": [["execution_error", {"exception_message": "node failed"}]],
            }
        }

        with self.assertRaisesRegex(RuntimeError, "node failed"):
            validate.require_successful_history("prompt-1", history)

    def test_validation_profiles_are_not_hardcoded_to_female(self):
        male = validate.validation_shots("character", "1boy")
        style = validate.validation_shots("style", None)

        self.assertTrue(all(count == "1boy" for _name, count, _prompt, _seed, _w, _h in male))
        self.assertTrue(any(count == "1girl" for _name, count, _prompt, _seed, _w, _h in style))
        self.assertTrue(any(count == "1boy" for _name, count, _prompt, _seed, _w, _h in style))

    def test_validation_prompt_uses_anima_section_order(self):
        prompt = validate.positive_prompt("mych4r", "1girl", "solo, outdoors")

        self.assertEqual(
            prompt,
            "masterpiece, best quality, score_7, safe, 1girl, mych4r, solo, outdoors",
        )


class DatasetProfileTests(unittest.TestCase):
    def test_male_profile_keeps_male_and_rejects_female(self):
        keywords = dataset_profile.offmodel_keywords("1boy")

        self.assertNotIn("1boy", keywords)
        self.assertIn("1girl", keywords)

    def test_natural_language_is_not_parsed_as_tags(self):
        tags = dataset_profile.parse_tags_text(
            "safe, 1boy, zkz, solo. A 1girl appears only in this sentence."
        )

        self.assertNotIn("1girl", tags)

    def test_danbooru_source_url_is_retained_when_filename_is_post_id(self):
        self.assertEqual(
            curate.source_url(Path("123456.png")),
            "https://danbooru.donmai.us/posts/123456",
        )
        self.assertIsNone(curate.source_url(Path("custom-name.png")))


class CivitaiPackTests(unittest.TestCase):
    def test_rebuild_removes_stale_samples(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-pack-") as temporary_dir:
            work = Path(temporary_dir)
            lora = work / "model.safetensors"
            lora.write_bytes(b"model")
            validation = work / "validation" / lora.stem
            validation.mkdir(parents=True)
            Image.new("RGB", (64, 64), "green").save(validation / "current.png")
            baseline = work / "validation" / "baseline"
            baseline.mkdir()
            Image.new("RGB", (64, 64), "blue").save(baseline / "baseline.png")
            old_samples = work / "civitai_upload" / "samples"
            old_samples.mkdir(parents=True)
            Image.new("RGB", (64, 64), "red").save(old_samples / "stale.png")

            result = make_civitai_pack.build_pack(
                work,
                "zkz",
                "zkz",
                "zkz-anima-v2",
                lora,
                "ZKZ - Anima",
                "Example Series",
                "Character",
                "portrait",
                False,
            )

            samples = work / "civitai_upload" / "samples"
            self.assertEqual(result["samples"], 1)
            self.assertEqual(sorted(path.name for path in samples.iterdir()), ["current.png"])
            config = json.loads(Path(result["config"]).read_text(encoding="utf-8"))
            self.assertEqual(config["version_name"], "v2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
