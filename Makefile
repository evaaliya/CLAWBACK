.PHONY: install up down serve seed demo scan recorded test e2e verify \
	docker-build docker-run docker-smoke

PY=.venv/bin/python
PYTEST=.venv/bin/pytest
UVICORN=.venv/bin/uvicorn
PORT?=8000
IMAGE?=clawback:local
SMOKE_NAME?=clawback-smoke
SMOKE_PORT?=8010

# One-time setup: virtualenv, dependencies, Playwright browser.
install:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	npm install
	npx playwright install chromium

# Run the backend and the web chat at http://localhost:$(PORT)
up:
	$(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --reload

# Production-like local serve (no reload; one worker like the container).
serve:
	$(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT) --workers 1

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
	RECORDED_MODE=true DEMO_RESET=enabled $(UVICORN) app.main:app --host 0.0.0.0 --port $(PORT)

# Unit and integration tests against a real SQLite file.
test:
	$(PYTEST) -v

# Starts the backend in recorded mode, runs Playwright, stops the backend.
# E2E uses demo/recorded responses so results do not depend on the network.
e2e:
	@rm -f .e2e.db .e2e.db-wal .e2e.db-shm
	@RECORDED_MODE=true DEMO_RESET=enabled LIVE_API_RATE_LIMIT=1000 DATABASE_PATH=./.e2e.db $(PY) -m app.seed
	@RECORDED_MODE=true DEMO_RESET=enabled LIVE_API_RATE_LIMIT=1000 DATABASE_PATH=./.e2e.db $(UVICORN) app.main:app --port $(PORT) > .e2e-server.log 2>&1 & echo $$! > .e2e-server.pid
	@ok=0; for i in $$(seq 1 30); do \
		if curl -sf http://127.0.0.1:$(PORT)/api/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" != "1" ]; then echo "api not ready"; cat .e2e-server.log; kill `cat .e2e-server.pid` 2>/dev/null; exit 1; fi
	@PLAYWRIGHT_BASE_URL=http://127.0.0.1:$(PORT) npx playwright test; status=$$?; \
	kill `cat .e2e-server.pid` 2>/dev/null; rm -f .e2e-server.pid .e2e.db .e2e.db-wal .e2e.db-shm; \
	exit $$status

# Full run plus the T1-T27 report in reports/verify-<timestamp>.md
verify:
	@mkdir -p reports
	@TS=$$(date +%Y%m%d-%H%M%S); \
	JUNIT=reports/pytest-$$TS.xml; \
	PWJSON=reports/playwright-$$TS.json; \
	OUT=reports/verify-$$TS.md; \
	echo "=== pytest -> $$JUNIT ==="; \
	$(PYTEST) -v --junitxml=$$JUNIT; PY_RC=$$?; \
	echo "=== e2e -> $$PWJSON ==="; \
	rm -f .e2e.db .e2e.db-wal .e2e.db-shm; \
	RECORDED_MODE=true DEMO_RESET=enabled LIVE_API_RATE_LIMIT=1000 DATABASE_PATH=./.e2e.db $(PY) -m app.seed; \
	(RECORDED_MODE=true DEMO_RESET=enabled LIVE_API_RATE_LIMIT=1000 DATABASE_PATH=./.e2e.db $(UVICORN) app.main:app --port $(PORT) > .e2e-server.log 2>&1 & echo $$! > .e2e-server.pid); \
	ok=0; for i in $$(seq 1 30); do \
		if curl -sf http://127.0.0.1:$(PORT)/api/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" != "1" ]; then echo "api not ready"; cat .e2e-server.log; kill `cat .e2e-server.pid` 2>/dev/null; exit 1; fi; \
	PLAYWRIGHT_BASE_URL=http://127.0.0.1:$(PORT) npx playwright test --reporter=json > $$PWJSON; E2E_RC=$$?; \
	kill `cat .e2e-server.pid` 2>/dev/null; rm -f .e2e-server.pid .e2e.db .e2e.db-wal .e2e.db-shm; \
	$(PY) scripts/verify_report.py --junit $$JUNIT --playwright $$PWJSON --out $$OUT \
		--pytest-rc $$PY_RC --e2e-rc $$E2E_RC; \
	echo "report: $$OUT"; \
	if [ $$PY_RC -ne 0 ] || [ $$E2E_RC -ne 0 ]; then exit 1; fi

docker-build:
	docker build -t $(IMAGE) .

# Maps host 8000 → container 8000; passes through a local .env when present.
docker-run: docker-build
	@docker rm -f clawback-run >/dev/null 2>&1 || true
	docker run --name clawback-run --rm -p 8000:8000 \
		--env-file .env \
		-e DATABASE_PATH=/data/clawback.db \
		$(IMAGE)

# Build, run recorded container, curl health, Playwright Golden Path, stop.
docker-smoke:
	@docker rm -f $(SMOKE_NAME) >/dev/null 2>&1 || true
	docker build -t $(IMAGE) .
	docker run -d --name $(SMOKE_NAME) -p $(SMOKE_PORT):8000 \
		-e RECORDED_MODE=true \
		-e DEMO_RESET=enabled \
		-e LIVE_API_RATE_LIMIT=1000 \
		-e DATABASE_PATH=/data/clawback.db \
		-e DEMO_TODAY=2026-10-27 \
		$(IMAGE)
	@ok=0; for i in $$(seq 1 60); do \
		if curl -sf http://127.0.0.1:$(SMOKE_PORT)/api/health >/dev/null; then ok=1; break; fi; \
		sleep 1; \
	done; \
	if [ "$$ok" != "1" ]; then echo "container not ready"; docker logs $(SMOKE_NAME); docker rm -f $(SMOKE_NAME); exit 1; fi
	@curl -sf http://127.0.0.1:$(SMOKE_PORT)/api/health | tee /tmp/clawback-smoke-health.json
	@echo
	@PLAYWRIGHT_BASE_URL=http://127.0.0.1:$(SMOKE_PORT) npx playwright test; status=$$?; \
	docker rm -f $(SMOKE_NAME) >/dev/null 2>&1; \
	exit $$status
