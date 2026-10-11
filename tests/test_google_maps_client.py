"""Unit and integration tests for GoogleMapsClient and PopularTimesScraper hybrid pinging."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from src.scraper.google_maps_client import GoogleMapsClient
from src.scraper.popular_times import PopularTimesScraper
from src.engine.models import BusynessReading


class TestGoogleMapsClient(unittest.TestCase):

    def setUp(self):
        self.client = GoogleMapsClient(
            api_key=None,
            cache_ttl_sec=300,
            request_timeout_sec=2.0,
            rate_limit_delay_sec=0.0,
            enabled=True
        )

    def test_cache_miss_and_hit(self):
        """Test in-memory TTL caching behaves correctly."""
        venue_id = "v_test_001"
        self.assertIsNone(self.client.get_cached_reading(venue_id))

        fake_reading = {
            "live_busyness": 75,
            "source": "google_maps_live",
            "google_place_id": "ChIJtest123"
        }
        self.client.cache_reading(venue_id, fake_reading)

        cached = self.client.get_cached_reading(venue_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["live_busyness"], 75)
        self.assertEqual(cached["source"], "google_maps_cache")

    def test_cache_expiration(self):
        """Test cache entries expire after TTL."""
        venue_id = "v_test_expired"
        self.client.cache_reading(venue_id, {"live_busyness": 50, "source": "test"})

        # Artificially age the cache entry beyond TTL
        self.client._cache[venue_id]["timestamp"] = datetime.now() - timedelta(seconds=350)
        self.assertIsNone(self.client.get_cached_reading(venue_id))

    def test_html_parsing_live_aria(self):
        """Test parsing live busyness from various Google Maps HTML patterns."""
        html_sample_1 = '<div><span aria-label="Currently 84% busy">Currently 84% busy</span></div>'
        self.assertEqual(self.client.parse_live_busyness_from_html(html_sample_1), 84)

        html_sample_2 = '<div><span>92% as busy as it gets right now</span></div>'
        self.assertEqual(self.client.parse_live_busyness_from_html(html_sample_2), 92)

        html_sample_3 = 'window.APP_INITIALIZATION_STATE=[1,2,["Currently 65%"],null];'
        self.assertEqual(self.client.parse_live_busyness_from_html(html_sample_3), 65)

    def test_html_parsing_empty_or_invalid(self):
        """Test graceful return when no busyness data is present in HTML."""
        html_empty = '<html><body><h1>Pizza Place</h1></body></html>'
        self.assertIsNone(self.client.parse_live_busyness_from_html(html_empty))

    @patch("requests.Session.get")
    def test_ping_google_maps_web_success(self, mock_get):
        """Test successful HTTP ping to Google Maps web endpoint."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html>Currently 72% busy ChIJabc1234567890123456789</html>'
        mock_get.return_value = mock_resp

        res = self.client.ping_google_maps_web("Amici's East Coast Pizzeria", "Mountain View, CA")
        self.assertIsNotNone(res)
        self.assertEqual(res["live_busyness"], 72)
        self.assertEqual(res["http_status"], 200)
        self.assertTrue(res["has_live_data"])
        self.assertEqual(res["google_place_id"], "ChIJabc1234567890123456789")

    @patch("requests.Session.get")
    def test_ping_google_maps_web_timeout_fallback(self, mock_get):
        """Test timeout resilience in web ping."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        res = self.client.ping_google_maps_web("Slow Pizzeria", "Cupertino, CA")
        self.assertIsNone(res)

    @patch("requests.Session.get")
    def test_query_places_api_with_key(self, mock_get):
        """Test official Places API query when api_key is configured."""
        client_with_key = GoogleMapsClient(api_key="AIzaSyTestMockKey", rate_limit_delay_sec=0.0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "result": {
                "place_id": "ChIJ_real_places_id_999",
                "business_status": "OPERATIONAL",
                "rating": 4.6,
                "user_ratings_total": 520,
                "opening_hours": {"open_now": True}
            }
        }
        mock_get.return_value = mock_resp

        places_data = client_with_key.query_places_api("Tony's Pizza", google_place_id="ChIJ_real_places_id_999")
        self.assertIsNotNone(places_data)
        self.assertEqual(places_data["place_id"], "ChIJ_real_places_id_999")
        self.assertEqual(places_data["rating"], 4.6)


class TestPopularTimesIntegration(unittest.TestCase):

    def setUp(self):
        self.scraper = PopularTimesScraper(
            db_path=":memory:",
            google_maps_config={"enabled": True, "rate_limit_delay_sec": 0.0}
        )

    def test_surge_override_precedence(self):
        """Simulated surge should always take precedence over Google Maps and baseline."""
        self.scraper.set_simulated_surge("NVDA", 98)
        reading = self.scraper.fetch_venue_busyness(
            venue_id="v_nvda_1",
            ticker="NVDA",
            venue_name="Domino's Pizza",
            venue_address="Santa Clara, CA"
        )
        self.assertEqual(reading.live_busyness, 98)
        self.assertEqual(reading.data_source, "simulated_surge")

    @patch.object(GoogleMapsClient, "ping_venue")
    def test_google_maps_live_reading_used(self, mock_ping):
        """When Google Maps returns live busyness, it should be reflected in the reading."""
        mock_ping.return_value = {
            "source": "google_maps_live",
            "live_busyness": 88,
            "google_place_id": "ChIJmocked123"
        }

        reading = self.scraper.fetch_venue_busyness(
            venue_id="v_aapl_1",
            ticker="AAPL",
            venue_name="Sliver Pizzeria",
            venue_address="Cupertino, CA",
            live_ping=True
        )
        self.assertEqual(reading.live_busyness, 88)
        self.assertEqual(reading.data_source, "google_maps_live")

    @patch.object(GoogleMapsClient, "ping_venue")
    def test_google_maps_fallback_to_baseline(self, mock_ping):
        """When Google Maps is unreachable or has no live data, it falls back to baseline."""
        mock_ping.return_value = {
            "source": "fallback_baseline",
            "live_busyness": None,
            "google_place_id": None
        }

        reading = self.scraper.fetch_venue_busyness(
            venue_id="v_msft_1",
            ticker="MSFT",
            venue_name="Pagliacci Pizza",
            venue_address="Redmond, WA",
            live_ping=True
        )
        self.assertIsNotNone(reading.normal_busyness)
        self.assertIn(reading.data_source, ["fallback_baseline", "google_maps_online"])

    def test_queue_venue_for_background_refresh(self):
        """Un-cached venues should be enqueued for background worker refresh."""
        self.scraper.queue_venue_for_refresh({
            "venue_id": "v_goog_1",
            "ticker": "GOOGL",
            "name": "State of Mind Slice",
            "address": "Mountain View, CA"
        })
        item = self.scraper.get_next_venue_to_refresh()
        self.assertIsNotNone(item)
        self.assertEqual(item["venue_id"], "v_goog_1")


if __name__ == "__main__":
    unittest.main()
