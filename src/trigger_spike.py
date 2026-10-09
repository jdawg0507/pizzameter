"""Interactive CLI tool to trigger simulated pizza spikes on targeted tickers for testing."""

import argparse
import asyncio
import json
import logging
import websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SpikeTrigger")


async def raise_spike_intent(ticker: str, z_score: float = 3.2, host: str = "127.0.0.1", port: int = 8765):
    uri = f"ws://{host}:{port}"
    try:
        async with websockets.connect(uri) as websocket:
            context = {
                "type": "fdc3.instrument",
                "name": f"Simulated Target {ticker}",
                "id": {"ticker": ticker.upper()},
                "metadata": {
                    "signalType": "MANUAL_SPIKE_TRIGGER",
                    "clusterZScore": z_score,
                    "reportingPizzerias": 4,
                    "intent": "ViewInstrument"
                }
            }
            payload = {
                "action": "RAISE_INTENT",
                "intent": "ViewInstrument",
                "context": context
            }
            await websocket.send(json.dumps(payload))
            logger.info(f"Broadcasted manual FDC3 Intent for {ticker.upper()} with Z={z_score} to ws://{host}:{port}")
    except Exception as e:
        logger.error(f"Failed to connect to FDC3 WebSocket on {uri}: {e}")
        logger.info("Make sure the PizzaMeter daemon or FDC3 bridge is running (python3 -m src.scraper.daemon).")


def main():
    parser = argparse.ArgumentParser(description="Trigger a PizzaMeter foot traffic spike on a ticker.")
    parser.add_argument("--ticker", type=str, default="NVDA", help="Target ticker (e.g. NVDA, AAPL, MSFT)")
    parser.add_argument("--zscore", type=float, default=3.15, help="Simulated cluster Z-score (e.g. 2.8)")
    args = parser.parse_args()

    asyncio.run(raise_spike_intent(args.ticker, args.zscore))


if __name__ == "__main__":
    main()
