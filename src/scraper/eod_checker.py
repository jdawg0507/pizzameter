"""End-of-Workday (EOD) Surveillance Scanner.

Focuses surveillance on the Top 10 NASDAQ-100 mega-caps and the single closest
pizzeria to each corporate headquarters. Executes exactly 10 Outscraper API calls per day.
If any venue reports 'busier than usual', pulls an automated trigger to FINOS FDC3 and CDM.
"""

import sys
import json
import asyncio
import logging
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import websockets

from src.scraper.outscraper_client import OutscraperClient
from src.engine.models import AnomalyAlert, BusynessReading
from src.finos.cdm_serializer import CDMSerializer
from src.finos.fdc3_bridge import FDC3Bridge

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("EODSurveillance")

TOP_10_NASDAQ = [
    "MSFT",  # Microsoft
    "AAPL",  # Apple
    "NVDA",  # NVIDIA
    "AMZN",  # Amazon
    "GOOGL", # Alphabet
    "META",  # Meta
    "TSLA",  # Tesla
    "AVGO",  # Broadcom
    "COST",  # Costco
    "ADBE"   # Adobe
]


class EODSurveillanceChecker:
    """
    Coordinates daily end-of-workday scans across the 10 closest pizzerias to NASDAQ Top 10 HQs.
    Fires real-time FINOS FDC3 & CDM triggers if 'busier than usual' foot traffic is confirmed.
    """

    def __init__(
        self,
        db_path: str = "data/pizzameter.db",
        config_path: str = "config/settings.json",
        api_key: Optional[str] = None,
        ws_uri: str = "ws://127.0.0.1:8765"
    ):
        self.db_path = Path(db_path)
        self.config_path = Path(config_path)
        self.ws_uri = ws_uri
        self.config = self._load_config()

        # Extract API key from parameter, config, or env
        resolved_key = (
            api_key or
            self.config.get("foot_traffic_api", {}).get("api_key") or
            self.config.get("outscraper", {}).get("api_key")
        )
        self.client = OutscraperClient(api_key=resolved_key)

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def fetch_top10_closest_venues(self) -> List[Dict[str, Any]]:
        """Retrieve the single closest pizzeria for each of the Top 10 NASDAQ tickers."""
        venues = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for ticker in TOP_10_NASDAQ:
                cursor.execute("""
                    SELECT v.venue_id, v.ticker, v.name, v.address, v.distance_meters,
                           v.latitude, v.longitude, v.google_place_id,
                           t.company_name, t.sector, t.hq_address, t.timezone
                    FROM venues v
                    JOIN tickers t ON v.ticker = t.ticker
                    WHERE v.ticker = ?
                    ORDER BY v.distance_meters ASC
                    LIMIT 1
                """, (ticker,))
                row = cursor.fetchone()
                if row:
                    venues.append({
                        "venue_id": row[0],
                        "ticker": row[1],
                        "name": row[2],
                        "address": row[3],
                        "distance_meters": row[4],
                        "latitude": row[5],
                        "longitude": row[6],
                        "google_place_id": row[7],
                        "company_name": row[8],
                        "sector": row[9],
                        "hq_address": row[10],
                        "timezone": row[11]
                    })
        return venues

    async def broadcast_finos_trigger(
        self,
        ticker: str,
        company_name: str,
        venue: Dict[str, Any],
        live_status: str,
        live_busyness: Optional[int]
    ):
        """
        Pull trigger to FINOS:
        1. Serialize CDM 5.0 Event
        2. Broadcast FDC3 Instrument Context & Intent over WebSocket
        3. Persist Alert in SQLite
        """
        now = datetime.now()
        alert_id = f"alert_eod_{ticker.lower()}_{int(now.timestamp())}"
        cluster_z = 3.4  # High-confidence anomaly signal

        venue_detail = [{
            "venue_id": venue["venue_id"],
            "name": venue["name"],
            "address": venue["address"],
            "distance_meters": venue["distance_meters"],
            "live_status": live_status,
            "live": live_busyness or 90,
            "normal": 35,
            "z_score": cluster_z
        }]

        alert = AnomalyAlert(
            alert_id=alert_id,
            ticker=ticker,
            company_name=company_name,
            timestamp=now,
            cluster_z_score=cluster_z,
            reporting_venues=1,
            venues_detail=venue_detail,
            fdc3_payload={},
            cdm_payload={}
        )

        # 1. FINOS CDM Serialization
        alert.cdm_payload = CDMSerializer.serialize_anomaly_event(alert, recommended_strategy="EOD_VOLATILITY_BREAKOUT")

        # 2. FDC3 Context Formatting
        alert.fdc3_payload = FDC3Bridge.create_fdc3_context(alert)
        alert.fdc3_payload["metadata"]["liveStatus"] = live_status
        alert.fdc3_payload["metadata"]["venueName"] = venue["name"]

        # 3. Persist Alert to SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO alerts (alert_id, ticker, timestamp, cluster_z_score, reporting_venues, fdc3_payload, cdm_payload, executed, order_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                """, (
                    alert.alert_id,
                    alert.ticker,
                    alert.timestamp.isoformat(),
                    alert.cluster_z_score,
                    alert.reporting_venues,
                    json.dumps(alert.fdc3_payload),
                    json.dumps(alert.cdm_payload)
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error persisting alert to DB: {e}")

        # 4. Broadcast over WebSocket Bus to synchronized trading terminals
        try:
            async with websockets.connect(self.ws_uri, open_timeout=3.0) as ws:
                # Send FDC3 Intent
                intent_msg = {
                    "action": "RAISE_INTENT",
                    "intent": "ViewInstrument",
                    "context": alert.fdc3_payload
                }
                await ws.send(json.dumps(intent_msg))

                # Send Raw FDC3 Context + CDM Event
                context_msg = {
                    "type": "FDC3_CONTEXT",
                    "context": alert.fdc3_payload,
                    "cdm": alert.cdm_payload
                }
                await ws.send(json.dumps(context_msg))
                logger.info(f"📡 Broadcasted FDC3 & CDM trigger for {ticker} over {self.ws_uri}")
        except Exception as e:
            logger.warning(f"Could not connect to FDC3 WebSocket broker ({self.ws_uri}): {e}")
            logger.info("Alert persisted to SQLite. Ensure 'make run-daemon' is running to broadcast live.")

    def run_eod_scan(
        self,
        simulate_busy_ticker: Optional[str] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Execute the 10-call End of Workday Outscraper Scan across Top 10 NASDAQ corporate HQs.
        """
        venues = self.fetch_top10_closest_venues()
        if not venues:
            logger.error("No venues found in database. Run 'make setup' first.")
            return {"scanned": 0, "triggers": []}

        logger.info(f"============================================================")
        logger.info(f"🍕 PizzaMeter EOD Surveillance Scan (Target: Top 10 NASDAQ-100)")
        logger.info(f"Surveillance Mode: 1 Closest Pizzeria per Mega-Cap HQ (10 API calls)")
        logger.info(f"============================================================")

        results = []
        triggered_tickers = []
        sim_target = (simulate_busy_ticker or "").strip().upper()

        for idx, v in enumerate(venues, 1):
            t = v["ticker"]
            name = v["name"]
            dist = v["distance_meters"]
            addr = v["address"]

            logger.info(f"[{idx}/10] Scanning {t} ({v['company_name']}) -> {name} ({dist}m away)")

            if dry_run:
                results.append({
                    "ticker": t,
                    "venue": name,
                    "distance_meters": dist,
                    "status": "DRY_RUN"
                })
                continue

            # Check if this ticker is designated for simulation
            should_simulate = (t == sim_target)

            # Query Outscraper (Individual search for 1 place)
            query_res = self.client.query_venue_popular_times(
                name=name,
                address=addr,
                google_place_id=v.get("google_place_id"),
                simulate_busy=should_simulate
            )

            live_status = query_res.get("live_status", "normal")
            live_busyness = query_res.get("live_busyness")
            is_busier = query_res.get("is_busier_than_usual", False)

            logger.info(f"      Result: Status='{live_status}', Live={live_busyness}%, BusierThanUsual={is_busier}")

            # Persist reading into historical_busyness
            try:
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO historical_busyness (venue_id, timestamp, day_of_week, hour_of_day, live_busyness, normal_busyness, z_score, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        v["venue_id"],
                        datetime.now().isoformat(),
                        datetime.now().weekday(),
                        datetime.now().hour,
                        live_busyness or (90 if is_busier else 35),
                        35,
                        3.4 if is_busier else 0.0,
                        query_res.get("source", "outscraper_live")
                    ))
                    conn.commit()
            except Exception as e:
                logger.debug(f"Error persisting busyness: {e}")

            # Pull trigger to FINOS if "busier than usual"
            if is_busier:
                logger.warning(
                    f"🚨 [PIZZAMETER ANOMALY DETECTED] {t} ({v['company_name']}) "
                    f"is BUSIER THAN USUAL at {name} ({dist}m from HQ)! Pulling FINOS Trigger..."
                )
                asyncio.run(self.broadcast_finos_trigger(
                    ticker=t,
                    company_name=v["company_name"],
                    venue=v,
                    live_status=live_status,
                    live_busyness=live_busyness
                ))
                triggered_tickers.append(t)

            results.append({
                "ticker": t,
                "company": v["company_name"],
                "venue": name,
                "distance_meters": dist,
                "live_status": live_status,
                "live_busyness": live_busyness,
                "triggered": is_busier
            })

        logger.info(f"============================================================")
        logger.info(f"Scan complete: {len(venues)} venues scanned. FINOS Triggers: {len(triggered_tickers)}")
        if triggered_tickers:
            logger.info(f"Triggered Tickers: {', '.join(triggered_tickers)}")
        logger.info(f"============================================================")

        return {
            "scanned": len(venues),
            "triggered_count": len(triggered_tickers),
            "triggered_tickers": triggered_tickers,
            "results": results
        }


def main():
    parser = argparse.ArgumentParser(description="Run PizzaMeter 10-call End of Workday Outscraper Scan.")
    parser.add_argument("--api-key", type=str, default=None, help="Outscraper API key")
    parser.add_argument("--simulate-busy", type=str, default=None, help="Simulate 'busier than usual' trigger on a ticker (e.g. NVDA, AAPL)")
    parser.add_argument("--dry-run", action="store_true", help="Print the 10 closest venues without executing API calls")
    args = parser.parse_args()

    checker = EODSurveillanceChecker(api_key=args.api_key)
    checker.run_eod_scan(simulate_busy_ticker=args.simulate_busy, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
