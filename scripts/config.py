"""Central configuration for public Morning content sources."""

SOURCES = [
    {
        "name": "Quanta Magazine",
        "feed": "https://www.quantamagazine.org/feed/",
        "category": "science",
        "language": "en",
        "weight": 5,
    },
    {
        "name": "JSTOR Daily",
        "feed": "https://daily.jstor.org/feed/",
        "category": "history",
        "language": "en",
        "weight": 4,
    },
    {
        "name": "NASA Earth Observatory",
        "feed": "https://earthobservatory.nasa.gov/feeds/earth-observatory.rss",
        "category": "nature",
        "language": "en",
        "weight": 5,
    },
    {
        "name": "Smithsonian Magazine",
        "feed": "https://www.smithsonianmag.com/rss/latest_articles/",
        "category": "discovery",
        "language": "en",
        "weight": 4,
    },
    {
        "name": "Aeon",
        "feed": "https://aeon.co/feed.rss",
        "category": "ideas",
        "language": "en",
        "weight": 4,
        "long_read": True,
        "long_read_path": "/essays/",
    },
    {
        "name": "הידען",
        "feed": "https://www.hayadan.org.il/feed",
        "category": "science",
        "language": "he",
        "weight": 4,
    },
]

NEGATIVE_KEYWORDS = {
    "killed": 7,
    "dead": 6,
    "death": 5,
    "war": 7,
    "attack": 6,
    "shooting": 8,
    "murder": 9,
    "bomb": 8,
    "crisis": 5,
    "election": 6,
    "campaign": 5,
    "terror": 9,
    "ceasefire": 7,
    "sanctions": 5,
    "trump": 6,
    "netanyahu": 6,
    "נהרג": 7,
    "מת": 5,
    "מוות": 6,
    "מלחמה": 7,
    "תקיפה": 6,
    "ירי": 7,
    "רצח": 9,
    "פצצה": 8,
    "משבר": 5,
    "בחירות": 6,
    "טרור": 9,
    "חטופים": 8,
}

POSITIVE_KEYWORDS = (
    "discover", "wonder", "beautiful", "curious", "new species", "ancient",
    "unexpected", "mystery", "explore", "restored", "breakthrough", "solved",
    "discovery", "ocean", "forest", "galaxy", "mathematics", "fossil",
    "גילוי", "מפתיע", "תעלומה", "עתיק", "טבע", "חלל", "מתמטיקה", "מאובן",
)

VISUAL_KEYWORDS = (
    "image", "photo", "map", "landscape", "ocean", "forest", "animal", "bird",
    "galaxy", "nebula", "planet", "volcano", "ice", "earth", "צילומים", "מפה",
    "נוף", "אוקיינוס", "יער", "כוכב", "הר געש",
)

LOW_VALUE_WIKIPEDIA_TERMS = (
    "disambiguation", "list of", "index of", "timeline of", "election", "murder",
    "massacre", "battle of", "war", "assassination", "רשימת", "פירושונים",
    "בחירות", "רצח", "טבח", "מלחמת", "קרב",
)

MAX_ITEMS = 7
MIN_QUALITY_SCORE = 5
HISTORY_DAYS = 30
REQUEST_TIMEOUT = 20
USER_AGENT = "MorningDailyMagazine/1.0 (+https://github.com/)"
