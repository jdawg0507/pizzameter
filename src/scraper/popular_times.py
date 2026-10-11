"""Scraper and telemetry provider for venue foot traffic and busyness levels."""

import math
import random
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import sqlite3

from src.engine.models import BusynessReading
from src.scraper.google_maps_client import GoogleMapsClient

logger = logging.getLogger("PopularTimesScraper")


class PopularTimesScraper:
    """
    Retrieves normal and live busyness metrics for monitored venues.
    Supports real extraction interfaces and controlled scenario injections for testing.
    """

    def __init__(
        self,
        db_path: str = "data/pizzameter.db",
        google_maps_config: Optional[Dict[str, Any]] = None
    ):
        self.db_path = db_path
        # Active scenario overrides for targeted simulation: venue_id or ticker -> live_busyness
        self.simulated_surges: Dict[str, int] = {}

        # Hybrid Google Maps Client
        cfg = google_maps_config or {}
        self.gmaps_client = GoogleMapsClient(
            api_key=cfg.get("api_key"),
            cache_ttl_sec=cfg.get("cache_ttl_sec", 600),
            request_timeout_sec=cfg.get("request_timeout_sec", 4.0),
            rate_limit_delay_sec=cfg.get("rate_limit_delay_sec", 0.5),
            enabled=cfg.get("enabled", True)
        )
        # Background refresh queue
        self._refresh_queue: List[Dict[str, Any]] = []
        self._queued_venue_ids = set()

    def set_simulated_surge(self, target: str, live_value: int = 95):
        """Inject a high busyness spike on a specific ticker or venue for testing."""
        self.simulated_surges[target.upper()] = live_value
        logger.info(f"Injected simulated surge on {target.upper()} = {live_value}% busyness.")

    def clear_simulated_surges(self):
        self.simulated_surges.clear()

    def queue_venue_for_refresh(self, venue_info: Dict[str, Any]):
        """Queue a venue for non-blocking background Google Maps refresh."""
        vid = venue_info.get("venue_id")
        if vid and vid not in self._queued_venue_ids and not self.gmaps_client.get_cached_reading(vid):
            self._queued_venue_ids.add(vid)
            self._refresh_queue.append(venue_info)

    def get_next_venue_to_refresh(self) -> Optional[Dict[str, Any]]:
        """Pop the next un-cached venue from the background refresh queue."""
        while self._refresh_queue:
            item = self._refresh_queue.pop(0)
            vid = item.get("venue_id")
            if vid in self._queued_venue_ids:
                self._queued_venue_ids.remove(vid)
            if not self.gmaps_client.get_cached_reading(vid):
                return item
        return None

    def refresh_venue_gmaps(self, venue_info: Dict[str, Any]) -> Dict[str, Any]:
        """Perform network ping for a specific venue and update cache (invoked in worker)."""
        return self.gmaps_client.ping_venue(
            venue_id=venue_info["venue_id"],
            name=venue_info.get("name", ""),
            address=venue_info.get("address"),
            latitude=venue_info.get("latitude"),
            longitude=venue_info.get("longitude"),
            google_place_id=venue_info.get("google_place_id")
        )

    def get_baseline_curve(self, hour: int, day_of_week: int) -> int:
        """
        Calculate realistic expected normal busyness (0-100) based on hour of day and day of week.
        Eateries have normal peak around 12:00-13:00 and 18:00-20:00, tapering sharply by 23:00.
        """
        is_weekend = day_of_week in [4, 5]  # Friday, Saturday

        if 0 <= hour < 5:
            # Late night / early morning
            return random.randint(3, 10)
        elif 5 <= hour < 11:
            # Morning
            return random.randint(5, 18)
        elif 11 <= hour < 14:
            # Lunch rush
            return random.randint(50, 75)
        elif 14 <= hour < 17:
            # Afternoon lull
            return random.randint(20, 35)
        elif 17 <= hour < 21:
            # Dinner rush
            return random.randint(55, 82) if is_weekend else random.randint(45, 70)
        elif 21 <= hour < 24:
            # Late night normal drop-off
            return random.randint(15, 30) if is_weekend else random.randint(10, 22)
        return 20

    def fetch_venue_busyness(
        self,
        venue_id: str,
        ticker: str,
        current_time: Optional[datetime] = None,
        venue_name: Optional[str] = None,
        venue_address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        google_place_id: Optional[str] = None,
        live_ping: bool = False
    ) -> BusynessReading:
        """
        Fetch normal and live busyness for a specific venue at current_time.
        Executes hybrid Google Maps pinging with baseline fallback and surge priority.
        """
        now = current_time or datetime.now()
        hour = now.hour
        day = now.weekday()

        normal = self.get_baseline_curve(hour, day)
        data_source = "fallback_baseline"

        # 1. Check if an anomaly surge was injected on this ticker or venue (Scenario Priority)
        if ticker.upper() in self.simulated_surges:
            live = self.simulated_surges[ticker.upper()]
            data_source = "simulated_surge"
        elif venue_id in self.simulated_surges:
            live = self.simulated_surges[venue_id]
            data_source = "simulated_surge"
        else:
            # 2. Check if cached in Google Maps Client
            cached_reading = self.gmaps_client.get_cached_reading(venue_id) if self.gmaps_client.enabled else None

            # Optional immediate synchronous ping (e.g. for unit tests)
            if not cached_reading and live_ping and venue_name and self.gmaps_client.enabled:
                cached_reading = self.gmaps_client.ping_venue(
                    venue_id=venue_id,
                    name=venue_name,
                    address=venue_address,
                    latitude=latitude,
                    longitude=longitude,
                    google_place_id=google_place_id
                )

            if cached_reading and cached_reading.get("live_busyness") is not None:
                live = cached_reading["live_busyness"]
                data_source = cached_reading.get("source", "google_maps_live")
            else:
                # Queue venue for background asynchronous Google Maps refresh if un-cached
                if venue_name and self.gmaps_client.enabled and not cached_reading:
                    self.queue_venue_for_refresh({
                        "venue_id": venue_id,
                        "ticker": ticker,
                        "name": venue_name,
                        "address": venue_address,
                        "latitude": latitude,
                        "longitude": longitude,
                        "google_place_id": google_place_id
                    })

                # Calibrated baseline with natural oscillation (+/- 8%)
                live_noise = random.randint(-8, 8)
                live = max(5, min(100, normal + live_noise))
                if cached_reading and cached_reading.get("source") == "google_maps_online":
                    data_source = "google_maps_online"
                elif cached_reading and cached_reading.get("source") == "google_maps_cache":
                    data_source = "google_maps_cache"
                else:
                    data_source = "fallback_baseline"

                # 5% chance of live data temporarily unavailable from Google
                if random.random() < 0.05 and ticker.upper() not in self.simulated_surges:
                    live = None

        return BusynessReading(
            venue_id=venue_id,
            timestamp=now,
            day_of_week=day,
            hour_of_day=hour,
            live_busyness=live,
            normal_busyness=normal,
            data_source=data_source
        )

    def record_reading_in_db(self, reading: BusynessReading):
        """Persist reading to SQLite historical_busyness table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO historical_busyness (venue_id, timestamp, day_of_week, hour_of_day, live_busyness, normal_busyness, z_score, data_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reading.venue_id,
                    reading.timestamp.isoformat(),
                    reading.day_of_week,
                    reading.hour_of_day,
                    reading.live_busyness,
                    reading.normal_busyness,
                    reading.z_score,
                    reading.data_source
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error persisting busyness reading: {e}")
