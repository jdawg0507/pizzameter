/**
 * PizzaMeter Real-Time Dashboard Controller
 * Integrates FDC3 WebSocket feed, Blotter Table, TradingView Chart, and Leaflet Geo-Radar Map.
 */

import { TradingViewManager } from "./tradingview_widget.js";
import { PizzaMeterMapManager } from "./map_widget.js";

class PizzaMeterDashboard {
  constructor() {
    this.ws = null;
    this.wsUrl = "ws://127.0.0.1:8765";
    this.tableData = [];
    this.selectedTicker = "NVDA";
    this.currentViewMode = "map"; // "chart", "map", or "split"
    this.tvManager = null;
    this.mapManager = null;

    this.init();
  }

  init() {
    this.tvManager = new TradingViewManager("tv_chart_container");
    this.mapManager = new PizzaMeterMapManager("map_container");
    this.mapManager.setTickerSelectCallback((ticker) => this.onSelectTicker(ticker));

    this.setupUIListeners();
    this.connectWebSocket();
  }

  setupUIListeners() {
    const triggerBtn = document.getElementById("btn_simulate_spike");
    const tickerInput = document.getElementById("input_target_ticker");
    const searchFilter = document.getElementById("search_ticker_filter");

    // Late-Night Spike injection button
    if (triggerBtn && tickerInput) {
      triggerBtn.addEventListener("click", () => {
        const sym = (tickerInput.value || "NVDA").trim().toUpperCase();
        this.sendSpikeTrigger(sym, 3.25);
      });
    }

    // Ticker blotter search filter
    if (searchFilter) {
      searchFilter.addEventListener("input", (e) => {
        this.renderTable(e.target.value.trim().toUpperCase());
      });
    }

    // View Switcher Tabs (Chart vs Map vs Split)
    const btnChart = document.getElementById("tab_chart_view");
    const btnMap = document.getElementById("tab_map_view");
    const btnSplit = document.getElementById("tab_split_view");

    if (btnChart && btnMap && btnSplit) {
      btnChart.addEventListener("click", () => this.setViewMode("chart"));
      btnMap.addEventListener("click", () => this.setViewMode("map"));
      btnSplit.addEventListener("click", () => this.setViewMode("split"));
    }

    // Map Specific Controls
    const btnOverview = document.getElementById("btn_map_overview");
    const btnRecenter = document.getElementById("btn_map_recenter");

    if (btnOverview) {
      btnOverview.addEventListener("click", () => {
        this.mapManager.resetViewOverview();
        this.logEvent("MAP", "Zoomed out to USA Overview (120 NASDAQ-100 Corporate HQs)");
      });
    }

    if (btnRecenter) {
      btnRecenter.addEventListener("click", () => {
        this.mapManager.focusTicker(this.selectedTicker);
        this.logEvent("MAP", `Re-centered 1-mile radar on ${this.selectedTicker} HQ`);
      });
    }
  }

  setViewMode(mode) {
    this.currentViewMode = mode;
    const wrapper = document.getElementById("visualizer_wrapper");
    const btnChart = document.getElementById("tab_chart_view");
    const btnMap = document.getElementById("tab_map_view");
    const btnSplit = document.getElementById("tab_split_view");

    if (wrapper) {
      wrapper.className = `visualizer-body view-${mode}`;
    }

    [btnChart, btnMap, btnSplit].forEach((btn) => btn?.classList.remove("active"));
    if (mode === "chart") btnChart?.classList.add("active");
    if (mode === "map") btnMap?.classList.add("active");
    if (mode === "split") btnSplit?.classList.add("active");

    // Let Leaflet recalculate container dimensions when toggling
    this.mapManager.invalidateSize();
  }

  connectWebSocket() {
    const pulseDot = document.getElementById("ws_pulse_dot");
    const statusText = document.getElementById("ws_status_text");

    console.log(`Connecting to FDC3 WebSocket at ${this.wsUrl}...`);
    this.ws = new WebSocket(this.wsUrl);

    this.ws.onopen = () => {
      console.log("Connected to PizzaMeter FDC3 bus.");
      if (pulseDot) pulseDot.className = "pulse-dot";
      if (statusText) statusText.textContent = "FINOS FDC3 Bus Online";
      this.logEvent("SYSTEM", "Connected to local FDC3 WebSocket broker (ws://127.0.0.1:8765)");
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleMessage(msg);
      } catch (err) {
        console.error("Error parsing WS message:", err);
      }
    };

    this.ws.onclose = () => {
      console.warn("FDC3 WebSocket disconnected. Retrying in 3s...");
      if (pulseDot) pulseDot.className = "pulse-dot disconnected";
      if (statusText) statusText.textContent = "FDC3 Bus Offline (Reconnecting)";
      setTimeout(() => this.connectWebSocket(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };
  }

  handleMessage(msg) {
    if (msg.type === "TELEMETRY_UPDATE" || msg.type === "SNAPSHOT") {
      const data = msg.data?.data || msg.data || [];
      if (Array.isArray(data)) {
        this.tableData = data;
        this.updateMetrics(data);
        this.renderTable();
        this.mapManager.updateTelemetry(data);
      }
    } else if (msg.type === "FDC3_CONTEXT") {
      const ctx = msg.context;
      const ticker = ctx?.id?.ticker;
      const z = ctx?.metadata?.clusterZScore;
      this.logEvent("FDC3_ALERT", `[${ticker}] Anomaly Detected! Cluster Z-Score = ${z}`, "log-alert");
      if (ticker) {
        this.onSelectTicker(ticker);
      }
    } else if (msg.type === "FDC3_INTENT") {
      const ticker = msg.context?.id?.ticker;
      this.logEvent("FDC3_INTENT", `Raised Intent: ${msg.intent} for ${ticker}`, "log-intent");
      if (ticker) {
        this.onSelectTicker(ticker);
      }
    }
  }

  updateMetrics(data) {
    const totalCountEl = document.getElementById("metric_total_hqs");
    const anomalyCountEl = document.getElementById("metric_active_anomalies");
    const meanZEl = document.getElementById("metric_mean_zscore");

    const total = data.length;
    const anomalies = data.filter((d) => d.cluster_z_score >= 2.2).length;
    const avgZ = total > 0 ? (data.reduce((acc, d) => acc + d.cluster_z_score, 0) / total).toFixed(2) : "0.00";

    if (totalCountEl) totalCountEl.textContent = total;
    if (anomalyCountEl) {
      anomalyCountEl.textContent = anomalies;
      anomalyCountEl.className = anomalies > 0 ? "metric-value pink" : "metric-value green";
    }
    if (meanZEl) meanZEl.textContent = avgZ;
  }

  renderTable(filterText = "") {
    const tbody = document.getElementById("blotter_table_body");
    if (!tbody) return;

    let rows = [...this.tableData];
    if (filterText) {
      rows = rows.filter(
        (r) =>
          r.ticker.includes(filterText) ||
          (r.company && r.company.toUpperCase().includes(filterText))
      );
    }
    rows.sort((a, b) => b.cluster_z_score - a.cluster_z_score);

    tbody.innerHTML = "";

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      if (row.ticker === this.selectedTicker) {
        tr.className = "selected";
      }

      let zClass = "z-normal";
      let statusTag = "NORMAL";
      if (row.cluster_z_score >= 2.2) {
        zClass = "z-critical";
        statusTag = "CRITICAL ANOMALY";
      } else if (row.cluster_z_score >= 1.2) {
        zClass = "z-elevated";
        statusTag = "ELEVATED";
      }

      tr.innerHTML = `
        <td><span class="ticker-pill cyber-chamfer-sm">${row.ticker}</span></td>
        <td style="font-weight: 500;">${row.company}</td>
        <td style="color: var(--text-muted); font-size: 0.78rem;">${row.sector || "Tech"}</td>
        <td style="color: var(--text-muted);">${row.avg_normal}%</td>
        <td><strong style="color: var(--text-bright);">${row.avg_live}%</strong></td>
        <td><span class="z-tag cyber-chamfer-sm ${zClass}">${row.cluster_z_score > 0 ? "+" : ""}${row.cluster_z_score}</span></td>
        <td><span class="z-tag cyber-chamfer-sm ${zClass}">${statusTag}</span></td>
      `;

      tr.addEventListener("click", () => {
        this.onSelectTicker(row.ticker);
      });

      tbody.appendChild(tr);
    });
  }

  onSelectTicker(ticker) {
    this.selectedTicker = ticker.toUpperCase();

    // 1. Sync TradingView Chart
    this.tvManager.setTicker(this.selectedTicker);

    // 2. Sync Leaflet Map Radar
    this.mapManager.focusTicker(this.selectedTicker);

    // 3. Update Blotter table active row highlight
    const rows = document.querySelectorAll("#blotter_table_body tr");
    rows.forEach((r) => {
      const sym = r.querySelector(".ticker-pill")?.textContent;
      if (sym === this.selectedTicker) {
        r.classList.add("selected");
      } else {
        r.classList.remove("selected");
      }
    });

    const activeTickerEl = document.getElementById("active_chart_ticker");
    if (activeTickerEl) activeTickerEl.textContent = this.selectedTicker;

    this.logEvent("DESKTOP_SYNC", `FDC3 Synced Chart & Geo-Radar Map onto ${this.selectedTicker}`);
  }

  sendSpikeTrigger(ticker, zScore) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      alert("FDC3 WebSocket server is not connected. Start daemon first!");
      return;
    }

    const payload = {
      action: "RAISE_INTENT",
      intent: "ViewInstrument",
      context: {
        type: "fdc3.instrument",
        id: { ticker: ticker },
        metadata: {
          signalType: "MANUAL_SPIKE_TRIGGER",
          clusterZScore: zScore,
          reportingPizzerias: 4
        }
      }
    };
    this.ws.send(JSON.stringify(payload));
    this.logEvent("INTENT_SENT", `Raised FDC3 ViewInstrument Intent for ${ticker} (Z=${zScore})`);
  }

  logEvent(category, text, extraClass = "") {
    const stream = document.getElementById("event_log_stream");
    if (!stream) return;

    const timeStr = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = `log-entry ${extraClass}`;
    entry.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-ticker">[${category}]</span> ${text}`;
    stream.prepend(entry);
  }
}

// Initialize on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.pizzaDashboard = new PizzaMeterDashboard();
});
