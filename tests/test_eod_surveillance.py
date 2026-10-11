"""Unit and integration tests for OutscraperClient and EODSurveillanceChecker."""

import unittest
from unittest.mock import patch, MagicMock
from src.scraper.outscraper_client import OutscraperClient
from src.scraper.eod_checker import EODSurveillanceChecker, TOP_10_NASDAQ


class TestOutscraperClient(unittest.TestCase):

    def setUp(self):
        self.client = OutscraperClient(api_key="mock_outscraper_key")

    @patch("requests.Session.get")
    def test_query_venue_popular_times_busier_trigger(self, mock_get):
        """When Outscraper returns 'busier than usual', is_busier_than_usual should be True."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                [
                    {
                        "name": "Domino's Pizza Overlake",
                        "full_address": "2608 152nd Ave NE, Redmond, WA",
                        "place_id": "ChIJ_mock_msft_pizzeria",
                        "rating": 4.2,
                        "reviews": 210,
                        "popular_times": {
                            "live_status": "busier than usual",
                            "live_busyness": 88
                        }
                    }
                ]
            ]
        }
        mock_get.return_value = mock_resp

        res = self.client.query_venue_popular_times("Domino's Pizza Overlake", "Redmond, WA")
        self.assertTrue(res["success"])
        self.assertEqual(res["live_status"], "busier than usual")
        self.assertEqual(res["live_busyness"], 88)
        self.assertTrue(res["is_busier_than_usual"])

    @patch("requests.Session.get")
    def test_query_venue_popular_times_normal(self, mock_get):
        """When Outscraper returns 'little busy' or 'not busy', is_busier_than_usual should be False."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                [
                    {
                        "name": "Amici's East Coast Pizzeria",
                        "full_address": "20620 Homestead Rd, Cupertino, CA",
                        "popular_times": {
                            "live_status": "little busy",
                            "live_busyness": 32
                        }
                    }
                ]
            ]
        }
        mock_get.return_value = mock_resp

        res = self.client.query_venue_popular_times("Amici's East Coast Pizzeria", "Cupertino, CA")
        self.assertTrue(res["success"])
        self.assertEqual(res["live_status"], "little busy")
        self.assertFalse(res["is_busier_than_usual"])

    def test_simulate_busy_mode(self):
        """Simulation override should return immediate high busyness without network calls."""
        res = self.client.query_venue_popular_times("Pizza Hut", "Santa Clara, CA", simulate_busy=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["is_busier_than_usual"])
        self.assertEqual(res["live_status"], "busier than usual")


class TestEODSurveillanceChecker(unittest.TestCase):

    def setUp(self):
        self.checker = EODSurveillanceChecker(db_path="data/pizzameter.db")

    def test_top10_venues_resolved(self):
        """Verify exactly 10 closest venues are returned, 1 per Top 10 mega-cap."""
        venues = self.checker.fetch_top10_closest_venues()
        self.assertEqual(len(venues), 10)
        tickers = [v["ticker"] for v in venues]
        for expected in TOP_10_NASDAQ:
            self.assertIn(expected, tickers)

    def test_dry_run_scan(self):
        """Dry run should execute cleanly across all 10 venues with 0 API calls."""
        scan_res = self.checker.run_eod_scan(dry_run=True)
        self.assertEqual(scan_res["scanned"], 10)
        self.assertEqual(scan_res["triggered_count"], 0)


if __name__ == "__main__":
    unittest.main()
