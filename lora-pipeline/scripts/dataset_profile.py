"""Shared dataset-target rules for curation and post-tag semantic review."""

from __future__ import annotations

from pathlib import Path

SUBJECT_TAGS: tuple[str, ...] = ("1girl", "1boy", "1other")

MULTI_SUBJECT: frozenset[str] = frozenset(
    {
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "multiple girls",
        "2boys",
        "3boys",
        "4boys",
        "5boys",
        "6+boys",
        "multiple boys",
        "2others",
        "3others",
        "multiple others",
        "multiple views",
        "comic",
        "4koma",
        "reference sheet",
        "character sheet",
    }
)

COMIC_SHEET: frozenset[str] = frozenset(
    {"comic", "4koma", "multiple views", "reference sheet", "character sheet"}
)

COMMON_OFFMODEL_KEYWORDS: tuple[str, ...] = ("genderswap", "futanari", "cosplay")

SUBJECT_MISMATCH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "1girl": ("1boy", "1other", "2boys", "2others", "multiple boys", "male focus"),
    "1boy": ("1girl", "1other", "2girls", "2others", "multiple girls", "female focus"),
    "1other": ("1girl", "1boy", "2girls", "2boys", "multiple girls", "multiple boys"),
}


def parse_tags_text(text: str) -> set[str]:
    tag_section = text.partition(". ")[0]
    return {tag.strip().lower() for tag in tag_section.split(",") if tag.strip()}


def parse_tags_file(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return parse_tags_text(path.read_text(encoding="utf-8", errors="replace"))


def match_keywords(tags: set[str], keywords: tuple[str, ...]) -> list[str]:
    return sorted({keyword for keyword in keywords if any(keyword in tag for tag in tags)})


def offmodel_keywords(subject_tag: str) -> tuple[str, ...]:
    if subject_tag not in SUBJECT_MISMATCH_KEYWORDS:
        expected = ", ".join(SUBJECT_TAGS)
        raise ValueError(f"subject_tag must be one of {expected}: {subject_tag!r}")
    return COMMON_OFFMODEL_KEYWORDS + SUBJECT_MISMATCH_KEYWORDS[subject_tag]
