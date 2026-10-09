"""Scraper and telemetry provider for venue foot traffic and busyness levels."""

import math
import random
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import sqlite3

from src.engine.models import BusynessReading

logger = logging.getLogger("PopularTimesScraper")


class PopularTimesScraper:
    """
    Retrieves normal and live busyness metrics for monitored venues.
    Supports real extraction interfaces and controlled scenario injections for testing.
    """

    def __init__(self, db_path: str = "data/pizzameter.db"):
        self.db_path = db_path
        # Active scenario overrides for targeted simulation: venue_id or ticker -> live_busyness
        self.simulated_surges: Dict[str, int] = {}

    def set_simulated_surge(self, target: str, live_value: int = 95):
        """Inject a high busyness spike on a specific ticker or venue for testing."""
        self.simulated_surges[target.upper()] = live_value
        logger.info(f"Injected simulated surge on {target.upper()} = {live_value}% busyness.")

    def clear_simulated_surges(self):
        self.simulated_surges.clear()

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
        current_time: Optional[datetime] = None
    ) -> BusynessReading:
        """
        Fetch normal and live busyness for a specific venue at current_time.
        """
        now = current_time or datetime.now()
        hour = now.hour
        day = now.weekday()

        normal = self.get_baseline_curve(hour, day)

        # Check if an anomaly surge was injected on this ticker or venue
        if ticker.upper() in self.simulated_surges:
            live = self.simulated_surges[ticker.upper()]
        elif venue_id in self.simulated_surges:
            live = self.simulated_surges[venue_id]
        else:
            # Normal random oscillation around baseline (+/- 10%)
            live_noise = random.randint(-8, 8)
            live = max(5, min(100, normal + live_noise))

        # 5% chance of live data temporarily unavailable from Google
        if random.random() < 0.05 and ticker.upper() not in self.simulated_surges:
            live = None

        return BusynessReading(
            venue_id=venue_id,
            timestamp=now,
            day_of_week=day,
            hour_of_day=hour,
            live_busyness=live,
            normal_busyness=normal
        )

    def record_reading_in_db(self, reading: BusynessReading):
        """Persist reading to SQLite historical_busyness table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO historical_busyness (venue_id, timestamp, day_of_week, hour_of_day, live_busyness, normal_busyness, z_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    reading.venue_id,
                    reading.timestamp.isoformat(),
                    reading.day_of_week,
                    reading.hour_of_day,
                    reading.live_busyness,
                    reading.normal_busyness,
                    reading.z_score
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error persisting busyness reading: {e}")
