# Diagram 2 — Data Change Detection System

```mermaid
flowchart TD
    A([Scheduler\nCron / Airflow/ Prefect]) --> B[Run scraper.py\nFetch all 1000 records]
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

## Design Notes

| Component | Purpose |
|---|---|
| `scrape_staging` | Temporary table holding the latest raw scrape. Wiped and reloaded each run. Prevents partial writes from corrupting the live `books` table. |
| Diff logic (D → E/F/G) | Three-way comparison: new arrivals, existing books to check for mutations, and disappearances. Each branch is independent and a price change does not affect removal detection. |
| `scrape_runs` log | Every run records timestamp, count, and status. This is the audit trail. If a run fails mid-way, the `status` column reflects it and downstream consumers can skip that run's data. |
| Soft delete (`is_active`) | Books that vanish from the catalogue are marked inactive, not deleted. `last_seen` tells you when they disappeared. Price history is preserved for trend analysis. |
| Scheduler | Any cron-compatible tool works. Daily frequency is sufficient for a slow-changing book catalogue. The design supports higher frequency without changes. |

