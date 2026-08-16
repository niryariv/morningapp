"""RSS and Atom collection using only publisher-provided metadata."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import feedparser

try:
    from .config import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS, SOURCES, VISUAL_KEYWORDS
    from .utils import (
        clean_text,
        fetch,
        first_image_from_html,
        iso_date_from_struct,
        keyword_matches,
        normalize_url,
        public_media_url,
        stable_id,
    )
except ImportError:  # Support direct execution via ``python scripts/update.py``.
    from config import NEGATIVE_KEYWORDS, POSITIVE_KEYWORDS, SOURCES, VISUAL_KEYWORDS
    from utils import (
        clean_text,
        fetch,
        first_image_from_html,
        iso_date_from_struct,
        keyword_matches,
        normalize_url,
        public_media_url,
        stable_id,
    )


def _entry_image(entry: Any, base_url: str) -> str | None:
    for field in ("media_content", "media_thumbnail"):
        for media in entry.get(field, []):
            value = media.get("url")
            if value:
                safe_url = public_media_url(urljoin(base_url, value))
                if safe_url:
                    return safe_url

    for enclosure in entry.get("enclosures", []):
        value = enclosure.get("href") or enclosure.get("url")
        media_type = enclosure.get("type", "")
        if value and (media_type.startswith("image/") or not media_type):
            safe_url = public_media_url(urljoin(base_url, value))
            if safe_url:
                return safe_url

    for field in ("summary", "description", "content"):
        value = entry.get(field)
        if isinstance(value, list):
            value = " ".join(part.get("value", "") for part in value)
        image = first_image_from_html(value)
        if image:
            safe_url = public_media_url(urljoin(base_url, image))
            if safe_url:
                return safe_url
    return None


def _category(source: dict[str, Any], title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if any(keyword_matches(text, word) for word in ("math", "mathematics", "mathematical", "geometry", "number theory", "algorithm", "מתמטיקה")):
        return "mathematics"
    if any(keyword_matches(text, word) for word in ("archaeology", "archaeological", "ancient", "museum", "artifact", "מאובן", "ארכאולוגיה", "ארכאולוגי")):
        return "history"
    if any(keyword_matches(text, word) for word in ("ocean", "forest", "animal", "ecology", "earth", "climate", "טבע", "סביבה")):
        return "nature"
    return source["category"]


def _score(source: dict[str, Any], title: str, summary: str, image: str | None) -> tuple[int, dict[str, int]]:
    text = f"{title} {summary}".lower()
    interest = min(5, 2 + source["weight"] // 2 + sum(keyword_matches(text, term) for term in POSITIVE_KEYWORDS))
    timelessness = 4 if source["category"] in {"history", "ideas", "nature"} else 3
    visual = 1 + (2 if image else 0) + min(2, sum(keyword_matches(text, term) for term in VISUAL_KEYWORDS))
    positivity = 3 + min(2, sum(keyword_matches(text, term) for term in POSITIVE_KEYWORDS))
    penalty = sum(value for term, value in NEGATIVE_KEYWORDS.items() if keyword_matches(text, term))
    score = interest * 3 + timelessness * 2 + visual + positivity + source["weight"] - penalty
    return score, {
        "interest_score": interest,
        "timelessness_score": timelessness,
        "visual_score": visual,
        "positivity_score": positivity,
        "negative_penalty": penalty,
    }


def collect_feed(session: Any, source: dict[str, Any]) -> list[dict[str, Any]]:
    response = fetch(session, source["feed"])
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"invalid feed: {parsed.bozo_exception}")

    candidates: list[dict[str, Any]] = []
    for entry in parsed.entries[:16]:
        try:
            title = clean_text(entry.get("title"), 180)
            raw_url = entry.get("link", "")
            url = normalize_url(urljoin(source["feed"], raw_url)) if isinstance(raw_url, str) else ""
            raw_summary = entry.get("summary") or entry.get("description") or ""
            summary = clean_text(raw_summary)
            summary = re.sub(
                r"\s+The post\b.*?\bappeared first on\b.*$",
                "",
                summary,
                flags=re.IGNORECASE,
            ).strip()
            summary = re.sub(
                r"\s+[-–—]\s+by\s+.+?\s+Read on Aeon\s*$",
                "",
                summary,
                flags=re.IGNORECASE,
            ).strip()
            if not title or not url or len(summary) < 55:
                continue
            image = _entry_image(entry, url)
            score, score_parts = _score(source, title, summary, image)
            category = _category(source, title, summary)
            long_read_path = source.get("long_read_path")
            is_long_read = bool(source.get("long_read")) and (not long_read_path or long_read_path in url)
            label = "Long read" if is_long_read else category.replace("_", " ").title()
            candidate = {
                "id": stable_id("feed", url),
                "category": category,
                "label": label,
                "title": title,
                "summary": summary,
                "url": url,
                "source": source["name"],
                "image": image,
                "image_alt": title if image else None,
                "published": iso_date_from_struct(entry.get("published_parsed") or entry.get("updated_parsed")),
                "reading_minutes": None,
                "language": source["language"],
                "score": score,
                "score_parts": score_parts,
                "is_long_read": is_long_read,
            }
            candidates.append(candidate)
        except (AttributeError, TypeError, ValueError):
            # One malformed publisher entry must not discard the rest of its feed.
            continue
    return candidates


def collect_all_feeds(session: Any, log: Any = print) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    successes = 0
    for source in SOURCES:
        try:
            found = collect_feed(session, source)
            candidates.extend(found)
            successes += 1
            log(f"{source['name']}: {len(found)} candidates")
        except Exception as exc:  # A single publisher must never stop the edition.
            log(f"{source['name']}: ERROR — {exc}")
    return candidates, successes
