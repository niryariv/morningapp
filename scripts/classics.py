"""Select one locally bundled public-domain classics excerpt per edition."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

try:
    from .utils import DATA_DIR, normalize_url, read_json
except ImportError:  # Support direct execution via ``python scripts/update.py``.
    from utils import DATA_DIR, normalize_url, read_json


CLASSICS_PATH = DATA_DIR / "classics.json"
REQUIRED_FIELDS = {
    "id", "author", "work", "locator", "excerpt", "translator", "tradition",
    "era", "source_url", "rights",
}


def load_classics(path: Path = CLASSICS_PATH) -> list[dict[str, Any]]:
    """Load and defensively validate the curated local shelf."""
    entries = read_json(path)
    if not isinstance(entries, list) or not entries:
        raise ValueError("classics dataset is missing or empty")

    validated: list[dict[str, Any]] = []
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not REQUIRED_FIELDS.issubset(entry):
            raise ValueError("classics dataset contains an incomplete entry")
        if not all(isinstance(entry[field], str) and entry[field].strip() for field in REQUIRED_FIELDS - {"translator"}):
            raise ValueError("classics dataset contains invalid text fields")
        if entry["translator"] is not None and not isinstance(entry["translator"], str):
            raise ValueError("classics translator must be text or null")
        if entry["id"] in ids:
            raise ValueError(f"duplicate classics id: {entry['id']}")
        if not normalize_url(entry["source_url"]):
            raise ValueError(f"unsafe classics source URL: {entry['id']}")
        if len(entry["excerpt"]) > 280:
            raise ValueError(f"classics excerpt is too long: {entry['id']}")
        ids.add(entry["id"])
        validated.append(entry)
    return validated


def collect_classic(edition_date: str, seen_ids: set[str]) -> dict[str, Any]:
    """Return the date-rotated first excerpt not used in the prior history window."""
    edition_day = date.fromisoformat(edition_date)
    entries = load_classics()
    start = edition_day.toordinal() % len(entries)
    entry = next(
        (entries[(start + offset) % len(entries)] for offset in range(len(entries))
         if entries[(start + offset) % len(entries)]["id"] not in seen_ids),
        None,
    )
    if entry is None:
        raise ValueError("all classics excerpts occur in recent history")

    title = entry["work"] if entry["author"] == entry["work"] else f"{entry['author']} — {entry['work']}"
    attribution = entry["locator"]
    if entry["translator"]:
        attribution += f" · trans. {entry['translator']}"
    else:
        attribution += " · original English"

    return {
        "id": entry["id"],
        "category": "classics",
        "label": "From the classics",
        "title": title,
        "summary": entry["excerpt"],
        "url": entry["source_url"],
        "source": attribution,
        "image": None,
        "image_alt": None,
        "published": None,
        "reading_minutes": 1,
        "language": "en",
        "score": 100,
        "score_parts": {"curated_public_domain": 100},
        "is_long_read": False,
        "is_classic": True,
    }
