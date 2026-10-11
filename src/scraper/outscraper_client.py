"""Outscraper Google Maps Popular Times API Client.

Performs targeted individual searches for specific venues to extract:
- popular_times (live_status e.g. 'busier than usual', 'little busy', 'not busy')
- live_busyness percentage (0-100)
- weekly graph baseline
- Google Place ID, ratings, and open status
"""

import os
import re
import json
import logging
from typing import Dict, Any, Optional, List
import requests

logger = logging.getLogger("OutscraperClient")


class OutscraperClient:
    """
    Dedicated client for querying Google Maps Popular Times via Outscraper API.
    Designed for targeted, low-frequency individual venue searches (e.g. 10 queries/day).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        request_timeout_sec: float = 15.0
    ):
        self.api_key = api_key or os.environ.get("OUTSCRAPER_API_KEY")
        self.request_timeout_sec = request_timeout_sec
        self.endpoint = "https://api.app.outscraper.com/maps/search-v2"
        self._session = requests.Session()

    def is_configured(self) -> bool:
        """Return True if an API key is present."""
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def query_venue_popular_times(
        self,
        name: str,
        address: Optional[str] = None,
        google_place_id: Optional[str] = None,
        simulate_busy: bool = False
    ) -> Dict[str, Any]:
        """
        Query Outscraper for a specific individual venue.
        Returns live status, busyness, and whether the venue is 'busier than usual'.
        """
        # Simulation override (for testing end-to-end FINOS triggers without consuming quota)
        if simulate_busy:
            return {
                "success": True,
                "name": name,
                "address": address,
                "live_status": "busier than usual",
                "live_busyness": 92,
                "normal_busyness": 35,
                "is_busier_than_usual": True,
                "place_id": google_place_id or "ChIJ_simulated_id",
                "rating": 4.5,
                "reviews": 380,
                "source": "outscraper_simulated"
            }

        if not self.is_configured():
            logger.warning("OUTSCRAPER_API_KEY not configured. Set via environment variable or settings.json.")
            return {
                "success": False,
                "error": "OUTSCRAPER_API_KEY_NOT_CONFIGURED",
                "is_busier_than_usual": False
            }

        query = f"{name}, {address or ''}".strip(", ")
        params = {
            "query": query,
            "limit": 1,
            "language": "en",
            "async": "false"
        }
        headers = {
            "X-API-KEY": self.api_key
        }

        try:
            logger.info(f"Querying Outscraper for venue: {query}")
            resp = self._session.get(
                self.endpoint,
                headers=headers,
                params=params,
                timeout=self.request_timeout_sec
            )

            if resp.status_code == 200:
                body = resp.json()
                data = body.get("data", [])
                if data and len(data) > 0 and len(data[0]) > 0:
                    place_item = data[0][0]
                    pop_times = place_item.get("popular_times") or {}

                    live_status = pop_times.get("live_status") or ""
                    live_busyness = pop_times.get("live_busyness")

                    # Check for "busier than usual" trigger conditions
                    status_lower = live_status.lower()
                    is_busier = (
                        "busier than usual" in status_lower or
                        "much busier" in status_lower or
                        "as busy as it gets" in status_lower or
                        (live_busyness is not None and live_busyness >= 80)
                    )

                    return {
                        "success": True,
                        "name": place_item.get("name") or name,
                        "address": place_item.get("full_address") or address,
                        "live_status": live_status or "normal",
                        "live_busyness": live_busyness,
                        "is_busier_than_usual": is_busier,
                        "place_id": place_item.get("place_id") or google_place_id,
                        "rating": place_item.get("rating"),
                        "reviews": place_item.get("reviews"),
                        "raw_popular_times": pop_times,
                        "source": "outscraper_live"
                    }
                else:
                    logger.warning(f"Outscraper returned 0 results for query: {query}")
                    return {"success": False, "error": "NO_RESULTS", "is_busier_than_usual": False}
            elif resp.status_code == 401 or resp.status_code == 403:
                logger.error("Outscraper API authentication failed (invalid API key).")
                return {"success": False, "error": "AUTH_FAILED", "is_busier_than_usual": False}
            elif resp.status_code == 429:
                logger.warning("Outscraper API quota reached (HTTP 429).")
                return {"success": False, "error": "RATE_LIMITED", "is_busier_than_usual": False}
            else:
                logger.warning(f"Outscraper returned HTTP {resp.status_code}: {resp.text[:100]}")
                return {"success": False, "error": f"HTTP_{resp.status_code}", "is_busier_than_usual": False}

        except requests.exceptions.Timeout:
            logger.error(f"Outscraper request timed out ({self.request_timeout_sec}s) for {name}")
            return {"success": False, "error": "TIMEOUT", "is_busier_than_usual": False}
        except Exception as e:
            logger.error(f"Exception during Outscraper request for {name}: {e}")
            return {"success": False, "error": str(e), "is_busier_than_usual": False}
