"""FDC3 Context & Intent Bridge over WebSocket for Desktop Interoperability."""

import json
import asyncio
import logging
from typing import Dict, Any, Set, Optional
import websockets

from src.engine.models import AnomalyAlert

logger = logging.getLogger("FDC3Bridge")


class FDC3Bridge:
    """
    Broadcasts FDC3 Context data and coordinates Intents over WebSockets.
    Complies with FINOS FDC3 2.0 specifications.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.connected_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.server = None
        self.latest_state: Dict[str, Any] = {}

    @staticmethod
    def create_fdc3_context(alert: AnomalyAlert) -> Dict[str, Any]:
        """Format an AnomalyAlert as a compliant FDC3 instrument context."""
        return {
            "type": "fdc3.instrument",
            "name": alert.company_name,
            "id": {
                "ticker": alert.ticker,
                "BBG": f"{alert.ticker} US Equity",
                "RIC": f"{alert.ticker}.OQ"
            },
            "metadata": {
                "signalType": "ALT_DATA_ANOMALY",
                "source": "PizzaMeterQuant",
                "alertId": alert.alert_id,
                "clusterZScore": alert.cluster_z_score,
                "reportingPizzerias": alert.reporting_venues,
                "timestamp": alert.timestamp.isoformat(),
                "recommendedAction": "VOLATILITY_EXPANSION",
                "intent": "ViewInstrument"
            }
        }

    async def register(self, websocket):
        self.connected_clients.add(websocket)
        logger.info(f"FDC3 Client connected: {websocket.remote_address} (Total: {len(self.connected_clients)})")
        # Send current state snapshot immediately to new client
        if self.latest_state:
            await websocket.send(json.dumps({
                "type": "SNAPSHOT",
                "data": self.latest_state
            }))

    async def unregister(self, websocket):
        if websocket in self.connected_clients:
            self.connected_clients.remove(websocket)
            logger.info(f"FDC3 Client disconnected. (Total: {len(self.connected_clients)})")

    async def broadcast_alert(self, alert: AnomalyAlert):
        """Broadcast FDC3 context message to all connected clients."""
        fdc3_msg = {
            "type": "FDC3_CONTEXT",
            "context": self.create_fdc3_context(alert),
            "cdm": alert.cdm_payload
        }
        await self.broadcast_raw(fdc3_msg)

    async def broadcast_raw(self, message: Dict[str, Any]):
        if not self.connected_clients:
            logger.debug("No FDC3 clients connected to receive message.")
            return

        payload = json.dumps(message)
        disconnected = set()
        for ws in self.connected_clients:
            try:
                await ws.send(payload)
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                disconnected.add(ws)

        for ws in disconnected:
            await self.unregister(ws)

    async def handler(self, websocket, path=None):
        await self.register(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get("action")
                    if action == "PING":
                        await websocket.send(json.dumps({"type": "PONG"}))
                    elif action == "RAISE_INTENT":
                        # Echo intent back out to other desktop windows
                        intent = data.get("intent", "ViewInstrument")
                        context = data.get("context", {})
                        logger.info(f"Intent raised by client: {intent} for {context.get('id', {}).get('ticker')}")
                        await self.broadcast_raw({
                            "type": "FDC3_INTENT",
                            "intent": intent,
                            "context": context
                        })
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            logger.debug(f"Client connection closed: {e}")
        finally:
            await self.unregister(websocket)

    async def start(self):
        logger.info(f"Starting FDC3 WebSocket Server on ws://{self.host}:{self.port}...")
        self.server = await websockets.serve(self.handler, self.host, self.port)
        return self.server
