"""Tests for fix_dataset.py — the safe (dry-run + quarantine) fixer.

Stdlib-only ``unittest`` harness so it runs under the trainer's embedded
Python. Each test builds its own tiny synthetic dataset in a temp dir, runs a
fixer command twice (dry-run, then --apply semantics via the function API) and
asserts both the *plan* and the *effect*.

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
import fix_dataset as F  # noqa: E402
from PIL import Image  # noqa: E402


def _img(seed: int, size: int = 512, mode: str = "RGB") -> Image.Image:
    """Deterministic, visually distinct image (same scheme as the doctor tests)."""
    img = Image.new(mode, (size, size))
    px = img.load()
    for y in range(size):
        for x in range(0, size, 8):
            r = (x * 3 + seed * 37) % 256
            g = (y * 5 + seed * 53) % 256
            b = (x + y + seed * 101) % 256
            value = (r, g, b, 255) if mode == "RGBA" else (r, g, b)
            for dx in range(8):
                if x + dx < size:
                    px[x + dx, y] = value
    return img


class FixDatasetTestCase(unittest.TestCase):
    """Fresh temp dir per test — fixers mutate the dataset."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dd-fix-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- organize ---------------------------------------------------------

    def test_organize_dry_run_changes_nothing(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text("zkz, 1girl", encoding="utf-8")

        result = F.cmd_organize(self.tmp, repeats=5, concept="zkz", apply=False)

        self.assertEqual(result["moved_images"], 1)
        self.assertGreater(result["action_count"], 0)
        self.assertFalse((self.tmp / "5_zkz").exists())
        self.assertTrue((self.tmp / "a.png").exists())

    def test_organize_apply_moves_images_and_sidecars(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text("zkz, 1girl", encoding="utf-8")
        (self.tmp / "a.json").write_text('{"character": "zkz"}', encoding="utf-8")

        F.cmd_organize(self.tmp, repeats=5, concept="zkz", apply=True)

        concept = self.tmp / "5_zkz"
        self.assertTrue((concept / "a.png").exists())
        self.assertTrue((concept / "a.txt").exists())
        self.assertTrue((concept / "a.json").exists())
        self.assertFalse((self.tmp / "a.png").exists())

    def test_organize_leaves_existing_concept_dirs_alone(self):
        nested = self.tmp / "3_other"
        nested.mkdir()
        _img(2).save(nested / "keep.png")
        _img(1).save(self.tmp / "loose.png")

        F.cmd_organize(self.tmp, repeats=5, concept="zkz", apply=True)

        self.assertTrue((nested / "keep.png").exists())
        self.assertTrue((self.tmp / "5_zkz" / "loose.png").exists())

    def test_organize_keeps_sidecars_paired_when_name_collides(self):
        concept = self.tmp / "5_zkz"
        concept.mkdir()
        _img(1).save(concept / "same.png")
        _img(2).save(self.tmp / "same.png")
        (self.tmp / "same.txt").write_text("zkz, second image", encoding="utf-8")

        F.cmd_organize(self.tmp, repeats=5, concept="zkz", apply=True)

        self.assertTrue((concept / "same.png").exists())
        self.assertFalse((concept / "same.txt").exists())
        self.assertTrue((concept / "same_1.png").exists())
        self.assertEqual(
            (concept / "same_1.txt").read_text(encoding="utf-8"),
            "zkz, second image",
        )

    # --- quarantine-corrupt -------------------------------------------------

    def test_quarantine_corrupt_moves_bad_files_aside(self):
        _img(1).save(self.tmp / "good.png")
        (self.tmp / "bad.png").write_bytes(b"not a real png")
        (self.tmp / "bad.txt").write_text("zkz", encoding="utf-8")

        F.cmd_quarantine_corrupt(self.tmp, apply=True)

        quarantine = self.tmp / C.QUARANTINE_DIR_NAME
        self.assertTrue((quarantine / "bad.png").exists())
        self.assertTrue((quarantine / "bad.txt").exists())
        self.assertTrue((self.tmp / "good.png").exists())
        # The doctor must no longer see the quarantined image.
        self.assertEqual([p.name for p in C.iter_images(self.tmp)], ["good.png"])

    # --- dedupe -------------------------------------------------------------

    def test_dedupe_keeps_highest_resolution_copy(self):
        _img(1, size=768).save(self.tmp / "big.png")
        _img(1, size=768).save(self.tmp / "copy.png")  # byte-identical content
        (self.tmp / "copy.txt").write_text("zkz", encoding="utf-8")
        _img(2).save(self.tmp / "unrelated.png")

        result = F.cmd_dedupe(self.tmp, near=False, apply=True)

        self.assertEqual(result["quarantined_images"], 1)
        survivors = {p.name for p in C.iter_images(self.tmp)}
        self.assertIn("unrelated.png", survivors)
        self.assertEqual(len(survivors), 2)  # one of big/copy + unrelated

    def test_dedupe_near_collapses_tweaked_copy(self):
        _img(1).save(self.tmp / "orig.png")
        tweaked = _img(1)
        tweaked.putpixel((0, 0), (1, 2, 3))
        tweaked.save(self.tmp / "tweaked.png")

        result = F.cmd_dedupe(self.tmp, near=True, apply=True)

        self.assertEqual(result["quarantined_images"], 1)
        self.assertEqual(len(C.iter_images(self.tmp)), 1)

    def test_dedupe_near_merges_overlapping_exact_group(self):
        original = self.tmp / "original.png"
        exact = self.tmp / "exact.png"
        near = self.tmp / "near.png"
        _img(1).save(original)
        shutil.copy2(original, exact)
        tweaked = _img(1)
        tweaked.putpixel((0, 0), (1, 2, 3))
        tweaked.save(near)

        result = F.cmd_dedupe(self.tmp, near=True, apply=True)

        self.assertEqual(result["duplicate_groups"], 1)
        self.assertEqual(result["quarantined_images"], 2)
        self.assertEqual(len(C.iter_images(self.tmp)), 1)

    # --- to-rgb ---------------------------------------------------------------

    def test_to_rgb_converts_and_backs_up(self):
        _img(1, mode="RGBA").save(self.tmp / "rgba.png")

        F.cmd_to_rgb(self.tmp, apply=True)

        with Image.open(self.tmp / "rgba.png") as img:
            self.assertEqual(img.mode, "RGB")
        backup = self.tmp / C.QUARANTINE_DIR_NAME / "rgba.png"
        with Image.open(backup) as img:
            self.assertEqual(img.mode, "RGBA")

    # --- add-trigger ------------------------------------------------------------

    def test_add_trigger_txt_preserves_existing_section_position(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text("1girl, solo, zkz", encoding="utf-8")
        _img(2).save(self.tmp / "b.png")
        (self.tmp / "b.txt").write_text("zkz, 1girl", encoding="utf-8")  # already first

        result = F.cmd_add_trigger(self.tmp, trigger="zkz", apply=True)

        self.assertEqual(result["rewritten_captions"], 0)
        self.assertEqual((self.tmp / "a.txt").read_text(encoding="utf-8"), "1girl, solo, zkz")
        self.assertEqual((self.tmp / "b.txt").read_text(encoding="utf-8"), "zkz, 1girl")

    def test_add_trigger_txt_inserts_after_metadata_and_preserves_prose(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text(
            "best quality, safe, 1girl, solo, outdoors. A person stands near a lake.",
            encoding="utf-8",
        )

        result = F.cmd_add_trigger(self.tmp, trigger="zkz", apply=True)

        self.assertEqual(result["rewritten_captions"], 1)
        self.assertEqual(
            (self.tmp / "a.txt").read_text(encoding="utf-8"),
            "best quality, safe, 1girl, zkz, solo, outdoors. A person stands near a lake.",
        )

    def test_add_trigger_json_sets_character_in_order(self):
        _img(1).save(self.tmp / "a.png")
        caption = {"tags": ["1girl"], "quality": "best quality"}
        (self.tmp / "a.json").write_text(json.dumps(caption), encoding="utf-8")

        F.cmd_add_trigger(self.tmp, trigger="zkz", apply=True)

        obj = json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(obj["character"], "zkz")
        self.assertEqual(list(obj), ["quality", "character", "tags"])  # recommended order

    def test_add_trigger_counts_missing_captions(self):
        _img(1).save(self.tmp / "untagged.png")
        result = F.cmd_add_trigger(self.tmp, trigger="zkz", apply=False)
        self.assertEqual(result["missing_captions"], 1)
        self.assertIn("WD14", result["hint_for_missing"])

    # --- strip-tags ---------------------------------------------------------------

    def test_strip_tags_removes_artifacts_and_duplicates(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text(
            "zkz, watermark, 1girl, zkz, worst quality", encoding="utf-8"
        )

        result = F.cmd_strip_tags(self.tmp, extra_tags="", apply=True)

        self.assertEqual(result["rewritten_captions"], 1)
        self.assertEqual(
            (self.tmp / "a.txt").read_text(encoding="utf-8"),
            "zkz, 1girl, worst quality",
        )

    def test_strip_tags_preserves_natural_language_suffix(self):
        _img(1).save(self.tmp / "a.png")
        (self.tmp / "a.txt").write_text(
            "safe, 1girl, zkz, watermark, outdoors. A girl stands by a lake, smiling.",
            encoding="utf-8",
        )

        F.cmd_strip_tags(self.tmp, extra_tags="", apply=True)

        self.assertEqual(
            (self.tmp / "a.txt").read_text(encoding="utf-8"),
            "safe, 1girl, zkz, outdoors. A girl stands by a lake, smiling.",
        )

    def test_strip_tags_extra_and_json_lists(self):
        _img(1).save(self.tmp / "a.png")
        caption = {"character": "zkz", "tags": ["1girl", "watermark", "school uniform"]}
        (self.tmp / "a.json").write_text(json.dumps(caption), encoding="utf-8")

        F.cmd_strip_tags(self.tmp, extra_tags="school uniform", apply=True)

        obj = json.loads((self.tmp / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(obj["tags"], ["1girl"])
        self.assertEqual(obj["character"], "zkz")  # string fields untouched

    # --- safety net -----------------------------------------------------------------

    def test_unique_dest_avoids_collisions(self):
        target = self.tmp / "x"
        target.mkdir()
        (target / "a.png").write_bytes(b"1")
        dest = F.unique_dest(target, "a.png")
        self.assertEqual(dest.name, "a_1.png")

    def test_iter_images_skips_quarantine(self):
        quarantine = self.tmp / C.QUARANTINE_DIR_NAME
        quarantine.mkdir()
        _img(1).save(quarantine / "hidden.png")
        _img(2).save(self.tmp / "visible.png")
        self.assertEqual([p.name for p in C.iter_images(self.tmp)], ["visible.png"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
