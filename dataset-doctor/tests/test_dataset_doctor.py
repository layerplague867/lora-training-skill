"""Unit + smoke tests for the dataset-doctor scripts.

Stdlib-only test harness (``unittest``) so it runs under the trainer's embedded
Python without installing pytest. Builds a small synthetic dataset (Pillow) in a
temp dir covering the edge cases the doctor is meant to catch:

  * a clean concept folder with captions
  * an exact duplicate (byte-identical copy)
  * a near-duplicate (one tweaked pixel)
  * a missing caption and an empty caption
  * an RGBA (non-RGB) image
  * a tiny image

Run:  python -m unittest discover -s dataset-doctor/tests
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import _common as C  # noqa: E402
import scan_dataset  # noqa: E402
import check_captions  # noqa: E402
import doctor  # noqa: E402
from PIL import Image  # noqa: E402


def _patterned_image(seed: int, size: int = 768, mode: str = "RGB") -> Image.Image:
    """Deterministic, visually distinct image so dhashes differ across seeds."""
    img = Image.new(mode, (size, size))
    px = img.load()
    for y in range(size):
        for x in range(0, size, 8):  # step to keep generation fast
            r = (x * 3 + seed * 37) % 256
            g = (y * 5 + seed * 53) % 256
            b = (x + y + seed * 101) % 256
            value = (r, g, b, 255) if mode == "RGBA" else (r, g, b)
            for dx in range(8):
                if x + dx < size:
                    px[x + dx, y] = value
    return img


def _write_caption(path: Path, tags: str) -> None:
    path.write_text(tags, encoding="utf-8")


class DatasetDoctorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="dd-test-"))
        concept = cls.tmp / "5_zkz"
        concept.mkdir(parents=True)

        # 6 clean images with captions, distinct patterns.
        for i in range(6):
            img_path = concept / f"img{i:02d}.png"
            _patterned_image(i).save(img_path)
            _write_caption(img_path.with_suffix(".txt"), f"zkz, 1girl, solo, long hair, tag{i}")

        # Exact duplicate of img00 (byte-identical copy) + its caption.
        shutil.copy(concept / "img00.png", concept / "dup_exact.png")
        _write_caption(concept / "dup_exact.txt", "zkz, 1girl, solo, long hair, tag0")

        # Near-duplicate of img01: same pattern, one pixel changed.
        near = _patterned_image(1)
        near.putpixel((0, 0), (1, 2, 3))
        near.save(concept / "dup_near.png")
        _write_caption(concept / "dup_near.txt", "zkz, 1girl, solo, long hair, tag1")

        # Missing caption (image present, no sidecar).
        _patterned_image(50).save(concept / "no_caption.png")

        # Empty caption.
        _patterned_image(51).save(concept / "empty_caption.png")
        _write_caption(concept / "empty_caption.txt", "   ")

        # RGBA (non-RGB) image with caption.
        _patterned_image(52, mode="RGBA").save(concept / "rgba.png")
        _write_caption(concept / "rgba.txt", "zkz, 1girl, solo")

        # Tiny image with caption.
        _patterned_image(53, size=128).save(concept / "tiny.png")
        _write_caption(concept / "tiny.txt", "zkz, 1girl")

        # Multi-line caption: the trainer only reads line 1, so line 2 is lost.
        _patterned_image(54).save(concept / "multiline.png")
        _write_caption(
            concept / "multiline.txt", "zkz, 1girl, solo, long hair\nA girl stands by the window."
        )

        cls.concept = concept

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- _common ---------------------------------------------------------

    def test_parse_concept_folder(self):
        self.assertEqual(C.parse_concept_folder("7_zkz"), (7, "zkz"))
        self.assertEqual(C.parse_concept_folder("10 my concept"), (10, "my concept"))
        self.assertEqual(C.parse_concept_folder("zkz"), (None, None))

    def test_pct_safe_divide(self):
        self.assertEqual(C.pct(1, 0), 0.0)
        self.assertEqual(C.pct(1, 4), 25.0)

    # --- scan_dataset ----------------------------------------------------

    def test_dhash_is_deterministic_and_distinct(self):
        a1 = scan_dataset.dhash(_patterned_image(1))
        a2 = scan_dataset.dhash(_patterned_image(1))
        b = scan_dataset.dhash(_patterned_image(2))
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)

    def test_near_dup_within_hamming_threshold(self):
        base = _patterned_image(1)
        tweaked = _patterned_image(1)
        tweaked.putpixel((0, 0), (1, 2, 3))
        dist = scan_dataset.hamming(scan_dataset.dhash(base), scan_dataset.dhash(tweaked))
        self.assertLessEqual(dist, scan_dataset.NEAR_DUP_HAMMING)

    def test_scan_detects_structure(self):
        res = scan_dataset.analyze_dataset(
            self.tmp, epochs=10, batch_size=1, target_reso=(512, 512)
        )
        self.assertEqual(res["mode"], "concept")
        self.assertEqual(res["concepts"][0]["repeats"], 5)
        codes = {i["code"] for i in res["issues"]}
        self.assertIn("missing_captions", codes)
        self.assertIn("exact_duplicates", codes)
        self.assertIn("near_duplicates", codes)
        self.assertIn("non_rgb_mode", codes)
        # effective images = total images * 5 repeats
        self.assertEqual(
            res["effective_steps"]["total_effective_images"],
            res["totals"]["images"] * 5,
        )

    def test_scan_accepts_single_concept_folder(self):
        # Pointing directly at "5_zkz" (not its parent) is still concept mode.
        res = scan_dataset.analyze_dataset(self.concept, target_reso=(512, 512))
        self.assertEqual(res["mode"], "concept")
        self.assertEqual(res["concepts"][0]["repeats"], 5)
        codes = {i["code"] for i in res["issues"]}
        self.assertNotIn("no_concept_folders", codes)

    def test_scan_flags_corrupt(self):
        bad = self.tmp / "9_broken"
        bad.mkdir()
        (bad / "broken.png").write_bytes(b"not a real png")
        res = scan_dataset.analyze_dataset(bad, target_reso=(512, 512))
        codes = {i["code"] for i in res["issues"]}
        self.assertIn("corrupt_images", codes)
        shutil.rmtree(bad)

    # --- check_captions --------------------------------------------------

    def test_split_tags_normalises(self):
        self.assertEqual(
            check_captions.split_tags("ZKZ,  1girl ,, solo "),
            ["zkz", "1girl", "solo"],
        )

    def test_natural_language_suffix_is_not_counted_as_tags(self):
        with tempfile.TemporaryDirectory(prefix="dd-caption-") as temporary_dir:
            caption = Path(temporary_dir) / "sample.txt"
            caption.write_text(
                "masterpiece, safe, 1girl, zkz, solo. A person stands by the window, smiling.",
                encoding="utf-8",
            )

            info = check_captions.load_caption(caption)

            self.assertEqual(info["tags"], ["masterpiece", "safe", "1girl", "zkz", "solo"])

    def test_trigger_inference_uses_sectioned_concept_folder(self):
        with tempfile.TemporaryDirectory(prefix="dd-trigger-") as temporary_dir:
            concept = Path(temporary_dir) / "5_mych4r"
            concept.mkdir()
            for index in range(2):
                image = concept / f"img{index}.png"
                Image.new("RGB", (64, 64), "white").save(image)
                image.with_suffix(".txt").write_text(
                    "masterpiece, safe, 1girl, mych4r, solo",
                    encoding="utf-8",
                )

            result = check_captions.analyze_captions(concept)

            self.assertEqual(result["trigger"]["inferred_candidate"], "mych4r")
            self.assertEqual(result["trigger"]["inference_source"], "concept_folder")

    def test_trigger_consistency(self):
        res = check_captions.analyze_captions(self.tmp, trigger="zkz")
        self.assertTrue(res["trigger"]["consistent"])
        self.assertGreaterEqual(res["trigger"]["presence_pct"], 90.0)

    def test_valid_quality_labels_are_not_artifacts(self):
        caption = self.concept / "img_00.txt"
        caption.write_text(
            "normal quality, 1girl, zkz, solo",
            encoding="utf-8",
        )

        res = check_captions.analyze_captions(self.tmp, trigger="zkz")

        codes = {issue["code"] for issue in res["issues"]}
        self.assertNotIn("artifact_tags", codes)

    def test_trigger_inference_when_none_given(self):
        res = check_captions.analyze_captions(self.tmp)
        self.assertEqual(res["trigger"]["inferred_candidate"], "zkz")

    def test_empty_caption_flagged(self):
        res = check_captions.analyze_captions(self.tmp)
        codes = {i["code"] for i in res["issues"]}
        self.assertIn("empty_captions", codes)

    def test_multiline_caption_flagged(self):
        # kohya's read_caption keeps only line 1 (train_util.py: split("\n")[0]),
        # so everything after a newline is silently lost at training time.
        res = check_captions.analyze_captions(self.tmp)
        codes = {i["code"] for i in res["issues"]}
        self.assertIn("multiline_caption", codes)
        self.assertEqual(res["per_caption"]["multiline"], 1)

    def test_anima_json_validation(self):
        good = {"character": "zkz", "tags": ["1girl", "solo"], "nl": "a girl"}
        self.assertEqual(check_captions.validate_anima_json(good), [])
        bad_order = {"tags": ["1girl"], "character": "zkz"}
        self.assertTrue(check_captions.validate_anima_json(bad_order))
        bad_type = {"tags": "1girl"}
        self.assertTrue(check_captions.validate_anima_json(bad_type))

    # --- doctor ----------------------------------------------------------

    def test_verdict_fail_on_corrupt(self):
        scan_res = {
            "issues": [{"severity": C.SEV_CRITICAL, "code": "corrupt_images", "fix": "x"}],
            "totals": {},
            "effective_steps": {},
        }
        cap_res = {"issues": [], "totals": {}}
        v = doctor.compute_verdict(scan_res, cap_res)
        self.assertEqual(v["verdict"], doctor.VERDICT_FAIL)

    def test_verdict_warn_on_medium(self):
        scan_res = {
            "issues": [{"severity": C.SEV_MEDIUM, "code": "exact_duplicates", "fix": "dedupe"}],
            "totals": {},
            "effective_steps": {},
        }
        cap_res = {"issues": [], "totals": {}}
        v = doctor.compute_verdict(scan_res, cap_res)
        self.assertEqual(v["verdict"], doctor.VERDICT_WARN)
        self.assertEqual(v["recommendations"][0]["action"], "dedupe")

    def test_verdict_pass_when_clean(self):
        v = doctor.compute_verdict(
            {"issues": [], "totals": {}, "effective_steps": {}}, {"issues": [], "totals": {}}
        )
        self.assertEqual(v["verdict"], doctor.VERDICT_PASS)

    def test_run_doctor_emits_json_serialisable(self):
        res = doctor.run_doctor(self.tmp, trigger="zkz", epochs=10, target_reso=(512, 512))
        json.dumps(res)  # must not raise
        self.assertIn(
            res["verdict"], (doctor.VERDICT_PASS, doctor.VERDICT_WARN, doctor.VERDICT_FAIL)
        )

    def test_doctor_requires_txt_caption_by_default(self):
        with tempfile.TemporaryDirectory(prefix="dd-json-") as temporary_dir:
            root = Path(temporary_dir)
            concept = root / "1_json"
            concept.mkdir()
            image = concept / "image.png"
            _patterned_image(80, size=1024).save(image)
            image.with_suffix(".json").write_text(
                json.dumps(
                    {
                        "character": "json-trigger",
                        "tags": ["1girl", "solo", "portrait", "outdoors"],
                    }
                ),
                encoding="utf-8",
            )

            default_result = doctor.run_doctor(
                root,
                trigger="json-trigger",
                target_reso=(1024, 1024),
            )
            json_result = doctor.run_doctor(
                root,
                prefer_json=True,
                trigger="json-trigger",
                target_reso=(1024, 1024),
            )

            self.assertEqual(default_result["summary"]["missing_captions"], 1)
            self.assertEqual(default_result["verdict"], doctor.VERDICT_WARN)
            self.assertEqual(json_result["summary"]["missing_captions"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
