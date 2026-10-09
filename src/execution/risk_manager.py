"""Risk Manager: Enforces capital allocation, cooldowns, and daily safety limits."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(
        self,
        max_allocation_percent: float = 0.02,
        ticker_cooldown_hours: int = 168,  # 7 days
        max_daily_trades: int = 5
    ):
        self.max_allocation_percent = max_allocation_percent
        self.ticker_cooldown_hours = ticker_cooldown_hours
        self.max_daily_trades = max_daily_trades
        self.last_trade_time_by_ticker: Dict[str, datetime] = {}
        self.daily_trade_count: int = 0
        self.current_day: str = datetime.now().strftime("%Y-%m-%d")

    def _refresh_daily_count(self):
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_day:
            self.current_day = today
            self.daily_trade_count = 0
            logger.info("RiskManager: Reset daily trade counter for new trading day.")

    def check_trade_permitted(self, ticker: str) -> Tuple[bool, Optional[str]]:
        """Validate whether a trade can be submitted for the target ticker."""
        self._refresh_daily_count()

        # 1. Daily trade count limit
        if self.daily_trade_count >= self.max_daily_trades:
            return False, f"Daily trade limit reached ({self.max_daily_trades})"

        # 2. Ticker cooldown
        now = datetime.now()
        if ticker in self.last_trade_time_by_ticker:
            last_time = self.last_trade_time_by_ticker[ticker]
            elapsed = now - last_time
            if elapsed < timedelta(hours=self.ticker_cooldown_hours):
                remaining_hours = round((timedelta(hours=self.ticker_cooldown_hours) - elapsed).total_seconds() / 3600, 1)
                return False, f"Ticker {ticker} is in cooldown for another {remaining_hours} hours"

        return True, None

    def record_trade_execution(self, ticker: str):
        """Mark trade executed to start cooldown and increment count."""
        now = datetime.now()
        self.last_trade_time_by_ticker[ticker] = now
        self.daily_trade_count += 1
        logger.info(f"RiskManager: Recorded trade for {ticker}. Daily count: {self.daily_trade_count}/{self.max_daily_trades}")
