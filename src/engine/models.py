"""Data models for the PizzaMeter quantitative pipeline."""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class TickerHQ:
    ticker: str
    name: str
    sector: str
    hq_address: str
    latitude: float
    longitude: float
    timezone: str
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VenuePOI:
    venue_id: str
    ticker: str
    name: str
    cuisine: str
    address: str
    distance_meters: float
    latitude: float
    longitude: float
    osm_id: Optional[str] = None
    google_place_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BusynessReading:
    venue_id: str
    timestamp: datetime
    day_of_week: int
    hour_of_day: int
    live_busyness: Optional[int]
    normal_busyness: int
    z_score: Optional[float] = None
    data_source: str = "baseline"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class AnomalyAlert:
    alert_id: str
    ticker: str
    company_name: str
    timestamp: datetime
    cluster_z_score: float
    reporting_venues: int
    venues_detail: List[Dict[str, Any]]
    fdc3_payload: Dict[str, Any]
    cdm_payload: Dict[str, Any]
    executed: bool = False
    order_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d
