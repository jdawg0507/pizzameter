"""Unit and integration tests for FootTrafficClient and zero-RNG PopularTimesScraper."""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from src.scraper.foot_traffic_client import FootTrafficClient
from src.scraper.popular_times import PopularTimesScraper


class TestFootTrafficClient(unittest.TestCase):

    def setUp(self):
        self.client = FootTrafficClient(
            provider="besttime",
            api_key=None,
            cache_ttl_sec=300,
            request_timeout_sec=2.0,
            enabled=True
        )

    def test_cache_miss_and_hit(self):
        """Test in-memory TTL caching behaves correctly."""
        venue_id = "v_test_001"
        self.assertIsNone(self.client.get_cached_reading(venue_id))

        fake_reading = {
            "live_busyness": 75,
            "source": "besttime_live",
            "google_place_id": "ChIJtest123"
        }
        self.client.cache_reading(venue_id, fake_reading)

        cached = self.client.get_cached_reading(venue_id)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["live_busyness"], 75)
        self.assertEqual(cached["source"], "besttime_live_cache")

    def test_cache_expiration(self):
        """Test cache entries expire after TTL."""
        venue_id = "v_test_expired"
        self.client.cache_reading(venue_id, {"live_busyness": 50, "source": "test"})

        # Artificially age the cache entry beyond TTL
        self.client._cache[venue_id]["timestamp"] = datetime.now() - timedelta(seconds=350)
        self.assertIsNone(self.client.get_cached_reading(venue_id))

    def test_deterministic_model_zero_rng(self):
        """Verify the deterministic model produces repeatable, continuous results without random."""
        # Consecutive calls with same parameters should return identical values
        normal1, live1 = FootTrafficClient.calculate_deterministic_model(12.5, 2, venue_seed=100)
        normal2, live2 = FootTrafficClient.calculate_deterministic_model(12.5, 2, venue_seed=100)
        self.assertEqual(normal1, normal2)
        self.assertEqual(live1, live2)

        # Lunch peak around 12:30 should be substantially higher than 03:00
        normal_lunch, _ = FootTrafficClient.calculate_deterministic_model(12.5, 2, venue_seed=100)
        normal_night, _ = FootTrafficClient.calculate_deterministic_model(3.0, 2, venue_seed=100)
        self.assertGreater(normal_lunch, normal_night)

        # Values should always be bounded 0-100
        for h in range(24):
            n, l = FootTrafficClient.calculate_deterministic_model(float(h), 0, venue_seed=50)
            self.assertTrue(0 <= n <= 100)
            self.assertTrue(0 <= l <= 100)

    @patch("requests.Session.post")
    def test_besttime_api_success(self, mock_post):
        """Test successful BestTime API response parsing."""
        client_with_key = FootTrafficClient(provider="besttime", api_key="bt_mock_key_123")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "OK",
            "venue_name": "Domino's Pizza",
            "venue_live_busyness": {
                "busyness": 82,
                "status": "Busier than usual"
            },
            "analysis": {
                "day_raw": [5, 5, 5, 5, 5, 10, 20, 30, 40, 50, 60, 70, 75, 70, 50, 40, 50, 65, 80, 85, 70, 40, 20, 10]
            }
        }
        mock_post.return_value = mock_resp

        res = client_with_key.query_besttime_api("Domino's Pizza", "Santa Clara, CA")
        self.assertIsNotNone(res)
        self.assertEqual(res["live_busyness"], 82)
        self.assertEqual(res["source"], "besttime_live")

    @patch("requests.Session.get")
    def test_outscraper_api_success(self, mock_get):
        """Test Outscraper API response parsing."""
        client_with_key = FootTrafficClient(provider="outscraper", api_key="outscraper_mock_key")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "popular_times": {
                        "live_popularity": 79
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        res = client_with_key.query_outscraper_api("Pagliacci Pizza", "Redmond, WA")
        self.assertIsNotNone(res)
        self.assertEqual(res["live_busyness"], 79)
        self.assertEqual(res["source"], "outscraper_live")


class TestPopularTimesIntegration(unittest.TestCase):

    def setUp(self):
        self.scraper = PopularTimesScraper(
            db_path=":memory:",
            google_maps_config={"enabled": True}
        )

    def test_surge_override_precedence(self):
        """Simulated surge should always take precedence over external APIs and baseline."""
        self.scraper.set_simulated_surge("NVDA", 98)
        reading = self.scraper.fetch_venue_busyness(
            venue_id="v_nvda_1",
            ticker="NVDA",
            venue_name="Domino's Pizza",
            venue_address="Santa Clara, CA"
        )
        self.assertEqual(reading.live_busyness, 98)
        self.assertEqual(reading.data_source, "simulated_surge")

    @patch.object(FootTrafficClient, "ping_venue")
    def test_commercial_api_reading_used(self, mock_ping):
        """When commercial API returns live busyness, it should be reflected in the reading."""
        mock_ping.return_value = {
            "source": "besttime_live",
            "live_busyness": 88,
            "normal_busyness": 65,
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
        self.assertEqual(reading.data_source, "besttime_live")

    def test_deterministic_zero_rng_fallback(self):
        """When no external API key is configured, uses deterministic model without random."""
        reading = self.scraper.fetch_venue_busyness(
            venue_id="v_msft_1",
            ticker="MSFT",
            venue_name="Pagliacci Pizza",
            venue_address="Redmond, WA"
        )
        self.assertIsNotNone(reading.normal_busyness)
        self.assertIsNotNone(reading.live_busyness)
        self.assertEqual(reading.data_source, "deterministic_model")

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
