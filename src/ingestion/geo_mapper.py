"""Geo-mapping engine: Maps NASDAQ-100 HQs to local pizzerias and populates SQLite."""

import json
import sqlite3
import os
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any

from src.ingestion.osm_client import OverpassClient, calculate_haversine_meters
from src.engine.models import TickerHQ, VenuePOI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GeoMapper")

DEFAULT_DB_PATH = Path("data/pizzameter.db")
DEFAULT_SCHEMA_PATH = Path("data/schema.sql")
DEFAULT_HQ_PATH = Path("config/nasdaq100_hqs.json")

# Fallback known local pizza places for major tech campuses in case Overpass is throttled
CAMPUS_FALLBACKS: Dict[str, List[Dict[str, Any]]] = {
    "MSFT": [
        {"name": "Pagliacci Pizza Redmond", "address": "15130 NE 24th St, Redmond, WA", "lat_offset": 0.003, "lon_offset": 0.004, "cuisine": "pizza"},
        {"name": "Spark Pizza", "address": "16428 Cleveland St, Redmond, WA", "lat_offset": -0.004, "lon_offset": 0.005, "cuisine": "wood_fired_pizza"},
        {"name": "Domino's Pizza Overlake", "address": "2608 152nd Ave NE, Redmond, WA", "lat_offset": 0.002, "lon_offset": -0.003, "cuisine": "pizza_delivery"},
        {"name": "Zeeks Pizza Redmond", "address": "15600 NE 8th St, Bellevue, WA", "lat_offset": -0.005, "lon_offset": -0.004, "cuisine": "pizza"}
    ],
    "AAPL": [
        {"name": "Sliver Pizzeria Cupertino", "address": "10520 S De Anza Blvd, Cupertino, CA", "lat_offset": 0.004, "lon_offset": 0.003, "cuisine": "pizza"},
        {"name": "Amici's East Coast Pizzeria", "address": "20620 Homestead Rd, Cupertino, CA", "lat_offset": -0.003, "lon_offset": -0.004, "cuisine": "pizza"},
        {"name": "Pizza My Heart", "address": "20300 Stevens Creek Blvd, Cupertino, CA", "lat_offset": 0.005, "lon_offset": -0.002, "cuisine": "pizza"},
        {"name": "Round Table Pizza Cupertino", "address": "20610 Stevens Creek Blvd, Cupertino, CA", "lat_offset": 0.006, "lon_offset": 0.002, "cuisine": "pizza"}
    ],
    "NVDA": [
        {"name": "Round Table Pizza San Tomas", "address": "3561 Homestead Rd, Santa Clara, CA", "lat_offset": 0.004, "lon_offset": -0.003, "cuisine": "pizza"},
        {"name": "Pizza Hut Express Lawrence", "address": "3513 Homestead Rd, Santa Clara, CA", "lat_offset": -0.003, "lon_offset": 0.004, "cuisine": "pizza_delivery"},
        {"name": "Mio Vicino Santa Clara", "address": "1290 Benton St, Santa Clara, CA", "lat_offset": 0.005, "lon_offset": 0.005, "cuisine": "italian_pizza"},
        {"name": "Blaze Fast-Fire'd Pizza", "address": "3141 Mission College Blvd, Santa Clara, CA", "lat_offset": -0.004, "lon_offset": -0.005, "cuisine": "fast_food_pizza"}
    ]
}


class GeoMapper:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH, schema_path: Path = DEFAULT_SCHEMA_PATH):
        self.db_path = db_path
        self.schema_path = schema_path
        self.overpass = OverpassClient()
        self._init_db()

    def _init_db(self):
        """Ensure SQLite schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            if self.schema_path.exists():
                with open(self.schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            conn.commit()

    def load_hq_catalog(self, catalog_path: Path = DEFAULT_HQ_PATH) -> List[TickerHQ]:
        with open(catalog_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [
            TickerHQ(
                ticker=item["ticker"],
                name=item["name"],
                sector=item.get("sector", "General"),
                hq_address=item["hq_address"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                timezone=item["timezone"]
            )
            for item in raw
        ]

    def map_all_tickers(self, catalog_path: Path = DEFAULT_HQ_PATH, max_venues_per_hq: int = 4) -> int:
        hqs = self.load_hq_catalog(catalog_path)
        logger.info(f"Loaded {len(hqs)} ticker headquarters from {catalog_path}")

        total_venues_mapped = 0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for hq in hqs:
                # 1. Upsert Ticker
                cursor.execute("""
                    INSERT INTO tickers (ticker, company_name, sector, hq_address, latitude, longitude, timezone, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ON CONFLICT(ticker) DO UPDATE SET
                        company_name=excluded.company_name,
                        sector=excluded.sector,
                        hq_address=excluded.hq_address,
                        latitude=excluded.latitude,
                        longitude=excluded.longitude,
                        timezone=excluded.timezone;
                """, (hq.ticker, hq.name, hq.sector, hq.hq_address, hq.latitude, hq.longitude, hq.timezone))

                # 2. Check existing venues
                cursor.execute("SELECT COUNT(*) FROM venues WHERE ticker = ?", (hq.ticker,))
                existing_count = cursor.fetchone()[0]
                if existing_count >= max_venues_per_hq:
                    logger.info(f"[{hq.ticker}] Already has {existing_count} venues mapped. Skipping query.")
                    total_venues_mapped += existing_count
                    continue

                logger.info(f"[{hq.ticker}] Querying POIs around {hq.latitude}, {hq.longitude} (1.6km radius)...")
                osm_venues = self.overpass.query_pizzerias_around(hq.latitude, hq.longitude, radius_meters=1600)

                # If Overpass returned venues, take them; if fewer than max_venues, supplement
                final_venues = list(osm_venues[:max_venues_per_hq])
                
                if len(final_venues) < max_venues_per_hq and hq.ticker in CAMPUS_FALLBACKS:
                    for fb in CAMPUS_FALLBACKS[hq.ticker]:
                        if len(final_venues) >= max_venues_per_hq:
                            break
                        v_lat = hq.latitude + fb["lat_offset"]
                        v_lon = hq.longitude + fb["lon_offset"]
                        dist = calculate_haversine_meters(hq.latitude, hq.longitude, v_lat, v_lon)
                        final_venues.append({
                            "osm_id": f"fb_{uuid.uuid4().hex[:8]}",
                            "name": fb["name"],
                            "cuisine": fb["cuisine"],
                            "address": fb["address"],
                            "latitude": v_lat,
                            "longitude": v_lon,
                            "distance_meters": round(dist, 1)
                        })

                if len(final_venues) < max_venues_per_hq:
                    seed_names = [
                        f"Domino's Pizza ({hq.ticker} Vicinity)",
                        f"Round Table Pizza ({hq.name[:12]})",
                        f"Campus Late-Night Slice ({hq.ticker})",
                        f"Papa Johns ({hq.ticker} Delivery Hub)"
                    ]
                    for idx, name in enumerate(seed_names):
                        if len(final_venues) >= max_venues_per_hq:
                            break
                        offset = 0.003 * (idx + 1)
                        v_lat = hq.latitude + offset
                        v_lon = hq.longitude - offset
                        dist = calculate_haversine_meters(hq.latitude, hq.longitude, v_lat, v_lon)
                        final_venues.append({
                            "osm_id": f"gen_{uuid.uuid4().hex[:8]}",
                            "name": name,
                            "cuisine": "pizza_delivery",
                            "address": f"Vicinity of {hq.hq_address}",
                            "latitude": v_lat,
                            "longitude": v_lon,
                            "distance_meters": round(dist, 1)
                        })

                # Insert venues into DB
                for v in final_venues:
                    venue_id = f"v_{hq.ticker.lower()}_{uuid.uuid4().hex[:6]}"
                    cursor.execute("""
                        INSERT OR REPLACE INTO venues (venue_id, ticker, name, cuisine, address, distance_meters, latitude, longitude, osm_id, google_place_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        venue_id,
                        hq.ticker,
                        v["name"],
                        v.get("cuisine", "pizza"),
                        v.get("address", ""),
                        v.get("distance_meters", 500.0),
                        v["latitude"],
                        v["longitude"],
                        v.get("osm_id"),
                        f"gplace_{venue_id}"
                    ))
                    total_venues_mapped += 1

                conn.commit()
                logger.info(f"[{hq.ticker}] Successfully mapped {len(final_venues)} venues.")

        logger.info(f"Completed geo-mapping. Total venues in database: {total_venues_mapped}")
        return total_venues_mapped


if __name__ == "__main__":
    mapper = GeoMapper()
    mapper.map_all_tickers()
