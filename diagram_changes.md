### Diagram 2: Data Change Detection


```mermaid
flowchart TD
    A([Scheduler\nCron / Airflow / Prefect]) --> B[Run scraper.py\nFetch all 1000 records]
    B --> C[Write to staging table\nscrape_staging]

    C --> D{Compare staging\nvs books table}

    D --> E[New URLs in staging\nnot in books]
    D --> F[URLs in both\ncheck price + rating]
    D --> G[URLs in books\nnot in staging]

    E --> E1[INSERT into books\nis_active = true\ninserted_at = now]
    E1 --> E2[INSERT into price_history]

    F --> F1{Price changed?}
    F1 -->|Yes| F2[INSERT into price_history \n Update the latest row's effective_to = now]
    F1 -->|No| F3[No action]

    F --> F4{Rating changed?}
    F4 -->|Yes| F5[INSERT into rating_history\n Update the latest row's effective_to = now]
    F4 -->|No| F6[No action]

    G --> G1[UPDATE books\nis_active = false\nupdated_at = now]

    E2 & F2 & F3 & F5 & F6 & G1 --> I([Done])
```

### Key Design Decision

| Decision                 | Reasoning                                                                                                                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `scrape_staging`          | Temporary table holding the latest raw scrape. Wiped and reloaded each run. Prevents partial writes from corrupting the live `books` table.                                                |
| Diff logic (D to E/F/G)   | Three-way comparison: new arrivals, existing books to check for changes, and books that have disappeared. Each branch is independent, so a price change does not affect removal detection. |
| Soft delete (`is_active`) | Books that vanish from the catalogue are marked inactive, not deleted. `last_seen` tells us exactly when they disappeared. Price history is fully preserved for trend analysis.           |
| Scheduler                 | Any cron-compatible tool works here. Daily frequency is sufficient for a slow-changing book catalogue. The design supports higher frequency without any changes to the schema.             |
