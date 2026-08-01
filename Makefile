%:
	@:

TARGET_ARGS = $(filter-out $@,$(MAKECMDGOALS))
NPM ?= npm
PYTHON_RUN ?= uv run python
PYTEST_RUN ?= uv run pytest
MUTMUT_RUN ?= uv run mutmut
PYSCN_VERSION ?= 1.24.0
TYPE_CHECK_PATHS = \
	apps/api/schemas.py \
	apps/core/agents/base.py \
	apps/core/ai_observability.py \
	apps/core/model_utils.py \
	apps/core/notifications.py \
	apps/mcp_server/server.py \
	apps/pages/services.py \
	apps/search/qdrant.py \
	citeguild/logging_utils.py \
	citeguild/sentry_utils.py
PYSCN_PATHS ?= apps citeguild manage.py
COVERAGE_FAIL_UNDER ?= 0
COVERAGE_RUN ?= uv run --with coverage coverage run --source=apps,citeguild -m pytest
COVERAGE_REPORT ?= uv run --with coverage coverage report -m --fail-under=$(COVERAGE_FAIL_UNDER)
HIGH_RISK_COVERAGE_FILES = \
	apps/api/services.py \
	apps/api/views.py \
	apps/core/models.py \
	apps/core/utils.py \
	apps/core/views.py
PGSANDBOX_EXTENSION_MIGRATION ?= core 0001_enable_extensions
PGSANDBOX_EXTENSION_MIGRATION_FILE ?= apps/core/migrations/0001_enable_extensions.py
PGSANDBOX_TEST_ENV = PYTHONPATH=. ENVIRONMENT=test DEBUG=0 SECRET_KEY=test-secret-key SITE_URL=http://localhost:8000 REDIS_HOST=127.0.0.1 REDIS_PORT=6379 REDIS_PASSWORD= REDIS_DB=0 MAILGUN_API_KEY= AWS_S3_ENDPOINT_URL=
LOCAL_WEB_PORT ?= 8000
LOCAL_POSTGRES_PORT ?= 5432
LOCAL_REDIS_PORT ?= 6379
LOCAL_MAILHOG_SMTP_PORT ?= 1025
LOCAL_MAILHOG_UI_PORT ?= 8025

LOCAL_MJML_PORT ?= 15500


LOCAL_MINIO_API_PORT ?= 9000
LOCAL_MINIO_CONSOLE_PORT ?= 9001

DJANGO_RUNSERVER_HOST ?= 0.0.0.0
DJANGO_RUNSERVER_PORT ?= $(LOCAL_WEB_PORT)
LOCAL_COMPOSE_SERVICES = db redis mailhog mjml minio
DOCKER_COMPOSE = docker compose -f docker-compose-local.yml

.PHONY: \
	api-fuzz \
	ci-local \
	coverage \
	coverage-high-risk \
	django-check \
	format-check \
	frontend-check \
	frontend-install \
	agent-services \
	agent-services-down \
	lint-python \
	makemigrations \
	manage \
	migrations-check \
	migrate \
	mutation-high-risk \
	mutation-results \
	python-quality \
	pytest-check \
	pyscn-analyze \
	pyscn-check \
	restart-worker \
	serve \
	shell \
	terminal-assets \
	terminal-makemigrations \
	terminal-manage \
	terminal-migrate \
	terminal-setup \
	terminal-shell \
	terminal-test \
	terminal-web \
	terminal-worker \
	test \
	test-local-postgres \
	template-check \
	type-check

serve:
	$(DOCKER_COMPOSE) up -d --build
	$(DOCKER_COMPOSE) logs -f backend

agent-services:
	$(DOCKER_COMPOSE) up -d $(LOCAL_COMPOSE_SERVICES)
	$(DOCKER_COMPOSE) run --rm createbuckets

agent-services-down:
	$(DOCKER_COMPOSE) stop $(LOCAL_COMPOSE_SERVICES)

terminal-setup:
	uv sync --locked
	npm ci
	npm run build

terminal-web:
	uv run python manage.py migrate
	uv run uvicorn citeguild.asgi:application --host $(DJANGO_RUNSERVER_HOST) --port $(DJANGO_RUNSERVER_PORT) --reload

terminal-worker:
	uv run python manage.py qcluster

terminal-assets:
	npm run watch

terminal-manage:
	uv run python manage.py $(TARGET_ARGS)

terminal-makemigrations:
	uv run python manage.py makemigrations

terminal-migrate:
	uv run python manage.py migrate

terminal-test:
	uv run pytest $(TARGET_ARGS)

terminal-shell:
	uv run python manage.py shell_plus --ipython

api-fuzz:
	$(PYTEST_RUN) apps/api/test_schema.py $(TARGET_ARGS)

shell:
	$(DOCKER_COMPOSE) run --rm backend uv run --no-sync python ./manage.py shell_plus --ipython

manage:
	$(DOCKER_COMPOSE) run --rm backend uv run --no-sync python ./manage.py $(TARGET_ARGS)

makemigrations:
	$(DOCKER_COMPOSE) run --rm backend uv run --no-sync python ./manage.py makemigrations

migrate:
	$(DOCKER_COMPOSE) run --rm backend uv run --no-sync python ./manage.py migrate

test:
	$(DOCKER_COMPOSE) run --rm backend uv run --no-sync pytest $(TARGET_ARGS)

ci-local:
	$(MAKE) python-quality
	$(MAKE) type-check
	$(MAKE) frontend-check
	$(MAKE) migrations-check
	$(MAKE) django-check
	$(MAKE) coverage-high-risk -- -q

python-quality:
	uv run pre-commit run --all-files --show-diff-on-failure
	$(MAKE) pyscn-check

frontend-install:
	$(NPM) ci

frontend-check:
	$(NPM) run lint
	$(NPM) run build

lint-python:
	uv run ruff check --force-exclude .

format-check:
	uv run ruff format --check --force-exclude .

template-check:
	uv run djlint --profile=django --check frontend/templates

migrations-check:
	$(PYTHON_RUN) manage.py makemigrations --check --dry-run

django-check:
	$(PYTHON_RUN) manage.py check

pytest-check:
	$(PYTEST_RUN) $(TARGET_ARGS)

coverage:
	$(COVERAGE_RUN) $(TARGET_ARGS)
	$(COVERAGE_REPORT)

coverage-high-risk:
	$(COVERAGE_RUN) $(TARGET_ARGS)
	$(COVERAGE_REPORT) $(HIGH_RISK_COVERAGE_FILES)

mutation-high-risk:
	$(MUTMUT_RUN) run $(TARGET_ARGS)

mutation-results:
	$(MUTMUT_RUN) results

type-check:
	uv run ty check $(TYPE_CHECK_PATHS)

test-local-postgres:
	@if [ -z "$$DATABASE_URL" ]; then \
		echo "DATABASE_URL is required. Ask an MCP-capable agent to create a PGSandbox database, then run DATABASE_URL='<connection-string>' make test-local-postgres"; \
		exit 2; \
	fi
	@if [ ! -f "$(PGSANDBOX_EXTENSION_MIGRATION_FILE)" ]; then \
		echo "Expected extension migration file $(PGSANDBOX_EXTENSION_MIGRATION_FILE) was not found. Update PGSANDBOX_EXTENSION_MIGRATION before running this target."; \
		exit 2; \
	fi
	$(PGSANDBOX_TEST_ENV) uv run python manage.py makemigrations --check --dry-run
	$(PGSANDBOX_TEST_ENV) uv run python manage.py migrate $(PGSANDBOX_EXTENSION_MIGRATION) --fake
	$(PGSANDBOX_TEST_ENV) uv run python manage.py migrate --noinput
	$(PGSANDBOX_TEST_ENV) uv run python manage.py check
	$(PGSANDBOX_TEST_ENV) DJANGO_TEST_USE_EXISTING_DATABASE=1 uv run pytest --reuse-db $(TARGET_ARGS)

pyscn-check:
	uvx pyscn@$(PYSCN_VERSION) check --skip-clones $(PYSCN_PATHS)

pyscn-analyze:
	uvx pyscn@$(PYSCN_VERSION) analyze --no-open $(PYSCN_PATHS)

restart-worker:
	$(DOCKER_COMPOSE) up -d workers --force-recreate
