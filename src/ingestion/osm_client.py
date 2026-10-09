"""Client for OpenStreetMap Overpass API to query POIs around coordinates."""

import math
import time
import logging
from typing import List, Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


def calculate_haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance in meters between two points on earth."""
    R = 6371000  # Radius of earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


class OverpassClient:
    """Queries OpenStreetMap Overpass API for pizza and late-night food amenities."""

    DEFAULT_ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]

    def __init__(self, endpoint_url: Optional[str] = None, timeout_sec: int = 2):
        self.endpoint_url = endpoint_url or self.DEFAULT_ENDPOINTS[0]
        self.timeout_sec = timeout_sec
        self.headers = {
            "User-Agent": "PizzaMeterQuant/1.0 (Alternative Data Research; OpenFin/FINOS Research Engine)"
        }
        self.consecutive_failures = 0
        self.network_disabled = False

    def query_pizzerias_around(self, lat: float, lon: float, radius_meters: int = 1600) -> List[Dict[str, Any]]:
        """
        Query Overpass for fast_food or restaurant POIs with pizza cuisine or delivery within radius.
        """
        if self.network_disabled:
            return []

        query = f"""
        [out:json][timeout:{self.timeout_sec}];
        (
          node["amenity"="fast_food"]["cuisine"~"pizza",i](around:{radius_meters},{lat},{lon});
          node["amenity"="restaurant"]["cuisine"~"pizza",i](around:{radius_meters},{lat},{lon});
          node["amenity"="fast_food"]["delivery"="yes"](around:{radius_meters},{lat},{lon});
          node["cuisine"~"pizza",i](around:{radius_meters},{lat},{lon});
        );
        out body;
        """

        for endpoint in [self.endpoint_url] + [ep for ep in self.DEFAULT_ENDPOINTS if ep != self.endpoint_url]:
            try:
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=self.headers,
                    timeout=self.timeout_sec
                )
                if response.status_code == 200:
                    self.consecutive_failures = 0
                    data = response.json()
                    elements = data.get("elements", [])
                    return self._process_elements(elements, lat, lon)
                elif response.status_code == 429:
                    logger.warning(f"Overpass endpoint {endpoint} returned HTTP 429 rate limit. Backing off...")
                    self.consecutive_failures += 1
            except Exception as e:
                logger.warning(f"Error querying Overpass endpoint {endpoint}: {e}")
                self.consecutive_failures += 1

        if self.consecutive_failures >= 2:
            logger.info("Overpass endpoints unresponsive or rate limited. Enabling fast local vicinity generator.")
            self.network_disabled = True

        return []

    def _process_elements(self, elements: List[Dict[str, Any]], hq_lat: float, hq_lon: float) -> List[Dict[str, Any]]:
        """Parse raw OSM elements, compute distances, and sort by proximity."""
        venues = []
        seen_names = set()

        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue

            # Simple deduplication by normalized name
            norm_name = name.strip().lower()
            if norm_name in seen_names:
                continue
            seen_names.add(norm_name)

            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                continue

            dist = calculate_haversine_meters(hq_lat, hq_lon, lat, lon)
            street = tags.get("addr:street", "")
            housenumber = tags.get("addr:housenumber", "")
            address = f"{housenumber} {street}".strip() or tags.get("addr:full", "Local Vicinity")

            venues.append({
                "osm_id": str(el.get("id")),
                "name": name,
                "cuisine": tags.get("cuisine", "pizza"),
                "address": address,
                "latitude": lat,
                "longitude": lon,
                "distance_meters": round(dist, 1)
            })

        # Sort closest first
        venues.sort(key=lambda x: x["distance_meters"])
        return venues
