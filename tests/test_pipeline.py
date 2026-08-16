from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from scripts import apod, classics, feeds, poetry, update, utils, wikipedia


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


class PoetryTests(unittest.TestCase):
    def test_curated_shelf_is_balanced_multiline_and_public_domain(self):
        entries = poetry.load_poetry(ROOT / "data" / "poetry.json")
        self.assertEqual(len(entries), 32)
        self.assertEqual(len({entry["id"] for entry in entries}), 32)
        self.assertEqual(
            {language: sum(entry["language"] == language for entry in entries) for language in {"en", "he"}},
            {"en": 16, "he": 16},
        )
        self.assertEqual(
            {language: sum(entry["is_complete"] and entry["language"] == language for entry in entries)
             for language in {"en", "he"}},
            {"en": 2, "he": 2},
        )
        for entry in entries:
            self.assertLessEqual(len(entry["excerpt"]), 360)
            self.assertIn("\n", entry["excerpt"])
            if entry["language"] == "en":
                self.assertTrue(entry["source_url"].startswith("https://www.gutenberg.org/ebooks/"))
                self.assertIn("Public domain in the USA", entry["rights"])
            else:
                self.assertTrue(entry["source_url"].startswith("https://benyehuda.org/read/"))
                self.assertIn("נחלת הכלל", entry["rights"])

    def test_complete_poems_use_exact_primary_work_records(self):
        complete = {
            entry["id"]: entry for entry in poetry.load_poetry(ROOT / "data" / "poetry.json")
            if entry["is_complete"]
        }
        self.assertEqual(set(complete), {
            "poetry-en-blake-lily-complete",
            "poetry-en-dickinson-word-complete",
            "poetry-he-halevi-libbi-complete",
            "poetry-he-halevi-sear-complete",
        })
        self.assertTrue(all(entry["locator"].startswith("Complete poem") for entry in complete.values()))
        self.assertEqual(complete["poetry-he-halevi-libbi-complete"]["source_url"], "https://benyehuda.org/read/8780")
        self.assertEqual(complete["poetry-he-halevi-sear-complete"]["source_url"], "https://benyehuda.org/read/9113")

    def test_complete_marker_must_be_boolean(self):
        entries = poetry.load_poetry(ROOT / "data" / "poetry.json")
        entries[0]["is_complete"] = "yes"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "poetry.json"
            utils.write_json(path, entries)
            with self.assertRaisesRegex(ValueError, "is_complete must be boolean"):
                poetry.load_poetry(path)

    def test_rotation_alternates_languages_and_avoids_prior_thirty_excerpts(self):
        start = datetime(2026, 1, 1)
        seen: list[str] = []
        languages: list[str] = []
        for offset in range(32):
            day = (start + timedelta(days=offset)).date().isoformat()
            item = poetry.collect_poem(day, set(seen[-30:]))
            seen.append(item["id"])
            languages.append(item["language"])
        self.assertEqual(len(set(seen)), 32)
        self.assertTrue(all(left != right for left, right in zip(languages, languages[1:])))
        self.assertEqual(
            poetry.collect_poem("2026-01-01", set())["id"],
            poetry.collect_poem("2026-01-01", set())["id"],
        )

    def test_collector_exposes_attribution_in_existing_card_schema(self):
        item = poetry.collect_poem("2026-08-16", set())
        public = utils.as_public_item(item)
        self.assertEqual(public["category"], "poetry")
        self.assertEqual(public["label"], "Poem")
        self.assertIn("Project", public["source"])
        self.assertIn("\n", public["summary"])
        self.assertIn(public["language"], {"en", "he"})


class ShuffleTests(unittest.TestCase):
    def test_generated_shelf_is_public_unique_and_useful_on_first_day(self):
        shelf = update.build_shuffle_shelf()
        today = utils.read_json(ROOT / "data" / "today.json")["items"]
        current_ids = {item["id"] for item in today}
        alternatives = [item for item in shelf if item["id"] not in current_ids]

        self.assertEqual(len({item["id"] for item in shelf}), len(shelf))
        self.assertEqual(
            sum(item["category"] == "classics" for item in shelf), len(classics.load_classics()),
        )
        self.assertEqual(
            sum(item["category"] == "poetry" for item in shelf), len(poetry.load_poetry()),
        )
        self.assertGreaterEqual(
            sum(item["category"] not in {"classics", "poetry"} for item in alternatives),
            5,
        )
        public_fields = set(utils.as_public_item({}))
        self.assertTrue(all(set(item) == public_fields for item in shelf))

    def test_published_shuffle_shelf_matches_generated_data(self):
        source = utils.read_json(ROOT / "data" / "shuffle.json")
        published = utils.read_json(ROOT / "docs" / "data" / "shuffle.json")
        self.assertEqual(source, published)
        self.assertEqual(source["items"], update.build_shuffle_shelf())

    def test_browser_selector_builds_two_valid_nonrepeating_mixes(self):
        script = r'''
          const fs = require("fs");
          global.window = {};
          eval(fs.readFileSync("docs/shuffle.js", "utf8"));
          const pool = JSON.parse(fs.readFileSync("docs/data/shuffle.json", "utf8")).items;
          const today = JSON.parse(fs.readFileSync("docs/data/today.json", "utf8")).items;
          const random = () => 0.37;
          const first = window.MorningShuffle.chooseMix(pool, today, random);
          const second = window.MorningShuffle.chooseMix(pool, first, random);
          const check = (mix, prior) => {
            if (!mix || mix.length !== 7) throw new Error("mix must contain seven items");
            if (new Set(mix.map((item) => item.id)).size !== 7) throw new Error("duplicate IDs");
            if (mix.filter((item) => item.category === "classics").length !== 1) throw new Error("classic anchor");
            if (mix.filter((item) => item.category === "poetry").length !== 1) throw new Error("poetry anchor");
            const priorIds = new Set(prior.map((item) => item.id));
            if (mix.some((item) => priorIds.has(item.id))) throw new Error("immediate duplicate");
          };
          check(first, today);
          check(second, first);
          if (window.MorningShuffle.chooseMix(first, first, random) !== null) throw new Error("missing no-alternate state");
        '''
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


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

    def test_one_poem_and_one_classic_are_selected_despite_shared_seen_urls(self):
        classic = candidate(
            "https://www.gutenberg.org/ebooks/3330",
            id="classic-test", category="classics", is_classic=True, score=6,
        )
        poems = [
            candidate(
                "https://www.gutenberg.org/ebooks/6130",
                id=f"poetry-en-test-{number}", category="poetry", is_poetry=True, score=7,
            )
            for number in (1, 2)
        ]
        chosen = update.select_items(
            [classic, *poems, *[
                candidate(f"https://example.com/{letter}", source=f"Source {letter}", category=f"topic-{letter}")
                for letter in "abcdefghij"
            ]],
            {classic["url"], poems[0]["url"]},
        )
        self.assertEqual(len(chosen), update.MAX_ITEMS)
        self.assertEqual(sum(item.get("is_classic", False) for item in chosen), 1)
        self.assertEqual(sum(item.get("is_poetry", False) for item in chosen), 1)

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

    def test_poetry_history_reads_ids_from_only_prior_thirty_days(self):
        tz = ZoneInfo("Asia/Jerusalem")
        day = datetime(2026, 8, 16, tzinfo=tz)
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            history = data_dir / "history"
            history.mkdir()
            utils.write_json(history / "2026-08-15.json", {"items": [
                {"id": "poetry-he-recent"}, {"id": 42}, {"id": "feed-other"},
            ]})
            utils.write_json(history / "2026-07-16.json", {"items": [{"id": "poetry-en-old"}]})
            with patch.object(update, "DATA_DIR", data_dir):
                ids = update.load_recent_poetry_ids(day)
        self.assertEqual(ids, {"poetry-he-recent"})


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
        self.assertLessEqual(len(edition["items"]), update.MAX_ITEMS)
        self.assertEqual(sum(item["id"].startswith("classic-") for item in edition["items"]), 1)
        self.assertEqual(sum(item["id"].startswith("poetry-") for item in edition["items"]), 1)

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
        self.assertEqual(sum(item["id"].startswith("poetry-") for item in edition["items"]), 1)
        self.assertLessEqual(len(edition["items"]), update.MAX_ITEMS)

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


class PwaTests(unittest.TestCase):
    def test_manifest_is_installable_from_a_github_pages_subpath(self):
        manifest = utils.read_json(ROOT / "docs" / "manifest.webmanifest")
        self.assertEqual(manifest["id"], "./")
        self.assertEqual(manifest["start_url"], "./")
        self.assertEqual(manifest["scope"], "./")
        self.assertEqual(manifest["display"], "standalone")

        icons = {(icon["sizes"], icon["type"], icon["purpose"]): icon["src"] for icon in manifest["icons"]}
        self.assertIn(("192x192", "image/png", "any"), icons)
        self.assertIn(("512x512", "image/png", "any"), icons)
        self.assertIn(("512x512", "image/png", "maskable"), icons)
        for src in icons.values():
            self.assertTrue(src.startswith("./icons/"))
            self.assertTrue((ROOT / "docs" / src.removeprefix("./")).is_file())

    def test_png_icon_dimensions_match_manifest(self):
        for name, expected in {
            "morning-180.png": (180, 180),
            "morning-192.png": (192, 192),
            "morning-512.png": (512, 512),
            "morning-maskable-512.png": (512, 512),
        }.items():
            payload = (ROOT / "docs" / "icons" / name).read_bytes()
            self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", payload[16:24]), expected)

    def test_png_icons_have_opaque_background_and_visible_sunrise_mark(self):
        def colors_in_indexed_png(path):
            payload = path.read_bytes()
            position = 8
            chunks = {}
            while position < len(payload):
                length = struct.unpack(">I", payload[position:position + 4])[0]
                kind = payload[position + 4:position + 8]
                chunks.setdefault(kind, b"")
                chunks[kind] += payload[position + 8:position + 8 + length]
                position += length + 12
            width, height, depth, color_type = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
            self.assertEqual((depth, color_type), (8, 3))
            self.assertNotIn(b"tRNS", chunks)
            palette = [tuple(chunks[b"PLTE"][i:i + 3]) for i in range(0, len(chunks[b"PLTE"]), 3)]
            encoded = zlib.decompress(chunks[b"IDAT"])
            colors = []
            prior = bytearray(width)
            offset = 0
            for _ in range(height):
                filter_type = encoded[offset]
                source = encoded[offset + 1:offset + 1 + width]
                offset += width + 1
                row = bytearray(width)
                for index, byte in enumerate(source):
                    left = row[index - 1] if index else 0
                    up = prior[index]
                    upper_left = prior[index - 1] if index else 0
                    if filter_type == 0:
                        value = byte
                    elif filter_type == 1:
                        value = byte + left
                    elif filter_type == 2:
                        value = byte + up
                    elif filter_type == 3:
                        value = byte + ((left + up) // 2)
                    else:
                        estimate = left + up - upper_left
                        nearest = min((left, up, upper_left), key=lambda value: abs(estimate - value))
                        value = byte + nearest
                    row[index] = value % 256
                colors.extend(palette[index] for index in row)
                prior = row
            return colors

        for name in (
            "morning-180.png", "morning-192.png", "morning-512.png", "morning-maskable-512.png",
        ):
            colors = colors_in_indexed_png(ROOT / "docs" / "icons" / name)
            self.assertGreater(colors.count((244, 240, 232)), len(colors) // 2)
            self.assertGreater(colors.count((49, 95, 81)), len(colors) // 100)

    def test_install_metadata_and_worker_cover_offline_shell(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        worker = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")
        app = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")

        self.assertIn('rel="manifest" href="./manifest.webmanifest"', html)
        self.assertIn('rel="apple-touch-icon" href="./icons/morning-180.png"', html)
        self.assertIn('name="theme-color" media="(prefers-color-scheme: dark)"', html)
        self.assertIn('navigator.serviceWorker.register("./sw.js")', app)
        for resource in (
            "./index.html", "./style.css", "./shuffle.js", "./app.js", "./manifest.webmanifest",
            "./data/today.json", "./data/shuffle.json", "./data/archive.json", "./icons/morning-512.png",
        ):
            self.assertIn(f'"{resource}"', worker)
        self.assertIn('event.request.mode === "navigate"', worker)
        self.assertIn('caches.match("./index.html")', worker)

    def test_shuffle_control_has_accessible_states_and_race_guard(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="shuffle-edition"', html)
        self.assertIn('aria-busy="false"', html)
        self.assertIn('id="shuffle-status"', html)
        self.assertIn('role="status" aria-live="polite"', html)
        self.assertIn("if (isShuffling || !currentEdition) return;", app)
        self.assertIn("if (event.detail > 1) return;", app)
        self.assertIn('elements.shuffle.setAttribute("aria-busy", String(busy))', app)
        self.assertIn("No different mix is available yet.", app)
        self.assertIn("Couldn’t shuffle. Check your connection, then try again.", app)

    def test_footer_credits_authors_and_links_to_repository(self):
        html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        styles = (ROOT / "docs" / "style.css").read_text(encoding="utf-8")
        worker = (ROOT / "docs" / "sw.js").read_text(encoding="utf-8")

        self.assertIn("By Nir Yariv and Codex. Summer 2026", html)
        self.assertIn(
            'class="github-link" href="https://github.com/niryariv/morningapp" aria-label="View source on GitHub"',
            html,
        )
        self.assertNotIn(">View source on GitHub</a>", html)
        self.assertIn('<span class="repository-link">', html)
        self.assertIn('<svg aria-hidden="true" focusable="false" viewBox="0 0 16 16">', html)
        self.assertIn(".repository-link {", styles)
        self.assertIn("display: inline-flex;", styles)
        self.assertIn("width: 2.75rem;", styles)
        self.assertIn("height: 2.75rem;", styles)
        self.assertIn("fill: currentColor;", styles)
        self.assertIn("calc(var(--reader-size) * 0.68)", styles)
        self.assertIn('const CACHE = "morning-shell-v7";', worker)


if __name__ == "__main__":
    unittest.main()
