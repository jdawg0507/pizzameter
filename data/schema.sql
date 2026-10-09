-- SQLite Database Schema for PizzaMeter

CREATE TABLE IF NOT EXISTS tickers (
    ticker TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    sector TEXT,
    hq_address TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT NOT NULL,
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS venues (
    venue_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    cuisine TEXT,
    address TEXT,
    distance_meters REAL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    osm_id TEXT,
    google_place_id TEXT,
    FOREIGN KEY(ticker) REFERENCES tickers(ticker)
);

CREATE TABLE IF NOT EXISTS historical_busyness (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venue_id TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    day_of_week INTEGER NOT NULL,  -- 0=Monday, 6=Sunday
    hour_of_day INTEGER NOT NULL,  -- 0-23
    live_busyness INTEGER,
    normal_busyness INTEGER,
    z_score REAL,
    FOREIGN KEY(venue_id) REFERENCES venues(venue_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    cluster_z_score REAL NOT NULL,
    reporting_venues INTEGER NOT NULL,
    fdc3_payload TEXT NOT NULL,
    cdm_payload TEXT NOT NULL,
    executed INTEGER DEFAULT 0,
    order_id TEXT,
    FOREIGN KEY(ticker) REFERENCES tickers(ticker)
);

CREATE INDEX IF NOT EXISTS idx_busyness_venue_time ON historical_busyness(venue_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker, timestamp);
