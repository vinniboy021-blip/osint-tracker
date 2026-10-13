SHELL := /bin/bash
COMPOSE ?= docker compose
PYTHON ?= .venv/bin/python
EMAIL ?=
BACKUP ?=
.PHONY: setup install up prod down restart logs health migrate admin backup restore purge test integration e2e lint audit check connectors
setup:
	python3 scripts/setup_env.py
install:
	python3 -m venv .venv
	.venv/bin/pip install -e 'apps/api[dev]'
	cd apps/web && npm ci
up:
	$(COMPOSE) up -d --build
prod:
	$(COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d --build
down:
	$(COMPOSE) down
restart:
	$(COMPOSE) restart
logs:
	$(COMPOSE) logs --tail=100 -f
health:
	$(COMPOSE) ps
	curl --fail --silent http://localhost:$${API_PORT:-8000}/ready
migrate:
	$(COMPOSE) run --rm migrate
admin:
	@test -n "$(EMAIL)" || (echo 'Use make admin EMAIL=administrador@example.org'; exit 1)
	$(COMPOSE) exec api python -m app.cli create-admin --email "$(EMAIL)"
backup:
	python3 scripts/backup.py $(if $(BACKUP),"$(BACKUP)",)
restore:
	@test -n "$(BACKUP)" || (echo 'Use make restore BACKUP=/caminho/do/backup'; exit 1)
	python3 scripts/restore.py "$(BACKUP)" --replace-data
purge:
	PYTHONPATH=apps/api $(PYTHON) scripts/purge_expired_evidence.py
test:
	cd apps/api && ../../$(PYTHON) -m pytest
connectors:
	cd apps/api && ../../$(PYTHON) -m pytest tests/test_connectors_contract.py
integration:
	cd apps/api && RUN_INTEGRATION=1 ../../$(PYTHON) -m pytest -m integration
e2e:
	cd apps/web && npm run test:e2e
lint:
	$(PYTHON) -m ruff check apps/api
	$(PYTHON) -m mypy apps/api/app
	cd apps/web && npm run lint && npm run typecheck
audit:
	$(PYTHON) -m pip_audit
	cd apps/web && npm audit --audit-level=high
check: lint test
