"""Unit tests for FINOS Common Domain Model (CDM) serialization."""

import unittest
from datetime import datetime
from src.engine.models import AnomalyAlert
from src.finos.cdm_serializer import CDMSerializer


class TestCDMSerializer(unittest.TestCase):
    def test_cdm_structure_and_lineage(self):
        alert = AnomalyAlert(
            alert_id="ALT_TEST_001",
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            timestamp=datetime(2026, 10, 5, 21, 30, 0),
            cluster_z_score=3.14,
            reporting_venues=3,
            venues_detail=[
                {"venue_id": "v1", "live": 85, "normal": 20, "z_score": 3.5},
                {"venue_id": "v2", "live": 75, "normal": 22, "z_score": 2.8}
            ],
            fdc3_payload={},
            cdm_payload={}
        )

        cdm = CDMSerializer.serialize_anomaly_event(alert)

        # Assert FINOS CDM header
        self.assertEqual(cdm["rosetta"]["model"], "FINOS Common Domain Model (CDM)")
        self.assertEqual(cdm["rosetta"]["modelVersion"], "5.0.0")

        # Assert Business Event structure
        b_event = cdm["businessEvent"]
        self.assertEqual(b_event["eventDate"], "2026-10-05")
        self.assertEqual(b_event["eventQualifier"], "ExecutionInstruction")

        instruction = b_event["instruction"][0]
        self.assertEqual(instruction["instructionType"], "ProposedOrder")
        self.assertEqual(instruction["lineage"]["clusterZScore"], 3.14)
        self.assertEqual(instruction["lineage"]["signalSource"], "PentagonPizzaIndexAltData")

        # Assert Tradable Product
        product = instruction["proposedTrade"]["tradableProduct"]["productIdentification"]
        self.assertEqual(product["primaryId"], "NVDA")
        self.assertEqual(product["exchange"], "XNAS")


if __name__ == "__main__":
    unittest.main()
