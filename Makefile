# PizzaMeter Automation Makefile

.PHONY: help setup test run-daemon run-ui spike eod-check

help:
	@echo "PizzaMeter NASDAQ-100 Anomaly Engine Commands:"
	@echo "  make setup        - Initialize database and map all corporate HQs to pizzerias"
	@echo "  make test         - Run quantitative unit and integration tests"
	@echo "  make run-daemon   - Start the background anomaly engine and FDC3 WebSocket broker"
	@echo "  make run-ui       - Serve the frontend quant dashboard on http://localhost:3000"
	@echo "  make spike TICKER=NVDA - Inject a simulated late-night pizza spike on a ticker"
	@echo "  make eod-check    - Execute the 10-call End of Workday Outscraper Scan on Top 10 HQs"
	@echo "  make eod-check TICKER=NVDA - Run EOD scan with simulated busy trigger on a ticker"

setup:
	python3 -m src.ingestion.geo_mapper

test:
	python3 -m unittest discover tests

run-daemon:
	python3 -m src.scraper.daemon

run-ui:
	cd frontend && python3 -m http.server 3000

spike:
	python3 -m src.trigger_spike --ticker $(or $(TICKER),NVDA)

eod-check:
	python3 -m src.scraper.eod_checker $(if $(TICKER),--simulate-busy $(TICKER),)
