"""FINOS Common Domain Model (CDM) Serializer for PizzaMeter Trade & Signal Events."""

import json
from datetime import datetime
from typing import Dict, Any, Optional

from src.engine.models import AnomalyAlert


class CDMSerializer:
    """
    Serializes quantitative anomalies and execution proposals into
    FINOS Common Domain Model (CDM) compliant JSON schemas.
    """

    @staticmethod
    def serialize_anomaly_event(alert: AnomalyAlert, recommended_strategy: str = "VOLATILITY_EXPANSION") -> Dict[str, Any]:
        """
        Create a FINOS CDM Workflow Event payload encapsulating the anomaly signal
        and proposed execution instructions.
        """
        timestamp_iso = alert.timestamp.isoformat()
        date_str = alert.timestamp.strftime("%Y-%m-%d")

        cdm_payload = {
            "rosetta": {
                "model": "FINOS Common Domain Model (CDM)",
                "modelVersion": "5.0.0",
                "schemaType": "org.finos.cdm.Event"
            },
            "header": {
                "messageId": f"MSG-{alert.alert_id}",
                "sentTimestamp": timestamp_iso,
                "source": {
                    "system": "PizzaMeterQuant",
                    "subsystem": "AnomalyEngine.ZScoreCluster",
                    "version": "1.0.0"
                }
            },
            "businessEvent": {
                "eventDate": date_str,
                "eventQualifier": "ExecutionInstruction",
                "instruction": [
                    {
                        "instructionType": "ProposedOrder",
                        "intent": recommended_strategy,
                        "lineage": {
                            "signalSource": "PentagonPizzaIndexAltData",
                            "clusterZScore": alert.cluster_z_score,
                            "reportingVenuesCount": alert.reporting_venues,
                            "triggerThreshold": 2.2,
                            "confidenceInterval": "98.5%"
                        },
                        "proposedTrade": {
                            "tradeIdentifier": [
                                {
                                    "identifierType": "InternalTradeID",
                                    "identifierValue": f"TRD-{alert.alert_id}"
                                }
                            ],
                            "tradeDate": date_str,
                            "tradableProduct": {
                                "productTaxonomy": [
                                    {
                                        "source": "ISDA",
                                        "value": "Equity:SingleStock"
                                    }
                                ],
                                "productIdentification": {
                                    "primaryId": alert.ticker,
                                    "idScheme": "Ticker",
                                    "exchange": "XNAS",
                                    "companyName": alert.company_name
                                }
                            },
                            "executionDetails": {
                                "executionType": "Algorithmic",
                                "executionVenue": "AlpacaPaper",
                                "orderStrategy": "OpeningRangeBreakoutBracket",
                                "timeInForce": "Day",
                                "currency": "USD"
                            }
                        }
                    }
                ],
                "eventEffect": {
                    "transferredStatus": "PreExecutionAlert"
                }
            },
            "provenance": {
                "venueBreakdown": alert.venues_detail
            }
        }
        return cdm_payload

    @staticmethod
    def to_pretty_json(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, indent=2)
