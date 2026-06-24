# My Book Scraper for NexMart

I created a Python web scraper built to extract book data from [books.toscrape.com](http://books.toscrape.com). It collects titles, prices, ratings, and URLs across all 50 pages of the catalogue and exports them to a CSV file.

This document walks through the HTML structure I observed, the field-level findings I hit during development, and the database schema and change detection design for a production-grade version of this system.

---

## What Gets Scraped

| Field | Source |
|---|---|
| Title | `title` attribute on the `<a>` tag inside each book card |
| URL | `href` attribute on the same `<a>` tag |
| Price | `.price_color` class inside `.product_price` |
| Rating | CSS class word on the `<p class="star-rating">` element |

---

## HTML Structure Observations

### Title, Price, and URL

The title lives inside an anchor (`<a>`) tag. The price is in a class called `product_price > price_color`. The URL comes from the `href` of that same anchor tag.

<img src="images/title_price_url.png" alt="HTML structure for title, price, and URL" />

### Rating

The rating sits on a `<p>` tag with the class `star-rating`. The actual star count is encoded as a second CSS class word like `Three` or `Five`. There is no numeric attribute to read directly, so it requires a mapping step.

<img src="images/rating.png" alt="HTML structure for rating" />

### Pagination

The pagination "next" button lives inside a `<li class="next">` element. The href is a relative URL that needs to be merged with the base URL to form a full address. Each page holds 20 books, and the scraper walks through all 50 pages sequentially to collect all 1000 records.

<img src="images/pagination.png" alt="HTML structure for pagination" />

---

## Field Observations

These are the non-obvious things I found while building the scraper. Most of them would have caused silent data corruption if I had not caught them.

### 1. The price field has an encoding artifact, not just a currency symbol

The raw HTML price sometimes looks like `Â£53.74` depending on how the page is decoded. The pound sign (`£`) is a multi-byte UTF-8 character that renders as `Â£` when decoded with the wrong encoding. Rather than stripping a known leading character like `£`, I stripped everything that is not a digit or decimal point. This handles both the clean and corrupted rendering without hardcoding any specific character, and it stays safe if other unexpected strings come through.

### 2. Book titles are truncated in the `<a>` tag text but the full title is in the `title` attribute

The visible link text for long titles gets cut off with `...` like `"A Light in the ..."`. The full title lives in the `title` attribute of the same `<a>` tag. Using `.text` instead of `["title"]` would have silently truncated roughly 30 to 40 book names. The CSV would look fine at a glance, but the data would be wrong.

<img src="images/probable_error.png" alt="Truncated title example showing the difference between visible text and the title attribute" />

### 3. Rating is encoded as a CSS class word, not a number

Star rating is stored as a class on the `<p>` element like `<p class="star-rating Three">`. There is no `data-rating` attribute or numeric value anywhere in the HTML. 
<img src="images/rating.png" alt="Rating structure showing the static nature" />

I mapped the word to an integer using a static dictionary called `RATING_MAP`. Books with missing or unrecognised ratings default to `0`. This would break silently if the site ever added a `"Six"` or `"Seven"` class since a value of `0` would appear in the output without raising an error. An alternative would be to raise an exception on unknown class values, but that would halt the entire scrape for one bad record. I chose the silent default with the expectation that a downstream schema constraint would catch it.

### 4. Relative URLs in pagination use `../` in deeper catalogue paths

On page 1, the "next" button href is `page-2.html`, relative to `BASE_URL`. On some other pages I noticed relative URLs with `../` prefixes. To handle this uniformly, I stripped all `../` segments before appending to `BASE_URL`. The cleaner approach would be `urllib.parse.urljoin`, which I considered but skipped to avoid over-engineering a site with a predictable and stable URL structure.

### 5. I chose `requests` and `BeautifulSoup` over Scrapy intentionally

Scrapy adds a full framework: spiders, pipelines, settings, and middlewares. For a 50-page linear crawl with no JavaScript rendering, that would be roughly four times more code for the same output. I added a `0.5s` delay between requests manually to be polite to the server. The trade-offs are no built-in rate limiting, no distributed crawl support, and no automatic retry queue. For this scope, those are acceptable gaps.

---

## Database Design

Books on the site are divided into categories, with multiple books falling under each one.

<img src="images/categories.png" alt="Book categories shown on the site" />

### Diagram 1: Normalized Relational Schema (ERD)

```mermaid
erDiagram
    SCRAPE_RUNS {
        int     id          PK
        datetime run_at
        int     books_found
        string  status
    }

    CATEGORIES {
        int     id          PK
        string  name        UK
    }

    BOOKS {
        int     id          PK
        string  url         UK
        string  title
        int     rating
        int     category_id FK
        bool    is_active
        datetime last_seen
    }

    PRICE_HISTORY {
        int     id          PK
        int     book_id     FK
        int     run_id      FK
        decimal price
        datetime recorded_at
    }

    BOOKS }o--|| CATEGORIES : "belongs to"
    BOOKS ||--o{ PRICE_HISTORY : "has"
    PRICE_HISTORY }o--|| SCRAPE_RUNS : "captured in"
```

### Key Design Decisions

| Decision | Reasoning |
|---|---|
| `books` is the core entity | Each row is one catalogue entry identified by a stable `url`, which the site uses as the canonical ID per book. All other tables reference it. |
| `url` as natural unique key on `books` | The URL encodes a slug that never changes for a given book on this site. More readable than a surrogate key when debugging. Example: `/scott-pilgrims-precious-little-life-scott-pilgrim-1_987` |
| Price lives in `price_history`, not `books` | Keeps the full historical record intact. Current price is just the latest row for that `book_id`. No data is lost when a price changes. This is the mechanism for change detection shown in Diagram 2. |
| `rating` on `books`, not in history | Rating on this site appears editorial and static. If it ever changed, the change detection flow in Diagram 2 would catch it and we could promote rating to a history table at that point. |
| `is_active` flag on `books` | Soft-delete approach: when a book disappears from the catalogue we set `is_active = false` and note `last_seen`. Hard deletes would break the price history foreign key chain. |
| `categories` normalised out | Storing category as a raw string on `books` would repeat `"Mystery"` hundreds of times across rows. Instead, `categories` holds each name exactly once and `books` references it via `category_id`. Two concrete benefits: a typo like `"Mysetery"` cannot silently create a phantom category since the FK constraint rejects unknown values, and aggregations like counting books per category work correctly because every book in a category points to the same row, not a loose string. The trade-off is one extra JOIN, which is negligible at this scale. Note: the current scraper does not collect category data, but the product page exposes it and the schema is ready for it. |
| `scrape_runs` as audit log | Every run records timestamp, count, and status. This makes diffs possible since change detection compares run N against run N-1. If a run fails mid-way, `status` reflects it and downstream consumers can skip that run's data entirely. |

### Diagram 2: Data Change Detection

```mermaid
flowchart TD
    A([Scheduler\nCron / Airflow / Prefect]) --> B[Run scraper.py\nFetch all 1000 records]
    B --> C[Write to staging table\nscrape_staging]

    C --> D{Compare staging\nvs books table}

    D --> E[New URLs in staging\nnot in books]
    D --> F[URLs in both\ncheck price + rating]
    D --> G[URLs in books\nnot in staging]

    E --> E1[INSERT into books\nis_active = true\nfirst_seen = now]
    E1 --> E2[INSERT into price_history\nrun_id = current run]

    F --> F1{Price changed?}
    F1 -->|Yes| F2[INSERT into price_history\nnew price row]
    F1 -->|No| F3[No action\nprice unchanged]

    F --> F4{Rating changed?}
    F4 -->|Yes| F5[UPDATE books.rating\nlog change in scrape_runs]
    F4 -->|No| F6[No action]

    G --> G1[UPDATE books\nis_active = false\nlast_seen = now]

    E2 & F2 & F3 & F5 & F6 & G1 --> H[Update scrape_runs\nstatus = complete\nbooks_found = N]

    H --> I([Done])
```

### Component Notes

| Component | Purpose |
|---|---|
| `scrape_staging` | Temporary table holding the latest raw scrape. Wiped and reloaded each run. Prevents partial writes from corrupting the live `books` table. |
| Diff logic (D to E/F/G) | Three-way comparison: new arrivals, existing books to check for changes, and books that have disappeared. Each branch is independent, so a price change does not affect removal detection. |
| `scrape_runs` log | Every run records timestamp, count, and status. This is the audit trail. If a run fails mid-way, the `status` column reflects it and downstream consumers can skip that run's data. |
| Soft delete (`is_active`) | Books that vanish from the catalogue are marked inactive, not deleted. `last_seen` tells you exactly when they disappeared. Price history is fully preserved for trend analysis. |
| Scheduler | Any cron-compatible tool works here. Daily frequency is sufficient for a slow-changing book catalogue. The design supports higher frequency without any changes to the schema. |

---

## Summary

### Schema (ERD)

The normalized schema has 4 tables:

- `books` -- one row per unique book, identified by URL
- `categories` -- normalised out to avoid string repetition across rows
- `price_history` -- every price observation, linked to a specific scrape run
- `scrape_runs` -- audit log of every execution

Current price is the latest `price_history` row for a given `book_id`. Books that disappear from the site are soft-deleted with `is_active = false`, which preserves all historical pricing data.

### Change Detection

Each run writes to a `scrape_staging` table first. A diff then classifies every record into one of three buckets:

- **New URL** -- insert into `books`, log the first price in `price_history`
- **Existing URL, price changed** -- insert a new `price_history` row
- **Existing URL, gone from site** -- set `is_active = false`, record `last_seen`

The `scrape_runs` table ties every price snapshot to the exact run that captured it, making the full history traceable and auditable.
