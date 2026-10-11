"""Google Maps live telemetry and popular times pinging client.

Provides a hybrid ingestion interface:
1. Direct Google Maps HTTP pinging for place metadata, business status, and live popular times.
2. Official Google Places API integration if GOOGLE_MAPS_API_KEY is configured.
3. High-throughput TTL caching and rate limiting to prevent IP throttling.
4. Resilient statistical fallback to baseline distribution when Google Maps data is unavailable.
"""

import os
import re
import json
import time
import urllib.parse
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
import requests

logger = logging.getLogger("GoogleMapsClient")


class GoogleMapsClient:
    """
    Hybrid client for pinging Google Maps live busyness and popular times.
    Supports official Google Places API and direct web/mobile response parsing,
    with smart TTL caching and resilient statistical fallback.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl_sec: int = 600,
        request_timeout_sec: float = 4.0,
        rate_limit_delay_sec: float = 0.5,
        enabled: bool = True
    ):
        self.enabled = enabled
        self.api_key = api_key or os.environ.get("GOOGLE_MAPS_API_KEY")
        self.cache_ttl_sec = cache_ttl_sec
        self.request_timeout_sec = request_timeout_sec
        self.rate_limit_delay_sec = rate_limit_delay_sec

        # In-memory venue cache: venue_id -> {"timestamp": datetime, "reading": dict}
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_request_time: float = 0.0

        # Session with realistic browser headers for web pinging
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        })

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
            reading["source"] = "google_maps_cache"
            return reading

        return None

    def cache_reading(self, venue_id: str, reading: Dict[str, Any]):
        """Persist reading to in-memory TTL cache."""
        self._cache[venue_id] = {
            "timestamp": datetime.now(),
            "reading": reading
        }

    def _apply_rate_limit(self):
        """Enforce spacing between live HTTP requests to avoid rate limiting."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay_sec:
            time.sleep(self.rate_limit_delay_sec - elapsed)
        self._last_request_time = time.time()

    def query_places_api(
        self,
        name: str,
        address: Optional[str] = None,
        google_place_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Query official Google Places API if api_key is present.
        Fetches operational status, rating, place_id, and open/closed details.
        """
        if not self.api_key:
            return None

        self._apply_rate_limit()

        try:
            if google_place_id and not google_place_id.startswith("gplace_"):
                # Use Place Details API
                url = (
                    f"https://maps.googleapis.com/maps/api/place/details/json"
                    f"?place_id={google_place_id}"
                    f"&fields=place_id,name,business_status,rating,user_ratings_total,opening_hours"
                    f"&key={self.api_key}"
                )
            else:
                # Use Find Place from Text
                query = f"{name} {address or ''}".strip()
                url = (
                    f"https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
                    f"?input={urllib.parse.quote(query)}"
                    f"&inputtype=textquery"
                    f"&fields=place_id,name,formatted_address,geometry,business_status,rating,user_ratings_total,opening_hours"
                    f"&key={self.api_key}"
                )

            resp = self._session.get(url, timeout=self.request_timeout_sec)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result") or (data.get("candidates") and data["candidates"][0])
                if result:
                    return {
                        "place_id": result.get("place_id"),
                        "business_status": result.get("business_status", "OPERATIONAL"),
                        "rating": result.get("rating"),
                        "user_ratings_total": result.get("user_ratings_total"),
                        "is_open": result.get("opening_hours", {}).get("open_now")
                    }
            elif resp.status_code == 429:
                logger.warning("Google Places API rate limit reached (HTTP 429).")
        except Exception as e:
            logger.debug(f"Error querying Google Places API for {name}: {e}")

        return None

    def parse_live_busyness_from_html(self, html_text: str) -> Optional[int]:
        """
        Extract live busyness level (0-100) from Google Maps HTML/JS payload.
        Inspects live aria labels, structured busyness regex patterns, and embedded arrays.
        """
        # Pattern 1: Aria label or text e.g. "Currently 78% busy" or "Usually 50% busy"
        match_busy = re.search(r'Currently\s+(\d{1,3})%\s*busy', html_text, re.IGNORECASE)
        if match_busy:
            val = int(match_busy.group(1))
            return max(0, min(100, val))

        # Pattern 2: "(\d{1,3})% as busy as it gets"
        match_as_busy = re.search(r'(\d{1,3})%\s*as\s+busy\s+as', html_text, re.IGNORECASE)
        if match_as_busy:
            val = int(match_as_busy.group(1))
            return max(0, min(100, val))

        # Pattern 3: Live popularity json pattern: ["current_popularity", 82] or [null,null,82]
        match_json = re.search(r'\[null,\s*null,\s*(\d{1,3})\]', html_text)
        if match_json:
            val = int(match_json.group(1))
            if 0 <= val <= 100:
                return val

        # Pattern 4: Busyness indicator in APP_INITIALIZATION_STATE
        init_match = re.search(r'window\.APP_INITIALIZATION_STATE\s*=\s*(\[.*?\]);', html_text)
        if init_match:
            try:
                # Search within init state snippet for percentage pattern
                raw_chunk = init_match.group(1)
                sub_match = re.search(r'\"Currently\s+(\d{1,3})%\"', raw_chunk)
                if sub_match:
                    return int(sub_match.group(1))
            except Exception:
                pass

        return None

    def ping_google_maps_web(
        self,
        name: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a live HTTP ping against Google Maps search endpoint for the venue.
        Returns live busyness and parsed metadata if available.
        """
        self._apply_rate_limit()

        query_parts = [name]
        if address:
            query_parts.append(address)
        query = " ".join(query_parts)

        url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(query)}"

        try:
            resp = self._session.get(url, timeout=self.request_timeout_sec)
            if resp.status_code == 200:
                live_val = self.parse_live_busyness_from_html(resp.text)

                # Extract real Google Place ID if present in HTML
                place_id_match = re.search(r'ChIJ[a-zA-Z0-9_\-]{20,}', resp.text)
                found_place_id = place_id_match.group(0) if place_id_match else None

                return {
                    "live_busyness": live_val,
                    "google_place_id": found_place_id,
                    "http_status": 200,
                    "has_live_data": (live_val is not None)
                }
            elif resp.status_code == 429:
                logger.warning(f"Google Maps HTTP rate limit (429) for venue: {name}")
                return {"http_status": 429, "rate_limited": True}
        except requests.exceptions.Timeout:
            logger.debug(f"Google Maps request timed out ({self.request_timeout_sec}s) for {name}")
        except Exception as e:
            logger.debug(f"Error pinging Google Maps for {name}: {e}")

        return None

    def ping_venue(
        self,
        venue_id: str,
        name: str,
        address: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        google_place_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute full hybrid ping workflow for a specific venue:
        1. Check TTL cache
        2. Query Places API if key exists
        3. Query Google Maps web search
        4. Populate cache
        """
        if not self.enabled:
            return {
                "source": "disabled",
                "live_busyness": None,
                "google_place_id": google_place_id
            }

        # 1. Check TTL Cache
        cached = self.get_cached_reading(venue_id)
        if cached:
            return cached

        # 2. Places API (if key available)
        resolved_place_id = google_place_id
        places_data = self.query_places_api(name, address, google_place_id)
        if places_data and places_data.get("place_id"):
            resolved_place_id = places_data["place_id"]

        # 3. Direct Google Maps HTTP ping
        web_data = self.ping_google_maps_web(name, address, latitude, longitude)

        live_val = None
        source = "fallback_baseline"

        if web_data:
            if web_data.get("google_place_id") and not resolved_place_id:
                resolved_place_id = web_data["google_place_id"]

            if web_data.get("live_busyness") is not None:
                live_val = web_data["live_busyness"]
                source = "google_maps_live"
            elif web_data.get("http_status") == 200:
                # Venue reached on Google Maps, but Google has no live telemetry at this hour
                source = "google_maps_online"

        result = {
            "source": source,
            "live_busyness": live_val,
            "google_place_id": resolved_place_id,
            "places_metadata": places_data,
            "timestamp": datetime.now()
        }

        # Cache result
        self.cache_reading(venue_id, result)
        return result
