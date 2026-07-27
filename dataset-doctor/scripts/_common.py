"""Shared helpers for the dataset-doctor scripts.

Pure, dependency-light utilities used by scan_dataset.py, check_captions.py and
doctor.py. Only the standard library is imported here; Pillow/numpy are imported
lazily by the callers that actually need image decoding.

The trainer this skill targets (lora-scripts-next / SD-Trainer) follows the
kohya/sd-scripts dataset convention:

    train_data_dir/
        <repeats>_<concept>/      e.g. "7_zkz"  -> 7 repeats, concept "zkz"
            img001.png
            img001.txt            sidecar caption (.txt is the training source of truth)
            ...

These helpers know how to walk that layout and pair every image with its
caption file, regardless of whether the caller points at the parent
``train_data_dir`` or directly at a single ``<repeats>_<concept>`` folder.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

# --- Constants ---------------------------------------------------------------

# Extensions sd-scripts will actually load as training images. AVIF/HEIC are
# intentionally excluded: Pillow cannot open them without extra plugins, so
# flagging them as "corrupt" would be misleading.
IMAGE_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".tif", ".tiff"}
)
CAPTION_TXT_EXT = ".txt"
CAPTION_JSON_EXT = ".json"

# Where fix_dataset.py moves files instead of deleting them. The name never
# matches CONCEPT_PATTERN, and iter_images() skips it, so quarantined files
# are invisible to both the trainer and the doctor.
QUARANTINE_DIR_NAME = "_quarantine"

CONCEPT_PATTERN = re.compile(r"^(\d+)[_ ](.+)$")

# Severity levels, ordered. Mirrors the user's CRITICAL/HIGH/MEDIUM/LOW ladder
# but scoped to dataset readiness.
SEV_CRITICAL = "critical"
SEV_HIGH = "high"
SEV_MEDIUM = "medium"
SEV_LOW = "low"
SEV_INFO = "info"

_SEVERITY_ORDER = {
    SEV_CRITICAL: 0,
    SEV_HIGH: 1,
    SEV_MEDIUM: 2,
    SEV_LOW: 3,
    SEV_INFO: 4,
}
_SEVERITY_EMOJI = {
    SEV_CRITICAL: "⛔",  # no entry
    SEV_HIGH: "\U0001f534",  # red circle
    SEV_MEDIUM: "\U0001f7e1",  # yellow circle
    SEV_LOW: "\U0001f535",  # blue circle
    SEV_INFO: "ℹ️",  # info
}


# --- Issue model -------------------------------------------------------------


@dataclass
class Issue:
    """A single finding. ``code`` is a stable machine key; ``message`` is human
    text; ``fix`` is the recommended remediation; ``items`` carries example
    offenders (capped by the caller)."""

    severity: str
    code: str
    message: str
    fix: str = ""
    items: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "fix": self.fix,
            "items": self.items,
        }


def sort_issues(issues: Iterable[Issue]) -> list[Issue]:
    """Most severe first; stable within a severity."""
    return sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 99))


def severity_emoji(severity: str) -> str:
    return _SEVERITY_EMOJI.get(severity, "•")


def worst_severity(issues: Iterable[Issue]) -> Optional[str]:
    sevs = [i.severity for i in issues]
    if not sevs:
        return None
    return min(sevs, key=lambda s: _SEVERITY_ORDER.get(s, 99))


# --- Filesystem / dataset layout --------------------------------------------


def parse_concept_folder(name: str) -> tuple[Optional[int], Optional[str]]:
    """Parse a ``<repeats>_<concept>`` folder name.

    Returns ``(repeats, concept)`` or ``(None, None)`` when the name does not
    follow the kohya repeat convention.
    """
    match = CONCEPT_PATTERN.match(name.strip())
    if not match:
        return None, None
    return int(match.group(1)), match.group(2)


@dataclass
class ConceptDir:
    path: Path
    repeats: int
    concept: str


def discover_concept_dirs(root: Path) -> list[ConceptDir]:
    """Find ``<repeats>_<concept>`` subfolders directly under ``root``."""
    concepts: list[ConceptDir] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        repeats, concept = parse_concept_folder(child.name)
        if repeats is not None and concept is not None:
            concepts.append(ConceptDir(path=child, repeats=repeats, concept=concept))
    return concepts


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def iter_images(root: Path, recursive: bool = True) -> list[Path]:
    """All image files under ``root`` (sorted, deterministic). Files inside a
    ``_quarantine`` folder are excluded — they were set aside by fix_dataset.py
    and must not count as training data."""
    walker = root.rglob("*") if recursive else root.glob("*")
    return sorted(
        p for p in walker if p.is_file() and is_image(p) and QUARANTINE_DIR_NAME not in p.parts
    )


def find_caption_path(image_path: Path, prefer_json: bool) -> Optional[Path]:
    """Locate the sidecar caption for an image.

    With ``prefer_json`` the same-stem ``.json`` wins when present, else the
    ``.txt`` is used. Without it, only the trainer-supported ``.txt`` counts.
    """
    json_path = image_path.with_suffix(CAPTION_JSON_EXT)
    txt_path = image_path.with_suffix(CAPTION_TXT_EXT)
    if prefer_json and json_path.is_file():
        return json_path
    if txt_path.is_file():
        return txt_path
    return None


def read_text(path: Path) -> str:
    """Read a text/caption file as UTF-8, tolerating stray bytes."""
    return path.read_text(encoding="utf-8", errors="replace")


def md5_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --- Output helpers ----------------------------------------------------------


def dump_json(data: dict, output: Optional[Path] = None) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if output is not None:
        output.write_text(text, encoding="utf-8")
    return text


def pct(part: int, whole: int) -> float:
    """Percentage with safe divide-by-zero (returns 0.0)."""
    if whole <= 0:
        return 0.0
    return round(100.0 * part / whole, 1)
