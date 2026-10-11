"""Institutional Foot Traffic and Popular Times Telemetry Provider.

Supports:
1. BestTime.app API for official Google Maps Popular Times and real-time live occupancy.
2. Outscraper API for commercial Google Maps Popular Times extraction.
3. Deterministic zero-RNG quantitative model based on bimodal Gaussian foot traffic distributions.
4. Intelligent TTL caching to prevent rate-limits and optimize external API quotas.
"""

import os
import math
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import requests

logger = logging.getLogger("FootTrafficClient")


class FootTrafficClient:
    """
    Commercial foot-traffic provider integrating BestTime.app and Outscraper APIs,
    with an analytical, zero-RNG deterministic fallback model to avoid IP throttling.
    """

    def __init__(
        self,
        provider: str = "besttime",
        api_key: Optional[str] = None,
        cache_ttl_sec: int = 1800,
        request_timeout_sec: float = 8.0,
        enabled: bool = True
    ):
        self.provider = provider.lower()
        self.api_key = (
            api_key
            or os.environ.get("BESTTIME_API_KEY")
            or os.environ.get("OUTSCRAPER_API_KEY")
            or os.environ.get("GOOGLE_MAPS_API_KEY")
        )
        self.cache_ttl_sec = cache_ttl_sec
        self.request_timeout_sec = request_timeout_sec
        self.enabled = enabled

        # In-memory venue cache: venue_id -> {"timestamp": datetime, "reading": dict}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._session = requests.Session()

    def get_cached_reading(self, venue_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached reading if still within TTL."""
        entry = self._cache.get(venue_id)
        if not entry:
            return None

        cached_time = entry.get("timestamp")
        if not cached_time:
            return None

        if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl_sec):
            reading = dict(entry["reading"])
            reading["source"] = f"{reading.get('source', 'foot_traffic')}_cache"
            return reading

        return None

    def cache_reading(self, venue_id: str, reading: Dict[str, Any]):
        """Persist reading to in-memory TTL cache."""
        self._cache[venue_id] = {
            "timestamp": datetime.now(),
            "reading": reading
        }

    @staticmethod
    def calculate_deterministic_model(
        hour_float: float,
        day_of_week: int,
        venue_seed: int = 0
    ) -> Tuple[int, int]:
        """
        Pure mathematical, deterministic foot traffic distribution with ZERO RNG.
        Employs a bimodal Gaussian mixture model calibrated to restaurant rush hours:
        - Lunch Peak: mu=12.5h (12:30), sigma=1.1, amplitude=68%
        - Dinner Peak: mu=19.0h (weekdays) or 20.0h (weekends), sigma=1.5, amplitude=75-82%
        - Night Baseline: 6-8%
        - Micro-variance: Continuous sinusoidal harmonic offset tied deterministically to venue_seed.
        """
        is_weekend = day_of_week in [4, 5]  # Friday, Saturday

        # Lunch Gaussian peak (12:30)
        lunch_amp = 68.0
        lunch = lunch_amp * math.exp(-((hour_float - 12.5) ** 2) / (2 * (1.1 ** 2)))

        # Dinner Gaussian peak (19:00 on weekdays, 20:00 on weekends)
        dinner_mu = 20.0 if is_weekend else 19.0
        dinner_amp = 82.0 if is_weekend else 74.0
        dinner = dinner_amp * math.exp(-((hour_float - dinner_mu) ** 2) / (2 * (1.5 ** 2)))

        # Base late-night background foot traffic
        base = 8.0 if is_weekend else 6.0
        normal = int(round(base + lunch + dinner))
        normal = max(5, min(100, normal))

        # Deterministic micro-variance using harmonic trigonometry (ZERO RNG)
        var = int(round(
            4.5 * math.sin(venue_seed * 0.15 + hour_float * 1.7) +
            2.0 * math.cos(venue_seed * 0.08 + hour_float * 0.8)
        ))
        live = max(5, min(100, normal + var))

        return normal, live

    def query_besttime_api(
        self,
        name: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Query BestTime.app API for commercial Google Maps Popular Times & Live Busyness.
        Returns live busyness and normal hourly baseline if available.
        """
        if not self.api_key:
            return None

        url = "https://besttime.app/api/v1/venues"
        params = {
            "api_key_private": self.api_key,
            "venue_name": name,
            "venue_address": address or f"{latitude},{longitude}"
        }

        try:
            resp = self._session.post(url, params=params, timeout=self.request_timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "OK":
                    live_data = data.get("venue_live_busyness", {})
                    live_val = live_data.get("busyness")
                    analysis = data.get("analysis", {})
                    day_raw = analysis.get("day_raw", [])
                    return {
                        "live_busyness": live_val,
                        "day_raw": day_raw,
                        "source": "besttime_live",
                        "status": live_data.get("status")
                    }
            elif resp.status_code in [401, 403]:
                logger.warning("BestTime API key invalid or unauthorized.")
            elif resp.status_code == 429:
                logger.warning("BestTime API quota exceeded (HTTP 429).")
        except Exception as e:
            logger.debug(f"Error querying BestTime API for {name}: {e}")

        return None

    def query_outscraper_api(
        self,
        name: str,
        address: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Query Outscraper API for Google Maps Popular Times."""
        if not self.api_key:
            return None

        url = "https://api.app.outscraper.com/maps/popular-times"
        headers = {"X-API-KEY": self.api_key}
        params = {"query": f"{name} {address or ''}".strip(), "async": "false"}

        try:
            resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("data", [])
                if results and len(results) > 0:
                    pop_data = results[0].get("popular_times", {})
                    live_val = pop_data.get("live_popularity")
                    return {
                        "live_busyness": live_val,
                        "source": "outscraper_live"
                    }
        except Exception as e:
            logger.debug(f"Error querying Outscraper API for {name}: {e}")

        return None

    def ping_venue(
        self,
        venue_id: str,
        name: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        google_place_id: Optional[str] = None,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Execute telemetry retrieval for a venue:
        1. Check memory TTL cache.
        2. Query commercial API (BestTime / Outscraper) if api_key is configured.
        3. If no API key or API call fails: evaluate zero-RNG deterministic model.
        """
        now = current_time or datetime.now()
        hour_float = now.hour + (now.minute / 60.0)
        day_of_week = now.weekday()

        # Deterministic seed from venue_id string
        seed = sum(ord(c) for c in venue_id)

        # 1. Check TTL cache
        cached = self.get_cached_reading(venue_id)
        if cached:
            return cached

        # 2. Commercial API integration (BestTime / Outscraper)
        api_result = None
        if self.enabled and self.api_key:
            if self.provider == "besttime" or "besttime" in (self.api_key or ""):
                api_result = self.query_besttime_api(name, address, latitude, longitude)
            elif self.provider == "outscraper":
                api_result = self.query_outscraper_api(name, address)

        if api_result and api_result.get("live_busyness") is not None:
            # Baseline from API day_raw if present, else deterministic model
            normal, _ = self.calculate_deterministic_model(hour_float, day_of_week, seed)
            if api_result.get("day_raw") and len(api_result["day_raw"]) > now.hour:
                normal = api_result["day_raw"][now.hour]

            result = {
                "source": api_result.get("source", "commercial_api"),
                "live_busyness": api_result["live_busyness"],
                "normal_busyness": normal,
                "google_place_id": google_place_id,
                "timestamp": now
            }
            self.cache_reading(venue_id, result)
            return result

        # 3. Deterministic Zero-RNG Quantitative Model
        normal, live = self.calculate_deterministic_model(hour_float, day_of_week, seed)

        result = {
            "source": "deterministic_model",
            "live_busyness": live,
            "normal_busyness": normal,
            "google_place_id": google_place_id,
            "timestamp": now
        }
        self.cache_reading(venue_id, result)
        return result


# Maintain backward compatibility alias for GoogleMapsClient
GoogleMapsClient = FootTrafficClient
