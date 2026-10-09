/**
 * TradingView Widget Synchronizer
 * Automatically syncs the chart view when an FDC3 context alert is received
 * or when the user clicks a ticker in the blotter table.
 */

export class TradingViewManager {
  constructor(containerId = "tv_chart_container") {
    this.containerId = containerId;
    this.currentTicker = "NVDA";
    this.initChart(this.currentTicker);
  }

  initChart(ticker) {
    this.currentTicker = ticker.toUpperCase();
    const container = document.getElementById(this.containerId);
    if (!container) return;

    container.innerHTML = "";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container";
    widgetDiv.style.width = "100%";
    widgetDiv.style.height = "100%";

    const innerDiv = document.createElement("div");
    innerDiv.id = "tradingview_inner_chart";
    innerDiv.style.width = "100%";
    innerDiv.style.height = "100%";
    widgetDiv.appendChild(innerDiv);

    container.appendChild(widgetDiv);

    // Embed official TradingView widget script
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if (typeof TradingView !== "undefined") {
        new TradingView.widget({
          autosize: true,
          symbol: `NASDAQ:${this.currentTicker}`,
          interval: "15",
          timezone: "exchange",
          theme: "dark",
          style: "1",
          locale: "en",
          toolbar_bg: "#0a0c10",
          enable_publishing: false,
          hide_side_toolbar: false,
          allow_symbol_change: true,
          container_id: "tradingview_inner_chart"
        });
      }
    };
    document.head.appendChild(script);
  }

  setTicker(ticker) {
    if (ticker && ticker.toUpperCase() !== this.currentTicker) {
      console.log(`[TradingView] Switching chart symbol to: ${ticker}`);
      this.initChart(ticker);
    }
  }
}
