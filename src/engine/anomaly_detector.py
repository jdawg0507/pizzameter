"""Quantitative Anomaly Engine: Z-Score calculation and multi-interval persistence filter."""

import math
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from src.engine.models import BusynessReading, AnomalyAlert

logger = logging.getLogger("AnomalyEngine")


class AnomalyDetector:
    """
    Computes statistical Z-Scores for individual venues and aggregated cluster scores
    for corporate HQ zones:
    
      Z_i = (B_live - B_normal) / max(sigma, min_sigma)
      S_ticker = (1 / N) * sum(Z_i)
    
    A trigger requires S_ticker >= min_z_score sustained across consecutive polling intervals.
    """

    def __init__(
        self,
        min_z_score_trigger: float = 2.2,
        consecutive_intervals_required: int = 2,
        min_baseline_sigma: float = 7.5
    ):
        self.min_z_score_trigger = min_z_score_trigger
        self.consecutive_intervals_required = consecutive_intervals_required
        self.min_baseline_sigma = min_baseline_sigma
        # In-memory history tracking: ticker -> list of consecutive (timestamp, S_ticker)
        self.streak_history: Dict[str, List[Tuple[datetime, float]]] = {}

    def compute_venue_z_score(
        self,
        live_busyness: Optional[int],
        normal_busyness: int,
        historical_variance: Optional[float] = None
    ) -> Optional[float]:
        """Compute standardized Z-Score for a single venue."""
        if live_busyness is None:
            return None

        # Calculate standard deviation or fallback to minimum baseline
        if historical_variance is not None and historical_variance > 0:
            sigma = math.sqrt(historical_variance)
        else:
            # Rule of thumb: standard deviation proportional to busyness level, bounded
            sigma = max(normal_busyness * 0.20, self.min_baseline_sigma)

        sigma = max(sigma, self.min_baseline_sigma)
        z = (live_busyness - normal_busyness) / sigma
        return round(z, 3)

    def evaluate_cluster(
        self,
        ticker: str,
        company_name: str,
        readings: List[BusynessReading],
        current_time: Optional[datetime] = None
    ) -> Tuple[float, Optional[AnomalyAlert]]:
        """
        Evaluate a set of venue readings for a given ticker HQ at the current polling interval.
        Returns: (cluster_z_score, optional AnomalyAlert if triggered)
        """
        now = current_time or datetime.now()

        valid_z_scores = []
        venue_details = []

        for r in readings:
            z = r.z_score
            if z is None and r.live_busyness is not None:
                z = self.compute_venue_z_score(r.live_busyness, r.normal_busyness)

            if z is not None:
                valid_z_scores.append(z)
                venue_details.append({
                    "venue_id": r.venue_id,
                    "live": r.live_busyness,
                    "normal": r.normal_busyness,
                    "z_score": z
                })

        if not valid_z_scores:
            logger.debug(f"[{ticker}] No active live busyness readings reporting.")
            self._reset_streak(ticker)
            return (0.0, None)

        # Cluster score is the mean Z-Score across all reporting venues
        cluster_z = round(sum(valid_z_scores) / len(valid_z_scores), 3)

        # Check threshold
        if cluster_z >= self.min_z_score_trigger:
            if ticker not in self.streak_history:
                self.streak_history[ticker] = []
            self.streak_history[ticker].append((now, cluster_z))

            streak_len = len(self.streak_history[ticker])
            logger.info(
                f"[{ticker}] Elevated cluster Z-score: {cluster_z} (Streak: {streak_len}/{self.consecutive_intervals_required})"
            )

            # Fire alert if sustained for required intervals
            if streak_len >= self.consecutive_intervals_required:
                alert_id = f"ALT_{ticker}_{now.strftime('%Y%m%d_%H%M%S')}"
                alert = AnomalyAlert(
                    alert_id=alert_id,
                    ticker=ticker,
                    company_name=company_name,
                    timestamp=now,
                    cluster_z_score=cluster_z,
                    reporting_venues=len(valid_z_scores),
                    venues_detail=venue_details,
                    fdc3_payload={},  # Populated by FDC3 bridge
                    cdm_payload={}    # Populated by CDM serializer
                )
                return (cluster_z, alert)
        else:
            self._reset_streak(ticker)

        return (cluster_z, None)

    def _reset_streak(self, ticker: str):
        if ticker in self.streak_history and len(self.streak_history[ticker]) > 0:
            logger.debug(f"[{ticker}] Streak reset (Z-score dropped below {self.min_z_score_trigger})")
            self.streak_history[ticker] = []
