"""Scraper and telemetry provider for venue foot traffic and busyness levels."""

import math
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import sqlite3

from src.engine.models import BusynessReading
from src.scraper.foot_traffic_client import FootTrafficClient

logger = logging.getLogger("PopularTimesScraper")


class PopularTimesScraper:
    """
    Retrieves normal and live busyness metrics for monitored venues.
    Integrates commercial Foot Traffic APIs (BestTime / Outscraper) and a deterministic,
    zero-RNG bimodal mathematical distribution model.
    """

    def __init__(
        self,
        db_path: str = "data/pizzameter.db",
        google_maps_config: Optional[Dict[str, Any]] = None
    ):
        self.db_path = db_path
        # Active scenario overrides for targeted simulation: venue_id or ticker -> live_busyness
        self.simulated_surges: Dict[str, int] = {}

        # Commercial Foot Traffic & Deterministic Client (BestTime / Outscraper)
        cfg = google_maps_config or {}
        self.gmaps_client = FootTrafficClient(
            provider=cfg.get("provider", "besttime"),
            api_key=cfg.get("api_key"),
            cache_ttl_sec=cfg.get("cache_ttl_sec", 1800),
            request_timeout_sec=cfg.get("request_timeout_sec", 8.0),
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
        """Queue a venue for non-blocking background foot traffic refresh."""
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
        """Perform telemetry check for a specific venue and update cache (invoked in worker)."""
        return self.gmaps_client.ping_venue(
            venue_id=venue_info["venue_id"],
            name=venue_info.get("name", ""),
            address=venue_info.get("address"),
            latitude=venue_info.get("latitude"),
            longitude=venue_info.get("longitude"),
            google_place_id=venue_info.get("google_place_id")
        )

    def get_baseline_curve(self, hour: int, day_of_week: int, venue_seed: int = 0) -> int:
        """
        Calculates expected normal busyness (0-100) via deterministic bimodal Gaussian mixture.
        Zero RNG utilized.
        """
        normal, _ = FootTrafficClient.calculate_deterministic_model(float(hour), day_of_week, venue_seed)
        return normal

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
        Executes commercial Foot Traffic API queries with zero-RNG deterministic fallback.
        """
        now = current_time or datetime.now()
        hour_float = now.hour + (now.minute / 60.0)
        day = now.weekday()
        venue_seed = sum(ord(c) for c in venue_id)

        # Baseline and live calculated deterministically (ZERO RNG)
        det_normal, det_live = FootTrafficClient.calculate_deterministic_model(hour_float, day, venue_seed)
        normal = det_normal
        live = det_live
        data_source = "deterministic_model"

        # 1. Check if an anomaly surge was injected on this ticker or venue (Scenario Priority)
        if ticker.upper() in self.simulated_surges:
            live = self.simulated_surges[ticker.upper()]
            data_source = "simulated_surge"
        elif venue_id in self.simulated_surges:
            live = self.simulated_surges[venue_id]
            data_source = "simulated_surge"
        else:
            # 2. Check if cached in Foot Traffic Client
            cached_reading = self.gmaps_client.get_cached_reading(venue_id) if self.gmaps_client.enabled else None

            # Optional immediate synchronous ping (e.g. for unit tests)
            if not cached_reading and live_ping and venue_name and self.gmaps_client.enabled:
                cached_reading = self.gmaps_client.ping_venue(
                    venue_id=venue_id,
                    name=venue_name,
                    address=venue_address,
                    latitude=latitude,
                    longitude=longitude,
                    google_place_id=google_place_id,
                    current_time=now
                )

            if cached_reading and cached_reading.get("live_busyness") is not None:
                live = cached_reading["live_busyness"]
                normal = cached_reading.get("normal_busyness", normal)
                data_source = cached_reading.get("source", "commercial_api")
            else:
                # Queue venue for background asynchronous foot traffic refresh if un-cached
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

        return BusynessReading(
            venue_id=venue_id,
            timestamp=now,
            day_of_week=day,
            hour_of_day=now.hour,
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
