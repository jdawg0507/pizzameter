# 🍕 PizzaMeter: NASDAQ-100 Late-Night Busyness Anomaly Engine

> Translating the Pentagon Pizza Index into an automated alternative data trading signal for the NASDAQ-100, built on FINOS standards (FDC3 & CDM).

---

## Architecture Overview

```
[Cron / Local Daemon]
        │  (Polls Google "Popular Times" / Live Busyness)
        ▼
[1. Geo-Mapping & Ingestion Layer]
   - NASDAQ-100 HQ Coordinates
   - 1-Mile Bounding Box POI Scraper (Overpass API)
        │
        ▼
[2. Z-Score Anomaly Engine]
   - Rolling baseline comparison: (Live - Mean_t) / StdDev_t
   - Spike Filter: S_ticker >= 2.2 sustained over >= 2 intervals
        │
        ▼
[3. FINOS Layer: Standardized Dispatch]
   - Serializes anomaly to FINOS CDM Trade/Event payload
   - Broadcasts FDC3 2.0 Intent (`ViewInstrument` / Context Alert)
        │
   ┌────┴──────────────────────────┐
   ▼                               ▼
[4a. FDC3 Trading Desktop]   [4b. Event-Driven Execution]
   - Auto-syncs blotter table  - Triggers volatility scalp /
   - Centers TradingView         straddle paper order via 
     chart on target ticker      Alpaca Paper API
```

---

## Quickstart

### 1. Requirements
- Python 3.9+ (`requests`, `websockets` installed)
- Modern web browser (Chrome, Safari, Edge)

### 2. Verify Setup & Geo-Mapping
All corporate HQs and pizzerias are pre-mapped into `data/pizzameter.db`:
```bash
make setup
```

### 3. Run Quantitative Tests
```bash
make test
```

### 4. Start the Anomaly Daemon & FDC3 Bridge
Starts the real-time polling engine and FDC3 WebSocket broker on `ws://127.0.0.1:8765`:
```bash
make run-daemon
```

### 5. Launch the Quant Terminal Dashboard
In a new terminal window:
```bash
make run-ui
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Testing Live Spikes & FDC3 Interoperability

To simulate an abnormal late-night surge at NVIDIA (`NVDA`) headquarters:
```bash
make spike TICKER=NVDA
```
Or use the **🚨 Inject Pizza Surge** button in the top of the dashboard UI.
- The blotter row highlights with a critical crimson alert.
- The TradingView chart auto-focuses on `NASDAQ:NVDA` via FDC3 context synchronization.
- A standardized **FINOS CDM 5.0** execution instruction payload is logged and submitted to the Alpaca Paper execution simulator.

---

## Directory Structure
- `config/`: NASDAQ-100 HQ coordinate catalog & system settings.
- `data/`: SQLite database and schema.
- `src/ingestion/`: Overpass OSM client & spatial clustering.
- `src/scraper/`: Busyness telemetry provider and daemon scheduler.
- `src/engine/`: Z-score calculations, cluster persistence filters, and models.
- `src/finos/`: FDC3 2.0 WebSocket bridge & FINOS CDM serializer.
- `src/execution/`: Alpaca Paper API broker and risk limits.
- `frontend/`: Real-time dark-mode quant blotter with TradingView integration.
- `tests/`: Comprehensive unit tests.
