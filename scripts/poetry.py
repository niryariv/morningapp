"""Select one locally bundled public-domain poem or excerpt per edition."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

try:
    from .utils import DATA_DIR, normalize_url, read_json
except ImportError:  # Support direct execution via ``python scripts/update.py``.
    from utils import DATA_DIR, normalize_url, read_json


POETRY_PATH = DATA_DIR / "poetry.json"
REQUIRED_FIELDS = {
    "id", "author", "work", "locator", "excerpt", "translator", "language",
    "source_name", "source_url", "source_edition", "rights",
}


def load_poetry(path: Path = POETRY_PATH) -> list[dict[str, Any]]:
    """Load and defensively validate the curated bilingual poetry shelf."""
    entries = read_json(path)
    if not isinstance(entries, list) or not entries:
        raise ValueError("poetry dataset is missing or empty")

    validated: list[dict[str, Any]] = []
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not REQUIRED_FIELDS.issubset(entry):
            raise ValueError("poetry dataset contains an incomplete entry")
        text_fields = REQUIRED_FIELDS - {"translator"}
        if not all(isinstance(entry[field], str) and entry[field].strip() for field in text_fields):
            raise ValueError("poetry dataset contains invalid text fields")
        if entry["translator"] is not None and not isinstance(entry["translator"], str):
            raise ValueError("poetry translator must be text or null")
        if "is_complete" in entry and not isinstance(entry["is_complete"], bool):
            raise ValueError("poetry is_complete must be boolean")
        if entry["language"] not in {"en", "he"}:
            raise ValueError(f"unsupported poetry language: {entry['id']}")
        if entry["id"] in ids:
            raise ValueError(f"duplicate poetry id: {entry['id']}")
        if not normalize_url(entry["source_url"]):
            raise ValueError(f"unsafe poetry source URL: {entry['id']}")
        if len(entry["excerpt"]) > 360:
            raise ValueError(f"poetry excerpt is too long: {entry['id']}")
        if "\n" not in entry["excerpt"]:
            raise ValueError(f"poetry excerpt must preserve line breaks: {entry['id']}")
        ids.add(entry["id"])
        validated.append({**entry, "is_complete": entry.get("is_complete", False)})
    return validated


def collect_poem(edition_date: str, seen_ids: set[str]) -> dict[str, Any]:
    """Return a deterministic, language-balanced poem absent from recent history."""
    edition_day = date.fromisoformat(edition_date)
    entries = load_poetry()
    target_language = "he" if edition_day.toordinal() % 2 else "en"
    language_entries = [entry for entry in entries if entry["language"] == target_language]
    if not language_entries:
        raise ValueError(f"poetry shelf has no {target_language} entries")

    start = (edition_day.toordinal() // 2) % len(language_entries)
    entry = next(
        (language_entries[(start + offset) % len(language_entries)]
         for offset in range(len(language_entries))
         if language_entries[(start + offset) % len(language_entries)]["id"] not in seen_ids),
        None,
    )
    if entry is None:
        raise ValueError(f"all {target_language} poetry excerpts occur in recent history")

    title = f"{entry['author']} — {entry['work']}"
    attribution = f"{entry['locator']} · {entry['source_name']}"
    if entry["translator"]:
        attribution = f"{entry['locator']} · trans. {entry['translator']} · {entry['source_name']}"

    return {
        "id": entry["id"],
        "category": "poetry",
        "label": "Poem",
        "title": title,
        "summary": entry["excerpt"],
        "url": entry["source_url"],
        "source": attribution,
        "image": None,
        "image_alt": None,
        "published": None,
        "reading_minutes": 1,
        "language": entry["language"],
        "score": 99,
        "score_parts": {"curated_public_domain": 99},
        "is_long_read": False,
        "is_poetry": True,
    }
