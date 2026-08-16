"""Shared helpers for fetching, cleaning, scoring, and serializing content."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from config import REQUEST_TIMEOUT, USER_AGENT


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DOCS_DATA_DIR = ROOT / "docs" / "data"


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml, text/xml, */*",
    })
    return session


def fetch(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    response = session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
    response.raise_for_status()
    return response


def clean_text(value: str | None, limit: int = 430) -> str:
    if not value:
        return ""
    soup = BeautifulSoup(value, "html.parser")
    for element in soup(("script", "style", "figure", "figcaption")):
        element.decompose()
    text = html.unescape(soup.get_text(" ", strip=True))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:–—-")
    return f"{shortened}…"


def first_image_from_html(value: str | None) -> str | None:
    if not value:
        return None
    image = BeautifulSoup(value, "html.parser").find("img")
    if not image:
        return None
    src = image.get("src") or image.get("data-src")
    return str(src).strip() if src else None


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url.strip())
        excluded = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid"}
        query = urlencode([(key, value) for key, value in parse_qsl(parts.query) if key.lower() not in excluded])
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))
    except ValueError:
        return url.strip()


def stable_id(prefix: str, url: str) -> str:
    digest = hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def iso_date_from_struct(value: Any) -> str | None:
    if not value:
        return None
    try:
        return date(value.tm_year, value.tm_mon, value.tm_mday).isoformat()
    except (AttributeError, TypeError, ValueError):
        return None


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def as_public_item(candidate: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id", "category", "label", "title", "summary", "url", "source", "image",
        "image_alt", "published", "reading_minutes", "language",
    )
    return {field: candidate.get(field) for field in fields}

