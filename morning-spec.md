# Morning — Personal Positive Reading Feed

## 1. Goal

Build a small personal website called **Morning** that provides a calm, interesting, finite set of things to read each morning.

The purpose is to replace habitual morning scrolling through X, breaking news, and other high-arousal feeds with content that encourages curiosity, learning, beauty, and perspective.

The site must:

- contain no breaking-news feed
- contain no infinite scroll
- contain no comments, likes, engagement metrics, or trending topics
- have no user accounts
- use no paid services
- require no server
- run entirely using **GitHub Actions + GitHub Pages**
- refresh automatically once per day
- work well on a phone
- remain useful if some external sources are temporarily unavailable

The experience should feel closer to opening a small daily magazine than opening a social network.

---

# 2. Technical constraints

## Hosting

Use:

- GitHub repository
- GitHub Actions
- GitHub Pages

Do not use:

- Vercel
- Netlify
- Cloudflare Workers
- AWS
- Firebase
- Supabase
- paid APIs
- databases
- external backend services
- analytics platforms

The resulting site must be a completely static site.

---

# 3. Architecture

Use the following simple pipeline:

```text
Public RSS/API/web sources
        ↓
GitHub Action (once per day)
        ↓
Python content collection script
        ↓
data/today.json
        ↓
Static HTML/CSS/JS
        ↓
GitHub Pages
```

The daily GitHub Action should fetch fresh material and generate a structured JSON file.

The web frontend should simply render that JSON.

Do not perform API calls from the browser unless there is a compelling reason. Prefer fetching everything during the GitHub Action.

This makes the frontend deterministic, fast, and resistant to CORS problems.

---

# 4. Repository structure

Use approximately this structure:

```text
morning/
├── .github/
│   └── workflows/
│       └── update.yml
│
├── scripts/
│   ├── update.py
│   ├── feeds.py
│   ├── wikipedia.py
│   ├── apod.py
│   └── utils.py
│
├── data/
│   ├── today.json
│   └── history/
│
├── docs/
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   ├── manifest.webmanifest
│   └── icons/
│
├── requirements.txt
├── README.md
└── .gitignore
```

GitHub Pages should publish the `/docs` directory from the main branch unless Codex finds a cleaner GitHub Pages deployment method.

Avoid a frontend build system unless genuinely necessary.

Prefer:

- plain HTML
- plain CSS
- vanilla JavaScript

Do not introduce React, Vue, Next.js, npm, Tailwind, bundlers, or similar dependencies merely for convenience.

---

# 5. Daily content

The page should contain approximately **6–8 items per day**.

The feed should deliberately be finite.

Suggested categories:

1. Image of the day
2. Science
3. Mathematics / physics
4. History / archaeology
5. Nature / geography
6. Random discovery
7. Long read
8. Optional wildcard

Not every category must appear every day.

A normal morning page should contain around seven items.

---

# 6. Preferred content sources

All sources must be publicly accessible and free.

Prefer RSS, Atom, or documented public APIs over scraping HTML.

## Astronomy

### NASA Astronomy Picture of the Day

Use NASA APOD.

Display:

- title
- image
- short explanation
- source URL
- date

If an API key is required, support a GitHub Actions secret such as:

```text
NASA_API_KEY
```

But the application must also work with NASA's public/demo access if available.

Do not make possession of an API key mandatory for first launch.

If APOD for the day is a video rather than an image, either:

- use its thumbnail if available
- or omit the image and show the item as a normal article

---

# 7. Science sources

Prefer RSS feeds from sources such as:

- Quanta Magazine
- Scientific American
- Smithsonian
- Nature-related public feeds where usable
- NASA
- ESA
- NOAA
- USGS

Do not scrape sites aggressively.

Do not circumvent paywalls.

An article should only be included when the publicly available metadata is sufficient to create a useful card.

---

# 8. History and archaeology

Candidate sources:

- Smithsonian
- JSTOR Daily
- History Today, where an RSS/public feed exists
- archaeology publications with public RSS
- museum or university feeds
- Wikipedia

Prefer substantive historical pieces over current political commentary.

---

# 9. Wikipedia discovery

Include one Wikipedia-based item each day.

Possible approaches:

### Featured article

Prefer a current featured article if reliably retrievable.

Otherwise:

### Random article

Use the MediaWiki API to fetch random articles.

Filter obvious low-value candidates where practical.

Avoid:

- disambiguation pages
- list-only pages
- extremely short stubs
- current political figures where possible
- gruesome/crime-focused subjects where possible

This filtering does not have to be perfect.

Retrieve:

- title
- extract
- thumbnail if available
- canonical URL

---

# 10. On This Day

Optionally include one historical event associated with today's date.

Use Wikipedia or another public source.

Do not dump a large list.

Select **one interesting event**.

Prefer:

- scientific discoveries
- exploration
- culture
- engineering
- archaeology
- invention
- unusual historical events

Avoid making wars, assassinations, disasters, and political crises the default.

---

# 11. Nature / geography

Include material from sources such as:

- NASA Earth Observatory
- NOAA
- USGS
- national parks
- geography / ecology publications
- Wikimedia Commons where suitable

Strongly prefer visually interesting material.

Possible themes:

- landscapes
- geology
- animals
- oceans
- forests
- maps
- remote places
- natural phenomena

---

# 12. Long read

Include at most one longer article.

Candidate sources:

- Aeon
- Nautilus
- Quanta
- Smithsonian
- JSTOR Daily

The item should clearly indicate that it is a longer read.

Example:

```text
12 min read
```

Estimate reading time from available summary/article text only if reliable.

Otherwise omit the estimate.

---

# 13. Content-selection philosophy

The system should not simply display the newest seven RSS entries.

It should deliberately create a balanced morning edition.

Selection priorities:

### High priority

- curiosity
- discovery
- scientific understanding
- history
- nature
- beautiful imagery
- surprising facts
- thoughtful long-form material

### Lower priority

- product announcements
- corporate news
- celebrity news
- politics
- conflict
- crime
- catastrophe
- financial markets
- culture-war material

This is not intended to become a general news aggregator.

---

# 14. Simple scoring

Implement a lightweight scoring mechanism.

Each candidate item can receive scores for:

```python
interest_score
positivity_score
timelessness_score
visual_score
novelty_score
```

A simple weighted score is sufficient.

Example:

```python
score = (
    interest_score * 3
    + timelessness_score * 2
    + visual_score
    + positivity_score
)
```

Do not use an LLM or paid classification API.

Use simple source/category weighting plus keyword heuristics.

---

# 15. Negative-topic filtering

Create a configurable blocklist / penalty list.

Examples:

```python
NEGATIVE_KEYWORDS = [
    "killed",
    "dead",
    "war",
    "attack",
    "shooting",
    "murder",
    "bomb",
    "crisis",
    "election",
    "campaign",
    "terror",
]
```

Do not necessarily ban every item containing these words.

Instead apply a strong negative score.

Some historically or scientifically worthwhile items may legitimately contain such terms.

---

# 16. Deduplication

Prevent repeated material.

Store the IDs or URLs of recently displayed items.

For example:

```text
data/history/2026-08-15.json
data/history/2026-08-14.json
...
```

When selecting today's items, inspect roughly the previous 30 days.

Avoid showing the same URL twice within that period.

For Wikipedia random pages, avoid previously used article titles.

---

# 17. Daily JSON format

Generate:

```text
data/today.json
```

Example structure:

```json
{
  "date": "2026-08-16",
  "generated_at": "2026-08-16T04:15:00Z",
  "items": [
    {
      "id": "apod-2026-08-16",
      "category": "astronomy",
      "label": "Image of the day",
      "title": "Example title",
      "summary": "Short description here.",
      "url": "https://example.com/article",
      "source": "NASA",
      "image": "https://example.com/image.jpg",
      "image_alt": "Description of the image",
      "published": "2026-08-16",
      "reading_minutes": null
    }
  ]
}
```

The frontend should know nothing about individual source APIs.

It should render only this normalized structure.

---

# 18. History archive

Keep previous editions.

Store:

```text
data/history/YYYY-MM-DD.json
```

Before overwriting `today.json`, save the previous/current edition into the archive where appropriate.

The interface should make it possible to navigate to recent days.

For example:

```text
‹ Yesterday        Today        Tomorrow ›
```

Obviously future editions won't exist.

A simpler archive button is also acceptable.

---

# 19. Frontend design

The visual style should be quiet and editorial.

Think:

- morning newspaper
- magazine
- book
- reading room

Not:

- social network
- dashboard
- news portal

Use generous whitespace.

Mobile-first design.

Suggested page width:

```css
max-width: 720px;
```

---

# 20. Header

Example:

```text
Morning
Saturday · 15 August

Seven interesting things for today.
```

Keep the header small.

No giant hero banner.

---

# 21. Cards

Each item should contain:

```text
CATEGORY

Article title

Short 1–3 sentence description.

[image if appropriate]

Source · estimated reading time

Read →
```

Cards should not show:

- share counts
- likes
- comments
- popularity
- trending indicators
- timestamps such as "3 minutes ago"

Exact publication dates can exist in metadata but should not create urgency.

---

# 22. APOD layout

The astronomy image can be visually larger than the other items.

Example:

```text
IMAGE OF THE DAY

[large image]

The Sombrero Galaxy

NASA · Astronomy Picture of the Day

Short explanation.
```

Clicking the image/title should open the original source.

---

# 23. No infinite scroll

This is a hard requirement.

When the user reaches the final item, show:

```text
That's all for this morning.
```

Optionally underneath:

```text
Go have breakfast.
```

No "load more".

No automatic recommendations.

No endless archive below the current edition.

---

# 24. Reading mode

External links should open in a new tab.

Do not attempt to scrape and republish full copyrighted articles.

Only display:

- title
- short excerpt/summary
- source
- link
- publicly available image metadata

---

# 25. Calm-mode details

The UI should deliberately avoid attention-grabbing patterns.

Do not use:

- red badges
- notification dots
- flashing animation
- autoplay
- carousels
- urgency language
- "breaking"
- "trending"
- push notifications

Animations, if any, should be subtle and optional.

---

# 26. Dark mode

Support:

```css
@media (prefers-color-scheme: dark)
```

No manual setting is necessary initially.

Both modes should prioritize comfortable reading.

---

# 27. PWA support

Make the site installable as a simple PWA.

Include:

```text
manifest.webmanifest
```

Set:

```text
name: Morning
short_name: Morning
display: standalone
```

Provide suitable icons.

A service worker is optional.

If implemented, keep it extremely simple.

The previous day's page should preferably remain available when offline.

---

# 28. GitHub Action

Create:

```text
.github/workflows/update.yml
```

Run once per day.

Target approximately early morning Israel time.

Because GitHub Actions cron uses UTC, document the chosen UTC time and the daylight-saving limitation.

A reasonable schedule is around:

```yaml
schedule:
  - cron: "15 3 * * *"
```

Also support:

```yaml
workflow_dispatch:
```

so the content can be regenerated manually.

---

# 29. Workflow steps

The workflow should roughly:

```text
checkout repository
↓
setup Python
↓
install requirements
↓
run scripts/update.py
↓
detect whether files changed
↓
commit generated data
↓
push commit
↓
deploy through GitHub Pages
```

Use the GitHub Actions built-in token.

Do not require a personal access token unless unavoidable.

---

# 30. Failure behavior

The daily build must be resilient.

One failed source must not fail the entire update.

For each source:

```python
try:
    ...
except Exception:
    log error
    continue
```

If only five good stories are found instead of seven, publish five.

Never fill the page with low-quality content simply to reach a quota.

If all fetching fails, preserve yesterday's edition rather than creating an empty page.

---

# 31. Source configuration

Keep source definitions in one place.

Example:

```python
SOURCES = [
    {
        "name": "Quanta Magazine",
        "feed": "...",
        "category": "science",
        "weight": 5
    }
]
```

Adding or removing a source should not require modifying the rest of the application.

---

# 32. Dependencies

Keep Python dependencies minimal.

Likely:

```text
requests
feedparser
beautifulsoup4
```

BeautifulSoup should only be used when necessary.

Prefer RSS/API metadata over scraping pages.

Use the Python standard library wherever practical.

---

# 33. Logging

The Action output should clearly report what happened.

Example:

```text
Morning update — 2026-08-16

NASA APOD: OK
Quanta: 12 candidates
Smithsonian: 8 candidates
Wikipedia: OK
JSTOR Daily: 5 candidates

43 candidates
19 passed filters
7 selected

Generated data/today.json
Archived previous edition
```

Errors should identify the source without crashing the entire process.

---

# 34. README

The README should explain:

1. what Morning is
2. how the architecture works
3. how to enable GitHub Pages
4. how to run locally
5. how to trigger a manual update
6. how to add/remove RSS sources
7. what GitHub Secrets are optional
8. how daily scheduling works
9. how the history archive works

Include local commands such as:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/update.py
python -m http.server 8000 --directory docs
```

---

# 35. First version scope

Do not over-engineer version 1.

Version 1 should have:

- daily scheduled generation
- NASA APOD
- 4–8 RSS sources
- Wikipedia discovery
- simple scoring/filtering
- deduplication
- 6–8 daily cards
- archive
- responsive UI
- dark mode
- PWA manifest
- GitHub Pages deployment

Do not implement:

- accounts
- personalization UI
- databases
- machine learning
- LLM summaries
- browser extensions
- complex recommendation algorithms
- analytics
- social sharing
- comments

---

# 36. Quality requirements

Before considering the project finished, verify:

- GitHub Action succeeds from a clean checkout.
- The site works without a local development server.
- No browser console errors occur.
- Missing images do not break layout.
- Failed RSS feeds do not break generation.
- `today.json` is valid JSON.
- Duplicate URLs are avoided.
- The site works comfortably on a phone-sized viewport.
- Dark mode is readable.
- Every external article links back to its original publisher.
- No paid service or paid API is required.
- A fresh GitHub user can fork the repository, enable Pages, and obtain a working Morning site.

---

# 37. Content principle

When uncertain whether an item belongs in Morning, use this test:

> Would I be glad this was one of the first things I encountered after waking up?

The site does not have to be relentlessly cheerful.

Interesting, profound, strange, beautiful, intellectually demanding, and surprising are all appropriate.

But it should generally leave the reader more curious about the world rather than more alarmed by it.

---

# 38. Expected Codex output

Implement the entire working repository.

Do not merely describe the solution.

Create all necessary:

- Python scripts
- GitHub Actions workflow
- HTML
- CSS
- JavaScript
- manifest
- configuration
- sample/fallback data
- README

Run the scripts locally where possible and fix errors before finishing.

Use sensible public RSS/API endpoints and verify that the selected endpoints actually return usable data.

If a proposed source does not expose a reliable public feed, replace it with another high-quality source rather than adding brittle scraping.

At completion, report:

- files created
- content sources used
- how the selection algorithm works
- how to run locally
- how to enable GitHub Pages
- any optional GitHub Secrets
- any limitations

---

## Implementation note

Verify every RSS/API endpoint at implementation time rather than hard-coding URLs from this specification. Feeds change, while the architecture above does not depend on any particular publisher.
