from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from scripts import apod, classics, feeds, update, utils, wikipedia


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload=None, content: bytes = b""):
        self._payload = payload
        self.content = content

    def json(self):
        return self._payload


def candidate(url: str, **overrides):
    item = {
        "id": utils.stable_id("test", url),
        "category": "science",
        "label": "Science",
        "title": "A worthwhile discovery",
        "summary": "A sufficiently detailed summary of a calm and interesting scientific discovery.",
        "url": url,
        "source": "Test Source",
        "image": None,
        "image_alt": None,
        "published": "2026-08-16",
        "reading_minutes": None,
        "language": "en",
        "score": 20,
        "score_parts": {},
        "is_long_read": False,
    }
    item.update(overrides)
    return item


class UtilityTests(unittest.TestCase):
    def test_normalize_url_removes_tracking_and_rejects_unsafe_values(self):
        self.assertEqual(
            utils.normalize_url("HTTPS://Example.COM/story/?utm_source=x&keep=yes#section"),
            "https://example.com/story?keep=yes",
        )
        for value in ("javascript:alert(1)", "data:text/html,x", "/relative", "https://u:p@example.com/x", None, 4):
            self.assertEqual(utils.normalize_url(value), "")

    def test_keyword_matching_uses_word_boundaries(self):
        self.assertTrue(utils.keyword_matches("A war changed history", "war"))
        self.assertFalse(utils.keyword_matches("Useful software for astronomy", "war"))
        self.assertFalse(utils.keyword_matches("האמת מעניינת", "מת"))
        self.assertTrue(utils.keyword_matches("סיפור על מת מפורסם", "מת"))

    def test_json_write_is_atomic_and_unicode_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "edition.json"
            utils.write_json(path, {"title": "בוקר"})
            self.assertEqual(utils.read_json(path), {"title": "בוקר"})
            self.assertFalse(path.with_suffix(".json.tmp").exists())


class CollectorTests(unittest.TestCase):
    @patch("scripts.apod.fetch")
    def test_video_apod_requests_and_uses_thumbnail(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse({
            "title": "A video sky",
            "explanation": "A long enough explanation of a beautiful astronomical observation.",
            "media_type": "video",
            "thumbnail_url": "https://img.example/thumb.jpg",
            "date": "2026-08-16",
        })
        item = apod.collect_apod(Mock(), "2026-08-16")
        self.assertEqual(item["image"], "https://img.example/thumb.jpg")
        self.assertEqual(mocked_fetch.call_args.kwargs["params"]["thumbs"], "true")

    @patch("scripts.apod.fetch")
    def test_apod_blank_optional_key_uses_demo_key(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse({
            "title": "A sky",
            "explanation": "A long enough explanation of a beautiful astronomical observation.",
            "media_type": "image",
            "url": "https://img.example/sky.jpg",
        })
        with patch.dict("os.environ", {"NASA_API_KEY": ""}):
            apod.collect_apod(Mock(), "2026-08-16")
        self.assertEqual(mocked_fetch.call_args.kwargs["params"]["api_key"], "DEMO_KEY")

    @patch("scripts.apod.fetch")
    def test_apod_rejects_unsafe_media_url(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse({
            "title": "A sky",
            "explanation": "A long enough explanation of an astronomical observation.",
            "media_type": "image",
            "url": "javascript:alert(1)",
        })
        self.assertIsNone(apod.collect_apod(Mock(), "2026-08-16")["image"])

    @patch("scripts.feeds.fetch")
    def test_feed_resolves_relative_links_and_ignores_unsafe_image(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse(content=b"")
        parsed = SimpleNamespace(bozo=False, entries=[{
            "title": "A calm article",
            "link": "/article",
            "summary": "A detailed and sufficiently long summary about a scientific discovery in a forest.",
            "media_content": [{"url": "javascript:alert(1)"}],
        }])
        source = {"name": "Example", "feed": "https://example.com/feed", "category": "science", "language": "en", "weight": 4}
        with patch("scripts.feeds.feedparser.parse", return_value=parsed):
            items = feeds.collect_feed(Mock(), source)
        self.assertEqual(items[0]["url"], "https://example.com/article")
        self.assertIsNone(items[0]["image"])

    @patch("scripts.feeds.fetch")
    def test_one_malformed_feed_entry_does_not_discard_valid_entries(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse(content=b"")
        parsed = SimpleNamespace(bozo=False, entries=[
            {"title": "Broken", "link": "https://example.com/broken", "summary": 123},
            {
                "title": "Healthy",
                "link": "https://example.com/healthy",
                "summary": "A detailed and sufficiently long summary about a scientific discovery in a forest.",
            },
        ])
        source = {"name": "Example", "feed": "https://example.com/feed", "category": "science", "language": "en", "weight": 4}
        with patch("scripts.feeds.feedparser.parse", return_value=parsed):
            items = feeds.collect_feed(Mock(), source)
        self.assertEqual([item["title"] for item in items], ["Healthy"])

    @patch("scripts.feeds.fetch")
    def test_aeon_byline_boilerplate_is_removed(self, mocked_fetch):
        mocked_fetch.return_value = FakeResponse(content=b"")
        parsed = SimpleNamespace(bozo=False, entries=[{
            "title": "A thoughtful essay",
            "link": "https://aeon.co/essays/a-thoughtful-essay",
            "summary": (
                "A detailed public summary that is comfortably long enough for a useful Morning card. "
                "- by Example Author Read on Aeon"
            ),
        }])
        source = {
            "name": "Aeon",
            "feed": "https://aeon.co/feed.rss",
            "category": "ideas",
            "language": "en",
            "weight": 4,
            "long_read": True,
            "long_read_path": "/essays/",
        }
        with patch("scripts.feeds.feedparser.parse", return_value=parsed):
            items = feeds.collect_feed(Mock(), source)
        self.assertEqual(
            items[0]["summary"],
            "A detailed public summary that is comfortably long enough for a useful Morning card.",
        )

    def test_scoring_does_not_penalize_war_inside_software(self):
        source = {"category": "science", "weight": 4}
        _, parts = feeds._score(source, "Software for astronomy", "A useful tool", None)
        self.assertEqual(parts["negative_penalty"], 0)
        _, parts = feeds._score(source, "War and astronomy", "A historical account", None)
        self.assertEqual(parts["negative_penalty"], 7)

    def test_each_feed_failure_isolated(self):
        sources = [
            {"name": "Broken", "feed": "https://broken.example/feed", "category": "science", "language": "en", "weight": 1},
            {"name": "Healthy", "feed": "https://healthy.example/feed", "category": "science", "language": "en", "weight": 1},
        ]
        logs = []
        with patch.object(feeds, "SOURCES", sources), patch.object(
            feeds, "collect_feed", side_effect=[RuntimeError("offline"), [candidate("https://healthy.example/a")]]
        ):
            items, successes = feeds.collect_all_feeds(Mock(), logs.append)
        self.assertEqual(successes, 1)
        self.assertEqual(len(items), 1)
        self.assertTrue(any("Broken: ERROR" in line for line in logs))

    @patch("scripts.wikipedia.fetch")
    def test_wikipedia_rejects_non_http_article_and_image_urls(self, mocked_fetch):
        mocked_fetch.side_effect = [
            FakeResponse({"query": {"categorymembers": [{"pageid": 1, "title": "ערך נבחר"}]}}),
            FakeResponse({"query": {"pages": [{
                "pageid": 1,
                "title": "ערך נבחר",
                "extract": "תיאור ארוך ומעניין של ערך מומלץ. " * 12,
                "fullurl": "javascript:alert(1)",
                "thumbnail": {"source": "data:image/svg+xml,x"},
            }]}}),
        ]
        with self.assertRaisesRegex(ValueError, "no suitable"):
            wikipedia.collect_wikipedia(Mock(), set(), "2026-08-16")


class ClassicsTests(unittest.TestCase):
    def test_curated_shelf_is_short_public_domain_and_spans_traditions(self):
        entries = classics.load_classics(ROOT / "data" / "classics.json")
        self.assertEqual(len(entries), 31)
        self.assertEqual(len({entry["id"] for entry in entries}), 31)
        self.assertGreaterEqual(len({entry["tradition"] for entry in entries}), 7)
        for entry in entries:
            self.assertLessEqual(len(entry["excerpt"]), 280)
            self.assertTrue(entry["source_url"].startswith("https://www.gutenberg.org/ebooks/"))
            self.assertIn("Public domain in the USA", entry["rights"])

    def test_rotation_is_deterministic_and_avoids_prior_thirty_excerpts(self):
        start = datetime(2026, 1, 1)
        seen: list[str] = []
        chosen: list[str] = []
        for offset in range(31):
            day = (start + timedelta(days=offset)).date().isoformat()
            item = classics.collect_classic(day, set(seen[-30:]))
            chosen.append(item["id"])
            seen.append(item["id"])
        self.assertEqual(len(set(chosen)), 31)
        self.assertEqual(
            classics.collect_classic("2026-01-01", set())["id"],
            classics.collect_classic("2026-01-01", set())["id"],
        )

    def test_collector_exposes_attribution_in_existing_card_schema(self):
        item = classics.collect_classic("2026-08-16", set())
        public = utils.as_public_item(item)
        self.assertEqual(public["category"], "classics")
        self.assertEqual(public["label"], "From the classics")
        self.assertIn(" · ", public["source"])
        self.assertEqual(public["reading_minutes"], 1)
        self.assertEqual(set(public), {
            "id", "category", "label", "title", "summary", "url", "source",
            "image", "image_alt", "published", "reading_minutes", "language",
        })


class SelectionAndHistoryTests(unittest.TestCase):
    def test_selection_deduplicates_normalized_urls_and_limits_long_reads(self):
        items = [
            candidate("https://example.com/a?utm_source=one", score=10),
            candidate("https://example.com/a", score=30),
            candidate("https://example.com/long-1", source="Aeon", category="ideas", is_long_read=True, score=29),
            candidate("https://example.com/long-2", source="Other", category="ideas", is_long_read=True, score=28),
        ]
        chosen = update.select_items(items, set())
        self.assertEqual(sum(item["url"].startswith("https://example.com/a") for item in chosen), 1)
        self.assertLessEqual(sum(bool(item["is_long_read"]) for item in chosen), 1)

    def test_classic_is_selected_even_when_its_edition_url_was_seen(self):
        classic = candidate(
            "https://www.gutenberg.org/ebooks/3330",
            id="classic-analects-test",
            category="classics",
            label="From the classics",
            source="Book I · trans. James Legge",
            is_classic=True,
            score=6,
        )
        second_classic = dict(
            classic,
            id="classic-analects-other",
            url="https://www.gutenberg.org/ebooks/216",
            source="Chapter 8 · trans. James Legge",
        )
        chosen = update.select_items(
            [classic, second_classic, candidate("https://example.com/a")],
            {classic["url"]},
        )
        self.assertIn(classic, chosen)
        self.assertEqual(sum(item.get("is_classic", False) for item in chosen), 1)

    def test_history_reads_only_prior_thirty_days_and_survives_malformed_urls(self):
        tz = ZoneInfo("Asia/Jerusalem")
        day = datetime(2026, 8, 16, tzinfo=tz)
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            history = data_dir / "history"
            history.mkdir()
            utils.write_json(history / "2026-08-15.json", {"items": [
                {"url": "https://example.com/a?utm_source=x", "source": "ויקיפדיה", "title": "אלף"},
                {"url": 42, "source": "Other", "title": "Malformed"},
            ]})
            utils.write_json(history / "2026-07-16.json", {"items": [{"url": "https://example.com/old"}]})
            utils.write_json(history / "2026-08-14.json", ["not", "an", "edition"])
            with patch.object(update, "DATA_DIR", data_dir):
                urls, titles = update.load_recent_history(day)
        self.assertEqual(urls, {"https://example.com/a"})
        self.assertEqual(titles, {"אלף"})

    def test_classic_history_reads_ids_from_only_prior_thirty_days(self):
        tz = ZoneInfo("Asia/Jerusalem")
        day = datetime(2026, 8, 16, tzinfo=tz)
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            history = data_dir / "history"
            history.mkdir()
            utils.write_json(history / "2026-08-15.json", {"items": [
                {"id": "classic-recent"}, {"id": 42}, {"id": "feed-other"},
            ]})
            utils.write_json(history / "2026-07-16.json", {"items": [{"id": "classic-old"}]})
            with patch.object(update, "DATA_DIR", data_dir):
                ids = update.load_recent_classic_ids(day)
        self.assertEqual(ids, {"classic-recent"})


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data = self.root / "data"
        self.docs_data = self.root / "docs" / "data"
        self.data.mkdir()
        utils.write_json(self.data / "fallback.json", {
            "date": "2000-01-01",
            "generated_at": "2000-01-01T00:00:00Z",
            "is_fallback": True,
            "items": [utils.as_public_item(candidate("https://example.com/fallback"))],
        })
        self.paths = patch.multiple(update, DATA_DIR=self.data, DOCS_DATA_DIR=self.docs_data)
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        self.tempdir.cleanup()

    def test_total_outage_preserves_existing_edition(self):
        existing = {"date": "2026-08-15", "items": [utils.as_public_item(candidate("https://example.com/existing"))]}
        utils.write_json(self.data / "today.json", existing)
        with patch.object(update, "collect_apod", side_effect=RuntimeError("offline")), patch.object(
            update, "collect_all_feeds", return_value=([], 0)
        ), patch.object(update, "collect_wikipedia", side_effect=RuntimeError("offline")):
            self.assertEqual(update.build_edition("2026-08-16"), 0)
        self.assertEqual(utils.read_json(self.data / "today.json"), existing)
        self.assertEqual(utils.read_json(self.docs_data / "today.json"), existing)

    def test_total_outage_on_clean_checkout_publishes_fallback(self):
        with patch.object(update, "collect_apod", side_effect=RuntimeError("offline")), patch.object(
            update, "collect_all_feeds", return_value=([], 0)
        ), patch.object(update, "collect_wikipedia", side_effect=RuntimeError("offline")):
            self.assertEqual(update.build_edition("2026-08-16"), 0)
        edition = utils.read_json(self.data / "today.json")
        self.assertEqual(edition["date"], "2026-08-16")
        self.assertTrue(edition["is_fallback"])
        self.assertTrue(edition["items"])

    def test_partial_outage_still_publishes_available_content(self):
        available = candidate("https://example.com/live", featured=True)
        with patch.object(update, "collect_apod", side_effect=RuntimeError("offline")), patch.object(
            update, "collect_all_feeds", return_value=([available], 1)
        ), patch.object(update, "collect_wikipedia", side_effect=RuntimeError("offline")):
            self.assertEqual(update.build_edition("2026-08-16"), 0)
        edition = utils.read_json(self.data / "today.json")
        self.assertFalse(edition["is_fallback"])
        self.assertIn("https://example.com/live", [item["url"] for item in edition["items"]])
        self.assertEqual(sum(item["id"].startswith("classic-") for item in edition["items"]), 1)

    def test_malformed_previous_date_cannot_escape_history_directory(self):
        utils.write_json(self.data / "today.json", {"date": "../../escaped", "items": []})
        edition = {"date": "2026-08-16", "generated_at": "2026-08-16T00:00:00Z", "items": []}
        update.archive_and_publish(edition)
        self.assertFalse((self.root / "escaped.json").exists())
        self.assertEqual(utils.read_json(self.data / "today.json"), edition)


class EntrypointTests(unittest.TestCase):
    def test_package_entrypoint_works_from_clean_checkout_layout(self):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.update", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Edition date", result.stdout)


if __name__ == "__main__":
    unittest.main()
