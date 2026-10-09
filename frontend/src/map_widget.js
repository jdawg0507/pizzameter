/**
 * PizzaMeter HQ & Pizzeria Geo-Radar Map
 * Powered by Leaflet.js and CartoDB Dark Matter tiles.
 * Displays all NASDAQ-100 corporate headquarters and the 1-mile perimeter of surrounding pizzerias.
 */

import { GEO_CATALOG } from "./geo_catalog.js";

export class PizzaMeterMapManager {
  constructor(containerId = "map_container") {
    this.containerId = containerId;
    this.map = null;
    this.hqMarkers = {};
    this.venueMarkers = [];
    this.perimeterCircle = null;
    this.selectedTicker = "NVDA";
    this.telemetryByTicker = {};
    this.onTickerSelectCallback = null;

    this.initMap();
  }

  setTickerSelectCallback(cb) {
    this.onTickerSelectCallback = cb;
  }

  initMap() {
    const container = document.getElementById(this.containerId);
    if (!container || !window.L) {
      console.warn("Map container or Leaflet not ready.");
      return;
    }

    // Default view centered on Silicon Valley / US Overview
    const defaultCenter = [37.37, -121.96]; // Santa Clara (NVDA)
    this.map = window.L.map(this.containerId, {
      center: defaultCenter,
      zoom: 14,
      zoomControl: false,
      attributionControl: false
    });

    // Add sleek dark zoom controls to top-right
    window.L.control.zoom({ position: "topright" }).addTo(this.map);

    // CartoDB Dark Matter tile layer
    window.L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      {
        maxZoom: 19,
        subdomains: "abcd",
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }
    ).addTo(this.map);

    // Render all 120 NASDAQ-100 Corporate HQs
    this.renderAllHQs();

    // Select default ticker
    this.focusTicker("NVDA");
  }

  renderAllHQs() {
    if (!this.map) return;

    Object.values(GEO_CATALOG).forEach((hq) => {
      if (!hq.latitude || !hq.longitude) return;

      const isDefault = hq.ticker === "NVDA";
      const icon = window.L.divIcon({
        className: "custom-hq-marker-wrap",
        html: `
          <div class="hq-pin cyber-chamfer-sm ${isDefault ? 'active' : ''}" id="hq_pin_${hq.ticker}">
            <span class="hq-dot"></span>
            <span class="hq-label">${hq.ticker}</span>
          </div>
        `,
        iconSize: [64, 26],
        iconAnchor: [32, 13]
      });

      const marker = window.L.marker([hq.latitude, hq.longitude], { icon: icon }).addTo(this.map);

      // Popup on click
      marker.bindTooltip(`
        <div style="font-family: var(--font-body); font-size: 0.8rem; padding: 4px;">
          <strong style="color: var(--accent-cyan); font-family: var(--font-head);">${hq.ticker}</strong> — ${hq.company}<br/>
          <span style="color: #6b7280; font-size: 0.72rem; font-family: var(--font-label);">${hq.hq_address}</span>
        </div>
      `, { direction: "top", offset: [0, -12], opacity: 0.95 });

      marker.on("click", () => {
        if (this.onTickerSelectCallback) {
          this.onTickerSelectCallback(hq.ticker);
        } else {
          this.focusTicker(hq.ticker);
        }
      });

      this.hqMarkers[hq.ticker] = marker;
    });
  }

  focusTicker(ticker) {
    this.selectedTicker = ticker.toUpperCase();
    const hq = GEO_CATALOG[this.selectedTicker];
    if (!hq || !this.map) return;

    // Pan & Zoom to HQ smoothly
    this.map.flyTo([hq.latitude, hq.longitude], 14, {
      duration: 1.0,
      easeLinearity: 0.25
    });

    // Update active pin styling
    Object.keys(this.hqMarkers).forEach((sym) => {
      const pinEl = document.getElementById(`hq_pin_${sym}`);
      if (pinEl) {
        if (sym === this.selectedTicker) {
          pinEl.classList.add("active");
        } else {
          pinEl.classList.remove("active");
        }
      }
    });

    // Draw 1-Mile (1609m) Radar Perimeter Circle
    if (this.perimeterCircle) {
      this.map.removeLayer(this.perimeterCircle);
    }

    const telemetry = this.telemetryByTicker[this.selectedTicker];
    const isAnomaly = telemetry && telemetry.cluster_z_score >= 2.2;
    const isElevated = telemetry && telemetry.cluster_z_score >= 1.2;

    let circleColor = "#00d4ff";
    let circleFill = "rgba(0, 212, 255, 0.08)";
    if (isAnomaly) {
      circleColor = "#ff00ff";
      circleFill = "rgba(255, 0, 255, 0.16)";
    } else if (isElevated) {
      circleColor = "#ffaa00";
      circleFill = "rgba(255, 170, 0, 0.12)";
    }

    this.perimeterCircle = window.L.circle([hq.latitude, hq.longitude], {
      color: circleColor,
      fillColor: circleFill,
      fillOpacity: 0.25,
      radius: 1600, // 1 mile
      weight: 1.5,
      dashArray: "4, 6"
    }).addTo(this.map);

    // Clear old venue markers
    this.clearVenueMarkers();

    // Render Pizzerias around this HQ
    const venues = (telemetry && telemetry.venues) ? telemetry.venues : hq.venues;
    if (venues && venues.length > 0) {
      venues.forEach((v) => {
        if (!v.latitude || !v.longitude) return;

        const live = v.live !== undefined ? v.live : (v.live_busyness !== undefined ? v.live_busyness : "--");
        const normal = v.normal !== undefined ? v.normal : (v.normal_busyness !== undefined ? v.normal_busyness : "--");
        const z = v.z_score !== undefined ? v.z_score : (v.cluster_z_score !== undefined ? v.cluster_z_score : 0);

        let pinClass = "pizza-pin-normal";
        if (z >= 2.2) {
          pinClass = "pizza-pin-critical";
        } else if (z >= 1.2) {
          pinClass = "pizza-pin-elevated";
        }

        const pizzaIcon = window.L.divIcon({
          className: "custom-pizza-marker-wrap",
          html: `
            <div class="pizza-pin cyber-chamfer-sm ${pinClass}">
              <span class="pizza-icon">🍕</span>
              <span class="pizza-live-badge cyber-chamfer-sm">${live}%</span>
            </div>
          `,
          iconSize: [44, 44],
          iconAnchor: [22, 22]
        });

        const vMarker = window.L.marker([v.latitude, v.longitude], { icon: pizzaIcon }).addTo(this.map);

        // Rich Tooltip
        vMarker.bindPopup(`
          <div class="map-popup-card">
            <div class="popup-title">🍕 ${v.name}</div>
            <div class="popup-sub">${v.cuisine || 'Pizza & Late-Night Delivery'}</div>
            <div class="popup-dist">📍 ${Math.round(v.distance_meters)}m from ${hq.ticker} Headquarters</div>
            <div class="popup-stat-row">
              <div class="popup-stat">
                <span class="lbl">LIVE FOOT TRAFFIC</span>
                <span class="val ${z >= 2.2 ? 'crit' : 'norm'}">${live}%</span>
              </div>
              <div class="popup-stat">
                <span class="lbl">NORMAL BASELINE</span>
                <span class="val">${normal}%</span>
              </div>
              <div class="popup-stat">
                <span class="lbl">Z-SCORE</span>
                <span class="val ${z >= 2.2 ? 'crit' : 'norm'}">${z > 0 ? '+' : ''}${z}</span>
              </div>
            </div>
            <div class="popup-addr">${v.address || 'Local Corporate Perimeter'}</div>
          </div>
        `, { maxWidth: 280, className: "dark-map-popup" });

        this.venueMarkers.push(vMarker);
      });
    }
  }

  clearVenueMarkers() {
    this.venueMarkers.forEach((m) => this.map.removeLayer(m));
    this.venueMarkers = [];
  }

  updateTelemetry(telemetryData) {
    if (!Array.isArray(telemetryData)) return;

    telemetryData.forEach((item) => {
      this.telemetryByTicker[item.ticker] = item;

      // Update HQ pin pulsing if anomaly
      const pinEl = document.getElementById(`hq_pin_${item.ticker}`);
      if (pinEl) {
        if (item.cluster_z_score >= 2.2) {
          pinEl.classList.add("anomaly-pulse");
        } else {
          pinEl.classList.remove("anomaly-pulse");
        }
      }
    });

    // If current selected ticker has updated venues, refresh them
    if (this.selectedTicker && this.telemetryByTicker[this.selectedTicker]) {
      this.focusTicker(this.selectedTicker);
    }
  }

  resetViewOverview() {
    if (!this.map) return;
    this.map.flyTo([39.82, -98.58], 4, { duration: 1.5 }); // Overview of entire USA
  }

  invalidateSize() {
    if (this.map) {
      setTimeout(() => this.map.invalidateSize(), 150);
    }
  }
}
