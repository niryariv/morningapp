"""Date-seeded discovery from Hebrew Wikipedia's featured articles."""

from __future__ import annotations

import hashlib
from typing import Any

from config import LOW_VALUE_WIKIPEDIA_TERMS, NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS
from utils import clean_text, fetch, stable_id


WIKIPEDIA_API = "https://he.wikipedia.org/w/api.php"
FEATURED_CATEGORY = "קטגוריה:ערכים מומלצים"


def collect_wikipedia(session: Any, seen_titles: set[str], edition_date: str) -> dict[str, Any]:
    category_params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": FEATURED_CATEGORY,
        "cmnamespace": 0,
        "cmtype": "page",
        "cmlimit": "max",
        "format": "json",
        "formatversion": 2,
        "origin": "*",
    }
    category_payload = fetch(session, WIKIPEDIA_API, params=category_params).json()
    members = category_payload.get("query", {}).get("categorymembers", [])
    eligible = [member for member in members if member.get("title") not in seen_titles]
    eligible.sort(
        key=lambda member: hashlib.sha256(f"{edition_date}:{member.get('title', '')}".encode("utf-8")).hexdigest()
    )
    page_ids = [str(member["pageid"]) for member in eligible[:24] if member.get("pageid")]
    if not page_ids:
        raise ValueError("featured article category returned no unused pages")

    detail_params = {
        "action": "query",
        "pageids": "|".join(page_ids),
        "prop": "extracts|pageimages|info",
        "exintro": 1,
        "explaintext": 1,
        "exsentences": 4,
        "piprop": "thumbnail",
        "pithumbsize": 1000,
        "inprop": "url",
        "format": "json",
        "formatversion": 2,
        "origin": "*",
    }
    payload = fetch(session, WIKIPEDIA_API, params=detail_params).json()
    pages = payload.get("query", {}).get("pages", [])

    candidates: list[dict[str, Any]] = []
    for page in pages:
        title = clean_text(page.get("title"), 180)
        summary = clean_text(page.get("extract"), 480)
        url = page.get("fullurl")
        combined = f"{title} {summary}".lower()
        if not title or not url or len(summary) < 180 or title in seen_titles:
            continue
        if any(term in combined for term in LOW_VALUE_WIKIPEDIA_TERMS):
            continue
        penalty = sum(value for term, value in NEGATIVE_KEYWORDS.items() if term in combined)
        if penalty >= 7:
            continue
        image = page.get("thumbnail", {}).get("source")
        curiosity_bonus = min(4, sum(term in combined for term in POSITIVE_KEYWORDS))
        candidates.append({
            "id": stable_id("wikipedia", url),
            "category": "discovery",
            "label": "Wikipedia discovery",
            "title": title,
            "summary": summary,
            "url": url,
            "source": "ויקיפדיה",
            "image": image,
            "image_alt": title if image else None,
            "published": None,
            "reading_minutes": None,
            "language": "he",
            "score": 27 + (2 if image else 0) + curiosity_bonus - penalty,
            "score_parts": {"interest_score": 4, "timelessness_score": 5, "visual_score": 3 if image else 1, "positivity_score": 3, "negative_penalty": penalty},
            "is_long_read": False,
            "wikipedia": True,
        })
    if not candidates:
        raise ValueError("no suitable random article found")
    return max(candidates, key=lambda item: item["score"])
