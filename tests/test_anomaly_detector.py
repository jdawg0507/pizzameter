"""Unit tests for Quantitative Anomaly Engine."""

import unittest
from datetime import datetime
from src.engine.models import BusynessReading
from src.engine.anomaly_detector import AnomalyDetector


class TestAnomalyDetector(unittest.TestCase):
    def setUp(self):
        self.detector = AnomalyDetector(
            min_z_score_trigger=2.2,
            consecutive_intervals_required=2,
            min_baseline_sigma=7.5
        )

    def test_single_venue_z_score_calculation(self):
        # Normal = 20, Live = 20 -> Z = 0
        z = self.detector.compute_venue_z_score(live_busyness=20, normal_busyness=20)
        self.assertEqual(z, 0.0)

        # Normal = 20, Live = 50 -> delta = 30, sigma = max(4, 7.5) = 7.5 -> Z = 4.0
        z = self.detector.compute_venue_z_score(live_busyness=50, normal_busyness=20)
        self.assertEqual(z, 4.0)

        # None live -> returns None
        z = self.detector.compute_venue_z_score(live_busyness=None, normal_busyness=20)
        self.assertIsNone(z)

    def test_cluster_persistence_filter(self):
        # Create readings with elevated live busyness
        readings = [
            BusynessReading(venue_id="v1", timestamp=datetime.now(), day_of_week=0, hour_of_day=20, live_busyness=80, normal_busyness=20),
            BusynessReading(venue_id="v2", timestamp=datetime.now(), day_of_week=0, hour_of_day=20, live_busyness=85, normal_busyness=25),
            BusynessReading(venue_id="v3", timestamp=datetime.now(), day_of_week=0, hour_of_day=20, live_busyness=75, normal_busyness=20),
        ]

        # Interval 1: High Z-score, but streak is only 1/2 -> No alert yet
        cluster_z, alert1 = self.detector.evaluate_cluster("NVDA", "NVIDIA Corp", readings)
        self.assertGreater(cluster_z, 2.2)
        self.assertIsNone(alert1, "First interval should not trigger alert (requires 2 consecutive intervals)")

        # Interval 2: High Z-score sustained -> Alert triggers!
        cluster_z2, alert2 = self.detector.evaluate_cluster("NVDA", "NVIDIA Corp", readings)
        self.assertIsNotNone(alert2, "Second consecutive interval must trigger AnomalyAlert")
        self.assertEqual(alert2.ticker, "NVDA")
        self.assertEqual(alert2.reporting_venues, 3)

    def test_streak_reset_on_normal_reading(self):
        elevated = [
            BusynessReading(venue_id="v1", timestamp=datetime.now(), day_of_week=0, hour_of_day=20, live_busyness=80, normal_busyness=20)
        ]
        normal = [
            BusynessReading(venue_id="v1", timestamp=datetime.now(), day_of_week=0, hour_of_day=20, live_busyness=22, normal_busyness=20)
        ]

        # Elevated reading
        self.detector.evaluate_cluster("AAPL", "Apple Inc", elevated)
        self.assertEqual(len(self.detector.streak_history.get("AAPL", [])), 1)

        # Normal reading -> resets streak
        self.detector.evaluate_cluster("AAPL", "Apple Inc", normal)
        self.assertEqual(len(self.detector.streak_history.get("AAPL", [])), 0)


if __name__ == "__main__":
    unittest.main()
