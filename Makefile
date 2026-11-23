SHELL := /bin/bash
export PATH := $(CURDIR)/.tools/node/bin:$(PATH)
export UV_CACHE_DIR := $(CURDIR)/.cache/uv
export UV_PYTHON_INSTALL_DIR := $(CURDIR)/.tools/python

.PHONY: setup dev run build test check smoke browser-setup e2e docker-up docker-down
setup:
	uv sync --python 3.13
	cd frontend && npm --cache ../.cache/npm ci
dev:
	.venv/bin/python scripts/dev.py
run:
	.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
build:
	cd frontend && npm run build
test:
	.venv/bin/python -m pytest -q
	cd frontend && npm test
check:
	.venv/bin/python scripts/verify_vendor.py
	.venv/bin/ruff check app tests scripts
	.venv/bin/ruff format --check app tests scripts
	$(MAKE) build
smoke:
	.venv/bin/python scripts/smoke.py
e2e:
	cd frontend && PLAYWRIGHT_BROWSERS_PATH=../.cache/playwright npm run test:e2e
browser-setup:
	cd frontend && PLAYWRIGHT_BROWSERS_PATH=../.cache/playwright npx playwright install chromium
docker-up:
	docker compose up --build -d
docker-down:
	docker compose down
