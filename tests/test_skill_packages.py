from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAMES = ("dataset-doctor", "lora-pipeline", "lora-trainer")


def load_yaml_mapping(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"expected a string-keyed YAML mapping: {path}")
    return value


def load_skill_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError(f"SKILL.md must start with YAML frontmatter: {path}")
    value = yaml.safe_load(parts[1])
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"expected string-keyed SKILL.md frontmatter: {path}")
    return value


class SkillPackageTests(unittest.TestCase):
    def test_skill_frontmatter(self) -> None:
        for skill_name in SKILL_NAMES:
            with self.subTest(skill=skill_name):
                metadata = load_skill_frontmatter(ROOT / skill_name / "SKILL.md")
                self.assertEqual(metadata.get("name"), skill_name)
                description = metadata.get("description")
                self.assertIsInstance(description, str)
                self.assertTrue(description.strip())

    def test_openai_agent_metadata(self) -> None:
        for skill_name in SKILL_NAMES:
            with self.subTest(skill=skill_name):
                metadata = load_yaml_mapping(ROOT / skill_name / "agents" / "openai.yaml")
                interface = metadata.get("interface")
                self.assertIsInstance(interface, dict)
                if not isinstance(interface, dict):
                    continue
                self.assertIsInstance(interface.get("display_name"), str)
                short_description = interface.get("short_description")
                self.assertIsInstance(short_description, str)
                if isinstance(short_description, str):
                    self.assertLessEqual(len(short_description), 64)
                prompt = interface.get("default_prompt")
                self.assertIsInstance(prompt, str)
                if isinstance(prompt, str):
                    self.assertIn(f"${skill_name}", prompt)


if __name__ == "__main__":
    unittest.main()
