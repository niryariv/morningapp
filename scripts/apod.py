"""NASA Astronomy Picture of the Day collector."""

from __future__ import annotations

import os
from typing import Any

from utils import clean_text, fetch


APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"


def collect_apod(session: Any, edition_date: str) -> dict[str, Any]:
    response = fetch(
        session,
        APOD_ENDPOINT,
        params={"api_key": os.environ.get("NASA_API_KEY", "DEMO_KEY"), "date": edition_date},
    )
    payload = response.json()
    title = clean_text(payload.get("title"), 180)
    summary = clean_text(payload.get("explanation"), 500)
    source_url = f"https://apod.nasa.gov/apod/ap{edition_date[2:].replace('-', '')}.html"
    media_type = payload.get("media_type")
    image = payload.get("url") if media_type == "image" else payload.get("thumbnail_url")
    if not title or not summary:
        raise ValueError("APOD response lacks a title or explanation")
    return {
        "id": f"apod-{edition_date}",
        "category": "astronomy",
        "label": "Image of the day" if image else "Astronomy",
        "title": title,
        "summary": summary,
        "url": source_url,
        "source": "NASA APOD",
        "image": image,
        "image_alt": title if image else None,
        "published": payload.get("date", edition_date),
        "reading_minutes": None,
        "language": "en",
        "score": 40,
        "score_parts": {"interest_score": 5, "timelessness_score": 4, "visual_score": 5, "positivity_score": 4, "negative_penalty": 0},
        "is_long_read": False,
        "featured": True,
    }

