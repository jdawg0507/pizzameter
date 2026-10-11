# 🍕 PizzaMeter // NASDAQ-100 Late-Night Busyness Anomaly Engine

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FINOS FDC3](https://img.shields.io/badge/FINOS-FDC3%202.0-008080?style=for-the-badge)](https://fdc3.finos.org/)
[![FINOS CDM](https://img.shields.io/badge/FINOS-CDM%205.0-004D40?style=for-the-badge)](https://cdm.finos.org/)
[![Leaflet](https://img.shields.io/badge/Leaflet-1.9.4-199900?style=for-the-badge&logo=leaflet&logoColor=white)](https://leafletjs.com/)
[![TradingView](https://img.shields.io/badge/TradingView-Technical%20Charts-2962FF?style=for-the-badge&logo=tradingview&logoColor=white)](https://www.tradingview.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**An institutional-grade alternative data trading surveillance system translating the historical "Pentagon Pizza Index" into an automated, quantitative anomaly detection and execution pipeline for the NASDAQ-100.**

[Key Features](#-key-features) • [Quantitative Thesis](#-quantitative-thesis) • [Architecture](#-architecture) • [Quickstart](#-quickstart) • [Quant Web Terminal](#-quant-web-terminal) • [Project Structure](#-project-structure)

</div>

---

## 💡 Quantitative Thesis: The Pizza Index

The **"Pentagon Pizza Index"** is an intelligence community legend dating back to the Cold War and Operation Desert Storm: sudden spikes in late-night Domino's and pizza deliveries to the Pentagon, CIA, and White House consistently preceded major geopolitical conflicts or military interventions by several hours.

**PizzaMeter** translates this operational intelligence thesis into equity markets:
- Corporate crises, emergency M&A negotiations, hostile takeover defenses, and surprise product launches correlate with engineers, executives, and legal counsel working through the night.
- By continuously monitoring real-time foot traffic and popular times across **all pizzerias within a 1-mile geospatial radius** of every NASDAQ-100 corporate headquarters (e.g., Apple Park, NVIDIA HQ, Microsoft Redmond), PizzaMeter surfaces statistically significant anomalies ($Z \ge 2.2$) before news hits public wire services.
- Detected anomalies are serialized into **FINOS CDM 5.0** execution events and broadcast across desktop applications using **FINOS FDC3 2.0** context protocols.

---

## ⚡ Key Features

- **🌐 Geospatial POI Ingestion:**
  - Automated clustering of NASDAQ-100 corporate headquarters with precision coordinates.
  - OpenStreetMap Overpass API queries dynamic 1-mile radius bounding boxes to map all active food and pizza establishments.
- **📈 Real-Time Z-Score Anomaly Engine:**
  - Calculates rolling baseline foot traffic distributions $(\mu_t, \sigma_t)$ indexed by day of week and hour of day.
  - Multi-interval persistence filter: requires $Z \ge 2.2$ sustained over $\ge 2$ consecutive polling intervals to eliminate single-sample false positives.
- **🏛️ Institutional FINOS Standards Compliance:**
  - **FDC3 2.0 Desktop Interoperability:** Broadcasts `ViewInstrument` contexts and alerts over a high-throughput WebSocket bus to synchronize multi-window trader workspaces.
  - **FINOS CDM 5.0 Serialization:** Packages anomaly events into standard Common Domain Model Trade and Execution Instruction payloads.
- **🛡️ Risk-Managed Execution Simulation:**
  - Plugs into Alpaca Paper API to trigger volatility scalps, straddles, or pre-market breakout orders upon confirmed cluster anomalies.
  - Configurable cooldowns, maximum drawdown thresholds, and position limits.
- **🖥️ Cyberpunk Trading Blotter & Radar Terminal:**
  - Real-time dark-mode Blotter Table with live foot-traffic meters, baseline comparisons, and cluster Z-scores.
  - Interactive **Leaflet Radar Map** rendering 1-mile radius surveillance geofences, HQ markers, and individual pizza venue nodes.
  - Synchronized **TradingView Technical Chart** auto-focused on selected or surging tickers via FDC3.
  - Real-time audit log stream capturing all telemetry and execution dispatches.
  - **🚨 Surge Injection Tool** for instant simulation and demonstration of live anomaly spikes.

---

## 📐 Architecture

```
                       [Scheduled Daemon / Telemetry Ingestion]
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                           1. GEOSPATIAL & POI LAYER                               │
│  - Catalog of 100+ NASDAQ-100 Corporate HQs (config/nasdaq100_hqs.json)           │
│  - Overpass API 1-Mile Geofence POI Mapper (src/ingestion/osm_client.py)           │
│  - SQLite Database Store (data/pizzameter.db & data/schema.sql)                  │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                         2. QUANTITATIVE ANOMALY ENGINE                            │
│  - Rolling Baseline Distribution: Z = (Live_Traffic - μ_hourly) / σ_hourly        │
│  - Cluster Aggregation & Persistence Filter (src/engine/anomaly_detector.py)      │
│  - Trigger Criterion: Z_cluster >= 2.2 sustained across >= 2 polling cycles       │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                        3. FINOS INTEROPERABILITY LAYER                            │
│  - CDM Serializer: Encodes anomaly into FINOS CDM 5.0 ExecutionInstruction payload│
│  - FDC3 WebSocket Broker (src/finos/fdc3_bridge.py on ws://127.0.0.1:8765)         │
│  - Context Broadcasting: Type 'fdc3.instrument' & Intent 'ViewInstrument'         │
└───────────────────────────────────┬───────────────────────────────────────────────┘
                                    │
           ┌────────────────────────┴────────────────────────┐
           ▼                                                 ▼
┌─────────────────────────────────────┐   ┌─────────────────────────────────────┐
│    4a. QUANT BLOTTER TERMINAL       │   │    4b. EXECUTION SIMULATOR          │
│  - Live HTML5 / Vanilla CSS UI      │   │  - Alpaca Paper Trading Broker      │
│  - Interactive Leaflet Radar Map    │   │  - Straddle / Volatility Scalp      │
│  - Embedded TradingView Chart Widget│   │  - Position Limits & Cooldown Rules │
│  - Instant Surge Demonstration Tool │   │    (src/execution/alpaca_paper.py)  │
└─────────────────────────────────────┘   └─────────────────────────────────────┘
```

---

## 🚀 Quickstart

### Prerequisites
- Python 3.9+
- Modern Web Browser (Chrome, Safari, Firefox, Edge)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/<your-username>/pizzameter.git
cd pizzameter
pip install -r requirements.txt
```

### 2. Initialize Geocoding & Local Database
Populates `data/pizzameter.db` with NASDAQ-100 headquarters coordinates and surrounding pizzerias:
```bash
make setup
```

### 3. Run Automated Tests
Execute quantitative verification and FINOS CDM serialization tests:
```bash
make test
```

### 4. Start the Surveillance Daemon & FDC3 Bridge
Launches the background anomaly evaluation engine and WebSocket server on `ws://127.0.0.1:8765`:
```bash
make run-daemon
```

### 5. Launch the Web Trading Terminal
In a separate terminal window, start the frontend server:
```bash
make run-ui
```
Open **[http://localhost:3000](http://localhost:3000)** in your browser.

---

## 🧪 Simulating Live Spikes (Surge Injection)

To verify the end-to-end detection, alerting, and charting workflow:

### Via Terminal
Inject an abnormal 3.8σ foot traffic surge at NVIDIA (`NVDA`) headquarters:
```bash
make spike TICKER=NVDA
```
Or test any other tracked NASDAQ-100 ticker:
```bash
make spike TICKER=AAPL
make spike TICKER=MSFT
make spike TICKER=AMZN
```

### Via Web Terminal UI
1. Locate the **`> SURGE_INJECTION`** control at the top of the Blotter panel.
2. Enter a ticker symbol (e.g. `NVDA`, `TSLA`, `GOOGL`).
3. Click **⚡ INJECT PIZZA SURGE**.
4. Observe:
   - Row updates immediately with a **CRIMSON ALERT (Z ≥ 2.2)**.
   - Blotter auto-sorts to bring the anomaly to the top.
   - Radar map zooms and centers on the campus with pulsing danger rings.
   - TradingView widget auto-switches to the corresponding ticker.
   - FINOS CDM execution instruction is logged in the live telemetry stream.

---

## 🖥️ Quant Web Terminal

The frontend (`frontend/`) is engineered with Vanilla CSS and ES modules for zero-bloat, instantaneous load times, and a Bloomberg/cyberpunk quant aesthetic:

| Component | Description |
| :--- | :--- |
| **HQ Busyness Blotter** | Real-time tabular monitor with live foot-traffic meters, baseline averages, cluster Z-scores, and status badges. Search and filter by ticker. |
| **Geospatial Radar Map** | Powered by Leaflet. Features custom tactical dark tiles, NASDAQ-100 HQ markers, 1-mile geofencing circles, and individual pizza venue markers with popups. |
| **TradingView Widget** | Interactive technical candlestick charts with timeframe switching, integrated indicators, and dynamic FDC3 ticker synchronization. |
| **Visualizer Switcher** | Toggle seamlessly between **📈 Chart**, **🗺️ Radar Map**, or **🔀 Split View** side-by-side. |
| **FINOS Stream** | Chronological audit log of all WebSocket connections, heartbeat pings, FDC3 context updates, and CDM trade payloads. |

---

## 📁 Project Structure

```
pizzameter/
├── .gitignore                    # Git exclusions (database, cache, virtualenvs)
├── Makefile                      # Automation recipes (setup, test, run, spike)
├── README.md                     # Comprehensive documentation & architecture guide
├── requirements.txt              # Python runtime dependencies
├── config/
│   ├── nasdaq100_hqs.json        # 100+ NASDAQ-100 corporate HQ coordinates
│   └── settings.json             # Engine parameters, thresholds, and intervals
├── data/
│   ├── schema.sql                # Relational SQLite schema for HQs, venues, and readings
│   └── pizzameter.db             # Local SQLite database (generated via make setup)
├── frontend/
│   ├── index.html                # Single-page terminal interface
│   ├── styles/
│   │   ├── main.css              # Cyberpunk quant design system (variables, grid, chamfers)
│   │   └── leaflet.css           # Leaflet map styling
│   └── src/
│       ├── app.js                # Core controller, WebSocket client & FDC3 state
│       ├── map_widget.js         # Leaflet geospatial visualization & radar circles
│       ├── tradingview_widget.js # Dynamic TradingView widget controller
│       ├── geo_catalog.js        # Fallback HQ catalog for offline/standalone execution
│       └── leaflet.js            # Standalone Leaflet distribution
├── src/
│   ├── ingestion/
│   │   ├── osm_client.py         # OpenStreetMap Overpass API bounding-box queries
│   │   └── geo_mapper.py         # Database seeding & spatial association
│   ├── scraper/
│   │   ├── popular_times.py      # Live busyness fetcher & historical baseline model
│   │   └── daemon.py             # Periodic polling engine & WebSocket broadcaster
│   ├── engine/
│   │   ├── models.py             # Data structures (HQ, Pizzeria, Reading, AnomalyAlert)
│   │   └── anomaly_detector.py   # Statistical Z-score calculation & persistence filters
│   ├── finos/
│   │   ├── cdm_serializer.py     # FINOS Common Domain Model (CDM 5.0) serializer
│   │   └── fdc3_bridge.py        # FDC3 2.0 message broker & intent dispatcher
│   ├── execution/
│   │   ├── alpaca_paper.py       # Alpaca Paper API broker integration
│   │   └── risk_manager.py       # Portfolio limits, max loss, and trade cooldowns
│   └── trigger_spike.py          # CLI injection utility for demonstrations
└── tests/
    ├── test_anomaly_detector.py  # Unit tests for baseline math & persistence logic
    └── test_cdm_serializer.py    # Unit tests for FINOS CDM compliance
```

---

## 📊 Statistical Methodology

For each monitored headquarters $H_i$, let $\mathcal{P}(H_i)$ denote the set of pizzerias located within Euclidean distance $d \le 1.0\text{ mile}$.

1. **Hourly Baseline Normalization:**
   For each pizzeria $p \in \mathcal{P}(H_i)$ at time $t$ (day of week $w$, hour $h$):
   $$\mu_{p,w,h} = \mathbb{E}[\text{Traffic}_{p,w,h}], \quad \sigma_{p,w,h} = \mathrm{Std}[\text{Traffic}_{p,w,h}]$$

2. **Venue Z-Score:**
   $$Z_{p,t} = \frac{x_{p,t} - \mu_{p,w,h}}{\max(\sigma_{p,w,h}, \epsilon)}$$

3. **Cluster Aggregation:**
   $$Z_{H_i, t} = \frac{1}{|\mathcal{P}(H_i)|} \sum_{p \in \mathcal{P}(H_i)} Z_{p,t}$$

4. **Alert Trigger Condition:**
   An anomaly alert is triggered if and only if:
   $$Z_{H_i, t} \ge 2.2 \quad \text{for } t \in [T, T - \Delta t]$$
   where persistence threshold $\Delta t \ge 2$ intervals (preventing single-cycle spikes).

---

## ⚖️ Disclaimer

*PizzaMeter is designed for quantitative research, educational exploration, and demonstration of FINOS standards (FDC3 & CDM). It does not constitute financial advice. Any automated order dispatch functionality is wired to paper trading simulators.*

---

<div align="center">
  <sub>Built with 🍕 and Python • Powered by FINOS Standards</sub>
</div>
