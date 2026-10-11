"""PizzaMeter Orchestration Daemon: Polling loop, anomaly evaluation, FINOS broadcast, and execution."""

import asyncio
import json
import logging
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.engine.models import BusynessReading, AnomalyAlert
from src.engine.anomaly_detector import AnomalyDetector
from src.scraper.popular_times import PopularTimesScraper
from src.finos.fdc3_bridge import FDC3Bridge
from src.finos.cdm_serializer import CDMSerializer
from src.execution.alpaca_paper import AlpacaPaperExecutor
from src.execution.risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("PizzaMeterDaemon")


class PizzaMeterDaemon:
    def __init__(
        self,
        config_path: str = "config/settings.json",
        db_path: str = "data/pizzameter.db"
    ):
        self.config_path = Path(config_path)
        self.db_path = Path(db_path)
        self.config = self._load_config()

        # Subsystems
        self.anomaly_detector = AnomalyDetector(
            min_z_score_trigger=self.config.get("anomaly", {}).get("min_z_score_trigger", 2.2),
            consecutive_intervals_required=self.config.get("anomaly", {}).get("consecutive_intervals_required", 2),
            min_baseline_sigma=self.config.get("anomaly", {}).get("min_baseline_sigma", 7.5)
        )
        self.scraper = PopularTimesScraper(
            db_path=str(self.db_path),
            google_maps_config=self.config.get("google_maps", {})
        )
        self.fdc3_bridge = FDC3Bridge(
            host=self.config.get("finos", {}).get("ws_host", "127.0.0.1"),
            port=self.config.get("finos", {}).get("ws_port", 8765)
        )
        self.risk_manager = RiskManager(
            max_allocation_percent=self.config.get("execution", {}).get("risk", {}).get("max_allocation_percent", 0.02),
            ticker_cooldown_hours=self.config.get("execution", {}).get("risk", {}).get("ticker_cooldown_hours", 168),
            max_daily_trades=self.config.get("execution", {}).get("risk", {}).get("max_daily_trades", 5)
        )
        alpaca_cfg = self.config.get("execution", {}).get("alpaca", {})
        self.executor = AlpacaPaperExecutor(
            api_key_id=alpaca_cfg.get("api_key_id"),
            api_secret_key=alpaca_cfg.get("api_secret_key"),
            base_url=alpaca_cfg.get("base_url", "https://paper-api.alpaca.markets"),
            risk_manager=self.risk_manager
        )

        self.running = False
        self.poll_interval_sec = 10  # 10s intervals for live UI streaming demo (configurable)

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def fetch_all_monitored_venues(self) -> List[Dict[str, Any]]:
        """Fetch all tickers and their associated venues from SQLite."""
        venues = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT v.venue_id, v.ticker, v.name, v.cuisine, v.distance_meters,
                       t.company_name, t.sector, t.hq_address, t.timezone,
                       t.latitude, t.longitude, v.latitude, v.longitude, v.address,
                       v.google_place_id
                FROM venues v
                JOIN tickers t ON v.ticker = t.ticker
                WHERE t.is_active = 1
                ORDER BY v.ticker, v.distance_meters ASC
            """)
            for row in cursor.fetchall():
                venues.append({
                    "venue_id": row[0],
                    "ticker": row[1],
                    "name": row[2],
                    "cuisine": row[3],
                    "distance_meters": row[4],
                    "company_name": row[5],
                    "sector": row[6],
                    "hq_address": row[7],
                    "timezone": row[8],
                    "hq_lat": row[9],
                    "hq_lon": row[10],
                    "venue_lat": row[11],
                    "venue_lon": row[12],
                    "venue_address": row[13],
                    "google_place_id": row[14]
                })
        return venues

    async def execute_poll_cycle(self) -> Dict[str, Any]:
        """Perform one complete evaluation cycle across all monitored tickers."""
        venues = self.fetch_all_monitored_venues()
        if not venues:
            logger.warning("No monitored venues found in database. Run GeoMapper first.")
            return {}

        # Group venues by ticker
        by_ticker: Dict[str, List[Dict[str, Any]]] = {}
        company_names: Dict[str, str] = {}
        for v in venues:
            t = v["ticker"]
            if t not in by_ticker:
                by_ticker[t] = []
            by_ticker[t].append(v)
            company_names[t] = v["company_name"]

        cycle_results = []
        now = datetime.now()

        for ticker, ticker_venues in by_ticker.items():
            readings: List[BusynessReading] = []
            for v in ticker_venues:
                reading = self.scraper.fetch_venue_busyness(
                    venue_id=v["venue_id"],
                    ticker=ticker,
                    current_time=now,
                    venue_name=v.get("name"),
                    venue_address=v.get("venue_address"),
                    latitude=v.get("venue_lat"),
                    longitude=v.get("venue_lon"),
                    google_place_id=v.get("google_place_id")
                )
                # Compute single-venue Z-score
                reading.z_score = self.anomaly_detector.compute_venue_z_score(
                    reading.live_busyness,
                    reading.normal_busyness
                )
                self.scraper.record_reading_in_db(reading)
                readings.append(reading)

            # Evaluate cluster anomaly
            cluster_z, alert = self.anomaly_detector.evaluate_cluster(
                ticker=ticker,
                company_name=company_names[ticker],
                readings=readings,
                current_time=now
            )

            # Status classification
            if cluster_z >= 2.2:
                status = "CRITICAL_ANOMALY"
            elif cluster_z >= 1.2:
                status = "ELEVATED"
            else:
                status = "NORMAL"

            avg_normal = round(sum(r.normal_busyness for r in readings) / len(readings), 1)
            valid_live = [r.live_busyness for r in readings if r.live_busyness is not None]
            avg_live = round(sum(valid_live) / len(valid_live), 1) if valid_live else avg_normal

            item_summary = {
                "ticker": ticker,
                "company": company_names[ticker],
                "sector": ticker_venues[0]["sector"],
                "hq_address": ticker_venues[0]["hq_address"],
                "latitude": ticker_venues[0]["hq_lat"],
                "longitude": ticker_venues[0]["hq_lon"],
                "active_venues": len(readings),
                "avg_normal": avg_normal,
                "avg_live": avg_live,
                "cluster_z_score": cluster_z,
                "status": status,
                "timestamp": now.strftime("%H:%M:%S"),
                "venues": [
                    {
                        "venue_id": v["venue_id"],
                        "name": v["name"],
                        "cuisine": v["cuisine"],
                        "address": v["venue_address"],
                        "distance_meters": v["distance_meters"],
                        "latitude": v["venue_lat"],
                        "longitude": v["venue_lon"],
                        "live": r.live_busyness,
                        "normal": r.normal_busyness,
                        "z_score": r.z_score,
                        "source": r.data_source,
                        "google_place_id": v.get("google_place_id")
                    }
                    for v, r in zip(ticker_venues, readings)
                ]
            }
            cycle_results.append(item_summary)

            # Handle Alert
            if alert:
                logger.warning(
                    f"🚨 [PIZZAMETER ANOMALY DETECTED] {ticker} ({company_names[ticker]}) "
                    f"Cluster Z-Score: {cluster_z} across {alert.reporting_venues} pizzerias!"
                )
                # 1. Serialize FINOS CDM
                alert.cdm_payload = CDMSerializer.serialize_anomaly_event(alert)
                # 2. Format FDC3 Context
                alert.fdc3_payload = self.fdc3_bridge.create_fdc3_context(alert)

                # 3. Broadcast over FDC3 WebSocket
                await self.fdc3_bridge.broadcast_alert(alert)

                # 4. Execute Alpaca Paper Trade
                exec_result = self.executor.execute_anomaly_order(alert)
                alert.executed = exec_result.get("success", False)
                alert.order_id = exec_result.get("order_id")

                # 5. Persist Alert to SQLite
                self._record_alert_in_db(alert)

        # Broadcast latest telemetry snapshot to all connected Perspective/blotter clients
        snapshot = {
            "type": "TELEMETRY_UPDATE",
            "timestamp": now.isoformat(),
            "data": cycle_results
        }
        self.fdc3_bridge.latest_state = snapshot
        await self.fdc3_bridge.broadcast_raw(snapshot)

        return snapshot

    def _record_alert_in_db(self, alert: AnomalyAlert):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO alerts (alert_id, ticker, timestamp, cluster_z_score, reporting_venues, fdc3_payload, cdm_payload, executed, order_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.alert_id,
                    alert.ticker,
                    alert.timestamp.isoformat(),
                    alert.cluster_z_score,
                    alert.reporting_venues,
                    json.dumps(alert.fdc3_payload),
                    json.dumps(alert.cdm_payload),
                    1 if alert.executed else 0,
                    alert.order_id
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving alert to database: {e}")

    async def _gmaps_worker(self):
        """Asynchronously refreshes Google Maps telemetry in background without blocking the FDC3 event loop."""
        rate_delay = self.config.get("google_maps", {}).get("rate_limit_delay_sec", 1.0)
        logger.info(f"Google Maps background telemetry worker online (throttle: {rate_delay}s).")
        while self.running:
            try:
                venue_to_refresh = self.scraper.get_next_venue_to_refresh()
                if venue_to_refresh:
                    # Run network HTTP request in thread pool so asyncio event loop never blocks
                    await asyncio.to_thread(
                        self.scraper.refresh_venue_gmaps,
                        venue_to_refresh
                    )
                await asyncio.sleep(rate_delay)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Error in Google Maps worker: {e}")
                await asyncio.sleep(2.0)

    async def run(self):
        self.running = True
        logger.info("Initializing PizzaMeter Daemon...")
        # Start FDC3 WebSocket Server
        await self.fdc3_bridge.start()

        # Launch Google Maps asynchronous background worker
        worker_task = asyncio.create_task(self._gmaps_worker())

        logger.info(f"PizzaMeter Daemon online. Polling cycle every {self.poll_interval_sec}s.")
        try:
            while self.running:
                try:
                    await self.execute_poll_cycle()
                except Exception as e:
                    logger.error(f"Error during poll cycle: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval_sec)
        finally:
            worker_task.cancel()


if __name__ == "__main__":
    daemon = PizzaMeterDaemon()
    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        logger.info("PizzaMeter Daemon stopped by user.")
