.PHONY: install up down seed demo scan recorded test e2e verify

PY=.venv/bin/python
PYTEST=.venv/bin/pytest
UVICORN=.venv/bin/uvicorn
PORT?=8000

# One-time setup: virtualenv, dependencies, Playwright browser.
install:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	npm install
	npx playwright install chromium

# Run the backend and the web chat at http://localhost:$(PORT)
up:
	$(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --reload

down:
	@pkill -f "uvicorn app.main:app" || true

# Load demo/ into SQLite (idempotent).
seed:
	$(PY) -m app.seed

# Reset the database to the seeded demo state.
demo:
	$(PY) scripts/demo.py

# Run the deadline scan once (same function as the Serverless Job).
scan:
	$(PY) jobs/scan.py

# Run the backend in recorded mode (no Nebius or Tavily calls).
recorded:
	RECORDED_MODE=true $(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT)

# Unit and integration tests against a real SQLite file.
test:
	$(PYTEST) -v

# Starts the backend in recorded mode, runs Playwright, stops the backend.
# E2E uses recorded responses so results do not depend on the network.
e2e:
	@RECORDED_MODE=true DATABASE_PATH=./.e2e.db $(PY) -m app.seed
	@RECORDED_MODE=true DATABASE_PATH=./.e2e.db $(UVICORN) app.main:app --port $(PORT) > .e2e-server.log 2>&1 & echo $$! > .e2e-server.pid
	@ok=0; for i in $$(seq 1 30); do \
		if curl -sf http://127.0.0.1:$(PORT)/api/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" != "1" ]; then echo "api not ready"; kill `cat .e2e-server.pid` 2>/dev/null; exit 1; fi
	@npx playwright test; status=$$?; \
	kill `cat .e2e-server.pid` 2>/dev/null; rm -f .e2e-server.pid .e2e.db; \
	exit $$status

# Full run plus the T1-T23 report in reports/verify-<timestamp>.md
verify:
	@mkdir -p reports
	@TS=$$(date +%Y%m%d-%H%M%S); \
	JUNIT=reports/pytest-$$TS.xml; \
	PWJSON=reports/playwright-$$TS.json; \
	OUT=reports/verify-$$TS.md; \
	echo "=== pytest -> $$JUNIT ==="; \
	$(PYTEST) -v --junitxml=$$JUNIT; PY_RC=$$?; \
	echo "=== e2e -> $$PWJSON ==="; \
	RECORDED_MODE=true DATABASE_PATH=./.e2e.db $(PY) -m app.seed; \
	(RECORDED_MODE=true DATABASE_PATH=./.e2e.db $(UVICORN) app.main:app --port $(PORT) > .e2e-server.log 2>&1 & echo $$! > .e2e-server.pid); \
	ok=0; for i in $$(seq 1 30); do \
		if curl -sf http://127.0.0.1:$(PORT)/api/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" != "1" ]; then echo "api not ready"; kill `cat .e2e-server.pid` 2>/dev/null; exit 1; fi; \
	npx playwright test --reporter=json > $$PWJSON; E2E_RC=$$?; \
	kill `cat .e2e-server.pid` 2>/dev/null; rm -f .e2e-server.pid .e2e.db; \
	$(PY) scripts/verify_report.py --junit $$JUNIT --playwright $$PWJSON --out $$OUT \
		--pytest-rc $$PY_RC --e2e-rc $$E2E_RC; \
	echo "report: $$OUT"; \
	if [ $$PY_RC -ne 0 ] || [ $$E2E_RC -ne 0 ]; then exit 1; fi
