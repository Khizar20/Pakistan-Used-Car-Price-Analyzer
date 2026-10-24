-- Schema version 1. Timestamps are canonical UTC ISO strings, including offsets.
CREATE TABLE scrape_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    scope_key TEXT,
    scope_pages JSON NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    pages_fetched INTEGER NOT NULL DEFAULT 0 CHECK (pages_fetched >= 0),
    listings_seen INTEGER NOT NULL DEFAULT 0 CHECK (listings_seen >= 0),
    errors INTEGER NOT NULL DEFAULT 0 CHECK (errors >= 0),
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'partial', 'failed', 'interrupted')),
    error_summary TEXT
);
CREATE UNIQUE INDEX ux_running_scrape ON scrape_runs(status) WHERE status = 'running';
CREATE TABLE listings (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_listing_id TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    is_active BOOLEAN NOT NULL CHECK (is_active IN (0, 1)),
    disappeared_at TEXT,
    last_scope_key TEXT NOT NULL,
    last_seen_run_id INTEGER NOT NULL REFERENCES scrape_runs(id),
    consecutive_misses INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_misses >= 0),
    last_absent_date TEXT,
    make TEXT,
    model TEXT,
    variant TEXT,
    model_year INTEGER CHECK (model_year BETWEEN 1900 AND 2100),
    mileage_km INTEGER CHECK (mileage_km >= 0),
    engine_cc INTEGER CHECK (engine_cc >= 0),
    transmission TEXT,
    fuel_type TEXT,
    body_type TEXT,
    assembly TEXT,
    color TEXT,
    city TEXT,
    registered_city TEXT,
    seller_type TEXT,
    is_featured BOOLEAN,
    has_photos_count INTEGER CHECK (has_photos_count >= 0),
    features JSON,
    quality_flag JSON NOT NULL,
    duplicate_of TEXT,
    UNIQUE (source, source_listing_id)
);
CREATE INDEX ix_listings_cohort ON listings(make, model, model_year);
CREATE INDEX ix_listings_source_id ON listings(source_listing_id);
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY,
    listing_id INTEGER NOT NULL REFERENCES listings(id),
    observed_at TEXT NOT NULL,
    observed_date TEXT NOT NULL,
    price_pkr INTEGER CHECK (price_pkr >= 0),
    is_active BOOLEAN NOT NULL CHECK (is_active IN (0, 1)),
    scrape_run_id INTEGER NOT NULL REFERENCES scrape_runs(id),
    quality_flag JSON NOT NULL,
    UNIQUE (listing_id, observed_date)
);
CREATE INDEX ix_snapshots_listing_observed ON snapshots(listing_id, observed_at);
