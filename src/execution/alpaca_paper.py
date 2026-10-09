"""Alpaca Paper Trading Integration for Automated Signal Execution."""

import os
import uuid
import logging
from typing import Dict, Any, Optional
import requests

from src.engine.models import AnomalyAlert
from src.execution.risk_manager import RiskManager

logger = logging.getLogger("AlpacaPaperExecutor")


class AlpacaPaperExecutor:
    """
    Handles paper order execution via Alpaca Paper API when an anomaly trigger occurs.
    Includes simulation mode when live API credentials are not supplied.
    """

    def __init__(
        self,
        api_key_id: Optional[str] = None,
        api_secret_key: Optional[str] = None,
        base_url: str = "https://paper-api.alpaca.markets",
        risk_manager: Optional[RiskManager] = None
    ):
        self.api_key_id = api_key_id or os.getenv("ALPACA_PAPER_KEY_ID")
        self.api_secret_key = api_secret_key or os.getenv("ALPACA_PAPER_SECRET_KEY")
        self.base_url = base_url
        self.risk_manager = risk_manager or RiskManager()

        self.is_live_configured = bool(
            self.api_key_id
            and self.api_secret_key
            and not self.api_key_id.startswith("YOUR_")
        )

        if self.is_live_configured:
            logger.info("Alpaca Paper API configured with active credentials.")
        else:
            logger.info("Alpaca Paper API running in Sandbox Simulation mode (simulated paper broker).")

    def execute_anomaly_order(self, alert: AnomalyAlert) -> Dict[str, Any]:
        """
        Execute an event-driven volatility position for the triggered ticker.
        """
        ticker = alert.ticker

        # 1. Verify risk permissions
        permitted, reason = self.risk_manager.check_trade_permitted(ticker)
        if not permitted:
            logger.warning(f"Trade for {ticker} rejected by RiskManager: {reason}")
            return {
                "success": False,
                "status": "REJECTED_BY_RISK",
                "reason": reason,
                "order_id": None
            }

        # 2. Live Alpaca Paper API submission
        if self.is_live_configured:
            try:
                headers = {
                    "APCA-API-KEY-ID": self.api_key_id,
                    "APCA-API-SECRET-KEY": self.api_secret_key,
                    "Content-Type": "application/json"
                }

                # Submit an Opening Range Breakout or Market-On-Open bracket order
                order_payload = {
                    "symbol": ticker,
                    "qty": 10,
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "opg",  # Market on Open
                    "order_class": "bracket",
                    "take_profit": {
                        "limit_price": 0  # Dynamic on live market
                    },
                    "stop_loss": {
                        "stop_price": 0
                    }
                }

                url = f"{self.base_url}/v2/orders"
                resp = requests.post(url, json=order_payload, headers=headers, timeout=10)
                if resp.status_code in [200, 201]:
                    order_data = resp.json()
                    order_id = order_data.get("id")
                    self.risk_manager.record_trade_execution(ticker)
                    logger.info(f"Alpaca Paper Order Submitted successfully: {order_id} for {ticker}")
                    return {
                        "success": True,
                        "status": "SUBMITTED",
                        "order_id": order_id,
                        "details": order_data
                    }
                else:
                    logger.error(f"Alpaca API error {resp.status_code}: {resp.text}")
                    return {
                        "success": False,
                        "status": "API_ERROR",
                        "reason": resp.text,
                        "order_id": None
                    }
            except Exception as e:
                logger.error(f"Exception submitting order to Alpaca: {e}")
                return {
                    "success": False,
                    "status": "EXCEPTION",
                    "reason": str(e),
                    "order_id": None
                }

        # 3. High-Fidelity Simulation Mode
        simulated_order_id = f"sim_ord_{uuid.uuid4().hex[:10]}"
        self.risk_manager.record_trade_execution(ticker)
        logger.info(
            f"[SIMULATED ALPACA PAPER] Order {simulated_order_id} filled for {ticker} "
            f"(Strategy: Volatility Expansion / ORB Bracket, Z-Score: {alert.cluster_z_score})"
        )
        return {
            "success": True,
            "status": "SIMULATED_FILLED",
            "order_id": simulated_order_id,
            "strategy": "OpeningRangeBreakoutBracket",
            "symbol": ticker,
            "notional": "$10,000.00",
            "confidence": f"{round(alert.cluster_z_score, 2)} Z-Score"
        }
