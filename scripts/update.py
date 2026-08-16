#!/usr/bin/env python3
"""Generate a finite, balanced Morning edition from public sources."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from apod import collect_apod
    from classics import collect_classic
    from poetry import collect_poem
    from config import HISTORY_DAYS, MAX_ITEMS, MIN_QUALITY_SCORE
    from feeds import collect_all_feeds
    from utils import DATA_DIR, DOCS_DATA_DIR, as_public_item, get_session, normalize_url, read_json, utc_now, write_json
    from wikipedia import collect_wikipedia
else:
    from .apod import collect_apod
    from .classics import collect_classic
    from .poetry import collect_poem
    from .config import HISTORY_DAYS, MAX_ITEMS, MIN_QUALITY_SCORE
    from .feeds import collect_all_feeds
    from .utils import DATA_DIR, DOCS_DATA_DIR, as_public_item, get_session, normalize_url, read_json, utc_now, write_json
    from .wikipedia import collect_wikipedia


ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def log(message: str = "") -> None:
    print(message, flush=True)


def load_recent_history(edition_day: datetime) -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    wikipedia_titles: set[str] = set()
    for offset in range(1, HISTORY_DAYS + 1):
        path = DATA_DIR / "history" / f"{(edition_day - timedelta(days=offset)).date().isoformat()}.json"
        edition = read_json(path, {})
        if not isinstance(edition, dict) or not isinstance(edition.get("items"), list):
            continue
        for item in edition["items"]:
            if not isinstance(item, dict):
                continue
            if item.get("url"):
                normalized_url = normalize_url(item["url"])
                if normalized_url:
                    urls.add(normalized_url)
            if item.get("source") in {"Wikipedia", "ויקיפדיה"} and item.get("title"):
                wikipedia_titles.add(item["title"])
    return urls, wikipedia_titles


def load_recent_classic_ids(edition_day: datetime) -> set[str]:
    """Return excerpt IDs published during the same 30-day history window."""
    ids: set[str] = set()
    for offset in range(1, HISTORY_DAYS + 1):
        path = DATA_DIR / "history" / f"{(edition_day - timedelta(days=offset)).date().isoformat()}.json"
        edition = read_json(path, {})
        if not isinstance(edition, dict) or not isinstance(edition.get("items"), list):
            continue
        for item in edition["items"]:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.startswith("classic-"):
                ids.add(item_id)
    return ids


def load_recent_poetry_ids(edition_day: datetime) -> set[str]:
    """Return poetry excerpt IDs published during the 30-day history window."""
    ids: set[str] = set()
    for offset in range(1, HISTORY_DAYS + 1):
        path = DATA_DIR / "history" / f"{(edition_day - timedelta(days=offset)).date().isoformat()}.json"
        edition = read_json(path, {})
        if not isinstance(edition, dict) or not isinstance(edition.get("items"), list):
            continue
        for item in edition["items"]:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if isinstance(item_id, str) and item_id.startswith("poetry-"):
                ids.add(item_id)
    return ids


def select_items(candidates: list[dict[str, Any]], seen_urls: set[str]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = normalize_url(item.get("url", ""))
        is_classic = bool(item.get("is_classic"))
        is_poetry = bool(item.get("is_poetry"))
        is_curated = is_classic or is_poetry
        if not url or (url in seen_urls and not is_curated) or item.get("score", 0) < MIN_QUALITY_SCORE:
            continue
        # Several curated excerpts may cite the same source edition. Their
        # excerpt IDs, rather than the shared book URL, define novelty.
        dedup_key = f"curated:{item.get('id', '')}" if is_curated else url
        previous = unique.get(dedup_key)
        if not previous or item.get("score", 0) > previous.get("score", 0):
            unique[dedup_key] = item

    pool = sorted(unique.values(), key=lambda item: (item.get("score", 0), bool(item.get("image"))), reverse=True)
    selected: list[dict[str, Any]] = []
    categories: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    long_read_used = False
    classic_used = False
    poetry_used = False

    def add(item: dict[str, Any]) -> bool:
        nonlocal classic_used, poetry_used, long_read_used
        if item in selected or len(selected) >= MAX_ITEMS:
            return False
        if item.get("is_long_read") and long_read_used:
            return False
        if item.get("is_classic") and classic_used:
            return False
        if item.get("is_poetry") and poetry_used:
            return False
        selected.append(item)
        categories[item["category"]] += 1
        sources[item["source"]] += 1
        long_read_used = long_read_used or bool(item.get("is_long_read"))
        classic_used = classic_used or bool(item.get("is_classic"))
        poetry_used = poetry_used or bool(item.get("is_poetry"))
        return True

    # These form the edition's reliable visual, bilingual, and reflective anchors.
    for predicate in (
        lambda item: item.get("featured"),
        lambda item: item.get("wikipedia"),
        lambda item: item.get("is_classic"),
        lambda item: item.get("is_poetry"),
    ):
        match = next((item for item in pool if predicate(item)), None)
        if match:
            add(match)

    # Reserve a place for nature/geography and for one thoughtful long read when available.
    nature = next((item for item in pool if item["category"] == "nature" and item not in selected), None)
    if nature:
        add(nature)
    long_read = next((item for item in pool if item.get("is_long_read") and item not in selected), None)
    if long_read:
        add(long_read)

    # Prefer category and publisher variety over tiny differences in score.
    for item in pool:
        if len(selected) >= MAX_ITEMS:
            break
        if categories[item["category"]] >= 2 or sources[item["source"]] >= 2:
            continue
        add(item)
    for item in pool:
        if len(selected) >= MAX_ITEMS:
            break
        add(item)

    # The image of the day leads; remaining items retain their balanced selection order.
    selected.sort(key=lambda item: not item.get("featured", False))
    return selected


def archive_and_publish(edition: dict[str, Any]) -> None:
    current_path = DATA_DIR / "today.json"
    previous = read_json(current_path)
    if isinstance(previous, dict) and previous.get("date"):
        previous_date = previous["date"]
        try:
            parsed_previous_date = datetime.strptime(previous_date, "%Y-%m-%d").date().isoformat()
        except (TypeError, ValueError):
            parsed_previous_date = None
        if parsed_previous_date == previous_date:
            write_json(DATA_DIR / "history" / f"{previous_date}.json", previous)

    write_json(current_path, edition)
    write_json(DATA_DIR / "history" / f"{edition['date']}.json", edition)
    sync_public_data()


def sync_public_data() -> None:
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = read_json(DATA_DIR / "today.json")
    if today:
        write_json(DOCS_DATA_DIR / "today.json", today)

    history_source = DATA_DIR / "history"
    history_target = DOCS_DATA_DIR / "history"
    history_target.mkdir(parents=True, exist_ok=True)
    dates: list[str] = []
    if history_source.exists():
        for source in sorted(history_source.glob("????-??-??.json"), reverse=True):
            shutil.copyfile(source, history_target / source.name)
            dates.append(source.stem)
    write_json(DOCS_DATA_DIR / "archive.json", {"dates": dates})


def build_edition(edition_date: str | None = None) -> int:
    now_local = datetime.now(ISRAEL_TZ)
    if edition_date:
        try:
            edition_day = datetime.strptime(edition_date, "%Y-%m-%d").replace(tzinfo=ISRAEL_TZ)
        except ValueError as exc:
            raise SystemExit(f"Invalid --date value: {exc}") from exc
    else:
        edition_day = now_local
    day = edition_day.date().isoformat()

    log(f"Morning update — {day}\n")
    seen_urls, seen_wikipedia_titles = load_recent_history(edition_day)
    seen_classic_ids = load_recent_classic_ids(edition_day)
    seen_poetry_ids = load_recent_poetry_ids(edition_day)
    session = get_session()
    candidates: list[dict[str, Any]] = []
    successful_sources = 0
    classic_candidate: dict[str, Any] | None = None
    poetry_candidate: dict[str, Any] | None = None

    try:
        classic_candidate = collect_classic(day, seen_classic_ids)
        candidates.append(classic_candidate)
        log("Classics shelf: OK")
    except Exception as exc:
        log(f"Classics shelf: ERROR — {exc}")

    try:
        poetry_candidate = collect_poem(day, seen_poetry_ids)
        candidates.append(poetry_candidate)
        log("Poetry shelf: OK")
    except Exception as exc:
        log(f"Poetry shelf: ERROR — {exc}")

    try:
        candidates.append(collect_apod(session, day))
        successful_sources += 1
        log("NASA APOD: OK")
    except Exception as exc:
        log(f"NASA APOD: ERROR — {exc}")

    feed_candidates, feed_successes = collect_all_feeds(session, log)
    candidates.extend(feed_candidates)
    successful_sources += feed_successes

    try:
        candidates.append(collect_wikipedia(session, seen_wikipedia_titles, day))
        successful_sources += 1
        log("Hebrew Wikipedia: OK")
    except Exception as exc:
        log(f"Hebrew Wikipedia: ERROR — {exc}")

    log(f"\n{len(candidates)} candidates")
    selected = select_items(candidates, seen_urls)
    log(f"{len(selected)} selected")

    if successful_sources == 0 or not selected:
        existing = read_json(DATA_DIR / "today.json")
        if isinstance(existing, dict) and isinstance(existing.get("items"), list) and existing["items"]:
            sync_public_data()
            log("All fetching failed; preserved the previous edition.")
            return 0
        fallback = read_json(DATA_DIR / "fallback.json")
        if not isinstance(fallback, dict) or not isinstance(fallback.get("items"), list) or not fallback["items"]:
            log("ERROR: no sources and no fallback edition are available")
            return 1
        fallback["date"] = day
        fallback["generated_at"] = utc_now()
        fallback["is_fallback"] = True
        if classic_candidate and not any(
            isinstance(item, dict) and item.get("id", "").startswith("classic-")
            for item in fallback["items"]
        ):
            fallback["items"].append(as_public_item(classic_candidate))
        if poetry_candidate and not any(
            isinstance(item, dict) and item.get("id", "").startswith("poetry-")
            for item in fallback["items"]
        ):
            fallback["items"].append(as_public_item(poetry_candidate))
        # Keep the clean-checkout edition bounded while retaining both anchors.
        while len(fallback["items"]) > MAX_ITEMS:
            removable = next(
                (index for index in range(len(fallback["items"]) - 1, -1, -1)
                 if not str(fallback["items"][index].get("id", "")).startswith(("classic-", "poetry-"))),
                None,
            )
            if removable is None:
                fallback["items"] = fallback["items"][:MAX_ITEMS]
                break
            fallback["items"].pop(removable)
        archive_and_publish(fallback)
        log("No sources available; published the bundled fallback edition.")
        return 0

    edition = {
        "date": day,
        "generated_at": utc_now(),
        "is_fallback": False,
        "items": [as_public_item(item) for item in selected],
    }
    archive_and_publish(edition)
    log(f"\nGenerated {DATA_DIR / 'today.json'}")
    log(f"Published {DOCS_DATA_DIR / 'today.json'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Edition date in YYYY-MM-DD format (defaults to Israel's current date)")
    args = parser.parse_args()
    return build_edition(args.date)


if __name__ == "__main__":
    raise SystemExit(main())
